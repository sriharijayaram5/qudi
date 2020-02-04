# -*- coding: utf-8 -*-
"""
Dummy implementation for simple data acquisition.

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
import numpy as np
import time
import copy

from core.module import Base, ConfigOption



class ProteusQDummy(Base):
    """ A simple dummy for the ProteusQ.

    REQUIRES DEFINITELY AN IMPROVEMENT.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'simple_data_dummy.SimpleDummy'
        ip_address: '192.168.2.10'
        port: 55555
        unlock_key: <your obtained key, either in hex or number> e.g. of the form: 58293468969010369791345065897427835159

    """

    __version__ = '0.1.0'

    _modclass = 'ProteusQDummy'
    _modtype = 'hardware'


    # AFM measurement parameter
    MEAS_PARAMS = {}
    MEAS_PARAMS['Height(Dac)'] = {'measured_units' : 'nm',
                                  'scale_fac': 1e-9,    # multiplication factor to obtain SI units   
                                  'si_units': 'm', 
                                  'nice_name': 'Height (from DAC)'}
    MEAS_PARAMS['Height(Sen)'] = {'measured_units' : 'nm', 
                                  'scale_fac': 1e-9,    # multiplication factor to obtain SI units   
                                  'si_units': 'm', 
                                  'nice_name': 'Height (from Sensor)'}
    MEAS_PARAMS['Iprobe'] = {'measured_units' : 'pA', 
                             'scale_fac': 1e-12,    # multiplication factor to obtain SI units   
                             'si_units': 'A', 
                             'nice_name': 'Probe Current'}
    MEAS_PARAMS['Mag'] = {'measured_units' : 'arb. u.', 
                          'scale_fac': 1,    # important: use integer representation, easier to compare if scale needs to be applied
                          'si_units': 'arb. u.', 
                          'nice_name': 'Tuning Fork Magnitude'}
    MEAS_PARAMS['Phase'] = {'measured_units' : 'deg.', 
                            'scale_fac': 1,    # multiplication factor to obtain SI units   
                            'si_units': 'deg.', 
                            'nice_name': 'Tuning Fork Phase'}
    MEAS_PARAMS['Freq'] = {'measured_units' : 'Hz', 
                           'scale_fac': 1,    # multiplication factor to obtain SI units   
                           'si_units': 'Hz', 
                           'nice_name': 'Frequency Shift'}
    MEAS_PARAMS['Nf'] = {'measured_units' : 'arb. u.',
                         'scale_fac': 1,    # multiplication factor to obtain SI units    
                         'si_units': 'arb. u.', 
                         'nice_name': 'Normal Force'}
    MEAS_PARAMS['Lf'] = {'measured_units' : 'arb. u.', 
                         'scale_fac': 1,    # multiplication factor to obtain SI units   
                         'si_units': 'arb. u.', 
                         'nice_name': 'Lateral Force'}
    MEAS_PARAMS['Ex1'] = {'measured_units' : 'arb. u.', 
                          'scale_fac': 1,    # multiplication factor to obtain SI units  
                          'si_units': 'arb. u.', 
                          'nice_name': 'External Sensor'}


    def on_activate(self):
        pass

    def on_deactivate(self):
        pass


    def get_meas_params(self):
        """ Obtain a dict with the available measurement parameters. """
        return copy.copy(self.MEAS_PARAMS)


    def get_sample_scanner_pos(self, axis_label_list=['X1', 'Y1', 'Z1']):
        """ Get the sample scanner position. 

        @param list axis_label_list: axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'x', 'Y', 'y', 'Z', 'z'] 
                                     or postfixed with a '1':
                                        ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 

        @return dict: sample scanner position dict in m (SI units). Normal 
                      output [0 .. AxisRange], though may fall outside this 
                      interval. Error: output <= -1000
        """

        sc_pos = {'X1': 0.0, 'Y1': 0.0, 'Z1': 0.0} # sample scanner pos
        
        return sc_pos


    def get_objective_scanner_pos(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner position. 

        @param str axis_label_list: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """

        sc_pos = {'X1': 0.0, 'Y1': 0.0, 'Z1': 0.0}  # objective scanner pos
 
        return sc_pos

    def prepare_pixelclock(self):
        pass




