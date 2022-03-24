# -*- coding: utf-8 -*-
"""
SPM ASC500 implementation.

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
import time
import numpy as np
from qtpy import QtCore
from scipy.interpolate import interp1d
from hardware.spm.spm_library.ASC500_Python_Control.lib.asc500_device import Device

from interface.scanner_interface import ScannerInterface, ScannerMode, ScanStyle, \
                                        ScannerState, ScannerConstraints, ScannerMeasurements  
from core.configoption import ConfigOption

_binPath = 'C:\\qudi\\proteusq-modules\\hardware\\spm\\spm_library\\ASC500_Python_Control\\Installer\\ASC500CL-V2.7.13'
_dllPath = 'C:\\qudi\\proteusq-modules\\hardware\\spm\\spm_library\\ASC500_Python_Control\\64bit_lib\\ASC500CL-LIB-WIN64-V2.7.13\\daisybase\\lib\\'

class SPM_ASC500(Base, ScannerInterface):
    """SPM wrapper for the communication with the ASC500 module.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'smart_spm.SmartSPM'
        libpath: 'path/to/lib/folder'

    """

    _modclass = 'SPM_ASC500'
    _modtype = 'hardware'

    _SCANNER_CONSTRAINTS = ScannerConstraints()
    _SCANNER_MEASUREMENTS = ScannerMeasurements()

    sigCollectObjectiveCounts = QtCore.Signal()

    _sync_in_timeout = ConfigOption('sync_in_timeout', missing='warn', default=0)

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

        self._dev = Device(_binPath, _dllPath)

        self._dev.base.startServer()

        self._dev.base.setDataEnable(1)
        self._spm_curr_state = ScannerState.UNCONFIGURED

        self._objective_x_volt, self._objective_y_volt, self._objective_z_volt = 0.0, 0.0, 0.0
        # DO NOT CHANGE
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_RT'), 3e6, 0)
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_RT'), 3e6, 1)
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_RT'), 3e6, 2)
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_RT'), 3e6, 3)

        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_LT'), 7.5e6, 0)
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_LT'), 7.5e6, 1)
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_LT'), 7.5e6, 2)
        self._dev.base.setParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_LT'), 7.5e6, 3)

        self.slew_rates = {'X2':None, 'Y2':None, 'Z2':None}
        # self.set_obj_slew_rate({'Z2':1})

        self._create_scanner_contraints()
        self._create_scanner_measurements()
        self._trig = False
        self.objective_lock = False

        return

    def on_deactivate(self):
        """ Clean up and deactivate the spm module. """
        # self._dev.scanner.closeScanner()
        # self._dev.base.stopServer()
        self._spm_curr_state = ScannerState.DISCONNECTED
        
        return 
    
    def set_obj_slew_rate(self, axis_dict):
        '''
        Slew rate given as integers for the axis key. SPM takes rate in units of 466uV/s.
        '''
        axes = {'X2':0, 'Y2':1, 'Z2':2} # axes DAC number
        for key in axis_dict.keys():
            self._dev.base.setParameter(self._dev.base.getConst('ID_DAC_GEN_STEP'), axis_dict[key], axes[key])

            self.log.info(f'{key} slew rate set to {axis_dict[key]}*466 uV/s')
            self.slew_rates[key]  = axis_dict[key]

    def _create_scanner_contraints(self):

        sc = self._SCANNER_CONSTRAINTS

        sc.max_detectors = 1
        std_config = {
            ScannerMode.OBJECTIVE_XY:  { 'plane'       : 'X2Y2', 
                                         'scan_style'  : ScanStyle.LINE },

            ScannerMode.OBJECTIVE_XZ:  { 'plane'       : 'X2Z2', 
                                         'scan_style'  : ScanStyle.LINE },

            ScannerMode.OBJECTIVE_YZ:  { 'plane'       : 'Y2Z2', 
                                         'scan_style'  : ScanStyle.LINE },
            
            ScannerMode.OBJECTIVE_ZX:  { 'plane'       : 'Z2X2', 
                                         'scan_style'  : ScanStyle.LINE },                                         

            ScannerMode.PROBE_CONTACT: { 'plane'       : 'XY', 
                                         'scan_style'  : ScanStyle.LINE }}

        # current modes, as implemented.  Enable others when available
        sc.scanner_modes = [ ScannerMode.PROBE_CONTACT,
                             ScannerMode.OBJECTIVE_XY,
                              ScannerMode.OBJECTIVE_XZ,
                               ScannerMode.OBJECTIVE_YZ,
                               ScannerMode.OBJECTIVE_ZX
                             ]  

        sc.scanner_mode_states = { ScannerMode.PROBE_CONTACT: [ ScannerState.IDLE,
                                                                ScannerState.PROBE_MOVING,
                                                                ScannerState.PROBE_SCANNING,
                                                                ScannerState.PROBE_LIFTED],
                                    ScannerMode.OBJECTIVE_XY: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING],

                                   ScannerMode.OBJECTIVE_XZ: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING],
                                    
                                    ScannerMode.OBJECTIVE_ZX: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING],

                                   ScannerMode.OBJECTIVE_YZ: [  ScannerState.IDLE,
                                                                ScannerState.OBJECTIVE_MOVING,
                                                                ScannerState.OBJECTIVE_SCANNING]
                                }

        sc.scanner_styles = [ScanStyle.LINE] 

        sc.scanner_mode_params = {ScannerMode.PROBE_CONTACT:         { 'line_points': 100 },
                                    ScannerMode.OBJECTIVE_XY:          { 'line_points': 100 },
                                    ScannerMode.OBJECTIVE_XZ:          { 'line_points': 100 },
                                    ScannerMode.OBJECTIVE_ZX:          { 'line_points': 100 },
                                    ScannerMode.OBJECTIVE_YZ:          { 'line_points': 100 }
                                 }       

        sc.scanner_mode_params_defaults = {
                                   ScannerMode.PROBE_CONTACT:         { 'meas_params': []},
                                   ScannerMode.OBJECTIVE_XY:          { 'meas_params': []},
                                   ScannerMode.OBJECTIVE_XZ:          { 'meas_params': []},
                                   ScannerMode.OBJECTIVE_ZX:          { 'meas_params': []},
                                   ScannerMode.OBJECTIVE_YZ:          { 'meas_params': []}
                                }  # to be defined
        
    def _create_scanner_measurements(self):
        sm = self._SCANNER_MEASUREMENTS 

        sm.scanner_measurements = { 
            'Height(Dac)' : {'measured_units' : 'm',
                             'scale_fac': 1,    # multiplication factor to obtain SI units   
                             'si_units': 'm', 
                             'nice_name': 'Height'}

            # 'Mag' :         {'measured_units' : '350*uv', 
            #                  'scale_fac': 1/(1/305.2*1e6),    
            #                  'si_units': 'v', 
            #                  'nice_name': 'Tuning Fork HF1 Amplitude'},

            # 'Phase' :       {'measured_units' : '83.82*ndeg.', 
            #                  'scale_fac': 1/(1/83.82*1e9),    
            #                  'si_units': 'deg.', 
            #                  'nice_name': 'Tuning Fork Phase'},

            # 'Freq' :        {'measured_units' : 'mHz', 
            #                  'scale_fac': 1/(1e3),    
            #                  'si_units': 'Hz', 
            #                  'nice_name': 'Tuning Fork Frequency'},
            
            ,'counts' :        {'measured_units' : 'arb.', 
                             'scale_fac': 1,    
                             'si_units': 'arb.', 
                             'nice_name': 'Counts'}
        }

        sm.scanner_axes = { 'SAMPLE_AXES':     ['X', 'Y', 'Z'],
                            
                            'OBJECTIVE AXES': ['X2', 'Y2', 'Z2'],
                           

                            'VALID_AXES'     : ['X', 'Y', 'Z', 'X2', 'Y2', 'Z2']
        }

        sm.scanner_planes = ['XY', 'X2Y2', 'X2Z2', 'Y2Z2']

        sample_x_range, sample_y_range, sample_z_range = self._dev.limits.getXActualTravelLimit(), self._dev.limits.getYActualTravelLimit(), self._dev.limits.getZActualTravelLimit()
        objective_x_range, objective_y_range, objective_z_range = self._objective_piezo_act_range()

        sm.scanner_sensors = {  # name of sensor parameters 
                                'SENS_PARAMS_SAMPLE'    : ['SenX', 'SenY', 'SenZ'],   # AFM sensor parameters

                                # maximal range of the AFM scanner , X, Y, Z
                                'SAMPLE_SCANNER_RANGE' :    [[0, sample_x_range], [0, sample_y_range], [0, sample_z_range]],

                                'OBJECTIVE_SCANNER_RANGE' :    [[0, objective_x_range], [0, objective_y_range], [0, objective_z_range]]
                             }
        
    def _objective_piezo_act_range(self):
        dict = self.get_sample_scan_range()
        return dict['X'], dict['Y'], dict['Z']
    
    def _objective_piezo_act_pos(self):
        piezo_range = self._objective_piezo_act_range()
        u_lim = self._dev.base.getParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_CT'), 0)/1e6  
        obj_volt_range = np.array([0, u_lim])
        pos_interp_xy = interp1d(obj_volt_range, np.array([0.0 ,piezo_range[0]]), kind='linear')
        pos_interp_z = interp1d(obj_volt_range, np.array([0.0 ,piezo_range[2]]), kind='linear')

        def rounder(x):
            try:
                return np.round(x,-1*int(np.ceil(np.log10(x))-4)) * 1e-6
            except OverflowError:
                return np.round(x,0) * 1e-6
            
        self._objective_x_volt = rounder(self._dev.base.getParameter(self._dev.base.getConst('ID_DAC_VALUE'), 0) * 305.2)

        self._objective_y_volt = rounder(self._dev.base.getParameter(self._dev.base.getConst('ID_DAC_VALUE'), 1) * 305.2)

        self._objective_z_volt = rounder(self._dev.base.getParameter(self._dev.base.getConst('ID_DAC_VALUE'), 2) * 305.2)

        return float(pos_interp_xy(self._objective_x_volt)), float(pos_interp_xy(self._objective_y_volt)), float(pos_interp_z(self._objective_z_volt))

    def _objective_volt_for_pos(self, pos, xy):
        piezo_range = self._objective_piezo_act_range()
        u_lim = self._dev.base.getParameter(self._dev.base.getConst('ID_GENDAC_LIMIT_CT'), 0)/1e6  
        obj_volt_range = np.array([0, u_lim])
        pos_interp_xy = interp1d(np.array([0.0 ,piezo_range[0]]), obj_volt_range, kind='linear')
        pos_interp_z = interp1d(np.array([0.0 ,piezo_range[2]]), obj_volt_range, kind='linear')
        return pos_interp_xy(pos) if xy else pos_interp_z(pos)

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
        (self, xOffset, yOffset, pxSize, columns, lines, sampTime):
        """
        dev_state = self.get_current_device_state()
        self._spm_curr_mode = mode
        self._spm_curr_sstyle = scan_style
        #curr_mode, curr_params, curr_sstyle = self.get_current_device_config()

        # note that here, all methods configure the SPM for "TscanMode.LINE_SCAN"
        # since all measurements are gathered in a line format
        # however, the movement is determined by the ScanStyle, which determines
        # if a trigger signal will be produced for the recorder device 
        std_config = {
            ScannerMode.OBJECTIVE_XY:  { 'plane'       : 'X2Y2', 
                                         'scan_style'  : ScanStyle.LINE },

            ScannerMode.OBJECTIVE_XZ:  { 'plane'       : 'X2Z2', 
                                         'scan_style'  : ScanStyle.LINE },

            ScannerMode.OBJECTIVE_ZX:  { 'plane'       : 'Z2X2', 
                                         'scan_style'  : ScanStyle.LINE },                                         

            ScannerMode.OBJECTIVE_YZ:  { 'plane'       : 'Y2Z2', 
                                         'scan_style'  : ScanStyle.LINE },

            ScannerMode.PROBE_CONTACT: { 'plane'       : 'XY', 
                                         'scan_style'  : ScanStyle.LINE },

            # other configurations to be defined as they are implemented
        }

        if not ((dev_state == ScannerState.UNCONFIGURED) or (dev_state == ScannerState.IDLE)):
            self.log.error(f'SPM cannot be configured in the '
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
        params = { **params, **{k:sc_defaults[k] for k in sc_defaults.keys() - params.keys()}}
        # is_ok = self._check_params_for_mode(mode, params)
        # if not is_ok: 
        #     self.log.error(f'Parameters are not correct for mode "{ScannerMode.name(mode)}". '
        #                    f'Configuration stopped.')
        #     return -1
        
        ret_val = 1

        self._dev.scanner.resetScannerCoordSystem()
        self._dev.scanner.setOutputsActive()
        self._dev.scanner.setDataEnable(1)

        if mode == ScannerMode.UNCONFIGURED:
            return -1   # nothing to do, mode is unconfigured, so we shouldn't continue

        elif mode == ScannerMode.OBJECTIVE_XY:
            # Objective scanning returns no parameters
            self._spm_curr_state =  ScannerState.IDLE
            self._chn_no = 6 # counter channel

        elif mode == ScannerMode.OBJECTIVE_XZ:
            # Objective scanning returns no parameters
            self._spm_curr_state =  ScannerState.IDLE
            self._chn_no = 6 # counter channel

        elif mode == ScannerMode.OBJECTIVE_YZ:
            # Objective scanning returns no parameters
            self._spm_curr_state =  ScannerState.IDLE
            self._chn_no = 6 # counter channel
        
        elif mode == ScannerMode.OBJECTIVE_ZX:
            # Objective scanning returns no parameters
            self._spm_curr_state =  ScannerState.IDLE
            self._chn_no = 6 # counter channel

        elif mode == ScannerMode.PROBE_CONTACT:
            # Scanner library specific style is always "LINE_STYLE" 
            # both line-wise and point-wise scans configure a line;
            # For internal "line_style" scan definitions, the additional trigger signal 
            # is activated
            self._spm_curr_state =  ScannerState.IDLE
            self._chn_no = 2

        else:
            self.log.error(f'Error configure_scanner(): mode = "{ScannerMode.name(mode)}"'
                            ' has not been implemented yet')
            return -1

        self._line_points = params['line_points']
        self._spm_curr_sstyle = scan_style
        self._curr_meas_params = ['Height(Dac)']
    
        return ret_val, 0, self._curr_meas_params

    def get_current_configuration(self):
        """ Returns the current scanner configuration
            of type ScannerMode, ScanStyle

        @return tuple: (mode, scan_style)
        """
        if self._dev.scanner.getScannerState()==1:
            return (ScannerMode.PROBE_SCANNING, ScanStyle.LINE)
        else:
            return (ScannerMode.IDLE, ScanStyle.LINE)

    def configure_line(self, 
                       line_corr0_start, line_corr0_stop, 
                       line_corr1_start, line_corr1_stop, # not used in case of Z sweep
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
        if self._spm_curr_mode == ScannerMode.PROBE_CONTACT:
            scan_range = self.get_sample_scan_range(['X','Y'])
            axis_dict = {'X': line_corr0_stop, 'Y': line_corr1_stop}
            for i in scan_range:
                if axis_dict[i] > scan_range[i]:
                    self.log.warning(f'Sample scanner {i} to abs. position outside scan range: {axis_dict[i]*1e6:.3f} um')
                    self.overrange = True
                    return self.get_sample_pos(list(axis_dict.keys()))
            self.overrange = False

            px=int((abs(line_corr0_stop-line_corr0_start))*1e9)
            sT=time_forward/self._line_points
            self._dev.base.setParameter(self._dev.base.getConst('ID_SCAN_PSPEED'), px/time_back, 0)
            
            self._configureSamplePath(line_corr0_start, line_corr0_stop, 
                                    line_corr1_start, line_corr1_stop, self._line_points)
            self._polled_data = np.zeros(self._line_points)
            self._configurePathDataBuffering(sampTime=sT)

            if self._spm_curr_sstyle==ScanStyle.POINT:
                self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_PATHCTRL'), -1, 0 ) # -1 is grid mode
                self._dev.scanner.setRelativeOrigin(self.end_coords) # set after path or it will attempt going to origin for some reason
                self._spm_curr_state =  ScannerState.PROBE_SCANNING

            return
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_XY:
            self.fast_axis = 0
            scan_range = self.get_objective_scan_range(['X2','Y2'])
            axis_dict = {'X2': line_corr0_stop, 'Y2': line_corr1_stop}
            for i in scan_range:
                if axis_dict[i] > scan_range[i]:
                    self.log.warning(f'Objective scanner {i} to abs. position outside scan range: {axis_dict[i]*1e6:.3f} um')
                    self.overrange = True
                    return self.get_objective_pos(list(axis_dict.keys()))
            self.overrange = False
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_XZ:
            self.fast_axis = 0
            scan_range = self.get_objective_scan_range(['X2','Z2'])
            axis_dict = {'X2': line_corr0_stop, 'Z2': line_corr1_stop}
            for i in scan_range:
                if axis_dict[i] > scan_range[i]:
                    self.log.warning(f'Objective scanner {i} to abs. position outside scan range: {axis_dict[i]*1e6:.3f} um')
                    self.overrange = True
                    return self.get_objective_pos(list(axis_dict.keys()))
            self.overrange = False
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_ZX:
            self.fast_axis = 2
            scan_range = self.get_objective_scan_range(['Z2','X2'])
            axis_dict = {'Z2': line_corr0_stop, 'X2': line_corr1_stop}
            for i in scan_range:
                if axis_dict[i] > scan_range[i]:
                    self.log.warning(f'Objective scanner {i} to abs. position outside scan range: {axis_dict[i]*1e6:.3f} um')
                    self.overrange = True
                    return self.get_objective_pos(list(axis_dict.keys()))
            self.overrange = False
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_YZ:
            self.fast_axis = 1
            scan_range = self.get_objective_scan_range(['Y2','Z2'])
            axis_dict = {'Y2': line_corr0_stop, 'Z2': line_corr1_stop}
            for i in scan_range:
                if axis_dict[i] > scan_range[i]:
                    self.log.warning(f'Objective scanner {i} to abs. position outside scan range: {axis_dict[i]*1e6:.3f} um')
                    self.overrange = True
                    return self.get_objective_pos(list(axis_dict.keys()))
            self.overrange = False
        self.idle_time = time_back
        sT=time_forward/self._line_points
        self._create_objective_line(xOffset=line_corr0_start, yOffset=line_corr1_start, pxSize=abs(line_corr0_stop-line_corr0_start)/self._line_points, columns=self._line_points)
        self._polled_data = np.zeros(self._line_points)
        self._configurePathDataBuffering(sampTime=sT)
    
    def set_ext_trigger(self, trig=False):
        self._trig = trig
    
    def _configureSamplePath(self, line_corr0_start, line_corr0_stop, line_corr1_start, line_corr1_stop, line_points):
        self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_PATHPREP'), 1, 0)
        self._dev.base.setParameter(self._dev.base.getConst('ID_EXTTRG_TIMEOUT'), self._sync_in_timeout, 0) # 0ms timeout - will wait until SYNC IN is received
        self._dev.base.setParameter(self._dev.base.getConst('ID_EXTTRG_HS'), 1, 0) # enable trigger
        self._dev.base.setParameter(self._dev.base.getConst('ID_EXTTRG_EDGE'), 0, 0) # 0 is rising edge
        # set number of xy grid points
        self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_GRIDP_X'), line_points, 0)
        self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_GRIDP_Y'), 1, 0)
        # if going to use grid mode, i.e, ('ID_SPEC_PATHCTRL'), -1, 0, then the GUI_X/Y points of index 0,1,2,3 are the BL,BR,TL,TR coordinates of a parallelogram - BL is start and TR is end
        # coords = [BL,BR,TL,TR] 

        self._coords = [[line_corr0_start,line_corr1_start],[line_corr0_stop,line_corr1_stop],[line_corr0_start,line_corr1_start],[line_corr0_stop,line_corr1_stop]]
        
        self._dev.scanner.setNumberOfColumns(1)
        self._dev.scanner.setNumberOfLines(1)
        self._dev.scanner.setPixelSize(1e-9)
        self._dev.base.setParameter(self._dev.base.getConst('ID_SCAN_ROTATION'), 0, 0)
        
        self.end_coords = [line_corr0_stop,line_corr1_stop]
        
        for index, val in enumerate(self._coords):
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_GUI_X'), int(val[0]/10e-12), index)  # start point is current position
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_GUI_Y'), int(val[1]/10e-12), index)  # start point is current position

        # define number path actions at a point ('ID_PATH_ACTION'), no. of actions, 0 
        if self._spm_curr_sstyle == ScanStyle.LINE:
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 2 if self._trig else 1, 0)
            # define which actions specifically ('ID_PATH_ACTION'), 0=manual handshake/2=Spec 1 dummy engine, 1=as the first action if no. of actions>=1 
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 2, 1)
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 4, 2)
        else:
            # If the scan mode is ESR then one needs to scan point by point mode. This would be non blocking between each point and therefore the manual
            # handshake makes sure the tip waits at the next point until logic is ready to proceed
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 3, 0)
            # define which actions specifically ('ID_PATH_ACTION'), 0=manual handshake/2=Spec 1 dummy engine, 1=as the first action if no. of actions>=1 
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 0, 1)
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 2, 2)
            self._dev.base.setParameter(self._dev.base.getConst('ID_PATH_ACTION'), 4, 3)
    
    def _create_objective_line(self, xOffset, yOffset, pxSize, columns):
        self.objective_scan_line = {}
        if self._spm_curr_mode == ScannerMode.OBJECTIVE_XY:
            self.objective_scan_line['X2'] = np.linspace(xOffset, xOffset + pxSize*columns, columns)
            self.objective_scan_line['Y2'] = np.ones(columns)*yOffset
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_XZ:
            self.objective_scan_line['X2'] = np.linspace(xOffset, xOffset + pxSize*columns, columns)
            self.objective_scan_line['Z2'] = np.ones(columns)*yOffset
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_ZX:
            self.objective_scan_line['Z2'] = np.linspace(xOffset, xOffset + pxSize*columns, columns)
            self.objective_scan_line['X2'] = np.ones(columns)*yOffset
        
        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_YZ:
            self.objective_scan_line['Y2'] = np.linspace(xOffset, xOffset + pxSize*columns, columns)
            self.objective_scan_line['Z2'] = np.ones(columns)*yOffset

    def scan_line(self, int_time=0.05): 
        """Execute a scan line measurement. 

        @param float int_time: integration time in s while staying on one point.
                               this setting is only valid for point-scan mode 
                               and will be ignored for a line-scan mode.  
        
        Every scan procedure starts with setup_spm method. Then
        setup_scan_line follows (first time and then next time current 
        scan line was completed)

        @return int: status variable with: 0 = call failed, 1 = call successful
        """
        if self.overrange:
            return 0

        if self._spm_curr_mode == ScannerMode.PROBE_CONTACT:
            while True:
                if self._dev.base.getParameter(self._dev.base.getConst('ID_PATH_RUNNING'), 0)==1 or self._dev.base.getParameter(self._dev.base.getConst('ID_SCAN_STATUS'), 0)==2:
                    pass
                else:
                    break
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_PATHCTRL'), -1, 0 ) # -1 is grid mode
             # set after path or it will attempt going to origin for some reason
            self._spm_curr_state =  ScannerState.PROBE_SCANNING
            self._poll_path_data()
            self._dev.scanner.setRelativeOrigin(self.end_coords)

        elif self._spm_curr_mode == ScannerMode.OBJECTIVE_XY or self._spm_curr_mode == ScannerMode.OBJECTIVE_XZ or self._spm_curr_mode == ScannerMode.OBJECTIVE_YZ or self._spm_curr_mode == ScannerMode.OBJECTIVE_ZX:
            self._spm_curr_state =  ScannerState.OBJECTIVE_SCANNING
            self._scan_objective()
        
        return 1
        
    def _scan_objective(self):
        axis_dict = {}
        keys = list(self.objective_scan_line.keys())
        axis_dict[keys[0]] = self.objective_scan_line[keys[0]][0]
        axis_dict[keys[1]] = self.objective_scan_line[keys[1]][0]
        self.set_objective_pos_abs(axis_dict, self.idle_time)
        self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_STATUS'), 1, self.spec_engine_dummy)
        self._poll_path_data()

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
        if self.overrange:
            return 0

        if self._spm_curr_mode == ScannerMode.PROBE_CONTACT:
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_PATHPROCEED') ,1 ,0)
            while True:
                if self._dev.base.getParameter(self._dev.base.getConst('ID_PATH_RUNNING'), 0)==1 or self._dev.base.getParameter(self._dev.base.getConst('ID_SCAN_STATUS'), 0)==2:
                    pass
                else:
                    break
            
            self._poll_point_data()
            return self._polled_data
            
        return 0
    
    def _configurePathDataBuffering(self, sampTime):
        # The channel configuration and GUI element showing the input for the Specs have little do with each other. Multiple channels can be triggered by a spec. If the GUI channel is the same 
        # as the channel chosen for the custom spec then the GUI elements also update. Things will always work and data is buffered, but the nice spec GUI may not update if the channel is not the same there.
        # this is simply by order in which in it is added (stupid people attocube outsourced to).

        if self._spm_curr_mode == ScannerMode.PROBE_CONTACT:
            self.spec_engine_dummy = 1
            self.spec_count = 469 # this value works because it is not changed after spec engine starts - necessary for correct buffer size
            
            self._dev.base.configureChannel(self._chn_no, # any Number between 0 and 13.
                                    self._dev.base.getConst(f'CHANCONN_SPEC_{self.spec_engine_dummy}'), # How you want to the data to be triggered - CHANCONN_PERMANENT is time triggered data
                                    self._dev.base.getConst('CHANADC_AFMAMPL'), # The ADC channel you want to get the data from
                                    1, # 0/1 -  if you want to switch on averaging
                                    sampTime) # Scanner sample time [s]

            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_DAC_NO'), 3, self.spec_engine_dummy) # index 1 is spec engine 2. Spec engine 0 is Z-Spec. 4 is the 4th DAC which is not used for objective scanning
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_START_DISP'), 0, self.spec_engine_dummy)
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_END_DISP'), 1000, self.spec_engine_dummy)
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_COUNT'), self.spec_count, self.spec_engine_dummy)

            self.spec_count = self._dev.base.getParameter(self._dev.base.getConst('ID_SPEC_COUNT'), self.spec_engine_dummy)
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_MSPOINTS'), int((sampTime/2.5e-6)/self.spec_count), self.spec_engine_dummy)
            self._dev.base.configureDataBuffering(self._chn_no, self.spec_count) # chNo = same as above; bufSize = Buffersize.
        else:
            self.spec_engine_dummy = 2
            self.spec_count = self._line_points
            self._dev.base.setParameter(self._dev.base.getConst('ID_CNT_EXP_TIME'),int(sampTime/2.5e-6), 0)
            
            self._dev.base.configureChannel(self._chn_no, # any Number between 0 and 13.
                                    self._dev.base.getConst(f'CHANCONN_SPEC_{self.spec_engine_dummy}'), # How you want to the data to be triggered - CHANCONN_PERMANENT is time triggered data
                                    23, # The counter  ADC channel
                                    1, # 0/1 -  if you want to switch on averaging
                                    sampTime) # Scanner sample time [s]
            
            start_cart = self.objective_scan_line[{0:'X2', 1:'Y2', 2:'Z2'}[self.fast_axis]][0]
            stop_cart = self.objective_scan_line[{0:'X2', 1:'Y2', 2:'Z2'}[self.fast_axis]][-1]
            start = self._objective_volt_for_pos(start_cart, True if not self.fast_axis==2 else False)
            stop = self._objective_volt_for_pos(stop_cart, True if not self.fast_axis==2 else False)
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_DAC_NO'), self.fast_axis, self.spec_engine_dummy) # index 1 is spec engine 1. Spec engine 0 is Z-Spec. 4 is the 4th DAC which is not used for objective scanning
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_START_DISP'), start*1e3, self.spec_engine_dummy)
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_END_DISP'), stop*1e3, self.spec_engine_dummy)
            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_COUNT'), self.spec_count, self.spec_engine_dummy)

            self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_MSPOINTS'), int(sampTime/2.5e-6), self.spec_engine_dummy)
            self._dev.base.configureDataBuffering(self._chn_no, self.spec_count) # chNo = same as above; bufSize = Buffersize.
        
    def _find_spec_count(self, start_cart, stop_cart, m, xy=True):
        spec_engine = 2
        n = 3e6//(305.2*m)
        spec_count0 = int(np.round(3/(305.2e-6*n)))
        success = False
        for i in range(100):
            k = 1
            for j in range(2):
                sc0 = spec_count0+i*(k)
                k*=-1
                start = self._objective_volt_for_pos(start_cart, xy)
                stop = self._objective_volt_for_pos(stop_cart, xy)
                self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_START_DISP'), start*1e3, spec_engine)
                self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_END_DISP'), stop*1e3, spec_engine)
                self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_COUNT'), sc0, spec_engine)
                self._dev.base.setParameter(self._dev.base.getConst('ID_SPEC_STATUS'), 0, spec_engine)
                time.sleep(0.1)
                sc = self._dev.base.getParameter(self._dev.base.getConst('ID_SPEC_COUNT'), spec_engine)
                if sc==sc0:
                    return sc
        return -1

    def _poll_path_data(self):
        '''
        Polls the buffer after the spec engine is triggered at each point. _grabASCData is a blocking statement that only passes after buffer is full.
        To implement Dual Pass the Z position will be set at every point inside the for loop
        '''
        n = self._line_points if self._spm_curr_mode == ScannerMode.PROBE_CONTACT else 1
        
        for i in range(n):
            self.spec_count = self._dev.base.getParameter(self._dev.base.getConst('ID_SPEC_COUNT'), self.spec_engine_dummy)
            data = self._grabASCData(self.spec_count)
            if self._spm_curr_mode == ScannerMode.PROBE_CONTACT:
                self._polled_data[i] = np.mean(data)
            else:
                self._polled_data = data

    def _poll_point_data(self):
        '''
        Polls the buffer after the spec engine is triggered at each point. _grabASCData is a blocking statement that only passes after buffer is full.
        To implement Dual Pass the Z position will be set at every point inside the for loop
        '''

        self.spec_count = self._dev.base.getParameter(self._dev.base.getConst('ID_SPEC_COUNT'), self.spec_engine_dummy)
        data = self._grabASCData(self.spec_count)
        self._polled_data = np.mean(data)

    def _grabASCData(self, bufSize=200):
        while True:
            # Wait until buffer is full
            if self._dev.base.waitForFullBuffer(self._chn_no) != 0:
                    break
        try:
            buffer = self._dev.base.getDataBuffer(self._chn_no, 1, bufSize)
        except:
            self.log.error('Buffer fail')
            return 0
        values = buffer[3][:]
        meta = buffer[4]
        phys_vals = []
        # TODO do all unit conversions, maybe post polling
        for val in values:
            phys_vals.append(self._dev.base.convValue2Phys(meta, val))
        return np.array(phys_vals)

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

        phys_vals = np.array([self._polled_data])
        return phys_vals
    
    def check_spm_scan_params_by_plane(self, plane, coord0_start, coord0_stop, coord1_start,coord1_stop):
        return -1 if coord0_start>coord0_stop or coord1_start>coord1_stop else 1

    def finish_scan(self):
        """ Request completion of the current scan line 
        It is correct (but not abs necessary) to end each scan 
        process by this method. There is no problem for 'Point' scan, 
        performed with 'scan_point', to stop it at any moment. But
        'Line' scan will stop after a line was finished, otherwise 
        your software may hang until scan line is complete.

        @return int: status variable with: 0 = call failed, 1 = call successfull
        """
        self._dev.scanner.sendScannerCommand(self._dev.base.getConst('SCANRUN_OFF'))
        self._spm_curr_state =  ScannerState.IDLE
        return 1
    
    def stop_measurement(self):
        """ Immediately terminate the measurment
        Hardcore stop mechanism, which proposes the following actions:
        - if PROBE_CONSTANT_HEIGHT: land_probe
        - if PROBE_DUAL_PASS: land_probe
        - if PROBE_Z_SWEEP: BreakProbeSweepZ
        @params: None

        @return: None
        """    
        self._dev.zcontrol.setPositionZ(0)
        # self._dev.scanner.closeScanner()

    def calibrate_constant_height(self, calib_points, safety_lift):
        """ Calibrate constant height

        Performs a lift-move-land height mode calibration for the sample
        at the defined calib_points locations.  During the move, the
        probe is lifted to a safe height for travel ('safety_lift')
        
        @param: array calib_points: sample coordinates X & Y of where 
                to obtain the height; e.g. [ [x0, y0], [X, Y], ... [xn, yn]]
        @param: float safety_lift: height (m) to lift the probe during traversal
                (+ values up...increasing the distance between probe & sample)
        
        @return: array calibrate_points: returns measured heights with the 
                 the original coordinates:  [[x0, y0, z0], [X, Y, Z], ... [xn, yn, zn]] 
        """
        pass

    def get_constant_height_calibration(self):
        """ Returns the calibration points, as gathered by the calibrate_constant_height() mode

        @return: array calibrate_points: returns measured heights with the 
                 the original coordinates:  [[x0, y0, z0], [X, Y, Z], ... [xn, yn, zn]] 
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
        self._dev.resetServer()

    def get_current_device_state(self):
        """ Get the current device state 

        @return: ScannerState.(state) 
                 returns the state of the device, as allowed for the mode  
        """  
        return self._spm_curr_state

    def set_current_device_state(self, state):
        """ Sets the current device state 
        @param: ScannerState: set the current state of the device

        @return bool: status variable with: 
                        False (=0) call failed
                        True (=1) call successful
        """      
        self._spm_curr_state = state
        return True

    def get_current_device_config(self):     
        """ Gets the current device state 

        @return: ScannerState: current device state
        """      
        return self.get_current_device_state()

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
        return {'Device':'ASC500'} 

    def get_scanner_constraints(self):
        """ Returns the current scanner contraints

        @return dict: scanner contraints as defined for the device
        """
        return copy.copy(self._SCANNER_CONSTRAINTS)

    def get_available_scan_modes(self):
        """ Gets the available scan modes for the device 

        @return: list: available scan modes of the device, as [ScannerMode ...] 
        """      
        return self._curr_scanner_constraints.scanner_modes

    def get_parameters_for_mode(self, mode):
        """ Gets the parameters required for the mode
        Returns the scanner_constraints.scanner_mode_params for given mode

        @param: ScannerMode mode: mode to obtain parameters for (required parameters)
        
        @return: parameters for mode, from scanner_constraints
        """
        return self._curr_scanner_constraints.scanner_mode_params[mode] 
    
    def get_available_scan_style(self):
        """ Gets the available scan styles for the device 
        Currently, this is only 2 modes: [ScanStyle.LINE, ScanStyle.POINT]

        @return: list: available scan styles of the device, as [ScanStyle ...] 
        """      
        return self._curr_scanner_constraints.scanner_styles

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
        return self._curr_scanner_measurements.scanner_axes

    def get_available_measurement_methods(self):
        """  Gets the available measurement modes of the device
        obtains the dictionary of aviable measurement methods
        This is device specific, but is an implemenation of the 
        ScannerMeasurements class

        @return: scanner_measurements class implementation 
        """
        return self._curr_scanner_measurements


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
        piezo_range = self._objective_piezo_act_range()
        piezo_range_dict = {'X2': piezo_range[0], 'Y2': piezo_range[1], 'Z2': piezo_range[2]}
        ret_dict = {i : piezo_range_dict[i.upper()] for i in axis_label_list}
        return ret_dict

    def get_objective_pos(self, axis_label_list=['X2', 'Y2', 'Z2']):
        """ Get the objective scanner position. 

        @param str axis_label_list: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """
        x, y, z = self._objective_piezo_act_pos()
        sc_pos = {'X2': x, 'Y2': y, 'Z2': z}  # objective scanner pos
 
        return {i : sc_pos[i.upper()] for i in axis_label_list}


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
        return self.get_objective_pos(axis_label_list)

    def set_objective_pos_abs(self, axis_label_dict, move_time=0.1):
        """ Set the objective scanner target position. (absolute coordinates) 
        Returns the potential position of the scanner objective (understood to be the next point)

        @param str axis_label_dict: the axis label, either capitalized or lower 
                                    case, possible values: 
                                        ['X2', 'x2', 'Y2', 'y2', 'Z2', 'z2'] 

        @return float: normal output [0 .. AxisRange], though may fall outside 
                       this interval. Error: output <= -1000
                       sample scanner position in m (SI units).
        """
        
        # if velocity is given, time will be ignored
        if self.objective_lock:
            self.log.warning('Objective locked. Cannot move objective right until toggled.')
            return self.get_objective_pos(list(axis_label_dict.keys()))
        scan_range = self.get_objective_scan_range(list(axis_label_dict.keys()))
        for i in scan_range:
            if axis_label_dict[i] > scan_range[i]:
                self.log.warning(f'Objective scanner {i} to abs. position outside scan range: {axis_label_dict[i]*1e6:.3f} um')
                return self.get_objective_pos(list(axis_label_dict.keys()))
        volt = {i.upper() : self._objective_volt_for_pos(axis_label_dict[i], True if 'X' in i or 'Y' in i else False) for i in axis_label_dict}
        ret_list = []
        for i in volt:
            self._move_objective(i, volt[i], move_time)
        return self.get_objective_pos(list(axis_label_dict.keys()))
    
    def _move_objective(self, axis, volt, move_time):
        axes = {'X2':0, 'Y2':1, 'Z2':2}
        curr_volt = self._dev.base.getParameter(self._dev.base.getConst('ID_DAC_VALUE'), axes[axis])*305.2/1e6
        move_time=0.0
        if move_time==0:
            self._dev.base.setParameter(self._dev.base.getConst('ID_DAC_VALUE'), abs(int(volt/305.2*1e6)), axes[axis])
            while True:
                trans_volt = self._dev.base.getParameter(self._dev.base.getConst('ID_DAC_VALUE'), axes[axis])*305.2/1e6
                if np.isclose(trans_volt, volt, rtol=1e-02, atol=1e-02):
                    break
        else:
            for v in np.linspace(curr_volt, volt, 100):
                self._dev.base.setParameter(self._dev.base.getConst('ID_DAC_VALUE'), abs(int(v/305.2*1e6)), axes[axis])
                time.sleep(move_time/100)
        return self.get_objective_pos([axis])

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
                                position X=+10um, Y=+5um, Z=+2um
                                this is translated to absolute coordinates via
                                x_new_abs[i] = x_curr_abs[i] + x_rel[i]
                                (where X is a generic axis)

        @param float move_time: optional, time how fast the scanner is moving 
                                to desired position. Value must be within 
                                [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """
        for i in axis_rel_dict:
            axis_rel_dict[i] += self.get_objective_pos([i])[i]
        return self.set_objective_pos_abs(axis_rel_dict, move_time)


    # Probe scanner Axis/Movement functions
    # ==============================

    def get_sample_scan_range(self, axis_label_list=['X','Y','Z']):
        """ Get the sample scanner range for the provided axis label list. 

        @param list axis_label_list: the axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 
                                     or postfixed with a '1':
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 

        @return dict: sample scanner range dict with requested entries in m 
                      (SI units).
        """
        ret_dict = {'X': self._dev.base.getParameter(self._dev.base.getConst('ID_PIEZO_ACTRG_X'), 0)*1e-11, 
                'Y': self._dev.base.getParameter(self._dev.base.getConst('ID_PIEZO_ACTRG_Y'), 0)*1e-11, 
                'Z': self._dev.base.getParameter(self._dev.base.getConst('ID_REG_ZABS_LIMM'), 0)*1e-12}
        return {i : ret_dict[i[0]] for i in axis_label_list}

    def get_sample_pos(self, axis_label_list=['X', 'Y', 'Z']):
        """ Get the sample scanner position. 

        @param list axis_label_list: axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 
                                     or postfixed with a '1':
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 

        @return dict: sample scanner position dict in m (SI units). Normal 
                      output [0 .. AxisRange], though may fall outside this 
                      interval. Error: output <= -1000
        """

        sc_pos = {} # sample scanner pos
        sc_pos['X'], sc_pos['Y'], sc_pos['Z'] = self._dev.scanner.getPositionsXYZRel()
        
        return {i : sc_pos[i[0]] for i in axis_label_list}


    def get_sample_target_pos(self, axis_label_list=['X', 'Y', 'Z']):
        """ Get the set point of the axes locations (this is where it will move to) 

        @param list axis_label_list: axis label string list, entries either 
                                     capitalized or lower case, possible values: 
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 
                                     or postfixed with a '1':
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 

        @return dict: sample scanner position dict in m (SI units). Normal 
                      output [0 .. AxisRange], though may fall outside this 
                      interval. Error: output <= -1000
        """
        pos_dict = {'X': self._dev.base.getConst('ID_POSI_TARGET_X')*1e-11, 'Y':self._dev.base.getConst('ID_POSI_TARGET_Y')*1e-11, 'Z':0}
        return {i : pos_dict[i[0]] for i in axis_label_list}

    def set_sample_pos_abs(self, axis_dict, move_time=0.1):
        """ Set the sample scanner position.

        @param dict axis_dict: the axis label dict, entries either 
                                     capitalized or lower case, possible keys:
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z']
                                     or postfixed with a '1':
                                        ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 
                                    Values are the desired position for the 
                                    sample scanner in m. E.g an passed value may
                                    look like

                                        axis_label_dict = {'X':10e-6, 'Y':5e-6}

                                    to set the sample scanner to the absolute 
                                    position X=10um and Y=5um.

        @param float move_time: optional, time how fast the scanner is moving 
                                to desired position. Value must be within 
                                [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """
        scan_range = self.get_sample_scan_range(list(axis_dict.keys()))
        for i in scan_range:
            if axis_dict[i] > scan_range[i]:
                self.log.warning(f'Sample scanner {i} to abs. position outside scan range: {axis_dict[i]*1e6:.3f} um')
                return self.get_sample_pos(list(axis_dict.keys()))
        
        const_dict = {'X' : 'ID_POSI_TARGET_X', 'Y' : 'ID_POSI_TARGET_Y', 'Z' : 'ID_REG_SET_Z_M'}
        
        for i in axis_dict:
            if i[0].upper() == 'Z':
                axis_dict[i] *= 10 
            self._dev.base.setParameter(self._dev.base.getConst(const_dict[i[0].upper()]), axis_dict[i]*1e11, 0 )
        
        self._dev.base.setParameter(self._dev.base.getConst('ID_POSI_GOTO'), 1, 0)  
        return self.get_sample_pos(list(axis_dict.keys()))
    
    def set_sample_pos_rel(self, axis_rel_dict, move_time=0.1):
        """ Set the sample scanner position, relative to current position.

        @param dict axis_rel_dict:  the axis label dict, entries either 
                                capitalized or lower case, possible keys:
                                     ['X', 'X', 'Y', 'Y', 'Z', 'Z']
                                or postfixed with a '1':
                                   ['X', 'X', 'Y', 'Y', 'Z', 'Z'] 
                                Values are the desired position for the 
                                sample scanner in m. E.g an passed value may
                                look like

                                   axis_label_dict = {'X':10e-6, 'Y':5e-6}

                                to set the sample scanner to the relative  
                                    position X=+10um and Y=+5um.
                                this is translated to absolute coordinates via
                                x_new_abs[i] = x_curr_abs[i] + x_rel[i]
                                (where X is a generic axis)

        @param float move_time: optional, time how fast the scanner is moving 
                                to desired position. Value must be within 
                                [0, 20] seconds.
        
        @return float: the actual position set to the axis, or -1 if call failed.
        """
        curr_pos = self.get_sample_pos(list(axis_rel_dict.keys()))
        for i in axis_rel_dict:
            axis_rel_dict[i] += curr_pos[i]
        return self.set_sample_pos_abs(axis_rel_dict)

    # Probe lifting functions
    # ========================

    def lift_probe(self, rel_z):
        """ Lift the probe on the surface.

        @param float rel_z: lifts the probe by rel_z distance (m) (adds to previous lifts)  

        @return bool: Function returns True if method succesful, False if not
        """
        self._dev.base.setParameter(self._dev.base.getConst('ID_REG_LOOP_ON'), 0, 0)
        curr_z_pm = getParameter(self._dev.base.getConst('ID_REG_SET_Z_M'))
        rel_z_pm = rel_z*10e12
        move_rel_pm = int(curr_z_pm + rel_z_pm)
        self._dev.base.setParameter(self._dev.base.getConst('ID_REG_SET_Z_M'), move_rel_pm, 0)
        return self._dev.base.getParameter(self._dev.base.getConst('ID_REG_SET_Z_M'))==move_rel_pm
    
    def retract_probe(self):
        """ Retract sample or in this module language probe completely and switch off loop.
        @return bool: True if sample is retracted
        """
        self._dev.base.setParameter(self._dev.base.getConst('ID_REG_LOOP_ON'), 0, 0)
        self._dev.base.setParameter(self._dev.base.getConst('ID_REG_SET_Z_M'), 0, 0)
        return self._dev.base.getParameter(self._dev.base.getConst('ID_REG_SET_Z_M'))==0

    def get_lifted_value(self):
        """ Gets the absolute lift from the sample (sample land, Z=0)

        Note, this is not the same as the absolute Z position of the sample + lift
        Since the sample height is always assumed to be 0 (no Z dimension).  
        In reality, the sample has some thickness and the only way to measure Z 
        is to make a distance relative to this surface

        @return float: absolute lifted distance from sample (m)
        """
        return self._dev.base.getParameter(self._dev.base.getConst('ID_REG_SET_Z_M'))*10e-12

    def is_probe_landed(self): 
        """ Returns state of probe, if it is currently landed or lifted

        @return bool: True = probe is currently landed 
                      False = probe is in lifted mode
        """
        return self._dev.base.getParameter(self._dev.base.getConst('ID_REG_LOOP_ON'))==1

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
        landed = self.is_probe_landed()
        self._dev.base.setParameter(self._dev.base.getConst('ID_REG_LOOP_ON'), 1, 0)
        return not landed
