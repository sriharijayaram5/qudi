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

import os
import copy
import threading
import numpy as np
from deprecation import deprecated
from qtpy import QtCore

from core.module import Base, ConfigOption
from hardware.spm.remote_spm import TScanMode, RemoteSPMLibrary

from interface.scanner_interface import ScannerInterface, ScannerMode, ScannerStyle, \
                                        ScannerState, ScannerConstraints, ScannerMeasurements  

class SmartSPM(Base, ScannerInterface):
    """ Smart SPM wrapper for the communication with the module.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'smart_spm.SmartSPM'
        libpath: 'path/to/lib/folder'

    """

    # Settings for Qudi Module:
    # -------------------------

    _modclass = 'SmartSPM'
    _modtype = 'hardware'

    _threaded = True
    _version_comp = 'aist-nt_v3.5.150'   # indicates the compatibility of the version.
    __version__ = '0.6.2'
    _spm_dll_ver = '0.0.0'

    # Default values for measurement
    # ------------------------------

    # here are data saved from the test TScanCallback
    #_test_line_scan = []
    #_test_array_scan = []

    _afm_scan_line = np.zeros(0) # scan line array for afm scanner
    _afm_scan_array = np.zeros((9*2, 10, 10)) # Parameters for forward scan dir:
                                              # 0:Height(Dac), 1:Height(Sen), 
                                              # 2:Iprobe, 3:Mag, 4:Phase, 5:Freq, 
                                              # 6:Nf, 7:Lf, 8:Ex1
                                              # and whole thing in reversed scan
                                              # direction.

    _line_counter = 0
 
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

    _curr_meas_params = []    # store here the current selection from MEAS_PARAMS

    SENS_PARAMS_AFM = ['SenX', 'SenY', 'SenZ']   # AFM sensor parameter
    SENS_PARAMS_OBJ = ['SenX2', 'SenY2', 'SenZ2']   # Objective sensor parameter
    
     
    SAMPLE_AXIS = ['X', 'x', 'Y', 'y', 'Z', 'z', 'X1', 'x1', 'Y1', 'y1',
                       'Z1', 'z1']
    OBJECTIVE_AXIS = ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2']
    VALID_AXIS =  SAMPLE_AXIS + OBJECTIVE_AXIS

    PLANE_LIST = ['XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2']
    _curr_plan = 'XY'   # store here the current plane

    # maximal range of the AFM scanner , x, y, z
    AFM_SCANNER_RANGE = [[0, 100e-6], [0, 100e-6], [0, 12e-6]]
    OBJECTIVE_SCANNER_RANGE = [[0, 30e-6], [0, 30e-6], [0, 10e-6]]

    _curr_meas_mode = TScanMode.LINE_SCAN

    # Line index counter for line scans
    _line_index_ctr = 0
    # a stop request:
    _stop_request = False
    # the current setting of the point trigger
    _ext_trigger_state = False

    # Signals:
    # external signal: signature: (line number, number of _curr_meas_params, datalist)
    sigLineFinished = QtCore.Signal(int, int, object)

    _libpath = ConfigOption('libpath', default='spm-library')   # default is the relative path

    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        # checking for the right configuration
        for key in config.keys():
            self.log.debug('{0}: {1}'.format(key, config[key]))


    # ==========================================================================
    # Enhance the current module by threading capabilities:
    # ==========================================================================

    @QtCore.Slot(QtCore.QThread)
    def moveToThread(self, thread):
        super().moveToThread(thread)

    def getModuleThread(self):
        """ Get the thread associated to this module.

          @return QThread: thread with qt event loop associated with this module
        """
        return self._manager.tm._threads['mod-hardware-' + self._name].thread

    # ==========================================================================

    def on_activate(self):
        """ Prepare and activate the spm module. """

        self._spm_dll_ver = self.get_library_version()
        self._dev = RemoteSPMLibrary(self._libpath) 
        self._dev.connect_spm()


    def on_deactivate(self):
        """ Clean up and deactivate the spm module. """
        self._dev.disconnect_spm()

        
    def get_library_version(self, libpath=None):
        """ Get the spm dll library version.

        @params str path: optional path to the folder, where library is situated.
        """
        if libpath is None:
            libpath = self._libpath

        file_name = 'version.txt'
        path = os.path.join(libpath, file_name)

        try:
            with open(path, 'r') as ver_file:
                return [line.strip().split(' ')[1] for line in ver_file.readlines() if 'version' in line][0]
        except Exception as e:
            self.log.warning('Could not obtain the library version of the SPM DLL file.')
            return '0.0.0'

    # ==========================================================================
    #                       Scanner interface methods 
    # ==========================================================================
    def configure_scanner(self, mode, params):
        """ Configures the scanner device for current measurement. 

        @param ScannerMode mode: mode of scanner
        @param ScannerStyle scan_style: movement of scanner
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """
        pass

    def get_current_configuration(self):
        """ Returns the current scanner configuration

        @return tuple: (mode, scan_style)
        """
        pass

    def configure_scan_line(self, 
                            corr0_start, corr0_stop, 
                            corr1_start, corr1_stop, # not used in case of z sweep
                            time_forward, time_back):
        # will configure a line depending on the selected mode
        # (required configure_scan_device be done before the scan)
        # allocate the array where data will be saved to
        pass
        
    def scan_line(self): 
        # (required configure_scan_line to be called prior)
        # will execute a scan line depending on the selected mode
        pass

    def get_measurement(self):
        # (required configure_scan_line to be called prior)
        # => blocking method, either with timeout or stoppable via stop measurement
        pass

    def scan_point(self):
        # (blocking method, required configure_scan_line to be called prior)
        pass
    
    def stop_measurement(self):
        # => hardcore stop mechanism
        # => if PROBE_CONSTANT_HEIGHT: land_probe
        # => if PROBE_DUAL_PASS: land_probe
        # => if PROBE_Z_SWEEP: BreakProbeSweepZ

        # - land probe after each scan! land_probe(fast=False)
        # => configuration will be set to UNCONFIGURED
        pass

    def calibrate_constant_height(self, calib_points, safety_lift):
        # array with (x,y) points, safety_lift, ) 
        # => return calibration points array of (x,y,z)
        pass

    def get_constant_height_calibration(self):
        # => return calibration points array of (x,y,z)
        pass


    # Device specific functions
    # =========================
    def reset_device(self):
        pass

    def get_current_device_state(self):
        pass

    def get_current_device_config(self):     
        #=> internally: _set_current_device_config()
        pass

    def get_available_scan_modes(self):
        pass

    def get_parameter_for_modes(self):
        pass

    def get_available_scan_style(self):
        pass


    #Objective scanner Axis/Movement functions
    #==============================

    def get_objective_scan_range(self, axes=['X','Y','Z']):
        pass

    def get_objective_pos(self):
        pass

    def get_objective_target_pos(self):
        pass

    def set_objective_pos_abs(self, vel=None, time=None):
        # if velocity is given, time will be ignored
        pass

    def set_objective_pos_rel(self, vel=None, time=None):  
        # if velocity is given, time will be ignored
        pass


    # Probe scanner Axis/Movement functions
    # ==============================

    def get_probe_scan_range(self, axes=['X','Y','Z']):
        pass

    def get_probe_pos(self):
        pass

    def get_probe_target_pos(self):
        pass

    def set_probe_pos_abs(self, vel=None, time=None):
        #if velocity is given, time will be ignored
        pass
    
    def set_probe_pos_rel(self, vel=None, time=None):
        # if velocity is given, time will be ignored
        pass


    # Probe lifting functions
    # ========================

    def lift_probe(self, rel_value):
        pass

    def get_lifted_value(self):
        # return absolute lifted value
        pass

    def is_probe_landed(self): 
        # return True/False
        pass

    def land_probe(self, fast=False):
        pass
           
    # ==========================================================================
    #                       SPM control methods
    # ==========================================================================
    # axisId: X, Y, Z (or X1, Y1, Z1); X2, Y2, Z2; or lowercase; units: um

    
    #TODO: Combine the methods in a general get_axis_range function for sample 
    #      and objective scanner. Check whether it makes sense.

    # It is more a safety measure to split the request for position and axis 
    # range between the objective and sample scanner.
    

    def get_sample_scanner_range(self, axis_label_list=['X1', 'Y1', 'Z1']):
        """ Get the sample scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'x', 'Y', 'y', 'Z', 'z'] 
                                     or postfixed with a '1':
                                        ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 

        @return dict: sample scanner range dict with requested entries in m 
                      (SI units).
        """

        sc_range = {} # sample scanner range

        for axis_label in axis_label_list:

            axis_label = axis_label.upper()

            if axis_label in self.SAMPLE_AXIS:
                ret_val = self._dev.get_axis_range(axis_label)  # value in um
                if ret_val == 0:
                    self.log.error(f'Error in retrieving the {axis_label} axis range from Sample Scanner.')
                
                sc_range[axis_label] = ret_val * 1e-6 
            else:
                self.log.warning(f'Invalid label "{axis_label}" for Sample Scanner range request. Request skipped.')
        
        return sc_range

    def get_object_scanner_range(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return dict: objective scanner range dict with requested entries in m 
                      (SI units).
        """

        sc_range = {} # objective scanner range

        for axis_label in axis_label_list:

            axis_label = axis_label.upper() 

            if axis_label in self.OBJECTIVE_AXIS:
                ret_val = self._dev.get_axis_range(axis_label)  # value in um
                if ret_val == 0:
                    self.log.error(f'Error in retrieving the {axis_label} axis range from Objective Scanner.')
                sc_range[axis_label] = ret_val * 1e-6 
            else:
                self.log.warning(f'Invalid label "{axis_label}" for Objective Scanner range request. Request skipped.')
        
        return sc_range


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

        sc_pos = {} # sample scanner pos

        for axis_label in axis_label_list:

            axis_label = axis_label.upper() 

            if axis_label in self.SAMPLE_AXIS:
                ret_val = self._dev.get_axis_position(axis_label)
                if ret_val <= -1000:
                    self.log.error(f'Error in retrieving the {axis_label} axis position from Sample Scanner.')
                sc_pos[axis_label] = ret_val * 1e-6
            else:
                self.log.warning(f'Not valid label "{axis_label}" for Sample Scanner position request. Request skipped.')
        
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

        sc_pos = {} # objective scanner pos

        for axis_label in axis_label_list:

            axis_label = axis_label.upper() 

            if axis_label in self.OBJECTIVE_AXIS:
                #ret_val = self._lib.AxisPosition(axis_label.encode()) # value in um
                ret_val = self._dev.get_axis_position(axis_label)
                if ret_val <= -1000:
                    self.log.error(f'Error in retrieving the {axis_label} axis position from Objective Scanner.')
                sc_pos[axis_label] = ret_val * 1e-6
            else:
                self.log.warning(f'Not valid label "{axis_label}" for Objective Scanner position request. Request skipped.')
        
        return sc_pos


    def set_sample_scanner_pos(self, axis_label_dict, move_time=0.1):
        """ Set the sample scanner position.

        @param dict axis_label_dict: the axis label dict, entries either 
                                     capitalized or lower case, possible keys:
                                        ['X', 'x', 'Y', 'y', 'Z', 'z']
                                     or postfixed with a '1':
                                        ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 
                                    Values are the desired position for the 
                                    sample scanner in m. E.g an passed value may
                                    look like

                                        axis_label_dict = {'X':10e-6, 'Y':5e-6}

                                    to set the sample scanner to the absolute 
                                    position x=10um and y=5um.

        @param float move_time: optional, time how fast the scanner is moving 
                                to desired position. Value must be within 
                                [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """

        valid_axis = {}

        for axis_label in axis_label_dict:

            axis_label = axis_label.upper() 
            pos_val = axis_label_dict[axis_label]

            if axis_label in self.SAMPLE_AXIS:
                if axis_label in ['X', 'X1']:
                   ret = self._check_spm_scan_params(x_afm_start=pos_val)
                elif axis_label in ['Y', 'Y1']:
                   ret = self._check_spm_scan_params(y_afm_start=pos_val)
                else:
                   ret = self._check_spm_scan_params(z_afm_start=pos_val)
            else:
                self.log.warning(f'The passed axis label "{axis_label}" is not valid for the sample scanner! Skip call.')
                return -1

            if ret:
                self.log.error(f'Cannot set sample scanner position of axis "{axis_label}" to {pos_val*1e6:.2f}um.')
            else:
                valid_axis[axis_label] = pos_val

        if len(valid_axis) == 0:
            return valid_axis

        self._dev.set_scanner_axes(valid_axis, move_time)

        return self.get_sample_scanner_pos(list(valid_axis))


    def set_objective_scanner_pos(self, axis_label_dict, move_time=0.1):
        """ Set the objective scanner position.

        @param dict axis_label_dict: the axis label dict, entries either 
                                     capitalized or lower case, possible values:
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2']
                                    keys are the desired position for the objective
                                    scanner in m.
        @param float move_time: optional, time how fast the scanner is moving 
                                 to desired position. Value must be within 
                                 [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """

        valid_axis = {}

        for axis_label in axis_label_dict:

            axis_label = axis_label.upper() 
            pos_val = axis_label_dict[axis_label]

            if axis_label in self.OBJECTIVE_AXIS:
                if axis_label == 'X2':
                   ret = self._check_spm_scan_params(x_obj_start=pos_val)
                elif axis_label == 'Y2':
                   ret = self._check_spm_scan_params(y_obj_start=pos_val)
                else:
                   ret = self._check_spm_scan_params(z_obj_start=pos_val)
            else:
                self.log.warning(f'The passed axis label "{axis_label}" is not valid for the objective scanner! Skip call.')
                return -1

            if ret:
                self.log.error(f'Cannot set objective scanner position of axis "{axis_label}" to {pos_val*1e6:.2f}um.')
            else:
                valid_axis[axis_label] = axis_label_dict[axis_label]

        if len(valid_axis) == 0:
            return valid_axis

        self._dev.set_scanner_axes(valid_axis, move_time)

        return self.get_objective_scanner_pos(list(valid_axis))


    @deprecated('Current function is no longer in use')
    def initialize_afm_scan_array(self, num_columns, num_rows):
        """ Initialize the afm scan array. 
        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """

        num_meas_params = len(self.get_available_meas_params())

        # times two due to forward and backward scan.
        return np.zeros((num_meas_params*2, num_rows, num_columns))


    def get_meas_params(self):
        """ Obtain a dict with the available measurement parameters. """
        return copy.copy(self.MEAS_PARAMS)


    #TODO: think about to move this checking routine to logic level and not hardware level
    def _check_spm_scan_params(self, x_afm_start=None, x_afm_stop=None,  
                              y_afm_start=None, y_afm_stop=None,
                              z_afm_start=None, z_afm_stop=None, 
                              x_obj_start=None, x_obj_stop=None,
                              y_obj_start=None, y_obj_stop=None,
                              z_obj_start=None, z_obj_stop=None):
        """ Helper function to check whether input parameters are suitable. 

        @param float x_afm_start: start the afm scan from position x
        @param float x_afm_stop: stop the afm scan at position x
        @param float y_afm_start: start the afm scan from position y
        @param float y_afm_stop: stop the afm scan at position y
        @param float x_obj_start: start the objective scan from position x
        @param float x_obj_stop: stop the objective scan at position x
        @param float y_obj_start: start the objective scan from position y
        @param float y_obj_stop: stop the objective scan at position y
        @param float z_obj_start: start the objective scan from position z
        @param float z_obj_stop: stop the objective scan at position z

        @return int: 0 = False, a range parameter is not fulfilled
                     1 = True, everything is alright   

        Note, all parameters are optional, only those containing values 
        different from None will be checked.
        """
        ret = False
        tol = 0.1e-6 # give a tolerance of 0.1um, since this would be still fine with the scanner.

        if x_afm_start is not None:
            res = x_afm_start < (self.AFM_SCANNER_RANGE[0][0]-tol) or  x_afm_start > (self.AFM_SCANNER_RANGE[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_start of AFM parameter!\n'
                               f'x_start has to be within [{self.AFM_SCANNER_RANGE[0][0]*1e6},{self.AFM_SCANNER_RANGE[0][1]*1e6}]um '
                               f'but it was set to "{x_afm_start*1e6}"um.')

        if x_afm_stop is not None:
            res = x_afm_stop < (self.AFM_SCANNER_RANGE[0][0]-tol) or  x_afm_stop > (self.AFM_SCANNER_RANGE[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_stop of AFM parameter!\n'
                               f'x_stop has to be within [{self.AFM_SCANNER_RANGE[0][0]*1e6},{self.AFM_SCANNER_RANGE[0][1]*1e6}]um '
                               f'but it was set to "{x_afm_stop*1e6}"um.')

        if y_afm_start is not None:
            res = y_afm_start < (self.AFM_SCANNER_RANGE[1][0]-tol) or  y_afm_start > (self.AFM_SCANNER_RANGE[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_start of AFM parameter!\n'
                               f'y_start has to be within [{self.AFM_SCANNER_RANGE[1][0]*1e6},{self.AFM_SCANNER_RANGE[1][1]*1e6}]um '
                               f'but it was set to "{y_afm_start*1e6}"um.')
        
        if y_afm_stop is not None:
            res = y_afm_stop < (self.AFM_SCANNER_RANGE[1][0]-tol) or  y_afm_stop > (self.AFM_SCANNER_RANGE[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_stop of AFM parameter!\n'
                               f'y_stop has to be within [{self.AFM_SCANNER_RANGE[1][0]*1e6},{self.AFM_SCANNER_RANGE[1][1]*1e6}]um '
                               f'but it was set to "{y_afm_stop*1e6}"um.')

        if x_obj_start is not None:
            res = x_obj_start < (self.OBJECTIVE_SCANNER_RANGE[0][0]-tol) or  x_obj_start > (self.OBJECTIVE_SCANNER_RANGE[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_start of Objective parameter!\n'
                               f'x_start has to be within [{self.OBJECTIVE_SCANNER_RANGE[0][0]*1e6},{self.OBJECTIVE_SCANNER_RANGE[0][1]*1e6}]um '
                               f'but it was set to "{x_obj_start*1e6}"um.')

        if x_obj_stop is not None:
            res = x_obj_stop < (self.OBJECTIVE_SCANNER_RANGE[0][0]-tol) or  x_obj_stop > (self.OBJECTIVE_SCANNER_RANGE[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_stop of Objective parameter!\n'
                               f'x_stop has to be within [{self.OBJECTIVE_SCANNER_RANGE[0][0]*1e6},{self.OBJECTIVE_SCANNER_RANGE[0][1]*1e6}]um '
                               f'but it was set to "{x_obj_stop*1e6}"um.')

        if y_obj_start is not None:
            res = y_obj_start < (self.OBJECTIVE_SCANNER_RANGE[1][0]-tol) or  y_obj_start > (self.OBJECTIVE_SCANNER_RANGE[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_start of Objective parameter!\n'
                               f'y_start has to be within [{self.OBJECTIVE_SCANNER_RANGE[1][0]*1e6},{self.OBJECTIVE_SCANNER_RANGE[1][1]*1e6}]um '
                               f'but it was set to "{y_obj_start*1e6}"um.')

        if y_obj_stop is not None:
            res = y_obj_stop < (self.OBJECTIVE_SCANNER_RANGE[1][0]-tol) or  y_obj_stop > (self.OBJECTIVE_SCANNER_RANGE[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_stop of Objective parameter!\n'
                               f'y_stop has to be within [{self.OBJECTIVE_SCANNER_RANGE[1][0]*1e6},{self.OBJECTIVE_SCANNER_RANGE[1][1]*1e6}]um '
                               f'but it was set to "{y_obj_stop*1e6}"um.')

        if z_obj_start is not None:
            res = z_obj_start < (self.OBJECTIVE_SCANNER_RANGE[2][0]-tol) or  z_obj_start > (self.OBJECTIVE_SCANNER_RANGE[2][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for z_start of Objective parameter!\n'
                               f'z_start has to be within [{self.OBJECTIVE_SCANNER_RANGE[2][0]*1e6},{self.OBJECTIVE_SCANNER_RANGE[2][1]*1e6}]um '
                               f'but it was set to "{z_obj_start*1e6}"um.')

        if z_obj_stop is not None:
            res = z_obj_stop < (self.OBJECTIVE_SCANNER_RANGE[2][0]-tol) or  z_obj_stop > (self.OBJECTIVE_SCANNER_RANGE[2][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for z_stop of Objective parameter!\n'
                               f'z_stop has to be within [{self.OBJECTIVE_SCANNER_RANGE[2][0]*1e6},{self.OBJECTIVE_SCANNER_RANGE[2][1]*1e6}]um '
                               f'but it was set to "{z_obj_stop*1e6}"um.')
        return ret


    def check_spm_scan_params_by_plane(self, plane, coord0_start, coord0_stop, coord1_start, coord1_stop):

            # check input values
        if plane == 'XY':
            ret_val = self._check_spm_scan_params(x_afm_start=coord0_start, x_afm_stop=coord0_stop,
                                                  y_afm_start=coord1_start, y_afm_stop=coord1_stop)
        elif (plane == 'XZ' or plane == 'YZ'):
            self.log.error('AFM XZ or YZ scan is not supported. Abort.')
            ret_val = True 
        elif plane == 'X2Y2':
            ret_val = self._check_spm_scan_params(x_obj_start=coord0_start, x_obj_stop=coord0_stop,
                                                  y_obj_start=coord1_start, y_obj_stop=coord1_stop)  
        elif plane == 'X2Z2':
            ret_val = self._check_spm_scan_params(x_obj_start=coord0_start, x_obj_stop=coord0_stop,
                                                  z_obj_start=coord1_start, z_obj_stop=coord1_stop) 
        elif plane == 'Y2Z2':
            ret_val = self._check_spm_scan_params(y_obj_start=coord0_start, y_obj_stop=coord0_stop,
                                                  z_obj_start=coord1_start, z_obj_stop=coord1_stop)           

        return ret_val

           
    def create_scan_leftright(self, x_start, x_stop, y_start, y_stop, res_y):
        """ Create a scan line array for measurements from left to right.
        
        This is only a 'forward measurement', meaning from left to right. It is 
        assumed that a line scan is performed and fast axis is the x axis.
        
        @return list: with entries having the form [x_start, x_stop, y_start, y_stop]
        """
        
        arr = []
        
        y = np.linspace(y_start, y_stop, res_y)
        
        for index, y_val in enumerate(y):
            
            scan_line = []
            scan_line.extend((x_start, x_stop))
            scan_line.extend((y_val, y_val))
                
            arr.append(scan_line)
        return arr     
    
    def create_scan_leftright2(self, x_start, x_stop, y_start, y_stop, res_y):
        """ Create a scan line array for measurements from left to right and back.
        
        This is only a forward and backward measurement, meaning from left to 
        right, and then from right to left. It is assumed that a line scan is 
        performed and fast axis is the x axis.
        
        @return list: with entries having the form [x_start, x_stop, y_start, y_stop]
        """
        arr = []
        
        y = np.linspace(y_start, y_stop, res_y)

        for index, y_val in enumerate(y):
            
            # one scan line forward
            scan_line = []
            scan_line.extend((x_start, x_stop))
            scan_line.extend((y_val, y_val))
            arr.append(scan_line)
            
            # another scan line back
            scan_line = []
            scan_line.extend((x_stop, x_start))
            scan_line.extend((y_val, y_val))
            arr.append(scan_line)
            
        return arr 


    @deprecated('Current function no longer in use')
    def scan_afm_line_by_point(self):
        pass


    @deprecated('Current function no longer in use')
    def scan_obj_line_by_point(self):
        pass

    @deprecated('Current function no longer in use')
    def scan_area_by_line(self, x_start, x_stop, y_start, y_stop, res_x, res_y, 
                          time_forward=1, time_back=1, meas_params=['Height(Dac)']):
        """ Measurement method for a scan by line. An XY area is scanned.
        
        @param float x_start: start coordinate in um
        @param float x_stop: start coordinate in um
        @param float y_start: start coordinate in um
        @param float y_stop: start coordinate in um
        @param int res_x: number of points in x direction
        @param int res_y: number of points in y direction
        @param float time_forward: time forward during the scan
        @param float time_back: time backward after the scan
        @param list meas_params: list of possible strings of the measurement 
                                 parameter. Have a look at MEAS_PARAMS to see 
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list. 
        """
        
        reverse_meas = False
        self._stop_request = False
        self._meas_array_scan = []
        self._scan_counter = 0
        self._line_counter = 0

        # check input values
        ret_val = self._check_spm_scan_params(x_afm_start=x_start, x_afm_stop=x_stop,
                                              y_afm_start=y_start, y_afm_stop=y_stop)
        if ret_val:
            return self._meas_array_scan
        
        scan_arr = self.create_scan_leftright2(x_start, x_stop, y_start, y_stop, res_y)
        
        ret_val, _, _ = self._dev.setup_spm(plane='XY', 
                                       line_points=res_x, 
                                       meas_params=meas_params)

        if ret_val < 1:
            return self._meas_array_scan

        for scan_coords in scan_arr:

            self._dev.setup_scan_line(corr0_start=scan_coords[0], corr0_stop=scan_coords[1], 
                                 corr1_start=scan_coords[2], corr1_stop=scan_coords[3], 
                                 time_forward=time_forward, time_back=time_back)
            self.scan_line()

            # this method will wait until the line was measured.
            scan_line = self._dev.get_scanned_line(reshape=False)

            if reverse_meas:
                self._meas_array_scan.append(list(reversed(scan_line)))
                reverse_meas = False
            else:
                self._meas_array_scan.append(scan_line)
                reverse_meas = True
                
            self._scan_counter += 1
            #self.send_log_message('Line complete.')

            if self._stop_request:
                break

        self.log.info('Scan finished. Yeehaa!')
        print('Scan finished. Yeehaa!')
        self._dev.finish_scan()
        
        return self._meas_array_scan


    @deprecated('Current function no longer in use')
    def start_measure_line(self, coord0_start=48*1e-6, coord0_stop=53*1e-6, 
                           coord1_start=47*1e-6, coord1_stop=52*1e-6, 
                           res_x=40, res_y=40, time_forward=1.5, time_back=1.5,
                           meas_params=['Phase', 'Height(Dac)', 'Height(Sen)']):

        self.meas_thread = threading.Thread(target=self.scan_area_by_line, 
                                            args=(coord0_start, coord0_stop, 
                                                  coord1_start, coord1_stop, 
                                                  res_x, res_y, 
                                                  time_forward, time_back,
                                                  meas_params), 
                                            name='meas_thread')

        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
        else:
            self.meas_thread.start()


    @deprecated('Current function is no longer in use')
    def create_scan_snake(self, x_start, x_stop, y_start, y_stop, res_y):
        """ Create a snake like movement within the scan."""
        # it is assumed that a line scan is performed and fast axis is the x axis.
        
        arr = []
        
        y = np.linspace(y_start, y_stop, res_y)
        
        reverse = False
        for index, y_val in enumerate(y):
            
            scan_line = []
            
            if reverse:
                scan_line.extend((x_stop, x_start))
                reverse = False
            else:
                scan_line.extend((x_start, x_stop))
                reverse = True
                
            scan_line.extend((y_val, y_val))
                
            arr.append(scan_line)
        return arr
 

    @deprecated('Current function is no longer used')
    def check_meas_run(self):
        if hasattr(self, 'meas_thread'):
            if self.meas_thread.isAlive():
                return True
        return False


# ==============================================================================
#                   Higher level interface functions
# ==============================================================================


    def set_up_scanner_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of the
                                      clock
        @param str clock_channel: if defined, this is the physical channel of
                                  the clock

        @return int: error code (0:OK, -1:error)
        """
        pass


    def set_up_afm_scanner(self, scan_params):
        """ Configures the afm scanner for the scan. """
        pass

    def set_up_objective_scanner(self):
        """ Configures the afm scanner for the scan. """
        pass


    def scan_objective_line(self, line_path=None, pixel_clock=False):
        """ Scans a line and returns the counts on that line. """

        pass

    def scan_afm_line(self, line_path=None, scan_params=None):
        """ Scans a line and returns the counts on that line. """
        pass


    def close_afm_scanner(self):
        """ Closes the AFM scanner. """
        pass

    def close_objective_scanner(self):
        """ Closes the AFM scanner. """
        pass

    # =========================================================================
    # Helper functions
    # =========================================================================

    def slice_meas(self, num_params, meas_arr):
        """Slice the provided measurement array according to measured parameters

        Create basically from a measurement matrix (where each row contains 
        the measurement like this

        [ 
            [p1, p2, p3, p1, p2, p3],
            [p1, p2, p3, p1, p2, p3]
            .....
        ]

        Should give
        [
            [ [p1, p1],
              [p1, p1],
              ...
            ],
            [ [p2, p2],
              [p2, p2],
              ...
            ],
            [ [p3, p3],
              [p3, p3],
              ...
        ]

        """

        meas_res = []
        rows, columns = np.shape(meas_arr)

        for num in range(num_params):

            arr = np.zeros((rows, columns//num_params))
            for index, entry in enumerate(arr):
                arr[index] = meas_arr[index][num::num_params]

            meas_res.append(arr)

        return meas_res