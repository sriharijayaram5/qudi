# -*- coding: utf-8 -*-
"""
Dummy implementation for the microwaveq device.

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

from datetime import datetime
from qtpy import QtCore
import threading
import numpy as np
import time
import struct

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from interface.slow_counter_interface import SlowCounterInterface, SlowCounterConstraints, CountingMode
from .microwaveq_py.microwaveQ import microwaveQ

from interface.microwave_interface import MicrowaveInterface
from interface.microwave_interface import MicrowaveLimits
from interface.microwave_interface import MicrowaveMode
from interface.microwave_interface import TriggerEdge


# Interfaces to implement:
# SlowCounterInterface, RecorderInterface, MicrowaveInterface, ODMRCounterInterface
#   Question: SwitchInterface for GPIO???

class MicrowaveQDummy(Base):
    """ A simple Data generator dummy.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'simple_data_dummy.SimpleDummy'
        ip_address: '192.168.2.10'
        port: 55555
        unlock_key: <your obtained key, either in hex or number> e.g. of the form: 51233412369010369791345065897427812359

    """

    _modclass = 'MicrowaveQDummy'
    _modtype = 'hardware'

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass


    # RecorderInterface:

    """
    prepare_pixelclock
    prepare_pixelclock_single_iso_b
    arm_device
    get_line
    stop_measurement
        get_counter() ==> NOT USED!!
    prepare_cw_esr
    start_esr
    get_esr_meas
    get_device_mode
    is_measurement_running
    meas_cond   => should be not accessed!!

    #TODO: GPI and GPO control !!!
    """



