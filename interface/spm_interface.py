# -*- coding: utf-8 -*-

"""
This file contains the LabQ Interface for scanning probe microscopy devices.

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

import abc
from enum import Enum
from core.util.interfaces import InterfaceMetaclass


class SPMInterface(metaclass=InterfaceMetaclass):
    """ Define the controls for a spm device."""

    _modtype = 'SPMInterface'
    _modclass = 'interface'

    # @abc.abstractmethod
    # def get_constraints(self):
    #     """ Retrieve the hardware constrains from the counter device.

    #     @return SlowCounterConstraints: object with constraints for the counter
    #     """
    #     pass

class SPMMode(Enum):
    CONTINUOUS = 0
    GATED = 1
    FINITE_GATED = 2


class SPMConstraints:

    def __init__(self):
        # maximum numer of possible detectors for slow counter
        self.max_detectors = 0
        # frequencies in Hz
        self.min_count_frequency = 5e-5
        self.max_count_frequency = 5e5
        # add CountingMode enums to this list in instances
        self.counting_mode = []

