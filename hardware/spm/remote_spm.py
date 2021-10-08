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
import copy
from deprecation import deprecated

from ctypes import c_float, c_void_p, c_int, c_char_p, c_char, c_bool, POINTER, byref
from qtpy import QtCore

from core.module import Base
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

class RemoteSPMLibrary(Base):

    _libpath = ''  # path to dll
    _lib = None

    # internal library parameter
    MAX_SIG_NAME_LEN = 40 # max string allocation length for a signal name
    MAX_AXIS_ID_LEN = 8   # max length for name of one axis
    MAX_SIG_NUM = 30      # Maximal numbers of readout signals from controller

    # valid measurement parameters (defined by higher method)
    MEAS_PARAMS = {}
    PLANE_LIST = {}

    # current location as known
    _curr_afm_pos = [0, 0]  # just x and y
    _curr_objective_pos = [0, 0, 0]

    # keep a list of the created callbacks
    _TCallback_ref_dict = {}
    _TScanCallback_ref_dict = {}
    _TRestartCallback_ref_dict = {}

    # Here are the data saved from the measurement routine
    #FIXME: Replace _meas_line_scan and _meas_array_scan with 
    #       _afm_scan_line and _afm_scan_array
    _meas_line_scan = []
    _meas_array_scan = []

    _curr_scan_style = TScanMode.LINE_SCAN

    # waiting condition flag
    _wait_cond = QtCore.QWaitCondition()

    # internal signal for data processing.
    _sig_scan_data = QtCore.Signal(int, ctypes.POINTER(c_float))
    sigLineRestarted = QtCore.Signal()    # signal will be emitted if loss of 
                                          # connection error occurred.

    def __init__(self,config, **kwargs):

        super().__init__(config=config, **kwargs)

        # locking mechanism for thread safety. Use it like
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.
        self.threadlock = Mutex()


    def connect_spm(self, libpath, libname): 
        if not os.path.isabs(libpath):   
            self._libpath = os.path.join(os.path.dirname(__file__), libpath)
        else:
            self._libpath = libpath
        
        self._clientdll = libname

        self._load_library(self._libpath, self._clientdll)

        self._connect_spm()

        # prepare test callback
        self._set_test_callback()

        # prepare scan callback
        self._set_scan_callback()

        # prepare function argument type definitions
        self._prepare_library_calls()

        # data, as returned from the SPM, is routed through this signal to be processed
        self._sig_scan_data.connect(self._process_data)

        # connect to the restart signal
        self._set_restart_line_callback()

        self.initialize()


    def disconnect_spm(self):
        self._disconnect_spm()
        self._unload_library()


    def initialize(self):
        
        self._line_counter = 0
        self._line_end_reached = False
        self.scan_forward = True

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


    def get_axis_range(self, axislabel):
        """ Returns the range of the axis as right end point (max)
            @params str: axislabel:  axis label to be checked.  
                This must be encoded as python byte string.  As passed, 
                this will use the values as the pointer to this byte string 
                Currently accepted values:
                    sample   : str(s).encode('utf-8') of s=['X1', 'Y1', 'Z1'] 
                    objective: str(s).encode('utf-8') of s=['X2', 'Y2', 'Z2'] 

                    This is not checked for validity

            @returns  float: val:  max range of axis in um
        """
        axislabel = axislabel.upper() if len(axislabel) > 1 else axislabel.upper() + '1'
        if  (not any([ v in axislabel for v in ['X', 'Y', 'Z']]) ) and \
            (not any([ v in axislabel for v in ['1', '2']])):
            self.log.error("Invalid axis label supplied")

        return self._lib.AxisRange(axislabel.encode())


    def get_axis_position(self, axislabel):
        """ Returns the current postion of the probe/objective along the axis
            @params c_char_p: axislabel:  axis label to be checked.  
                This must be encoded as python byte string.  As passed, 
                this will use the values as the pointer to this byte string 
                Currently accepted values:
                    sample   : str(s).encode('utf-8') of s=['X1', 'Y1', 'Z1'] 
                    objective: str(s).encode('utf-8') of s=['X2', 'Y2', 'Z2'] 

                    This is not checked for validity

            @returns  float: val:  current position of axis in um
        """
        axislabel = axislabel.upper() if len(axislabel) > 1 else axislabel.upper() + '1'
        if  (not any([ v in axislabel for v in ['X', 'Y', 'Z']]) ) and \
            (not any([ v in axislabel for v in ['1', '2']])):
            self.log.error("Invalid axis label supplied")

        return self._lib.AxisPosition(axislabel.encode())


    def set_axis_position(self, axislabel, pos, move_time):
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
        axislabel = axislabel.upper() if len(axislabel) > 1 else axislabel.upper() + '1'
        if  (not any([ v in axislabel for v in ['X', 'Y', 'Z']]) ) and \
            (not any([ v in axislabel for v in ['1', '2']])):
            self.log.error("Invalid axis label supplied")
 
        pos_val = c_float(pos*1e6) # spm library needs position in um
        sweepTime = c_float(move_time)
        return self._lib.SetAxisPosition(axislabel.encode(), 
                                         byref(pos_val), 
                                         sweepTime)


    def set_scanner_axes(self, valid_axis_dict, move_time):
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
            ret = self.set_axis_position(axis_label, pos_val, move_time)
            
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
            self.log.error(f'Library Call to set position for the axis "{list(valid_axis_dict)}" with position {list(valid_axis_dict.values())}um failed.')

        return ret


    def obtain_axis_setpoint(self, axis):
        """ Obtain the future/next value in the callback for the selected axes.

        @param str axis: The name of one of the possible axes, valid values are
                         within the list:
                            ['X', 'x', 'Y', 'y', 'Z', 'z', 'X1', 'x1', 'Y1', 'y1',
                             'Z1', 'z1', 'X2', 'x2', 'Y2', 'y2', 'Z2', 'z2']
        
        Unlike the _set_scanner_axes method, this function does not return the 
        current coordinate, but its future value, which will occur at the end of
        some ongoing procedure in the SPM-software. The method is of need for 
        TCallback procedure implementation.

        """

        axis = axis.upper() # convert to uppercase

        ret = 0
        if axis in self.VALID_AXIS:
            ret = self._lib.AxisSetpoint(axis.encode())

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


    def _unload_library(self):
        if hasattr(self, '_lib'):
            del self._lib


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


    def _connect_spm(self):
        """ Establish connection to SPM-software. 
        
        @return bool: indicates whether initialization was successful.
        """

        ret_val = bool(self._lib.Initialization())

        if ret_val:
            self.log.info('SPM Stage connected.')
        else:
            self.log.warning('NOT possible to connect to the SPM stage.')

        return ret_val
    

    def _disconnect_spm(self):
        """ Disconnection from the SPM-software. """
        self._lib.Finalization()    # no return value
        return 0


    def _create_test_TCallback(self):
        """ Create a callback function which receives a number to be printed.

        @return: reference to a function with simple printout.
        """
        
        def print_message(num): 
            print('The number:', num) 
            self.log.info(f'New number appeared: {num}')
            return 0
        
        return print_message


    def _set_TCallback(self, func):
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
    

    def _set_test_callback(self):
        """ Set a created callback for testing purpose. """

        test_TCallback = self._create_test_TCallback()
        self._set_TCallback(test_TCallback)


    def _test_callback(self):
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
    

    def _set_TScanCallback(self, func):
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


    def _set_TRestartLineCallback(self, func):
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


    def _create_restart_callback(self):
        """ Create a callback function which can be registered.

        @return: reference to a function connected to emit functionality.
        """

        def restart_linescan():
            self.log.warning('Loss of connection occurred! Check if reconnect was successful.')
            self.sigLineRestarted.emit()
            return 0

        return restart_linescan


    def _set_restart_line_callback(self):
        """ Setup the restart line callback functionality. 

        Call this higher order function to connect a Restart event to the 
        emission of the signal from sigLineRestarted.
        """
        # prepare a test scan callback
        TRestartCallback = self._create_restart_callback()
        self._set_TRestartLineCallback(TRestartCallback)


    def _create_measure_TScanCallback(self):
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


    def _set_scan_callback(self):
        
        # prepare a measure scan callback 
        measure_TScanCallback = self._create_measure_TScanCallback()
        self._set_TScanCallback(measure_TScanCallback)


    def _test_scan_callback(self):
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
    def _process_data(self, size, arr):
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

    
    def setup_spm(self, plane='XY', line_points=100, meas_params=[],
                  scan_style=TScanMode.LINE_SCAN):
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
        @param TScanMode scan_style: The enum selection of the current scan mode.
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
            self.log.error(f'The passed plane "{plane}" is not a suitable ' +
                           f'parameter. Please choose one from: ' + 
                           f'{self.PLANE_LIST}.') 
            self._curr_plane = ''
            return (-1, self._curr_plane,  self._curr_meas_params)

        self._curr_plane = plane 

        plane_id = plane.encode('UTF-8')
        plane_id_p = c_char_p(plane_id)
        
        line_points_c = c_int(line_points)

        
        if not isinstance(scan_style, TScanMode) and not isinstance(scan_style, int):
            scan_style = TScanMode.LINE_SCAN
            self.log.error(f'ScanMode for method setup_spm is not valid. Setting to default value {scan_style.name}.')

        elif isinstance(scan_style, int):

            scan_style_temp = None
            for entry in TScanMode:
                if entry.value == scan_style:
                    scan_style_temp = entry  # set the proper scan mode

            if scan_style_temp is None:
                scan_style_temp = TScanMode.LINE_SCAN
                self.log.warning(f'Passed number "{scan_style}" for ScanMode is unknown for method setup_spm.' + 
                                 f'Setting to default value: {scan_style_temp.name} with number {scan_style_temp.value}')
                scan_style_temp = TScanMode._meas_line_scan # default value

            scan_style = scan_style_temp

        self._curr_scan_style = scan_style # set current measurement mode

        self._lib.SetupScanCommon.argtypes = [c_char_p,
                                             c_int,
                                             TScanMode,
                                             c_int,
                                             POINTER((c_char * self.MAX_SIG_NAME_LEN) * sigsCnt.value)]

        ret_val = self._lib.SetupScanCommon(plane_id_p, 
                                            line_points_c, 
                                            scan_style, 
                                            sigsCnt, 
                                            byref(sigs_buffers))

        # in case a line measurement is performed, pre-allocate the required array
        self._meas_line_scan = np.zeros(line_points*len(self._curr_meas_params),
                                        dtype=np.float)

        self._stop_request = False

        if ret_val == 0:
            self.log.error(f'Library call "SetupScanCommon", with parameters ' +
                           f'"{plane}", "{line_points}", ' + 
                           f'"{self._curr_meas_params}" failed.')

        return (ret_val, self._curr_plane,  copy.copy(self._curr_meas_params))


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

    def stop_measurement(self):
        self._stop_request = True
        self._wait_cond.wakeAll()
        #self.finish_scan()


    @deprecated('This function has yet to find a use')
    def get_ext_trigger(self):
        """ Check whether external triggering is enabled.

        @return bool: True: trigger enabled, False: trigger disabled.
        """
        return self._ext_trigger_state.value

    @deprecated('This function has yet to find a use')
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

    @deprecated('This function has yet to find a use')
    def break_probe_sweep_z(self):
        """ Stops the z sweep procedure of the z probe. 

        Please check in the method self.probe_sweep_z(...), when this function 
        call can be executed. 
        """
        self._lib.BreakProbeSweepZ()

    @deprecated('This function has yet to find a use')
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

    @deprecated('This function has yet to find a use')
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

    @deprecated('This function has yet to find a use')
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
    @deprecated('Current function is not in use')
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

    @deprecated('This function has yet to find a use')
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


    @deprecated('This function has yet to find a use')
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


    @deprecated('This function has yet to find a use')
    def get_plane_points(self):
        """ Obtain the currently set plane points. 

        @return tuple(list x_val, list y_val, list z_val):
                    the list contains the start and stop values of the scan

        """

        # convert on the fly the list back from um to m
        return ([val*1e-6 for val in self._ps_x_c[:]], 
                [val*1e-6 for val in self._ps_y_c[:]],
                [val*1e-6 for val in self._ps_z_c[:]])


    @deprecated('This function has yet to find a use')
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

    @deprecated('This function has yet to find a use')
    def get_plane_lift(self):
        """ Obtain the currently set plain lift parameters. 

        @return tuple(float lift, float liftback) 
            lift in m
            liftback in m    
        """
        return (self._lift_c.value * 1e-9, self._liftback_c.value * 1e-9)

    @deprecated('Current function no longer in use')
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

    @deprecated('Current function no longer in use')
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


    @deprecated('Current function no longer in use')
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

    @deprecated('Current function no longer in use')
    def get_2pass_lift(self):
        """ Obtain the currently set plain lift parameters for 2pass scan. 

        @return tuple(float lift, float liftback) 
            lift in m
            liftback in m    
        """
        return (self._lift_2pass_c.value * 1e-9, 
                self._liftback_2pass_c.value * 1e-9)

    @deprecated('Current function no longer in use')
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

    @deprecated('This function has yet to find a use')
    def get_ext_trigger(self):
        """ Check whether external triggering is enabled.

        @return tuple(bool trigger_pass1, bool trigger_pass2)
        """
        return self._trigger_pass1_c.value, self._trigger_pass2_c.value



