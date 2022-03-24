# -*- coding: utf-8 -*-
"""
This file contains the Qudi logic <####>.

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


#from hardware.microwaveQ.microwaveq import MicrowaveQ    # for debugging only
#from hardware.spm.spm_new import SmartSPM                # for debugging only
from interface.scanner_interface import ScanStyle, ScannerMode
from hardware.timetagger_counter import HWRecorderMode
from core.module import Connector, StatusVar
from core.configoption import ConfigOption
from logic.generic_logic import GenericLogic
from core.util import units
from core.util.mutex import Mutex
from scipy.linalg import lstsq
from math import log10, floor
from scipy.stats import norm
from collections import deque
import threading
import numpy as np
import os
import re
import time
import datetime
import matplotlib.pyplot as plt
import math
from . import gwyfile as gwy

from deprecation import deprecated

from qtpy import QtCore

class WorkerThread(QtCore.QRunnable):
    """ Create a simple Worker Thread class, with a similar usage to a python
    Thread object. This Runnable Thread object is intented to be run from a
    QThreadpool.

    @param obj_reference target: A reference to a method, which will be executed
                                 with the given arguments and keyword arguments.
                                 Note, if no target function or method is passed
                                 then nothing will be executed in the run
                                 routine. This will serve as a dummy thread.
    @param tuple args: Arguments to make available to the run code, should be
                       passed in the form of a tuple
    @param dict kwargs: Keywords arguments to make available to the run code
                        should be passed in the form of a dict
    @param str name: optional, give the thread a name to identify it.
    """

    def __init__(self, target=None, args=(), kwargs={}, name=''):
        super(WorkerThread, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.target = target
        self.args = args
        self.kwargs = kwargs

        if name == '':
            name = str(self.get_thread_obj_id())

        self.name = name
        self._is_running = False

    def get_thread_obj_id(self):
        """ Get the ID from the current thread object. """

        return id(self)

    @QtCore.Slot()
    def run(self):
        """ Initialise the runner function with passed self.args, self.kwargs."""

        if self.target is None:
            return

        self._is_running = True
        self.target(*self.args, **self.kwargs)
        self._is_running = False

    def is_running(self):
        return self._is_running

    def autoDelete(self):
        """ Delete the thread. """
        self._is_running = False
        return super(WorkerThread, self).autoDelete()

#TODO: reimplement the SetAutoDelete functionality
               
# ==========================================================================
#               Start Methods for the Internal status check 
class HealthChecker(object):
    """ Performs a periodic check on an op function,
        performed by a timer interval when the update status has fallen late

        The health check should be suspended in the time the optimizer is operating, 
        since if performed in this time, will cause a failed run.  However, we should 
        not let it sleep forever, as it may have also died during the optimization
    """
    _timer = None
    _armed = False
    _dead_time_mult = 10

    def __init__(self,log=None,**kwargs):
        # for now, do nothing.  This will be initizliaed later
        pass

    def setup(self,interval=10,         # interval in seconds at which to perform the check
              default_delta_t=10,       # default time to at first update 
              dead_time_mult=10,        # multiplier of time delta, after which the op function is tested 
              check_function=None,      # op function to check
              connect_start = [],       # signals to trigger start
              connect_update = [],      # signals to trigger update_status
              connect_stop = [],        # signals to trigger stop
              connect_opt_start = [],   # signals for start of optimizer
              connect_opt_stop = [],    # signals for stop of optimizer
              default_opt_skips = 10,   # number of times to skip check waiting for optimizer
              log=None,                 # pointer to logger object
            **kwargs):
        self.log = log
        self._timer = QtCore.QTimer()
        self._lock = Mutex()
        self._interval = interval   # currently, set timer for every 10 seconds
        self._last_time = None
        self._time_delta = None
        self._dead_time_mult = dead_time_mult
        self._default_delta_t = default_delta_t
        self._optimizer_skip_n = default_opt_skips
        self._optimizer_skip_i = 0    # burndown counter for optimizer skips
        self._armed = False

        # attaches to a 0 argument function, return value is irrelevant
        # failure to actuate indicates an ill condtion 
        self._check_function = check_function  

        # self signals
        self._timer.timeout.connect(self.perform_check)
        self._timer.setSingleShot(False)

        # start signals to connect to
        for sig in connect_start:
            sig.connect(self.start_timer)
        
        # update signals to connect to
        for sig in connect_update:
            sig.connect(self.update_status)
        
        # stop signals to connect to
        for sig in connect_stop:
            sig.connect(self.stop_timer)

        # start of the optimizer skip
        for sig in connect_opt_start:
            sig.connect(self.start_optimizer_skip)
        
        # stop of the optimizer skip
        for sig in connect_opt_stop:
            sig.connect(self.stop_optimizer_skip)


    def set_armed(self,arm=True):
        with self._lock:
            self._armed = arm 

    def start_timer(self,arm=False):
        """ Start the timer, if timer is running, it will be restarted. """
        self._timer.start(self._interval * 1000) # in ms
        self.set_armed(arm)

    def stop_timer(self):
        """ Stop the timer. """
        if self._timer is not None:
            self._timer.stop()
            self.set_armed(False)
            self.log.debug("HealthCheck: stopped timer")

    def start_optimizer_skip(self):
        """ The optimizer has been started """
        with self._lock:
            if not self._armed: return
            self._optimizer_skip_i = self._optimizer_skip_n
        self.log.debug("HeathChecker: recognized optimizer start")

    def stop_optimizer_skip(self):
        """ The optimizer has finished, no more skipping """
        with self._lock:
            if not self._armed: return
            self._optimizer_skip_i = 0
        self.update_status()
        self.log.debug("HeathChecker: recognized optimizer finish")

    def update_status(self,pos=None):
        """ updates the time since last writing of a measurement"""
        with self._lock:
            # not armed, but triggered
            if not self._armed: 
                return
            # end of line call, fired from self.sigQuantiLineFinished.emit()
            if pos is None:
                self._last_time = None
            
            # pixel call, fired from self.sigNewAFMPos.emit()
            if self._last_time is None:
                self._time_delta = self._default_delta_t 
                self._last_time = time.time() 
            else:
                now = time.time()
                self._time_delta = now - self._last_time  
                self._last_time = now
            
            #self.log.debug(f"HealthCheck:pos={pos}, last_time={self._last_time}, time_delta={self._time_delta}")

    def perform_check(self):
        """ request health status update """
        # not armed, but triggered
        if not self._armed: 
            return

        # check on the last time the health status was updated
        # if it was a really long time ago (10* last delta), then MQ could be dead
        docheck = False
        with self._lock:
            now = time.time()
            if self._optimizer_skip_i:
                # waiting for optimizer to finish
                self._optimizer_skip_i -= 1
                self.log.debug(f"HealthCheck_perform: skipped due to optimizer, remaining skips={self._optimizer_skip_i}")

            elif self._last_time is not None:
                # see if the time since last update was > dead_time_mult*last meas delta, 
                # if so, then perform MQ check
                delta_t = now - self._last_time 
                docheck = delta_t > max(self._dead_time_mult*self._time_delta, self._default_delta_t)
                self.log.debug(f"HealthCheck_perform: is healthy={not docheck}")
            else:
                delta_t = 0     # can't tell, since it hasn't been run yet

        if docheck:
            try:
                # this revives the MicrowaveQ if it has disconnected 
                status= self._check_function()
                if self.log: self.log.debug(f"HealthCheck reports laziness, op_function result={status}")
            except:
                # hopefully by asking its status, it will come back alive 
                if self.log: self.log.debug("HealthCheck reports possible death, attempting resurection")
 

class PulseSequence:
    '''
    A pulse sequence to be loaded that is made of PulseBlock instances. The pulse blocks can be repeated
    as well and multiple can be added.
    '''
    def __init__(self):
        self.pulse_dict = {0:[], 1:[], 2:[], 3:[], 4:[], 5:[], 6:[], 7:[]}

    def append(self, block_list):
        '''
        append a list of tuples of type: 
        [(PulseBlock_instance_1, n_repetitions), (PulseBlock_instance_2, n_repetitions)]
        '''
        for block, n in block_list:
            for i in range(n):
                for key in block.block_dict.keys():
                    self.pulse_dict[key].extend(block.block_dict[key])

    
class PulseBlock:
    '''
    Small repeating pulse blocks that can be appended to a PulseSequence instance
    '''
    def __init__(self):
        self.block_dict = {0:[], 1:[], 2:[], 3:[], 4:[], 5:[], 6:[], 7:[]}
    
    def append(self, init_length, channels, repetition):
        '''
        init_length in s; will be converted by sequence class to ns
        channels are digital channels of PS in swabian language
        '''
        tf = {True:1, False:0}
        for i in range(repetition):
            for chn in channels.keys():
                self.block_dict[chn].extend([(init_length/1e-9, tf[channels[chn]])])    


class AFMConfocalLogic(GenericLogic):
    """ Main AFM logic class providing advanced measurement control. """


    _modclass = 'AFMConfocalLogic'
    _modtype = 'logic'

    __version__ = '0.1.5' # version number 

    _meas_path = ConfigOption('meas_path', default='', missing='warn')

    # declare connectors. It is either a connector to be connected to another
    # logic or another hardware. Hence the interface variable will take either 
    # the name of the logic class (for logic connection) or the interface class
    # which is implemented in a hardware instrument (for a hardware connection)
    spm_device = Connector(interface='ScannerInterface') # hardware example
    savelogic = Connector(interface='SaveLogic')  # logic example
    counter_device = Connector(interface='SlowCounterInterface')
    counter_logic = Connector(interface='CounterLogic')
    fitlogic = Connector(interface='FitLogic')
    pulser = Connector(interface='PulserInterface')
    microwave = Connector(interface='MicrowaveInterface')

    # configuration parameters/options for the logic. In the config file you
    # have to specify the parameter, here: 'conf_1'
    # _conf_1 = ConfigOption('conf_1', missing='error')

    # status variables, save status of certain parameters if object is 
    # deactivated.
    # _count_length = StatusVar('count_length', 300)

    # for debugging purposes on the main thread, set to False
    _USE_THREADED = True
    #_USE_THREADED = False    # debug

    _stop_request = False
    _stop_request_all = False
    _health_check = HealthChecker() 

    # AFM signal 
    _meas_line_scan = []
    _spm_line_num = 0   # store here the current line number
    # total matrix containing all measurements of all parameters
    _meas_array_scan = []
    _meas_array_scan_fw = []    # forward
    _meas_array_scan_bw = []    # backward
    _afm_meas_duration = 0  # store here how long the measurement has taken
    _afm_meas_optimize_interval = 0 # in seconds

    # APD signal
    _apd_line_scan = []
    _apd_line_num = 0   # store here the current line number
    _apd_array_scan = []
    _apd_array_scan_fw = [] # forward
    _apd_array_scan_bw = [] # backward
    _scan_counter = 0
    _end_reached = False
    _obj_meas_duration = 0
    _opti_meas_duration = 0

    _curr_scan_params = []

    # pixel clock margin timing results (specified integration vs actual pixel clock time)
    _pixel_clock_tdiff = {}
    _pixel_clock_tdiff_data = {}

    # prepare measurement lines for the general measurement modes
    _obj_scan_line = np.zeros(10)   # scan line array for objective scanner
    _afm_scan_line = np.zeros(10)   # scan line array for objective scanner
    _qafm_scan_line = np.zeros(10)   # scan line array for combined afm + objective scanner
    _opti_scan_line = np.zeros(10)  # for optimizer

    #prepare the required arrays:
    # all of the following dicts should have the same unified structure
    _obj_scan_array = {} # all objective scan data are stored here
    _afm_scan_array = {}  # all pure afm data are stored here
    _qafm_scan_array = {} # all qafm data are stored here
    _opti_scan_array = {} # all optimizer data are stored here
    _esr_scan_array = {} # all the esr data from a scan are stored here

    #FIXME: Implement for this the methods:
    _esr_line_array = {} # the current esr scan and its matrix is stored here
    _saturation_array = {} # all saturation related data here

    # Single Iso-B settings
    _iso_b_single_mode = StatusVar(default=True)
    _freq1_iso_b_frequency = StatusVar(default=500e6)
    _freq2_iso_b_frequency = StatusVar(default=550e6)
    _iso_b_power = StatusVar(default=-30.0)
    _fwhm_iso_b_frequency = StatusVar(default=10e6)

    # color scale/color map definition
    _color_map = 'inferno'

    # acceptable object types for gwyddion
    _gwyobjecttypes = { 'imgobjects': ['qafm', 'obj', 'opti', 'afm'],
                        'graphobjects': ['esr']
                      }

    # Signals:
    # ========

    # Objective scanner
    # for the pure objective scanner, emitted will be the name of the scan, so 
    # either obj_xy, obj_xz or obj_yz
    sigObjScanInitialized = QtCore.Signal(str)
    sigObjLineScanFinished = QtCore.Signal(str)    
    sigObjScanFinished = QtCore.Signal()  

    # Qualitative Scan (Quenching Mode)
    sigQAFMScanInitialized = QtCore.Signal()
    sigQAFMLineScanFinished = QtCore.Signal()
    sigQAFMScanStarted = QtCore.Signal()
    sigQAFMScanFinished = QtCore.Signal()
    
    #FIXME: Check whether this is really required.
    # Pure AFM Scan
    sigAFMLineScanFinished = QtCore.Signal()

    # position of Objective in SI in x,y,z
    sigNewObjPos = QtCore.Signal(dict)
    sigObjTargetReached = QtCore.Signal()

    # position of AFM in SI in x,y,z
    sigNewAFMPos = QtCore.Signal(dict)
    sigAFMTargetReached = QtCore.Signal()

    # Optimizer related signals
    sigOptimizeScanInitialized = QtCore.Signal(str)
    sigOptimizeLineScanFinished = QtCore.Signal(str) 
    sigOptimizeScanFinished = QtCore.Signal()

    # HealthChecker signals
    sigHealthCheckStartSkip = QtCore.Signal()
    sigHealthCheckStopSkip = QtCore.Signal()

    # save data signals
    sigSaveDataGwyddion = QtCore.Signal(object,object,object,object) 
    sigSaveDataGwyddionFinished = QtCore.Signal(int)

    # saved signals
    sigQAFMDataSaved = QtCore.Signal()
    sigObjDataSaved = QtCore.Signal()
    sigOptiDataSaved = QtCore.Signal()
    sigQuantiDataSaved = QtCore.Signal()

    # Quantitative Scan (Full B Scan)
    sigQuantiLineFinished = QtCore.Signal()
    sigQuantiScanStarted = QtCore.Signal()
    sigQuantiScanFinished = QtCore.Signal()

    # Single IsoB Parameter
    sigIsoBParamsUpdated = QtCore.Signal()

    _obj_pos = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    _afm_pos = {'x': 0.0, 'y': 0.0}

    __data_to_be_saved = 0  # emit a signal if the data to be saved reaches 0

    #optimizer: x_max, y_max, c_max, z_max, c_max_z
    _opt_val = [0, 0, 0, 0, 0]

    # make a dummy worker thread:
    _worker_thread = WorkerThread(print)
    _optimizer_thread = WorkerThread(print)

    # NV parameters:
    ZFS = 2.87e9    # Zero-field-splitting
    E_FIELD = 0.0   # strain field

    # Move Settings
    _sg_idle_move_target_sample = StatusVar(default=0.5)
    _sg_idle_move_target_obj = StatusVar(default=0.5)

    # Scan Settings
    _sg_idle_move_scan_sample = StatusVar(default=0.1)
    _sg_idle_move_scan_obj = StatusVar(default=0.1)
    _sg_int_time_sample_scan = StatusVar(default=0.01)
    _sg_int_time_obj_scan = StatusVar(default=0.01)

    # Save Settings
    _sg_root_folder_name = StatusVar(default='')
    _sg_create_summary_pic = StatusVar(default=True)
    _sg_save_to_gwyddion = StatusVar(default=False)

    # Save scan automatically after it has finished
    _sg_auto_save_quanti = StatusVar(default=False)
    _sg_auto_save_qafm = StatusVar(default=False)

    # Optimizer Settings
    _sg_optimizer_x_range = StatusVar(default=1.0e-6)
    _sg_optimizer_x_res = StatusVar(default=15)
    _sg_optimizer_y_range = StatusVar(default=1.0e-6)
    _sg_optimizer_y_res = StatusVar(default=15)
    _sg_optimizer_z_range = StatusVar(default=2.0e-6)
    _sg_optimizer_z_res = StatusVar(default=50)    
    _sg_optimizer_int_time = StatusVar(default=0.01)
    _sg_periodic_optimizer = False  # do not save this a status var
    _sg_optimizer_period = StatusVar(default=60)
    _optimize_request = False

    # iso-b settings
    _sg_iso_b_operation = False    # indicate whether iso-b is on
    _sg_iso_b_single_mode = StatusVar(default=True)  # default mode is single iso-B 
    _sg_iso_b_single_mode = StatusVar(default=True)  # default mode is single iso-B 
    _sg_iso_b_autocalibrate_margin = StatusVar(default=True)  # default is autocalibrate
    _sg_n_iso_b_pulse_margin = StatusVar(default=0.005)  # fraction of integration time for pause 
    _sg_n_iso_b_n_freq_splits = StatusVar(default=10)    # number of frequency sub splits to use
    _sg_n_iso_b_laser_cooldown_length = StatusVar(default=10e-6) # laser cool down time (s)

    _sg_pulsed_measure_operation = False

    # target positions of the optimizer
    _optimizer_x_target_pos = 15e-6
    _optimizer_y_target_pos = 15e-6
    _optimizer_z_target_pos = 5e-6

    sigSettingsUpdated = QtCore.Signal()

    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        # locking mechanism for thread safety. Use it like
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.
        self.threadlock = Mutex()

        # checking for the right configuration
        for key in config.keys():
            self.log.debug('{0}: {1}'.format(key, config[key]))

        # make at first a certain shape


    def on_activate(self):
        """ Initialization performed during activation of the module. """

        # Connect to hardware and save logic
        self._spm = self.spm_device()
        #self._spm = SmartSPM()                    # temporarily get language server's help
        self._save_logic = self.savelogic()
        self._counter = self.counter_device()   # temporarily disable
        #self._counter = MicrowaveQ()           # uncomment to get language server's help
        self._counterlogic = self.counter_logic()
        self._fitlogic = self.fitlogic()
        self._pulser = self.pulser()
        self._mw = self.microwave()

        self._qafm_scan_array = self.initialize_qafm_scan_array(0, 100e-6, 10, 
                                                                0, 100e-6, 10)

        self._obj_scan_array = self.initialize_obj_scan_array('obj_xy', 
                                                               0, 30e-6, 30,
                                                               0, 30e-6, 30)
        self._obj_scan_array = self.initialize_obj_scan_array('obj_xz', 
                                                               0, 30e-6, 30,
                                                               0, 10e-6, 30)
        self._obj_scan_array = self.initialize_obj_scan_array('obj_yz', 
                                                               0, 30e-6, 30,
                                                               0, 10e-6, 30)

        self._opti_scan_array = self.initialize_opti_xy_scan_array(0, 2e-6, 30,
                                                                   0, 2e-6, 30)

        self._opti_scan_array = self.initialize_opti_z_scan_array(0, 10e-6, 30)

        self.sigNewObjPos.emit(self.get_obj_pos())
        self.sigNewAFMPos.emit(self.get_afm_pos())

        self._save_logic.sigSaveFinished.connect(self.decrease_save_counter)
    
        self.sigSaveDataGwyddion.connect(self._save_to_gwyddion)
        self.sigSaveDataGwyddionFinished.connect(self.decrease_save_counter)

        self._meas_path = os.path.abspath(self._meas_path)

        #FIXME: Introduce a state variable to prevent redundant configuration calls of the hardware.
        # self._counter.configure_recorder(mode=HWRecorderMode.PIXELCLOCK,
        #                                  params={'mw_frequency': 2.8e9, 
        #                                          'num_meas': 100})

        # safety precaution in case the meas path does not exist
        if not os.path.exists(self._meas_path):
            self._meas_path = self._save_logic.get_path_for_module(module_name='AttoDRY2200_Pi3_SPM')

        # in this threadpool our worker thread will be run
        self.threadpool = QtCore.QThreadPool()

        # check the version of the spm interface
        self.start_spm_version_check()

        self.sigOptimizeScanFinished.connect(self._optimize_finished)

    def on_deactivate(self):
        """ Deinitializations performed during deactivation of the module. """

        pass

    def start_spm_version_check(self):

        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self._spm.check_interface_version,
                                           args=(10,),     # pause time to avoid threadlock
                                           name='spm_version_check')

        self.threadpool.start(self._worker_thread)


    def initialize_qafm_scan_array(self, x_start, x_stop, num_columns, 
                                         y_start, y_stop, num_rows):
        """ Initialize the qafm scan array. 

        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """


        coord0_arr = np.linspace(x_start, x_stop, num_columns, endpoint=True)
        coord1_arr = np.linspace(y_start, y_stop, num_rows, endpoint=True)

        #FIXME: use Tesla not Gauss, right not, this is just for display purpose
        # add counts to the parameter list
        meas_params_units = {'counts':       {'measured_units' : 'c/s',
                                            'scale_fac': 1,    # multiplication factor to obtain SI units    
                                            'si_units': 'c/s', 
                                            'nice_name': 'Fluorescence'},
                             'counts2':      {'measured_units' : 'c/s',
                                              'scale_fac': 1,    # multiplication factor to obtain SI units    
                                              'si_units': 'c/s', 
                                              'nice_name': 'Fluorescence'},
                             'counts_diff':  {'measured_units' : 'c/s',
                                              'scale_fac': 1,    # multiplication factor to obtain SI units    
                                              'si_units': 'c/s', 
                                              'nice_name': 'Fluorescence'},
                             'b_field':      {'measured_units' : 'G',
                                              'scale_fac': 1,    # multiplication factor to obtain SI units
                                              'si_units': 'G',
                                              'nice_name': 'Magnetic field '},
                            }
        meas_params_units.update(self.get_afm_meas_params())

        meas_params = list(meas_params_units)

        meas_dir = ['fw', 'bw']
        meas_dict = {}

        for direction in meas_dir:
            for param in meas_params:

                name = f'{param}_{direction}' # this is the naming convention!

                meas_dict[name] = {'data': np.zeros((num_rows, num_columns))}
                #meas_dict[name] = {'data': np.random.rand(num_rows, num_columns)}
                meas_dict[name]['coord0_arr'] = coord0_arr
                meas_dict[name]['coord1_arr'] = coord1_arr
                meas_dict[name]['corr_plane_coeff'] = [0.0, 0.0, 0.0] 
                meas_dict[name]['image_correction'] = False
                meas_dict[name].update(meas_params_units[param])
                meas_dict[name]['params'] = {}
                meas_dict[name]['display_range'] = None

        self.sigQAFMScanInitialized.emit()

        return meas_dict

    def initialize_esr_scan_array(self, esr_start, esr_stop, esr_num,
                                  coord0_start, coord0_stop, num_columns,
                                  coord1_start, coord1_stop, num_rows):
        """ Initialize the ESR scan array data.
        The dimensions are not the same for the ESR data, it is a 3 dimensional
        tensor rather then a 2 dimentional matrix. """


        meas_dir = ['fw', 'bw']
        meas_dict = {}

        for entry in meas_dir:
            name = f'esr_{entry}'

            meas_dict[name] = {'data': np.zeros((num_rows, num_columns, esr_num)),
                               'data_std': np.zeros((num_rows, num_columns, esr_num)),
                               'data_fit': np.zeros((num_rows, num_columns, esr_num)),
                               'coord0_arr': np.linspace(coord0_start, coord0_stop, num_columns, endpoint=True),
                               'coord1_arr': np.linspace(coord1_start, coord1_stop, num_rows, endpoint=True),
                               'coord2_arr': np.linspace(esr_start, esr_stop, esr_num, endpoint=True),
                               'measured_units': 'c/s',
                               'scale_fac': 1,  # multiplication factor to obtain SI units
                               'si_units': 'c/s',
                               'nice_name': 'Fluorescence',
                               'params': {},  # !!! here are all the measurement parameter saved
                               'display_range': None,
                               }

        return meas_dict


    def initialize_obj_scan_array(self, plane_name, coord0_start, coord0_stop, num_columns, 
                                     coord1_start, coord1_stop, num_rows):

        meas_dict = {'data': np.zeros((num_rows, num_columns)),
                     'coord0_arr': np.linspace(coord0_start, coord0_stop, num_columns, endpoint=True),
                     'coord1_arr': np.linspace(coord1_start, coord1_stop, num_rows, endpoint=True),
                     'measured_units' : 'c/s', 
                     'scale_fac': 1,    # multiplication factor to obtain SI units   
                     'si_units': 'c/s', 
                     'nice_name': 'Fluorescence',
                     'params': {}, # !!! here are all the measurement parameter saved
                     'display_range': None,
                     }
            
        self._obj_scan_array[plane_name] = meas_dict

        self.sigObjScanInitialized.emit(plane_name)

        return self._obj_scan_array
        

    def initialize_opti_xy_scan_array(self, coord0_start, coord0_stop, num_columns, 
                                      coord1_start, coord1_stop, num_rows):
        """ Initialize the optimizer scan array. 

        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """
        name = 'opti_xy'

        meas_dict = {'data': np.zeros((num_rows, num_columns)),
                     'data_fit': np.zeros((num_rows, num_columns)),
                     'coord0_arr': np.linspace(coord0_start, coord0_stop, num_columns, endpoint=True),
                     'coord1_arr': np.linspace(coord1_start, coord1_stop, num_rows, endpoint=True),
                     'measured_units' : 'c/s', 
                     'scale_fac': 1,    # multiplication factor to obtain SI units 
                     'si_units': 'c/s', 
                     'nice_name': 'Fluorescence',
                     'params': {}, # !!! here are all the measurement parameter saved, including the fit parameter
                     'display_range': None,
                    }

        self._opti_scan_array[name] = meas_dict

        self.sigOptimizeScanInitialized.emit(name)

        return self._opti_scan_array

    def initialize_opti_z_scan_array(self, coord0_start, coord0_stop, num_points):
        """ Initialize the z scan line. 

        @param int num_points: number of points for the line
        """
        name = 'opti_z'

        meas_dict = {'data': np.zeros(num_points),
                     'coord0_arr': np.linspace(coord0_start, coord0_stop, num_points, endpoint=True),
                     'measured_units' : 'c/s', 
                     'scale_fac': 1,    # multiplication factor to obtain SI units 
                     'si_units': 'c/s', 
                     'nice_name': 'Fluorescence',
                     'params': {}, # !!! here are all the measurement parameter saved
                     'fit_result': None,
                     'display_range':None,
                     'data_fit': np.zeros(num_points)
                     }

        self._opti_scan_array[name] = meas_dict

        self.sigOptimizeScanInitialized.emit(name)
        return self._opti_scan_array

    def get_afm_meas_params(self):
        return self._spm.get_available_measurement_params()


    def get_curr_scan_params(self):
        """ Return the actual list of scanning parameter, forward and backward. """

        scan_param = []

        for entry in self._curr_scan_params:
            scan_param.append(f'{entry}_fw')
            scan_param.append(f'{entry}_bw')

        return scan_param


    def get_qafm_settings(self, setting_list=None):
        """ Obtain all the settings for the qafm in a dict container. 

        @param list setting_list: optional, if specific settings are required, 
                                  and not all of them, then you can specify 
                                  those in this list.  

        @return dict: with all requested or available settings for qafm.
        """

        # settings dictionary
        sd = {}
        # Move Settings
        sd['idle_move_target_sample'] = self._sg_idle_move_target_sample
        sd['idle_move_target_obj'] = self._sg_idle_move_target_obj
        # Scan Settings
        sd['idle_move_scan_sample'] = self._sg_idle_move_scan_sample
        sd['idle_move_scan_obj'] = self._sg_idle_move_scan_obj
        sd['int_time_sample_scan'] = self._sg_int_time_sample_scan
        sd['int_time_obj_scan'] = self._sg_int_time_obj_scan
        # Save Settings
        sd['root_folder_name'] = self._sg_root_folder_name
        sd['create_summary_pic'] = self._sg_create_summary_pic
        sd['auto_save_quanti'] = self._sg_auto_save_quanti
        sd['auto_save_qafm'] = self._sg_auto_save_qafm
        sd['save_to_gwyddion'] = self._sg_save_to_gwyddion
        # Optimizer Settings
        sd['optimizer_x_range'] = self._sg_optimizer_x_range
        sd['optimizer_x_res'] = self._sg_optimizer_x_res
        sd['optimizer_y_range'] = self._sg_optimizer_y_range
        sd['optimizer_y_res'] = self._sg_optimizer_y_res
        sd['optimizer_z_range'] = self._sg_optimizer_z_range
        sd['optimizer_z_res'] = self._sg_optimizer_z_res

        sd['optimizer_int_time'] = self._sg_optimizer_int_time
        sd['optimizer_period'] = self._sg_optimizer_period

        sd['iso_b_operation'] = self._sg_iso_b_operation
        sd['iso_b_single_mode'] = self._sg_iso_b_single_mode
        sd['iso_b_autocalibrate_margin'] = self._sg_iso_b_autocalibrate_margin
        sd['n_iso_b_pulse_margin'] = self._sg_n_iso_b_pulse_margin
        sd['n_iso_b_n_freq_splits'] = self._sg_n_iso_b_n_freq_splits

        sd['pulsed_measure_operation'] = self._sg_pulsed_measure_operation

        if setting_list is None:
            return sd
        else:
            ret_sd = {}
            for entry in setting_list:
                item = sd.get(entry, None)
                if item is not None:
                    ret_sd[entry] = item
            return ret_sd

    def set_qafm_settings(self, set_dict):
        """ Set the current qafm settings. 

        @params dict set_dict: a dictionary containing all the settings which 
                               needs to be set. For an empty dict, nothing will
                               happen. 
                               Hint: use the get_qafm_settings method to obtain
                                     a full list of available items.
                               E.g.: To set the single_iso_b_operation perform
                                    setting = {'single_iso_b_operation': True}
                                    self.set_qafm_settings(setting)

        """
        
        for entry in set_dict:
            attr_name = f'_sg_{entry}'
            if hasattr(self, attr_name):
                setattr(self, attr_name, set_dict[entry])

        self.sigSettingsUpdated.emit()

    def set_color_map(self, cmap_name):
        """  Sets the color map to be used in the 'display_figures' routine
            This information is set from the Gui definition of the color map

        @param str cmap_name:  color map name (from Matplotlib) to be used for save figures
        """
        self._color_map = cmap_name

    
    def get_hardware_status(self,request=None):
        """ Access function for counter logic
        @params: list request (or None): specific request parameters to return
        @return dict:  hardware status as gathered from counter logic, 
                       specifically microwaveQ:
                       'available_features' : what is possible
                       'unlocked_features'  : what the license allows
                       'fpga_version'       : version level of FPGA
                       'dac_alarms'         : DAC alarms as reported by board
                    if this is a 'counter_dummy', then 'None' is returned
        """
        if request is None:
            request = ['available_features', 'unlocked_features',
                       'fpga_version','dac_alarms',
                       'spm_library_version', 'spm_server_version',
                       'spm_client_version','spm_is_server_compatible',
                       'spm_pixelclock_timing']

        status = dict()
        spm_status = self._spm.get_device_meta_info()

        if 'available_features' in request:
            status['available_features'] = self._counter._dev.get_available_features()

        if 'unlocked_features' in request:
            status['unlocked_features'] = self._counter._dev.get_unlocked_features()
        
        if 'fpga_version' in request:
            status['fpga_version'] = self._counter._dev.sys.fpgaVersion.get()
        
        if 'dac_alarms' in request:
            status['dac_alarms'] = self._counter._dev.get_DAC_alarms()

        if 'spm_library_version' in request:
            status['spm_library_version'] = spm_status['LIBRARY_VERSION'] 

        if 'spm_server_version' in request:
            status['spm_server_version'] = spm_status['SERVER_VERSION'] 

        if 'spm_client_version' in request:
            status['spm_client_version'] = spm_status['CLIENT_VERSION'] 
    
        if 'spm_is_server_compatible' in request:
            status['spm_is_server_compatible'] = spm_status['IS_SERVER_COMPATIBLE'] 

        if 'spm_pixelclock_timing' in request:
            status['spm_pixelclock_timing'] = self._pixel_clock_tdiff 
        
        return status


    def get_iso_b_operation(self):
        """ return status if in iso-b mode"""
        return self._sg_iso_b_operation

    def set_iso_b_operation(self, state):
        """ set iso-b operation mode"""
        self.set_qafm_settings({'iso_b_operation': state})

    def set_iso_b_mode(self, state):
        """ switch on single iso b """
        self.set_qafm_settings({'iso_b_single_mode': state})
        
    def get_iso_b_mode(self):
        """ Check whether single iso-b is switched on. """
        return self._sg_iso_b_single_mode

    def set_iso_b_params(self, single_mode=None, freq1=None, freq2=None, fwhm=None, power=None):

        if single_mode is not None:
            self._iso_b_single_mode = single_mode
            self.set_iso_b_mode(state=single_mode)

        if freq1 is not None:
            self._freq1_iso_b_frequency = freq1

        if freq2 is not None:
            self._freq2_iso_b_frequency = freq2

        if fwhm is not None:
            self._fwhm_iso_b_frequency = fwhm

        if power is not None:
            self._iso_b_power = power

        self.sigIsoBParamsUpdated.emit()

    def get_iso_b_params(self):
        """ return the frequency and power"""
        return self._sg_iso_b_operation, \
               self._sg_iso_b_single_mode, \
               self._freq1_iso_b_frequency, \
               self._freq2_iso_b_frequency, \
               self._fwhm_iso_b_frequency, \
               self._iso_b_power
            
# ==============================================================================
#           Scan helper functions
# ==============================================================================

    def create_scan_leftright(self, x_start, x_stop, y_start, y_stop, res_y):
        """ Create a scan line array for measurements from left to right.
        
        This is only a 'forward measurement', meaning from left to right. It is 
        assumed that a line scan is performed and fast axis is the x axis.
        
        @return list: with entries having the form [x_start, x_stop, y_start, y_stop]
        """
        y = np.linspace(y_start, y_stop, res_y)
        
        arr = []
        for y_val in y:
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
        y = np.linspace(y_start, y_stop, res_y)

        arr = []
        for y_val in y:
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


    @deprecated('Current function is no longer in use')
    def create_scan_snake(self, x_start, x_stop, y_start, y_stop, res_y):
        """ Create a snake like movement within the scan."""
        # it is assumed that a line scan is performed and fast axis is the x axis.
        y = np.linspace(y_start, y_stop, res_y)
        
        reverse = False
        arr = []
        for y_val in y:
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


# ==============================================================================
#           QAFM area scan functions
# ==============================================================================

    #FIXME: Think about transferring the normalization of the 'Height(Dac)' and 
    #       'Height(Sen)' parameter to the hardware level.
    #       In the hardware, the last measured value can always be tracked.
    #       You also know that if the method setup_spm is used, then we have to 
    #       update the normalization parameter. 
    #       For now, it can be confusing, hence, at the moment, this 
    #       normalization will take place in the logic.
    def scan_area_qafm_bw_fw_by_line(self, coord0_start, coord0_stop, coord0_num,
                                     coord1_start, coord1_stop, coord1_num,
                                     integration_time, plane='XY',
                                     meas_params=['counts', 'Height(Dac)'],
                                     continue_meas=False):

        """ QAFM measurement (optical + afm) forward and backward for a scan by line.

        @param float coord0_start: start coordinate in m
        @param float coord0_stop: start coordinate in m
        @param int coord0_num: number of points in coord0 direction
        @param float coord1_start: start coordinate in m
        @param float coord1_stop: start coordinate in m
        @param int coord1_num: number of points in coord1 direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                            'XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement
                                 parameter. Have a look at MEAS_PARAMS to see
                                 the available parameters. Include the parameter
                                 'Counts', if you want to measure them.

        @return 2D_array: measurement results in a two dimensional list.
        """

        if integration_time is None:
            integration_time = self._sg_int_time_sample_scan

        self.module_state.lock()
        self.sigQAFMScanStarted.emit()

        # set up the spm device:
        reverse_meas = False
        self._stop_request = False
        laser_cooldown_length = self._sg_n_iso_b_laser_cooldown_length
        pulse_margin_frac = self._sg_n_iso_b_pulse_margin

        # determine iso_b_mode
        scan_mode = 'pixel'
        if self._sg_iso_b_operation:
            if self._iso_b_single_mode:
                scan_mode = 'single iso-b'
            else:
                scan_mode = 'dual iso-b'

        # time in which the stage is just moving without measuring
        time_idle_move = self._sg_idle_move_scan_sample

        scan_speed_per_line = integration_time * coord0_num

        scan_arr = self.create_scan_leftright2(coord0_start, coord0_stop,
                                               coord1_start, coord1_stop,
                                               coord1_num)

        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                        params={'line_points' : coord0_num,
                                                'meas_params' : meas_params },
                                        scan_style=ScanStyle.LINE) 
        print(curr_scan_params, meas_params)

        spm_start_idx = 0

        #FIXME: check whether bugs can occur if you do not reset the following values.
        if not continue_meas:
            # if optimization happens during the scan, then we need to handle
            # manually the normalization of both AFM parameters. Every time 
            # 'setup_spm' is called, then the zero value is referred to the first
            # measured point. 
            self._height_sens_norm = 0.0
            self._height_dac_norm = 0.0

        _update_normalization = 0   # number of items to normalize
        pulse_lengths = []
        freq_list = []
        freq1_pulse_time, freq2_pulse_time = integration_time, integration_time # default divisor times 
        self._spm.set_ext_trigger(False)
        if 'counts' in meas_params:
            self._spm.set_ext_trigger(True)
            curr_scan_params.insert(0, 'counts')  # fluorescence of freq1 parameter
            spm_start_idx = 1 # start index of the temporary scan for the spm parameters
            
            if scan_mode == 'pixel':
                ret_val_mq = self._counter.configure_recorder(mode=HWRecorderMode.PIXELCLOCK, 
                                                              params={'num_meas': coord0_num})
                self._pulser.load_swabian_sequence(self._make_pulse_sequence(HWRecorderMode.PIXELCLOCK, integration_time))
                self._pulser.pulser_on(trigger=True, n=1)
                self.log.info(f'Prepared pixelclock, val {ret_val_mq}')

            elif scan_mode == 'single iso-b':
                ret_val_mq = self._counter.configure_recorder(
                    mode=HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B,
                    params={'mw_frequency':self._freq1_iso_b_frequency,
                            'mw_power': self._iso_b_power, 
                            'num_meas': coord0_num })
                self._pulser.load_swabian_sequence(self._make_pulse_sequence(HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B, integration_time))
                self._pulser.pulser_on(trigger=True, n=1)
                self._mw.set_cw(self._freq1_iso_b_frequency, self._iso_b_power)
                self._mw.cw_on()
                self.log.info(f'Prepared pixelclock single iso b, val {ret_val_mq}')

            elif scan_mode == 'dual iso-b':
                # dual iso-b
                if self._sg_iso_b_autocalibrate_margin:
                    if not self._pixel_clock_tdiff:
                        self.log.error("Dual iso-B: to use pulse margin autocalibration,"
                                       " at least 1 quenching scan must be performed; Perform the quenching scan first") 
                    else:
                        int_time_ms = int(integration_time * 1000)
                        tdiff = self._pixel_clock_tdiff.get(int_time_ms, None)
                        min_margin = tdiff['margin_2sd'] if tdiff is not None \
                                     else  min([td['margin_2sd'] for td in self._pixel_clock_tdiff.values()])

                        # time consumed in pulse is: pixel clock margin, laser cooldown, 
                        # and the number of frequency configurations made (=n_freq*n_splits)
                        t_consume = abs(min_margin) + \
                                    self._sg_n_iso_b_laser_cooldown_length + \
                                    2 * self._sg_n_iso_b_n_freq_splits * self._counter._iso_b_pulse_config_time

                        pulse_margin_frac = t_consume / integration_time  
                        self.log.info(f'Autocalibrated pulse margin used = {pulse_margin_frac}')

                freq_list=[self._freq1_iso_b_frequency, self._freq2_iso_b_frequency] 
                pulse_length = integration_time * (1 - pulse_margin_frac) / len(freq_list)
                pulse_lengths=[pulse_length]*len(freq_list)
                freq1_pulse_time, freq2_pulse_time = pulse_lengths

                ret_val_mq = self._counter.configure_recorder(
                    mode=HWRecorderMode.PIXELCLOCK_N_ISO_B,
                    params={'mw_frequency_list': freq_list,
                            'mw_pulse_lengths': pulse_lengths,
                            'mw_power': self._iso_b_power,
                            'mw_n_freq_splits': self._sg_n_iso_b_n_freq_splits,
                            'mw_laser_cooldown_time': self._sg_n_iso_b_laser_cooldown_length,
                            'num_meas': coord0_num })

                self.log.info(f'Used "mw_n_freq_splits={self._sg_n_iso_b_n_freq_splits}')
                    
                # add counts2 parameter
                curr_scan_params.insert(1, 'counts2')      # fluorescence of freq2 parameter
                curr_scan_params.insert(2, 'counts_diff')  # difference in 'counts2' - 'counts' 
                spm_start_idx = 3 # start index of the temporary scan for the spm parameters
                #curr_scan_params.insert(3, 'b_field')  # insert the magnetic field parameter   # FIXME
                #spm_start_idx = 4 # start index of the temporary scan for the spm parameters

                self.log.info(f'Prepared pixelclock dual iso b, val {ret_val_mq}')
            
            else:
                self.log.error('AFM_logic error; inconsitent modality')


            if ret_val_mq < 0:
                self.module_state.unlock()
                self.sigQAFMScanFinished.emit()

                self.log.info(f'Return.')

                return self._qafm_scan_array
        
        meas_params = curr_scan_params
            
        # this case is for starting a new measurement:
        if (self._spm_line_num == 0) or (not continue_meas):
            self._spm_line_num = 0
            self._afm_meas_duration = 0

            # AFM signal
            self._qafm_scan_array = self.initialize_qafm_scan_array(coord0_start,
                                                                    coord0_stop,
                                                                    coord0_num,
                                                                    coord1_start,
                                                                    coord1_stop,
                                                                    coord1_num)
            self._scan_counter = 0

        # check input values
        # ret_val |= self._spm.check_spm_scan_params_by_plane(plane,
        #                                                     coord0_start,
        #                                                     coord0_stop,
        #                                                     coord1_start,
        #                                                     coord1_stop)
        if ret_val < 1:
            self.module_state.unlock()
            self.sigQAFMScanFinished.emit()
            return self._qafm_scan_array

        start_time_afm_scan = datetime.datetime.now()
        self._curr_scan_params = curr_scan_params

        num_params = len(curr_scan_params)

        # save the measurement parameter
        for entry in self._qafm_scan_array:
            self._qafm_scan_array[entry]['params']['Parameters for'] = 'QAFM measurement'
            self._qafm_scan_array[entry]['params']['axis name for coord0'] = 'X'
            self._qafm_scan_array[entry]['params']['axis name for coord1'] = 'Y'
            self._qafm_scan_array[entry]['params']['measurement plane'] = 'XY'
            self._qafm_scan_array[entry]['params']['coord0_start (m)'] = coord0_start
            self._qafm_scan_array[entry]['params']['coord0_stop (m)'] = coord0_stop
            self._qafm_scan_array[entry]['params']['coord0_num (#)'] = coord0_num
            self._qafm_scan_array[entry]['params']['coord1_start (m)'] = coord1_start
            self._qafm_scan_array[entry]['params']['coord1_stop (m)'] = coord1_stop
            self._qafm_scan_array[entry]['params']['coord1_num (#)'] = coord1_num
            self._qafm_scan_array[entry]['params']['correction_plane_eq'] = str(self._qafm_scan_array[entry]['corr_plane_coeff'])
            self._qafm_scan_array[entry]['params']['image_correction'] = str(self._qafm_scan_array[entry]['image_correction'])
            self._qafm_scan_array[entry]['params']['Scan speed per line (s)'] = scan_speed_per_line
            self._qafm_scan_array[entry]['params']['Idle movement speed (s)'] = time_idle_move

            self._qafm_scan_array[entry]['params']['Counter measurement mode'] = self._counter.get_current_measurement_method_name()
            self._qafm_scan_array[entry]['params']['integration time per pixel (s)'] = integration_time
            self._qafm_scan_array[entry]['params']['time per frequency pulse (s)'] = str([freq1_pulse_time, freq2_pulse_time])
            self._qafm_scan_array[entry]['params']['Measurement parameter list'] = str(curr_scan_params)
            self._qafm_scan_array[entry]['params']['Measurement start'] = start_time_afm_scan.isoformat()

        pixel_clock_tdiff = deque(maxlen=2500) 
        for line_num, scan_coords in enumerate(scan_arr):

            # for a continue measurement event, skip the first measurements
            # until one has reached the desired line, then continue from there.
            if line_num < self._spm_line_num:
                continue

            #-------------------
            # Perform line scan
            #-------------------
            self._qafm_scan_line = np.zeros((num_params, coord0_num))

            if 'counts' in meas_params:
                self._counter.start_recorder(arm=True)

            self._spm.configure_line(line_corr0_start=scan_coords[0],
                                     line_corr0_stop=scan_coords[1],
                                     line_corr1_start=scan_coords[2],
                                     line_corr1_stop=scan_coords[3],
                                     time_forward=scan_speed_per_line,
                                     time_back=time_idle_move)

            self._spm.scan_line()  # start the scan line

            #-------------------
            # Process line scan
            #-------------------

            # AFM signal (from SPM)
            if  set(curr_scan_params) - {'counts', 'counts2', 'counts_diff'}:
                # i.e. afm parameters are set
                self._qafm_scan_line[spm_start_idx:] = self._spm.get_measurements(reshape=True)
            else:
                # perform just the scan without using the data.
                self._spm.get_measurements(reshape=True)

            # Optical signal (from MicrowaveQ)
            # The same variables are requested from 'pixel', 'single iso-b', and 'dual iso-b'
            # if they don't exist, then missing value is returned as None
            counts, int_time, counts2, counts_diff = \
                self._counter.get_measurements(['counts', 'int_time', 'counts2', 'counts_diff']) 

            if  'counts' in meas_params:
                # utilize integration time measurement if available 

                if int_time is None or np.any(np.isclose(int_time,0,atol=1e-12)):
                    int_time = freq1_pulse_time
                else:
                    pixel_clock_tdiff.extendleft((int_time - integration_time).tolist())

                i = meas_params.index('counts')
                self._qafm_scan_line[i] = counts/int_time
                # print(self._qafm_scan_line[i])

            if 'counts2' in meas_params:
                # integration times for iso-B measurements are exact, not dependent upon pixel clock pulse
                i = meas_params.index('counts2')
                self._qafm_scan_line[i] = counts2 / freq2_pulse_time

                i = meas_params.index('counts_diff')
                self._qafm_scan_line[i] = counts_diff / (freq1_pulse_time + freq2_pulse_time) / 2

                # FIXME: currently, this method will not work based on only 2 points
                #        Issues:
                #               - In reducing the slope formed by L(freq1)/L(freq2)   (L()=Lorenztian)
                #                 there are two possible solutions: to left and right of inflection point (sigma/sqrt(3))
                #                 It is not possible to determine which side you are on without a 3rd point
                #               - With only 2 points, the slope of a curve is not distguishable from noise
                #               
                #i = meas_params.index('b_field')
                #self._qafm_scan_line[i] = self.calc_mag_field_single_res(
                #        self.calc_eps_shift_dual_iso_b(
                #            counts1=self._counter.get_measurements('counts'),
                #            counts2=self._counter.get_measurements('counts2'),
                #            freq1=self._freq1_iso_b_frequency,
                #            freq2=self._freq2_iso_b_frequency,
                #            sigma=self._fwhm_iso_b_frequency / 2) 
                #        +  (self._freq1_iso_b_frequency + self._freq2_iso_b_frequency) /2,  
                #        self.ZFS, 
                #        self.E_FIELD) * 10000

            row_i = line_num // 2    # row number for qafm_array
            if not reverse_meas:
                # current is forward pass, optimization occured on backward pass
                ref_j = -1             
                curr_direc, past_direc  = '_fw' , '_bw'
            else:
                # current is backward pass, optimization occured on forward pass
                ref_j = 0             
                curr_direc, past_direc  = '_bw' , '_fw'

            # Iterate through parameters
            for index, param_name in enumerate(curr_scan_params):
                name = param_name + curr_direc 

                # check if line was a reverse scan, if so, flip
                if not reverse_meas:
                    data = self._qafm_scan_line[index] 
                else:
                    data = np.flip(self._qafm_scan_line[index], axis=0) 

                # store transformed data
                self._qafm_scan_array[name]['data'][row_i] = data * self._qafm_scan_array[name]['scale_fac']

                # if optimization was performed after last measurement, then adjust the normalization 
                if _update_normalization:

                    if 'Height(Dac)' in name:
                        self._height_dac_norm =   self._qafm_scan_array['Height(Dac)' + past_direc]['data'][row_i - 1][ref_j]   \
                                                - self._qafm_scan_array['Height(Dac)' + curr_direc]['data'][row_i    ][ref_j]
                        _update_normalization -= 1   # parameter complete

                    if 'Height(Sen)' in name:
                        self._height_sens_norm =  self._qafm_scan_array['Height(Sen)' + past_direc]['data'][row_i - 1][ref_j]   \
                                                - self._qafm_scan_array['Height(Sen)' + curr_direc]['data'][row_i    ][ref_j]
                        _update_normalization -= 1   # parameter complete

                
                # apply normalization (at start, normalization parameters = 0)
                if 'Height(Dac)' in name:
                    self._qafm_scan_array[name]['data'][row_i] += self._height_dac_norm

                if 'Height(Sen)' in name:
                    self._qafm_scan_array[name]['data'][row_i] += self._height_sens_norm
            
            # determine correction plane for relative measurements
            if row_i >= 1:
                for name in {p + sfx for p in curr_scan_params for sfx in ('_fw', '_bw')} & \
                            {'Height(Dac)_fw', 'Height(Dac)_bw', 'Height(Sen)_fw','Height(Sen)_bw'}:
                    x_range = [self._qafm_scan_array[name]['coord0_arr'][0], 
                               self._qafm_scan_array[name]['coord0_arr'][-1]]
                    y_range = [self._qafm_scan_array[name]['coord1_arr'][0], 
                               self._qafm_scan_array[name]['coord1_arr'][row_i]]
                    xy_data = self._qafm_scan_array[name]['data'][:row_i+1]
                    _,C = self.correct_plane(xy_data=xy_data,x_range=x_range,y_range=y_range)
                    #self.log.debug(f"Determined tilt correction for name={name} as C={C.tolist()}")

                    # update plane equation
                    self._qafm_scan_array[name]['params']['correction_plane_eq'] = str(C.tolist())
                    self._qafm_scan_array[name]['params']['image_correction'] = str(self._qafm_scan_array[name]['image_correction'])
                    self._qafm_scan_array[name]['corr_plane_coeff'] = C.copy()

            # change direction
            if reverse_meas:
                reverse_meas = False
                self.sigQAFMLineScanFinished.emit()      # emit only a signal if the reversed is finished.
            else:
                reverse_meas = True

            self.log.info(f'Line number {line_num} completed.')

            # determine pixel clock margin to use
            if pixel_clock_tdiff:
                int_time_ms = int(integration_time * 1000)
                tdiff = np.array(pixel_clock_tdiff)

                # obtain the min time difference for the short pulses
                # where there is less than 0.01% chance of being lower (short pulse)
                if tdiff.min() < 0.0:
                    sym_tdiff = tdiff[ tdiff < -tdiff.min()]
                    mu, sigma = norm.fit(sym_tdiff)
                    margin_01p = norm.ppf(0.0001,mu,sigma)  # the 0.01% chance
                else:
                    margin_01p = tdiff.min() 
                    
                margin_2sd = margin_01p - 2*tdiff.std()     # extra safety margin

                self._pixel_clock_tdiff[int_time_ms] = { 'n'         : tdiff.shape[0],
                                                         'mean'      : tdiff.mean(),
                                                         'stdev'     : tdiff.std(),
                                                         'min'       : tdiff.min(),
                                                         'max'       : tdiff.max(),
                                                         'margin_01p': margin_01p,
                                                         'margin_2sd': margin_2sd }
                self._pixel_clock_tdiff_data[int_time_ms] = pixel_clock_tdiff

            # enable the break only if next scan goes into forward movement
            if self._stop_request and not reverse_meas:
                break

            # store the current line number
            self._spm_line_num = line_num

            # if next measurement is not in the reverse way, make a quick stop
            # and perform here an optimization first
            if self.get_optimize_request():

                _update_normalization = 0
                if 'Height(Dac)' in curr_scan_params: _update_normalization += 1 
                if 'Height(Sen)' in curr_scan_params: _update_normalization += 1 

                self._counter.stop_measurement()
                self._spm.finish_scan()

                self.sigHealthCheckStartSkip.emit()
                time.sleep(2)
                self.log.debug('optimizer started.')

                self.default_optimize()
                _, _, _ = self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                                      params= {'line_points': coord0_num,
                                                               'meas_params': meas_params},
                                                      scan_style=ScanStyle.LINE) 

                if 'counts' in meas_params:
                    self._spm.set_ext_trigger(True)

                # pixel clock
                if scan_mode == 'pixel':
                    self._counter.configure_recorder(
                        mode=HWRecorderMode.PIXELCLOCK, 
                        params={'mw_frequency': self._freq1_iso_b_frequency,
                                'num_meas': coord0_num})

                # single iso-b
                elif scan_mode == 'single iso-b':
                    self._counter.configure_recorder(
                        mode=HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B,
                        params={'mw_frequency':self._freq1_iso_b_frequency,
                                'mw_power': self._iso_b_power, 
                                'num_meas': coord0_num })

                # dual iso-b
                elif scan_mode == 'dual iso-b':
                    self._counter.configure_recorder(
                        mode=HWRecorderMode.PIXELCLOCK_N_ISO_B,
                        params={'mw_frequency_list': freq_list,
                                'mw_pulse_lengths': pulse_lengths,
                                'mw_power': self._iso_b_power,
                                'mw_n_freq_splits': self._sg_n_iso_b_n_freq_splits,
                                'mw_laser_cooldown_time': self._sg_n_iso_b_laser_cooldown_length,
                                'num_meas': coord0_num })

                # incosistend mode found
                else:
                    self.log.error('AFM_logic error; inconsitent modality')

                self.log.debug('optimizer finished.')

        stop_time_afm_scan = datetime.datetime.now()
        self._afm_meas_duration = self._afm_meas_duration + (stop_time_afm_scan - start_time_afm_scan).total_seconds()

        if line_num == self._spm_line_num:
            self.log.info(f'Scan finished at {int(self._afm_meas_duration)}s. Yeehaa!')
        else:
            self.log.info(f'Scan stopped at {int(self._afm_meas_duration)}s.')

        for entry in self._qafm_scan_array:
            self._qafm_scan_array[entry]['params']['Measurement stop'] = stop_time_afm_scan.isoformat()
            self._qafm_scan_array[entry]['params']['Total measurement time (s)'] = self._afm_meas_duration

        # clean up the counter
        if 'counts' in meas_params:
            self._counter.stop_measurement()

        # clean up the spm
        self._spm.finish_scan()
        self._mw.off()
        self.module_state.unlock()
        self.sigQAFMScanFinished.emit()

        return self._qafm_scan_array


    def start_scan_area_qafm_bw_fw_by_line(self, coord0_start=48*1e-6, coord0_stop=53*1e-6, coord0_num=40,
                            coord1_start=47*1e-6, coord1_stop=52*1e-6, coord1_num=40, integration_time=None,
                            plane='XY', meas_params=['counts', 'Phase', 'Height(Dac)', 'Height(Sen)'],
                            continue_meas=False):

        if self._USE_THREADED:
            if self.check_thread_active():
                self.log.error("A measurement is currently running, stop it first!")
                return

            self._worker_thread = WorkerThread(target=self.scan_area_qafm_bw_fw_by_line,
                                               args=(coord0_start, coord0_stop, coord0_num,
                                                     coord1_start, coord1_stop, coord1_num,
                                                     integration_time, plane,
                                                     meas_params, continue_meas),
                                               name='qafm_fw_bw_line')

            self.threadpool.start(self._worker_thread)

        else:
            # intended only for debugging purposes on main thread
            self.scan_area_qafm_bw_fw_by_line(coord0_start, coord0_stop, coord0_num,
                                              coord1_start, coord1_stop, coord1_num,
                                              integration_time, plane,
                                              meas_params, continue_meas)


# ==============================================================================
#           Quantitative Mode with ESR forward and backward movement
# ==============================================================================

    @staticmethod
    def calc_mag_field_single_res(res_freq, zero_field=2.87e9, e_field=0.0):
        """ Calculate the magnetic field experience by the NV, assuming low 
            mag. field.

        according to:
        https://iopscience.iop.org/article/10.1088/0034-4885/77/5/056503

        """

        gyro_nv = 28e9  # gyromagnetic ratio of the NV in Hz/T (would be 28 GHz/T)

        return np.sqrt(abs(res_freq - zero_field)**2 - e_field**2) / gyro_nv

    @staticmethod
    def calc_mag_field_double_res(res_freq_low, res_freq_high, 
                                  zero_field=2.87e9, e_field=0.0):
        """ Calculate the magnetic field experience by the NV, assuming low 
            mag. field by measuring two frequencies.

        @param float res_freq_low: lower resonance frequency in Hz
        @param float res_freq_high: high resonance frequency in Hz
        @param float zero_field: Zerofield splitting of NV in Hz
        @param float e_field: Estimated electrical field on the NV center

        @return float: the experiences mag. field of the NV in Tesla

        according to:
        https://www.osapublishing.org/josab/fulltext.cfm?uri=josab-33-3-B19&id=335418

        """

        gyro_nv = 28e9  # gyromagnetic ratio of the NV in Hz/T (would be 28 GHz/T)

        return np.sqrt((res_freq_low**2 +res_freq_high**2 - res_freq_low*res_freq_high - zero_field**2)/3 - e_field**2) / gyro_nv

    @staticmethod
    def calc_eps_shift_dual_iso_b(counts1, counts2, freq1, freq2, sigma=None):
        """ Calculate the relative magnetic field in the dual isoB situation, 
            where counts1 and counts2 refer to photon count at lower & upper frequencies respectively.
            For initialization, sigma = FWHM/2;  d = abs(freq2 - freq1)/2.  Ideally, freq1 & freq2
            will be chosen such that d = abs(freq2 - freq1)/2 = sigma/sqrt(3).  This gives the inflection 
            point of the Lorenztian. In short, a centered definition is freq1 = x_0 - d; freq2 = x_0 + d
            Refer to qudi\logic\lorentzianlikemethods.py
                             !      A
                f(x=x_0) = I = -----------
                                pi * sigma


                                            _                            _
                                            |         (sigma)^2          |
                L(x; I, x_0, sigma) =   I * |  --------------------------|
                                            |_ (x_0 - x)^2 + (sigma)^2  _|

        @param float counts1: counts achieved at lower frequency (left of dip) (c/s)
        @param float counts2: counts achieved at upper frequency (right of dip) (c/s)
        @param float freq1: lower frequency (Hz)
        @param float freq2: upper frequency (Hz)
        @param float sigma: width of curve at HWHM.  At FWHM, this is 2*sigma

        @return float mag_field: the relative mag. field of the NV in Tesla
        """
        # protect against /0; ideally counts2 is very large and 1 is ~0
        c2 = counts2.copy()
        c2[c2 == 0] = 1

        ratio = counts1/c2
        d = abs(freq2 - freq1)/2

        if sigma is None:
            sigma = d 

        # at ratio = 1, the field is 0
        mag_field = np.zeros_like(counts1,dtype='float64')

        # using eps1 method, ratio < 1
        s = ratio < 1
        operand = 4*d**2 * ( ratio[s]/ (1-ratio[s])**2) -sigma**2
        operand[operand < 0.0 ] = 0.0
            
        mag_field[s] = np.sqrt(operand) - d * ( (1+ratio[s])/(1-ratio[s]))

        # using eps4 method, ratio > 1 
        s = ratio > 1
        operand = 4*d**2 * ( ratio[s]/ (ratio[s]-1)**2) -sigma**2
        operand[operand < 0.0 ] = 0.0

        mag_field[s] = -np.sqrt(operand) + d * ( (1+ratio[s])/(ratio[s]-1))

        return mag_field



    def scan_area_quanti_qafm_fw_bw_by_point(self, coord0_start, coord0_stop,
                                          coord0_num, coord1_start, coord1_stop,
                                          coord1_num, int_time_afm=0.1,
                                          idle_move_time=0.1, freq_start=2.77e9,
                                          freq_stop=2.97e9, freq_points=100,
                                          esr_count_freq=200,
                                          mw_power=-25, num_esr_runs=30,
                                          optimize_period = 100,
                                          meas_params=['Height(Dac)'],
                                          single_res=True,
                                          continue_meas=False):

        """ QAFM measurement (optical + afm) forward and backward for a scan by point.

        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param int coord0_num: number of points in coord0 direction
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int coord1_num: start coordinate in um
        @param int coord0_num: number of points in coord1 direction
        @param float int_time_afm: integration time for afm operations
        @param float idle_move_time: time for a movement where nothing is measured
        @param float freq_start: start frequency for ESR scan in Hz
        @param float freq_stop: stop frequency for ESR scan in Hz
        @param float freq_points: number of frequencies for ESR scan
        @param float esr_count_freq: The count frequency in ESR scan in Hz
        @param float mw_power: microwave power during scan
        @param int num_esr_runs: number of ESR runs
        @param float optimize_period: time after which an optimization request 
                                      is set

        @param list meas_params: list of possible strings of the measurement
                                 parameter. Have a look at MEAS_PARAMS to see
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list.
        """

        # self.log.info('forward backward scan started.')
        # self.log.info(f'{coord0_start, coord0_stop, coord0_num, coord1_start, coord1_stop, coord1_num, int_time_afm, idle_move_time, freq_start, freq_stop, freq_points, esr_count_freq, mw_power, num_esr_runs, optimize_period, meas_params, single_res, continue_meas}')
        # time.sleep(3)
        # self.sigQuantiScanFinished.emit()
        # return
        
        #self.module_state.lock()
        self.sigQuantiScanStarted.emit()
        plane = 'XY'

        # set up the spm device:
        reverse_meas = False
        self._stop_request = False

        self._optimize_period = optimize_period

        # make the counter for esr ready
        freq_list = np.linspace(freq_start, freq_stop, freq_points, endpoint=True)

        ret_val = self._counter.configure_recorder(
            mode=HWRecorderMode.ESR,
            params={'mw_frequency_list': freq_list,
                    'mw_power': mw_power,
                    'count_frequency': esr_count_freq,
                    'num_meas': num_esr_runs})

        if ret_val < 0:
            self.sigQuantiScanFinished.emit()
            return self._qafm_scan_array

        # return to normal operation
        self.sigHealthCheckStopSkip.emit()

        # scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = int_time_afm
        scan_arr = self.create_scan_leftright2(coord0_start, coord0_stop,
                                                    coord1_start, coord1_stop, coord1_num)

        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                        params= {'line_points': coord0_num,
                                                 'meas_params': meas_params},
                                        scan_style=ScanStyle.POINT) 

        curr_scan_params.insert(0, 'b_field')  # insert the magnetic field (place holder) 
        curr_scan_params.insert(0, 'counts')  # insert the fluorescence parameter

        # this case is for starting a new measurement:
        if (self._spm_line_num == 0) or (not continue_meas):
            self._spm_line_num = 0
            self._afm_meas_duration = 0

            # AFM signal
            self._qafm_scan_array = self.initialize_qafm_scan_array(coord0_start, 
                                                                    coord0_stop, 
                                                                    coord0_num,
                                                                    coord1_start, 
                                                                    coord1_stop, 
                                                                    coord1_num)
            self._scan_counter = 0


            self._esr_scan_array = self.initialize_esr_scan_array(freq_start, 
                                                                  freq_stop, 
                                                                  freq_points,
                                                                  coord0_start, 
                                                                  coord0_stop, 
                                                                  coord0_num,
                                                                  coord1_start, 
                                                                  coord1_stop, 
                                                                  coord1_num)

            # check input values
        ret_val |= self._spm.check_spm_scan_params_by_plane(plane, coord0_start, coord0_stop,
                                                            coord1_start, coord1_stop)
        if ret_val < 1:
            self.sigQuantiScanFinished.emit()
            return self._qafm_scan_array

        start_time_afm_scan = datetime.datetime.now()
        self._curr_scan_params = curr_scan_params

        # save the measurement parameter
        for entry in self._qafm_scan_array:
            self._qafm_scan_array[entry]['params']['Parameters for'] = 'QAFM measurement'
            self._qafm_scan_array[entry]['params']['axis name for coord0'] = 'X'
            self._qafm_scan_array[entry]['params']['axis name for coord1'] = 'Y'
            self._qafm_scan_array[entry]['params']['measurement plane'] = 'XY'
            self._qafm_scan_array[entry]['params']['coord0_start (m)'] = coord0_start
            self._qafm_scan_array[entry]['params']['coord0_stop (m)'] = coord0_stop
            self._qafm_scan_array[entry]['params']['coord0_num (#)'] = coord0_num
            self._qafm_scan_array[entry]['params']['coord1_start (m)'] = coord1_start
            self._qafm_scan_array[entry]['params']['coord1_stop (m)'] = coord1_stop
            self._qafm_scan_array[entry]['params']['coord1_num (#)'] = coord1_num

            self._qafm_scan_array[entry]['params']['ESR Frequency start (Hz)'] = freq_start
            self._qafm_scan_array[entry]['params']['ESR Frequency stop (Hz)'] = freq_stop
            self._qafm_scan_array[entry]['params']['ESR Frequency points (#)'] = freq_points
            self._qafm_scan_array[entry]['params']['ESR Count Frequency (Hz)'] = esr_count_freq
            self._qafm_scan_array[entry]['params']['ESR MW power (dBm)'] = mw_power
            self._qafm_scan_array[entry]['params']['ESR Measurement runs (#)'] = num_esr_runs
            self._qafm_scan_array[entry]['params']['Expect one resonance dip'] = single_res
            self._qafm_scan_array[entry]['params']['Optimize Period (s)'] = optimize_period

            self._qafm_scan_array[entry]['params']['AFM integration time per pixel (s)'] = int_time_afm
            self._qafm_scan_array[entry]['params']['AFM time for idle move (s)'] = idle_move_time
            self._qafm_scan_array[entry]['params']['Measurement parameter list'] = str(curr_scan_params)
            self._qafm_scan_array[entry]['params']['Measurement start'] = start_time_afm_scan.isoformat()

        for line_num, scan_coords in enumerate(scan_arr):

            # for a continue measurement event, skip the first measurements
            # until one has reached the desired line, then continue from there.
            if line_num < self._spm_line_num:
                continue

            num_params = len(curr_scan_params)

            self._spm.configure_line(line_corr0_start=scan_coords[0],
                                     line_corr0_stop=scan_coords[1],
                                     line_corr1_start=scan_coords[2],
                                     line_corr1_stop=scan_coords[3],
                                     time_forward=scan_speed_per_line,
                                     time_back=idle_move_time)

            # -1 otherwise it would be more than coord0_num points, since first one is counted too.
            x_step = (scan_coords[1] - scan_coords[0]) / (coord0_num - 1)

            self._afm_pos = {'x': scan_coords[0], 'y': scan_coords[2]}

            self._spm.scan_point()  # these are points to throw away
            self.sigNewAFMPos.emit(self._afm_pos)

            # if len(vals) > 0:
            #    self.log.error("The scanner range was not correctly set up!")

            last_elem = list(range(coord0_num))[-1]
            for index in range(coord0_num):

                # first two entries are counts and b_field, remaining entries are the scan parameter
                self._scan_point = np.zeros(num_params) 

                # at first the AFM parameter
                self._scan_point[2:] = self._spm.scan_point()  
                
                # obtain ESR measurement
                self._counter.start_recorder()
                esr_meas = self._counter.get_measurements()[:, 2:]

                esr_meas_mean = esr_meas.mean(axis=0)
                esr_meas_std = esr_meas.std(axis=0)
                
                mag_field = 0.0

                try:

                    # just for safety reasons (allocate already some data for it)
                    esr_data_fit = np.zeros(len(esr_meas_mean))

                    # perform analysis and fit for the measured data:
                    if single_res:
                        res = self._fitlogic.make_lorentzian_fit(freq_list,
                                                                 esr_meas_mean,
                                                                 estimator=self._fitlogic.estimate_lorentzian_dip)
                        esr_data_fit = res.best_fit

                        res_freq = res.params['center'].value
                        #FIXME: use Tesla not Gauss, right not, this is just for display purpose
                        mag_field =  self.calc_mag_field_single_res(res_freq, 
                                                                    self.ZFS, 
                                                                    self.E_FIELD) * 10000


                    else:    
                        res = self._fitlogic.make_lorentziandouble_fit(freq_list, 
                                                                       esr_meas_mean,
                                                                       estimator=self._fitlogic.estimate_lorentziandouble_dip)
                        esr_data_fit = res.best_fit

                        res_freq_low = res.params['l0_center'].value
                        res_freq_high = res.params['l1_center'].value
                        #FIXME: use Tesla not Gauss, right not, this is just for display purpose
                        mag_field = self.calc_mag_field_double_res(res_freq_low,
                                                              res_freq_high, 
                                                              self.ZFS, 
                                                              self.E_FIELD)* 10000

                    fluorescence = res.params['offset']

                except:
                    self.log.warning(f'Fit was not working at line {line_num//2} and index {index}. Data needs to be post-processed.')

                # here the counts are saved:
                self._scan_point[0] = fluorescence
                # here the b_field is saved:
                self._scan_point[1] = mag_field
                
                if reverse_meas:

                    for param_index, param_name in enumerate(curr_scan_params):
                        name = f'{param_name}_bw'

                        self._qafm_scan_array[name]['data'][line_num // 2][coord0_num-index-1] = self._scan_point[param_index] * self._qafm_scan_array[name]['scale_fac']

                    # insert number from the back
                    self._esr_scan_array['esr_bw']['data'][line_num// 2][coord0_num-index-1] = esr_meas_mean
                    self._esr_scan_array['esr_bw']['data_std'][line_num//2][coord0_num-index-1] = esr_meas_std

                    self._esr_scan_array['esr_bw']['data_fit'][line_num//2][coord0_num-index-1] = esr_data_fit
 
                else:

                    for param_index, param_name in enumerate(curr_scan_params):
                        name = f'{param_name}_fw'

                        self._qafm_scan_array[name]['data'][line_num // 2][index] = self._scan_point[param_index] * self._qafm_scan_array[name]['scale_fac']

                    self._esr_scan_array['esr_fw']['data'][line_num//2][index] = esr_meas_mean
                    self._esr_scan_array['esr_fw']['data_std'][line_num//2][index] = esr_meas_std

                    self._esr_scan_array['esr_fw']['data_fit'][line_num//2][coord0_num-index-1] = esr_data_fit


                self.log.info(f'Point: {line_num * coord0_num + index + 1} out of {coord0_num*coord1_num*2}, {(line_num * coord0_num + index +1)/(coord0_num*coord1_num*2) * 100:.2f}% finished.')

                if index != last_elem:
                    self._afm_pos['x'] += x_step
                    self.sigNewAFMPos.emit({'x': self._afm_pos['x']})

                self._scan_counter += 1

                # emit a signal at every point, so that update can happen in real time.
                self.sigQAFMLineScanFinished.emit()

                # remove possibility to stop during line scan.
                if self._stop_request:
                   break

            # self.log.info(f'Line number {line_num} completed.')
            self.log.info(f'Line number {line_num} completed.')

            # store the current line number
            self._spm_line_num = line_num

            # break irrespective of the direction of the scan
            if self._stop_request:
                break

            # perform optimization always after line finishes
            if self.get_optimize_request():

                self.log.info('Enter optimization.')
                self.sigHealthCheckStartSkip.emit()
                time.sleep(2)

                self._counter.stop_measurement()
                self._counter.configure_recorder(mode=HWRecorderMode.PIXELCLOCK,
                                                 params={'mw_frequency': np.mean(freq_list),
                                                         'num_meas': coord0_num})

                self._spm.finish_scan()

                self.default_optimize()
                _, _, _ = self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                                      params= {'line_points': coord0_num,
                                                               'meas_params': meas_params},
                                                      scan_style=ScanStyle.LINE) 
 
                self._counter.configure_recorder(
                    mode=HWRecorderMode.ESR,
                    params={'mw_frequency_list': freq_list,
                            'mw_power': mw_power,
                            'count_frequency': esr_count_freq,
                            'num_meas': num_esr_runs } )

                time.sleep(2)
                self.sigHealthCheckStopSkip.emit()

        stop_time_afm_scan = datetime.datetime.now()
        self._afm_meas_duration = self._afm_meas_duration + (stop_time_afm_scan - start_time_afm_scan).total_seconds()

        if line_num == self._spm_line_num:
            self.log.info(f'Scan finished at {int(self._afm_meas_duration)}s. Yeehaa!')
        else:
            self.log.info(f'Scan stopped at {int(self._afm_meas_duration)}s.')

        for entry in self._qafm_scan_array:
            self._qafm_scan_array[entry]['params']['Measurement stop'] = stop_time_afm_scan.isoformat()
            self._qafm_scan_array[entry]['params']['Total measurement time (s)'] = self._afm_meas_duration

        # clean up the spm
        self._spm.finish_scan()
        #self.module_state.unlock()
        self.sigQuantiScanFinished.emit()

        return self._qafm_scan_array

    def start_scan_area_quanti_qafm_fw_bw_by_point(self, coord0_start, coord0_stop,
                                              coord0_num, coord1_start, coord1_stop,
                                              coord1_num, int_time_afm=0.1,
                                              idle_move_time=0.1, freq_start=2.77e9,
                                              freq_stop=2.97e9, freq_points=100,
                                              esr_count_freq=200,
                                              mw_power=-25, num_esr_runs=30,
                                              optimize_period=100,
                                              meas_params=['Height(Dac)'],
                                              single_res=True,
                                              continue_meas=False):

        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return
           
        self._health_check.setup(interval=20,                                       # perform check every interval (s)
                                 default_delta_t=int_time_afm * num_esr_runs *1.5,  # minimum time to expect between updates
                                 check_function=self._counter._dev.ctrl.isBusy,     # op function to check health 
                                 connect_start=[],                                  # start triggered manually
                                 connect_update=[self.sigQuantiLineFinished,        # signals which will trigger update
                                                 self.sigNewAFMPos],
                                 connect_stop=[self.sigQuantiScanFinished],         # signal to trigger stop of health check
                                 connect_opt_start=[self.sigHealthCheckStartSkip],   # signal to note that optimizer has started 
                                 connect_opt_stop=[self.sigHealthCheckStopSkip],    # signal to note that optimizer has finished
                                 log=self.log
                                )

        self._health_check.start_timer(arm=True)
        self.sigHealthCheckStartSkip.emit()

        if self._USE_THREADED:
            self._worker_thread = WorkerThread(target=self.scan_area_quanti_qafm_fw_bw_by_point,
                                               args=(coord0_start, coord0_stop,
                                                     coord0_num, coord1_start, coord1_stop,
                                                     coord1_num, int_time_afm,
                                                     idle_move_time, freq_start,
                                                     freq_stop, freq_points,
                                                     esr_count_freq,
                                                     mw_power, num_esr_runs,
                                                     optimize_period,
                                                     meas_params,
                                                     single_res,
                                                     continue_meas),
                                               name='quanti_thread')
            self.threadpool.start(self._worker_thread)

        else:
            self.scan_area_quanti_qafm_fw_bw_by_point(coord0_start, coord0_stop,
                                                     coord0_num, coord1_start, coord1_stop,
                                                     coord1_num, int_time_afm,
                                                     idle_move_time, freq_start,
                                                     freq_stop, freq_points,
                                                     esr_count_freq,
                                                     mw_power, num_esr_runs,
                                                     optimize_period,
                                                     meas_params,
                                                     single_res,
                                                     continue_meas)

    # ==============================================================================
    #           Quantitative Mode with ESR just forward movement
    # ==============================================================================

    def scan_area_quanti_qafm_fw_by_point(self, coord0_start, coord0_stop,
                                             coord0_num, coord1_start, coord1_stop,
                                             coord1_num, int_time_afm=0.1,
                                             idle_move_time=0.1, freq_start=2.77e9,
                                             freq_stop=2.97e9, freq_points=100,
                                             esr_count_freq=200,
                                             mw_power=-25, num_esr_runs=30,
                                             optimize_period=100,
                                             meas_params=['Height(Dac)'],
                                             single_res=True,
                                             continue_meas=False):

        """ QAFM measurement (optical + afm) snake movement for a scan by point.

        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param int coord0_num: number of points in coord0 direction
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int coord1_num: start coordinate in um
        @param int coord0_num: number of points in coord1 direction
        @param float int_time_afm: integration time for afm operations
        @param float idle_move_time: time for a movement where nothing is measured
        @param float freq_start: start frequency for ESR scan in Hz
        @param float freq_stop: stop frequency for ESR scan in Hz
        @param float freq_points: number of frequencies for ESR scan
        @param count_freq: The count frequency in ESR scan in Hz
        @param float mw_power: microwave power during scan
        @param int num_esr_runs: number of ESR runs

        @param list meas_params: list of possible strings of the measurement
                                 parameter. Have a look at MEAS_PARAMS to see
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list.
        """

        # self.log.info('forwards scan started.')
        # self.log.info(f'{coord0_start, coord0_stop, coord0_num, coord1_start, coord1_stop, coord1_num, int_time_afm, idle_move_time, freq_start, freq_stop, freq_points, esr_count_freq, mw_power, num_esr_runs, optimize_period, meas_params, single_res, continue_meas}')
        # time.sleep(3)
        # self.sigQuantiScanFinished.emit()
        # return

        # self.module_state.lock()
        self.sigQuantiScanStarted.emit()
        plane = 'XY'

        # set up the spm device:
        ## reverse_meas = False
        self._stop_request = False

        self._optimize_period = optimize_period

        # make the counter for esr ready
        freq_list = np.linspace(freq_start, freq_stop, freq_points, endpoint=True)
        
        ret_val = self._counter.configure_recorder(
            mode=HWRecorderMode.ESR,
            params={'mw_frequency_list': freq_list,
                    'num_meas': num_esr_runs } )
                    
        self._mw.set_list(freq_list, mw_power)
                
        self._pulser.load_swabian_sequence(self._make_pulse_sequence(HWRecorderMode.ESR, 1/esr_count_freq, freq_points, num_esr_runs))
        self._pulser.pulser_on(trigger=True, n=1)

        if ret_val < 0:
            self.sigQuantiScanFinished.emit()
            return self._qafm_scan_array

        # return to normal operation
        self.sigHealthCheckStopSkip.emit()

        # scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = int_time_afm

        scan_arr = self.create_scan_leftright(coord0_start, coord0_stop,
                                              coord1_start, coord1_stop, coord1_num)
        # scan_arr = self._spm.create_scan_snake(coord0_start, coord0_stop,
        #                                        coord1_start, coord1_stop, coord1_num)

        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                        params= {'line_points': coord0_num,
                                                 'meas_params': meas_params},
                                        scan_style=ScanStyle.POINT) 

        curr_scan_params.insert(0, 'b_field')  # insert the fluorescence parameter
        curr_scan_params.insert(0, 'counts')  # insert the fluorescence parameter

        # this case is for starting a new measurement:
        if (self._spm_line_num == 0) or (not continue_meas):
            self._spm_line_num = 0
            self._afm_meas_duration = 0

            # AFM signal
            self._qafm_scan_array = self.initialize_qafm_scan_array(coord0_start, coord0_stop, coord0_num,
                                                                    coord1_start, coord1_stop, coord1_num)
            self._scan_counter = 0

            self._esr_scan_array = self.initialize_esr_scan_array(freq_start, freq_stop, freq_points,
                                                                  coord0_start, coord0_stop, 
                                                                  coord0_num,
                                                                  coord1_start, coord1_stop, 
                                                                  coord1_num)

        # check input values
        ret_val |= self._spm.check_spm_scan_params_by_plane(plane, coord0_start, coord0_stop,
                                                            coord1_start, coord1_stop)
        if ret_val < 1:
            self.sigQuantiScanFinished.emit()
            return self._qafm_scan_array

        start_time_afm_scan = datetime.datetime.now()
        self._curr_scan_params = curr_scan_params

        # save the measurement parameter
        for entry in self._qafm_scan_array:
            self._qafm_scan_array[entry]['params']['Parameters for'] = 'QAFM measurement'
            self._qafm_scan_array[entry]['params']['axis name for coord0'] = 'X'
            self._qafm_scan_array[entry]['params']['axis name for coord1'] = 'Y'
            self._qafm_scan_array[entry]['params']['measurement plane'] = 'XY'
            self._qafm_scan_array[entry]['params']['coord0_start (m)'] = coord0_start
            self._qafm_scan_array[entry]['params']['coord0_stop (m)'] = coord0_stop
            self._qafm_scan_array[entry]['params']['coord0_num (#)'] = coord0_num
            self._qafm_scan_array[entry]['params']['coord1_start (m)'] = coord1_start
            self._qafm_scan_array[entry]['params']['coord1_stop (m)'] = coord1_stop
            self._qafm_scan_array[entry]['params']['coord1_num (#)'] = coord1_num

            self._qafm_scan_array[entry]['params']['ESR Frequency start (Hz)'] = freq_start
            self._qafm_scan_array[entry]['params']['ESR Frequency stop (Hz)'] = freq_stop
            self._qafm_scan_array[entry]['params']['ESR Frequency points (#)'] = freq_points
            self._qafm_scan_array[entry]['params']['ESR Count Frequency (Hz)'] = esr_count_freq
            self._qafm_scan_array[entry]['params']['ESR MW power (dBm)'] = mw_power
            self._qafm_scan_array[entry]['params']['ESR Measurement runs (#)'] = num_esr_runs
            self._qafm_scan_array[entry]['params']['Expect one resonance dip'] = single_res
            self._qafm_scan_array[entry]['params']['Optimize Period (s)'] = optimize_period

            self._qafm_scan_array[entry]['params']['AFM integration time per pixel (s)'] = int_time_afm
            self._qafm_scan_array[entry]['params']['AFM time for idle move (s)'] = idle_move_time
            self._qafm_scan_array[entry]['params']['Measurement parameter list'] = str(curr_scan_params)
            self._qafm_scan_array[entry]['params']['Measurement start'] = start_time_afm_scan.isoformat()

        for line_num, scan_coords in enumerate(scan_arr):

            # for a continue measurement event, skip the first measurements
            # until one has reached the desired line, then continue from there.
            if line_num < self._spm_line_num:

                # take care of the proper order of the data
                # if line_num%2 == 0:
                #     # i.e. next measurement must be in reversed order
                #     reverse_meas = True
                # else:
                #     reverse_meas = False
                continue

            num_params = len(curr_scan_params)

            self.set_afm_pos({'x': scan_coords[0], 'y': scan_coords[2]})
            time.sleep(1)

            self._spm.configure_line(line_corr0_start=scan_coords[0],
                                     line_corr0_stop=scan_coords[1],
                                     line_corr1_start=scan_coords[2],
                                     line_corr1_stop=scan_coords[3],
                                     time_forward=scan_speed_per_line,
                                     time_back=idle_move_time)
            
            self._mw.list_on()

            # -1 otherwise it would be more than coord0_num points, since first one is counted too.
            x_step = (scan_coords[1] - scan_coords[0]) / (coord0_num - 1)

            self._afm_pos = {'x': scan_coords[0], 'y': scan_coords[2]}

            # self._spm.scan_point()  # these are points to throw away
            self.sigNewAFMPos.emit(self._afm_pos)

            # if len(vals) > 0:
            #    self.log.error("The scanner range was not correctly set up!")

            last_elem = list(range(coord0_num))[-1]

            for index in range(coord0_num):

                # first two entries are counts and b_field, remaining entries are the scan parameter
                self._scan_point = np.zeros(num_params) 

                # at first the AFM parameter
                # arm recorder
                self._counter.start_recorder(arm=True)

                self._debug = self._spm.scan_point()
                self._scan_point[2:] = self._debug 
                
                # obtain ESR measurement
                esr_meas = self._counter.get_measurements()[:, 2:]

                esr_meas_mean = esr_meas.mean(axis=0)
                esr_meas_std = esr_meas.std(axis=0)
                
                mag_field = 0.0
                fluorescence = 0.0

                try:

                    # just for safety reasons (allocate already some data for it)
                    esr_data_fit = np.zeros(len(esr_meas_mean))

                    # perform analysis and fit for the measured data:
                    if single_res:
                        res = self._fitlogic.make_lorentzian_fit(freq_list,
                                                                 esr_meas_mean,
                                                                 estimator=self._fitlogic.estimate_lorentzian_dip)

                        esr_data_fit = res.best_fit

                        res_freq = res.params['center'].value
                        #FIXME: use Tesla not Gauss, right not, this is just for display purpose
                        mag_field =  self.calc_mag_field_single_res(res_freq, 
                                                                    self.ZFS, 
                                                                    self.E_FIELD) * 10000


                    else:    
                        res = self._fitlogic.make_lorentziandouble_fit(freq_list, 
                                                                       esr_meas_mean,
                                                                       estimator=self._fitlogic.estimate_lorentziandouble_dip)

                        esr_data_fit = res.best_fit

                        res_freq_low = res.params['l0_center'].value
                        res_freq_high = res.params['l1_center'].value
                        #FIXME: use Tesla not Gauss, right not, this is just for display purpose
                        mag_field = self.calc_mag_field_double_res(res_freq_low,
                                                                   res_freq_high,
                                                                   self.ZFS,
                                                                   self.E_FIELD) * 10000

                    fluorescence = res.params['offset'].value

                except:
                    self.log.warning(f'Fit was not working at line {line_num} and index {index}. Data needs to be post-processed.')

                # here the counts are saved:
                self._scan_point[0] = fluorescence
                # here the b_field is saved:
                self._scan_point[1] = mag_field

                # save measured data in array:
                for param_index, param_name in enumerate(curr_scan_params):
                    name = f'{param_name}_fw'

                    self._qafm_scan_array[name]['data'][line_num][index] = self._scan_point[param_index] * self._qafm_scan_array[name]['scale_fac']

                self._esr_scan_array['esr_fw']['data'][line_num][index] = esr_meas_mean
                self._esr_scan_array['esr_fw']['data_std'][line_num][index] = esr_meas_std
                self._esr_scan_array['esr_fw']['data_fit'][line_num][index] = esr_data_fit

                # For debugging, display status text:
                progress_text = f'Point: {line_num * coord0_num + index + 1} out of {coord0_num * coord1_num }, {(line_num * coord0_num + index + 1) / (coord0_num * coord1_num ) * 100:.2f}% finished.'
                print(progress_text)
                self.log.info(progress_text)

                # track current AFM position:
                if index != last_elem:
                    self._afm_pos['x'] += x_step
                    self.sigNewAFMPos.emit({'x': self._afm_pos['x']})

                self._scan_counter += 1

                # emit a signal at every point, so that update can happen in real time.
                self.sigQAFMLineScanFinished.emit()
                self._mw.reset_listpos()

                # possibility to stop during line scan.
                if self._stop_request:
                    break

            self.log.info(f'Line number {line_num} completed.')
            print(f'Line number {line_num} completed.')

            self.sigQAFMLineScanFinished.emit()   # this triggers repainting of the line
            self.sigQuantiLineFinished.emit()     # this signals line is complete, return to new line

            # store the current line number
            self._spm_line_num = line_num

            if self._stop_request:
                break

            # perform optimization always after line finishes
            if self.get_optimize_request():

                self.log.info('Enter optimization.')
                self.sigHealthCheckStartSkip.emit()
                time.sleep(2)

                self._counter.configure_recorder(mode=HWRecorderMode.PIXELCLOCK,
                                                 params={'mw_frequency': self._freq1_iso_b_frequency,
                                                         'num_meas': coord0_num})
                self._spm.finish_scan()

                time.sleep(1)

                self.default_optimize()
                _, _, _ = self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                                      params= {'line_points': coord0_num,
                                                               'meas_params': meas_params},
                                                      scan_style=ScanStyle.LINE) 

                self._counter.configure_recorder(
                    mode=HWRecorderMode.ESR,
                    params={'mw_frequency_list': freq_list,
                            'mw_power': mw_power,
                            'count_frequency': esr_count_freq,
                            'num_meas': num_esr_runs } )
                time.sleep(2)
                self.sigHealthCheckStopSkip.emit()

            self.log.info('Pass optimization.')

        stop_time_afm_scan = datetime.datetime.now()
        self._afm_meas_duration = self._afm_meas_duration + (
                    stop_time_afm_scan - start_time_afm_scan).total_seconds()

        if line_num == self._spm_line_num:
            self.log.info(f'Scan finished at {int(self._afm_meas_duration)}s. Yeehaa!')
        else:
            self.log.info(f'Scan stopped at {int(self._afm_meas_duration)}s.')

        for entry in self._qafm_scan_array:
            self._qafm_scan_array[entry]['params']['Measurement stop'] = stop_time_afm_scan.isoformat()
            self._qafm_scan_array[entry]['params']['Total measurement time (s)'] = self._afm_meas_duration

        # clean up the spm
        self._spm.finish_scan()
        self._mw.off()
        self._counter.stop_measurement()
        # self.module_state.unlock()
        self.sigQuantiScanFinished.emit()

        return self._qafm_scan_array

    def start_scan_area_quanti_qafm_fw_by_point(self, coord0_start, coord0_stop,
                                                   coord0_num, coord1_start, coord1_stop,
                                                   coord1_num, int_time_afm=0.1,
                                                   idle_move_time=0.1, freq_start=2.77e9,
                                                   freq_stop=2.97e9, freq_points=100,
                                                   esr_count_freq=200,
                                                   mw_power=-25, num_esr_runs=30,
                                                   optimize_period=100,
                                                   meas_params=['Height(Dac)'],
                                                   single_res=True,
                                                   continue_meas=False):

        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return
        
        self._health_check.setup(interval=20,                                       # perform check every interval (s)
                                 default_delta_t=int_time_afm * num_esr_runs *1.5,  # minimum time to expect between updates
                                 check_function=self._counter._dev.ctrl.isBusy,     # op function to check health 
                                 connect_start=[],                                  # start triggered manually
                                 connect_update=[self.sigQuantiLineFinished,        # signals which will trigger update
                                                 self.sigNewAFMPos],
                                 connect_stop=[self.sigQuantiScanFinished],         # signal to trigger stop of health check
                                 connect_opt_start=[self.sigHealthCheckStartSkip],   # signal to note that optimizer has started 
                                 connect_opt_stop=[self.sigHealthCheckStopSkip],    # signal to note that optimizer has finished
                                 log=self.log
                                )

        self._health_check.start_timer(arm=True)
        self.sigHealthCheckStartSkip.emit()

        if self._USE_THREADED:
            self._worker_thread = WorkerThread(target=self.scan_area_quanti_qafm_fw_by_point,
                                               args=(coord0_start, coord0_stop,
                                                     coord0_num, coord1_start, coord1_stop,
                                                     coord1_num, int_time_afm,
                                                     idle_move_time, freq_start,
                                                     freq_stop, freq_points,
                                                     esr_count_freq,
                                                     mw_power, num_esr_runs,
                                                     optimize_period,
                                                     meas_params,
                                                     single_res,
                                                     continue_meas),
                                               name='qanti_thread')
            self.threadpool.start(self._worker_thread)

        else:
            self.scan_area_quanti_qafm_fw_by_point(coord0_start, coord0_stop,
                                                   coord0_num, coord1_start, coord1_stop,
                                                   coord1_num, int_time_afm,
                                                   idle_move_time, freq_start,
                                                   freq_stop, freq_points,
                                                   esr_count_freq,
                                                   mw_power, num_esr_runs,
                                                   optimize_period,
                                                   meas_params,
                                                   single_res,
                                                   continue_meas)

# ==============================================================================
#             forward and backward QAFM (optical + afm) scan
# ==============================================================================

# ==============================================================================
# pure optical measurement, by line
# ==============================================================================

    def scan_area_obj_by_line(self, coord0_start, coord0_stop, coord0_num,
                               coord1_start, coord1_stop, coord1_num,
                               integration_time, plane='X2Y2',
                               continue_meas=False):

        """ Tip scanning measurement (optical) forward for a scan by line.

        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int coord0_num: number of points in x direction
        @param int coord1_num: number of points in y direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                        'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement
                                 parameter. Have a look at MEAS_PARAMS to see
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list.
        """
        if integration_time is None:
            integration_time = self._sg_int_time_obj_scan

        self.module_state.lock()

        coord0, coord1 = (0.0, 0.0)

        mapping = {'coord0': 0}

        if plane == 'X2Y2':
            arr_name = 'obj_xy'
            scanner_mode = ScannerMode.OBJECTIVE_XY
            mapping = {'coord0': 0, 'coord1': 1, 'fixed': 2}
        elif plane == 'X2Z2':
            arr_name = 'obj_xz'
            scanner_mode = ScannerMode.OBJECTIVE_XZ
            mapping = {'coord0': 0, 'fixed': 1, 'coord1': 2, }
        elif plane == 'Y2Z2':
            arr_name = 'obj_yz'
            scanner_mode = ScannerMode.OBJECTIVE_YZ
            mapping = {'fixed': 0, 'coord0': 1, 'coord1': 2}

        # set up the spm device:
        reverse_meas = False
        self._stop_request = False

        # time in which the stage is just moving without measuring
        time_idle_move = self._sg_idle_move_scan_obj

        mode, _ = self._counter.get_current_device_mode()
        ret_val = self._counter.configure_recorder(mode=HWRecorderMode.PIXELCLOCK,
                                                   params={'mw_frequency': self._freq1_iso_b_frequency,
                                                           'num_meas': coord0_num})
        # self._pulser.load_swabian_sequence(self._make_pulse_sequence(HWRecorderMode.PIXELCLOCK, integration_time))

        if ret_val < 0:
            self.module_state.unlock()
            self.sigObjScanFinished.emit()
            return self._obj_scan_array

        # scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = integration_time * coord0_num

        # FIXME: Uncomment for snake like scan, however, not recommended!!!
        #       As it will distort the picture.
        # scan_arr = self._spm.create_scan_snake(coord0_start, coord0_stop,
        #                                        coord1_start, coord1_stop,
        #                                        coord1_num)

        scan_arr = self.create_scan_leftright(coord0_start, coord0_stop,
                                              coord1_start, coord1_stop,
                                              coord1_num)


        # FIXME: check whether the number of parameters are required and whether they are set correctly.
        # self._spm._params_per_point = len(names_buffers)
        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=scanner_mode,
                                        params= {'line_points': coord0_num },
                                        scan_style=ScanStyle.LINE) 


        curr_scan_params.insert(0, 'counts')  # insert the fluorescence parameter

        self._spm.set_ext_trigger(True)


        # FIXME: Implement an better initialization procedure
        # FIXME: Create a better naming for the matrices

        if (self._spm_line_num == 0) or (not continue_meas):
            self._spm_line_num = 0
            self._obj_meas_duration = 0

            self._obj_scan_array = self.initialize_obj_scan_array(arr_name,
                                                                  coord0_start,
                                                                  coord0_stop,
                                                                  coord0_num,
                                                                  coord1_start,
                                                                  coord1_stop,
                                                                  coord1_num)

            self._scan_counter = 0

            # check input values
        ret_val |= self._spm.check_spm_scan_params_by_plane(plane,
                                                            coord0_start,
                                                            coord0_stop,
                                                            coord1_start,
                                                            coord1_stop)

        if ret_val < 1:
            return self._obj_scan_array

        start_time_obj_scan = datetime.datetime.now()
        num_params = len(curr_scan_params)

        # save the measurement parameter
        self._obj_scan_array[arr_name]['params']['Parameters for'] = 'Objective measurement'
        self._obj_scan_array[arr_name]['params']['axis name for coord0'] = arr_name[-2].upper()
        self._obj_scan_array[arr_name]['params']['axis name for coord1'] = arr_name[-1].upper()
        self._obj_scan_array[arr_name]['params']['measurement plane'] = arr_name[-2:].upper()
        self._obj_scan_array[arr_name]['params']['coord0_start (m)'] = coord0_start
        self._obj_scan_array[arr_name]['params']['coord0_stop (m)'] = coord0_stop
        self._obj_scan_array[arr_name]['params']['coord0_num (#)'] = coord0_num
        self._obj_scan_array[arr_name]['params']['coord1_start (m)'] = coord1_start
        self._obj_scan_array[arr_name]['params']['coord1_stop (m)'] = coord1_stop
        self._obj_scan_array[arr_name]['params']['coord1_num (#)'] = coord1_num
        self._obj_scan_array[arr_name]['params']['Scan speed per line (s)'] = scan_speed_per_line
        self._obj_scan_array[arr_name]['params']['Idle movement speed (s)'] = time_idle_move

        self._obj_scan_array[arr_name]['params']['integration time per pixel (s)'] = integration_time
        self._obj_scan_array[arr_name]['params']['Measurement start'] = start_time_obj_scan.isoformat()


        for line_num, scan_coords in enumerate(scan_arr):

            # for a continue measurement event, skip the first measurements
            # until one has reached the desired line, then continue from there.
            if line_num < self._spm_line_num:
                continue

            # optical signal only
            self._obj_scan_line = np.zeros(num_params * coord0_num)

            self._spm.configure_line(line_corr0_start=scan_coords[0],
                                     line_corr0_stop=scan_coords[1],
                                     line_corr1_start=scan_coords[2],
                                     line_corr1_stop=scan_coords[3],
                                     time_forward=scan_speed_per_line,
                                     time_back=time_idle_move)

            # self._counter.start_recorder(arm=True)
            self._spm.scan_line()

            #FIXME: Uncomment for snake like scan, however, not recommended!!!
            #       As it will distort the picture.
            # if line_num % 2 == 0:
            #     self._obj_scan_array[arr_name]['data'][line_num] = self._counter.get_measurement() / integration_time
            # else:
            #     self._obj_scan_array[arr_name]['data'][line_num] = self._counter.get_measurement()[::-1] / integration_time

            counts, int_time = self._spm.get_measurements(),  None

            if int_time is None or np.any(np.isclose(int_time,0,atol=1e-12)):
                int_time = integration_time

            self._obj_scan_array[arr_name]['data'][line_num] = counts / int_time 
            self.sigObjLineScanFinished.emit(arr_name)

            # enable the break only if next scan goes into forward movement
            if self._stop_request:
                break

            # store the current line number
            self._spm_line_num = line_num
            #print(f'Line number {line_num} completed.')

        stop_time_obj_scan = datetime.datetime.now()
        self._obj_meas_duration = self._obj_meas_duration + (
                    stop_time_obj_scan - start_time_obj_scan).total_seconds()

        if line_num == self._spm_line_num:
            self.log.info(f'Objective scan finished after {int(self._obj_meas_duration)}s. Yeehaa!')
        else:
            self.log.info(f'Objective scan stopped after {int(self._obj_meas_duration)}s.')

        self._obj_scan_array[arr_name]['params']['Measurement stop'] = stop_time_obj_scan.isoformat()
        self._obj_scan_array[arr_name]['params']['Total measurement time (s)'] = self._obj_meas_duration

        # clean up the spm
        self._spm.finish_scan()
        # clean up the counter
        # self._counter.stop_measurement()
        if self.module_state()!='idle':
            self.module_state.unlock()
        self.sigObjScanFinished.emit()

        return self._obj_scan_array


    def start_scan_area_obj_by_line(self, coord0_start=48*1e-6, coord0_stop=53*1e-6, coord0_num=40,
                                     coord1_start=47*1e-6, coord1_stop=52*1e-6, coord1_num=40,
                                     integration_time=None, plane='X2Y2',
                                     continue_meas=False):

        if self._USE_THREADED:
            if self.check_thread_active():
                self.log.error("A measurement is currently running, stop it first!")
                return

            self._worker_thread = WorkerThread(target=self.scan_area_obj_by_line,
                                               args=(coord0_start, coord0_stop, coord0_num,
                                                     coord1_start, coord1_stop, coord1_num,
                                                     integration_time,
                                                     plane, continue_meas),
                                               name='obj_scan')
            self.threadpool.start(self._worker_thread)

        else:
            # for debugging purposes on the main thread
            self.scan_area_obj_by_line(coord0_start, coord0_stop, coord0_num,
                                       coord1_start, coord1_stop, coord1_num,
                                       integration_time, plane, continue_meas)


# ==============================================================================
# Optimizer scan an area by point
# ==============================================================================

    def scan_area_obj_by_line_opti(self, coord0_start, coord0_stop, coord0_num,
                                    coord1_start, coord1_stop, coord1_num,
                                    integration_time):

        """ Measurement method for a scan by line, with just one linescan

        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int coord0_num: number of points in x direction
        @param int coord1_num: number of points in y direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                            'XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement
                                 parameter. Have a look at MEAS_PARAMS to see
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list.
        """

        # FIXME: implement general optimizer for all the planes
        plane = 'X2Y2'

        opti_name = 'opti_xy'

        start_time_opti = datetime.datetime.now()
        self._opti_meas_duration = 0

        # set up the spm device:
        self._stop_request = False
        # scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = integration_time * coord0_num

        #FIXME: Make this a setting value
        time_idle_move = 0.1 # in seconds, time in which the stage is just
                             # moving without measuring

        ret_val = self._counter.configure_recorder(
            mode=HWRecorderMode.PIXELCLOCK, 
            params={'mw_frequency': self._freq1_iso_b_frequency,
                    'num_meas': coord0_num})

        if ret_val < 0:
            self.sigObjScanFinished.emit()
            self._stop_request = True   # Set a stop request to stop a false measurement!
            return self._opti_scan_array


        scan_arr = self.create_scan_leftright(coord0_start, coord0_stop,
                                              coord1_start, coord1_stop,
                                              coord1_num)

        #TODO: implement the scan line mode
        ret_val, _, _ = self._spm.configure_scanner(mode=ScannerMode.OBJECTIVE_XY,
                                                    params= {'line_points': coord0_num },
                                                    scan_style=ScanStyle.LINE) 
        self._spm.set_ext_trigger(True)

        self._opti_scan_array = self.initialize_opti_xy_scan_array(coord0_start,
                                                                   coord0_stop,
                                                                   coord0_num,
                                                                   coord1_start,
                                                                   coord1_stop,
                                                                   coord1_num)
        # check input values
        # ret_val |= self._spm.check_spm_scan_params_by_plane(plane,
        #                                                     coord0_start,
        #                                                     coord0_stop,
        #                                                     coord1_start,
        #                                                     coord1_stop)

        if ret_val < 1:
            return self._opti_scan_array

        self._opti_scan_array[opti_name]['params']['Parameters for'] = 'Optimize XY measurement'
        self._opti_scan_array[opti_name]['params']['axis name for coord0'] = opti_name[-2].upper()
        self._opti_scan_array[opti_name]['params']['axis name for coord1'] = opti_name[-1].upper()
        self._opti_scan_array[opti_name]['params']['measurement plane'] = opti_name[-2:].upper()
        self._opti_scan_array[opti_name]['params']['coord0_start (m)'] = coord0_start
        self._opti_scan_array[opti_name]['params']['coord0_stop (m)'] = coord0_stop
        self._opti_scan_array[opti_name]['params']['coord0_num (#)'] = coord0_num
        self._opti_scan_array[opti_name]['params']['coord1_start (m)'] = coord1_start
        self._opti_scan_array[opti_name]['params']['coord1_stop (m)'] = coord1_stop
        self._opti_scan_array[opti_name]['params']['coord1_num (#)'] = coord1_num
        self._opti_scan_array[opti_name]['params']['Scan speed per line (s)'] = scan_speed_per_line
        self._opti_scan_array[opti_name]['params']['Idle movement speed (s)'] = time_idle_move

        self._opti_scan_array[opti_name]['params']['integration time per pixel (s)'] = integration_time
        self._opti_scan_array[opti_name]['params']['Measurement start'] = start_time_opti.isoformat()

        self._scan_counter = 0

        for line_num, scan_coords in enumerate(scan_arr):

            # APD signal
            self._opti_scan_line = np.zeros(coord0_num)

            self._spm.configure_line(line_corr0_start=scan_coords[0],
                                     line_corr0_stop=scan_coords[1],
                                     line_corr1_start=scan_coords[2],
                                     line_corr1_stop=scan_coords[3],
                                     time_forward=scan_speed_per_line,
                                     time_back=time_idle_move)

            # self._counter.start_recorder(arm=True)
            self._spm.scan_line()

            counts, int_time = self._spm.get_measurements(),  None

            if int_time is None or np.any(np.isclose(int_time,0,atol=1e-12)):
                int_time = integration_time

            self._opti_scan_array[opti_name]['data'][line_num] = counts / int_time
            self.sigOptimizeLineScanFinished.emit(opti_name)

            if self._stop_request:
                break

            # self.log.info(f'Line number {line_num} completed.')
            # print(f'Line number {line_num} completed.')

        stop_time_opti = datetime.datetime.now()
        self._opti_meas_duration = (stop_time_opti - start_time_opti).total_seconds()
        self.log.info(f'Optimizer XY finished after {int(self._opti_meas_duration)}s. Yeehaa!')

        self._opti_scan_array[opti_name]['params']['Measurement stop'] = stop_time_opti.isoformat()
        self._opti_scan_array[opti_name]['params']['Total measurement time (s)'] = self._opti_meas_duration


        # clean up the counter
        # self._counter.stop_measurement()

        # clean up the spm
        self._spm.finish_scan()


        return self._opti_scan_array

# ==============================================================================
#           Scan of just one line for optimizer by line
# ==============================================================================

    def scan_line_obj_by_line_opti(self, coord0_start, coord0_stop, coord1_start,
                                    coord1_stop, res, integration_time,
                                    continue_meas=False):

        """ Measurement method for a scan by line.

        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int res_x: number of points in x direction
        @param int res_y: number of points in y direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                            'XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement
                                 parameter. Have a look at MEAS_PARAMS to see
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list.
        """

        plane = 'Z2X2'

        opti_name = 'opti_z'

        self._start = time.time()


        # set up the spm device:
        reverse_meas = False
        self._stop_request = False

        # FIXME: Make this a setting value
        time_idle_move = 0.1 # in seconds, time in which the stage is just
                             # moving without measuring

        ret_val = self._counter.configure_recorder(
            mode=HWRecorderMode.PIXELCLOCK, 
            params={'mw_frequency': self._freq1_iso_b_frequency,
                    'num_meas': res})

        if ret_val < 0:
            self.sigOptimizeLineScanFinished.emit(opti_name)
            self._stop_request = True   # Set a stop request to stop a false measurement!
            return self._opti_scan_array
            
        # scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = integration_time * res

        scan_coords = [coord0_start, coord0_stop, coord1_start, coord1_stop]

        # FIXME: check whether the number of parameters are required and whether they are set correctly.
        # self._spm._params_per_point = len(names_buffers)
        ret_val, _, _ = self._spm.configure_scanner(mode=ScannerMode.OBJECTIVE_ZX,
                                                    params= {'line_points': res },
                                                    scan_style=ScanStyle.LINE) 

        self._spm.set_ext_trigger(True)

        self._opti_scan_array = self.initialize_opti_z_scan_array(coord0_start,
                                                                  coord0_stop,
                                                                  res)
        # check input values
        # ret_val |= self._spm.check_spm_scan_params_by_plane(plane,
        #                                                     coord0_start,
        #                                                     coord0_stop,
        #                                                     coord1_start,
        #                                                     coord1_stop)
        if ret_val < 1:
            return self._opti_scan_array

        self._scan_counter = 0

        start_time_opti = datetime.datetime.now()

        self._opti_scan_array[opti_name]['params']['Parameters for'] = 'Optimize Z measurement'
        self._opti_scan_array[opti_name]['params']['axis name for coord0'] = 'Z'
        self._opti_scan_array[opti_name]['params']['measurement direction '] = 'Z'
        self._opti_scan_array[opti_name]['params']['coord0_start (m)'] = coord0_start
        self._opti_scan_array[opti_name]['params']['coord0_stop (m)'] = coord0_stop
        self._opti_scan_array[opti_name]['params']['coord0_num (#)'] = res

        self._opti_scan_array[opti_name]['params']['Scan speed per line (s)'] = scan_speed_per_line
        self._opti_scan_array[opti_name]['params']['Idle movement speed (s)'] = time_idle_move

        self._opti_scan_array[opti_name]['params']['integration time per pixel (s)'] = integration_time
        self._opti_scan_array[opti_name]['params']['Measurement start'] = start_time_opti.isoformat()

        # Optimizer Z signal
        self._opti_scan_array[opti_name]['data'] = np.zeros(res)

        self._spm.configure_line(line_corr0_start=scan_coords[0],
                                 line_corr0_stop=scan_coords[1],
                                 line_corr1_start=scan_coords[2],
                                 line_corr1_stop=scan_coords[3],
                                 time_forward=scan_speed_per_line,
                                 time_back=time_idle_move)

        # self._counter.start_recorder(arm=True)
        self._spm.scan_line()

        counts, int_time = self._spm.get_measurements(),  None

        if int_time is None or np.any(np.isclose(int_time,0,atol=1e-12)):
            int_time = integration_time

        self._opti_scan_array[opti_name]['data'] = counts[0] / int_time 

        #print(f'Optimizer Z scan complete.')
        self.sigOptimizeLineScanFinished.emit(opti_name)

        stop_time_opti = datetime.datetime.now()
        self._opti_meas_duration = (stop_time_opti - start_time_opti).total_seconds()
        self.log.info(f'Scan finished after {int(self._opti_meas_duration)}s. Yeehaa!')

        self._opti_scan_array[opti_name]['params']['Measurement stop'] = stop_time_opti.isoformat()
        self._opti_scan_array[opti_name]['params']['Total measurement time (s)'] = self._opti_meas_duration

        # clean up the spm
        self._spm.finish_scan()
        # clean up the counter
        # self._counter.stop_measurement()

        return self._opti_scan_array

# ==============================================================================
#   Optimize position routine
# ==============================================================================

    def get_optimizer_target(self):
        """ Obtain the current target position for the optimizer. 

        @return tuple: with (x, y, z) as the target position in m.
        """

        return (self._optimizer_x_target_pos, 
                self._optimizer_y_target_pos,
                self._optimizer_z_target_pos)

    def set_optimizer_target(self, x_target=None, y_target=None, z_target=None):
        """ Set the target position for the optimizer around which optimization happens. """

        if x_target is not None:
            self._optimizer_x_target_pos = x_target 
        if y_target is not None:
            self._optimizer_y_target_pos = y_target 
        if z_target is not None:
            self._optimizer_z_target_pos = z_target 

        #FIXME: Think about a general method and a generic return for this method
        #       to obtain the currently set target positions.



    #FIXME: Check, whether optimizer can get out of scan range, and if yes, 
    #       react to this!
    def default_optimize(self, run_in_thread=False):
        """ Note, this is a blocking method for optimization! """
        pos = self.get_obj_pos()

        _optimize_period = 60

        # make step symmetric
        x_step = self._sg_optimizer_x_range/2
        y_step = self._sg_optimizer_y_range / 2
        z_step = self._sg_optimizer_z_range / 2

        x_start = self._optimizer_x_target_pos - x_step
        x_stop = self._optimizer_x_target_pos + x_step
        res_x = self._sg_optimizer_x_res
        y_start = self._optimizer_y_target_pos - y_step
        y_stop = self._optimizer_y_target_pos + y_step
        res_y = self._sg_optimizer_y_res
        z_start = self._optimizer_z_target_pos - z_step
        z_stop = self._optimizer_z_target_pos + z_step
        res_z = self._sg_optimizer_z_res
        int_time_xy = self._sg_optimizer_int_time
        int_time_z = self._sg_optimizer_int_time

        if run_in_thread:
            self.start_optimize_pos(x_start, x_stop, res_x, y_start, y_stop,
                                    res_y,  z_start, z_stop, res_z, int_time_xy,
                                    int_time_z)
        else:
            self.optimize_obj_pos(x_start, x_stop, res_x, y_start, y_stop,
                                  res_y, z_start, z_stop, res_z, int_time_xy, 
                                  int_time_z)


    def optimize_obj_pos(self, x_start, x_stop, res_x, y_start, y_stop, res_y,
                         z_start, z_stop, res_z, int_time_xy, int_time_z):
        """ Optimize position for x, y and z by going to maximal value"""

        self._opt_val[0], self._opt_val[1], self._opt_val[3] = self.get_optimizer_target()

        # If the optimizer is called by itself, the the module state needs to be
        # locked, else we need to take care not to unlock it after finalizing
        # the process.
        optimizer_standalone_call = False
        
        if self.module_state() == 'idle':
            self.module_state.lock()
            optimizer_standalone_call = True

        opti_scan_arr = self.scan_area_obj_by_line_opti(x_start, x_stop, res_x,
                                                        y_start, y_stop, res_y,
                                                        int_time_xy)

        if self._stop_request or z_start<0 or x_start<0:
            
            # only unlock, if it is a standalone call.
            if optimizer_standalone_call:
                self.module_state.unlock()

            self.sigOptimizeScanFinished.emit()
            if z_start<0 or x_start<0:
                self.log.warning('X or Z position too low for optimize range!')
            return

        x_max, y_max, c_max = self._calc_max_val_xy(arr=opti_scan_arr['opti_xy']['data'], 
                                                    x_start=x_start, x_stop=x_stop, 
                                                    y_start=y_start, y_stop=y_stop)

        self._opti_scan_array['opti_xy']['params']['coord0 optimal pos (nm)'] = x_max
        self._opti_scan_array['opti_xy']['params']['coord1 optimal pos (nm)'] = y_max
        self._opti_scan_array['opti_xy']['params']['signal at optimal pos (c/s)'] = c_max

        if self._stop_request:
            
            # only unlock, if it is a standalone call.
            if optimizer_standalone_call:
                self.module_state.unlock()

            self.sigOptimizeScanFinished.emit()
            return


        pos = self.set_obj_pos( {'x': x_max, 'y': y_max})

        # curr_pos = self.get_obj_pos()
        # self._spm._set_pos_xy([x_max, y_max])
        # time.sleep(1)
        # self._spm._set_pos_xy([x_max, y_max])
        # time.sleep(1)
        # self._obj_pos[0] = x_max
        # self._obj_pos[1] = y_max
        self.sigNewObjPos.emit(self._obj_pos)


        # opti_scan_arr = self.scan_line_obj_by_point_opti(coord0_start=x_max, coord0_stop=x_max,
        #                                                coord1_start=z_start, coord1_stop=z_stop,
        #                                                res=res_z,
        #                                                integration_time=int_time_z,
        #                                                wait_first_point=True)
        opti_scan_arr = self.scan_line_obj_by_line_opti(coord1_start=x_max,
                                                        coord1_stop=x_max,
                                                        coord0_start=z_start,
                                                        coord0_stop=z_stop,
                                                        res=res_z,
                                                        integration_time=int_time_z)

        if self._stop_request:
            
            # only unlock, if it is a standalone call.
            if optimizer_standalone_call:
                self.module_state.unlock()
            
            self.sigOptimizeScanFinished.emit()
            return

        z_max, c_max_z, res = self._calc_max_val_z(opti_scan_arr['opti_z']['data'], 
                                              z_start, z_stop)

        self._opti_scan_array['opti_z']['params']['coord0 optimal pos (nm)'] = z_max
        self._opti_scan_array['opti_z']['params']['signal at optimal pos (c/s)'] = c_max_z
        self._opti_scan_array['opti_z']['data_fit'] = res.best_fit

        self.log.debug(f'Found maximum at: [{x_max*1e6:.2f}, {y_max*1e6:.2f}, {z_max*1e6:.2f}]')

        self.set_obj_pos({'x': x_max, 'y': y_max, 'z': z_max})


        self._optimizer_x_target_pos = x_max
        self._optimizer_y_target_pos = y_max
        self._optimizer_z_target_pos = z_max

        self._opt_val = [x_max, y_max, c_max, z_max, c_max_z]
        
        # only unlock, if it is a standalone call.
        if optimizer_standalone_call:
            self.module_state.unlock()

        self.sigOptimizeLineScanFinished.emit('opti_z')
        self.sigOptimizeScanFinished.emit()
        self._counter.stop_measurement()

        return x_max, y_max, c_max, z_max, c_max_z


    def start_optimize_pos(self, x_start, x_stop, res_x, y_start, y_stop, res_y, 
                           z_start, z_stop, res_z, int_time_xy, int_time_z):

        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.optimize_obj_pos,
                                           args=(x_start, x_stop, res_x,
                                                 y_start, y_stop, res_y,
                                                 z_start, z_stop, res_z,
                                                 int_time_xy, int_time_z),
                                           name='optimizer')
        self.threadpool.start(self._worker_thread)


# ==============================================================================
# QAFM measurement with optimization possibility:
# ==============================================================================

    #FIXME: This methods needs to be checked!!
    @deprecated("This method seems not to be used")
    def measure_point_optimized(self, x_start_afm=48*1e-6, x_stop_afm=53*1e-6, 
                                y_start_afm=47*1e-6, y_stop_afm=52*1e-6, 
                                res_x_afm=40, res_y_afm=40, integration_time_afm=0.02, 
                                plane_afm='XY',
                                meas_params=['Phase', 'Height(Dac)', 'Height(Sen)'],
                                continue_meas=False, optimize_int=60,
                                res_x_obj=25, res_y_obj=25, res_z_obj=25, 
                                int_time_xy_obj=0.01, int_time_z_obj=0.02):

        self._stop_request_all = False
        self._afm_meas_optimize_interval = optimize_int

        self.start_measure_point(x_start_afm, x_stop_afm, y_start_afm, y_stop_afm, 
                                 res_x_afm, res_y_afm, 
                                 integration_time_afm, plane_afm, meas_params, 
                                 continue_meas)

        # just safety wait
        time.sleep(0.1)

        time_start =  time.time()

        while not self._stop_request_all:
            time.sleep(1)

            if (time.time() - time_start) > self._afm_meas_optimize_interval:
                self.stop_measure()

                timeout = 60
                counter = 0
                # make a timeout for waiting
                while self.module_state() != 'idle':
                    time.sleep(1)
                    counter += 1

                    if counter > timeout:
                        self.log.warning('Timeout reached! Abort optimize and quit.')
                        return

                x_start = self._opt_val[0] - 0.5*1e-6
                x_stop = self._opt_val[0] + 0.5*1e-6
                y_start = self._opt_val[1] - 0.5*1e-6
                y_stop = self._opt_val[1] + 0.5*1e-6
                z_start = 0*1e-6
                z_stop = 8*1e-6
                self.optimize_pos(x_start=x_start, x_stop=x_stop, 
                                  y_start=y_start, y_stop=y_stop, 
                                  z_start=z_start, z_stop=z_stop, 
                                  res_x=res_x_obj, res_y=res_y_obj, res_z=res_z_obj, 
                                  int_time_xy=int_time_xy_obj, 
                                  int_time_z=int_time_z_obj)


                time_start = time.time()

                self.start_measure_point(x_start_afm, x_stop_afm, y_start_afm, 
                                         y_stop_afm, res_x_afm, res_y_afm, 
                                         integration_time_afm, plane_afm, 
                                         meas_params, True)
                time.sleep(0.1)


            if self.module_state() == 'idle':
                break


        self.log.info("Measurement completely finished, yeehaa!")


    @deprecated("This method seems not to be used")
    def start_measure_point_optimized(self, x_start_afm=48*1e-6, x_stop_afm=53*1e-6, 
                                      y_start_afm=47*1e-6, y_stop_afm=52*1e-6, 
                                      res_x_afm=40, res_y_afm=40, 
                                      integration_time_afm=0.02, plane_afm='XY',
                                      meas_params=['Phase', 'Height(Dac)', 'Height(Sen)'],
                                      continue_meas=False, optimize_int=60,
                                      res_x_obj=25, res_y_obj=25, res_z_obj=25, 
                                      int_time_xy_obj=0.01, int_time_z_obj=0.02):

        if self.check_meas_opt_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread_opt = threading.Thread(target=self.measure_point_optimized, 
                                            args=(x_start_afm, x_stop_afm, 
                                                  y_start_afm, y_stop_afm, 
                                                  res_x_afm, res_y_afm, 
                                                  integration_time_afm, plane_afm,
                                                  meas_params, continue_meas,
                                                  optimize_int, res_x_obj, 
                                                  res_y_obj, res_z_obj, 
                                                  int_time_xy_obj, int_time_z_obj), 
                                            name='meas_thread_opt')
        self.meas_thread_opt.start()


# ==============================================================================
#           Method to measure just one line instead of whole area point
# ==============================================================================
    @deprecated("This method seems not to be used")
    def scan_line_by_point(self, coord0_start, coord0_stop, coord1_start, coord1_stop, res, 
                           integration_time, plane='XY', meas_params=['Height(Dac)'],
                           wait_first_point=False, continue_meas=False):

        """ Measurement method for a scan by point.
        
        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int res_x: number of points in x direction
        @param int res_y: number of points in y direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                            'XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement 
                                 parameter. Have a look at MEAS_PARAMS to see 
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list. 
        """


        self._start = time.time()

        if not np.isclose(self._counterlogic.get_count_frequency(), 1/integration_time):
            self._counterlogic.set_count_frequency(frequency=1/integration_time)
        self._counterlogic.startCount()

        # set up the spm device:
        reverse_meas = False
        self._stop_request = False
        #scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = integration_time
        scan_arr = [[coord0_start, coord0_stop, coord1_start, coord1_stop]]

        #FIXME: check whether the number of parameters are required and whether they are set correctly.
        # self._spm._params_per_point = len(names_buffers)
        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                        params= {'line_points': res,
                                                 'meas_params': meas_params},
                                        scan_style=ScanStyle.LINE) 

        # AFM signal
        self._meas_array_scan = np.zeros(len(meas_params)*res)

        # APD signal
        self._apd_array_scan = np.zeros(res)

        # check input values
        ret_val |= self._spm.check_spm_scan_params_by_plane(plane, coord0_start, coord0_stop, coord1_start, coord1_stop)   

        if ret_val < 1:
            return self._apd_array_scan, self._meas_array_scan

        self._scan_counter = 0

        for line_num, scan_coords in enumerate(scan_arr):
            
            # AFM signal
            self._meas_line_scan = np.zeros(len(curr_scan_params)*res)
            # APD signal
            self._apd_line_scan = np.zeros(res)
            
            self._spm.configure_line(line_corr0_start=scan_coords[0], 
                                     line_corr0_stop=scan_coords[1], 
                                     line_corr1_start=scan_coords[2], 
                                     line_corr1_stop=scan_coords[3], 
                                     time_forward=scan_speed_per_line, 
                                     time_back=scan_speed_per_line)
            
            vals = self._spm.scan_point()  # these are points to throw away

            if wait_first_point and (self._scan_counter == 0):
                time.sleep(2)

            #if len(vals) > 0:
            #    self.log.error("The scanner range was not correctly set up!")

            for index in range(res):

                #Important: Get first counts, then the SPM signal!
                #self._apd_line_scan[index] = self._counter.get_counter(1)[0][0]
                self._apd_line_scan[index] = self._counterlogic.get_last_counts(1)[0][0]

                self._meas_line_scan[index*len(curr_scan_params):(index+1)*len(curr_scan_params)] = self._spm.scan_point()
                
                self._scan_counter += 1
                if self._stop_request:
                    break

                self._meas_array_scan = self._meas_line_scan
                self._apd_array_scan = self._apd_line_scan

            if self._stop_request:
                break

            #self.log.info(f'Line number {line_num} completed.')
            print(f'Line number {line_num} completed.')
                
        self._stop = time.time() - self._start
        self.log.info(f'Scan finished after {int(self._stop)}s. Yeehaa!')

        # clean up the counter:
        #self._counter.close_counter()
        #self._counter.close_clock()
        
        # clean up the spm
        self._spm.finish_scan()
        
        return self._apd_array_scan, self._meas_array_scan

    @deprecated("This method seems not to be used")
    def start_measure_line_point(self, coord0_start=0*1e-6, coord0_stop=0*1e-6, 
                                 coord1_start=0*1e-6, coord1_stop=10*1e-6, 
                                 res=100, integration_time=0.02, plane='XY',
                                 meas_params=['Phase', 'Height(Dac)', 'Height(Sen)'],
                                 wait_first_point=False):

        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread = threading.Thread(target=self.scan_line_by_point, 
                                            args=(coord0_start, coord0_stop, 
                                                  coord1_start, coord1_stop, 
                                                  res, 
                                                  integration_time,
                                                  plane,
                                                  meas_params, wait_first_point), 
                                            name='meas_thread')

        self.meas_thread.start()

# ==============================================================================
#        General stop routine, to stop the current running measurement
# ==============================================================================

    def stop_measure(self):
        #self._counter.stop_measurement()
        self._stop_request = True

        #FIXME: this is mostly for debugging reasons, but it should be removed later.
        # unlock the state in case an error has happend.
        if not self._worker_thread.is_running() or not self._counter.is_measurement_running:
            # self._counter.meas_cond.wakeAll()
            if self.module_state() != 'idle':
                self.module_state.unlock()

            #self._worker_thread.autoDelete()

            return -1

        return 0

        #self._spm.finish_scan()

    def stop_immediate(self):
        self._spm.stop_measurement()
        self._counter.stop_measurement()
        self._health_check.stop_timer()
        self.sigQAFMScanFinished.emit()
        self.sigQuantiScanFinished.emit()
        self.log.debug("Immediate stop request completed")

# ==============================================================================
#        Pulser configuration
# ==============================================================================
    def _make_pulse_sequence(self, mode, int_time, freq_points=1, num_esr_runs=1):

        d_ch = {0: False , 1: False , 2: False , 3: False , 4: False , 5: False , 6: False , 7: False }
        clear = lambda x: {i:False for i in x.keys()}
        
        if mode == HWRecorderMode.PIXELCLOCK:
            seq = PulseSequence()
            
            block_1 = PulseBlock()
            
            d_ch = clear(d_ch)
            d_ch[self._pulser._pixel_start] = True
            block_1.append(init_length = 1e-6, channels = d_ch, repetition = 1)

            d_ch = clear(d_ch)
            block_1.append(init_length = int_time, channels = d_ch, repetition = 1)

            d_ch = clear(d_ch)
            d_ch[self._pulser._pixel_stop] = True
            d_ch[self._pulser._sync_in] = True
            block_1.append(init_length = 1e-6, channels = d_ch, repetition = 1)

            seq.append([(block_1, 1)])

            pulse_dict = seq.pulse_dict
        
        elif mode == HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B:
            seq = PulseSequence()
            
            block_1 = PulseBlock()
            
            d_ch = clear(d_ch)
            d_ch[self._pulser._pixel_start] = True
            block_1.append(init_length = 1e-6, channels = d_ch, repetition = 1)

            d_ch = clear(d_ch)
            d_ch[self._pulser._mw_switch] = True
            block_1.append(init_length = int_time, channels = d_ch, repetition = 1)

            d_ch = clear(d_ch)
            d_ch[self._pulser._pixel_stop] = True
            d_ch[self._pulser._sync_in] = True
            block_1.append(init_length = 1e-6, channels = d_ch, repetition = 1)

            seq.append([(block_1, 1)])

            pulse_dict = seq.pulse_dict

        elif mode == HWRecorderMode.ESR:

            seq = PulseSequence()
            
            block_1 = PulseBlock()

            d_ch = clear(d_ch)
            d_ch[self._pulser._mw_trig] = True
            d_ch[self._pulser._laser] = True
            d_ch[self._pulser._mw_switch] = True
            d_ch[self._pulser._pixel_start] = True
            block_1.append(init_length = int_time, channels = d_ch, repetition = 1)

            d_ch = clear(d_ch)
            d_ch[self._pulser._pixel_stop] = True
            block_1.append(init_length = 1e-6, channels = d_ch, repetition = 1)

            seq.append([(block_1, freq_points*num_esr_runs)])

            block_2 = PulseBlock()

            d_ch = clear(d_ch)
            d_ch[self._pulser._sync_in] = True
            block_2.append(init_length = 1e-6, channels = d_ch, repetition = 1)

            seq.append([(block_2, 1)])

            pulse_dict = seq.pulse_dict
        
        return pulse_dict

# ==============================================================================
#        Higher level optimization routines for objective scanner
# ==============================================================================

    def optimize_pos(self, x_start, x_stop, y_start, y_stop, z_start,z_stop, 
                     res_x, res_y, res_z, int_time_xy, int_time_z):
        """ Optimize position for x, y and z by going to maximal value"""


        apd_arr_xy, afm_arr_xy = self.scan_by_point_single_line(x_start, x_stop, 
                                       y_start, y_stop, res_x, res_y, 
                                       int_time_xy, plane='X2Y2', meas_params=[], 
                                       wait_first_point=True)

        if self._stop_request:
            return

        x_max, y_max, c_max = self._calc_max_val_xy(arr=apd_arr_xy, x_start=x_start,
                                                    x_stop=x_stop, y_start=y_start,
                                                    y_stop=y_stop)
        if self._stop_request:
            return

        self.set_obj_pos({'x': x_max, 'y':y_max})

        # self._spm._set_pos_xy([x_max, y_max])
        # time.sleep(1)
        # self._spm._set_pos_xy([x_max, y_max])
        # time.sleep(1)

        apd_arr_z, afm_arr_z = self.scan_line_by_point(coord0_start=x_max, coord0_stop=x_max, 
                                                       coord1_start=z_start, coord1_stop=z_stop, 
                                                       res=res_z, 
                                                       integration_time=int_time_z, 
                                                       plane='X2Z2', meas_params=[],
                                                       wait_first_point=True)

        if self._stop_request:
            return

        z_max, c_max_z, _ = self._calc_max_val_z(apd_arr_z, z_start, z_stop)

        self.set_obj_pos({'x': x_max, 'y': y_max, 'z':z_max})

        # self._spm.set_pos_obj([x_max, y_max, z_max])
        # time.sleep(2)
        # self._spm.set_pos_obj([x_max, y_max, z_max])

        self._opt_val = [x_max, y_max, c_max, z_max, c_max_z]

        return x_max, y_max, c_max, z_max, c_max_z


    def _calc_max_val_xy(self, arr, x_start, x_stop, y_start, y_stop):
        """ Calculate the maximal value in an 2d array. """
        np.amax(arr)
        column_max = np.amax(arr, axis=1).argmax()
        row_max = np.amax(arr, axis=0).argmax()
        column_num, row_num = np.shape(arr)

        x_max = (row_max + 1)/row_num * (x_stop - x_start) + x_start
        y_max = (column_max + 1)/column_num * (y_stop - y_start) + y_start
        c_max = arr[column_max, row_max]

        #FIXME: make sure c_max is the fitted value coming from x_max and y_max

        x_axis = np.linspace(x_start,x_stop,row_num)
        y_axis = np.linspace(y_start,y_stop,column_num)

        optimizer_x, optimizer_y = np.meshgrid(x_axis, y_axis)

        xy_axes = np.empty((len(x_axis) * len(y_axis), 2))
        xy_axes = (optimizer_x.flatten(), optimizer_y.flatten())

        for i in range(3):
            try:
                res = self._fitlogic.make_twoDgaussian_fit(xy_axes,arr.ravel(),
                    estimator=self._fitlogic.estimate_twoDgaussian_MLE)

                x_max = res.params['center_x'].value
                y_max = res.params['center_y'].value

                break

            except:
                pass

        return (x_max, y_max, c_max)


    def _calc_max_val_z(self, arr_z, z_start, z_stop):
        """ Calculate maximum value from z scan. """
        c_max = arr_z.max()
        z_max = arr_z.argmax()/len(arr_z) * (z_stop-z_start) + z_start
        z_axis = np.linspace(z_start,z_stop,len(arr_z))

        res = self._fitlogic.make_gaussianlinearoffset_fit(z_axis,arr_z,
            estimator=self._fitlogic.estimate_gaussianlinearoffset_peak)

        #FIXME: make sure c_max is the fitted value coming from z_max

        z_max = res.params['center'].value

        return z_max, c_max, res


    @deprecated("This method seems not to be used")
    def start_measure_opt_pos(self, x_start, x_stop, y_start, y_stop, z_start, z_stop, 
                              res_x, res_y, res_z, int_time_xy, int_time_z):

        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread = threading.Thread(target=self.optimize_pos, 
                                            args=(x_start, x_stop, 
                                                  y_start, y_stop,
                                                  z_start, z_stop, 
                                                  res_x, res_y, res_z,
                                                  int_time_xy, int_time_z), 
                                            name='meas_thread')
        self.meas_thread.start()

# ==============================================================================
#        Perform a scan just in one direction
# ==============================================================================

    @deprecated('Current function no longer in use; currently it will not work')
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
        ret_val = self._spm._check_spm_scan_params(x_afm_start=x_start, x_afm_stop=x_stop,
                                              y_afm_start=y_start, y_afm_stop=y_stop)
        if ret_val:
            return self._meas_array_scan
        
        scan_arr = self.create_scan_leftright2(x_start, x_stop, y_start, y_stop, res_y)
        
        ret_val, _, _ = self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                                    params= {'line_points': res_x,
                                                             'meas_params': meas_params},
                                                    scan_style=ScanStyle.LINE) 

        if ret_val < 1:
            return self._meas_array_scan

        for scan_coords in scan_arr:

            self._spm.configure_line(line_corr0_start=scan_coords[0], 
                                     line_corr0_stop=scan_coords[1], 
                                     line_corr1_start=scan_coords[2], 
                                     line_corr1_stop=scan_coords[3], 
                                     time_forward=time_forward, 
                                     time_back=time_back)
            self.scan_line()

            # this method will wait until the line was measured.
            scan_line = self._spm.get_measurements(reshape=False)

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
        self._spm._dev.finish_scan()
        
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

        if self._spm.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
        else:
            self.meas_thread.start()

    @deprecated("This method seems not to be used")
    def scan_by_point_single_line(self, coord0_start, coord0_stop, 
                                  coord1_start, coord1_stop, 
                                  res_x, res_y, integration_time, plane='XY', 
                                  meas_params=['Height(Dac)'], 
                                  wait_first_point=False):

        """ Measurement method for a scan by point, with just one linescan
        
        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int res_x: number of points in x direction
        @param int res_y: number of points in y direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                            'XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement 
                                 parameter. Have a look at MEAS_PARAMS to see 
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list. 
        """

        self._start = time.time()

        if not np.isclose(self._counterlogic.get_count_frequency(), 1/integration_time):
            self._counterlogic.set_count_frequency(frequency=1/integration_time)
        self._counterlogic.startCount()

        # set up the spm device:
        self._stop_request = False
        #scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = integration_time
        scan_arr = self.create_scan_leftright(coord0_start, coord0_stop, 
                                              coord1_start, coord1_stop, res_y)

        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                        params= {'line_points': res_x,
                                                 'meas_params': meas_params},
                                        scan_style=ScanStyle.LINE) 

        # AFM signal
        self._meas_array_scan = np.zeros((res_y, len(curr_scan_params)*res_x))
        # APD signal
        self._apd_array_scan = np.zeros((res_y, res_x))

        # check input values
        ret_val |= self._spm.check_spm_scan_params_by_plane(plane, coord0_start, coord0_stop, coord1_start, coord1_stop)   

        if ret_val < 1:
            return (self._apd_array_scan, self._meas_array_scan)

        self._scan_counter = 0
        for line_num, scan_coords in enumerate(scan_arr):
            
            # AFM signal
            self._meas_line_scan = np.zeros(len(curr_scan_params)*res_x)
            # APD signal
            self._apd_line_scan = np.zeros(res_x)
            
            self._spm.configure_line(line_corr0_start=scan_coords[0], 
                                     line_corr0_stop=scan_coords[1], 
                                     line_corr1_start=scan_coords[2], 
                                     line_corr1_stop=scan_coords[3], 
                                     time_forward=scan_speed_per_line, 
                                     time_back=scan_speed_per_line)
            
            vals = self._spm.scan_point()  # these are points to throw away

            # wait a bit before starting to count the first value.
            if wait_first_point and (self._scan_counter == 0):
                time.sleep(2)

            #if len(vals) > 0:
            #    self.log.error("The scanner range was not correctly set up!")

            for index in range(res_x):

                #Important: Get first counts, then the SPM signal!
                self._apd_line_scan[index] = self._counter.get_counter(1)[0][0]
                self._meas_line_scan[index*len(curr_scan_params):(index+1)*len(curr_scan_params)] = self._spm.scan_point()
                
                self._scan_counter += 1
                if self._stop_request:
                    break

            self._meas_array_scan[line_num] = self._meas_line_scan
            self._apd_array_scan[line_num] = self._apd_line_scan

            if self._stop_request:
                break

            #self.log.info(f'Line number {line_num} completed.')
            print(f'Line number {line_num} completed.')
                
        self._stop = time.time() - self._start
        self.log.info(f'Scan finished after {int(self._stop)}s. Yeehaa!')

        # clean up the counter:
        # self._counter.close_counter()
        # self._counter.close_clock()
        
        # clean up the spm
        self._spm.finish_scan()
        
        return (self._apd_array_scan, self._meas_array_scan)


    @deprecated("This method seems not to be used")
    def start_measure_scan_by_point_single_line(self, coord0_start=0*1e-6, coord0_stop=0*1e-6, 
                                                coord1_start=0*1e-6, coord1_stop=10*1e-6, 
                                                res_x=100, res_y=100, integration_time=0.02, 
                                                plane='XY',
                                                meas_params=['Phase', 'Height(Dac)', 'Height(Sen)']):
        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread = threading.Thread(target=self.scan_by_point_single_line, 
                                            args=(coord0_start, coord0_stop, 
                                                  coord1_start, coord1_stop, 
                                                  res_x, res_y,
                                                  integration_time,
                                                  plane,
                                                  meas_params), 
                                            name='meas_thread')
        self.meas_thread.start()

# ==============================================================================
#        Perform a scan in a snake line way
# ==============================================================================

    @deprecated("This method seems not to be used")
    def scan_area_by_point_snakeline(self, coord0_start, coord0_stop, 
                                     coord1_start, coord1_stop, res_x, res_y, 
                                     integration_time, plane='XY', 
                                     meas_params=['Height(Dac)']):

        """ Measurement method for a scan by point.
        
        @param float coord0_start: start coordinate in um
        @param float coord0_stop: start coordinate in um
        @param float coord1_start: start coordinate in um
        @param float coord1_stop: start coordinate in um
        @param int res_x: number of points in x direction
        @param int res_y: number of points in y direction
        @param float integration_time: time for the optical integration in s
        @param str plane: Name of the plane to be scanned. Possible options are
                            'XY', 'YZ', 'XZ', 'X2Y2', 'Y2Z2', 'X2Z2'
        @param list meas_params: list of possible strings of the measurement 
                                 parameter. Have a look at MEAS_PARAMS to see 
                                 the available parameters.

        @return 2D_array: measurement results in a two dimensional list. 
        """

        self._start = time.time()

        if not np.isclose(self._counterlogic.get_count_frequency(), 1/integration_time):
            self._counterlogic.set_count_frequency(frequency=1/integration_time)
        self._counterlogic.startCount()

        # set up the spm device:
        reverse_meas = False
        self._stop_request = False
        #scan_speed_per_line = 0.01  # in seconds
        scan_speed_per_line = integration_time
        scan_arr = self.create_scan_snake(coord0_start, coord0_stop, 
                                               coord1_start, coord1_stop, res_y)

        ret_val, _, curr_scan_params = \
            self._spm.configure_scanner(mode=ScannerMode.PROBE_CONTACT,
                                        params= {'line_points': res_x,
                                                 'meas_params': meas_params},
                                        scan_style=ScanStyle.LINE) 

        # AFM signal
        self._meas_array_scan = np.zeros((res_y, len(curr_scan_params)*res_x))
        # APD signal
        self._apd_array_scan = np.zeros((res_y, res_x))

        # check input values
        ret_val |= self._spm.check_spm_scan_params_by_plane(plane, coord0_start, coord0_stop, 
                                                            coord1_start, coord1_stop)   

        if ret_val < 1:
            return (self._apd_array_scan, self._meas_array_scan)

        self._scan_counter = 0

        for line_num, scan_coords in enumerate(scan_arr):
            
            # AFM signal
            self._meas_line_scan = np.zeros(len(curr_scan_params)*res_x)
            # APD signal
            self._apd_line_scan = np.zeros(res_x)
            
            self._spm.configure_line(line_corr0_start=scan_coords[0], 
                                     line_corr0_stop=scan_coords[1], 
                                     line_corr1_start=scan_coords[2], 
                                     line_corr1_stop=scan_coords[3], 
                                     time_forward=scan_speed_per_line, 
                                     time_back=scan_speed_per_line)
            
            vals = self._spm.scan_point()  # these are points to throw away

            #if len(vals) > 0:
            #    self.log.error("The scanner range was not correctly set up!")

            for index in range(res_x):

                #Important: Get first counts, then the SPM signal!
                self._apd_line_scan[index] = self._counter.get_counter(1)[0][0]
                self._meas_line_scan[index*len(curr_scan_params):(index+1)*len(curr_scan_params)] = self._spm.scan_point()
                
                self._scan_counter += 1
                if self._stop_request:
                    break

            if reverse_meas:
                self._meas_array_scan[line_num] = self._meas_line_scan[::-1]
                self._apd_array_scan[line_num] = self._apd_line_scan[::-1]
                reverse_meas = False
            else:
                self._meas_array_scan[line_num] = self._meas_line_scan
                self._apd_array_scan[line_num] = self._apd_line_scan
                reverse_meas = True

            if self._stop_request:
                break

            #self.log.info(f'Line number {line_num} completed.')
            print(f'Line number {line_num} completed.')
                
        self._stop = time.time() - self._start
        self.log.info(f'Scan finished after {int(self._stop)}s. Yeehaa!')

        # clean up the counter:
        # self._counter.close_counter()
        # self._counter.close_clock()
        
        # clean up the spm
        self._spm.finish_scan()
        
        return (self._apd_array_scan, self._meas_array_scan)


    @deprecated("This method seems not to be used")
    def start_measure_scan_area_by_point_snakeline(self, coord0_start=0*1e-6, coord0_stop=0*1e-6, 
                                                   coord1_start=0*1e-6, coord1_stop=10*1e-6, 
                                                   res_x=100, res_y=100, integration_time=0.02, 
                                                   plane='XY',
                                                   meas_params=['Phase', 'Height(Dac)', 'Height(Sen)']):

        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread = threading.Thread(target=self.scan_area_by_point_snakeline, 
                                            args=(coord0_start, coord0_stop, 
                                                  coord1_start, coord1_stop, 
                                                  res_x, res_y, 
                                                  integration_time,
                                                  plane,
                                                  meas_params), 
                                            name='meas_thread')
        self.meas_thread.start()

# ==============================================================================
#        Optimize objective scanner and track the maximal fluorescence level
# ==============================================================================

    @QtCore.Slot()
    def _optimize_finished(self):
        self.set_optimize_request(False)

    def set_optimize_request(self, state):
        """ Set the optimizer request flag.
        Optimization is performed at the next possible moment.

        Procedure:
            The gui should set all the optimizer settings parameter in the 
            logic, then check if meas thread is running and existing, 
                if no, run optimization routine
                if yes, set just the optimize request flag and the running 
                method will call the optimization at an appropriated point in 
                time.
            
            The optimization request will be not accepted during an optical 
            scan.
        """

        if state:

            if self.check_thread_active():
                if not self._worker_thread.name == 'obj_scan':
                    # set optimize request only if the state is appropriate for 
                    # this.
                    self._optimize_request = state

                    return True

            else:
                self.default_optimize(run_in_thread=True)
                return True

        else:
            self._optimize_request = state

        return False

    def get_optimize_request(self):
        return self._optimize_request

    @deprecated("This method seems not be used")
    def track_optimal_pos(self, x_start, x_stop, y_start, y_stop, z_start,z_stop, 
                          res_x, res_y, res_z, int_time_xy, int_time_z, wait_inbetween=60):

        self._stop_request = False
        self._opt_pos = {}

        counter = 0
        sleep_counter = 0



        while not self._stop_request:

            x_max, y_max, c_max, z_max, c_max_z = self.optimize_pos(x_start, x_stop, 
                                                                    y_start, y_stop, 
                                                                    z_start,z_stop, 
                                                                    res_x, res_y, res_z, 
                                                                    int_time_xy, int_time_z)

            # sleep for 1 minute
            while sleep_counter < wait_inbetween and not self._stop_request:
                time.sleep(1)
                sleep_counter += 1

            counts = self._counter.get_counter(100)[0].mean()
            self._opt_pos[counter] = [time.time(), x_max, y_max, c_max, z_max, c_max_z, counts]

            counter += 1
            sleep_counter = 0

            x_start = x_max - 0.5 *1e-6
            x_stop = x_max + 0.5 *1e-6
            y_start = y_max - 0.5 *1e-6
            y_stop = y_max + 0.5 *1e-6

        return self._opt_pos

    @deprecated("This method seems not to be used")
    def start_track_optimal_pos(self, x_start=14*1e-6, x_stop=15*1e-6, y_start=14*1e-6, y_stop=15*1e-6, 
                                z_start=0*1e-6, z_stop=10*1e-6, res_x=25, res_y=25, res_z=500, 
                                int_time_xy=0.05, int_time_z=0.05, wait_inbetween=60):

        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread = threading.Thread(target=self.track_optimal_pos, 
                                            args=(x_start, x_stop, 
                                                  y_start, y_stop, 
                                                  z_start,z_stop, 
                                                  res_x, res_y, res_z, 
                                                  int_time_xy, int_time_z,
                                                  wait_inbetween), 
                                            name='meas_thread')
        self.meas_thread.start()

# ==============================================================================
#        Record fluorescence as a function of time at fixed objective position
# ==============================================================================

    @deprecated("This method seems not to be used")
    def record_fluorescence(self, timeinterval=10, average_time=1, count_freq=50):
        """ Record the fluorescence signal over a certain time interval.

        @param float timeinterval: wait time between measurements
        @param float average_time: time over which to average counts
        @param float count_freq: count frequency of the fluorescence counter
        """

        # the fluorescence track arrays
        self._f_track_time = []
        self._f_track_counts = []

        if not np.isclose(self._counterlogic.get_count_frequency(), count_freq):
            self._counterlogic.set_count_frequency(frequency=count_freq)
        self._counterlogic.startCount()

        while not self._stop_request:
            time.sleep(timeinterval)
            samples = int(average_time*count_freq)
            self._f_track_counts.append(self._counter.get_counter(samples)[0].mean())
            self._f_track_time.append(time.time())

        return (self._f_track_time, self._f_track_counts)

    @deprecated("This method seems not to be used")
    def start_record_fluorescence(self, timeinterval=10, average_time=1, count_freq=50):

        if self.check_meas_run():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self.meas_thread = threading.Thread(target=self.record_fluorescence, 
                                        args=(timeinterval, average_time,
                                              count_freq), 
                                        name='meas_thread')
        self.meas_thread.start()


    def check_thread_active(self):
        """ Check whether current worker thread is running. """

        if hasattr(self, '_worker_thread'):
            if self._worker_thread.is_running():
                return True
        return False




    def check_meas_opt_run(self):
        """ Check routine, whether main optimization measurement thread is running. """
        if hasattr(self, 'meas_thread_opt'):
            if self.meas_thread_opt.isAlive():
                return True
        
        return False

    def get_qafm_data(self):
        return self._qafm_scan_array

    def get_obj_data(self):
        return self._obj_scan_array

    def get_opti_data(self):
        return self._opti_scan_array

    def get_esr_data(self):
        return self._esr_scan_array

    def get_obj_pos(self, pos_list=['x', 'y', 'z']):
        """ Get objective position.

        @param list pos_list: optional, specify, which axis you want to have.
                              Possibilities are 'X' or 'x', 'Y' or 'y', 'Z' or
                              'z'.

        @return dict: the full position dict, containing the updated values.
        """

        # adapt to the standard convention of the hardware, do not manipulate
        # the passed list.
        target_pos_list = [0.0] * len(pos_list)
        for index, entry in enumerate(pos_list):
            target_pos_list[index] = entry.upper() + '2'

        pos = self._spm.get_objective_pos(target_pos_list)

        for entry in pos:
            self._obj_pos[entry[0].lower()] = pos[entry]

        return self._obj_pos

    def get_afm_pos(self, pos_list=['x', 'y']):
        """ Get AFM position.

        @param list pos_list: optional, specify, which axis you want to have.
                              Possibilities are 'X' or 'x', 'Y' or 'y'.

        @return dict: the full position dict, containing the updated values.
        """

        # adapt to the standard convention of the hardware, do not manipulate
        # the passed list.
        target_pos_list = [0.0] * len(pos_list)
        for index, entry in enumerate(pos_list):
            target_pos_list[index] = entry.upper() + '1'

        pos = self._spm.get_sample_pos(target_pos_list)

        for entry in pos:
            self._afm_pos[entry[0].lower()] = pos[entry] # for now I drop the z position

        return self._afm_pos

    def set_obj_pos(self, pos_dict, move_time=None):
        """ Set the objective position.

        @param dict pos_dict: a position dictionary containing keys as 'x', 'y'
                              and 'z' and the values are the positions in m.
                              E.g.:
                                    {'x': 10e-6, 'z': 1e-6}

        @return dict: the actual set position within the position dict. The full
                      position dict is returned.
        """

        if move_time is None:
            move_time = self._sg_idle_move_target_obj

        target_pos_dict = {}
        for entry in pos_dict:
            target_pos_dict[entry.upper() + '2'] = pos_dict[entry]

        pos = self._spm.set_objective_pos_abs(target_pos_dict, 
                                              move_time=move_time)

        for entry in pos:
            self._obj_pos[entry[0].lower()] = pos[entry]

        self.sigNewObjPos.emit(pos)
        if self.module_state() != 'locked':
            self.sigObjTargetReached.emit()

        return self._obj_pos

    def set_afm_pos(self, pos_dict, move_time=None):
        """ Set the AFM position.

        @param dict pos_dict: a position dictionary containing keys as 'x' and
                             'y', and the values are the positions in m.
                              E.g.:
                                    {'x': 10e-6, 'y': 1e-6}

        @return dict: the actual set position within the position dict. The full
                      position dict is returned.
        """

        if move_time is None:
            move_time = self._sg_idle_move_target_sample

        target_pos_dict = {}
        for entry in pos_dict:
            target_pos_dict[entry.upper()] = pos_dict[entry]

        pos = self._spm.set_sample_pos_abs(target_pos_dict, move_time=move_time)

        for entry in pos:
            self._afm_pos[entry[0].lower()] = pos[entry]

        self.sigNewAFMPos.emit(pos)
        self.sigAFMTargetReached.emit()
        return self._afm_pos       



    def record_sample_distance(self, start_z, stop_z, num_z, int_time):
        pass

    def start_record_sample_distance(self, start_z, stop_z, num_z, int_time):
        pass



    def get_qafm_save_directory(self, use_qudi_savescheme=True, root_path=None,
                           daily_folder=True, probe_name=None, sample_name=None):

        return_path = self._get_root_dir(use_qudi_savescheme, root_path)

        if not use_qudi_savescheme:

            # if probe name is provided, make the folder for it
            if probe_name is not None or probe_name != '':
                probe_name = self.check_for_illegal_char(probe_name)
                return_path = os.path.join(return_path, probe_name)

            # if sample name is provided, make the folder for it
            if sample_name is not None or sample_name != '':
                sample_name = self.check_for_illegal_char(sample_name)
                return_path = os.path.join(return_path, sample_name)

            # if daily folder is required, create it:
            if daily_folder:
                daily_folder_name = time.strftime("%Y%m%d")
                return_path = os.path.join(return_path, daily_folder_name)

            if not os.path.exists(return_path):
                os.makedirs(return_path, exist_ok=True)

        return os.path.abspath(return_path)

    def get_probe_path(self, use_qudi_savescheme=False, root_path=None, probe_name=None):

        return_path = self._get_root_dir(use_qudi_savescheme, root_path)

        # if probe name is provided, make the folder for it
        if probe_name is not None or probe_name != '':
            probe_name = self.check_for_illegal_char(probe_name)
            return_path = os.path.join(return_path, probe_name)

        if not os.path.exists(return_path):
            os.makedirs(return_path, exist_ok=True)

        return os.path.abspath(return_path)


    def get_confocal_path(self, use_qudi_savescheme=False, root_path=None,
                          daily_folder=True, probe_name=None):

        return_path = self.get_probe_path(use_qudi_savescheme, root_path,
                                          probe_name)

        return_path = os.path.join(return_path, 'Confocal')

        # if daily folder is required, create it:
        if daily_folder:
            daily_folder_name = time.strftime("%Y%m%d")
            return_path = os.path.join(return_path, daily_folder_name)

        if not os.path.exists(return_path):
            os.makedirs(return_path, exist_ok=True)

        return return_path


    def _get_root_dir(self, use_qudi_savescheme=False, root_path=None):
        """ Check the passed root path and return the correct path.

        By providing a root path you force the method to take it, if the path
        is valid.

        If qudi scheme is selected, then the rootpath is ignored.
        """

        if use_qudi_savescheme:
            return_path = self._save_logic.get_path_for_module(module_name='AttoDRY2200_Pi3_SPM')
        else:

            if root_path is None or root_path == '' or not os.path.exists(root_path):

                # check if a root folder name is specified.

                if self._sg_root_folder_name == '': 
                    return_path = self._meas_path
                else:

                    return_path = os.path.join(self._meas_path, self._sg_root_folder_name)
                    if not os.path.exists(return_path):
                        os.makedirs(return_path)

                # self.log.debug(f'The provided rootpath "{root_path}" for '
                #                  f'save operation does not exist! Take '
                #                  f'default one: "{return_path}"')

            else:
                if os.path.exists(root_path):
                    return_path = self._meas_path
                    self.log.debug(f'The provided rootpath "{root_path}" for '
                                   f'save operation does not exist! Take '
                                   f'default one: "{return_path}"')
                else:
                    return_path = root_path


        return return_path


    def check_for_illegal_char(self, input_str):
        # remove illegal characters for Windows file names/paths 
        # (illegal filenames are a superset (41) of the illegal path names (36))
        # this is according to windows blacklist obtained with Powershell
        # from: https://stackoverflow.com/questions/1976007/what-characters-are-forbidden-in-windows-and-linux-directory-names/44750843#44750843
        #
        # PS> $enc = [system.Text.Encoding]::UTF8
        # PS> $FileNameInvalidChars = [System.IO.Path]::GetInvalidFileNameChars()
        # PS> $FileNameInvalidChars | foreach { $enc.GetBytes($_) } | Out-File -FilePath InvalidFileCharCodes.txt

        illegal = '\u0022\u003c\u003e\u007c\u0000\u0001\u0002\u0003\u0004\u0005\u0006\u0007\u0008' + \
                  '\u0009\u000a\u000b\u000c\u000d\u000e\u000f\u0010\u0011\u0012\u0013\u0014\u0015' + \
                  '\u0016\u0017\u0018\u0019\u001a\u001b\u001c\u001d\u001e\u001f\u003a\u002a\u003f\u005c\u002f' 

        output_str, _ = re.subn('['+illegal+']','_', input_str)
        output_str = output_str.replace('\\','_')   # backslash cannot be handled by regex
        output_str = output_str.replace('..','_')   # double dots are illegal too 
        output_str = output_str[:-1] if output_str[-1] == '.' else output_str # can't have end of line '.'

        if output_str != input_str:
            self.log.warning(f"The name '{input_str}' had invalid characters, "
                             f"name was modified to '{output_str}'")

        return output_str


    def save_qafm_data(self, tag=None, probe_name=None, sample_name=None,
                       use_qudi_savescheme=False, root_path=None, 
                       daily_folder=True, timestamp=None):

        scan_params = self.get_curr_scan_params()
        
        if scan_params == []:
            self.log.warning('Nothing measured to be saved for the QAFM measurement. Save routine skipped.')
            self.sigQAFMDataSaved.emit()
            return

        #scan_params = ['counts_fw','counts_bw','Height(Sen)_fw','Height(Sen)_bw','Mag_fw','Mag_bw','Phase_fw','Phase_bw',
        #                'Freq_fw','Freq_bw'] #Tests for data obtained from .dat file

        save_path =  self.get_qafm_save_directory(use_qudi_savescheme=use_qudi_savescheme,
                                             root_path=root_path,
                                             daily_folder=daily_folder,
                                             probe_name=probe_name,
                                             sample_name=sample_name)

        data = self.get_qafm_data()

        if timestamp is None:
            timestamp = datetime.datetime.now()

        for entry in scan_params:
            parameters = {}
            parameters.update(data[entry]['params'])
            nice_name = data[entry]['nice_name']
            unit = data[entry]['si_units']

            parameters['Name of measured signal'] = nice_name
            parameters['Units of measured signal'] = unit

            figure_data = data[entry]['data']

            corr_plane_coeff = None
            if data[entry]['image_correction']:
                corr_plane_coeff = data[entry]['corr_plane_coeff']

            # check whether figure has only zeros as data, skip this then
            if not np.any(figure_data):
                self.log.debug(f'The data array "{entry}" contains only zeros and will be not saved.')
                continue

            image_extent = [data[entry]['coord0_arr'][0],
                            data[entry]['coord0_arr'][-1],
                            data[entry]['coord1_arr'][0],
                            data[entry]['coord1_arr'][-1]]

            axes = ['X', 'Y']

            cbar_range = data[entry]['display_range']

            parameters['display_range'] = cbar_range

            #self.log.info(f'Save: {entry}')
            fig = self.draw_figure(figure_data, image_extent, axes, cbar_range,
                                        signal_name=nice_name, signal_unit=unit, corr_plane_coeff=corr_plane_coeff )

            image_data = {}
            image_data[f'QAFM XY scan image of a {nice_name} measurement without axis.\n'
                       'The upper left entry represents the signal at the upper left pixel position.\n'
                       'A pixel-line in the image corresponds to a row '
                       f'of entries where the Signal is in {unit}:'] = figure_data

            filelabel = f'QAFM_{entry}'

            if tag is not None:
                filelabel = f'{tag}_{filelabel}'

            fig = self._save_logic.save_data(image_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=fig)

            self.increase_save_counter()
            # prepare the full raw data in an OrderedDict:

            signal_name = data[entry]['nice_name']
            units_signal = data[entry]['si_units']

            raw_data = {}
            raw_data['X position (m)'] = np.tile(data[entry]['coord0_arr'], len(data[entry]['coord0_arr']))
            raw_data['Y position (m)'] = np.repeat(data[entry]['coord1_arr'], len(data[entry]['coord1_arr']))
            raw_data[f'{signal_name} ({units_signal})'] = data[entry]['data'].flatten()

            filelabel = filelabel + '_raw'

            self._save_logic.save_data(raw_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t')
            self.increase_save_counter()

        # this method will be anyway skipped, if no data are present.
        self.save_quantitative_data(tag=tag, probe_name=probe_name, sample_name=sample_name,
                                    use_qudi_savescheme=use_qudi_savescheme, root_path=root_path, 
                                    daily_folder=daily_folder, timestamp=timestamp)

        if self._sg_save_to_gwyddion:
            filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + tag + '_QAFM.gwy') 

            # threaded
            self.start_save_to_gwyddion(dataobj=data,
                                          gwyobjtype='qafm',filename=os.path.join(save_path,filename))

            # main thread, for debugging
            #self._save_to_gwyddion(dataobj=data,gwyobjtype='qafm',filename=os.path.join(save_path,filename))
            self.increase_save_counter()


    def draw_figure(self, image_data_in, image_extent, scan_axis=None, cbar_range=None,
                    percentile_range=None, signal_name='', signal_unit='', corr_plane_coeff=None):

        # Prefix definition for SI units measurement, powers of 1000
        prefix = { -4: 'p', -3: 'n',         # prefix to use for powers of 1000
                   -2: r'$\mathrm{\mu}$', -1: 'm', 
                    0: '', 1:'k', 
                    2: 'M', 3: 'G', 
                    4: 'T'}

        if scan_axis is None:
            scan_axis = ['X', 'Y']

        # save image data with plane correction?
        if corr_plane_coeff is not None:
            image_data = self.tilt_correction(data= image_data_in, 
                                              x_axis= np.linspace(image_extent[0],image_extent[1],image_data_in.shape[1]),
                                              y_axis= np.linspace(image_extent[2],image_extent[3],image_data_in.shape[0]),
                                              C= corr_plane_coeff) 
            signal_name += ', tilt corrected' 
        else:
            image_data = image_data_in.copy()
            
        # Scale data, determine SI prefix 
        value_range =  [np.min(image_data), np.max(image_data)]
        n = floor(log10(max([abs(v) for v in value_range])))  // 3     # 1000^n 
        scale_fac = 1 / 1000**n

        # scale the data
        scaled_data = image_data*scale_fac
        c_prefix = prefix[n]    # data prefix

        # If no colorbar range was given, take full range of data
        if cbar_range is None:
            # no color bar range specified, determine from data min/max
            draw_cb_range = np.array(value_range)  # scale to the plot range

            # discard zeros if they are exactly the lowest value
            if np.isclose(draw_cb_range[0], 0.0):
                draw_cb_range[0] = image_data[np.nonzero(image_data)].min()
        else:
            # was already scaled
            draw_cb_range = np.array(cbar_range)
        
        draw_cb_range *= scale_fac

        # ------------------
        # coordinate scaling
        # ------------------
        # Scale axes values using SI prefix
        #prefix[-2] = 'u'  # use simple ascii for axes with 1000^-2
        image_dimension = image_extent.copy()
        if np.allclose(image_dimension, np.zeros_like(image_dimension), atol=0.0):
            n = 0
        else:
            n = floor(log10(max([abs(v) for v in image_dimension])))  // 3     # 1000^n 

        image_dimension = [v / 1000**n for v in image_dimension]
        x_prefix = y_prefix = prefix[n]

        self.log.debug(('image_dimension: ', image_dimension))

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, ax = plt.subplots()

        # Create image plot
        cfimage = ax.imshow(scaled_data,
                            cmap=plt.get_cmap(self._color_map), # reference the right place in qd
                            origin="lower",
                            vmin=draw_cb_range[0],
                            vmax=draw_cb_range[1],
                            interpolation='none',
                            extent=image_dimension
                            )

        ax.set_aspect(1)
        ax.set_xlabel(scan_axis[0] + ' position (' + x_prefix + 'm)')
        ax.set_ylabel(scan_axis[1] + ' position (' + y_prefix + 'm)')
        ax.spines['bottom'].set_position(('outward', 10))
        ax.spines['left'].set_position(('outward', 10))
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.get_xaxis().tick_bottom()
        ax.get_yaxis().tick_left()

        # Draw the colorbar
        cbar = plt.colorbar(cfimage, shrink=0.8)#, fraction=0.046, pad=0.08, shrink=0.75)
        cbar.set_label(f'{signal_name} ({c_prefix}{signal_unit})')

        # remove ticks from colorbar for cleaner image
        cbar.ax.tick_params(which=u'both', length=0)

        return fig


    def save_quantitative_data(self, tag=None, probe_name=None, sample_name=None,
                               use_qudi_savescheme=False, root_path=None, 
                               daily_folder=True, timestamp=None):

        save_path =  self.get_qafm_save_directory(use_qudi_savescheme=use_qudi_savescheme,
                                                  root_path=root_path,
                                                  daily_folder=daily_folder,
                                                  probe_name=probe_name,
                                                  sample_name=sample_name)

        if timestamp is None:
            timestamp = datetime.datetime.now()

        data = self.get_esr_data()

        # go basically through the esr_fw and esr_bw scans.
        for entry in data:
            parameters = {}
            parameters.update(data[entry]['params'])
            nice_name = data[entry]['nice_name']
            unit = data[entry]['si_units']

            parameters['Name of measured signal'] = nice_name
            parameters['Units of measured signal'] = unit

            figure_data = data[entry]['data']
            std_err_data = data[entry]['data_std']
            fit_data = data[entry]['data_fit']


            # check whether figure has only zeros as data, skip this then
            if not np.any(figure_data):
                self.log.debug(f'The data array "{entry}" contains only zeros and will be not saved.')
                continue

            # parameters['Data arrangement note'] =  'The save data contain directly the fluorescence\n'\
            #                                        f'signals of the esr spectrum in {unit}. Each i-th spectrum\n' \
            #                                        'was taken at position (x_i, y_k), where the top\n' \
            #                                        'most data correspond to (x_0, y_0) position \n' \
            #                                        '(the left lower corner of the image). For the\n'\
            #                                        'next spectrum the x_i index will be incremented\n'\
            #                                        'until it reaches the end of the line. Then y_k\n' \
            #                                        'is incremented and x_i starts again from the \n' \
            #                                        'beginning.'

            rows, columns, entries = figure_data.shape


            image_data = {}
            # reshape the image before sending out to save logic.
            image_data[f'ESR scan measurements with {nice_name} signal without axis.\n'
                        'The save data contain directly the fluorescence\n'
                       f'signals of the esr spectrum in {unit}. Each i-th spectrum\n'
                        'was taken at position (x_i, y_k), where the top\n' 
                        'most data correspond to (x_0, y_0) position \n'
                        '(the left lower corner of the image). For the\n'
                        'next spectrum the x_i index will be incremented\n'
                        'until it reaches the end of the line. Then y_k\n'
                        'is incremented and x_i starts again from the \n'
                        'beginning.'] = figure_data.reshape(rows*columns, entries)

            filelabel = f'esr_data_{entry}'

            if tag is not None:
                filelabel = f'{tag}_{filelabel}'

            fig = self._save_logic.save_data(image_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=None)

            self.increase_save_counter()

            image_data = {}
            # reshape the image before sending out to save logic.
            image_data[f'ESR scan std measurements with {nice_name} signal without axis.\n'
                        'The save data contain directly the fluorescence\n'
                       f'signals of the esr spectrum in {unit}. Each i-th spectrum\n'
                        'was taken at position (x_i, y_k), where the top\n' 
                        'most data correspond to (x_0, y_0) position \n'
                        '(the left lower corner of the image). For the\n'
                        'next spectrum the x_i index will be incremented\n'
                        'until it reaches the end of the line. Then y_k\n'
                        'is incremented and x_i starts again from the \n'
                        'beginning.'] = std_err_data.reshape(rows*columns, entries)

            filelabel = f'esr_data_std_{entry}'

            if tag is not None:
                filelabel = f'{tag}_{filelabel}'

            fig = self._save_logic.save_data(image_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=None)

            self.increase_save_counter()

            image_data = {}
            # reshape the image before sending out to save logic.
            image_data[f'ESR scan fits with {nice_name} signal without axis.\n'
                        'The save data contain directly the fluorescence\n'
                       f'signals of the esr spectrum in {unit}. Each i-th spectrum\n'
                        'was taken at position (x_i, y_k), where the top\n' 
                        'most data correspond to (x_0, y_0) position \n'
                        '(the left lower corner of the image). For the\n'
                        'next spectrum the x_i index will be incremented\n'
                        'until it reaches the end of the line. Then y_k\n'
                        'is incremented and x_i starts again from the \n'
                        'beginning.'] = fit_data.reshape(rows*columns, entries)

            filelabel = f'esr_data_fit_{entry}'

            if tag is not None:
                filelabel = f'{tag}_{filelabel}'

            fig = self._save_logic.save_data(image_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=None)
            self.increase_save_counter()

            if self._sg_save_to_gwyddion:
                filename_pfx = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + tag ) 
                self.start_save_to_gwyddion(dataobj=data[entry], gwyobjtype='esr',
                                            filename=os.path.join(save_path,f"{filename_pfx}_{entry}.gwy"))
                self.increase_save_counter()



    def increase_save_counter(self, ret_val=0):
        """ Update the save counter.

        @param int ret_val: save status from the save logic, if -1, then error
                            occured during save, if 0 then everything is fine,
                            not used at the moment
        """
        self.__data_to_be_saved += 1

    def decrease_save_counter(self, ret_val=0):
        """ Update the save counter.

        @param int ret_val: save status from the save logic, if -1, then error
                            occurred during save, if 0 then everything is fine.
                            
        """

        if ret_val == 0:

            with self.threadlock:
                self.__data_to_be_saved -= 1

            if self.__data_to_be_saved == 0:
                self.sigQAFMDataSaved.emit()
                self.sigObjDataSaved.emit()
                self.sigOptiDataSaved.emit()

    def get_save_counter(self):
        return self.__data_to_be_saved

    #FIXME: update the savelogic with the new method 'save_figure' to make this work
    #       then, uncomment the part of the code labeled with UNCOMMENT.
    @deprecated("Current method is not maintained, use 'save_qafm_data' method instead.")
    def save_all_qafm_figures(self, tag=None, probe_name=None, sample_name=None,
                       use_qudi_savescheme=False, root_path=None, 
                       daily_folder=True):

        scan_params = self.get_curr_scan_params()
        
        #scan_params = ['counts_fw','counts_bw','Height(Sen)_fw','Height(Sen)_bw'] #Tests for data obtained from .dat file

        if scan_params == []:
            self.log.warning('Nothing measured to be saved for the QAFM measurement. Save routine skipped.')
            self.sigQAFMDataSaved.emit()
            return

        save_path =  self.get_qafm_save_directory(use_qudi_savescheme=use_qudi_savescheme,
                                             root_path=root_path,
                                             daily_folder=daily_folder,
                                             probe_name=probe_name,
                                             sample_name=sample_name)

        data = {}
        for entry in scan_params:
            data[entry] = self.get_qafm_data()[entry]

        timestamp = datetime.datetime.now()

        fig = self.draw_all_qafm_figures(data)

        # save only total figure here
        # UNCOMMENT THIS:
        # filelabel = f'{tag}_QAFM'
        # self._save_logic.save_figure(fig, 
        #                              filepath=save_path, 
        #                              timestamp=timestamp,
        #                              filelabel=filelabel)

        for entry in scan_params:
            parameters = {}
            parameters.update(data[entry]['params'])
            nice_name = data[entry]['nice_name']
            unit = data[entry]['si_units']

            parameters['Name of measured signal'] = nice_name
            parameters['Units of measured signal'] = unit

            figure_data = data[entry]['data']
            image_extent = [data[entry]['coord0_arr'][0],
                            data[entry]['coord0_arr'][-1],
                            data[entry]['coord1_arr'][0],
                            data[entry]['coord1_arr'][-1]]

            axes = ['X', 'Y']

            cbar_range = data[entry]['display_range']

            parameters['display_range'] = cbar_range

            image_data = {}
            image_data[f'QAFM XY scan image of a {nice_name} measurement without axis.\n'
                       'The upper left entry represents the signal at the upper left pixel position.\n'
                       'A pixel-line in the image corresponds to a row '
                       f'of entries where the Signal is in {unit}:'] = figure_data

            filelabel = f'QAFM_{entry}'

            if tag is not None:
                filelabel = f'{tag}_{filelabel}'

            fig = self._save_logic.save_data(image_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t')

            # prepare the full raw data in an OrderedDict:

            signal_name = data[entry]['nice_name']
            units_signal = data[entry]['si_units']

            raw_data = {}
            raw_data['X position (m)'] = np.tile(data[entry]['coord0_arr'], len(data[entry]['coord0_arr']))
            raw_data['Y position (m)'] = np.repeat(data[entry]['coord1_arr'], len(data[entry]['coord1_arr']))
            raw_data[f'{signal_name} ({units_signal})'] = data[entry]['data'].flatten()

            filelabel = filelabel + '_raw'

            self._save_logic.save_data(raw_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t')
            self.increase_save_counter()


    def draw_all_qafm_figures(self, qafm_data, scan_axis=None, cbar_range=None,
                    percentile_range=None, signal_name='', signal_unit=''):
        
        data = qafm_data #typically just get_qafm_data()

        #Starting the count to see how many images will be plotted and in which arrangement.
        nrows = 0
        ncols = 0
        counter = 0

        for entry in data:
            if np.mean(data[entry]['data']) != 0:
                counter = counter + 1

        if counter == 1:
            print('Try using draw_fig')
            pass

        #Simple arrangement, <3 images is 1 row, <7 images is 2, <13 images is 3 rows else 4 rows
        #Can be changed for any arrangement here.  
        if counter <= 2:
            nrows = 1
            ncols = counter
        else:
            if counter > 2 and counter <= 6:
                nrows = 2
                ncols = math.ceil(counter/nrows)
            else:
                if counter <= 12:
                    nrows = 3
                    ncols = math.ceil(counter/nrows)
                else:
                    nrows = 4
                    ncols = math.ceil(counter/nrows)

        fig, axs = plt.subplots(nrows = nrows, ncols = ncols, dpi=300, squeeze = True)

        plt.style.use(self._save_logic.mpl_qd_style)

        #Variable used to eliminate the empty subplots created in the figure. 
        axis_position_comparison = []
        for i in range(nrows):
            for j in range(ncols):
                axis_position_comparison.append([i,j])

        counter_rows = 0
        counter_cols = 0
        axis_position = []
        axis_position_container = []

        for entry in data:
            if '_fw' in entry or '_bw' in entry:
                data_entry = data[entry]
                image_data = data_entry['data']
                
                if np.mean(image_data) != 0:
                    
                    image_extent = [data_entry['coord0_arr'][0],
                                    data_entry['coord0_arr'][-1],
                                    data_entry['coord1_arr'][0],
                                    data_entry['coord1_arr'][-1]]
                    scan_axis = ['X','Y']
                    cbar_range = data_entry['display_range']
                    signal_name = data_entry['nice_name']
                    signal_unit = data_entry['si_units']
                    
                    # Scale color values using SI prefix
                    prefix = ['p', 'n', r'$\mathrm{\mu}$', 'm', '', 'k', 'M', 'G']
                    scale_fac = 1000**4 # since it starts from p
                    prefix_count = 0

                    draw_cb_range = np.array(cbar_range)*scale_fac
                    image_dimension = image_extent.copy()

                    if abs(draw_cb_range[0]) > abs(draw_cb_range[1]):
                        while abs(draw_cb_range[0]) > 1000:
                            scale_fac = scale_fac / 1000
                            draw_cb_range = draw_cb_range / 1000
                            prefix_count = prefix_count + 1
                    else:
                        while abs(draw_cb_range[1]) > 1000:
                            scale_fac = scale_fac/1000
                            draw_cb_range = draw_cb_range/1000
                            prefix_count = prefix_count + 1

                    scaled_data = image_data*scale_fac
                    c_prefix = prefix[prefix_count]

                    # Scale axes values using SI prefix
                    axes_prefix = ['', 'm',r'$\mathrm{\mu}$', 'n']  # mu = r'$\mathrm{\mu}$'
                    x_prefix_count = 0
                    y_prefix_count = 0

                    while np.abs(image_dimension[1] - image_dimension[0]) < 1:
                        image_dimension[0] = image_dimension[0] * 1000.
                        image_dimension[1] = image_dimension[1] * 1000.
                        x_prefix_count = x_prefix_count + 1

                    while np.abs(image_dimension[3] - image_dimension[2]) < 1:
                        image_dimension[2] = image_dimension[2] * 1000.
                        image_dimension[3] = image_dimension[3] * 1000.
                        y_prefix_count = y_prefix_count + 1

                    x_prefix = axes_prefix[x_prefix_count]
                    y_prefix = axes_prefix[y_prefix_count]
                    
                    #If there are only 2 images to plot, there is only 1 row, which makes the imaging 
                    #have only 1 axes making the creation of the image different than if there were more. 
                    if counter == 2:
                        
                        cfimage = axs[counter_cols].imshow(scaled_data,cmap=plt.get_cmap(self._color_map),
                                                            origin='lower', vmin= draw_cb_range[0],
                                                            vmax=draw_cb_range[1],interpolation='none',
                                                            extent=image_dimension)
                        
                        axs[counter_cols].set_aspect(1)
                        axs[counter_cols].set_xlabel(scan_axis[0] + ' position (' + x_prefix + 'm)')
                        axs[counter_cols].set_ylabel(scan_axis[1] + ' position (' + y_prefix + 'm)')
                        axs[counter_cols].spines['bottom'].set_position(('outward', 10))
                        axs[counter_cols].spines['left'].set_position(('outward', 10))
                        axs[counter_cols].spines['top'].set_visible(False)
                        axs[counter_cols].spines['right'].set_visible(False)
                        axs[counter_cols].get_xaxis().tick_bottom()
                        axs[counter_cols].get_yaxis().tick_left()

                        cbar = plt.colorbar(cfimage, ax=axs[counter_cols], shrink=0.8)
                        cbar.set_label(f'{signal_name} ({c_prefix}{signal_unit})')
                    
                    else:
            
                        cfimage = axs[counter_rows][counter_cols].imshow(scaled_data,cmap=plt.get_cmap(self._color_map),
                                                                        origin='lower', vmin= draw_cb_range[0],
                                                                        vmax=draw_cb_range[1],interpolation='none',
                                                                        extent=image_dimension)
                        
                        #Required since the qudi default font is too big for all of the subplots.
                        plt.rcParams.update({'font.size': 8})
                        axs[counter_rows][counter_cols].set_aspect(1)
                        axs[counter_rows][counter_cols].set_xlabel(scan_axis[0] + ' position (' + x_prefix + 'm)')
                        axs[counter_rows][counter_cols].set_ylabel(scan_axis[1] + ' position (' + y_prefix + 'm)')
                        axs[counter_rows][counter_cols].spines['bottom'].set_position(('outward', 10))
                        axs[counter_rows][counter_cols].spines['left'].set_position(('outward', 10))
                        axs[counter_rows][counter_cols].spines['top'].set_visible(False)
                        axs[counter_rows][counter_cols].spines['right'].set_visible(False)
                        axs[counter_rows][counter_cols].get_xaxis().tick_bottom()
                        axs[counter_rows][counter_cols].get_yaxis().tick_left()

                        cbar = plt.colorbar(cfimage, ax=axs[counter_rows][counter_cols], shrink=0.8)
                        cbar.set_label(f'{signal_name} ({c_prefix}{signal_unit})')
                    
                    axis_position = [counter_rows,counter_cols]
                    axis_position_container.append(axis_position)
                    
                    counter_cols = counter_cols + 1
                    
                    #Used to make sure the counters for columns and rows work correctly.
                    if counter_cols == ncols:
                        counter_rows = counter_rows + 1
                        counter_cols = 0
        
        #Removing the empty axis figures created at the end of all plotting.
        if counter > 2:
            for position in axis_position_comparison:
                if position not in axis_position_container:
                    axs[position[0]][position[1]].remove()

        plt.tight_layout()

        return fig

    def save_obj_data(self, obj_name_list, tag=None, probe_name=None, sample_name=None,
                      use_qudi_savescheme=False, root_path=None, 
                      daily_folder=None):

        if len(obj_name_list) == 0:
            self.sigObjDataSaved.emit()
            self.log.warning(f'Save aborted, no data to save selected!')

        # get the objective data
        data = self.get_obj_data()

        for entry in obj_name_list:
            if len(data[entry]['params']) == 0:
                self.sigObjDataSaved.emit()
                self.log.warning(f'Save aborted, no proper data in the image {entry}.')
                return

        save_path = self.get_confocal_path(use_qudi_savescheme=use_qudi_savescheme,
                                           root_path=root_path,
                                           daily_folder=daily_folder,
                                           probe_name=probe_name)

        timestamp = datetime.datetime.now()

        for entry in obj_name_list:
            parameters = {}
            parameters.update(data[entry]['params'])
            nice_name = data[entry]['nice_name']
            unit = data[entry]['si_units']

            parameters['Name of measured signal'] = nice_name
            parameters['Units of measured signal'] = unit

            figure_data = data[entry]['data']
            image_extent = [data[entry]['coord0_arr'][0],
                            data[entry]['coord0_arr'][-1],
                            data[entry]['coord1_arr'][0],
                            data[entry]['coord1_arr'][-1]]

            axes = [data[entry]['params']['axis name for coord0'], data[entry]['params']['axis name for coord1']]

            cbar_range = data[entry]['display_range']

            parameters['display_range'] = cbar_range

            fig = self.draw_figure(figure_data, image_extent, axes, cbar_range,
                                        signal_name=nice_name, signal_unit=unit)

            image_data = {}
            image_data[f'Objective scan image with a {nice_name} measurement without axis.\n'
                       'The upper left entry represents the signal at the upper left pixel position.\n'
                       'A pixel-line in the image corresponds to a row '
                       f'of entries where the Signal is in {unit}:'] = figure_data

            filelabel = entry

            if tag is not None:
                filelabel = f'{tag}_{filelabel}'

            fig = self._save_logic.save_data(image_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=fig)
            self.increase_save_counter()
            # prepare the full raw data in an OrderedDict:

            signal_name = data[entry]['nice_name']
            units_signal = data[entry]['si_units']

            raw_data = {}
            raw_data[f'{axes[0]} position (m)'] = np.tile(data[entry]['coord0_arr'], len(data[entry]['coord0_arr']))
            raw_data[f'{axes[1]} position (m)'] = np.repeat(data[entry]['coord1_arr'], len(data[entry]['coord1_arr']))
            raw_data[f'{signal_name} ({units_signal})'] = data[entry]['data'].flatten()

            filelabel = filelabel + '_raw'

            self._save_logic.save_data(raw_data,
                                       filepath=save_path,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t')

            self.increase_save_counter()

            # save objective data to gwyddion format
            if self._sg_save_to_gwyddion:
                filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + tag + '_obj_data.gwy') 
                self.start_save_to_gwyddion(dataobj=data,
                                            gwyobjtype='obj', filename=os.path.join(save_path,filename))
                self.increase_save_counter()
               


    def draw_obj_figure(self):
        pass

    def save_optimizer_data(self, tag=None, probe_name=None, sample_name=None, 
                            use_qudi_savescheme=False, root_path=None, 
                            daily_folder=None):

        # get the optimizer data
        data = self.get_opti_data()
        data_xy = data['opti_xy']
        data_z = data['opti_z']

        for entry in data:
            if len(data[entry]['params']) == 0:
                self.sigObjDataSaved.emit()
                self.log.warning(f'Save aborted, no proper data in the image {entry}.')
                return

        save_path = self.get_confocal_path(use_qudi_savescheme=use_qudi_savescheme,
                                           root_path=root_path,
                                           daily_folder=daily_folder,
                                           probe_name=probe_name)

        timestamp = datetime.datetime.now()

        parameters = {}
        parameters.update(data_xy['params'])
        nice_name = data_xy['nice_name']
        unit = data_xy['si_units']

        parameters['Name of measured signal'] = nice_name
        parameters['Units of measured signal'] = unit

        image_extent = [data_xy['coord0_arr'][0],
                        data_xy['coord0_arr'][-1],
                        data_xy['coord1_arr'][0],
                        data_xy['coord1_arr'][-1]]

        axes = [data_xy['params']['axis name for coord0'], data_xy['params']['axis name for coord1']]

        cbar_range = data_xy['display_range']

        parameters['display_range'] = cbar_range

        fig = self.draw_optimizer_figure(data_xy, data_z, image_extent, axes, cbar_range,
                                    signal_name=nice_name, signal_unit=unit)

        image_data = {}
        image_data[f'Objective scan image with a {nice_name} measurement without axis.\n'
                   'The upper left entry represents the signal at the upper left pixel position.\n'
                   'A pixel-line in the image corresponds to a row '
                   f'of entries where the Signal is in {unit}:'] = data_xy['data']

        filelabel = list(data)[0]

        if tag is not None:
            filelabel = f'{tag}_{filelabel}'

        fig = self._save_logic.save_data(image_data,
                                   filepath=save_path,
                                   timestamp=timestamp,
                                   parameters=parameters,
                                   filelabel=filelabel,
                                   fmt='%.6e',
                                   delimiter='\t',
                                   plotfig=fig)
        self.increase_save_counter()

        # prepare the full raw data in an OrderedDict:

        signal_name = data_xy['nice_name']
        units_signal = data_xy['si_units']

        raw_data = {}
        raw_data[f'{axes[0]} position (m)'] = np.tile(data_xy['coord0_arr'], len(data_xy['coord0_arr']))
        raw_data[f'{axes[1]} position (m)'] = np.repeat(data_xy['coord1_arr'], len(data_xy['coord1_arr']))
        raw_data[f'{signal_name} ({units_signal})'] = data_xy['data'].flatten()

        filelabel = filelabel + '_raw'

        self._save_logic.save_data(raw_data,
                                   filepath=save_path,
                                   timestamp=timestamp,
                                   parameters=parameters,
                                   filelabel=filelabel,
                                   fmt='%.6e',
                                   delimiter='\t')
        self.increase_save_counter()
        image_data = {}
        image_data[f'Objective scan image with a {nice_name} measurement in 1 axis.\n'
                   f'Where the Signal is in {unit}:'] = data_z['data']

        axes = [data_z['params']['axis name for coord0']]

        filelabel = list(data)[1]

        if tag is not None:
            filelabel = f'{tag}_{filelabel}'

        fig = self._save_logic.save_data(image_data,
                                   filepath=save_path,
                                   timestamp=timestamp,
                                   parameters=parameters,
                                   filelabel=filelabel,
                                   fmt='%.6e',
                                   delimiter='\t')
        self.increase_save_counter()
        # prepare the full raw data in an OrderedDict:

        parameters.update(data_z['params'])
        nice_name = data_z['nice_name']
        unit = data_z['si_units']
        signal_name = data_z['nice_name']
        units_signal = data_z['si_units']

        raw_data = {}
        raw_data[f'{axes[0]} position (m)'] = np.tile(data_z['coord0_arr'],1)      
        raw_data[f'{signal_name} ({units_signal})'] = data_z['data'].flatten()

        filelabel = filelabel + '_raw'

        self._save_logic.save_data(raw_data,
                                   filepath=save_path,
                                   timestamp=timestamp,
                                   parameters=parameters,
                                   filelabel=filelabel,
                                   fmt='%.6e',
                                   delimiter='\t')

        self.increase_save_counter()

        if self._sg_save_to_gwyddion:
            filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + tag + '_opti_data.gwy') 
            self.start_save_to_gwyddion(dataobj=data,gwyobjtype='opti',filename=os.path.join(save_path,filename))
            self.increase_save_counter()


    def draw_optimizer_figure(self, image_data_xy, image_data_z, image_extent, scan_axis=None, 
                              cbar_range=None, percentile_range=None, signal_name='', signal_unit=''):

        if scan_axis is None:
            scan_axis = ['X', 'Y']

        figure_data_xy = image_data_xy
        figure_data_z = image_data_z

        image_data_xy = image_data_xy['data']
        image_data_z = image_data_z['data']

        # If no colorbar range was given, take full range of data
        if cbar_range is None:
            cbar_range = [np.min(image_data_xy), np.max(image_data_xy)]

            # discard zeros if they are exactly the lowest value
            if np.isclose(cbar_range[0], 0.0):
                cbar_range[0] = image_data_xy[np.nonzero(image_data_xy)].min()

        # Scale color values using SI prefix
        prefix = ['p', 'n', r'$\mathrm{\mu}$', 'm', '', 'k', 'M', 'G']
        scale_fac = 1000**4 # since it starts from p
        prefix_count = 0

        draw_cb_range = np.array(cbar_range)*scale_fac
        image_dimension = image_extent.copy()

        if abs(draw_cb_range[0]) > abs(draw_cb_range[1]):
            while abs(draw_cb_range[0]) > 1000:
                scale_fac = scale_fac / 1000
                draw_cb_range = draw_cb_range / 1000
                prefix_count = prefix_count + 1
        else:
            while abs(draw_cb_range[1]) > 1000:
                scale_fac = scale_fac/1000
                draw_cb_range = draw_cb_range/1000
                prefix_count = prefix_count + 1

        scaled_data = image_data_xy*scale_fac
        c_prefix = prefix[prefix_count]

        # Scale axes values using SI prefix
        axes_prefix = ['', 'm', r'$\mathrm{\mu}$', 'n']  # mu = r'$\mathrm{\mu}$'
        x_prefix_count = 0
        y_prefix_count = 0

        #Rounding image dimension up to nm scale, to make sure value does not end at 0.9999
        while np.abs(round(image_dimension[1],9) - round(image_dimension[0],9)) < 1:
            image_dimension[0] = image_dimension[0] * 1000.
            image_dimension[1] = image_dimension[1] * 1000.
            x_prefix_count = x_prefix_count + 1

        while np.abs(round(image_dimension[3],9) - round(image_dimension[2],9)) < 1:
            image_dimension[2] = image_dimension[2] * 1000.
            image_dimension[3] = image_dimension[3] * 1000.
            y_prefix_count = y_prefix_count + 1

        x_prefix = axes_prefix[x_prefix_count]
        y_prefix = axes_prefix[y_prefix_count]

        #afm_scanner_logic.log.debug(('image_dimension: ', image_dimension))

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, axs = plt.subplots(ncols=2, squeeze=True)
        fig.subplots_adjust(wspace=0.1, left=0.02, right=0.98)
        ax = axs[0]
        axz = axs[1]

        # Create image plot for xy
        cfimage = ax.imshow(scaled_data,
                            cmap=plt.get_cmap(self._color_map), # reference the right place in qd
                            origin="lower",
                            vmin=draw_cb_range[0],
                            vmax=draw_cb_range[1],
                            interpolation='none',
                            extent=image_dimension,
                            )

        #Define aspects and ticks of xy image
        ax.set_aspect(1)
        ax.set_xlabel(scan_axis[0] + ' position (' + x_prefix + 'm)')
        ax.set_ylabel(scan_axis[1] + ' position (' + y_prefix + 'm)')
        ax.spines['bottom'].set_position(('outward', 10))
        ax.spines['left'].set_position(('outward', 10))
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.get_xaxis().tick_bottom()
        ax.get_yaxis().tick_left()

        # Draw the colorbar
        cbar = plt.colorbar(cfimage, shrink=0.8, ax=ax)#, fraction=0.046, pad=0.08, shrink=0.75)
        cbar.set_label(f'{signal_name} ({c_prefix}{signal_unit})')

        # remove ticks from colorbar for cleaner image
        cbar.ax.tick_params(which=u'both', length=0)

        #Create z plot using appropriate scale factors and units
        scale_factor_x = units.ScaledFloat(figure_data_z['coord0_arr'][0])
        scale_factor_x = scale_factor_x.scale_val

        scaled_data_x = figure_data_z['coord0_arr']/scale_factor_x

        scale_factor_y = units.ScaledFloat(figure_data_z['data'][0])
        scale_factor_y = scale_factor_y.scale_val

        scaled_data_y = figure_data_z['data']/scale_factor_y

        #Defining the same color map of the xy image for the points in the z plot
        cmap = plt.get_cmap(self._color_map)

        #Creating the initial z plot so that the multicolor dots are connected
        cfimage2 = axz.plot(scaled_data_x,scaled_data_y,'k', markersize=2, alpha=0.2)

        #Plotting each data point with a different color using the cmap
        for i in range(len(scaled_data_y)):
            if scaled_data_y[i] > scaled_data.max():
                point_color = cmap(int(np.rint(255)))
                axz.plot(scaled_data_x[i],scaled_data_y[i],'o',mfc= point_color, mec= point_color)
            else:
                point_color = cmap(int(np.rint(scaled_data_y[i]/scaled_data.max()*255)))
                axz.plot(scaled_data_x[i],scaled_data_y[i],'o',mfc= point_color, mec= point_color)

        axz.set_xlabel(figure_data_z['params']['axis name for coord0'] + ' position (' + r'$\mathrm{\mu}$' + 'm)')

        return fig


    def start_save_to_gwyddion(self, dataobj, gwyobjtype=None, 
                               filename=None, filelabel=None, 
                               timestamp=None, datakeys=None):
        """ 'save_data' signal instigator 
            - method depends on gwytype specified
        """
        if timestamp is None:
            timestamp = datetime.datetime.now()

        if filename is None:
            savefilename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' 
                                          + filelabel + f'_{gwyobjtype.upper()}.gwy') 
        else:
            savefilename = filename

        self.sigSaveDataGwyddion.emit(dataobj, gwyobjtype, savefilename, datakeys)


    def _save_to_gwyddion(self, dataobj, gwyobjtype=None, filename=None, datakeys=None):
        """ 'save_data' method selector (called in thread) 
            - method depends on gwytype specified
        """

        if gwyobjtype in self._gwyobjecttypes['imgobjects']:
            self._save_obj_to_gwyddion(dataobj=dataobj,filename=filename,datakeys=datakeys)
            self.sigSaveDataGwyddionFinished.emit(0)
        elif gwyobjtype in self._gwyobjecttypes['graphobjects']:
            self._save_esr_to_gwyddion(dataobj=dataobj,filename=filename,datakeys=datakeys)
            self.sigSaveDataGwyddionFinished.emit(0)
        else:
            self.log.error(f"SaveLogicGwyddion(): unknown gwyobjtype specified: {gwyobjtype}")
            self.sigSaveDataGwyddionFinished.emit(-1)


    def _save_obj_to_gwyddion(self,dataobj,filename,datakeys=None,gwytypes=['image','xyz']):
        """save_obj_to_gwyddion(): writes qudi data object to Gwyddion file
            input:  
            - dataobj: proteusQ data object of from dataobj['data_key']
            - filename: file path to save object
            - prefix:  name to be prefixed to all head objects
                
            requirements:
            dataobj['scan_type'] must contain keys {coord0[], coord1[], data[,], params[]}
        """
        
        # check for existance of valid object names
        if datakeys is None:
            datakeys = list(dataobj.keys())
        else:
            if isinstance(datakeys,str):
                datakeys = list(datakeys)
            alloweddatakeys = list(dataobj.keys())
            for n in datakeys:
                if not n in alloweddatakeys: 
                    self.log.error(f"_save_obj_to_gwyddion(): Invalid object name specified '{n}'")

        # check for existance of valid output types
        if not (gwytypes and set(gwytypes).issubset({'image', 'xyz'})): 
            self.log.error("_save_obj_to_gwyddion(): Incorrect Gwyddion output type specified")
                
        # overall object container
        objout = gwy.objects.GwyContainer()

        for dataki,datak in enumerate(sorted(datakeys, key=str.lower)):
            meas = dataobj[datak]

            # check that data is valid
            if not {'coord0_arr','coord1_arr','data'}.issubset(set(meas.keys())):
                continue 

            # check that there is non-trivial data (skip empty measurements)
            if np.sum(meas['data']) == 0.0:
                continue

            # transform data
            #scalefactor = meas['scale_fac']
            coord0 = meas['coord0_arr']
            coord1 = meas['coord1_arr']
            data_si = meas['data'] #* scalefactor
            xyz_data = np.array([x for j in range(coord1.shape[0]) 
                                for i in range(coord0.shape[0]) 
                                for x in (coord0[i], coord1[j], data_si[j,i])]) 

            params = meas['params']
            coord0_start = next(k for k in params.keys() if k.startswith('coord0_start'))
            coord0_stop = next(k for k in params.keys() if k.startswith('coord0_stop'))
            coord1_start = next(k for k in params.keys() if k.startswith('coord1_start'))
            coord1_stop = next(k for k in params.keys() if k.startswith('coord1_stop'))

            xy_units = coord0_start.split('(')[1].split(')')[0]
            z_units = meas['si_units']
            measname = datak + ":" + meas['nice_name']
            
            # encode to image
            img = gwy.objects.GwyDataField(data=data_si, si_unit_xy=xy_units, si_unit_z=z_units)
            img.xoff = params[coord0_start]
            img.xreal = params[coord0_stop] - params[coord0_start]
            img.yoff = params[coord1_start]
            img.yreal = params[coord1_stop] - params[coord1_start]

            # encode to xyz
            xyz = gwy.objects.GwySurface(data=xyz_data,si_unit_xy=xy_units,si_unit_z=z_units)

            # add to parent object 
            if 'image' in gwytypes: 
                # image types
                basekey = '/' + str(dataki) + '/data'
                objout[basekey + '/title'] = measname
                objout[basekey] = img
                
            if 'xyz' in gwytypes:
                # xyz types
                basekey = '/surface/' + str(dataki) 
                objout[basekey + '/title'] = measname
                objout[basekey] = xyz
                objout[basekey + '/preview'] = img
                objout[basekey + '/visible'] = True

                # comment meta data
                comm = gwy.objects.GwyContainer()
                for k,v in meas['params'].items():
                    if isinstance(v,(list,tuple)):
                        comm[k] = ",".join([str(vs) for vs in v])
                    else:
                        comm[k] = str(v)
                
                objout[basekey + '/meta'] = comm

        # write out file    
        if objout:
            objout.tofile(filename) 


    def _save_esr_to_gwyddion(self,dataobj,filename, datakeys=None,prefix=None):
        """
            save_esr_to_gwyddion(): writes esr data object to gwy container file
            input:  
            - dataobj: proteusQ data object of from dataobj['data_key']
            - filename: file path to save object
            - prefix:  name to be prefixed to all head objects
            
            requirements:
            dataobj must contain keys {coord0[], coord1[], coord2[],
                                        data[,,], data_std[,,], data_fit[,,], parameters[]}
        """

        # helper function for color generation
        # r/g/bspec = (min,max,number,startvalue)
        def colors(rspec=(0,1,10,0), gspec=(0,1,10,0), bspec=(0,1,10,0)):
            reds = np.linspace(*rspec[:3])
            reds =np.concatenate([reds[np.argwhere(reds >= rspec[-1])], 
                                reds[np.argwhere(reds < rspec[-1])]]).flatten()

            greens = np.linspace(*gspec[:3])
            greens =np.concatenate([greens[np.argwhere(greens >= gspec[-1])], 
                                greens[np.argwhere(greens < gspec[-1])]]).flatten()

            blues = np.linspace(*bspec[:3])
            blues =np.concatenate([blues[np.argwhere(blues >= bspec[-1])], 
                                blues[np.argwhere(blues < bspec[-1])]]).flatten()

            while True:
                for r in reds:
                    for g in greens:
                        for b in blues:
                            yield [('color.red', r), 
                                   ('color.green', g), 
                                   ('color.blue',b)]
        

        # check for existance of valid object names
        if datakeys is None:
            datakeys = list(dataobj.keys())
        else:
            if isinstance(datakeys,str):
                datakeys = list(datakeys)
            alloweddatakeys = list(dataobj.keys())
            for n in datakeys:
                if not n in alloweddatakeys:
                    self.log.error("_save_esr_to_gwyddion():Invalid object name specified '{n}'")

        # determine if anything is to be done
        if np.sum(dataobj['data']) == 0.0:
            return False

        # Output 
        # overall object container
        esrobj = gwy.objects.GwyContainer()

        # ESR mean data (quite dense)
        # create curves
        xdata = dataobj['coord2_arr']  # microwave frequency
        curves = []
        getcolors = colors((0,1,5,0.9),(0,1,5,0),(0,0.8,5,0))   # point color generator

        #  specifies 1st curve is points(1), 2nd curve is line(2), others hidden(0)
        ltypes = [1,2] 
        for j in range(dataobj['coord1_arr'].shape[0]):
            for i in range(dataobj['coord0_arr'].shape[0]):
                cols = next(getcolors)
    
                # measured data
                ydata = dataobj['data'][j,i,:]
                curve = gwy.objects.GwyGraphCurveModel(xdata=xdata, ydata=ydata)
                curve.update(cols)
                curve['description'] = f"coord[{j},{i}]"
                curve['type'] = ltypes.pop(0) if ltypes else 0
                curve['line_style'] = 0 
                curves.append(curve)

                # fit data
                ydata = dataobj['data_fit'][j,i,:]
                curve = gwy.objects.GwyGraphCurveModel(xdata=xdata, ydata=ydata)
                curve.update(cols)
                curve['description'] = f"coord[{j},{i}]_fit"
                curve['type'] = ltypes.pop(0) if ltypes else 0
                curve['line_style'] = 0 
                curves.append(curve)

        esrgraph = gwy.objects.GwyGraphModel()
        esrgraph['title'] = 'ESR: data per pixel'
        esrgraph['curves'] = curves
        esrgraph['x_unit'] = gwy.objects.GwySIUnit(unitstr='Hz')
        esrgraph['y_unit'] = gwy.objects.GwySIUnit(unitstr='c/s')
        esrgraph['bottom_label'] = 'Microwave Frequency'
        esrgraph['left_label'] = dataobj['nice_name'] + ' Count'

        esrobj['/0/graph/graph/1'] = esrgraph 
        esrobj['/0/graph/graph/1/visible'] = False 

        esrobj.tofile(filename) 
        return True


# Baseline correction functionality.
#TODO: put this in a more generic logic method structure, which can be used to
#      by other methods.

    @staticmethod
    def correct_plane(xy_data, zero_corr=False, x_range=None, y_range=None):
        """ Baseline correction algorithm, essentially based on solving an Eigenvalue equation.  

        @param np.array((N_row, M_col)) xy_data: 2D matrix
        @param bool zero_corr: Shift at the end of the algorithm the whole 
                               matrix by a specific offset, so that the smallest
                               value in the matrix is zero.
        @param list x_range: optional, containing the minimal and maximal value 
                             of the x axis of the matrix, if not provided, then
                             normalized values for the range are taken, i.e. 
                             values from 0 to 1. Both, x and y range needs to be
                             provided, otherwise the normalized values will be
                             taken.
        @param list y_range: optional, containing the minimal and maximal value
                             of the y axis of the matrix, if not provided, then
                             normalized values for the range are taken, i.e. 
                             values from 0 to 1. Both, x and y range needs to be
                             provided, otherwise the normalized values will be
                             taken.                           

        @return (mat_bc, C) 
            np.array((N_row, M_col)) mat: the baseline corrected matrix with 
                                          same, dimensions.
            np.array(3) C: containing the coefficients for the plane equation:
                            a*x + b*y + c = z 
                            => C = [a, b, c]
                            These can be used to generate the plane correction 
                            matrix. 
                            Note: Provide x_range and y_range to obtain have
                            meaningful values for C. If you are only interested
                            in a simple plane correction, then those values are
                            not required.
        
        similar to this solution:
        https://math.stackexchange.com/questions/99299/best-fitting-plane-given-a-set-of-points
        """
        
        # create at first a mash grid with the data, x and y are selected as 
        # normalized coordinates running from 0 to 1. Both arrays have to be 
        # specified, otherwise they are ignored.
        if (x_range is None) or (y_range is None):
            x_range = [0, 1]
            y_range = [0, 1]
    
        x_axis = np.linspace(x_range[0], x_range[1], xy_data.shape[1])
        y_axis = np.linspace(y_range[0], y_range[1], xy_data.shape[0])
        xv, yv = np.meshgrid(x_axis, y_axis)
        
        # flatten the data array in rows 
        data_rows = np.c_[xv.flatten(), yv.flatten() , xy_data.flatten()]

        # get the best-fit linear plane (1st-order):
        A = np.c_[data_rows[:,0], data_rows[:,1], np.ones(data_rows.shape[0])]
        # so the least square method tries to minimize the the vertical distance
        # from the points to the plane, i.e. to solve the equation A*x = b, or
        #       A * x = data_rows[:,2] 
          
        C,_,_,_ = lstsq(A, data_rows[:,2])    
        # C is essentially the minimize solution of , i.e.
        #       C = min( |data_rows[:,2] - A*x| ) 
        # where the coefficients in C represent a plane.

        # create a plane correction of the matrix:
        mat_corr = xy_data - (C[0]*xv + C[1]*yv + C[2])
        
        # make also a zero correction if required. This is not a baseline 
        # correction, it simply shifts the offset of the matrix such that the 
        # smallest entry in the matrix is zero. Note that an actual baseline 
        # corrected matrix would have a matrix mean value of zero). Applying 
        # this would shift the mean value of the matrix from zero.
        if zero_corr:
            mat_corr = mat_corr - mat_corr.min()
        
        return mat_corr, C


    @staticmethod
    def tilt_correction(data, x_axis, y_axis, C):
        """  Transforms the given measurement data by plane (tilt correction)
             assumes all data, as passed, is in original form.  The completeness 
             of the data matrix is determined on the spot

        @param np.array([[], []]): data:  a 2-dimensional array of measurements. 
                                          Incomplete measurements = 0.0.  
        @param np.array([])      x_axis:  x-coordinates (= 'coord0_arr')
        @param np.array([])      y_axis:  y-coordinates (= 'coord1_arr')
        @param np.array([])           C:  plane coefficients (f(x,y) = C[0]*x + C[1]*y + C[2])

        @return np.array([[],[]]) : data transformed by planar equation, 
        """
        # Note: operations are performed on copy of array..not the array itself

        data_o = data.copy()
        data_v = data_o[~np.all(data_o == 0.0, axis=1)]   # only the completed rows
        n_row = data_v.shape[0]                           # last index achieved
        xv, yv = np.meshgrid(x_axis, y_axis[:n_row])
        data_o[:n_row] = data_v - (C[0]*xv + C[1]*yv + C[2])

        return data_o


