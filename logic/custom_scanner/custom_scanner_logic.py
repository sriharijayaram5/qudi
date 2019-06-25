# -*- coding: utf-8 -*-
"""
This file contains the Qudi logic <####>.

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
from core.util.mutex import Mutex

from qtpy import QtCore

class CustomScannerLogic(GenericLogic):
    """ This is a skeleton for a logic module. """


    _modclass = 'CustomScannerLogic'
    _modtype = 'logic'


    test_sig = QtCore.Signal()

    ## declare connectors. It is either a connector to be connected to another 
    # logic or another hardware. Hence the interface variable will take either 
    # the name of the logic class (for logic connection) or the interface class
    # which is implemented in a hardware instrument (for a hardware connection)
    spm_device = Connector(interface='CustomScanner') # hardware example
    savelogic = Connector(interface='SaveLogic')  # logic example

    ## configuration parameters/options for the logic. In the config file you 
    # have to specify the parameter, here: 'conf_1'
    #_conf_1 = ConfigOption('conf_1', missing='error')

    # status variables, save status of certain parameters if object is 
    # deactivated.
    #_count_length = StatusVar('count_length', 300)


    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        # locking mechanism for thread safety. Use it like
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.
        self.threadlock = Mutex()

        # checking for the right configuration
        for key in config.keys():
            self.log.debug('{0}: {1}'.format(key, config[key]))

    def on_activate(self):
        """ Initialization performed during activation of the module. """

        # Connect to hardware and save logic
        self._spm = self.spm_device()
        self._save_logic = self.savelogic()


        self.test_sig.connect(self.perform)

    def on_deactivate(self):
        """ Deinitializations performed during deactivation of the module. """

        pass


    def perform(self):
        self._spm.test_another()
