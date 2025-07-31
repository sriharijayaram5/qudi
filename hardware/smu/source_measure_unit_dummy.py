# -*- coding: utf-8 -*-
"""
Author: Malik Lenger
Code for Yokogawa GS610 source measure unit.

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

from core.module import Base
from core.configoption import ConfigOption
from interface.smu_interface import SMUInterface
from interface.smu_interface import SMULimits
import visa
import time
import math
import random

class sourcemeasureunitDummy(Base, SMUInterface):
    """ Read human readable numbers from serial port.

    Example config for copy-paste:

    smu_GS610:
        module.Class: 'GS610_source_measure_unit.GS610sourcemeasureunit'
        serial_port: 'USB0::0x0B21::0x001E::90Z931989C::INSTR'

    """

    def on_activate(self):
        """ Activate module.
        """
        self.output_status = False
        self.source_func = 0 #0 == Voltage, 1 == Current
        self.source_shape = 0 #0 == DC, 1 == Pulsed
        self.source_mode = 0 #0 == Fixed, 1 == Sweep, 2 = List
        self.source_volt_autorange = False
        self.source_volt_range = 1
        self.source_volt_ramp_speed = 0.1
        self.source_curr_autorange = False
        self.source_curr_range = 1
        self.source_curr_ramp_speed = 0.01
        self.voltage_level = 0
        self.current_level = 0
        self.lower_voltage_limit = -10
        self.higher_voltage_limit = 10
        self.lower_current_limit = -0.5
        self.higher_current_limit = 0.5
        self.sense_state = False
        self.sense_fnc = 0 #0 == Voltage, 1 == Current, 2 == Resistance
        self.sense_four_port = False
        self.sens_autorange = False
        self.sens_autozero = False
        self.sense_delay = 0
        self.sense_achange_state = False
        self.trigger_source = 0
        self.integration_time = 100e-3
        
    def on_deactivate(self):
        """ Deactivate module.
        """
        pass
    
    def get_limits(self):
        limits = SMULimits()
        limits.min_voltage = -100
        limits.max_voltage = 100

        limits.min_current = -5
        limits.max_current = 5

        limits.min_sens_delay = 0.1e-6
        limits.max_sens_delay = 1
        return limits

    def get_status(self):
        output_status = self.get_output_status()

        src_func = self.get_source_function()
        src_shape = self.get_source_shape()
        src_mode = self.get_source_mode()

        sensing = self.get_sense_state()
        sense_func = self.get_sense_function()
        four_port = self.get_sense_four_port_state()

        return output_status, src_func, src_shape, src_mode, sensing, sense_func, four_port

    def get_output_status(self):
        return self.output_status

    def output_on(self):
        self.output_status = True
        return self.get_output_status()

    def output_off(self):
        self.output_status = False
        return self.get_output_status()
        
    def get_source_function(self):
        return self.source_func
    
    def set_source_function(self, function):
        self.source_func = function
        return self.get_source_function()

    def get_source_shape(self):
        return self.source_shape
    
    def set_source_shape(self, shape):
        self.source_shape = shape
        return self.get_source_shape()

    def get_source_mode(self):
        return self.source_mode 
    
    def set_source_mode(self, mode):
        self.source_mode = mode
        return self.get_source_mode()

    def get_source_volt_autorange(self):
        return self.source_volt_autorange
    
    def set_source_volt_autorange(self, autorange):
        self.source_volt_autorange = autorange
        return self.get_source_volt_autorange()
        
    def get_source_volt_range(self):
        return self.source_volt_range
    
    def set_source_volt_range(self, range):
        self.source_volt_range = range
        return self.get_source_volt_range()
    
    def get_source_volt_ramp_speed(self):
        return self.source_volt_ramp_speed

    def set_source_volt_ramp_speed(self, ramp_speed):
        self.source_volt_ramp_speed = ramp_speed
        return self.get_source_volt_ramp_speed()

    def get_source_curr_autorange(self):
        return self.source_curr_autorange
    
    def set_source_curr_autorange(self, autorange):
        self.source_curr_autorange = autorange
        return self.get_source_curr_autorange()
        
    def get_source_curr_range(self):
        return self.source_curr_range
    
    def set_source_curr_range(self, range):
        self.source_curr_range = range
        return self.get_source_curr_range()
    
    def get_source_curr_ramp_speed(self):
        return self.source_curr_ramp_speed

    def set_source_curr_ramp_speed(self, ramp_speed):
        self.source_curr_ramp_speed = ramp_speed
        return self.get_source_curr_ramp_speed()
    
    def set_voltage_level(self, voltage):
        self.voltage_level = voltage
        return self.get_voltage()

    def set_DC_voltage(self, voltage, autorange = False):
        self.set_source_function(0)
        self.set_source_shape(0)
        self.set_source_mode(0)
        self.set_source_volt_autorange(autorange)
        if not autorange:
            self.set_source_volt_range(abs(voltage))
        return self.set_voltage_level(voltage)

    def get_voltage(self):
        return self.voltage_level
    
    def set_current_level(self, current):
        self.current_level = current
        return self.get_current()

    def set_DC_current(self, current, autorange = False):
        self.set_source_function(1)
        self.set_source_shape(0)
        self.set_source_mode(0)
        self.set_source_curr_autorange(autorange)
        if not autorange:
            self.set_source_curr_range(abs(current))
        return self.set_current_level(current)

    def get_current(self):
        return self.current_level

    def set_voltage_limit(self, low_lim, up_lim):
        self.lower_voltage_limit = low_lim
        self.higher_voltage_limit = up_lim
        return self.get_voltage_limit()

    def get_voltage_limit(self):
        return self.lower_voltage_limit, self.higher_voltage_limit

    def set_current_limit(self, low_lim, up_lim):
        self.lower_current_limit = low_lim
        self.higher_current_limit = up_lim
        return self.get_current_limit()

    def get_current_limit(self):
        return self.lower_current_limit, self.higher_current_limit

    def get_sense_state(self):
        return self.sense_state
        
    def sensing_on(self):
        self.sense_state = True
        return self.get_sense_state()

    def sensing_off(self):
        self.sense_state = False
        return self.get_sense_state()

    def get_sense_function(self):
        return self.sense_fnc

    def get_sense_four_port_state(self):
        return self.sense_four_port
    
    def setup_sensing(self, sens_fnc, autorange, autozero, delay, achange, four_port, trigger, integration_time):
        self.sens_fnc = sens_fnc
        self.sens_autorange = autorange
        self.sens_autozero = autozero
        self.sense_delay = delay
        self.sense_achange_state = achange
        self.sense_four_port_state = four_port
        self.trigger_source = trigger
        self.integration_time = integration_time
        return self.sens_fnc, self.sens_autorange, self.sens_autozero, self.sense_delay, self.sense_achange_state, self.sense_four_port_state, self.trigger_source, self.integration_time

    def get_measurement(self, ext_triggered):
        time.sleep(self.integration_time)
        return random.uniform(0,5)
        
        
        
        
        