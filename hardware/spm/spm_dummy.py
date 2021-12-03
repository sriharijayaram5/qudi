# -*- coding: utf-8 -*-
"""
Dummy implementation for spm devices.

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
import copy
from core.module import Base
from core.util.mutex import Mutex

from interface.scanner_interface import ScannerInterface, ScannerMode, ScanStyle, \
                                        ScannerState, ScannerConstraints, ScannerMeasurements  

class SPMDummy(Base, ScannerInterface):
    """ Smart SPM wrapper for the communication with the module.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'smart_spm.SmartSPM'
        libpath: 'path/to/lib/folder'

    """

    _modclass = 'SPMDummy'
    _modtype = 'hardware'

    _SCANNER_CONSTRAINTS = ScannerConstraints()
    _SCANNER_MEASUREMENTS = ScannerMeasurements()

    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        # locking mechanism for thread safety. 
        self.threadlock = Mutex()

        # use it like this:
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.

        # checking for the right configuration
        for key in config.keys():
            self.log.debug('{0}: {1}'.format(key, config[key]))

    def on_activate(self):
        """ Prepare and activate the spm module. """
        self._create_scanner_contraints()
        self._create_scanner_measurements()

        pass

    def on_deactivate(self):
        """ Clean up and deactivate the spm module. """
        pass


    # current methods:

    """
    create_scan_leftright       => logic methods!!
    create_scan_leftright2      => logic methods!!
    create_scan_snake           => logic methods!!
    check_spm_scan_params_by_plane => put this check into logic and get all the limits from hardware

    get_meas_params             => get this from settings/limits
    setup_spm                   => configure_scan_device
    set_ext_trigger             => include in configure_scan_device
    setup_scan_line             => configure_scan_line
    scan_line                   => scan_line
    get_scanned_line            => get_scanned_line
    finish_scan                 => stop_scan
    scan_point                  => scan_point
    get_objective_scanner_pos
    set_objective_scanner_pos
    get_probe_scanner_pos
    set_probe_scanner_pos

    """ 

    # Interface methods
    """
    
    Device specific functions
    =========================
    reset_device()      => ???

    get_current_device_state()
    get_current_device_config()     => internally: _set_current_device_config()
    get_available_scan_modes()
    get_parameter_for_modes()
    get_available_scan_style()


    Objective scanner Movement functions
    ==============================
    get_objective_pos
    get_objective_target_pos
    set_objective_pos_abs (vel=None, time=None)  if velocity is given, time will be ignored
    set_objective_pos_rel (vel=None, time=None)  if velocity is given, time will be ignored


    Probe scanner Movement functions
    ==============================
    get_probe_pos
    get_probe_target_pos
    set_probe_pos_abs (vel=None, time=None)  if velocity is given, time will be ignored
    set_probe_pos_rel (vel=None, time=None)  if velocity is given, time will be ignored

    Scan Functions
    ==============

    configure_scan_device (mode, params, scan_style) 
        [scan_style can be included in the params dict]
        if configuration is not possible or failed, abort further scan in the logic
        return (True, False=Not successful, -1= invalid/missing parameter)

        mode:
            OBJECTIVE_XY 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode:
            OBJECTIVE_XZ 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode:
            OBJECTIVE_YZ 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN
                
        mode:
            PROBE_CONTACT 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode: 
            PROBE_CONSTANT_HEIGHT
        params:
            line_points
            meas_params
            lift_height
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode: 
            PROBE_DUAL_PASS
        params:
            line_points
            meas_params_pass1
            meas_params_pass2
            lift_height
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode: 
            PROBE_Z_SWEEP
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

    get_current_configuration()

    configure_scan_line(corr0_start, corr0_stop, corr1_start, corr1_stop, # not used in case of z sweep
                        time_forward, time_back)
        will configure a line depending on the selected mode


        (required configure_scan_device be done before the scan)
        allocate the array where data will be saved to
        
    scan_line (required configure_scan_line to be called prior)
        will execute a scan line depending on the selected mode

    get_measurement (required configure_scan_line to be called prior)
        => blocking method, either with timeout or stoppable via stop measurement

    scan_point (blocking method, required configure_scan_line to be called prior)
    
    stop_measurement()     => hardcore stop mechanism
        => if PROBE_CONSTANT_HEIGHT: land_probe
        => if PROBE_DUAL_PASS: land_probe
        => if PROBE_Z_SWEEP: BreakProbeSweepZ

        - land probe after each scan! land_probe(fast=False)
        => configuration will be set to UNCONFIGURED

    calibrate_constant_height( array with (x,y) points, safety_lift, ) 
        => return calibration points array of (x,y,z)

    get_constant_height_calibration()
        => return calibration points array of (x,y,z)


    Probe lifting functions
    ========================

    lift_probe(rel_value)
    get_lifted_value()  
        return absolute lifted value
    is_probe_landed() 
        return True/False
    land_probe(fast=False)

    """

    # SPM CONSTANTS/LIMITS      => get_spm_
    """
    DATA_CHANNEL_NAMES_LIST      => all available 
    DATA_CHANNEL_UNITS_LIST

    # ranges for objective scanner
    OBJECTIVE_SCANNER_X_MIN
    OBJECTIVE_SCANNER_X_MAX
    OBJECTIVE_SCANNER_Y_MIN
    OBJECTIVE_SCANNER_Y_MAX
    OBJECTIVE_SCANNER_Z_MIN
    OBJECTIVE_SCANNER_Z_MAX

    # ranges for probe scanner
    PROBE_SCANNER_X_MIN
    PROBE_SCANNER_X_MAX
    PROBE_SCANNER_Y_MIN
    PROBE_SCANNER_Y_MAX
    PROBE_SCANNER_Z_MIN
    PROBE_SCANNER_Z_MAX
    """

    #2D_SCAN_MODE          => get_available_scan_modes()
    """
    OBJECTIVE_XY
    OBJECTIVE_XZ
    OBJECTIVE_YZ
    PROBE_CONTACT
    PROBE_CONSTANT_HEIGHT
    PROBE_DUAL_PASS
    PROBE_Z_SWEEP
    """

    #SCAN_STYLE         => get_available_scan_style()
    """
    LINE_SCAN
    POINT_SCAN
    """


    #SPM_DEVICE_STATE   => get_current_device_state() will return one of those
    """
    DISCONNECTED
    IDLE                
    OBJECTIVE_MOVING
    OBJECTIVE_SCANNING
    PROBE_MOVING
    PROBE_SCANNING
    PROBE_LIFTED
    PROBE_SCANNING_LIFTED
    """



    #SPM SETTINGS       => all these settings are attributed to a function and 
    #                      not set individually!!
    """
    library version
    spm version
    idle_move_speed_during_scan_objective   => logic attribute, 
    scan_speed_objective                    => logic attribute

    idle_move_speed_during_scan_probe       => logic attribute
    scan_speed_probe                        => logic attribute

    idle_move_speed_position                => logic attribute

    lift_speed                              => logic attribute
    """
    # -----------------------------------------------------------------
    # Start of dummy methods
    # -----------------------------------------------------------------

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

        sc.scanner_mode_params = { ScannerMode.OBJECTIVE_XY:          { 'line_points': 100 },
                                   ScannerMode.OBJECTIVE_XZ:          { 'line_points': 100 },
                                   ScannerMode.OBJECTIVE_YZ:          { 'line_points': 100 },
                                   ScannerMode.PROBE_CONTACT:         { 'line_points': 100 },
                                   ScannerMode.PROBE_CONSTANT_HEIGHT: {},   # to be defined when implemented
                                   ScannerMode.PROBE_DUAL_PASS:       {},   # to be defined when implemented
                                   ScannerMode.PROBE_Z_SWEEP:         {}    # to be defined when implemented
                                 }       

        sc.scanner_mode_params_defaults = {
                                   ScannerMode.OBJECTIVE_XY:          { 'meas_params': []},
                                   ScannerMode.OBJECTIVE_XZ:          { 'meas_params': []},
                                   ScannerMode.OBJECTIVE_YZ:          { 'meas_params': []},
                                   ScannerMode.PROBE_CONTACT:         {},
                                   ScannerMode.PROBE_CONSTANT_HEIGHT: {},   # to be defined when implemented
                                   ScannerMode.PROBE_DUAL_PASS:       {},   # to be defined when implemented
                                   ScannerMode.PROBE_Z_SWEEP:         {}    # to be defined when implemented

                                }  # to be defined


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


    def check_interface_version(self, pause=None):
        """ Determines interface version from hardware interface 

        @param: int pause:  time to wait before posing hardware questions
                            (to avoid startup interference)

        @return: bool isCompatible:  a boolean flag indicating if the SPM client 
                            and server are compatible
        """
        return True 

    # Configure methods
    # =========================
    def configure_scanner(self, mode, params, scan_style=ScanStyle.LINE):
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
            of type ScannerMode, ScanStyle

        @return tuple: (mode, scan_style)
        """
        pass

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
        pass
        
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
        pass

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
        pass

    def get_measurements(self, reshape=True):
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
        pass
    
    def stop_measurement(self):
        """ Immediately terminate the measurment
        Hardcore stop mechanism, which proposes the following actions:
        - if PROBE_CONSTANT_HEIGHT: land_probe
        - if PROBE_DUAL_PASS: land_probe
        - if PROBE_Z_SWEEP: BreakProbeSweepZ
        @params: None

        @return: None
        """    
        pass

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
        pass

    def set_current_device_state(self, state):
        """ Sets the current device state 
        @param: ScannerState: set the current state of the device

        @return bool: status variable with: 
                        False (=0) call failed
                        True (=1) call successful
        """      
        pass

    def get_current_device_config(self):     
        """ Gets the current device state 

        @return: ScannerState: current device state
        """      
        pass

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

        @return: value or dict:  if 'query' is supplied, then specific setting is return
                otherwise, the entire dictionary is returned
        """      
        pass 

    def get_scanner_constraints(self):
        """ Returns the current scanner contraints

        @return dict: scanner contraints as defined for the device
        """
        return copy.copy(self._SCANNER_CONSTRAINTS)

    def get_available_scan_modes(self):
        """ Gets the available scan modes for the device 

        @return: list: available scan modes of the device, as [ScannerMode ...] 
        """      
        pass

    def get_parameters_for_mode(self, mode):
        """ Gets the parameters required for the mode
        Returns the scanner_constraints.scanner_mode_params for given mode

        @param: ScannerMode mode: mode to obtain parameters for (required parameters)
        
        @return: parameters for mode, from scanner_constraints
        """
        pass
    
    def get_available_scan_style(self):
        """ Gets the available scan styles for the device 
        Currently, this is only 2 modes: [ScanStyle.LINE, ScanStyle.POINT]

        @return: list: available scan styles of the device, as [ScanStyle ...] 
        """      
        pass

    def get_available_measurement_params(self):
        """  Gets the available measurement parameters (names) 
        obtains the dictionary of aviable measurement params 
        This is device specific, but is an implemenation of the 
        ScannerMeasurements class

        @return: scanner_measurements class implementation 
        """
        sm = self._SCANNER_MEASUREMENTS
        return copy.copy(sm.scanner_measurements)

    def get_available_measurement_axes(self,axes_name):
        """  Gets the available measurement axis of the device
        obtains the dictionary of aviable measurement axes given the name 
        This is device specific, but usually contains the avaialbe axes of 
        the sample scanner and objective scanner

        @return: (list) scanner_axes
        """
        pass

    def get_available_measurement_methods(self):
        """  Gets the available measurement modes of the device
        obtains the dictionary of aviable measurement methods
        This is device specific, but is an implemenation of the 
        ScannerMeasurements class

        @return: scanner_measurements class implementation 
        """
        pass


    #Objective scanner Axis/Movement functions
    #==============================

    def get_objective_scan_range(self, axis_label_list=['X2','Y2','Z2']):
        """ Get the objective scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return dict: objective scanner range dict with requested entries in m 
                      (SI units).
        """
        pass

    def get_objective_pos(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner position. 

        @param str axis_label_list: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """

        sc_pos = {'X2': 0.0, 'Y2': 0.0, 'Z2': 0.0}  # objective scanner pos
 
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
        pass

    def set_objective_pos_abs(self, axis_label_dict, move_time=0.1):
        """ Set the objective scanner target position. (absolute coordinates) 
        Returns the potential position of the scanner objective (understood to be the next point)

        @param str axis_label_list: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """
        
        # if velocity is given, time will be ignored
        pass

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
        pass


    # Probe scanner Axis/Movement functions
    # ==============================

    def get_sample_scan_range(self, axis_label_list=['X1','Y1','Z1']):
        """ Get the sample scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'x', 'Y', 'y', 'Z', 'z'] 
                                     or postfixed with a '1':
                                        ['X1', 'x1', 'Y1', 'y1', 'Z1', 'z1'] 

        @return dict: sample scanner range dict with requested entries in m 
                      (SI units).
        """
        pass

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

        sc_pos = {'X1': 0.0, 'Y1': 0.0, 'Z1': 0.0} # sample scanner pos
        
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
        pass

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
        pass
    
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
        pass


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
        pass
