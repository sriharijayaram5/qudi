# -*- coding: utf-8 -*-

"""
This file contains the Qudi Interface file to control microwave devices.

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

from core.interface import abstract_interface_method
from core.meta import InterfaceMetaclass
from core.util.helpers import in_range
from enum import Enum

class SMUInterface(metaclass=InterfaceMetaclass):
    """This is the Interface class to define the controls for the simple microwave hardware.

    This interface is designed to interface microwave generator where the power and frequency of the produced microwave
    can be set. Is can be operated in CW (continuous wave) or as a sweep system synchronised with a measured device.

    """

    @abstract_interface_method
    def get_status(self):
        """ Gets the current status of the SMU

        @return 
        """
        pass

    @abstract_interface_method
    def get_limits(self):
        """ Return the device-specific limits in a nested dictionary.

          @return SMULimits: SMUe limits object
        """
        pass

    def get_output_status(self):
        pass

    def output_on(self):
        pass

    def output_off(self):
        pass

    def get_source_function(self):
        pass
    
    def set_source_function(self, function):
        pass

    def get_source_shape(self):
        pass
    
    def set_source_shape(self, shape):
        pass

    def get_source_mode(self):
        pass
    
    def set_source_mode(self, mode):
        pass

    def get_source_volt_autorange(self):
        pass
    
    def set_source_volt_autorange(self, autorange):
        pass
        
    def get_source_volt_range(self):
        pass
    
    def set_source_volt_range(self, range):
        pass

    def get_source_volt_ramp_speed(self):
        pass

    def set_source_volt_ramp_speed(self, ramp_speed):
        pass

    def get_source_curr_autorange(self):
        pass
    
    def set_source_curr_autorange(self, autorange):
        pass
        
    def get_source_curr_range(self):
        pass
    
    def set_source_curr_range(self, range):
        pass

    def get_source_curr_ramp_speed(self):
        pass

    def set_source_curr_ramp_speed(self, ramp_speed):
        pass
    
    def set_voltage_level(self, voltage):
        pass

    def set_DC_voltage(self, voltage, autorange = False):
        pass

    def get_voltage(self):
        pass
    
    def set_current_level(self, current):
        pass

    def set_DC_current(self, current, autorange = False):
        pass

    def get_current(self):
        pass

    def set_voltage_limit(self, low_lim, up_lim):
        pass

    def get_voltage_limit(self):
        pass

    def set_current_limit(self, low_lim, up_lim):
        pass

    def get_current_limit(self):
        pass

    def get_sense_state(self):
        pass

    def sensing_on(self):
        pass

    def sensing_off(self):
        pass

    def get_sense_function(self):
        pass

    def get_sense_four_port_state(self):
        pass

    def setup_sensing(self, sens_fnc, autorange, autozero, delay, achange, four_port, trigger, integration_time):
        pass

    def get_measurement(self, ext_triggered):
        pass


class SMULimits:
    """ A container to hold all limits for microwave sources.
    """
    def __init__(self):
        """Create an instance containing all parameters with default values."""

        # voltage in V
        self.min_voltage = -10
        self.max_voltage = 10

        # current in A
        self.min_current = -10
        self.max_current = 0

        self.min_sens_delay = 0
        self.max_sens_delay = 1

    def voltage_in_range(self, voltage):
        return in_range(voltage, self.min_voltage, self.max_voltage)

    def current_in_range(self, current):
        return in_range(current, self.min_current, self.max_current)

