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

from ctypes import c_float, c_void_p, c_int, c_char_p, c_char
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

    _modclass = 'CustomScanner'
    _modtype = 'hardware'

    names = None
    units = None
    _meas_arr = []
    _total_scan = []
    _tot_meas = []
    _scan_counter = 0
    _threaded = True

    _semaphore = QtCore.QSemaphore()


    MEAS_PARAMS = ['Height(Dac)','Height(Sen)','Iprobe', 'Mag', 'Phase', 
                   'Freq', 'Nf', 'Lf', 'Ex1', 'SenX', 'SenY', 'SenZ', 
                   'SenX2', 'SenY2', 'SenZ2']


    #data_present_sig = QtCore.Signal(int, ctypes.POINTER(c_float))
    data_present_sig = QtCore.Signal(int, list)

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
        self.create_print_callback()
        self.create_scan_print_callback()
        
        # define return types for functions
        self._lib.ScannerRange.restype = c_float
        
        #self._lib.SetupScanLine.argtype = [c_float, c_float, 
        #                                   c_float, c_float,
        #                                   c_float, c_float]
        #self.data_present_sig.connect(self.do_something)
        self.data_present_sig.connect(self.process_data)

        self.end_reached = False
        self.scan_forward = True

    def on_deactivate(self):
        self.disconnect_spm()
        self._unload_library()



    def emit_signal(self, num):
        self.data_present_sig.emit(num)
        
    @QtCore.Slot(float)
    def do_something(self, num):
        # print('signal received.')
        #self._meas_arr2.append(num)
        self.log.info(f'Scan line: {num}.')
        
        
    def _load_library(self, path):
        
        libname = 'remote_spm.dll'
        curr_path = os.path.abspath(os.curdir) # get the current path
        
        # the load function requires that current path is set to
        # library path
        os.chdir(path)
        self._lib = ctypes.CDLL(libname)
        os.chdir(curr_path) # change back to initial path
    
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
    
    def set_callback(self, func):
        """ Set the callback function. The function must have the signature
        
        def func_name(int):
            # do something
            return 0
            
        """
        # This is the callback signature:
        # typedef void ( *TCallback )( int proc_index );

        callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
        
        # very important! the reference to the callback function has to be
        # saved to prevent it from getting caught by the garbage collector
        self._callback_func_ref = callback_type(func)

        return self._lib.SetCallback(self._callback_func_ref)
    
    def create_print_callback(self):
        
        def print_message(num): 
            print('The number:', num) 
            self.log.info(f'New number appeared: {num}')
            return 0
        
        return self.set_callback(print_message)
    
    def test_callback(self):
        return self._lib.InitTestCallback()
    
    def set_scan_callback(self, func):
        """ Set the scanner callback function. The function must have the signature
        
        def func_name(size, arr):
            # int size: size of the passed array
            # float arr[size]: float array of size 'size'.
            
            # do something
            
            return 0
            
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

        self._scan_callback_func_ref = scan_callback_type(func)
        
        return self._lib.SetScanCallback(self._scan_callback_func_ref)

    def create_scan_print_callback(self):
        
        def print_scan_values(size, arr_new):

            #self.data_present_sig.emit(size, arr)

            #size = copy.deepcopy(size_new)
            #arr = copy.deepcopy(arr_new)

            #size = copy.deepcopy(size_new)
            #arr = [arr_new[i] for i in range(size)]
            #self.data_present_sig.emit(size, arr)
            
            self._tot_meas.append((size, arr))
            
            if size == 0:
                #print('Line complete.')
                self.end_reached = True
                self._scan_counter += 1
                print('Count line: ', self._scan_counter)
                #self.data_present_sig.emit(float(self._scan_counter))
                return 0
                
            app_arr = [0]*size
            for index in range(size):
                #print(f'{arr[index]:.7f}', end=" ")
                app_arr[index] = arr[index]
            
            
            #print('Data was written.')
        
            self._meas_arr.extend(app_arr)

            
            return 0

        return self.set_scan_callback(print_scan_values)
    
    # @QtCore.Slot(int, ctypes.POINTER(c_float))
    @QtCore.Slot(int, list)
    def process_data(self, size, arr):
    
            self._tot_meas.append((size, arr))
            print(size, arr)
            
            # if size == 0:
            #     #print('Line complete.')
            #     self.end_reached = True
            #     self._scan_counter += 1
            #     print('Count line: ', self._scan_counter)
            #     #self.data_present_sig.emit(float(self._scan_counter))
            #     return 0
                
            # app_arr = [0]*size
            # for index in range(size):
            #     #print(f'{arr[index]:.7f}', end=" ")
            #     app_arr[index] = arr[index]
            
            
            # print('Data was written: ', size, app_arr)
        
            # self._meas_arr.extend(app_arr)


    def test_scan_callback(self):
        return self._lib.InitTestScanCallback()
    
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
            list names: list of (zero terminated) strings of the various signals
            list units: list of the associated units to the names list.
        """
        
        self._lib.SignalsList.argtype = [c_void_p, c_void_p]
        self._lib.SignalsList.restype = c_int
        
        #names_buffers = [ctypes.create_string_buffer(40) for i in range(15)]
        #names_pointers = (ctypes.c_char_p*15)(*map(ctypes.addressof, names_buffers))
        
        names_buffers = ((ctypes.c_char * 40) * 15)()

        #units_buffers = [ctypes.create_string_buffer(40) for i in range(15)]
        #units_pointers = (ctypes.c_char_p*15)(*map(ctypes.addressof, units_buffers))
        
        units_buffers = ((ctypes.c_char * 40) * 15)()
      
        #resp = self._lib.SignalsList(names_pointers, units_pointers)
        resp = self._lib.SignalsList(names_buffers, units_buffers)
        
        resp = self._lib.SignalsList(ctypes.byref(names_buffers), ctypes.byref(units_buffers))
        
        self.names = names_buffers
        self.units = units_buffers
        
        print([s.value.decode() for s in units_buffers])
        print([s.value.decode() for s in names_buffers])
        
        print(resp)
    
        return (self.names, self.units)
    
    def setup_scan_common(self, plane='XY', line_points=100, sigs_buffers=None):
        """ Setting up all required parameters to perform a scan.
        
        @param str plane: The selected plane, possible options:
                            XY, XZ, YZ for sample scanner
                            X2Y2, X2Z2, Y2Z2 for objective scanner
        @param int line_points: number of points to scan
        @param ctypes.c_char sigs_buffers: optional, c-like string array
        
        Every Scan procedure starts with this method.
        
        
        """
        
        if sigs_buffers is None:
            sigs_buffers = ((ctypes.c_char * 40) * 4)()
            sigs_buffers[0].value = b'Height(Dac)'
            sigs_buffers[0].value = b'Height(Sen)'
            sigs_buffers[0].value = b'Mag'
            sigs_buffers[0].value = b'Phase'

        sigsCnt = c_int(len(sigs_buffers))

        
        plane_id = plane.encode('UTF-8')
        plane_id_p = c_char_p(plane_id)
        
        line_points_c = ctypes.c_int(line_points)
        # ctypes.byref(sigs_buffers)
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
        """
        return self._lib.ExecScanLine()

    def scan_point(self):
        
        self.size_c = ctypes.c_int(0)
        self.size_c_p = ctypes.pointer(self.size_c)
        self.vals_c = ctypes.c_float(0.0)
        self.vals_c_p = ctypes.pointer(self.vals_c)
        #self._lib.ExecScanPoint(ctypes.addressof(size_c), ctypes.byref(vals_c))
        self._lib.ExecScanPoint(self.size_c_p, self.vals_c_p)

    
        return self.size_c, self.vals_c
    
    def finish_scan(self):
        """ It is correctly (but not abs necessary) to end each scan 
        process by this method. There is no problem for 'Point' scan, 
        performed with 'scan_point', to stop it at any moment. But
        'Line' scan will stop after a line was finished, otherwise 
        your software may hang until scan line is complete.
        """
        return self._lib.FinitScan()
    
    # ==========================================================================
    #                       Higher level functions
    # ==========================================================================

    def create_meas_params(self, meas_params_list):

        available_params = []

        for param in meas_params_list:
            if param in self.MEAS_PARAMS:
                available_params.append(param)

        if available_params == []:
            self.log.error(f'The provided list "{meas_params_list}" does not '
                           f'contain any measurement parameter which is '
                           f'allowed from this list: {self.MEAS_PARAMS}.')
            return []


        names_buffers = ((c_char * 40) * len(available_params))()
        for index, entry in enumerate(available_params):
            names_buffers[index].value = entry.encode('utf-8')

        return names_buffers


    
    def scan_area(self, x_start, x_end, y_start, y_end, res_x, res_y, 
                  time_forward=1, time_back=1, meas_params=['Phase']):

        """
        
        
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
        """
        
        reverse_meas = False
        self._stop_request = False
        
        scan_arr = self.create_scan_leftright2(x_start, x_end, y_start, y_end, res_y)
        
        names_buffers = self.create_meas_params(meas_params)
        
        
        self.setup_scan_common(line_points=res_x, sigs_buffers=names_buffers)

        self._total_scan = []
        self._tot_meas = []
        self._scan_counter = 0
        
        for scan_coords in scan_arr:
            self._meas_arr = []
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
                self._total_scan.append(list(reversed(self._meas_arr)))
                reverse_meas = False
            else:
                self._total_scan.append(self._meas_arr)
                reverse_meas = True
                
        self.log.info('Scan finished. Yeehaa!')
        print('Scan finished. Yeehaa!')
        self.finish_scan()
        
        return self._total_scan
    
    
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
        # it is assumed that a line scan is performed and fast axis is the x axis.
        
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
        # it is assumed that a line scan is performed and fast axis is the x axis.
        
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

    def start_measure(self, x_start=48, x_end=53, y_start=47, y_end=52, 
                      res_x=40, res_y=40, time_forward=1.5, time_back=1.5):

        self.meas_thread = threading.Thread(target=self.scan_area, 
                                            args=(x_start, x_end, 
                                                  y_start, y_end, 
                                                  res_x, res_y, 
                                                  time_forward, time_back), 
                                            name='meas_thread')

        self.meas_thread.start()

    def stop_measure(self):
        self._stop_request = True
        self.finish_scan()
