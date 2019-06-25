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

from ctypes import c_float, c_void_p, c_int, c_char_p, c_char, POINTER
from qtpy import QtCore

from core.module import Base, ConfigOption
from core.util.mutex import Mutex

class CustomScanner(Base):
    """ A simple Data generator dummy.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'custom_scanner.custom_scanner.CustomScanner'
        libpath: 'path/to/lib/folder'

    """

    # Settings for Qudi Module:
    # -------------------------

    _modclass = 'CustomScanner'
    _modtype = 'hardware'

    _threaded = True


    # Default values for measurement
    # ------------------------------

    # here are data saved from the test TScanCallback
    _test_line_scan = []
    _test_array_scan = []

    # Here are the data saved from the measurement routine
    _meas_line_scan = []
    _meas_array_scan = []

    _apd_line_scan = []
    _apd_array_scan = []

    _line_counter = 0
    _params_per_point = 1    # at least 1 or more



    MEAS_PARAMS = ['Height(Dac)','Height(Sen)','Iprobe', 'Mag', 'Phase', 
                   'Freq', 'Nf', 'Lf', 'Ex1', 'SenX', 'SenY', 'SenZ', 
                   'SenX2', 'SenY2', 'SenZ2']

    # keep a list of the created callbacks
    _TCallback_ref_dict = {}
    _TScanCallback_ref_dict = {}

    # internal signal for data processing.
    _sig_scan_data = QtCore.Signal(int, ctypes.POINTER(c_float))
    
    # external signal: signature: (line number, number of parameters, datalist)
    sig_line_finished = QtCore.Signal(int, int, object)

    _libpath = ConfigOption('libpath', missing='error')

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

    @QtCore.Slot(QtCore.QThread)
    def moveToThread(self, thread):
        super().moveToThread(thread)

    def getModuleThread(self):
        """ Get the thread associated to this module.

          @return QThread: thread with qt event loop associated with this module
        """
        return self._manager.tm._threads['mod-logic-' + self._name].thread

    def on_activate(self):

        self._lib = None
        self._load_library(self._libpath)
        
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
        self._sig_scan_data.connect(self.process_data2)

        self.end_reached = False
        self.scan_forward = True

    def on_deactivate(self):
        self.disconnect_spm()
        self._unload_library()
        
    def _load_library(self, path):
        
        libname = 'remote_spm.dll'
        curr_path = os.path.abspath(os.curdir) # get the current path
        
        # the load function requires that current path is set to
        # library path
        os.chdir(path)
        self._lib = ctypes.CDLL(libname)
        os.chdir(curr_path) # change back to initial path
    
    def _prepare_library_calls(self):
        """ Set necessary argtype and restype of function calls. """

        self._lib.SignalsList.argtype = [c_void_p, c_void_p]
        self._lib.SignalsList.restype = c_int
        self._lib.ScannerRange.restype = c_float
        self._lib.SetupScanLine.argtype = [c_float, c_float, 
                                           c_float, c_float,
                                           c_float, c_float]
        self._lib.ExecScanPoint.argtype = [POINTER(c_int), POINTER(c_float)]

    def _unload_library(self):
        if hasattr(self, '_lib'):
            del self._lib
    
    def connect_spm(self):

        ret_val = bool(self._lib.Initialization())

        if ret_val:
            self.log.info('SPM Stage connected.')
        else:
            self.log.warning('NOT possible to connect to the SPM stage.')

        return ret_val
    
    def is_connected(self):
        return bool(self._lib.IsConnected())
    
    def disconnect_spm(self):
        return self._lib.Finalization()

    def send_log_message(self, message):
        #mess = ctypes.c_char_p(message)
        mess = message.encode('utf-8')
        
        # the response function requires a zero terminated pointer
        # in python this is an empty string
        resp = ctypes.c_char_p(b"") 
        self._lib.SendLogMessage(mess, resp)
        
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
                        1 = call successfull
        """

        # This is the callback signature:
        # typedef void ( *TCallback )( int proc_index );
        callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
        
        # Very important! the reference to the callback function has to be
        # saved to prevent it from getting caught by the garbage collector
        self._TCallback_ref_dict[func.__name__] = callback_type(func)

        return self._lib.SetCallback(self._TCallback_ref_dict[func.__name__])
    
    def set_callback1(self):

        # prepare a test callback
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
                        1 = call successfull
        """
        return self._lib.InitTestCallback()
    
    def set_TScanCallback(self, func):
        """ Set the scanner callback function. The function must have the signature
        
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
        scan_callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, 
                                              ctypes.c_int, 
                                              ctypes.POINTER(ctypes.c_float))
                                              
        # the trick is that capitals 'POINTER' makes a type and 
        # lowercase 'pointer' makes a pointer to existing storage. 
        # You can use byref instead of pointer, they claim it's faster. 
        # I like pointer better because it's clearer what's happening.
        self._TScanCallback_ref_dict[func.__name__] = scan_callback_type(func)
        
        
        return self._lib.SetScanCallback(self._TScanCallback_ref_dict[func.__name__])

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
        return self._lib.InitTestScanCallback()


    @QtCore.Slot(int, ctypes.POINTER(c_float))
    def process_data(self, size, arr):
        """ Process the received data from a signal. """
    
        if size == 0:
            print(f'Line {self._line_counter} finished.')

            self.sig_line_finished.emit(self._line_counter, 
                                        self._params_per_point,
                                        self._meas_line_scan)
            self._line_counter += 1
            self._meas_array_scan.append(self._meas_line_scan)
            self._meas_line_scan = []
            self.end_reached = True
            return 0



        arr_new = [arr[entry] for entry in range(size)]
        self._meas_line_scan.extend(arr_new)

        return 0

    @QtCore.Slot(int, ctypes.POINTER(c_float))
    def process_data2(self, size, arr):
        """ Process the received data from a signal. """
    
        if size == 0:
            print(f'Line {self._line_counter} finished.')
            self._line_counter += 1
            self.end_reached = True
            return 0

        arr_new = [arr[entry] for entry in range(size)]
        self._meas_line_scan.extend(arr_new)

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
           
    
    def get_scanner_range_sample_x(self):
        return self._lib.ScannerRange(b'X')
    
    def get_scanner_range_sample_y(self):
        return self._lib.ScannerRange(b'Y')
    
    def get_scanner_range_sample_z(self):
        return self._lib.ScannerRange(b'Z')

    def get_scanner_range_objective_x(self):
        return self._lib.ScannerRange(b'X2')
    
    def get_scanner_range_objective_y(self):
        return self._lib.ScannerRange(b'Y2')
    
    def get_scanner_range_objective_z(self):
        return self._lib.ScannerRange(b'Z2')

    def get_signal_list(self):
        """ The function returns signal list with their entry.
        
        @return tuple(names, units):
            list names: list of strings names for available parameters
            list units: list of the associated units to the names list.
        """

        #names_buffers = [ctypes.create_string_buffer(40) for i in range(15)]
        #names_pointers = (ctypes.c_char_p*15)(*map(ctypes.addressof, names_buffers))

        # create 15 zero terminated strings, each of size 40 characters. 
        names_buffers = ((ctypes.c_char * 40) * 15)()

        #units_buffers = [ctypes.create_string_buffer(40) for i in range(15)]
        #units_pointers = (ctypes.c_char_p*15)(*map(ctypes.addressof, units_buffers))

        # create 15 zero terminated strings, each of size 40 characters. 
        units_buffers = ((ctypes.c_char * 40) * 15)()
        
        # resp indicates whether call was successful: either 0=False or 1=True
        resp = self._lib.SignalsList(ctypes.byref(names_buffers), 
                                     ctypes.byref(units_buffers))
        
        if not resp:
            self.log.warning('Call to request the SignalsList was not successful!')
        
        names = [s.value.decode() for s in units_buffers]
        units = [s.value.decode() for s in names_buffers]
    
        return names, units
    
    def setup_scan_common(self, plane='XY', line_points=100, sigs_buffers=None):
        """ Setting up all required parameters to perform a scan.
        
        @param str plane: The selected plane, possible options:
                            XY, XZ, YZ for sample scanner
                            X2Y2, X2Z2, Y2Z2 for objective scanner
        @param int line_points: number of points to scan
        @param ctypes.c_char sigs_buffers: optional, c-like string array
        
        Every Scan procedure starts with this method.
        
        @return int: status variable with: 0 = call failed, 1 = call successful
        """
        
        if sigs_buffers is None:
            sigs_buffers = ((ctypes.c_char * 40) * 4)()
            sigs_buffers[0].value = b'Height(Dac)'
            sigs_buffers[1].value = b'Height(Sen)'
            sigs_buffers[2].value = b'Mag'
            sigs_buffers[3].value = b'Phase'

        sigsCnt = c_int(len(sigs_buffers))

        
        plane_id = plane.encode('UTF-8')
        plane_id_p = c_char_p(plane_id)
        
        line_points_c = ctypes.c_int(line_points)

        return self._lib.SetupScanCommon(plane_id_p, line_points_c, sigsCnt, ctypes.byref(sigs_buffers))
    
    
    def setup_scan_line(self, x_start, x_stop, y_start, y_stop, 
                        time_forward, time_back):
        """ Setup the scan line parameters
        
        @param float x_start: start point for x in micrometer
        @param float x_stop: stop point for x in micrometer
        @param float y_start: start point for y in micrometer
        @param float y_stop: stop point for y in micrometer
        @param float time_forward: time for forward movement during linescan in s
        @param float time_back: time for backward movement during linescan in s
        
        @return int: status variable with: 0 = call failed, 1 = call successfull
        """
        x0 = c_float(x_start)
        y0 = c_float(y_start)
        x1 = c_float(x_stop)
        y1 = c_float(y_stop)
        tforw = c_float(time_forward)
        tback = c_float(time_back)
        
        return self._lib.SetupScanLine(x0, y0, x1, y1, tforw, tback)
    
    def scan_line(self):
        """Execute a scan line measurement. 
        
        Every scan procedure starts with setup_scan_common method. Then
        setup_scan_line follows (first time and then next time current 
        scan line was completed)

        @return int: status variable with: 0 = call failed, 1 = call successfull
        """
        return self._lib.ExecScanLine()

    def scan_point(self, num_params=None):
        """ After setting up the scanner perform a scan of a point. 

        @param int num_params: set the expected parameters per point, minimum is 1

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
            num_params = self._params_per_point

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
    
    # ==========================================================================
    #                       Higher level functions
    # ==========================================================================

    def create_meas_params(self, meas_params):
        """ Create a zero terminated string buffers with ctypes 

        @param list meas_params: list of string names for the parameters. Only
                                 names are allowed with are defined in
                                 self.MEAS_PARAMS.

        @return ctypes.c_char_Array: a corresponding array to the provides 
                                     python list of strings
        """

        available_params = []

        for param in meas_params:
            if param in self.MEAS_PARAMS:
                available_params.append(param)

        if available_params == []:
            self.log.error(f'The provided list "{meas_params}" does not '
                           f'contain any measurement parameter which is '
                           f'allowed from this list: {self.MEAS_PARAMS}.')
            return []


        names_buffers = ((c_char * 40) * len(available_params))()
        for index, entry in enumerate(available_params):
            names_buffers[index].value = entry.encode('utf-8')

        return names_buffers


    
    def scan_area_by_line(self, x_start, x_end, y_start, y_end, res_x, res_y, 
                          time_forward=1, time_back=1, meas_params=['Height(Dac)']):

        """ Measurement method for a scan by line.
        
        
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
        
        scan_arr = self.create_scan_leftright2(x_start, x_end, y_start, y_end, res_y)
        names_buffers = self.create_meas_params(meas_params)
        
        self._params_per_point = len(names_buffers)
        self.setup_scan_common(line_points=res_x, sigs_buffers=names_buffers)



        self._meas_array_scan = []
        self._scan_counter = 0
        
        for scan_coords in scan_arr:
            self._meas_line_scan = []
            self.end_reached = False
            
            self.setup_scan_line(x_start=scan_coords[0], x_stop=scan_coords[1], 
                                 y_start=scan_coords[2], y_stop=scan_coords[3], 
                                 time_forward=time_forward, time_back=time_back)
            self.scan_line()
            
            while True:
                if self.end_reached or self._stop_request:
                    break
                time.sleep(0.1)
                
            
            if self._stop_request:
                    break
            
            self.send_log_message('Line complete.')
        
            if reverse_meas:
                self._meas_array_scan.append(list(reversed(self._meas_line_scan)))
                reverse_meas = False
            else:
                self._meas_array_scan.append(self._meas_line_scan)
                reverse_meas = True
                
        self.log.info('Scan finished. Yeehaa!')
        print('Scan finished. Yeehaa!')
        self.finish_scan()
        
        return self._meas_array_scan
    
    
    def create_scan_snake(self, x_start, x_end, y_start, y_end, res_y):
        # it is assumed that a line scan is performed and fast axis is the x axis.
        
        arr = []
        
        y = np.linspace(y_start, y_end, res_y)
        
        reverse = False
        for index, y_val in enumerate(y):
            
            scan_line = []
            
            if reverse:
                scan_line.extend((x_end, x_start))
                reverse = False
            else:
                scan_line.extend((x_start, x_end))
                reverse = True
                
            scan_line.extend((y_val, y_val))
                
            arr.append(scan_line)
        return arr
            
    def create_scan_leftright(self, x_start, x_end, y_start, y_end, res_y):
        """ Create a scan line array for measurements from left to right.
        
        This is only a 'forward measurement', meaning from left to right. It is 
        assumed that a line scan is performed and fast axis is the x axis.
        
        @return list: with entries having the form [x_start, x_stop, y_start, y_stop]
        """
        
        arr = []
        
        y = np.linspace(y_start, y_end, res_y)
        
        reverse = False
        for index, y_val in enumerate(y):
            
            scan_line = []
            scan_line.extend((x_start, x_end))
            scan_line.extend((y_val, y_val))
                
            arr.append(scan_line)
        return arr     
    
    def create_scan_leftright2(self, x_start, x_end, y_start, y_end, res_y):
        """ Create a scan line array for measurements from left to right and back.
        
        This is only a forward and backward measurement, meaning from left to 
        right, and then from right to left. It is assumed that a line scan is 
        performed and fast axis is the x axis.
        
        @return list: with entries having the form [x_start, x_stop, y_start, y_stop]
        """
        arr = []
        
        y = np.linspace(y_start, y_end, res_y)

        for index, y_val in enumerate(y):
            
            # one scan line forward
            scan_line = []
            scan_line.extend((x_start, x_end))
            scan_line.extend((y_val, y_val))
            arr.append(scan_line)
            
            # another scan line back
            scan_line = []
            scan_line.extend((x_end, x_start))
            scan_line.extend((y_val, y_val))
            arr.append(scan_line)
            
        return arr 

    def start_measure_line(self, x_start=48, x_end=53, y_start=47, y_end=52, 
                           res_x=40, res_y=40, time_forward=1.5, time_back=1.5,
                           meas_params=['Phase', 'Height(Dac)', 'Height(Sen)']):

        self.meas_thread = threading.Thread(target=self.scan_area_by_line, 
                                            args=(x_start, x_end, 
                                                  y_start, y_end, 
                                                  res_x, res_y, 
                                                  time_forward, time_back,
                                                  meas_params), 
                                            name='meas_thread')

        self.meas_thread.start()

    def stop_measure(self):
        self._stop_request = True
        self.finish_scan()



