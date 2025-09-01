# -*- coding: utf-8 -*-

"""
A central module to control the default settings for all pulsed measurements done by the PODMR, QAFM, and jupyter_pulsed_AWG_master_logic.

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

import numpy as np
from collections import OrderedDict
import datetime
from decimal import Decimal

from core.connector import Connector
from core.statusvariable import StatusVar
from core.configoption import ConfigOption
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore


class PulsedSettingsLogic(GenericLogic):
    """ Logic module to control the default settings for all pulsed measurements done by the PODMR, QAFM, and jupyter_pulsed_AWG_master_logic
        This logic includes all settings for pulsed measurements, which are not changed frequently.

    Example config:

    pulsedsettingslogic:
        module.Class: 'pulsed_settings_logic.PulsedSettingsLogic'
        

    """

    # status vars
    awg_sync_time = StatusVar('awg_sync_time', 16e-9 + 476.5/1.25e9) #Has to be determined with sample clock
    laser_waiting_time = StatusVar('laser_waiting_time', 1.5e-6) 
    mw_waiting_time = StatusVar('mw_waiting_time', 0.1e-6) 
    read_out_time = StatusVar('read_out_time', 3e-6) 
    add_tt_read_out = StatusVar('add_tt_read_out', 0.6e-6)
    bin_width = StatusVar('bin_width', 1e-9)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """

        self.awg_sync_time = 16e-9 + 476.5/1.25e9 #Has to be determined with sample clock
        self.laser_waiting_time= 0.2e-6 #1e-6
        self.mw_waiting_time= 15e-6 #0.1e-6
        self.read_out_time= 50e-6 #20e-6 #3e-6
        self.add_tt_read_out = 0
        self.bin_width = 1e-9

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass
