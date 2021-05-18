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
from interface.recorder_interface import RecorderInterface
from qtpy import QtCore
import threading
import numpy as np
import time
import struct
from enum import Enum, auto

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from interface.slow_counter_interface import SlowCounterInterface, SlowCounterConstraints, CountingMode
from interface.odmr_counter_interface import ODMRCounterInterface
from interface.microwave_interface import MicrowaveInterface, MicrowaveLimits, MicrowaveMode, TriggerEdge
from interface.recorder_interface import RecorderInterface, RecorderMode, RecorderState, RecorderConstraints

from .microwaveq_py.microwaveQ import microwaveQ

# --------------------------------------
# Notes:
#  - This is derived from the "microwaveq_dummy.py".  Here, the fulfillment of the dummy methods takes place
#  - The intent is to create a working dummy here, based on the templates from ODMR_dummy, OOP logic, etc.
#  - The fullfillment with real hardware should take place in "microwaveq_new.py" 
#    (later, change to just "microwaveq.py", when all modifications are complete)
# --------------------------------------

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

    # specific interface variables
    _meas_running = False

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
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of the
                                      clock
        @param str clock_channel: if defined, this is the physical channel of
                                  the clock

        @return int: error code (0:OK, -1:error)
        """

        if clock_frequency is not None:
            self._esr_count_frequency = clock_frequency

        if self._meas_running:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

        return 0


    def set_up_odmr(self, counter_channel=None, photon_source=None):
        """ Configures the actual counter with a given clock.

        @param str counter_channel: if defined, this is the physical channel of
                                    the counter
        @param str photon_source: if defined, this is the physical channel where
                                  the photons are to count from
        @param str clock_channel: if defined, this specifies the clock for the
                                  counter
        @param str odmr_trigger_channel: if defined, this specifies the trigger
                                         output for the microwave

        @return int: error code (0:OK, -1:error)
        """
        return 0


    def set_odmr_length(self, length=100):
        pass

    def count_odmr(self, length=100):
        pass

    def close_odmr(self):
        pass

    def close_odmr_clock(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return 0


    def get_odmr_channels(self):
        """ Return a list of channel names.

        @return list(str): channels recorded during ODMR measurement
        """
        return ['ch0']


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
        """ Switches off any microwave output.

        @return int: error code (0:OK, -1:error)
        """
        self.output_active = False
        self.log.info('MicrowaveDummy>off')
        return         


    def get_status(self):
        """
        Gets the current status of the MW source, i.e. the mode (cw, list or sweep) and
        the output state (stopped, running)

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        if self.current_output_mode == MicrowaveMode.CW:
            mode = 'cw'
        elif self.current_output_mode == MicrowaveMode.LIST:
            mode = 'list'
        elif self.current_output_mode == MicrowaveMode.SWEEP:
            mode = 'sweep'
        return mode, self.output_active


    def get_power(self):
        pass

    def get_frequency(self):
        pass
    
    def cw_on(self):
        """
        Switches on cw microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """
        self.current_output_mode = MicrowaveMode.CW
        time.sleep(0.5)
        self.output_active = True
        self.log.info('MicrowaveDummy>CW output on')
        return 0

    
    def set_cw(self, frequency=None, power=None):
        """
        Configures the device for cw-mode and optionally sets frequency and/or power

        @param float frequency: frequency to set in Hz
        @param float power: power to set in dBm
        @param bool useinterleave: If this mode exists you can choose it.

        @return float, float, str: current frequency in Hz, current power in dBm, current mode

        Interleave option is used for arbitrary waveform generator devices.
        """
        self.log.debug('MicrowaveDummy>set_cw, frequency: {0:f}, power {0:f}:'.format(frequency,
                                                                                      power))
        self.output_active = False
        self.current_output_mode = MicrowaveMode.CW
        if frequency is not None:
            self.mw_cw_frequency = frequency
        if power is not None:
            self.mw_cw_power = power
        return self.mw_cw_frequency, self.mw_cw_power, 'cw'

    
    def list_on(self):
        """
        Switches on the list mode microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """
        self.current_output_mode = MicrowaveMode.LIST
        time.sleep(1)
        self.output_active = True
        self.log.info('MicrowaveDummy>List mode output on')
        return 0

    
    def set_list(self, frequency=None, power=None):
        """
        Configures the device for list-mode and optionally sets frequencies and/or power

        @param list frequency: list of frequencies in Hz
        @param float power: MW power of the frequency list in dBm

        @return list, float, str: current frequencies in Hz, current power in dBm, current mode
        """
        self.log.debug('MicrowaveDummy>set_list, frequency_list: {0}, power: {1:f}'
                       ''.format(frequency, power))
        self.output_active = False
        self.current_output_mode = MicrowaveMode.LIST
        if frequency is not None:
            self.mw_frequency_list = frequency
        if power is not None:
            self.mw_cw_power = power
        return self.mw_frequency_list, self.mw_cw_power, 'list'


    def reset_listpos(self):
        """
        Reset of MW list mode position to start (first frequency step)

        @return int: error code (0:OK, -1:error)
        """
        return 0
    

    def sweep_on(self):
        """ Switches on the sweep mode.

        @return int: error code (0:OK, -1:error)
        """
        self.current_output_mode = MicrowaveMode.SWEEP
        time.sleep(1)
        self.output_active = True
        self.log.info('MicrowaveDummy>Sweep mode output on')
        return 0

    
    def set_sweep(self, start=None, stop=None, step=None, power=None):
        """
        Configures the device for sweep-mode and optionally sets frequency start/stop/step
        and/or power

        @return float, float, float, float, str: current start frequency in Hz,
                                                 current stop frequency in Hz,
                                                 current frequency step in Hz,
                                                 current power in dBm,
                                                 current mode
        """
        self.log.debug('MicrowaveDummy>set_sweep, start: {0:f}, stop: {1:f}, step: {2:f}, '
                       'power: {3:f}'.format(start, stop, step, power))
        self.output_active = False
        self.current_output_mode = MicrowaveMode.SWEEP
        if (start is not None) and (stop is not None) and (step is not None):
            self.mw_start_freq = start
            self.mw_stop_freq = stop
            self.mw_step_freq = step
        if power is not None:
            self.mw_sweep_power = power
        return self.mw_start_freq, self.mw_stop_freq, self.mw_step_freq, self.mw_sweep_power, \
               'sweep'
    

    def reset_sweeppos(self):
        """
        Reset of MW sweep mode position to start (start frequency)

        @return int: error code (0:OK, -1:error)
        """
        return 0

    
    def set_ext_trigger(self, pol, timing):
        """ Set the external trigger for this device with proper polarization.

        @param TriggerEdge pol: polarisation of the trigger (basically rising edge or falling edge)
        @param float timing: estimated time between triggers

        @return object: current trigger polarity [TriggerEdge.RISING, TriggerEdge.FALLING]
        """
        self.log.info('MicrowaveDummy>ext_trigger set')
        self.current_trig_pol = pol
        return self.current_trig_pol, timing
    

    def trigger(self):
        """ Trigger the next element in the list or sweep mode programmatically.

        @return int: error code (0:OK, -1:error)

        Ensure that the Frequency was set AFTER the function returns, or give
        the function at least a save waiting time.
        """

        time.sleep(self._FREQ_SWITCH_SPEED)  # that is the switching speed
        return

    
    def get_limits(self):
        """Dummy limits"""
        limits = MicrowaveLimits()
        limits.supported_modes = (MicrowaveMode.CW, MicrowaveMode.LIST, MicrowaveMode.SWEEP)

        limits.min_frequency = 100e3
        limits.max_frequency = 20e9

        limits.min_power = -120
        limits.max_power = 30

        limits.list_minstep = 0.001
        limits.list_maxstep = 20e9
        limits.list_maxentries = 10001

        limits.sweep_minstep = 0.001
        limits.sweep_maxstep = 20e9
        limits.sweep_maxentries = 10001
        return limits

    
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
    