# -*- coding: utf-8 -*-
"""
Dummy implementation for spm devices.

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

import os
import ctypes
import numpy as np
import time
import threading
import copy

from qtpy import QtCore

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from enum import IntEnum


# Interfaces to implement:
# SPMInterface

class SPMDummy(Base):
    """ Smart SPM wrapper for the communication with the module.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'smart_spm.SmartSPM'
        libpath: 'path/to/lib/folder'

    """

    _modclass = 'SPMDummy'
    _modtype = 'hardware'

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
        """ Prepare and activate the spm module. """

        pass

    def on_deactivate(self):
        """ Clean up and deactivate the spm module. """
        pass


    # SPMInterface

    """
    get_meas_params
    create_scan_leftright
    create_scan_leftright2
    create_scan_snake
    setup_spm
    set_ext_trigger
    check_spm_scan_params_by_plane
    setup_scan_line
    scan_line
    get_scanned_line
    finish_scan
    scan_point
    get_objective_scanner_pos
    set_objective_scanner_pos
    get_sample_scanner_pos
    set_sample_scanner_pos

    """ 