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
from enum import Enum, EnumMeta
from posixpath import abspath
from core.util.interfaces import InterfaceMetaclass


class ScannerState(Enum):
    DISCONNECTED          = 0 
    UNCONFIGURED          = 1
    IDLE                  = 2 
    OBJECTIVE_MOVING      = 3
    OBJECTIVE_SCANNING    = 4
    PROBE_MOVING          = 5
    PROBE_SCANNING        = 6
    PROBE_LIFTED          = 7
    PROBE_SCANNING_LIFTED = 8

    @classmethod
    def name(cls,val):
        return { v:k for k,v in dict(vars(cls)).items() if isinstance(v,int)}.get(val, None)


class ScannerMode(Enum):
    UNCONFIGURED          = 0
    OBJECTIVE_XY          = 1
    OBJECTIVE_XZ          = 2
    OBJECTIVE_YZ          = 3
    PROBE_CONTACT         = 4
    PROBE_CONSTANT_HEIGHT = 5
    PROBE_DUAL_PASS       = 6
    PROBE_Z_SWEEP         = 7

    @classmethod
    def name(cls,val):
        return { v:k for k,v in dict(vars(cls)).items() if isinstance(v,int)}.get(val, None)

class ScanStyle(Enum):
    LINE = 0
    POINT = 1


class ScannerConstraints:

    def __init__(self):
        # maximum numer of possible detectors for slow counter
        self.max_detectors = 0

        # frequencies in Hz
        self.min_count_frequency = 5e-5
        self.max_count_frequency = 5e5

        # add available scanner modes
        self.scanner_modes = []

        # add available scan styles 
        self.scanner_styles = []

        # add scanner mode parameters
        self.scanner_mode_params = {}

        # here default values are specified 
        self.scanner_mode_params_defaults = {}

        # set allowable states, to be populated by allowable states of a mode
        self.scanner_mode_states = {}

        # set method for measurement type
        self.scanner_mode_measurements = {}


class ScannerMeasurements:

    def __init__(self):
        # measurement variables returned from SPM
        self.scanner_measurements = { # 'Height(Sen)' : {
                                      #                  'measured_units' : 'nm',
                                      #                  'scale_fac'      : 1e-9,  # multiplication factor to SI unit
                                      #                  'si_units'       : 'm',
                                      #                  'nice_name'      : 'Height (from Sensor)'
                                      #                  }
                                    }

        self.scanner_axes = { # 'SAMPLE_AXES' :    [ 'X',  'x',   'Y',  'y',  'Z',  'z', 
                              #                      'X1', 'x1 ', 'Y1', 'y1', 'Z1', 'z1'] 
                              # 
                              # 'OBJECTIVE_AXES' : [ 'X2', 'x2', 'Y2', 'y2', 'Z2', 'z2']
                              # 
                            }
    
        self.scanner_planes =  [ # 'X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'
                               ]

        self.scanner_sensors = { # 'SENS_PARAMS_AFM' : ['SenX', 'SenY', 'SenZ'],   # AFM sensor parameter
                                 # 'SENS_PARAMS_OBJ' : ['SenX2', 'SenY2', 'SenZ2'] 
                               }

