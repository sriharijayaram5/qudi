# -*- coding: utf-8 -*-

"""
This file contains the Qudi Interface file to control voltage sources.

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

class VolatgeSourceInterface(metaclass=InterfaceMetaclass):
    """This is the Interface class to define the controls for the simple voltage source (VS) hardware.

    This interface is designed to interface voltage source where the voltage can be set.

    """

    @abstract_interface_method
    def get_status(self): #
        """ Gets the current status of the VS

        @return 
        """
        pass

    @abstract_interface_method
    def get_limits(self): # 
        """ Return the device-specific limits in a nested dictionary.

          @return VSLimits: VS Limits object
        """
        pass

    def get_output_status(self): #
        pass

    def output_on(self): #
        pass

    def output_off(self): # 
        pass

    def get_source_function(self): #
        #This function is not necesarily to run a simple voltage source. However, if an SMU is used as voltage source, this function is needed.
        pass
    
    def set_source_function(self, function): # 
        #This function is not necesarily to run a simple voltage source. However, if an SMU is used as voltage source, this function is needed.
        pass

    def get_source_shape(self): #
        #This function is not necesarily to run a simple voltage source. However, if an SMU is used as voltage source, this function is needed.
        pass
    
    def set_source_shape(self, shape): # 
        #This function is not necesarily to run a simple voltage source. However, if an SMU is used as voltage source, this function is needed.
        pass

    def get_source_mode(self): #
        #This function is not necesarily to run a simple voltage source. However, if an SMU is used as voltage source, this function is needed.
        pass
    
    def set_source_mode(self, mode): # 
        #This function is not necesarily to run a simple voltage source. However, if an SMU is used as voltage source, this function is needed.
        pass

    def get_source_volt_autorange(self): #
        pass
    
    def set_source_volt_autorange(self, autorange): # 
        pass
        
    def get_source_volt_range(self): #
        pass
    
    def set_source_volt_range(self, range): # 
        pass

    def get_source_volt_ramp_speed(self): #
        pass

    def set_source_volt_ramp_speed(self, ramp_speed): # 
        pass

    
    def set_voltage_level(self, voltage): # 
        pass

    def set_DC_voltage(self, voltage, autorange = False): # 
        pass

    def get_voltage(self): #
        pass

    def set_voltage_limit(self, low_lim, up_lim): # 
        pass

    def get_voltage_limit(self): #
        pass

class VSLimits:
    """ A container to hold all limits for microwave sources.
    """
    def __init__(self):
        """Create an instance containing all parameters with default values."""

        # voltage in V
        self.min_voltage = -10
        self.max_voltage = 10

    def voltage_in_range(self, voltage):
        return in_range(voltage, self.min_voltage, self.max_voltage)

    def current_in_range(self, current):
        return in_range(current, self.min_current, self.max_current)

