# -*- coding: utf-8 -*-
"""
This file contains the main ProteusQ logic.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""


from core.module import Connector, StatusVar, ConfigOption
from logic.generic_logic import GenericLogic
from core.util import units
from core.util.mutex import Mutex
import threading
import numpy as np
import os
import time
import datetime
import matplotlib.pyplot as plt
import math
from .. import gwyfile as gwy

from deprecation import deprecated

from qtpy import QtCore

import traceback
import sys

#TODO: Write this to its own file because this is a pretty general way of 
#      creating Threaded objects/methods.
#
# this implementation was adapted from here:
#https://www.learnpyqt.com/tutorials/multithreading-pyqt-applications-qthreadpool/

class WorkerThread(QtCore.QRunnable):
    """ Create a simple Worker Thread class, with a similar usage to a python
    Thread object. This Runnable Thread object is indented to be run from a
    QThreadpool.

    @param obj_reference target: A reference to a method, which will be executed
                                 with the given arguments and keyword arguments.
                                 Note, if no target function or method is passed
                                 then nothing will be executed in the run
                                 routine. This will serve as a dummy thread.
    @param tuple args: Arguments to make available to the run code, should be
                       passed in the form of a tuple
    @param dict kwargs: Keywords arguments to make available to the run code
                        should be passed in the form of a dict
    @param str name: optional, give the thread a name to identify it.

    Signals:
        sigFinished(): will be fired if measurement is finished
        sigError(tuple): contains error in the form tuple(exctype, value, traceback.format_exc() )
        sigResult(object): contains the data of the result of the target function
        sigProgress(int): can be used to indicate progress
    """

    # signals of these object
    sigFinished = QtCore.Signal()
    sigError = QtCore.Signal(tuple)
    sigResult = QtCore.Signal(object)
    sigProgress = QtCore.Signal(int)

    #FIXME: change function signature to something like (self, target=None, name='', *args, **kwargs)
    def __init__(self, target=None, args=(), kwargs={}, name=''):
        super(WorkerThread, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.target = target
        self.args = args
        self.kwargs = kwargs

        if name == '':
            name = str(self.get_thread_obj_id())

        self.name = name
        self._is_running = False

    def get_thread_obj_id(self):
        """ Get the ID from the current thread object. """

        return id(self)

    @QtCore.Slot()
    def run(self):
        """ Initialise the runner function with passed self.args, self.kwargs."""

        try:
            if self.target is None:
                return

            self._is_running = True
            result = self.target(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.sigError.emit((exctype, value, traceback.format_exc()))
        else:
            self.sigResult.emit(result)  # Return the result of the processing
        finally:
            self.sigFinished.emit()  # Done
            
        self._is_running = False

    def is_running(self):
        return self._is_running

    def autoDelete(self):
        """ Delete the thread. """
        self._is_running = False
        return super(WorkerThread, self).autoDelete()


class ScanLogic(GenericLogic):
    """ Main Scanning logic of the ProteusQ. """


    _modclass = 'ScanLogic'
    _modtype = 'logic'

    # declare connectors. It is either a connector to be connected to another
    # logic or another hardware. Hence the interface variable will take either 
    # the name of the logic class (for logic connection) or the interface class
    # which is implemented in a hardware instrument (for a hardware connection)

    # logic modules
    save_logic = Connector(interface='SaveLogic')  # logic example
    counter_logic = Connector(interface='CounterLogic')
    fit_logic = Connector(interface='FitLogic')

    # placeholders for the actual logic objects
    _savelogic = None
    _counterlogic = None
    _fitlogic = None

    # hardware modules
    spm_device = Connector(interface='SPMInterface') # hardware example
    recorder_device = Connector(interface='RecorderInterface')
    slow_counter_device =  Connector(interface='SlowCounterInterface')
    mw_device = Connector(interface='RecorderInterface')

    # for the special case of microwaveq, the three devices recorder, 
    # slow_counter and mw are the same object. To make interface separation
    # clear, it will be accessed through different access points (but it will 
    # be still the same object, but only the interface methods are allowed to be 
    # used).

    # placeholders for the actual hardware objects
    _spm = None
    _recorder = None
    _counter = None
    _mw_gen = None

    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        # locking mechanism for thread safety. 
        self.threadlock = Mutex()

        # use it like this:
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.

        # checking for the right configuration
        for key in config.keys():
            self.log.debug('{0}: {1}'.format(key, config[key]))

    def on_activate(self):
        """ Initialization performed during activation of the module. """

        # Create the access to the hardware objects
        self._spm = self.spm_device()
        self._recorder = self.recorder_device()
        self._counter = self.slow_counter_device()
        self._mw_gen = self.mw_device()

        # create the access to the logic objects
        self._savelogic = self.save_logic()
        self._counterlogic = self.counter_logic()
        self._fitlogic = self.fit_logic()

    def on_deactivate(self):
        """ Deinitializations performed during deactivation of the module. """

        pass
