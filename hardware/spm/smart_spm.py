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
import ctypes
import numpy as np
import time
import threading
import copy

from ctypes import c_float, c_void_p, c_int, c_char_p, c_char, c_bool, POINTER, byref
from qtpy import QtCore

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from enum import IntEnum

class CtypesEnum(IntEnum):
    """A ctypes-compatible IntEnum superclass. 

    An equivalent enum definition in C may look like

        typedef enum {
            ZERO,
            ONE,
            TWO
        } MyEnum;

    Note that the enum data type start from 0, this has to be take into account
    for the python implementation. To make the enum work with ctypes 
    implementation either the 'from_param' method or the '_as_parameter' 
    attribute needs to be set. """

    # a more detailed post here:
    # https://v4.chriskrycho.com/2015/ctypes-structures-and-dll-exports.html
    @classmethod
    def from_param(cls, obj):
        return int(obj)


class TScanMode(CtypesEnum):
    """ The actual implementation of the scan mode"""
    LINE_SCAN = 0
    POINT_SCAN = 1


class SmartSPM(Base):
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
    _test_line_scan = []
    _test_array_scan = []

    # Here are the data saved from the measurement routine
    #FIXME: Replace _meas_line_scan and _meas_array_scan with 
    #       _afm_scan_line and _afm_scan_array
    _meas_line_scan = []
    _meas_array_scan = []

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

    # internal library parameter
    MAX_SIG_NAME_LEN = 40 # max string allocation length for a signal name
    MAX_AXIS_ID_LEN = 8   # max length for name of one axis
    MAX_SIG_NUM = 30      # Maximal numbers of readout signals from controller

    #FIXME:
    # _curr_afm_pos = {'x': 0, 'y': 0, 'z': 0}
    _curr_afm_pos = [0, 0]  # just x and y
    #FIXME:
    #_curr_objective_pos = {'x': 0, 'y': 0, 'z': 0}
    _curr_objective_pos = [0, 0, 0]

    _curr_meas_mode = TScanMode.LINE_SCAN

    # keep a list of the created callbacks
    _TCallback_ref_dict = {}
    _TScanCallback_ref_dict = {}
    _TRestartCallback_ref_dict = {}

    # internal signal for data processing.
    _sig_scan_data = QtCore.Signal(int, ctypes.POINTER(c_float))

    # Line index counter for line scans
    _line_index_ctr = 0
    # waiting condition flag
    _wait_cond = QtCore.QWaitCondition()
    # a stop request:
    _stop_request = False
    # the current setting of the point trigger
    _ext_trigger_state = False

    _line_points = 0      # number of points in line 
    _line_time =   0.0    # time for line (='tforw' = pulse_length*_line_points)

    # Signals:
    # external signal: signature: (line number, number of _curr_meas_params, datalist)
    sigPixelClockStarted = QtCore.Signal(int, float)  # number of pulses, line time 
    sigLineFinished = QtCore.Signal(int, int, object)
    sigLineRestarted = QtCore.Signal()    # signal will be emitted if loss of 
                                        # connection error occurred.

    _libpath = ConfigOption('libpath', default='spm-library')   # default is the relative path
    _clientdll = ConfigOption('clientdll', default='remote_spm.dll')  # default aist-nt 

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

        self._lib = None

        if not os.path.isabs(self._libpath):   
            self._libpath = os.path.join(os.path.dirname(__file__), self._libpath)

        self._load_library(self._libpath, self._clientdll)

        self._spm_dll_ver = self.get_library_version()
        
        self.connect_spm()

        # prepare a test callback
        self.set_callback1()

        # prepare a test scan callback
        #self.set_scancallback1()

        # measure callbacks
        #self.set_scancallback2()
        self.set_scancallback3()

        self._prepare_library_calls()

        #self._sig_scan_data.connect(self.process_data)
        #self._sig_scan_data.connect(self.process_data2)
        self._sig_scan_data.connect(self.process_data3)

        # connect to the restart signal
        self.set_restart_line_callback()

        self._line_end_reached = False
        self.scan_forward = True

        # check compatability of client & server side interfaces 
        #self.check_interface_version()

        # initialize trigger state for normal scans
        self._ext_trigger_state = c_bool(False)

        # initialize new array values for plane scan
        self._ps_x_c = (c_float * 2)() # float array        
        self._ps_y_c = (c_float * 2)() # float array   
        self._ps_z_c = (c_float * 2)() # float array 

        # initialize the lift value
        self._lift_c = c_float(0.0)
        self._liftback_c = c_float(0.0)

        # initialize the lift value for 2pass mode
        self._lift_2pass_c = c_float(0.0)
        self._liftback_2pass_c = c_float(0.0)

        # initialize trigger state for 2pass scan
        self._trigger_pass1_c = c_bool(False)
        self._trigger_pass2_c = c_bool(False)

    def on_deactivate(self):
        """ Clean up and deactivate the spm module. """
        self.disconnect_spm()
        self._unload_library()
        
    def _load_library(self, path='', libname='remote_spm.dll'):
        """ Helper to load the spm library. 
        
        @params str path: absolute path to the folder, where library is situated.
        """

        if (path == '') or os.path.exists(path):
            this_dir = os.path.dirname(__file__)
            path = os.path.join(this_dir, 'spm-library') # default location of
                                                         # the library

        curr_path = os.path.abspath(os.curdir) # get the current absolute path
        
        #FIXME: Find out why the call CDLL cannot handle absolute paths and 
        #       only library names.
        # the load function requires that current path is set to library path
        os.chdir(path)
        self._lib = ctypes.CDLL(libname)
        os.chdir(curr_path) # change back to initial path

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

    def _prepare_library_calls(self):
        """ Set necessary argtypes and restype of function calls. """

        self._lib.Initialization.restype = c_bool
        
        self._lib.Finalization.restype = None

        self._lib.IsConnected.restype = c_bool

        # returns interface version number (client=remote_spm.dll, server=aist)
        # for server interfaces less than aist 3.5.150, ServerInterfaceVersion() returns -1
        self._lib.ServerInterfaceVersion.restype = c_int
        self._lib.ClientInterfaceVersion.restype = c_int
        self._lib.IsServerCompatible.restype = c_bool

        self._lib.SendLogMessage.argtypes = [c_char_p, c_char_p]
        self._lib.SendLogMessage.restype = None

        self._lib.SignalsList.argtypes = [c_void_p, c_void_p]
        self._lib.SignalsList.restype = c_int

        self._lib.AxisRange.argtypes= [c_char_p]
        self._lib.AxisRange.restype = c_float

        self._lib.AxisPosition.argtypes = [c_char_p]
        self._lib.AxisPosition.restype = c_float

        self._lib.SetAxisPosition.argtypes = [c_char_p, POINTER(c_float), c_float]
        self._lib.SetAxisPosition.restype = c_bool

        # The argtypes of SetAxesPositions need to be defined for each call, 
        # since the array varies in size
        self._lib.SetAxesPositions.restype = c_bool

        self._lib.AxisSetpoint.argtypes = [c_char_p]
        self._lib.AxisSetpoint.restype = c_float

        self._lib.SignalsList.argtypes = [POINTER((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM), 
                                          POINTER((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM)]
        self._lib.SignalsList.restype = c_int

        self._lib.SetupScanCommon.argtypes = [c_char_p, 
                                              c_int, 
                                              TScanMode, 
                                              c_int, 
                                              POINTER((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM)]
        self._lib.SetupScanCommon.restype = c_bool                          

        self._lib.SetupScanLine.argtypes = [c_float, c_float, 
                                            c_float, c_float,
                                            c_float, c_float]
        self._lib.SetupScanLine.restype = c_bool

        #self._lib.ExecScanPoint.argtypes = [POINTER(c_int), POINTER(c_float)]
        self._lib.ExecScanPoint.restype = c_bool

        self._lib.SetTriggering.argtypes = [c_bool]
        self._lib.SetTriggering.restype = c_bool

        self._lib.ProbeSweepZ.restype = c_bool

        self._lib.ProbeLift.argtypes = [c_float, c_float]
        self._lib.ProbeLift.restype = c_bool

        self._lib.ProbeLand.restype = c_bool

        self._lib.FinitScan.restype = None

        self._lib.ProbeLand2.restype = c_bool

        # self._lib.SetupScanLineXYZ.argtypes = [c_float, c_float, 
        #                                        c_float, c_float, 
        #                                        c_float, c_float,
        #                                        c_float, c_float, c_float]
        # self._lib.SetupScanLineXYZ.restype = c_bool

        self._lib.SetupPlaneScan.argtypes = [c_int, c_int, 
                                             POINTER((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM)]
        self._lib.SetupPlaneScan.restype = c_bool   

        self._lib.SetPlanePoints.argtypes = [c_int, POINTER(c_float), 
                                             POINTER(c_float), POINTER(c_float)]
        self._lib.SetPlanePoints.restype = c_bool

        self._lib.SetPlaneLift.argtypes = [c_float, c_float]
        #FIXME: test the return parameter
        #self._lib.SetPlaneLift.restype = None

        self._lib.SetupScan2Pass.argtypes = [c_int, c_int, c_int, 
                                             POINTER((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM)]
        self._lib.SetupScan2Pass.restype = c_bool   

        self._lib.Setup2PassLine.argtypes = [c_float, c_float, c_float, c_float,
                                             c_float, c_float, c_float]
        self._lib.Setup2PassLine.restype = c_bool  

        self._lib.Set2PassLift.argtypes = [c_float, c_float]
        #FIXME: test the return parameter
        #self._lib.Set2PassLift.restype = None 
        
        self._lib.Set2PassTriggering.argtypes = [c_bool, c_bool]
        #FIXME: test the return parameter
        #self._lib.Set2PassTriggering.restype = None             

    def _unload_library(self):
        if hasattr(self, '_lib'):
            del self._lib
    
    def is_connected(self):
        return bool(self._lib.IsConnected())

    def server_interface_version(self):
        if hasattr(self, '_lib') and self.is_connected():
            # returns -1 if servers software is < 3.5.150
            return self._lib.ServerInterfaceVersion()
        else:
            return -2 

    def client_interface_version(self):
        return self._lib.ClientInterfaceVersion()

    def is_server_compatible(self):
        if hasattr(self, '_lib') and self.is_connected():
            return self._lib.IsServerCompatible()

    def connect_spm(self):
        """ Establish connection to SPM-software. 
        
        @return bool: indicates whether initialization was successful.
        """

        ret_val = bool(self._lib.Initialization())

        if ret_val:
            self.log.info('SPM Stage connected.')
        else:
            self.log.warning('NOT possible to connect to the SPM stage.')

        return ret_val
    
    def disconnect_spm(self):
        """ Disconnection from the SPM-software. """
        self._lib.Finalization()    # no return value
        return 0

    def check_interface_version(self,pause=None):
        """ Compares interface version of client and server interface"""
        if not self.is_connected(): 
            self.log.debug("Attempted to query SPM interface version before connected")
            return False

        #FIXME: a bad hack to get around thread lock
        if pause is not None:
            time.sleep(pause)

        isCompatible = self.is_server_compatible()

        if not isCompatible:
            clientv = self.client_interface_version()
            serverv = self.server_interface_version()
            if serverv < 0:
                self.log.warning(f"SPM server side is old and inconsistent with client side; use {self._spm_dll_ver}")
            elif clientv > serverv:
                self.log.warning(f"SPM client > server interface; possible incompatibilities; use aist version= {self._spm_dll_ver}")
            elif clientv < serverv:
                self.log.warning(f"SPM server > client interface; possible incompatibilities; use aist version= {self._spm_dll_ver}")

        return isCompatible 

    def send_log_message(self, message):
        """ Send a log message to the spm software.

        @params str message: a specific text to be transmitted to spm software

        Send the message to display in the Log-window in the SPM-software. After
        get the message, the SPM-software responses; the response-message data 
        is returned to the "response" char-array  (a '\0'-terminated string).
        """

        mess = message.encode('utf-8')  # create binary representation of string
        
        # the response function requires a zero terminated pointer
        # in python this is an empty string
        resp = ctypes.c_char_p(b"") 
        self._lib.SendLogMessage(mess, resp)
        self.log.debug(('Response: ', resp.value.decode()))
        
        return resp.value.decode()

    def create_test_TCallback(self):
        """ Create a callback function which receives a number to be printed.

        @return: reference to a function with simple printout.
        """
        
        def print_message(num): 
            print('The number:', num) 
            self.log.info(f'New number appeared: {num}')
            return 0
        
        return print_message

    def set_TCallback(self, func):
        """ Set the callback function. 
        
        @param reference func: a reference to a function with the following
                               signature: 

                def func_name(int):
                    # do something
                    return 0

        @return int: status variable with the meaning
                        0 = call failed
                        1 = call successful
        """

        # This is the callback signature:
        # typedef void ( *TCallback )( int proc_index );
        callback_type = ctypes.CFUNCTYPE(c_void_p, c_int)
        
        # Very important! the reference to the callback function has to be
        # saved to prevent it from getting caught by the garbage collector
        self._TCallback_ref_dict[func.__name__] = callback_type(func)

        return self._lib.SetCallback(self._TCallback_ref_dict[func.__name__])
    
    def set_callback1(self):
        """ Set a created callback for testing purpose. """

        test_TCallback = self.create_test_TCallback()
        self.set_TCallback(test_TCallback)

    def test_callback(self):
        """ Perform test call of the registered TCallback.

        The test call looks like:
            5 calls of the provided user function registered by the method 
            "set_TCallback". The interval between calls is of 2 seconds.
            Each time the transferred index (“proc_index” variable of the 
            TCallback function) is increased.

        @return int: status variable with the meaning
                        0 = call failed
                        1 = call successful
        """
        return self._lib.InitTestCallback()
    
    def set_TScanCallback(self, func):
        """ Set the scanner callback function. 

        @param reference func: a reference to a function with the following
                               signature:
        
                def func_name(size, arr):
                    # int size: size of the passed array
                    # float arr[size]: float array of size 'size'.
                    
                    # do something
                    
                    return 0
        
        @return int: status variable with: 0 = call failed, 1 = call successfull
        """

        #typedef void ( *TScanCallback )( int size, float * vals );
        # the last value (float * vals ) is an array of values, where size
        # determines its size.
        scan_callback_type = ctypes.CFUNCTYPE(c_void_p, 
                                              c_int, 
                                              POINTER(c_float))
                                              
        # the trick is that capitals 'POINTER' makes a type and 
        # lowercase 'pointer' makes a pointer to existing storage. 
        # You can use byref instead of pointer, they claim it's faster. 
        # I like pointer better because it's clearer what's happening.
        self._TScanCallback_ref_dict[func.__name__] = scan_callback_type(func)
        
        
        return self._lib.SetScanCallback(self._TScanCallback_ref_dict[func.__name__])


    def set_TRestartLineCallback(self, func):
        """ Set the restart line callback function. 

        @param reference func: a reference to a function with the following
                               signature:
        
                def func_name():
                    # no arguments expected.
                    
                    # do something
                    
                    return 0

        @return int: status variable with: 0 = call failed, 1 = call successful

        Called back after self.scan_line(), when PC-controller connection error 
        occurs. Call implies that the scan-line execution was restarted. This 
        call may occur at any moment after self.scan_line(), say, even during 
        movement to first scan point, i.e. when there was no trigger pulses 
        performed and no AFM signals points were measured/sent.
        """

        # typedef void ( *TRestartLineCallback )();
        restart_callback_type = ctypes.CFUNCTYPE(c_void_p)

        # store the reference to the callback, so that it does not get removed
        # by python
        self._TRestartCallback_ref_dict[func.__name__] = restart_callback_type(func)

        return self._lib.SetRestartLineCallback(self._TRestartCallback_ref_dict[func.__name__])

    def create_restart_callback(self):
        """ Create a callback function which can be registered.

        @return: reference to a function connected to emit functionality.
        """

        def restart_linescan():
            self.log.warning('Loss of connection occurred! Check if reconnect was successful.')
            self.sigLineRestarted.emit()
            return 0

        return restart_linescan

    def set_restart_line_callback(self):
        """ Setup the restart line callback functionality. 

        Call this higher order function to connect a Restart event to the 
        emission of the signal from sigLineRestarted.
        """
        # prepare a test scan callback
        TRestartCallback = self.create_restart_callback()
        self.set_TRestartLineCallback(TRestartCallback)

    def create_test_TScanCallback(self):
        """ Create a callback function which receives a number and a float array.

        @return: reference to a function with simple scan_val printout.
        """

        
        def print_scan_values(size, arr):
            """ Scan scan values."""
            
            arr = [arr[entry] for entry in range(size)]
            print(f'Received, num: {size}, arr: {arr}')
            self.log.info(f'Received, num: {size}, arr: {arr}')

            return 0

        return print_scan_values

    def create_measure_TScanCallback(self):
        """ Create a callback function which receives a number and a float array.

        @return: reference to a function with simple scan_val printout and save
                 to array.
        """

        
        def save_scan_values(size, arr_new):
            """ Scan scan values."""
            
            if size == 0:
                print('Line scan finished')
                self._line_counter += 1
                self._test_array_scan.append(self._test_line_scan)
                self._test_line_scan = []
                return 0

            arr = [arr_new[entry] for entry in range(size)]
            self._test_line_scan.extend(arr)

            return 0

        return save_scan_values
    
    def create_measure_TScanCallback2(self):
        """ Create the actual callback function which receives a number and a 
            float array.

        @return: reference to a function with simple scan_val printout.
        """

        def transfer_via_signal(size, arr):
            """ The received callback emits immediately a signal with data. 
                Connect to this signal the data processing.
            """
            self._sig_scan_data.emit(size, arr)
            return 0

        return transfer_via_signal


    def set_scancallback1(self):
        
        # prepare a test scan callback
        test_TScanCallback = self.create_test_TScanCallback()
        self.set_TScanCallback(test_TScanCallback)

    def set_scancallback2(self):
        
        # prepare a measure scan callback 
        measure_TScanCallback = self.create_measure_TScanCallback()
        self.set_TScanCallback(measure_TScanCallback)

    def set_scancallback3(self):
        
        # prepare a measure scan callback 
        measure_TScanCallback = self.create_measure_TScanCallback2()
        self.set_TScanCallback(measure_TScanCallback)

    def test_scan_callback(self):
        """ Perform test call of the registered TScanCallback.

        The test call looks like:
            7 calls of the provided user function registered by the methods
            "set_scancallback1", "set_scancallback2" or "set_scancallback3". 
            The interval between calls is of 1 second.
            Each time the "vals" arrays are of different size for each call and 
            it starts with size 1, containing numbers within the range of [0,1],
            i.e. the 7 calls should look like:
                call 1: [0.0]
                call 2: [0.0, 0.5]
                call 3: [0.0, 0.33333334, 0.66666668]
                call 4: [0.0, 0.25, 0.5, 0.75]
                call 5: [0.0, 0.2, 0.4, 0.6, 0.8]
                call 6: [0.0, 0.16666667, 0.33333334, 0.5, 0.66666668, 0.83333331]
                call 7: [0.0, 0.14285714, 0.28571429, 0.42857143, 0.57142859, 0.71428573, 0.85714286]

            precision is float. This corresponds to the python calls:
                np.linspace(0, 1, 1, endpoint=False)
                np.linspace(0, 1, 2, endpoint=False)
                np.linspace(0, 1, 3, endpoint=False)
                np.linspace(0, 1, 4, endpoint=False)
                np.linspace(0, 1, 5, endpoint=False)
                np.linspace(0, 1, 6, endpoint=False)
                np.linspace(0, 1, 7, endpoint=False)

        @return int: status variable with the meaning
                        0 = call failed
                        1 = call successful
        """
        return self._lib.InitTestScanCallback()


    @QtCore.Slot(int, ctypes.POINTER(c_float))
    def process_data(self, size, arr):
        """ Process the received data from a signal. """
    
        if size == 0:
            print(f'Line {self._line_counter} finished.')

            self.sigLineFinished.emit(self._line_counter, 
                                      len(self._curr_meas_params),
                                      self._meas_line_scan)
            self._line_counter += 1
            self._meas_array_scan.append(self._meas_line_scan)
            self._meas_line_scan = []
            self._line_end_reached = True
            return 0


        # extend the _meas_line_scan array by the amount of measured data.
        self._meas_line_scan.extend([arr[entry] for entry in range(size)])

        return 0


    @QtCore.Slot(int, ctypes.POINTER(c_float))
    def process_data2(self, size, arr):
        """ Process the received data from a signal. """
    
        if size == 0:
            #print(f'Line {self._line_counter} finished.')
            #self.log.info(f'Line {self._line_counter} finished.')
            self._line_counter += 1
            self._line_end_reached = True
            return 0

        # extend the _meas_line_scan array by the amount of measured data.
        self._meas_line_scan.extend([arr[entry] for entry in range(size)])

        return 0

    @QtCore.Slot(int, ctypes.POINTER(c_float))
    def process_data3(self, size, arr):
        """ Process the received data from a signal.

        @param int size: the length of the data stream
        @param ctypes.POINTER arr: pointer to a c like float array

        This processing should be faster, since the size of the data array is
        pre-allocated.
        """

        if size == 0:
            # print(f'Line {self._line_counter} finished.')
            # self.log.info(f'Line {self._line_counter} finished.')
            self._line_counter += 1
            self._line_end_reached = True
            self._wait_cond.wakeAll()
            self._line_index_ctr = 0
            return 0

        # extend the _meas_line_scan array by the amount of measured data.
        for entry in range(size):
            self._meas_line_scan[self._line_index_ctr] = arr[entry]
            self._line_index_ctr += 1
        return 0


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
                ret_val = self._lib.AxisRange(axis_label.encode()) # value in um
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
                ret_val = self._lib.AxisRange(axis_label.encode()) # value in um
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
                ret_val = self._lib.AxisPosition(axis_label.encode()) # value in um
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
                ret_val = self._lib.AxisPosition(axis_label.encode()) # value in um
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

        self._set_scanner_axes(valid_axis, move_time)

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

        self._set_scanner_axes(valid_axis, move_time)

        return self.get_objective_scanner_pos(list(valid_axis))

    def _set_scanner_axes(self, valid_axis_dict, move_time):
        """ General method without checks to set axis position. 

        @param dict valid_axis_dict: dictionary with valid axis with associated 
                                     absolute position in m. The axis labels are
                                     capitalized or lower case, possible keys:
                                        ['X', 'x', 'Y', 'y', 'Z', 'z']
                                     and postfixed with a '1' (sample scanner) 
                                     or a '2' (objective scanner). Example for 
                                     moving X1 and Y1 simultaneously:
                                        {'X1': 15e-6, 'Y1': 20e-6}

        Note1: this is an internal method and should not be used for production 
               use.
        Note2: This method takes always the shortest path to the target 
               position and does not set the coordinates one by one.
        """

        sweepTime = c_float(move_time)
        axesCnt = c_int(len(valid_axis_dict))

        if axesCnt == 1:
            axis_label = list(valid_axis_dict)[0]
            pos_val = valid_axis_dict[axis_label]
            ret = self._set_scanner_axis(axis_label, pos_val, move_time)
            
        else:

            # create zero terminated strings according to the positions, 
            # each of size 8 characters, with the number of axes.
            axesIds = ((c_char * self.MAX_AXIS_ID_LEN) * axesCnt.value)()
            
            # create float array
            values = (c_float * axesCnt.value)() # here are the values stored

            for index, axis_label in enumerate(valid_axis_dict):
                axesIds[index].value = axis_label.encode()
                values[index] = valid_axis_dict[axis_label]*1e6 # spm library expects um.

            self._lib.SetAxesPositions.argtypes = [c_int, 
                                                  POINTER((c_char * self.MAX_AXIS_ID_LEN) * axesCnt.value), 
                                                  POINTER(c_float * axesCnt.value), 
                                                  c_float]

            ret = self._lib.SetAxesPositions(axesCnt, 
                                             byref(axesIds), 
                                             byref(values), 
                                             sweepTime)
                
        if not ret:
            #self.log.error(f'Library Call to set position for the axis "{list(valid_axis_dict)}" with position {(np.array(list(valid_axis_dict.values))*1e6).round(2):.2f}um failed.')
            self.log.error(f'Library Call to set position for the axis "{list(valid_axis_dict)}" with position {list(valid_axis_dict.values())}um failed.')

        return ret


    def _set_scanner_axis(self, valid_axis, pos, move_time):
        """ Set just one axis of the scanner and move to this point.

        @param str valid_axis: a valid name for one of the axis. The axis labels
                               are capitalized or lower case, possible strings
                                        ['X', 'x', 'Y', 'y', 'Z', 'z']
                               and postfixed with a '1' (sample scanner) or a 
                               '2' (objective scanner). 
        @param float pos: the actual position where to move in m.
        @param float move_time: time for the movement process in seconds.

        @return: boolean value if call was successful or not.

        Example call:  _set_scanner_axis('X1', 5e-6, 0.5)

        """

        pos_val = c_float(pos*1e6) # spm library needs position in um
        sweepTime = c_float(move_time)
        return self._lib.SetAxisPosition(valid_axis.encode(), 
                                         byref(pos_val), 
                                         sweepTime)

    def _obtain_axis_setpoint(self, axes):
        """ Obtain the future/next value in the callback for the selected axes.

        @param str axes: The name of one of the possible axes, valid values are
                         within the list:
                            ['X', 'x', 'Y', 'y', 'Z', 'z', 'X1', 'x1', 'Y1', 'y1',
                             'Z1', 'z1', 'X2', 'x2', 'Y2', 'y2', 'Z2', 'z2']
        
        Unlike the _set_scanner_axes method, this function does not return the 
        current coordinate, but its future value, which will occur at the end of
        some ongoing procedure in the SPM-software. The method is of need for 
        TCallback procedure implementation.

        """

        axes = axes.upper() # convert to uppercase

        ret = 0
        if axes in self.VALID_AXIS:
            ret = self._lib.AxisSetpoint(axes.encode())

        return ret


    def get_signal_list(self):
        """ The function returns signal list with their entry.
        
        @return tuple(names, units):
            list names: list of strings names for available parameters
            list units: list of the associated units to the names list.

        Since signals number may be about MAX_SIG_NUM=15-30, declare 
        "names" and "units" as:
            char names[MAX_SIG_NUM][MAX_SIG_NAME_LEN]
            char units[MAX_SIG_NUM][MAX_SIG_NAME_LEN]
        """

        #names_buffers = [ctypes.create_string_buffer(40) for i in range(15)]
        #names_pointers = (ctypes.c_char_p*15)(*map(ctypes.addressof, names_buffers))

        # create 15 zero terminated strings, each of size 40 characters. 
        names_buffers = ((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM)()

        #units_buffers = [ctypes.create_string_buffer(40) for i in range(15)]
        #units_pointers = (ctypes.c_char_p*15)(*map(ctypes.addressof, units_buffers))

        # create 15 zero terminated strings, each of size 40 characters. 
        units_buffers = ((c_char * self.MAX_SIG_NAME_LEN) * self.MAX_SIG_NUM)()
        
        sig_nums = self._lib.SignalsList(byref(names_buffers), 
                                         byref(units_buffers))
        
        # if sig_nums = 0, then an error occurred, this is caught here.
        if not bool(sig_nums):
            self.log.warning('Call to request the SignalsList was not successful!')

        names = ['']*sig_nums
        units = ['']*sig_nums
        
        for index in range(sig_nums):
            names[index] = names_buffers[index].value.decode()
            units[index] = units_buffers[index].value.decode()
    
        return names, units
    

    def setup_spm(self, plane='XY', line_points=100, meas_params=[],
                  scan_mode=TScanMode.LINE_SCAN):
        """ Setting up all required parameters to perform a scan.
        
        @param str plane: The selected plane, possible options:
                            XY, XZ, YZ for sample scanner
                            X2Y2, X2Z2, Y2Z2 for objective scanner
        @param int line_points: number of points to scan
        @param list meas_params: optional, list of possible strings of the 
                                 measurement parameter. Have a look at 
                                 MEAS_PARAMS to see the available parameters. 
                                 If nothing is passed, an empty string array 
                                 will be created.
        @param TScanMode scan_mode: The enum selection of the current scan mode.
                                    Possibilities are (<=> equivalent to number)
                                        TScanMode.LINE_SCAN  <=> 0
                                        TScanMode.POINT_SCAN <=> 1
        
        @return (status_variable, plane,  with: 
                       -1 = input parameter error 
                        0 = call failed, 
                        1 = call successful

        Every Scan procedure starts with this method. Declare "sigs" as 
            char sigs[N][MAX_SIG_NAME_LEN]; 
        where N >= sigsCnt.
        
        """

        sigs_buffers = self._create_meas_params(meas_params)
        # extract the actual set parameter:
        self._curr_meas_params = [param.value.decode() for param in sigs_buffers]

        sigsCnt = c_int(len(sigs_buffers))

        if plane not in self.PLANE_LIST:
            self.log.error(f'The passed plane "{plane}" is not a suitable '
                           f'parameter. Please choose one from: '
                           f'{self.PLANE_LIST}.')
            self._curr_plane = ''
            return (-1, self._curr_plane,  self._curr_meas_params)

        self._curr_plane = plane 

        plane_id = plane.encode('UTF-8')
        plane_id_p = c_char_p(plane_id)
        
        self._line_points = line_points
        line_points_c = c_int(line_points)
        
        if not isinstance(scan_mode, TScanMode) and not isinstance(scan_mode, int):
            scan_mode = TScanMode.LINE_SCAN
            self.log.error(f'ScanMode for method setup_spm is not valid. Setting to default value: {scan_mode_temp.name}.')

        elif isinstance(scan_mode, int):

            scan_mode_temp = None
            for entry in TScanMode:
                if entry.value == scan_mode:
                    scan_mode_temp = entry  # set the proper scan mode

            if scan_mode_temp is None:
                scan_mode_temp = TScanMode.LINE_SCAN
                self.log.warning(f'Passed number "{scan_mode}" for ScanMode is unknown for method setup_spm. Setting to default value: {scan_mode_temp.name} with number {scan_mode_temp.value}')
                scan_mode_temp = TScanMode._meas_line_scan # default value

            scan_mode = scan_mode_temp

        self._curr_meas_mode = scan_mode # set current measurement mode

        self._lib.SetupScanCommon.argtypes = [c_char_p,
                                             c_int,
                                             TScanMode,
                                             c_int,
                                             POINTER((c_char * self.MAX_SIG_NAME_LEN) * sigsCnt.value)]

        ret_val = self._lib.SetupScanCommon(plane_id_p, 
                                            line_points_c, 
                                            scan_mode, 
                                            sigsCnt, 
                                            byref(sigs_buffers))

        # in case a line measurement is performed, pre-allocate the required array
        self._meas_line_scan = np.zeros(line_points*len(self._curr_meas_params),
                                        dtype=np.float)

        self._stop_request = False

        if ret_val == 0:
            self.log.error(f'Library call "SetupScanCommon", with parameters '
                           f'"{plane}", "{line_points}", '
                           f'"{self._curr_meas_params}" failed.')

        return (ret_val, self._curr_plane,  copy.copy(self._curr_meas_params))
    

    def _create_meas_params(self, meas_params):
        """ Helper method, create a zero terminated string buffers with ctypes 

        @param list meas_params: list of string names for the parameters. Only
                                 names are allowed with are defined in
                                 self.MEAS_PARAMS.

        @return ctypes.c_char_Array: a corresponding array to the provides 
                                     python list of strings

        A manual way of creating the meas_params without utilizing this function
        would be (in case of 4 parameters):
            sigs_buffers = ((ctypes.c_char * 40) * 0)()
            sigs_buffers[0].value = b'Height(Dac)'
            sigs_buffers[1].value = b'Height(Sen)'
            sigs_buffers[2].value = b'Mag'
            sigs_buffers[3].value = b'Phase'
        """

        available_params = []

        for param in meas_params:
            if param in self.MEAS_PARAMS:
                available_params.append(param)
            else:
                self.log.debug(f'The provided measurement parameter '
                                 f'"{param}" is not a valid parameter from the '
                                 f'list {list(self.MEAS_PARAMS)}. Skipping it.')

        if available_params == []:
            self.log.debug(f'The provided list "{meas_params}" does not '
                           f'contain any measurement parameter which is '
                           f'allowed from this list: {list(self.MEAS_PARAMS)}.')

        # create c-like string array:
        names_buffers = ((c_char * 40) * len(available_params))()
        for index, entry in enumerate(available_params):
            names_buffers[index].value = entry.encode('utf-8')

        return names_buffers
    

    #FIXME: Check consistent naming of arguments: x_start, x_stop, y_start, y_stop
    #FIXME: check whether the input parameters for scan line are valid for the 
    #       current plane, maybe not directly to be checked in setup_scan_line.
    #
    def setup_scan_line(self, corr0_start, corr0_stop, corr1_start, corr1_stop, 
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

        self._line_end_reached = False

        # remember to convert to micrometer units, since the spm library uses
        # this.
        x0 = c_float(corr0_start*1e6)
        y0 = c_float(corr1_start*1e6)
        x1 = c_float(corr0_stop*1e6)
        y1 = c_float(corr1_stop*1e6)
        tforw = c_float(time_forward)
        tback = c_float(time_back)
        
        return self._lib.SetupScanLine(x0, y0, x1, y1, tforw, tback)
    
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
        self.sigPixelClockStarted.emit(self._line_points, self._line_time / self._line_points)

        return self._lib.ExecScanLine(c_float(int_time))

    def scan_point(self, num_params=None):
        """ After setting up the scanner perform a scan of a point. 

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

        if num_params is None:
            num_params = len(self._curr_meas_params)

        self.size_c = c_int()
        self.vals_c = (c_float * num_params)() # float array
        self._lib.ExecScanPoint(ctypes.byref(self.size_c), ctypes.byref(self.vals_c))

        return [self.vals_c[index] for index in range(self.size_c.value)]
    
    def finish_scan(self):
        """ It is correctly (but not abs necessary) to end each scan 
        process by this method. There is no problem for 'Point' scan, 
        performed with 'scan_point', to stop it at any moment. But
        'Line' scan will stop after a line was finished, otherwise 
        your software may hang until scan line is complete.

        @return int: status variable with: 0 = call failed, 1 = call successfull
        """
        return self._lib.FinitScan()


    def set_ext_trigger(self, trigger_state):
        """ Set up an external trigger after performing a line or point scan.

        @param bool trigger_state: declare whether enable (=True) or disable 
                                  (=False) triggering.

        This method has to be called once, after setup_spm, otherwise triggering
        will be disabled.

        Note: Point trigger is executed at the end of the measurement of each 
              scan-point, both for line- and for point-scan.
              Exception: When use ExecScanPoint function, point trigger is not 
                         performed. 
              One extra trigger is performed at the beginning of the measurement
              of first point of the line.
        """    
        self._ext_trigger_state = c_bool(trigger_state)
        return self._lib.SetTriggering(self._ext_trigger_state)

    def get_ext_trigger(self):
        """ Check whether external triggering is enabled.

        @return bool: True: trigger enabled, False: trigger disabled.
        """
        return self._ext_trigger_state.value

    def probe_sweep_z(self, start_z, stop_z, num_points, sweep_time, 
                      idle_move_time, meas_params=[]):
        """ Prepare the z sweep towards and from the surface away. 

        @param float start_z: start value in m, positive value means the probe 
                              goes up from the surface, a negative value will 
                              move it closer to the surface
        @param float stop_z: stop value in m, positive value means the probe 
                              goes up from the surface, a negative value will 
                              move it closer to the surface
        @param int num_points: number of points in the movement process
        @param float sweep_time: time for the actual z scan
        @param float idle_move_time: time for idle movement to prepare probe to
                                     the position from where measurement can 
                                     start. This can speed up the idle parts of
                                     the scan.
        @param list meas_params: list of possible strings of the measurement 
                                 parameter. Have a look at MEAS_PARAMS to see 
                                 the available parameters. If nothing is passed,
                                 an empty string array will be created.

        @return bool: returns true if only Z-feedback is on, i.e. the probe is 
                      on surface also situation, when SenZ signal is Z-feedback
                      input is permissible; it is useful for tests Function uses
                      TScanCallback to send back signals.

        IMPORTANT:
        After execution ends the process returns the probe to the initial 
        configuration, i.e. set Z-feedback to its initial state and probe to 
        initial place.

        Stopping the process CAN ONLY BE DONE at certain moments, i.e. at 
        moments where the return of the current parameters is zero in size 
        (usually equivalent to reaching the end of scan).

        To setup the sweep, register at first via self.set_TScanCallback(...) 
        to receive the measurement parameters during the scan. Then run the
        self.setup_spm(...) method for general configuration and then this 
        method self.probe_sweep_z(...) for the precise scanning configuration.
        The scan can be executed via self.scan_line() and can be stopped via
        self.finish_scan().


        You may call BreakProbeSweepZ at any moment if only if the 
        len(meas_params) == 0.
        """

        ret_val = self._check_spm_scan_params(z_afm_start=start_z, z_afm_stop=stop_z)

        if ret_val:
            return False


        from_c = c_float(start_z^1e9)   # convert to nm, function expects in nm
        to_c = c_float(stop_z^1e9)      # convert to nm, function expects in nm
        pts_c = c_int(num_points)

        sweepT_c = c_float(sweep_time)
        kIdleMove_c = c_float(idle_move_time)

        sigs_buffers = self._create_meas_params(meas_params)
        # extract the actual set parameter:
        self._curr_meas_params = [param.value.decode() for param in sigs_buffers]

        sigsCnt_c = len(sigs_buffers)

        self._lib.ProbeSweepZ.argtypes = [c_float,  # from
                                          c_float,  # to
                                          c_int,    # pts
                                          c_float,  #sweepT
                                          c_float,
                                          c_int,
                                          POINTER((c_char * self.MAX_SIG_NAME_LEN) * sigsCnt_c.value)]

        ret_val = self._lib.ProbeSweepZ(from_c, 
                                        to_c, 
                                        pts_c, 
                                        sweepT_c, 
                                        kIdleMove_c,
                                        sigsCnt_c,
                                        byref(sigs_buffers))

        return ret_val


    def break_probe_sweep_z(self):
        """ Stops the z sweep procedure of the z probe. 

        Please check in the method self.probe_sweep_z(...), when this function 
        call can be executed. 
        """
        self._lib.BreakProbeSweepZ()

    def probe_lift(self, lift_by, trigger_time):
        """ Lift the current Probe (perform basically a retract)

        @param float lift_by: in m, in taken from current state, i.e. added to 
                              previous lift(s)
        @param float trigger_time: if triggering is enabled via 
                                        self.set_ext_trigger(True) 
                                   first trigger pulse is applied when the probe
                                   is just lifted. Second trigger is applied 
                                   after trigger_time in seconds.

        @return bool: Function returns True if Z-feedback is on, i.e. the probe
                      is on surface, otherwise if Z-feedback if off (and is 
                      taken to be the SenZ postion feedback) indicating that you
                      are not on the surface, then return value is False.
         """

        lift_c =  c_float(lift_by*1e9) # function expects in nm
        triggerTime_c = c_float(trigger_time)

        return self._lib.ProbeLift(lift_c, triggerTime_c)

    def probe_land(self):
        """ Land the probe on the surface.

        @return bool: Function returns true if the probe was first lifted, i.e.
                      Z-feedback input is SenZ

        Z-feedback input is switched to previous (Mag, Nf, etc.), the same is 
        for other parameters: gain, setpoint land may be too slow if starting 
        from big lifts, say from 1 micron; then it will be possible to rework 
        the function or implement some new.
        """

        return self._lib.ProbeLand()

    def probe_land_soft(self):
        """ A softer probe landing procedure

        Landing with constant and always reasonable value for Z-move rate unlike
        in the case of self.probe_land(). The method is useful when start 
        landing from big tip-sample gaps, say, more than 1 micron. When call the
        function after ProbeLift, it switches the Z-feedback input same as 
        self.probe_land().
        Otherwise it does not switch Z-feedback input, does not set setpoint and
        feedback gain.
        """
        return self._lib.ProbeLand2()

    #FIXME: THIS FUNCTION IS DEPRECATED! DO NOT USE IT!
    #FIXME: make function name consistent, choose either x_val, y_val, z_val or
    #       a general name e.g. coord0, coord1, coord2
    def setup_scan_line_xyz(self, x_start, x_stop, y_start, y_stop, z_start, 
                            z_stop, time_forward, time_back, liftback):
        """ Setup the scan line in an arbitrary 3D direction. 

        @param float x_start: start point for x movement in m
        @param float x_stop: stop point for x movement in m
        @param float y_start: start point for y movement in m
        @param float y_stop: stop point for y movement in m
        @param float z_start: start point for z movement in m
        @param float z_stop: stop point for z movement in m
        @param float time_forward: time for forward movement during the linescan
                                   procedure in seconds.
                                   For line-scan mode time_forward is equal to 
                                   the time-interval between starting of the 
                                   first scanned point and ending of the last 
                                   scan point. 
                                   For point-scan tforw is the sum of all 
                                   time-intervals between scan points.
        @param float time_back: sets the time-interval for back (idle) movement 
                                in second when the back displacement is abs 
                                equal to the forward displacement, it also 
                                defines the time interval when move to first 
                                scan point.
        @param float liftback: Provide an additional lift in m over the plane 
                               when performing line backward moves.
                               For backward moves there is NO CRASH DETECTION, 
                               i.e. NO PROTECTION AGAINST THE PROBE TOUCHING THE
                               SURFACE. So be aware what you are doing!

        To start "plane-scan" or XYZ-scan mode, first define the plane equation.
        For this use self.probe_lift(...), self.set_sample_scanner_pos(...) and 
        self.probe_land or self.probe_land_soft functions to touch the surface
        in different points and call self.get_sample_scanner_pos('Z1') to get
        the z value.
        For safe moves in XY-plane to prevent the probe from touching the 
        surface, consider the sample surface inclination to be about 4-5 microns
        per 100 microns in XY-plane (+ some add due to surface topography). 
        After all move the probe to be in the plane using self.probe_list 
        (scan process will be executed only when Z-feedback is SenZ).
        Call self.setup_spm(...) before the measurement to set up the required
        measurement parameters, and continue with this method. Some call logic
        applies to this method as it is to self.setup_scan_line.

        """

        # remember to convert to micrometer units, since the spm library uses
        # this.
        x0 = c_float(x_start*1e6)
        x1 = c_float(x_stop*1e6)
        y0 = c_float(y_start*1e6)
        y1 = c_float(y_stop*1e6)
        z0 = c_float(z_start*1e6)
        z1 = c_float(z_stop*1e6)

        tforw_c = c_float(time_forward)
        tback_c = c_float(time_back)
        liftback_c = c_float(liftback*1e6)
        
        return self._lib.SetupScanLineXYZ(x0, y0, x1, y1, tforw_c, tback_c, 
                                          liftback_c)

    def setup_plane_scan(self, line_point=100, meas_params=[]):
        """ Set up a general plane scan.

        @param int line_points: number of points to scan
        @param list meas_params: optional, list of possible strings of the 
                                 measurement parameter. Have a look at 
                                 MEAS_PARAMS to see the available parameters. 
                                 If nothing is passed, an empty string array 
                                 will be created.
        
        @return (status_variable, plane,  with: 
                       -1 = input parameter error 
                        0 = call failed, 
                        1 = call successful

        """

        linePts_c = c_int(line_point)

        sigs_buffers = self._create_meas_params(meas_params)
        # extract the actual set parameter:
        self._curr_meas_params = [param.value.decode() for param in sigs_buffers]

        sigsCnt_c = len(sigs_buffers)

        self._lib.SetupPlaneScan.argtypes = [c_int,  # linePts
                                             c_int,  # sigsCnt
                                             POINTER((c_char * self.MAX_SIG_NAME_LEN) * sigsCnt_c.value)]

        ret_val = self._lib.SetupPlaneScan(linePts_c, 
                                           sigsCnt_c,
                                           byref(sigs_buffers))
        return ret_val


    def set_plane_points(self, x_start, x_stop, y_start, y_stop, z_start, 
                         z_stop):
        """ Set the general scan plane. 

        @param float x_start: start x value of the scan in m
        @param float x_stop: stop x value of the scan in m
        @param float y_start: start y value of the scan in m
        @param float y_stop: stop y value of the scan in m
        @param float z_start: start z value of the scan in m
        @param float z_stop: stop z value of the scan in m

        Use this method after setting up the general scan with 
            self.setup_plane_scan(...)
        """

        # initialize new array values for plane scan
        self._ps_x_c = (c_float * 2)() # float array        
        self._ps_y_c = (c_float * 2)() # float array   
        self._ps_z_c = (c_float * 2)() # float array   

        # assign the proper values in c style, convert to um for library call
        self._ps_x_c[:] = [x_start/1e-6, x_stop/1e-6]
        self._ps_y_c[:] = [y_start/1e-6, y_stop/1e-6]
        self._ps_z_c[:] = [z_start/1e-6, z_stop/1e-6]

        ret_val = self._lib.SetPlanePoints(ctypes.byref(self._ps_x_c), 
                                           ctypes.byref(self._ps_y_c),
                                           ctypes.byref(self._ps_z_c)) 

        return ret_val


    def get_plane_points(self):
        """ Obtain the currently set plane points. 

        @return tuple(list x_val, list y_val, list z_val):
                    the list contains the start and stop values of the scan

        """

        # convert on the fly the list back from um to m
        return ([val*1e-6 for val in self._ps_x_c[:]], 
                [val*1e-6 for val in self._ps_y_c[:]],
                [val*1e-6 for val in self._ps_z_c[:]])


    def set_plane_lift(self, lift, liftback):
        """ Set the lift parameters. 

        @param float lift: lift of the scan in m
        @param float liftback: liftback of the scan in m

        During back-movement the lift over the surface plane is the sum of the 
        'lift' and 'liftback' values.
        """

        # convert to nm for library call
        self._lift_c = c_float(lift/1e-9)
        self._liftback_c = c_float(liftback/1e-9)

        return self._lib.SetPlaneLift(self.lift_c, self.liftback_c)

    def get_plane_lift(self):
        """ Obtain the currently set plain lift parameters. 

        @return tuple(float lift, float liftback) 
            lift in m
            liftback in m    
        """
        return (self._lift_c.value * 1e-9, self._liftback_c.value * 1e-9)


    def setup_scan_2pass(self, line_point=100, meas_params=[]):
        """ Setup the two pass scan mode.

        @param int line_points: number of points to scan
        @param list meas_params: optional, list of possible strings of the 
                                 measurement parameter. Have a look at 
                                 MEAS_PARAMS to see the available parameters. 
                                 If nothing is passed, an empty string array 
                                 will be created.
        
        @return (status_variable, plane,  with: 
                       -1 = input parameter error 
                        0 = call failed, 
                        1 = call successful

        For the general setup for a 2 pass scan, apply the following methods 
        in this order:

            self.setup_scan_2pass(...)
            self.set_2pass_lift(...)
            self.set_2pass_trigger(...)
            self.setup_2pass_line(...)
            self.scan_line()
        """

        linePts_c = c_int(line_point)

        sigs_buffers = self._create_meas_params(meas_params)
        # extract the actual set parameter:
        self._curr_meas_params = [param.value.decode() for param in sigs_buffers]

        sigsCnt_c = len(sigs_buffers)

        #TODO: check whether this is a relevant setting
        # You can select how many parameters you want to obtain for the 1pass 
        # scan, for now use the same parameter
        sigsCnt_1pass_c = sigsCnt_c

        self._lib.SetupScan2Pass.argtypes = [c_int,  # linePts
                                             c_int,  # sigsCnt
                                             c_int,  # pass1SigsCnt
                                             POINTER((c_char * self.MAX_SIG_NAME_LEN) * sigsCnt_c.value)]

        return self._lib.SetupScan2Pass(linePts_c, 
                                           sigsCnt_c,
                                           sigsCnt_1pass_c,
                                           byref(sigs_buffers))

    def setup_2pass_line(self, x_start, x_stop, y_start, y_stop, time_pass1,
                         time_pass2, time_pass2_back):
        """ Setup the 2pass scan line. 

        @param float x_start: start x value of the scan in m
        @param float x_stop: stop x value of the scan in m
        @param float y_start: start y value of the scan in m
        @param float y_stop: stop y value of the scan in m
        @param float time_pass1: time for the line scan in the first pass
        @param float time_pass2: tíme for the line scan in the second pass
        @param float time_pass2_back: time for the backmovement
        """

        # convert to um for library call
        x_start_c = c_float(x_start/1e-6)
        x_stop_c = c_float(x_stop/1e-6)
        y_start_c = c_float(y_start/1e-6)
        y_stop_c = c_float(y_stop/1e-6)
        time_pass1_c = c_float(time_pass1)
        time_pass2_c = c_float(time_pass2)
        time_pass2_back_c = c_float(time_pass2_back)

        return self._lib.Setup2PassLine(x_start_c, y_start_c, x_stop_c, 
                                        y_stop_c, time_pass1_c, time_pass2_c, 
                                        time_pass2_back_c)


    def set_2pass_lift(self, lift, liftback):
        """ Set lift parameter for the 2 pass scan

        @param float lift: lift of the scan in m
        @param float liftback: liftback of the scan in m

        During back-movement the lift over the surface plane is the sum of the 
        'lift' and 'liftback' values.
        """

        # convert to nm for library call
        self._lift_2pass_c = c_float(lift/1e-9)
        self._liftback_2pass_c = c_float(liftback/1e-9)

        return self._lib.Set2PassLift(self._lift_2pass_c, self._liftback_2pass_c)    

    def get_2pass_lift(self):
        """ Obtain the currently set plain lift parameters for 2pass scan. 

        @return tuple(float lift, float liftback) 
            lift in m
            liftback in m    
        """
        return (self._lift_2pass_c.value * 1e-9, 
                self._liftback_2pass_c.value * 1e-9)

    def set_ext_trigger_2pass(self, trigger_pass1, trigger_pass2):
        """ Set up an external trigger after performing a line in a two pass scan.

        @param bool trigger_pass1: declare whether enable (=True) or disable 
                                  (=False) triggering in first pass
        @param bool trigger_pass2: declare whether enable (=True) or disable 
                                  (=False) triggering in second pass

        This method has to be called once, after self.setup_scan_2pass(...) and
        self.setup_2pass_line(...), otherwise triggering will be disabled.

        Note: One extra trigger is performed at the beginning of the measurement
              of first point of the line.
        """    

        self._trigger_pass1_c = c_bool(trigger_pass1)
        self._trigger_pass2_c = c_bool(trigger_pass2)
        self._lib.Set2PassTriggering(c_trigger_state)

    def get_ext_trigger(self):
        """ Check whether external triggering is enabled.

        @return tuple(bool trigger_pass1, bool trigger_pass2)
        """
        return self._trigger_pass1_c.value, self._trigger_pass2_c.value

    # ==========================================================================
    #                       Higher level functions
    # ==========================================================================

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
            
    def create_scan_leftright(self, x_start, x_stop, y_start, y_stop, res_y):
        """ Create a scan line array for measurements from left to right.
        
        This is only a 'forward measurement', meaning from left to right. It is 
        assumed that a line scan is performed and fast axis is the x axis.
        
        @return list: with entries having the form [x_start, x_stop, y_start, y_stop]
        """
        
        arr = []
        
        y = np.linspace(y_start, y_stop, res_y)
        
        reverse = False
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


    def scan_afm_line_by_point(self):
        pass


    def scan_obj_line_by_point(self):
        pass


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
        
        ret_val, _, _ = self.setup_spm(plane='XY', 
                                       line_points=res_x, 
                                       meas_params=meas_params)

        if ret_val < 1:
            return self._meas_array_scan

        for scan_coords in scan_arr:

            self.setup_scan_line(corr0_start=scan_coords[0], corr0_stop=scan_coords[1], 
                                 corr1_start=scan_coords[2], corr1_stop=scan_coords[3], 
                                 time_forward=time_forward, time_back=time_back)
            self.scan_line()

            # this method will wait until the line was measured.
            scan_line = self.get_scanned_line(reshape=False)

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
        self.finish_scan()
        
        return self._meas_array_scan


    def get_scanned_line(self, reshape=True):
        """ Return a scanned line after it is completely scanned. Wait until
            this is the case.

        @param bool reshape: return in a reshaped structure, i.e every signal is
                             in its separate row.

        @return ndarray: with dimension either
                reshape=True : 2D array[num_of_signals, pixel_per_line]
                reshape=False:  1D array[num_of_signals * pixel_per_line]
        """

        # if the line is not finished yet and the scan has not requested to be 
        # stopped yet, then wait for the parameters to come.
        if not self._line_end_reached and not self._stop_request:
            with self.threadlock:
                self._wait_cond.wait(self.threadlock)

        if reshape and len(self._curr_meas_params) > 0:
            return np.reshape(self._meas_line_scan, ( len(self._meas_line_scan)//len(self._curr_meas_params), len(self._curr_meas_params) ) ).transpose()
        else:
            return self._meas_line_scan

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

    def stop_measure(self):
        self._stop_request = True
        self._wait_cond.wakeAll()
        #self.finish_scan()


    def set_pos_afm(self, target_pos, curr_pos=None):
        """ Position is just [x,y], no z. """

        if curr_pos is None:
            curr_pos = copy.copy(self._curr_afm_pos)

        time_scan = 0.01
        ret_val, _, _ = self.setup_spm(plane='XY', line_points=2, meas_params=[])
        if ret_val < 1:
            return 

        # check input values
        ret_val = self._check_spm_scan_params(x_afm_start=curr_pos[0], x_afm_stop=target_pos[0],
                                              y_afm_start=curr_pos[1], y_afm_stop=target_pos[1])
        if ret_val:
            return self._curr_afm_pos

        self.setup_scan_line(corr0_start=curr_pos[0], corr0_stop=target_pos[0], 
                             corr1_start=curr_pos[1], corr1_stop=target_pos[1], 
                             time_forward=time_scan, time_back=time_scan)
        self.scan_point()

        self.log.info(f'Pos before [x={curr_pos[0]}, y={curr_pos[1]}]')
        self.log.info(f'Pos after  [x={target_pos[0]}, y={target_pos[1]}]')

        self._curr_afm_pos[0] = target_pos[0]
        self._curr_afm_pos[1] = target_pos[1]

        return self._curr_afm_pos

    def set_pos_obj(self, target_pos, curr_pos=None):
        """ Position is [x, y, z]. """

        if curr_pos is None:
            curr_pos = self._curr_objective_pos

        self._set_pos_xy(target_pos[0:2], curr_pos[0:2])
        #self.log.info(f'Pos before [x={curr_pos[0]}, y={curr_pos[1]}, z={curr_pos[2]}]')
        #self.log.info(f'Pos after  [x={target_pos[0]}, y={target_pos[1]}, z={curr_pos[2]}]')

        time.sleep(0.5)

        self._set_pos_xz([target_pos[0], target_pos[2]], [curr_pos[0], curr_pos[2]])
        #self.log.info(f'Pos before [x={target_pos[0]}, y={target_pos[1]}, z={curr_pos[2]}]')
        #self.log.info(f'Pos after  [x={target_pos[0]}, y={target_pos[1]}, z={target_pos[2]}]')

        self._curr_objective_pos = copy.copy(target_pos)
        self.finish_scan()

        return self._curr_objective_pos

    def _set_pos_xy(self, xy_target_list, xy_curr_pos=None):

        if xy_curr_pos is None:
            xy_curr_pos = [0]*2
            xy_curr_pos[0] = self._curr_objective_pos[0] # first entry x
            xy_curr_pos[1] = self._curr_objective_pos[1] # second entry y

        time_scan = 0.01
        ret_val, _, _ = self.setup_spm(plane='X2Y2',line_points=2, meas_params=[])
        if ret_val < 1:
            return 

        # check input values
        ret_val = self._check_spm_scan_params(x_obj_start=xy_curr_pos[0], x_obj_stop=xy_target_list[0],
                                              y_obj_start=xy_curr_pos[1], y_obj_stop=xy_target_list[1])
        if ret_val:
            self.log.error('Set position aborted for objective x y coordinates.')
            return 

        self.setup_scan_line(corr0_start=xy_curr_pos[0], corr0_stop=xy_target_list[0], 
                             corr1_start=xy_curr_pos[1], corr1_stop=xy_target_list[1], 
                             time_forward=time_scan, time_back=time_scan)
        self.scan_point()

        self._curr_objective_pos[0] = xy_target_list[0]
        self._curr_objective_pos[1] = xy_target_list[1]


    def _set_pos_xz(self, xz_target_list, xz_curr_pos=None):
        #TODO: Almost duplicated function to _set_pos_xy, correct that.

        if xz_curr_pos is None:
            xz_curr_pos = [0]*2
            xz_curr_pos[0] = self._curr_objective_pos[0]    # first entry x
            xz_curr_pos[1] = self._curr_objective_pos[2]    # second entry z

        time_scan = 0.01
        ret_val, _, _ = self.setup_spm(plane='X2Z2', line_points=2, meas_params=[])
        if ret_val < 1:
            return 

        # check input values
        ret_val = self._check_spm_scan_params(x_obj_start=xz_target_list[0], x_obj_stop=xz_target_list[0],
                                              z_obj_start=xz_curr_pos[1], z_obj_stop=xz_target_list[1])
        if ret_val:
            self.log.error(f'Set position aborted for objective z coordinate. '
                           f'Check the target_pos: x={xz_target_list[0]*1e6:.2f}um, z={xz_target_list[1]*1e6:.2f}um and'
                           f'the current pos: x={xz_curr_pos[0]*1e6:.2f}um, z={xz_curr_pos[1]*1e6:.2f}um')
            return 

        self.setup_scan_line(corr0_start=xz_target_list[0], corr0_stop=xz_target_list[0], 
                             corr1_start=xz_curr_pos[1], corr1_stop=xz_target_list[1], 
                             time_forward=time_scan, time_back=time_scan)
        self.scan_point()

        self._curr_objective_pos[0] = xz_target_list[0]
        self._curr_objective_pos[2] = xz_target_list[1]


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