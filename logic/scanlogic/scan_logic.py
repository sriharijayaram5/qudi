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


class ScanLogic(GenericLogic):
    """ Main AFM logic class providing advanced measurement control. """


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
