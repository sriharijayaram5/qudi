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
from interface.odmr_counter_interface import ODMRCounterInterface
from interface.microwave_interface import MicrowaveInterface, MicrowaveLimits, MicrowaveMode, TriggerEdge
from interface.recorder_interface import RecorderInterface, RecorderMode, RecorderState, RecorderConstraints

from .microwaveq_py.microwaveQ import microwaveQ

class MicrowaveQDummy(Base, SlowCounterInterface, ODMRCounterInterface, RecorderInterface):
    """ A simple Data generator dummy.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'simple_data_dummy.SimpleDummy'
        ip_address: '192.168.2.10'
        port: 55555
        unlock_key: <your obtained key, either in hex or number> e.g. of the form: 51233412369010369791345065897427812359

    """
    __version__ = '0.1.0'
    _modclass = 'MicrowaveQDummy'
    _modtype = 'hardware'

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass

# SlowCounterInterface methods

    def get_constraints(self):
        pass

    def set_up_clock(self, clock_frequency=None, clock_channel=None):
        pass

    def set_up_counter(self,
                       counter_channels=None,
                       sources=None,
                       clock_channel=None,
                       counter_buffer=None):
        pass

    def get_counter(self, samples=None):
        pass

    def get_counter_channels(self):
        pass

    def close_counter(self):
        pass

    def close_clock(self):
        pass

# ODMRCounterInterface methods

    def set_up_odmr_clock(self, clock_frequency=None, clock_channel=None):
        pass

    def set_up_odmr(self, counter_channel=None, photon_source=None):
        pass

    def set_odmr_length(self, length=100):
        pass

    def count_odmr(self, length=100):
        pass
    
    def close_odmr(self):
        pass

    def close_odmr_clock(self):
        pass

    def get_odmr_channels(self):
        pass

    @property
    def oversampling(self):
        return False

    @oversampling.setter
    def oversampling(self, val):
        pass

    @property
    def lock_in_active(self):
        return False

    @lock_in_active.setter
    def lock_in_active(self, val):
        pass


# MicrowaveInteface methods

    def off(self):
        pass

    def get_status(self):
        pass

    def get_power(self):
        pass

    def get_frequency(self):
        pass
    
    def cw_on(self):
        pass
    
    def set_cw(self, frequency=None, power=None):
        pass
    
    def list_on(self):
        pass
    
    def set_list(self, frequency=None, power=None):
        pass
    
    def reset_listpos(self):
        pass
    
    def sweep_on(self):
        pass
    
    def set_sweep(self, start=None, stop=None, step=None, power=None):
        pass
    
    def reset_sweeppos(self):
        pass
    
    def set_ext_trigger(self, pol, timing):
        pass
    
    def trigger(self):
        pass
    
    def get_limits(self):
        pass
    
    def frequency_in_range(self, frequency):
        pass

    def power_in_range(self, power):
        pass
    
    def list_step_in_range(self, step):
        pass
    
    def sweep_step_in_range(self, step):
        pass
    
    def slope_in_range(self, slope):
        pass
    
# RecorderInterface methods

    def configure_recorder(mode, params):
        pass

    def start_recorder(arm=True):
        pass
    
    def get_measurment():
        pass
    
    def stop_measurement():
        pass
    
    def get_parameter_for_modes(mode=None):
        pass
    
    def get_current_device_mode():
        pass
    
    def get_current_device_state():
        pass
    

# Interfaces to implement:
# SlowCounterInterface, RecorderInterface, MicrowaveInterface, ODMRCounterInterface
#   Question: SwitchInterface for GPIO???

#class MicrowaveQDummy(Base):
#    """ A simple Data generator dummy.
#
#    Example config for copy-paste:
#
#    simple_data_dummy:
#        module.Class: 'simple_data_dummy.SimpleDummy'
#        ip_address: '192.168.2.10'
#        port: 55555
#        unlock_key: <your obtained key, either in hex or number> e.g. of the form: 51233412369010369791345065897427812359
#
#    """
#
#    _modclass = 'MicrowaveQDummy'
#    _modtype = 'hardware'
#
#    def on_activate(self):
#        pass
#
#    def on_deactivate(self):
#        pass
#
#
#    # RecorderInterface:
#
#    """
#    prepare_pixelclock                  => configure_recorder(mode, params)
#    prepare_pixelclock_single_iso_b
#
#    arm_device  => start_recorder(arm=True)
#
#    get_line
#    stop_measurement
#        get_counter() ==> NOT USED!!
#    
#    prepare_cw_esr
#    start_esr
#    get_esr_meas
#    
#    get_device_mode
#    is_measurement_running
#    meas_cond   => should be not accessed!!
#
#    #TODO: GPI and GPO control !!!
#    """
#
#
#    # Interface methods
#    """
#    configure_recorder(mode, params)
#    start_recorder(arm=True)
#    get_measurement()  => blocking method, either with timeout or stoppable via stop measurement
#    stop_measurement()  => hardcore stop mechanism
#
#    get_parameter_for_modes()   => obtain the required parameter for the current mode
#    get_current_device_mode()
#    get_current_device_state()
#    """
#
#    # OPERATION_MODES   => get_available_recorder_modes()  can be also configured in DUMMY or UNCONFIGURED
#    """
#    PIXELCLOCK                  
#    PIXELCLOCK_SINGLE_ISO_B
#    PIXELCLOCK_N_ISO_B
#
#    CW_MW
#    ESR
#    PULSED_ESR
#    COUNTER
#
#    PULSED
#    """
#
#    #RECORDER_STATE     => get_recorder_state()
#    """
#    DISCONNECTED
#    IDLE
#    ARMED => whenever new data arrives switch to BUSY
#    BUSY => whenever finished with data switch to idle
#    """
#
#
#
#    # Modes which are used in MicrowaveQ, these are implemented in logic
#    """
#    optimizer
#    confocal
#    quenching
#    single-iso-b
#    dual-iso-b
#    full-b 
#    """
