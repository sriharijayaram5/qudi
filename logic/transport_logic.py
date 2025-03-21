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


class TransportLogic(GenericLogic):
    """ Logic module to control the default settings for all pulsed measurements done by the PODMR, QAFM, and jupyter_pulsed_AWG_master_logic
        This logic includes all settings for pulsed measurements, which are not changed frequently.

    Example config:

    pulsedsettingslogic:
        module.Class: 'transport_logic.TransportLogic'
        

    """

    # status vars
    

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self.axis_units = {'V_G': {'applied_units': 'V',
                                   'si_units': 'V',
                                   'nice_name': 'Backgate Voltage'},
                           'V_S': {'applied_units': 'V',
                                   'si_units': 'V',
                                   'nice_name': 'Sample Voltage'}

                     }

        self.meas_params_units = {'resistance':       {'measured_units' : 'Ohm',
                                            'si_units': 'Ohm', 
                                            'nice_name': 'Resistance'},
                            }
        
        self._transport_1D_array = self.initialize_transport_1D_array(-10, 10, 11, None, None)
        self._transport_2D_array = self.initialize_transport_1D_array(-10, 10, 11, -10, 10, 11, None, None, None)

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def initialize_transport_1D_array(self, x_start, x_stop, x_num,
                                         x_axis_type, meas_params):
        """ Initialize the qafm scan array. 

        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """


        x_axis = np.linspace(x_start, x_stop, x_num, endpoint=True)

        if meas_params == None:
            meas_params = self.meas_params_units.keys()

        if x_axis_type == None:
            x_axis_type == 'V_G'

        meas_dict = {}
        for params in meas_params:
            name = f'1D_{params}'

            meas_dict[name] = {'data': np.zeros((x_num))}
            meas_dict[name]['x_axis'] = x_axis
            meas_dict[name]['data_info'].update(self.meas_params_units[params])
            meas_dict[name]['x_axis_info'].update(self.axis_units[x_axis_type])

        return meas_dict
    
    def initialize_transport_2D_array(self, x_start, x_stop, x_num,
                                      y_start, y_stop, y_num,
                                      x_axis_type, y_axis_type, meas_params):
        """ Initialize the qafm scan array. 

        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """


        x_axis = np.linspace(x_start, x_stop, x_num, endpoint=True) 
        y_axis = np.linspace(y_start, y_stop, y_num, endpoint=True) 

        if meas_params == None:
            meas_params = self.meas_params_units.keys()

        if x_axis_type == None:
            x_axis_type == 'V_G'

        if y_axis_type == None:
            y_axis_type == 'V_S'

        meas_dict = {}
        for params in meas_params:
            name = f'2D_{params}'

            meas_dict[name] = {'data': np.zeros((y_num, x_num))}
            meas_dict[name]['x_axis'] = x_axis
            meas_dict[name]['y_axis'] = y_axis
            meas_dict[name]['data_info'].update(self.meas_params_units[meas_params])
            meas_dict[name]['x_axis_info'].update(self.axis_units[x_axis_type])
            meas_dict[name]['y_axis_info'].update(self.axis_units[y_axis_type])

        return meas_dict
    
    def get_1D_data(self):
        return self._transport_1D_array
    
    def get_2D_data(self):
        return self._transport_2D_array