class ScannerInterface(metaclass=InterfaceMetaclass):
    """ Define the controls for a Scanner device."""

    _modtype = 'ScannerInterface'
    _modclass = 'interface'

    # Configure methods
    # =========================
    @abc.abstractmethod
    def configure_scanner(self, mode, params, scan_style=ScanStyle.LINE):
        """ Configures the scanner device for current measurement. 

        @param ScannerMode mode: mode of scanner
        @param ScannerStyle scan_style: movement of scanner
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """
        pass

    @abc.abstractmethod
    def get_current_configuration(self):
        """ Returns the current scanner configuration

        @return tuple: (mode, scan_style)
        """
        pass

    @abc.abstractmethod
    def configure_line(self, 
                       corr0_start, corr0_stop, 
                       corr1_start, corr1_stop, # not used in case of z sweep
                       time_forward, time_back):
        # will configure a line depending on the selected mode
        # this method is used to configure a scan_point() or scan_line() operation
        # (required configure_scan_device be done before the scan)
        # allocate the array where data will be saved to
        pass
        
    @abc.abstractmethod
    def scan_line(self): 
        # (required configure_scan_line to be called prior)
        # will execute a scan line depending on the selected mode
        pass

    @abc.abstractmethod
    def get_measurement(self):
        # (required configure_scan_line to be called prior)
        # => blocking method, either with timeout or stoppable via stop measurement
        pass

    @abc.abstractmethod
    def scan_point(self):
        # (blocking method, required configure_scan_line to be called prior)
        pass

    @abs.abstractmethod
    def finish_scan(self):
        # requests a finish of the measurement program
        # allows completion of the current measurement
        pass
    
    @abc.abstractmethod
    def stop_measurement(self):
        # => hardcore stop mechanism
        # => if PROBE_CONSTANT_HEIGHT: land_probe
        # => if PROBE_DUAL_PASS: land_probe
        # => if PROBE_Z_SWEEP: BreakProbeSweepZ

        # - land probe after each scan! land_probe(fast=False)
        # => configuration will be set to UNCONFIGURED
        pass

    @abc.abstractmethod
    def calibrate_constant_height(self, calib_points, safety_lift):
        # array with (x,y) points, safety_lift, ) 
        # => return calibration points array of (x,y,z)
        pass

    @abc.abstractmethod
    def get_constant_height_calibration(self):
        # => return calibration points array of (x,y,z)
        pass


    # Device specific functions
    # =========================
    @abc.abstractmethod
    def reset_device(self):
        # performs device reset, if applicable
        pass

    @abc.abstractmethod
    def get_current_device_state(self):
        # gets device state, based on available states of ScannerState Enum 
        pass

    @abc.abstractmethod
    def get_current_device_config(self):     
        # returns current configuration, from ScannerConfig and ScannerMode Enum
        # internally: _set_current_device_config()
        pass

    @abc.abstractmethod
    def get_device_meta_info(self, query=None):
        # returns info on the scanner hardware/software
        pass 

    @abc.abstractmethod
    def get_available_scan_modes(self):
        pass

    @abc.abstractmethod
    def get_available_scan_style(self):
        pass

    @abc.abstractmethod
    def get_available_scan_measurements(self):
        return 

    @abc.abstractmethod
    def get_parameters_for_mode(self):
        pass


    #Objective scanner Axis/Movement functions
    #==============================

    @abc.abstractmethod
    def get_objective_scan_range(self, axes=['X','Y','Z']):
        pass

    @abc.abstractmethod
    def get_objective_pos(self):
        pass

    @abc.abstractmethod
    def get_objective_target_pos(self):
        pass

    @abc.abstractmethod
    def set_objective_pos_abs(self, vel=None, time=None):
        # if velocity is given, time will be ignored
        pass

    @abc.abstractmethod
    def set_objective_pos_rel(self, vel=None, time=None):  
        # if velocity is given, time will be ignored
        pass


    # Probe scanner Axis/Movement functions
    # ==============================

    @abc.abstractmethod
    def get_sample_scan_range(self, axes=['X','Y','Z']):
        pass

    @abc.abstractmethod
    def get_sample_pos(self):
        pass

    @abc.abstractmethod
    def get_sample_target_pos(self):
        pass

    @abc.abstractmethod
    def set_sample_pos_abs(self, vel=None, time=None):
        #if velocity is given, time will be ignored
        pass
    
    @abc.abstractmethod
    def set_sample_pos_rel(self, vel=None, time=None):
        # if velocity is given, time will be ignored
        pass


    # Probe lifting functions
    # ========================

    @abc.abstractmethod
    def lift_probe(self, rel_value):
        pass

    @abc.abstractmethod
    def get_lifted_value(self):
        # return absolute lifted value
        pass

    @abc.abstractmethod
    def is_probe_landed(self): 
        # return True/False
        pass

    @abc.abstractmethod
    def land_probe(self, fast=False):
        pass

    # @abc.abstractmethod
    # def get_constraints(self):
    #     """ Retrieve the hardware constrains from the counter device.

    #     @return SlowCounterConstraints: object with constraints for the counter
    #     """
    #     pass