#    @deprecated('Current function is not in use')
#    def set_pos_afm(self, target_pos, curr_pos=None):
#        """ Position is just [x,y], no z. """
#    
#        if curr_pos is None:
#            curr_pos = copy.copy(self._curr_afm_pos)
#
#        time_scan = 0.01
#        ret_val, _, _ = self.setup_spm(plane='XY', line_points=2, meas_params=[])
#        if ret_val < 1:
#            return 
#
#        # check input values
#        ret_val = self._check_spm_scan_params(x_afm_start=curr_pos[0], x_afm_stop=target_pos[0],
#                                              y_afm_start=curr_pos[1], y_afm_stop=target_pos[1])
#        if ret_val:
#            return self._curr_afm_pos
#
#        self.setup_scan_line(corr0_start=curr_pos[0], corr0_stop=target_pos[0], 
#                             corr1_start=curr_pos[1], corr1_stop=target_pos[1], 
#                             time_forward=time_scan, time_back=time_scan)
#        self.scan_point()
#
#        self.log.info(f'Pos before [x={curr_pos[0]}, y={curr_pos[1]}]')
#        self.log.info(f'Pos after  [x={target_pos[0]}, y={target_pos[1]}]')
#
#        self._curr_afm_pos[0] = target_pos[0]
#        self._curr_afm_pos[1] = target_pos[1]
#
#        return self._curr_afm_pos
#
#    @deprecated('Current function is not in use')
#    def set_pos_obj(self, target_pos, curr_pos=None):
#        """ Position is [x, y, z]. """
#
#        if curr_pos is None:
#            curr_pos = self._curr_objective_pos
#
#        self._set_pos_xy(target_pos[0:2], curr_pos[0:2])
#        #self.log.info(f'Pos before [x={curr_pos[0]}, y={curr_pos[1]}, z={curr_pos[2]}]')
#        #self.log.info(f'Pos after  [x={target_pos[0]}, y={target_pos[1]}, z={curr_pos[2]}]')
#
#        time.sleep(0.5)
#
#        self._set_pos_xz([target_pos[0], target_pos[2]], [curr_pos[0], curr_pos[2]])
#        #self.log.info(f'Pos before [x={target_pos[0]}, y={target_pos[1]}, z={curr_pos[2]}]')
#        #self.log.info(f'Pos after  [x={target_pos[0]}, y={target_pos[1]}, z={target_pos[2]}]')
#
#        self._curr_objective_pos = copy.copy(target_pos)
#        self.finish_scan()
#
#        return self._curr_objective_pos
#
#    @deprecated('Current function is not in use')
#    def _set_pos_xy(self, xy_target_list, xy_curr_pos=None):
#
#        if xy_curr_pos is None:
#            xy_curr_pos = [0]*2
#            xy_curr_pos[0] = self._curr_objective_pos[0] # first entry x
#            xy_curr_pos[1] = self._curr_objective_pos[1] # second entry y
#
#        time_scan = 0.01
#        ret_val, _, _ = self.setup_spm(plane='X2Y2',line_points=2, meas_params=[])
#        if ret_val < 1:
#            return 
#
#        # check input values
#        ret_val = self._check_spm_scan_params(x_obj_start=xy_curr_pos[0], x_obj_stop=xy_target_list[0],
#                                              y_obj_start=xy_curr_pos[1], y_obj_stop=xy_target_list[1])
#        if ret_val:
#            self.log.error('Set position aborted for objective x y coordinates.')
#            return 
#
#        self.setup_scan_line(corr0_start=xy_curr_pos[0], corr0_stop=xy_target_list[0], 
#                             corr1_start=xy_curr_pos[1], corr1_stop=xy_target_list[1], 
#                             time_forward=time_scan, time_back=time_scan)
#        self.scan_point()
#
#        self._curr_objective_pos[0] = xy_target_list[0]
#        self._curr_objective_pos[1] = xy_target_list[1]
#
#    @deprecated('Current function is not in use')
#    def _set_pos_xz(self, xz_target_list, xz_curr_pos=None):
#        #TODO: Almost duplicated function to _set_pos_xy, correct that.
#
#        if xz_curr_pos is None:
#            xz_curr_pos = [0]*2
#            xz_curr_pos[0] = self._curr_objective_pos[0]    # first entry x
#            xz_curr_pos[1] = self._curr_objective_pos[2]    # second entry z
#
#        time_scan = 0.01
#        ret_val, _, _ = self.setup_spm(plane='X2Z2', line_points=2, meas_params=[])
#        if ret_val < 1:
#            return 
#
#        # check input values
#        ret_val = self._check_spm_scan_params(x_obj_start=xz_target_list[0], x_obj_stop=xz_target_list[0],
#                                              z_obj_start=xz_curr_pos[1], z_obj_stop=xz_target_list[1])
#        if ret_val:
#            self.log.error(f'Set position aborted for objective z coordinate. '
#                           f'Check the target_pos: x={xz_target_list[0]*1e6:.2f}um, z={xz_target_list[1]*1e6:.2f}um and'
#                           f'the current pos: x={xz_curr_pos[0]*1e6:.2f}um, z={xz_curr_pos[1]*1e6:.2f}um')
#            return 
#
#        self.setup_scan_line(corr0_start=xz_target_list[0], corr0_stop=xz_target_list[0], 
#                             corr1_start=xz_curr_pos[1], corr1_stop=xz_target_list[1], 
#                             time_forward=time_scan, time_back=time_scan)
#        self.scan_point()
#
#        self._curr_objective_pos[0] = xz_target_list[0]
#        self._curr_objective_pos[2] = xz_target_list[1]
