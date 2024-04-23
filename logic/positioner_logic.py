# -*- coding: utf-8 -*-
"""
This file contains the Qudi positioner logic class.

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

from qtpy import QtCore
from collections import OrderedDict
import numpy as np
import time
import matplotlib.pyplot as plt

from core.connector import Connector
from core.statusvariable import StatusVar
from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex

class PositionerLogic(GenericLogic):

    _positioner = Connector(interface='MotorInterface')

    def __init__(self, config, **kwargs):
        """ 
        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)
        return
    
    def on_activate(self):
        self.positioner = self._positioner()
        return

    def on_deactivate(self):
        return