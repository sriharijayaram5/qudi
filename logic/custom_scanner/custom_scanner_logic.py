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


from core.module import Connector, StatusVar, ConfigOption
from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
import threading
import numpy as np
import time

from qtpy import QtCore

class CustomScannerLogic(GenericLogic):
    """ This is a skeleton for a logic module. """


    _modclass = 'CustomScannerLogic'
    _modtype = 'logic'

    ## declare connectors. It is either a connector to be connected to another 
    # logic or another hardware. Hence the interface variable will take either 
    # the name of the logic class (for logic connection) or the interface class
    # which is implemented in a hardware instrument (for a hardware connection)
    spm_device = Connector(interface='CustomScanner') # hardware example
    savelogic = Connector(interface='SaveLogic')  # logic example
    counter_device = Connector(interface='SlowCounterInterface')

    ## configuration parameters/options for the logic. In the config file you 
    # have to specify the parameter, here: 'conf_1'
    #_conf_1 = ConfigOption('conf_1', missing='error')

    # status variables, save status of certain parameters if object is 
    # deactivated.
    #_count_length = StatusVar('count_length', 300)


    _stop_request = False
    # AFM signal
    _meas_line_scan = []
    _meas_array_scan = []
    _meas_array_scan_fw = []
    _meas_array_scan_bw = []


    # APD signal
    _apd_line_scan = []
    _apd_array_scan = []
    _apd_array_scan_fw = []
    _apd_array_scan_bw = []
    _scan_counter = 0
    _end_reached = False


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

    def on_activate(self):
        """ Initialization performed during activation of the module. """

        # Connect to hardware and save logic
        self._spm = self.spm_device()
        self._save_logic = self.savelogic()
        self._counter = self.counter_device()

    def on_deactivate(self):
        """ Deinitializations performed during deactivation of the module. """

        pass


    def perform(self):
        self._spm.test_another()



    def scan_area_by_point(self, x_start, x_end, y_start, y_end, res_x, res_y, 
                           integration_time, meas_params=['Height(Dac)']):

        """ Measurement method for a scan by point.
        
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

        self._start = time.time()

        # setup the counter device:
        ret = self._counter.set_up_clock(clock_frequency=1/integration_time)
        if ret < 0:
            return
        ret = self._counter.set_up_counter()
        if ret < 0:
            return

        # set up the spm device:
        reverse_meas = False
        self._stop_request = False
        scan_speed_per_line = 0.01  # in seconds
        scan_arr = self._spm.create_scan_leftright2(x_start, x_end, 
                                                    y_start, y_end, res_y)
        names_buffers = self._spm.create_meas_params(meas_params)
        self._spm._params_per_point = len(names_buffers)
        self._spm.setup_scan_common(line_points=res_x, 
                                    sigs_buffers=names_buffers)

        # AFM signal
        self._meas_array_scan_fw = np.zeros((res_y, len(names_buffers)*res_x))
        self._meas_array_scan_bw = np.zeros((res_y, len(names_buffers)*res_x))
        # APD signal
        self._apd_array_scan_fw = np.zeros((res_y, res_x))
        self._apd_array_scan_bw = np.zeros((res_y, res_x))

        self._scan_counter = 0

        for line_num, scan_coords in enumerate(scan_arr):
            
            # AFM signal
            self._meas_line_scan = np.zeros(len(names_buffers)*res_x)
            # APD signal
            self._apd_line_scan = np.zeros(res_x)
            
            self._spm.setup_scan_line(x_start=scan_coords[0], 
                                      x_stop=scan_coords[1], 
                                      y_start=scan_coords[2], 
                                      y_stop=scan_coords[3], 
                                      time_forward=scan_speed_per_line, 
                                      time_back=scan_speed_per_line)
            
            vals = self._spm.scan_point()  # these are points to throw away

            if len(vals) > 0:
                self.log.error("The scanner range was not correctly set up!")

            for index in range(res_x):

                #Important: Get first counts, then the SPM signal!
                self._apd_line_scan[index] = self._counter.get_counter(1)[0][0]
                self._meas_line_scan[index*len(names_buffers):(index+1)*len(names_buffers)] = self._spm.scan_point()
                
                self._scan_counter += 1
                if self._stop_request:
                    break

            if reverse_meas:
                self._meas_array_scan_bw[line_num//2] = self._meas_line_scan[::-1]
                reverse_meas = False
            else:
                self._meas_array_scan_fw[line_num//2] = self._meas_line_scan
                reverse_meas = True

            if self._stop_request:
                break

            self.log.info(f'Line number {line_num} completed.')
                
        self._stop = time.time() - self._start
        self.log.info(f'Scan finished after {int(self._stop)}s. Yeehaa!')

        # clean up the counter:
        self._counter.close_counter()
        self._counter.close_clock()
        # clean up the spm
        self._spm.finish_scan()
        
        return self._meas_array_scan_fw, self._meas_array_scan_bw


    def start_measure_point(self, x_start=48, x_end=53, y_start=47, y_end=52, 
                           res_x=40, res_y=40, integration_time=0.02,
                           meas_params=['Phase', 'Height(Dac)', 'Height(Sen)']):

        self.meas_thread = threading.Thread(target=self.scan_area_by_point, 
                                            args=(x_start, x_end, 
                                                  y_start, y_end, 
                                                  res_x, res_y, 
                                                  integration_time,
                                                  meas_params), 
                                            name='meas_thread')

        self.meas_thread.start()

    def stop_measure(self):
        self._stop_request = True
        self._spm.finish_scan()

    #TODO: split return array in two separate arrays for forwards and backward scan.