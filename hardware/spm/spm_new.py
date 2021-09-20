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
from time import time
import numpy as np
from deprecation import deprecated
from qtpy import QtCore

from core.module import Base, ConfigOption
from hardware.spm.remote_spm import TScanMode, RemoteSPMLibrary

from interface.scanner_interface import ScannerInterface, ScannerMode, ScanStyle, \
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
    #_threaded = False # debug only 
    _version_comp = 'aist-nt_v3.5.150'   # indicates the compatibility of the version.
    __version__ = '0.6.2'
    _spm_dll_ver = '0.0.0'

    # Default values for measurement
    # ------------------------------

    # here are data saved from the test TScanCallback
    #_test_line_scan = []
    #_test_array_scan = []

    # configuration 
    _SCANNER_CONSTRAINTS = ScannerConstraints()
    _SCANNER_MEASUREMENTS = ScannerMeasurements()
    
    _spm_state = ScannerState.DISCONNECTED
    _spm_curr_mode = ScannerMode.UNCONFIGURED
    _spm_curr_sstyle = ScanStyle.POINT
    _spm_curr_params = {}

    _afm_scan_line = np.zeros(0) # scan line array for afm scanner
    _afm_scan_array = np.zeros((9*2, 10, 10)) # Parameters for forward scan dir:
                                              # 0:Height(Dac), 1:Height(Sen), 
                                              # 2:Iprobe, 3:Mag, 4:Phase, 5:Freq, 
                                              # 6:Nf, 7:Lf, 8:Ex1
                                              # and whole thing in reversed scan
                                              # direction.

    _line_counter = 0
 
    # AFM measurement parameter
    _curr_meas_params = []    # store here the current selection from MEAS_PARAMS
    _curr_plan = 'XY'   # store here the current plane

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
    _clientdll = ConfigOption('clientdll', default='remote_spm.dll')  # default aist-nt

    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        self._dev = RemoteSPMLibrary(config, **kwargs) 

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

        if not os.path.isabs(self._libpath):   
            self._libpath = os.path.join(os.path.dirname(__file__), self._libpath)

        self._spm_dll_ver = self.get_library_version()

        self._dev.connect_spm(libpath=self._libpath, libname=self._clientdll)

        if self._dev.is_connected():
            self.set_current_device_state(ScannerState.UNCONFIGURED)
        else:
            self.log.error("Failed to connect to SPM")
            return

        self._create_scanner_contraints()
        self._create_scanner_measurements()


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

    def _create_scanner_contraints(self):

        sc = self._SCANNER_CONSTRAINTS

        sc.max_detectors = 1

        # current modes, as implemented.  Enable others when available
        sc.scanner_modes = [ ScannerMode.OBJECTIVE_XY, 
                             ScannerMode.OBJECTIVE_XZ,
                             ScannerMode.OBJECTIVE_YZ,
                             ScannerMode.PROBE_CONTACT,
                             ScannerMode.PROBE_CONSTANT_HEIGHT ]  

        sc.scanner_mode_states = { ScannerMode.OBJECTIVE_XY: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING],

                                   ScannerMode.OBJECTIVE_XZ: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING],

                                   ScannerMode.OBJECTIVE_YZ: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING],

                                   ScannerMode.PROBE_CONTACT: [ ScannerState.IDLE,
                                                                ScannerState.PROBE_MOVING,
                                                                ScannerState.PROBE_SCANNING,
                                                                ScannerState.PROBE_LIFTED],

                                   ScannerMode.PROBE_CONSTANT_HEIGHT: [
                                                                ScannerState.IDLE,
                                                                ScannerState.PROBE_MOVING,
                                                                ScannerState.PROBE_SCANNING_LIFTED,
                                                                ScannerState.PROBE_LIFTED],
                                    
                                   ScannerMode.PROBE_DUAL_PASS: [ ],   # not yet implemented
                                   ScannerMode.PROBE_Z_SWEEP  : [ ]    # not yet implemented
                                }

        sc.scanner_styles = [ScanStyle.POINT, ScanStyle.LINE] 

        sc.scanner_mode_params = {}           # to be defined
        sc.scanner_mode_params_defaults = {}  # to be defined

        
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

                            'VALID_AXES'     : [ *sm.scanner_axes['SAMPLE_AXES'], 
                                                 *sm.scanner_axes['OBJECTIVE_AXES']],
        }

        sm.scanner_planes = ['XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2']

        sm.scanner_sensors = {  # name of sensor parameters 
                                'SENS_PARAMS_SAMPLE'    : ['SenX', 'SenY', 'SenZ'],   # AFM sensor parameter
                                'SENS_PARAMS_OBJECTIVE' : ['SenX2', 'SenY2', 'SenZ2'],

                                # maximal range of the AFM scanner , x, y, z
                                'SAMPLE_SCANNER_RANGE' :    [[0, 100e-6], [0, 100e-6], [0, 12e-6]],
                                'OBJECTIVE_SCANNER_RANGE' : [[0, 30e-6], [0, 30e-6], [0, 10e-6]]
                             }


    def get_current_configuration(self):
        """ Returns the current scanner configuration

        @return tuple: (mode, scan_style)
        """
        return self._spm_curr_mode, self._spm_curr_sstyle 


    def configure_scanner(self, mode, params, scan_style=ScanStyle.LINE):
        """ Configures the scanner device for current measurement. 

        @param ScannerMode mode: mode of scanner
        @param ScannerStyle scan_style: movement of scanner
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """
        dev_state = self.get_current_device_state()
        curr_mode, curr_params, curr_sstyle = self.get_current_device_config()

        # note that here, all methods configure the SPM for "TscanMode.LINE_SCAN"
        # since all measurements are gathered in a line format
        # however, the movement is determined by the ScanStyle, which determines
        # if a trigger signal will be produced for the recorder device 
        std_config = {
            ScannerMode.OBJECTIVE_XY:  { 'plane'       : 'X2Y2', 
                                         'meas_params' : [],
                                         'scan_mode'   : TScanMode.LINE_SCAN },

            ScannerMode.OBJECTIVE_XZ:  { 'plane'       : 'X2Z2', 
                                         'meas_params' : [],
                                         'scan_mode'   : TScanMode.LINE_SCAN },

            ScannerMode.OBJECTIVE_YZ:  { 'plane'       : 'Y2Z2', 
                                         'meas_params' : [],
                                         'scan_mode'   : TScanMode.LINE_SCAN },

            ScannerMode.PROBE_CONTACT: { 'plane'       : 'XY', 
                                         'scan_mode'   : TScanMode.LINE_SCAN },

            # other configurations to be defined as they are implemented
        }

        if (dev_state != ScannerState.UNCONFIGURED) or (dev_state != ScannerState.IDLE):
            self.log.error(f'SmartSPM cannot be configured in the '
                           f'requested mode "{ScannerMode.name(mode)}", since the device '
                           f'state is in "{dev_state}". Stop ongoing '
                           f'measurements and make sure that the device is '
                           f'connected to be able to configure if '
                           f'properly.')
            return -1

        limits = self.get_scanner_constraints()

        if mode not in limits.scanner_modes:
            mode_name = ScannerMode.name(mode) if ScannerMode.name(mode) is not None else mode
            self.log.error(f'Requested mode "{mode_name}" not available for SPM. '
                            'Check that mode is defined via the ScannerMode Enum type. ' 
                            'Configuration stopped.')
            return -1            

        if not isinstance(scan_style,ScanStyle):
            self.log.error(f'ScanStyle="{scan_style} is not a know scan style')
            return -1
        
        sc_defaults = limits.scanner_mode_params_defaults[mode]
        is_ok = self._check_params_for_mode(mode, params)
        if not is_ok: 
            self.log.error(f'Parameters are not correct for mode "{ScannerMode.name(mode)}". '
                           f'Configuration stopped.')
            return -1
        
        ret_val = 0

        # the associated error message for a -1 return value should come from 
        # the method which was called (with a reason, why configuration could 
        # not happen).

        # after all the checks are successful, delegate the call to the 
        # appropriate preparation function.
        if mode == ScannerMode.UNCONFIGURED:
            return -1   # nothing to do, mode is unconfigured, so we shouldn't continue

        elif mode == ScannerMode.OBJECTIVE_XY:
            # Objective scanning returns no parameters
            ret_val, curr_plane, curr_meas_params = \
                self._dev.setup_spm(**std_config[ScannerMode.OBJECTIVE_XY],
                                    line_points = params['line_points'])

        elif mode == ScannerMode.OBJECTIVE_XZ:
            # Objective scanning returns no parameters
            ret_val, curr_plane, curr_meas_params = \
                self._dev.setup_spm(**std_config[ScannerMode.OBJECTIVE_XZ],
                                    line_points = params['line_points'])

        elif mode == ScannerMode.OBJECTIVE_YZ:
            # Objective scanning returns no parameters
            ret_val, curr_plane, curr_meas_params = \
                self._dev.setup_spm(**std_config[ScannerMode.OBJECTIVE_YZ],
                                    line_points = params['line_points'])

        elif mode == ScannerMode.PROBE_CONTACT:
            # Scanner library specific style is always "LINE_STYLE" 
            # both line-wise and point-wise scans configure a line;
            # For internal "line_style" scan definitions, the additional trigger signal 
            # is activated
            ret_val, curr_plane, curr_meas_params = \
                self._dev.setup_spm(**std_config[ScannerMode.PROBE_CONTACT],
                                    line_points = params['line_points'],
                                    meas_params = params['meas_params'])

        else:
            """
            To be eventually implemented:

            mode       : PROBE_CONSTANT_HEIGHT
            params     : [line_points, meas_params, lift_height]
            scan_style : LINE or POINT

            mode       : PROBE_DUAL_PASS
            params     : [ line_points, meas_params_pass1, meas_params_pass2, lift_height]
            scan_style : LINE or POINT

            mode       : PROBE_Z_SWEEP
            params     : [line_points, meas_params]
            scan_style : LINE or POINT 
            """

            self.log.error(f'Error configure_scanner(): mode = "{ScannerMode.name(mode)}"'
                            ' has not been implemented yet')
            return -1

        ret_val |= self.check_spm_scan_params_by_plane(plane=curr_plane,
                                                       coord0_start=params['coord0_start'], 
                                                       coord0_stop= params['coord0_stop'],
                                                       coord1_start=params['coord1_start'],
                                                       coord1_stop= params['coord1_stop'])

        if scan_style == ScanStyle.LINE:
            self._dev.set_ext_trigger(True)

        self._spm_curr_sstyle = scan_style

        return ret_val


    def configure_line(self, 
                       corr0_start, corr0_stop, 
                       corr1_start, corr1_stop, # not used in case of z sweep
                       time_forward, time_back):
        """ Setup the scan line parameters
        
        @param float coord0_start: start point for coordinate 0 in m
        @param float coord0_stop: stop point for coordinate 0 in m
        @param float coord1_start: start point for coordinate 1 in m
        @param float coord1_stop: stop point for coordinate 1 in m
        @param float time_forward: time for forward movement during linescan in s
                                   For line-scan mode time_forward is equal to 
                                   the time-interval between starting of the 
                                   first scanned point and ending of the last 
                                   scan point. 
                                   For point-scan tforw is the sum of all 
                                   time-intervals between scan points.
        @param float time_back: sets the time-interval for back (idle) movement 
                                in s when the back displacement is abs equal to 
                                the forward displacement, it also defines the 
                                time interval when move to first scan point.
        
        @return bool: status variable with: 
                        False (=0) call failed
                        True (=1) call successful

        This is a general function, a line is scanned in a previously configured
        plane. It is possible to set zero scan area, then some reasonable 
        values for time_forward and time_back will be chosen automatically.
        """               
        if self._spm_curr_sstyle != ScanStyle.LINE:
            self.log.error('Request to configure line of "LINE", but method not configured')

        return self._dev.setup_scan_line(corr0_start = corr0_start, corr0_stop = corr0_stop,
                                         corr1_start = corr1_start, corr1_stop = corr1_stop,
                                         time_forward = time_forward, time_back = time_back)

        
    def scan_line(self,int_time = 0.05): 
        """Execute a scan line measurement. 

        @param float int_time: integration time in s while staying on one point.
                               this setting is only valid for point-scan mode 
                               and will be ignored for a line-scan mode.  
        
        Every scan procedure starts with setup_spm method. Then
        setup_scan_line follows (first time and then next time current 
        scan line was completed)

        @return int: status variable with: 0 = call failed, 1 = call successful
        """
        if self._spm_curr_sstyle != ScanStyle.LINE:
            self.log.error('Request to perform scan style="LINE", but method not configured')

        return self._dev.scan_line(int_time=int_time)
        

    def scan_point(self, num_params=None):
        """ Obtain measurments from a point
        (blocking method, required configure_scan_line to be called prior)
        Performed after setting up the scanner perform a scan of a point. 

        @param int num_params: set the expected parameters per point, minimum is 0

        @return list: Measured signals of the previous point. 

        First number tells the size of the array, second variable is the pointer
        to the reference array. It is converted directly to a python list array.

        Explanation of the Point scan procedure:
            The function ExecScanPoint moves to the next point of the scan line 
            and return data measured for previous point of the line. For the 1st
            point of the scan line, the ExecScanPoint returns just size = 0.
            For the last point of the line need to call ExecScanPoint two times:
                to receive the data from previous point 
                and then from last point
            So, when next ExecScanPoint return control, you can start to get 
            data from some other external device, while SPM accumulating signals
            in given scan-point.
            After scan line ends, need to call next SetupScanLine
        """
        if self._spm_curr_sstyle != ScanStyle.POINT:
            self.log.error('Request to perform scan style="POINT", but method not configured')

        self._dev.scan_point(num_params=num_params) 


    def get_measurement(self):
        """ Obtains gathered measurements from scanner
            Returns a scanned line after it is completely scanned. Wait until
            this is the case.

        @param bool reshape: return in a reshaped structure, i.e every signal is
                             in its separate row.

        @return ndarray: with dimension either
                reshape=True : 2D array[num_of_signals, pixel_per_line]
                reshape=False:  1D array[num_of_signals * pixel_per_line]

        # (required configure_scan_line to be called prior)
        # => blocking method, either with timeout or stoppable via stop measurement
        """    
        pass


    def finish_scan(self):
        """ Request completion of the current scan line 
        It is correct (but not abs necessary) to end each scan 
        process by this method. There is no problem for 'Point' scan, 
        performed with 'scan_point', to stop it at any moment. But
        'Line' scan will stop after a line was finished, otherwise 
        your software may hang until scan line is complete.

        @return int: status variable with: 0 = call failed, 1 = call successfull
        """
        self._dev.finish_scan()
        self.set_current_device_state(ScannerState.UNCONFIGURED)
    

    def stop_measurement(self):
        """ Immediately terminate the measurment
        Hardcore stop mechanism, which proposes the following actions:
        - if PROBE_CONSTANT_HEIGHT: land_probe
        - if PROBE_DUAL_PASS: land_probe
        - if PROBE_Z_SWEEP: BreakProbeSweepZ
        """

        # - land probe after each scan! land_probe(fast=False)
        # => configuration will be set to UNCONFIGURED
        self._dev.stop_measurement() 
        self.set_current_device_state(ScannerState.UNCONFIGURED)


    def calibrate_constant_height(self, calib_points, safety_lift):
        """ Calibrate constant height

        Performs a lift-move-land height mode calibration for the sample
        at the defined calib_points locations.  During the move, the
        probe is lifted to a safe height for travel ('safety_lift')
        
        @param: array calib_points: sample coordinates X & Y of where 
                to obtain the height; e.g. [ [x0, y0], [x1, y1], ... [xn, yn]]
        @param: float safety_lift: height (m) to lift the probe during traversal
                (+ values up...increasing the distance between probe & sample)
        
        @return: array calibrate_points: returns measured heights with the 
                 the original coordinates:  [[x0, y0, z0], [x1, y1, z1], ... [xn, yn, zn]] 
        """    
        
        pass


    def get_constant_height_calibration(self):
        """ Returns the calibration points, as gathered by the calibrate_constant_height() mode

        @return: array calibrate_points: returns measured heights with the 
                 the original coordinates:  [[x0, y0, z0], [x1, y1, z1], ... [xn, yn, zn]] 
        """
        pass


    # Device specific functions
    # =========================
    def reset_device(self):
        """ Resets the device back to the initial state

        @params: None

        @return bool: status variable with: 
                        False (=0) call failed
                        True (=1) call successful
        """
        pass


    def get_current_device_state(self):
        """ Get the current device state 

        @return: ScannerState.(state) 
                 returns the state of the device, as allowed for the mode  
        """      
        return self._spm_state


    def set_current_device_state(self, state):
        """ Sets the current device state 

        @return: ScannerState: current device state
        """          """ Sets the current device state 

        @return: True (success) or False (failure)
                 (currently, there is no policing of the state for the mode)
        """      
        self._spm_state = state 
        return True 


    def get_current_device_config(self):     
        """ Gets the current device state 

        @return: ScannerState: current device state
        """  
        mode = self._spm_curr_mode 
        params = self._spm_curr_params
        style = self._spm_curr_sstyle

        return mode, params, style


    def get_device_meta_info(self, query=None):
        """ Gets the device meta info
        This is specific to the device, as needed by the implemenation.  
        The information is returned as a dictionary with the relevant values
        e.g.: {'SERVER_VERSION':       self._dev.server_interface_version(),
               'CLIENT_VERSION':       self._dev.client_interface_version(),
               'IS_SERVER_COMPATIBLE': self._dev.is_server_compatible(),
               'LIBRARY_VERSION':      self.get_library_version() 
               } 

        @param: str query(optional):  retrieve a specific key from the dictionary,
                otherwise, the entire dictionary is returned

        @return: value or dict:  if 'query is supplied, then specific setting is return
                otherwise, the entire dictionary is returned
        """      
        dev_info = {'SERVER_VERSION':       self._dev.server_interface_version(),
                    'CLIENT_VERSION':       self._dev.client_interface_version(),
                    'IS_SERVER_COMPATIBLE': self._dev.is_server_compatible(),
                    'LIBRARY_VERSION':      self.get_library_version()
                   } 

        if query is not None and dev_info.get(query):
            return dev_info[query] 
        else: 
            return dev_info


    def get_scanner_constraints(self):
        """ Returns the current scanner contraints

        @return dict: scanner contraints as defined for the device
        """
        return copy.copy(self._SCANNER_CONSTRAINTS)


    def get_available_scan_modes(self):
        """ Gets the available scan modes for the device 

        @return: list: available scan modes of the device, as [ScannerMode ...] 
        """      
        sc = self._SCANNER_CONSTRAINTS
        return copy.copy(sc.scanner_modes)


    def get_available_scan_style(self):
        """ Gets the available scan styles for the device 
        Currently, this is only 2 modes: [ScanStyle.LINE, ScanStyle.POINT]

        @return: list: available scan styles of the device, as [ScanStyle ...] 
        """
        sc = self._SCANNER_CONSTRAINTS 
        return copy.copy(sc.scanner_styles)
        

    def get_available_measurement_methods(self):
        """  Gets the available measurement modes of the device
        obtains the dictionary of aviable measurement methods
        This is device specific, but is an implemenation of the 
        ScannerMeasurements class

        @return: scanner_measurements class implementation 
        """
        sm = self._SCANNER_MEASUREMENTS
        return copy.copy(sm)


    def get_parameters_for_mode(self, mode):
        """ Gets the parameters required for the mode
        Returns the scanner_constraints.scanner_mode_params for given mode

        @param: ScannerMode mode: mode to obtain parameters for (required parameters)
        
        @return: parameters for mode, from scanner_constraints
        """
        sc = self._SCANNER_CONSTRAINTS
        return sc.scanner_mode_params.get(mode, None) 


    def get_scanner_measurements(self):
        """ Gets the parameters defined unders ScannerMeasurements definition
        This returns the implemenation of the ScannerMeasurements class

        @return ScannerMeasurements instance 
        """
        sm = self.get_available_measurements_methods()
        return sm.scanner_measurements


    def _check_params_for_mode(self, mode, params):
        """ Make sure that all the parameters are present for the current mode.
        
        @param ScannerMode mode: mode of scanner, as available from 
                                  ScannerMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        return bool:
                True: Everything is fine
                False: parameters are missing. Missing parameters will be 
                       indicated in the error log/message.

        This method assumes that the passed mode is in the available options,
        no need to double check if mode is present it available modes.
        """
        is_ok = True
        limits = self.get_scanner_constraints()
        allowed_modes = limits.scanner_modes
        required_params = limits.scanner_mode_params
        optional_params = limits.scanner_mode_params_defaults

        if mode not in allowed_modes:
            is_ok = False
            return is_ok

        # check that the required parameters are supplied
        fulfilled = set() 
        for entry in required_params:
            if params.get(entry, None) is None:
                self.log.warning(f'Parameter "{entry}" not specified for mode '
                                 f'"{ScannerMode.name(mode)}". Correct this!')
                is_ok = False
            else:
                fulfilled.update(entry)

        if not is_ok:
            return is_ok

        # check that optional parameters have been spelled correctly
        # here, the parameters which have already been processed are skipped
        remaining = set(params.keys()) - fulfilled
        for entry in remaining:
            if optional_params.get(entry, None):
                self.log.warning(f'Supplied optional parameter "{entry}" is not a known definition '
                                 f'for "{ScannerMode.name(mode)}". Correct this!')
                is_ok = False                                 

        return is_ok


    #Objective scanner Axis/Movement functions
    #==============================

    def get_objective_scan_range(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return dict: objective scanner range dict with requested entries in m 
                      (SI units).
        """
        sm = self.get_available_scan_measurements()
        axes = sm.scanner_axes['OBJECTIVE_AXES']

        sc_range = {} # objective scanner range

        for axis_label in axis_label_list:
            axis_label = axis_label.upper() 

            if axis_label in axes:
                ret_val = self._dev.get_axis_range(axis_label)  # value in um
                if ret_val == 0:
                    self.log.error(f'Error in retrieving the {axis_label} axis range from Objective Scanner.')
                sc_range[axis_label] = ret_val * 1e-6 
            else:
                self.log.warning(f'Invalid label "{axis_label}" for Objective Scanner range request. Request skipped.')
        
        return sc_range


    def get_objective_pos(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner position. 
        Returns the current position of the scanner objective

        @param str axis_label_list: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """
        sm = self.get_available_scan_measurements()
        axes = sm.scanner_axes['OBJECTIVE_AXES']

        sc_pos = {} # objective scanner pos

        for axis_label in axis_label_list:
            axis_label = axis_label.upper() 

            if axis_label in axes:
                ret_val = self._dev.get_axis_position(axis_label)
                if ret_val <= -1000:
                    self.log.error(f'Error in retrieving the {axis_label} axis position from Objective Scanner.')
                sc_pos[axis_label] = ret_val * 1e-6
            else:
                self.log.warning(f'Not valid label "{axis_label}" for Objective Scanner position request. Request skipped.')
        
        return sc_pos


    def get_objective_target_pos(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner target position. 
        Returns the potential position of the scanner objective (understood to be the next point)

        @param str axis_label_list: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """
        sm = self.get_available_scan_measurements()
        axes = sm.scanner_axes['OBJECTIVE_AXES']

        sc_pos = {} # objective scanner pos

        for axis_label in axis_label_list:
            axis_label = axis_label.upper() 

            if axis_label in axes:
                ret_val = self._dev.obtain_axis_setpoint(axis_label)
                if ret_val <= -1000:
                    self.log.error(f'Error in retrieving the {axis_label} axis target position from Objective Scanner.')
                sc_pos[axis_label] = ret_val * 1e-6
            else:
                self.log.warning(f'Not valid label "{axis_label}" for Objective Scanner position request. Request skipped.')
        
        return sc_pos


    def set_objective_pos_abs(self, axis_label_dict, move_time=0.1):
        """ Set the objective scanner position in physical coordinates (absolute).

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
        sm = self.get_available_scan_measurements()
        axis_list = sm.scanner_axes['OBJECTIVE_AXES']

        valid_axis = {}

        for axis_label in axis_label_dict:

            axis_label = axis_label.upper() 
            pos_val = axis_label_dict[axis_label]

            if axis_label in axis_list:
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

        return self.get_objective_pos(list(valid_axis))

   
    def set_objective_pos_rel(self, axis_rel_dict, move_time=0.1):
        """ Set the objective scanner position, relative to current position.

        @param dict axis_rel_dict:  the axis label dict, entries either 
                                capitalized or lower case, possible keys:
                                     ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2']
                                Values are the desired position for the 
                                sample scanner in m. E.g an passed value may
                                look like

                                    axis_rel_dict = {'X2':1.5e-6, 'Y2':-0.5e-6, 'Z2':10e-6}

                                to set the objectvie scanner to the relative  
                                position x=+10um, y=+5um, z=+2um
                                this is translated to absolute coordinates via
                                x_new_abs[i] = x_curr_abs[i] + x_rel[i]
                                (where x is a generic axis)

        @param float move_time: optional, time how fast the scanner is moving 
                                to desired position. Value must be within 
                                [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """
        axis_labels = list(axis_rel_dict.keys())
        curr_axis_pos_abs = self.get_objective_pos(axis_labels)
        
        new_axis_pos_abs = { l: curr_axis_pos_abs[l] + axis_rel_dict[l] for l in curr_axis_pos_abs.keys() } 

        return self.set_objective_pos_abs(new_axis_pos_abs, move_time=move_time)


    # Probe scanner Axis/Movement functions
    # ==============================

    def get_sample_scan_range(self, axis_label_list=['X1', 'Y1', 'Z1']):
        """ Get the sample scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'x', 'Y', 'y', 'Z', 'z'] 
                                     or postfixed with a '1':
                                        ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 

        @return dict: sample scanner range dict with requested entries in m 
                      (SI units).
        """
        sm = self.get_available_scan_measurements()
        axes = sm.scanner_axes['SAMPLE_AXES']

        sc_range = {} # sample scanner range

        for axis_label in axis_label_list:
            axis_label = axis_label.upper()

            if axis_label in axes:
                ret_val = self._dev.get_axis_range(axis_label)  # value in um
                if ret_val == 0:
                    self.log.error(f'Error in retrieving the {axis_label} axis range from Sample Scanner.')
                
                sc_range[axis_label] = ret_val * 1e-6 
            else:
                self.log.warning(f'Invalid label "{axis_label}" for Sample Scanner range request. Request skipped.')
        
        return sc_range


    def get_sample_pos(self, axis_label_list=['X1', 'Y1', 'Z1']):
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
        sm = self.get_available_scan_measurements()
        axes = sm.scanner_axes['SAMPLE_AXES']

        sc_pos = {} # sample scanner pos

        for axis_label in axis_label_list:
            axis_label = axis_label.upper() 

            if axis_label in axes:
                ret_val = self._dev.get_axis_position(axis_label)
                if ret_val <= -1000:
                    self.log.error(f'Error in retrieving the {axis_label} axis position from Sample Scanner.')
                sc_pos[axis_label] = ret_val * 1e-6
            else:
                self.log.warning(f'Not valid label "{axis_label}" for Sample Scanner position request. Request skipped.')
        
        return sc_pos


    def get_sample_target_pos(self, axis_label_list=['X1', 'Y1', 'Z1']):
        """ Get the set point of the axes locations (this is where it will move to) 

        @param list axis_label_list: axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'x', 'Y', 'y', 'Z', 'z'] 
                                     or postfixed with a '1':
                                        ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 

        @return dict: sample scanner position dict in m (SI units). Normal 
                      output [0 .. AxisRange], though may fall outside this 
                      interval. Error: output <= -1000
        """
        sm = self.get_available_scan_measurements()
        axes = sm.scanner_axes['SAMPLE_AXES']

        sc_pos = {} # sample scanner pos

        for axis_label in axis_label_list:
            axis_label = axis_label.upper() 

            if axis_label in axes:
                ret_val = self._dev.obtain_axis_setpoint(axis_label)
                if ret_val <= -1000:
                    self.log.error(f'Error in retrieving the {axis_label} axis target position from Sample Scanner.')
                sc_pos[axis_label] = ret_val * 1e-6
            else:
                self.log.warning(f'Not valid label "{axis_label}" for Sample Scanner position request. Request skipped.')
        
        return sc_pos


    def set_sample_pos_abs(self, axis_dict, move_time=0.1):
        """ Set the sample scanner position.

        @param dict axis_dict: the axis label dict, entries either 
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
        sm = self.get_available_scan_measurements()
        axis_list = sm.scanner_axes['SAMPLE_AXES']

        valid_axes = {}

        for axis_label in axis_dict:
            axis_label = axis_label.upper() 
            pos_val = axis_dict[axis_label]

            if axis_label in axis_list:
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
                valid_axes[axis_label] = pos_val

        if len(valid_axes) == 0:
            return valid_axes

        self._dev.set_scanner_axes(valid_axes, move_time)

        return self.get_sample_pos(list(valid_axes))

   
    def set_sample_pos_rel(self, axis_rel_dict, move_time=0.1):
        """ Set the sample scanner position, relative to current position.

        @param dict axis_rel_dict:  the axis label dict, entries either 
                                capitalized or lower case, possible keys:
                                     ['X', 'x', 'Y', 'y', 'Z', 'z']
                                or postfixed with a '1':
                                   ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 
                                Values are the desired position for the 
                                sample scanner in m. E.g an passed value may
                                look like

                                   axis_label_dict = {'X':10e-6, 'Y':5e-6}

                                to set the sample scanner to the relative  
                                    position x=+10um and y=+5um.
                                this is translated to absolute coordinates via
                                x_new_abs[i] = x_curr_abs[i] + x_rel[i]
                                (where x is a generic axis)

        @param float move_time: optional, time how fast the scanner is moving 
                                to desired position. Value must be within 
                                [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """
        axis_labels = list(axis_rel_dict.keys())
        curr_axis_pos_abs = self.get_sample_pos(axis_labels)
        
        new_axis_pos_abs = { l: curr_axis_pos_abs[l] + axis_rel_dict[l] for l in curr_axis_pos_abs.keys() } 

        return self.set_sample_pos_abs(new_axis_pos_abs, move_time=move_time)



    # Probe lifting functions
    # ========================

    def lift_probe(self, rel_z):
        """ Lift the probe on the surface.
        @param float rel_z: lifts the probe by rel_z distance (m) (adds to previous lifts)  

        @return bool: Function returns True if method succesful, False if not
        """
        pass


    def get_lifted_value(self):
        """ Gets the absolute lift from the sample (sample land, z=0)

        Note, this is not the same as the absolute Z position of the sample + lift
        Since the sample height is always assumed to be 0 (no Z dimension).  
        In reality, the sample has some thickness and the only way to measure Z 
        is to make a distance relative to this surface

        @return float: absolute lifted distance from sample (m)
        """
        pass


    def is_probe_landed(self): 
        """ Returns state of probe, if it is currently landed or lifted

        @return bool: True = probe is currently landed 
                      False = probe is in lifted mode
        """
        pass


    def land_probe(self, fast=False):
        """ Land the probe on the surface.
        @param bool: fast: if fast=True, use higher velocity to land (see below)

        @return bool: Function returns true if the probe was first lifted, i.e.
                      Z-feedback input is SenZ

        fast=True:
            Z-feedback input is switched to previous (Mag, Nf, etc.), the same is 
            for other parameters: gain, setpoint land may be too slow if starting 
            from big lifts, say from 1 micron; then it will be possible to rework 
            the function or implement some new.

        fast=False:
            Landing with constant and always reasonable value for Z-move rate unlike
            in the case of self.probe_land(). The method is useful when start 
            landing from big tip-sample gaps, say, more than 1 micron. When call the
            function after ProbeLift, it switches the Z-feedback input same as 
            self.probe_land().
            Otherwise it does not switch Z-feedback input, does not set setpoint and
            feedback gain.

        """
        if fast:
            return self._dev.probe_land() 
        else:
            return self._dev.probe_land_soft()
           

    #TODO: think about to move this checking routine to logic level and not hardware level
    def _check_spm_scan_params(self, 
                              x_afm_start=None, x_afm_stop=None,  
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
        sm = self.get_available_scan_measurements()
        sample_range = sm.scanner_measurements['SAMPLE_SCANNER_RANGE']
        objective_range = sm.scanner_measurements['OBJECTIVE_SCANNER_RANGE']

        if x_afm_start is not None:
            res = x_afm_start < (sample_range[0][0]-tol) or  x_afm_start > (sample_range[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_start of AFM parameter!\n'
                               f'x_start has to be within [{sample_range[0][0]*1e6},{sample_range[0][1]*1e6}]um '
                               f'but it was set to "{x_afm_start*1e6}"um.')

        if x_afm_stop is not None:
            res = x_afm_stop < (sample_range[0][0]-tol) or  x_afm_stop > (sample_range[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_stop of AFM parameter!\n'
                               f'x_stop has to be within [{sample_range[0][0]*1e6},{sample_range[0][1]*1e6}]um '
                               f'but it was set to "{x_afm_stop*1e6}"um.')

        if y_afm_start is not None:
            res = y_afm_start < (sample_range[1][0]-tol) or  y_afm_start > (sample_range[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_start of AFM parameter!\n'
                               f'y_start has to be within [{sample_range[1][0]*1e6},{sample_range[1][1]*1e6}]um '
                               f'but it was set to "{y_afm_start*1e6}"um.')
        
        if y_afm_stop is not None:
            res = y_afm_stop < (sample_range[1][0]-tol) or  y_afm_stop > (sample_range[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_stop of AFM parameter!\n'
                               f'y_stop has to be within [{sample_range[1][0]*1e6},{sample_range[1][1]*1e6}]um '
                               f'but it was set to "{y_afm_stop*1e6}"um.')

        if x_obj_start is not None:
            res = x_obj_start < (objective_range[0][0]-tol) or  x_obj_start > (objective_range[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_start of Objective parameter!\n'
                               f'x_start has to be within [{objective_range[0][0]*1e6},{objective_range[0][1]*1e6}]um '
                               f'but it was set to "{x_obj_start*1e6}"um.')

        if x_obj_stop is not None:
            res = x_obj_stop < (objective_range[0][0]-tol) or  x_obj_stop > (objective_range[0][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for x_stop of Objective parameter!\n'
                               f'x_stop has to be within [{objective_range[0][0]*1e6},{objective_range[0][1]*1e6}]um '
                               f'but it was set to "{x_obj_stop*1e6}"um.')

        if y_obj_start is not None:
            res = y_obj_start < (objective_range[1][0]-tol) or  y_obj_start > (objective_range[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_start of Objective parameter!\n'
                               f'y_start has to be within [{objective_range[1][0]*1e6},{objective_range[1][1]*1e6}]um '
                               f'but it was set to "{y_obj_start*1e6}"um.')

        if y_obj_stop is not None:
            res = y_obj_stop < (objective_range[1][0]-tol) or  y_obj_stop > (objective_range[1][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for y_stop of Objective parameter!\n'
                               f'y_stop has to be within [{objective_range[1][0]*1e6},{objective_range[1][1]*1e6}]um '
                               f'but it was set to "{y_obj_stop*1e6}"um.')

        if z_obj_start is not None:
            res = z_obj_start < (objective_range[2][0]-tol) or  z_obj_start > (objective_range[2][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for z_start of Objective parameter!\n'
                               f'z_start has to be within [{objective_range[2][0]*1e6},{objective_range[2][1]*1e6}]um '
                               f'but it was set to "{z_obj_start*1e6}"um.')

        if z_obj_stop is not None:
            res = z_obj_stop < (objective_range[2][0]-tol) or  z_obj_stop > (objective_range[2][1]+tol)
            ret = ret | res
            if res:
                self.log.error(f'Invalid scan settings for z_stop of Objective parameter!\n'
                               f'z_stop has to be within [{objective_range[2][0]*1e6},{objective_range[2][1]*1e6}]um '
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


    @deprecated('Current function is no longer in use')
    def initialize_afm_scan_array(self, num_columns, num_rows):
        """ Initialize the afm scan array. 
        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """

        num_meas_params = len(self.get_available_meas_params())

        # times two due to forward and backward scan.
        return np.zeros((num_meas_params*2, num_rows, num_columns))
          

    @deprecated('Current function no longer in use')
    def scan_afm_line_by_point(self):
        pass


    @deprecated('Current function no longer in use')
    def scan_obj_line_by_point(self):
        pass


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