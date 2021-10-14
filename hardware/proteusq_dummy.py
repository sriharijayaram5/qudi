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
from interface.scanner_interface import ScannerMeasurements



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

    _SCANNER_MEASUREMENTS = ScannerMeasurements()

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass

    # ----------------------
    #  Fake SPM methods
    # ----------------------
    def _create_scanner_measurements(self):
        sm = self._SCANNER_MEASUREMENTS 

        sm.scanner_measurements = { 
            'Height(Dac)' : {'measured_units' : 'nm',
                             'scale_fac': 1e-9,    # multiplication factor to obtain SI units   
                             'si_units': 'm', 
                             'nice_name': 'Height (from DAC)'},
     
            'Height(Sen)' : {'measured_units' : 'nm', 
                             'scale_fac': 1e-9,    
                             'si_units': 'm', 
                             'nice_name': 'Height (from Sensor)'},

            'Iprobe' :      {'measured_units' : 'pA', 
                             'scale_fac': 1e-12,   
                             'si_units': 'A', 
                             'nice_name': 'Probe Current'},
 
            'Mag' :         {'measured_units' : 'arb. u.', 
                             'scale_fac': 1,    # important: use integer representation, easier to compare if scale needs to be applied
                             'si_units': 'arb. u.', 
                             'nice_name': 'Tuning Fork Magnitude'},

            'Phase' :       {'measured_units' : 'deg.', 
                             'scale_fac': 1,    
                             'si_units': 'deg.', 
                             'nice_name': 'Tuning Fork Phase'},

            'Freq' :        {'measured_units' : 'Hz', 
                             'scale_fac': 1,    
                             'si_units': 'Hz', 
                             'nice_name': 'Frequency Shift'},

            'Nf' :          {'measured_units' : 'arb. u.',
                             'scale_fac': 1,    
                             'si_units': 'arb. u.', 
                             'nice_name': 'Normal Force'},

            'Lf' :          {'measured_units' : 'arb. u.', 
                             'scale_fac': 1,    
                             'si_units': 'arb. u.', 
                             'nice_name': 'Lateral Force'},

            'Ex1' :         {'measured_units' : 'arb. u.', 
                             'scale_fac': 1,    
                             'si_units': 'arb. u.', 
                             'nice_name': 'External Sensor'}
        }

        sm.scanner_axes = { 'SAMPLE_AXES':     ['X', 'Y', 'Z', 'x', 'y', 'z',
                                                'X1', 'Y1', 'Z1', 'x1', 'y1', 'z1'],
                            
                            'OBJECTIVE_AXES' : ['X2', 'Y2', 'Z2', 'x2', 'y2', 'z2'],

                            'VALID_AXES'     : ['X',  'Y',  'Z',  'x',  'y',  'z',
                                                'X1', 'Y1', 'Z1', 'x1', 'y1', 'z1',
                                                'X2', 'Y2', 'Z2', 'x2', 'y2', 'z2']
        }

        sm.scanner_planes = ['XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2']

        sm.scanner_sensors = {  # name of sensor parameters 
                                'SENS_PARAMS_SAMPLE'    : ['SenX', 'SenY', 'SenZ'],   # AFM sensor parameter
                                'SENS_PARAMS_OBJECTIVE' : ['SenX2', 'SenY2', 'SenZ2'],

                                # maximal range of the AFM scanner , x, y, z
                                'SAMPLE_SCANNER_RANGE' :    [[0, 100e-6], [0, 100e-6], [0, 12e-6]],
                                'OBJECTIVE_SCANNER_RANGE' : [[0, 30e-6], [0, 30e-6], [0, 10e-6]]
                             }


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

    def get_available_measurement_params(self):
        """  Gets the available measurement parameters (names) 
        obtains the dictionary of aviable measurement params 
        This is device specific, but is an implemenation of the 
        ScannerMeasurements class

        @return: scanner_measurements class implementation 
        """
        sm = self._SCANNER_MEASUREMENTS
        return copy.copy(sm.scanner_measurements)

    # -----------------------
    # Fake MicrowaveQ methods
    # -----------------------

    def configure_recorder(self, mode, params):
        return 0 

    def check_interface_version(self,pause=None):
        pass

