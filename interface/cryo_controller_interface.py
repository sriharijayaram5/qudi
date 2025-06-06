# -*- coding: utf-8 -*-

"""
This file contains the Qudi Interface file to control cryo controllers.

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

class CryoControllerInterface(metaclass=InterfaceMetaclass):
    """This is the Interface class to define the controls for the cryo controller hardware.

    """

    def get_sample_temp_setpoint(self):
        pass
    
    def get_sample_temp(self):
        pass
    
    def get_sample_temp_control_status(self):
        pass
    
    def get_reservoir_temp_setpoint(self):
        pass
    
    def get_reservoir_temp(self):
        pass
    
    def get_reservoir_temp_control_status(self):
        pass

