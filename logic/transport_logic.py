# -*- coding: utf-8 -*-

"""
A central module to control the default settings for all pulsed measurements done by the PODMR, QAFM, and jupyter_pulsed_AWG_master_logic.

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

import numpy as np
from collections import OrderedDict
import datetime
from decimal import Decimal
import time
from math import log10, floor
import matplotlib.pyplot as plt
import os
import pickle
import joblib
from . import gwyfile as gwy

from core.connector import Connector
from core.statusvariable import StatusVar
from core.configoption import ConfigOption
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from interface.smu_interface import SMUInterface
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

class TransportLogic(GenericLogic):
    """ Logic module to control the default settings for all pulsed measurements done by the PODMR, QAFM, and jupyter_pulsed_AWG_master_logic
        This logic includes all settings for pulsed measurements, which are not changed frequently.

    Example config:

    pulsedsettingslogic:
        module.Class: 'transport_logic.TransportLogic'
        

    """
    sample_smu = Connector(interface='SMUInterface')
    gate_voltage_source = Connector(interface='VolatgeSourceInterface')
    controller = Connector(interface='CryoControllerInterface')
    savelogic = Connector(interface='SaveLogic')

    # status vars
    

    #signals
    sig1DScanStarted = QtCore.Signal()
    sig1DScanPointFinished = QtCore.Signal()
    sig2DScanStarted = QtCore.Signal()
    sig2DScanPointFinished = QtCore.Signal()
    sigTimetraceStarted = QtCore.Signal()
    sigTimetracePointFinished = QtCore.Signal()
    sigScanFinished = QtCore.Signal()
    sigScanAutoSave = QtCore.Signal()
    sigDataSaved = QtCore.Signal()

    _worker_thread = WorkerThread(print)
    _USE_THREADED = True

    _color_map = 'inferno'

    _gwyobjecttypes = { 'imgobjects': ['2D_transport'],
                        'graphobjects': []
                      }

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._sample_smu = self.sample_smu()
        self._gate_voltage_source = self.gate_voltage_source()
        self._controller = self.controller()
        self._save_logic = self.savelogic()

        sample_source_limits = self.get_sample_source_limits()
        gate_source_limits = self.get_gate_source_limits()

        self.axis_units =  {'V_G': {'applied_units': 'V',
                                   'si_units': 'V',
                                   'nice_name': 'Backgate Voltage',
                                   'max_value': gate_source_limits.max_voltage,
                                   'min_value': gate_source_limits.min_voltage,
                                   'upper_limit': gate_source_limits.max_voltage,
                                   'lower_limit': gate_source_limits.min_voltage},
                            'V_S': {'applied_units': 'V',
                                   'si_units': 'V',
                                   'nice_name': 'Sample Voltage',
                                   'max_value': sample_source_limits.max_voltage,
                                   'min_value': sample_source_limits.min_voltage,
                                   'upper_limit': sample_source_limits.max_voltage,
                                   'lower_limit': sample_source_limits.min_voltage},
                            'I_S': {'applied_units': 'A',
                                    'si_units': 'A',
                                    'nice_name': 'Sample Current',
                                   'max_value': sample_source_limits.max_current,
                                   'min_value': sample_source_limits.min_current,
                                   'upper_limit': sample_source_limits.max_current,
                                   'lower_limit': sample_source_limits.min_current}

                     }

        self.meas_params_units = {  'R_S': {'applied_units' : 'Ohm',
                                            'si_units': 'Ohm', 
                                            'nice_name': 'Sample Resistance'},
                                    'V_S': {'applied_units': 'V',
                                            'si_units': 'V',
                                            'nice_name': 'Sample Voltage'},
                                    'I_S': {'applied_units': 'A',
                                            'si_units': 'A',
                                            'nice_name': 'Sample Current'}
                            }
        
        self._transport_1D_array = self.initialize_transport_1D_array(-10, 10, 11, None, None)
        self._transport_2D_array = self.initialize_transport_2D_array(-10, 10, 11, -10, 10, 11, None, None, None)
        self._transport_timetrace_array = self.initialize_transport_timetrace_array(None)

        self.timetrace_buffer = np.zeros([2, 1000])

        self.timetrace_timer = QtCore.QTimer()
        self.timetrace_timer.setSingleShot(True)
        self.timetrace_timer.setInterval(1 * 1000)  # in ms
        self.timetrace_timer.timeout.connect(self.timetrace_loop)
        self.sigTimetraceStarted.connect(self.start_timetrace_loop)

        self.timetrace_timestep = 1
        self.timetrace_measure_temperature = False
        self.timetrace_loop_running = False

        self._curr_scan_params = []

        self.threadpool = QtCore.QThreadPool()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def initialize_transport_1D_array(self, x_start, x_stop, x_num,
                                         x_axis_type = None, meas_params = None):
        """ Initialize the 1D transport scan array. 
        """


        x_axis = np.linspace(x_start, x_stop, x_num, endpoint=True)

        if meas_params == None:
            meas_params = self.meas_params_units.keys()

        if x_axis_type == None:
            x_axis_type = 'V_G'

        meas_dict = {}
        for params in meas_params:
            name = f'1D_{params}'

            meas_dict[name] = {'data': np.zeros((x_num))}
            meas_dict[name]['x_axis'] = x_axis
            meas_dict[name]['data_info'] = self.meas_params_units[params]
            meas_dict[name]['x_axis_info'] = self.axis_units[x_axis_type]
            meas_dict[name]['display_range'] = None
            meas_dict[name]['params'] = {}

        return meas_dict
    
    def initialize_transport_2D_array(self, x_start, x_stop, x_num,
                                      y_start, y_stop, y_num,
                                      x_axis_type = None, y_axis_type = None, meas_params = None):
        """ Initialize the qafm scan array. 

        @param int num_columns: number of columns, essentially the x resolution
        @param int num_rows: number of columns, essentially the y resolution
        """


        x_axis = np.linspace(x_start, x_stop, x_num, endpoint=True) 
        y_axis = np.linspace(y_start, y_stop, y_num, endpoint=True) 

        if meas_params == None:
            meas_params = self.meas_params_units.keys()

        if x_axis_type == None:
            x_axis_type = 'V_G'

        if y_axis_type == None:
            y_axis_type = 'V_S'

        meas_dict = {}
        for params in meas_params:
            name = f'2D_{params}'

            meas_dict[name] = {'data': np.zeros((y_num, x_num))}
            meas_dict[name]['x_axis'] = x_axis
            meas_dict[name]['y_axis'] = y_axis
            meas_dict[name]['data_info'] = self.meas_params_units[params]
            meas_dict[name]['x_axis_info'] = self.axis_units[x_axis_type]
            meas_dict[name]['y_axis_info'] = self.axis_units[y_axis_type]
            meas_dict[name]['display_range'] = None
            meas_dict[name]['params'] = {}

        return meas_dict
    
    def initialize_transport_timetrace_array(self, meas_params = None):
        """ Initialize the timetrace transport scan array. 
        """


        x_axis = np.zeros(1)

        if meas_params == None:
            meas_params = self.meas_params_units.keys()

        x_axis_info = {'applied_units': 's',
                        'si_units': 's',
                        'nice_name': 'Time'}
        
        temperature_info = {'applied_units' : 'K',
                            'si_units': 'K', 
                            'nice_name': 'Sample Temperature'}

        meas_dict = {}
        for params in meas_params:
            name = f'Timetrace_{params}'

            meas_dict[name] = {'data': np.zeros(1)}
            meas_dict[name]['temperature_data'] = np.zeros(1)
            meas_dict[name]['x_axis'] = x_axis
            meas_dict[name]['data_info'] = self.meas_params_units[params]
            meas_dict[name]['temperature_info'] = temperature_info
            meas_dict[name]['x_axis_info'] = x_axis_info
            meas_dict[name]['display_range'] = None
            meas_dict[name]['params'] = {}

        return meas_dict
    
    def get_1D_data(self):
        return self._transport_1D_array
    
    def get_2D_data(self):
        return self._transport_2D_array
    
    def get_timetrace_data(self):
        return self._transport_timetrace_array
    
    def start_scan_2D_DC_transport(self, x_axis_sweep_parameter, x_axis_start, x_axis_stop, x_axis_num,
                                   y_axis_sweep_parameter, y_axis_start, y_axis_stop, y_axis_num,
                                   use_DC_sample_current = True, DC_sample_current = 0, use_DC_sample_voltage = False, DC_sample_voltage = 0, use_DC_backgate_voltage = False, DC_backgate_voltage = 0,
                                   backgate_voltage_ramp_speed= 0.1, backgate_voltage_autorange = False, sample_voltage_ramp_speed = 0.1, sample_current_ramp_speed = 0.01, sample_transport_autorange = False,
                                   sens_fnc = 'R_S', sens_autorange = False, sens_autozero = False, sens_four_port = False, sens_achange = False, sens_delay = 0, sens_int_time = 0.1):
        
        if self.check_thread_active() or self.timetrace_loop_running:
            self.log.error("A measurement is currently running, stop it first!")
            self.sigScanFinished.emit()
            return
        
        if x_axis_sweep_parameter == y_axis_sweep_parameter:
            self.log.error(f"Sweeping the same parameter on both axis does not make sense. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        if (x_axis_sweep_parameter == 'I_S' and y_axis_sweep_parameter == 'V_S') or (x_axis_sweep_parameter == 'V_S' and y_axis_sweep_parameter == 'I_S'):
            self.log.error(f"Sweeping I_S and V_S together does not make sense. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        if (sens_fnc == x_axis_sweep_parameter) or (sens_fnc == y_axis_sweep_parameter):
            self.log.error(f"Sweeping {x_axis_sweep_parameter} and {y_axis_sweep_parameter} and sensing {sens_fnc} does not make sense. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        if x_axis_start == x_axis_stop:
            self.log.error(f"X axis start and stop should be different. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        if y_axis_start == y_axis_stop:
            self.log.error(f"Y axis start and stop should be different. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        if (x_axis_sweep_parameter in ['I_S', 'V_S', 'V_G']) and (y_axis_sweep_parameter in ['I_S', 'V_S', 'V_G']):
            fnt_target = self.scan_2D_DC_sweep
            args = (x_axis_start, x_axis_stop, x_axis_num, x_axis_sweep_parameter,
                    y_axis_start, y_axis_stop, y_axis_num, y_axis_sweep_parameter,
                    backgate_voltage_ramp_speed, backgate_voltage_autorange,
                    sample_voltage_ramp_speed, sample_current_ramp_speed, sample_transport_autorange,
                    sens_fnc, sens_autorange, sens_autozero,
                    sens_delay, sens_achange, sens_four_port, sens_int_time)
            
        
        else:
            self.log.error("Selected mode is not supported")
            self.sigScanFinished.emit()
            return
        
        if self._USE_THREADED:
            self._worker_thread = WorkerThread(target=fnt_target,
                                            args=args,
                                            name='1D_DC_transport')
            self.threadpool.start(self._worker_thread)

        else:
            self.sigScanFinished.emit()
            self.log.warning('Use threaded instead...')

    def scan_2D_DC_sweep(self, x_start, x_stop, x_num, x_axis_sweep_parameter,
                    y_start, y_stop, y_num, y_axis_sweep_parameter,
                    backgate_voltage_ramp_speed, backgate_voltage_autorange,
                    sample_voltage_ramp_speed, sample_current_ramp_speed, sample_transport_autorange,
                    sens_fnc, sens_autorange, sens_autozero,
                    sens_delay, sens_achange, sens_four_port, sens_int_time):
        
        self._stop_request = False
        
        #setup measurement arrays
        x_array = np.linspace(x_start, x_stop, x_num, endpoint=True)
        y_array = np.linspace(y_start, y_stop, y_num, endpoint=True)

        #setup x axis
        self.reset_outputs()
        if x_axis_sweep_parameter == 'V_S':
            lower_voltage_limit, upper_voltage_limit = self._sample_smu.get_voltage_limit()
            for x_value in x_array:
                if x_value<lower_voltage_limit or x_value>upper_voltage_limit:
                    self.log.error('Sample voltage sweep is outside the setted voltage limits. 2D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_2D_array
            self._sample_smu.set_source_function(0)
            autorange = self._sample_smu.set_source_volt_autorange(sample_transport_autorange)
            self._sample_smu.set_source_volt_ramp_speed(sample_voltage_ramp_speed)
            if not autorange:
                self._sample_smu.set_source_volt_range(max(abs(x_array[0]), abs(x_array[-1])))
            self._sample_smu.set_source_shape(0)
            self._sample_smu.set_source_mode(0)
            x_autorange = sample_transport_autorange
            x_smu = self._sample_smu
            x_fnc = self._sample_smu.set_voltage_level
        elif x_axis_sweep_parameter == 'I_S':
            lower_voltage_limit, upper_voltage_limit = self._sample_smu.get_current_limit()
            for x_value in x_array:
                if x_value<lower_voltage_limit or x_value>upper_voltage_limit:
                    self.log.error('Sample current sweep is outside the setted voltage limits. 2D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_2D_array
            self._sample_smu.set_source_function(1)
            autorange = self._sample_smu.set_source_curr_autorange(sample_transport_autorange)
            self._sample_smu.set_source_curr_ramp_speed(sample_current_ramp_speed)
            if not autorange:
                self._sample_smu.set_source_curr_range(max(abs(x_array[0]), abs(x_array[-1])))
            self._sample_smu.set_source_shape(0)
            self._sample_smu.set_source_mode(0)
            x_autorange = sample_transport_autorange
            x_smu = self._sample_smu
            x_fnc = self._sample_smu.set_current_level
        elif x_axis_sweep_parameter == 'V_G':
            lower_voltage_limit, upper_voltage_limit = self._gate_voltage_source.get_voltage_limit()
            for x_value in x_array:
                if x_value<lower_voltage_limit or x_value>upper_voltage_limit:
                    self.log.error('Backgate voltage sweep is outside the setted voltage limits. 2D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_2D_array
            self._gate_voltage_source.set_source_function(0)
            autorange = self._gate_voltage_source.set_source_volt_autorange(backgate_voltage_autorange)
            self._gate_voltage_source.set_source_volt_ramp_speed(backgate_voltage_ramp_speed)
            if not autorange:
                self._gate_voltage_source.set_source_volt_range(max(abs(x_array[0]), abs(x_array[-1])))
            self._gate_voltage_source.set_source_shape(0)
            self._gate_voltage_source.set_source_mode(0)
            x_autorange = backgate_voltage_autorange
            x_smu = self._gate_voltage_source
            x_fnc = self._gate_voltage_source.set_voltage_level
        else:
            self.log.error('X axis is not supported for this scan. 2D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_2D_array
        
        #setup y axis
        if y_axis_sweep_parameter == 'V_S':
            lower_voltage_limit, upper_voltage_limit = self._sample_smu.get_voltage_limit()
            for y_value in y_array:
                if y_value<lower_voltage_limit or y_value>upper_voltage_limit:
                    self.log.error('Sample voltage sweep is outside the setted voltage limits. 2D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_2D_array
            self._sample_smu.set_source_function(0)
            autorange = self._sample_smu.set_source_volt_autorange(sample_transport_autorange)
            self._sample_smu.set_source_volt_ramp_speed(sample_voltage_ramp_speed)
            if not autorange:
                self._sample_smu.set_source_volt_range(max(abs(y_array[0]), abs(y_array[-1])))
            self._sample_smu.set_source_shape(0)
            self._sample_smu.set_source_mode(0)
            y_autorange = sample_transport_autorange
            y_smu = self._sample_smu
            y_fnc = self._sample_smu.set_voltage_level
        elif y_axis_sweep_parameter == 'I_S':
            lower_voltage_limit, upper_voltage_limit = self._sample_smu.get_current_limit()
            for y_value in y_array:
                if y_value<lower_voltage_limit or y_value>upper_voltage_limit:
                    self.log.error('Sample current sweep is outside the setted voltage limits. 2D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_2D_array
            self._sample_smu.set_source_function(1)
            autorange = self._sample_smu.set_source_curr_autorange(sample_transport_autorange)
            self._sample_smu.set_source_curr_ramp_speed(sample_current_ramp_speed)
            if not autorange:
                self._sample_smu.set_source_curr_range(max(abs(y_array[0]), abs(y_array[-1])))
            self._sample_smu.set_source_shape(0)
            self._sample_smu.set_source_mode(0)
            y_autorange = sample_transport_autorange
            y_smu = self._sample_smu
            y_fnc = self._sample_smu.set_current_level
        elif y_axis_sweep_parameter == 'V_G':
            lower_voltage_limit, upper_voltage_limit = self._gate_voltage_source.get_voltage_limit()
            for y_value in y_array:
                if y_value<lower_voltage_limit or y_value>upper_voltage_limit:
                    self.log.error('Backgate voltage sweep is outside the setted voltage limits. 2D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_2D_array
            self._gate_voltage_source.set_source_function(0)
            autorange = self._gate_voltage_source.set_source_volt_autorange(backgate_voltage_autorange)
            self._gate_voltage_source.set_source_volt_ramp_speed(backgate_voltage_ramp_speed)
            if not autorange:
                self._gate_voltage_source.set_source_volt_range(max(abs(y_array[0]), abs(y_array[-1])))
            self._gate_voltage_source.set_source_shape(0)
            self._gate_voltage_source.set_source_mode(0)
            y_autorange = backgate_voltage_autorange
            y_smu = self._gate_voltage_source
            y_fnc = self._gate_voltage_source.set_voltage_level
        else:
            self.log.error('Y axis is not supported for this scan. 2D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_2D_array

        self._transport_2D_array = self.initialize_transport_2D_array(x_start, x_stop, x_num, y_start, y_stop, y_num, x_axis_sweep_parameter, y_axis_sweep_parameter, [sens_fnc])
        sens_fnc_key = list(self._transport_2D_array.keys())[0]

        self._curr_scan_params = list(self._transport_2D_array.keys())

        #setup sensing
        if sens_fnc == 'V_S':
            sens_function = 0
        elif sens_fnc == 'I_S':
            sens_function = 1
        elif sens_fnc == 'R_S':
            sens_function = 2
        else:
            self.log.error('Sensing function is not supported for this scan. 2D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_2D_array
        _, _, _, actual_delay, _, _, _, actual_integration_time = self._sample_smu.setup_sensing(sens_function, sens_autorange, sens_autozero, sens_delay, sens_achange, sens_four_port, 1, sens_int_time)

        start_time_scan = datetime.datetime.now()
        for entry in self._transport_2D_array:
            self._transport_2D_array[entry]['params']['Parameters for'] = '2D DC transport measurement'
            self._transport_2D_array[entry]['params']['X axis name'] = x_axis_sweep_parameter
            self._transport_2D_array[entry]['params']['X axis start'] = x_start
            self._transport_2D_array[entry]['params']['X axis stop'] = x_stop
            self._transport_2D_array[entry]['params']['X axis num'] = x_num
            self._transport_2D_array[entry]['params']['X axis autorange'] = x_autorange
            self._transport_2D_array[entry]['params']['Y axis name'] = y_axis_sweep_parameter
            self._transport_2D_array[entry]['params']['Y axis start'] = y_start
            self._transport_2D_array[entry]['params']['Y axis stop'] = y_stop
            self._transport_2D_array[entry]['params']['Y axis num'] = y_num
            self._transport_2D_array[entry]['params']['Y axis autorange'] = y_autorange
            self._transport_2D_array[entry]['params']['Sensed quantity'] = sens_fnc
            self._transport_2D_array[entry]['params']['Sensing autorange'] = sens_autorange
            self._transport_2D_array[entry]['params']['Sensing autozero'] = sens_autozero
            self._transport_2D_array[entry]['params']['Sensing delay'] = sens_delay
            self._transport_2D_array[entry]['params']['Sensing Achange'] = sens_achange
            self._transport_2D_array[entry]['params']['Sensing four port'] = sens_four_port
            self._transport_2D_array[entry]['params']['Sensing integration time (s)'] = actual_integration_time
            self._transport_2D_array[entry]['params']['Measurement start'] = start_time_scan.isoformat()
            
        #start sensing and outputs
        self._sample_smu.sensing_on()
        y_smu.output_on()
        x_smu.output_on()
        self.sig2DScanStarted.emit()

        #start measurement
        for idy, y_value in enumerate(y_array):
            y_fnc(y_value)
            for idx, x_value in enumerate(x_array):
                x_fnc(x_value)

                self._transport_2D_array[sens_fnc_key]['data'][idy][idx] = self._sample_smu.get_measurement(True)

                self.sig2DScanPointFinished.emit()

                if self._stop_request:
                    break

            if self._stop_request:
                break

        
        stop_time_scan = datetime.datetime.now()
        scan_duration = (stop_time_scan-start_time_scan).total_seconds()

        if self._stop_request:
            self.log.info(f'Measurement stopped at {int(scan_duration)}s.')
        else:
            self.log.info(f'Measurement finished at {int(scan_duration)}s. Yeehaa!')

        for entry in self._transport_2D_array:
            self._transport_2D_array[entry]['params']['Measurement stop'] = stop_time_scan.isoformat()
            self._transport_2D_array[entry]['params']['Total measurement time (s)'] = scan_duration

        self.reset_outputs()
        self.sigScanFinished.emit()
        self.sigScanAutoSave.emit()
        return self._transport_2D_array   
    
    def start_scan_1D_DC_transport(self, x_axis_sweep_parameter, x_axis_start, x_axis_stop, x_axis_num,
                                   use_DC_sample_current = True, DC_sample_current = 0, use_DC_sample_voltage = False, DC_sample_voltage = 0, use_DC_backgate_voltage = False, DC_backgate_voltage = 0,
                                   backgate_voltage_ramp_speed= 0.1, backgate_voltage_autorange = False, sample_voltage_ramp_speed = 0.1, sample_current_ramp_speed = 0.01, sample_transport_autorange = False,
                                   sens_fnc = 'R_S', sens_autorange = False, sens_autozero = False, sens_four_port = False, sens_achange = False, sens_delay = 0, sens_int_time = 0.1):
        
        if self.check_thread_active() or self.timetrace_loop_running:
            self.log.error("A measurement is currently running, stop it first!")
            self.sigScanFinished.emit()
            return
        
        if sens_fnc == x_axis_sweep_parameter:
            self.log.error(f"Sweeping {x_axis_sweep_parameter} and sensing {sens_fnc} does not make sense. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        if x_axis_sweep_parameter == 'V_G':
            if not use_DC_sample_current and not use_DC_sample_voltage:
                self.log.error(f"Sample current or sample voltage should be applied for backgate voltage sweep. Measurement is not started!")
                self.sigScanFinished.emit()
                return
            if (DC_sample_current == 0 and use_DC_sample_current) or (DC_sample_voltage == 0 and use_DC_sample_voltage):
                self.log.error(f"Sample current or sample voltage should be not zero for backgate voltage sweep. Measurement is not started!")
                self.sigScanFinished.emit()
                return
            fnt_target = self.scan_1D_DC_backgate_sweep
            args = (x_axis_start, x_axis_stop, x_axis_num,
                    use_DC_sample_current, DC_sample_current, use_DC_sample_voltage, DC_sample_voltage,
                    sample_voltage_ramp_speed, sample_current_ramp_speed, sample_transport_autorange,
                    backgate_voltage_ramp_speed, backgate_voltage_autorange,
                    sens_fnc, sens_autorange, sens_autozero,
                    sens_delay, sens_achange, sens_four_port, sens_int_time)
        
        elif x_axis_sweep_parameter == 'V_S' or x_axis_sweep_parameter == 'I_S':
            fnt_target = self.scan_1D_DC_sample_sweep
            args = (x_axis_start, x_axis_stop, x_axis_num,
                    use_DC_backgate_voltage, DC_backgate_voltage, backgate_voltage_ramp_speed, backgate_voltage_autorange,
                    sample_voltage_ramp_speed, sample_current_ramp_speed, x_axis_sweep_parameter, sample_transport_autorange,
                    sens_fnc, sens_autorange, sens_autozero,
                    sens_delay, sens_achange, sens_four_port, sens_int_time)
            
        
        else:
            self.log.error("Selected mode is not supported")
            self.sigScanFinished.emit()
            return
        
        if self._USE_THREADED:
            self._worker_thread = WorkerThread(target=fnt_target,
                                            args=args,
                                            name='1D_DC_transport')
            self.threadpool.start(self._worker_thread)

        else:
            self.sigScanFinished.emit()
            self.log.warning('Use threaded instead...')
    
    def scan_1D_DC_sample_sweep(self, x_start, x_stop, x_num,
                                use_DC_backgate_voltage, DC_backgate_voltage, backgate_voltage_ramp_speed, backgate_voltage_autorange,
                                sample_voltage_ramp_speed, sample_current_ramp_speed, src_fnc, src_autorange, 
                                sens_fnc, sens_autorange, sens_autozero,
                                sens_delay, sens_achange, sens_four_port, sens_int_time):
        
        self._stop_request = False
        
        #setup measurement arrays
        x_array = np.linspace(x_start, x_stop, x_num, endpoint=True)
        
        for x_value in x_array:
            if src_fnc == 'V_S':
                lower_voltage_limit, upper_voltage_limit = self._sample_smu.get_voltage_limit()
                if x_value<lower_voltage_limit or x_value>upper_voltage_limit:
                    self.log.error('Voltage sweep is outside the setted voltage limits. 1D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_1D_array
            elif src_fnc == 'I_S':
                lower_current_limit, upper_current_limit = self._sample_smu.get_current_limit()
                if x_value<lower_current_limit or x_value>upper_current_limit:
                    self.log.error('Current sweep is outside the setted current limits. 1D DC scan did not started!')
                    self.sigScanFinished.emit()
                    return self._transport_1D_array
            else:
                self.log.error('Source function is not supported for this scan. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array

        self._transport_1D_array = self.initialize_transport_1D_array(x_start, x_stop, x_num, src_fnc, [sens_fnc])
        sens_fnc_key = list(self._transport_1D_array.keys())[0]

        self._curr_scan_params = list(self._transport_1D_array.keys())

        #setup sample source
        self.reset_outputs()
        if src_fnc == 'V_S':
            self._sample_smu.set_source_function(0)
            self._sample_smu.set_source_volt_autorange(src_autorange)
            self._sample_smu.set_source_volt_ramp_speed(sample_voltage_ramp_speed)
            if not src_autorange:
                self._sample_smu.set_source_volt_range(max(abs(x_array[0]), abs(x_array[-1])))
        elif src_fnc == 'I_S':
            self._sample_smu.set_source_function(1)
            self._sample_smu.set_source_curr_autorange(src_autorange)
            self._sample_smu.set_source_curr_ramp_speed(sample_current_ramp_speed)
            if not src_autorange:
                self._sample_smu.set_source_curr_range(max(abs(x_array[0]), abs(x_array[-1])))
        else:
            self.log.error('Source function is not supported for this scan. 1D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_1D_array
        self._sample_smu.set_source_shape(0)
        self._sample_smu.set_source_mode(0)

        #setup gate source
        if use_DC_backgate_voltage:
            self._gate_voltage_source.set_source_volt_ramp_speed(backgate_voltage_ramp_speed)
            ret_val = self.set_backgate_DC_voltage(DC_backgate_voltage, backgate_voltage_autorange)
            if not ret_val:
                self.log.error('Backgate voltage was not set. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array
            self._gate_voltage_source.output_on()
            time.sleep(0.5)

        #setup sensing
        if sens_fnc == 'V_S':
            sens_function = 0
        elif sens_fnc == 'I_S':
            sens_function = 1
        elif sens_fnc == 'R_S':
            sens_function = 2
        else:
            self.log.error('Sensing function is not supported for this scan. 1D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_1D_array
        _, _, _, actual_delay, _, _, _, actual_integration_time = self._sample_smu.setup_sensing(sens_function, sens_autorange, sens_autozero, sens_delay, sens_achange, sens_four_port, 1, sens_int_time)

        start_time_scan = datetime.datetime.now()
        for entry in self._transport_1D_array:
            self._transport_1D_array[entry]['params']['Parameters for'] = '1D DC sample transport measurement'
            self._transport_1D_array[entry]['params']['X axis name'] = src_fnc
            self._transport_1D_array[entry]['params']['X axis start'] = x_start
            self._transport_1D_array[entry]['params']['X axis stop'] = x_stop
            self._transport_1D_array[entry]['params']['X axis num'] = x_num
            self._transport_1D_array[entry]['params']['X axis autorange'] = src_autorange
            if use_DC_backgate_voltage:
                self._transport_1D_array[entry]['params']['DC backgate voltage (V)'] = DC_backgate_voltage
            self._transport_1D_array[entry]['params']['Sensed quantity'] = sens_fnc
            self._transport_1D_array[entry]['params']['Sensing autorange'] = sens_autorange
            self._transport_1D_array[entry]['params']['Sensing autozero'] = sens_autozero
            self._transport_1D_array[entry]['params']['Sensing delay'] = sens_delay
            self._transport_1D_array[entry]['params']['Sensing Achange'] = sens_achange
            self._transport_1D_array[entry]['params']['Sensing four port'] = sens_four_port
            self._transport_1D_array[entry]['params']['Sensing integration time (s)'] = actual_integration_time
            self._transport_1D_array[entry]['params']['Measurement start'] = start_time_scan.isoformat()
            
        #start sensing and outputs
        self._sample_smu.sensing_on()
        self._sample_smu.output_on()
        self.sig1DScanStarted.emit()

        #start measurement
        for idx, x_value in enumerate(x_array):
            if src_fnc == 'V_S':
                self._sample_smu.set_voltage_level(x_value)
            elif src_fnc == 'I_S':
                self._sample_smu.set_current_level(x_value)

            self._transport_1D_array[sens_fnc_key]['data'][idx] = self._sample_smu.get_measurement(True)

            self.sig1DScanPointFinished.emit()

            if self._stop_request:
                break

        
        stop_time_scan = datetime.datetime.now()
        scan_duration = (stop_time_scan-start_time_scan).total_seconds()

        if self._stop_request:
            self.log.info(f'Measurement stopped at {int(scan_duration)}s.')
        else:
            self.log.info(f'Measurement finished at {int(scan_duration)}s. Yeehaa!')

        for entry in self._transport_1D_array:
            self._transport_1D_array[entry]['params']['Measurement stop'] = stop_time_scan.isoformat()
            self._transport_1D_array[entry]['params']['Total measurement time (s)'] = scan_duration

        self.reset_outputs()
        self.sigScanFinished.emit()
        self.sigScanAutoSave.emit()
        return self._transport_1D_array
            
    def scan_1D_DC_backgate_sweep(self, x_start, x_stop, x_num,
                                use_DC_sample_current, DC_sample_current, use_DC_sample_voltage, DC_sample_voltage,
                                sample_voltage_ramp_speed, sample_current_ramp_speed, sample_transport_autorange,
                                backgate_voltage_ramp_speed, backgate_voltage_autorange,
                                sens_fnc, sens_autorange, sens_autozero,
                                sens_delay, sens_achange, sens_four_port, sens_int_time):

        self._stop_request = False
        
        #setup measurement arrays
        x_array = np.linspace(x_start, x_stop, x_num, endpoint=True)
        
        for x_value in x_array:
            lower_voltage_limit, upper_voltage_limit = self._gate_voltage_source.get_voltage_limit()
            if x_value<lower_voltage_limit or x_value>upper_voltage_limit:
                self.log.error('Voltage sweep is outside the setted voltage limits. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array

        self._transport_1D_array = self.initialize_transport_1D_array(x_start, x_stop, x_num, 'V_G', [sens_fnc])
        sens_fnc_key = list(self._transport_1D_array.keys())[0]

        self._curr_scan_params = list(self._transport_1D_array.keys())

        #setup sample source
        self.reset_outputs()
        if use_DC_sample_voltage and not use_DC_sample_current:
            if DC_sample_voltage == 0:
                self.log.error('Sample voltage should not be zero. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array
            self._sample_smu.set_source_volt_ramp_speed(sample_voltage_ramp_speed)
            ret_val = self.set_sample_DC_voltage(DC_sample_voltage, sample_transport_autorange)
            if not ret_val:
                self.log.error('Sample voltage was not set. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array
            self._sample_smu.output_on()
            time.sleep(0.5)
        elif use_DC_sample_current and not use_DC_sample_voltage:
            if DC_sample_current == 0:
                self.log.error('Sample current should not be zero. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array
            self._sample_smu.set_source_curr_ramp_speed(sample_current_ramp_speed)
            ret_val = self.set_sample_DC_current(DC_sample_current, sample_transport_autorange)
            if not ret_val:
                self.log.error('Sample current was not set. 1D DC scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_1D_array
            self._sample_smu.output_on()
            time.sleep(0.5)
        else:
            self.log.error('No sample voltage or current applied. 1D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_1D_array
        
        #setup gate source
        self._gate_voltage_source.set_source_function(0)
        autorange = self._gate_voltage_source.set_source_volt_autorange(backgate_voltage_autorange)
        self._gate_voltage_source.set_source_volt_ramp_speed(backgate_voltage_ramp_speed)
        if not autorange:
            self._gate_voltage_source.set_source_volt_range(max(abs(x_array[0]), abs(x_array[-1])))
        self._gate_voltage_source.set_source_shape(0)
        self._gate_voltage_source.set_source_mode(0)


        #setup sensing
        if sens_fnc == 'V_S':
            sens_function = 0
        elif sens_fnc == 'I_S':
            sens_function = 1
        elif sens_fnc == 'R_S':
            sens_function = 2
        else:
            self.log.error('Sensing function is not supported for this scan. 1D DC scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_1D_array
        _, _, _, actual_delay, _, _, _, actual_integration_time = self._sample_smu.setup_sensing(sens_function, sens_autorange, sens_autozero, sens_delay, sens_achange, sens_four_port, 1, sens_int_time)

        start_time_scan = datetime.datetime.now()
        for entry in self._transport_1D_array:
            self._transport_1D_array[entry]['params']['Parameters for'] = '1D DC sample transport measurement'
            self._transport_1D_array[entry]['params']['X axis name'] = 'V_G'
            self._transport_1D_array[entry]['params']['X axis start'] = x_start
            self._transport_1D_array[entry]['params']['X axis stop'] = x_stop
            self._transport_1D_array[entry]['params']['X axis num'] = x_num
            self._transport_1D_array[entry]['params']['X axis autorange'] = backgate_voltage_autorange
            if use_DC_sample_voltage:
                self._transport_1D_array[entry]['params']['DC sample voltage (V)'] = DC_sample_voltage
            if use_DC_sample_current:
                self._transport_1D_array[entry]['params']['DC sample current (A)'] = DC_sample_current
            self._transport_1D_array[entry]['params']['Sensed quantity'] = sens_fnc
            self._transport_1D_array[entry]['params']['Sensing autorange'] = sens_autorange
            self._transport_1D_array[entry]['params']['Sensing autozero'] = sens_autozero
            self._transport_1D_array[entry]['params']['Sensing delay'] = sens_delay
            self._transport_1D_array[entry]['params']['Sensing Achange'] = sens_achange
            self._transport_1D_array[entry]['params']['Sensing four port'] = sens_four_port
            self._transport_1D_array[entry]['params']['Sensing integration time (s)'] = actual_integration_time
            self._transport_1D_array[entry]['params']['Measurement start'] = start_time_scan.isoformat()
            
        #start sensing and outputs
        self._sample_smu.sensing_on()
        self._gate_voltage_source.output_on()
        self.sig1DScanStarted.emit()

        #start measurement
        for idx, x_value in enumerate(x_array):
            self._gate_voltage_source.set_voltage_level(x_value)

            self._transport_1D_array[sens_fnc_key]['data'][idx] = self._sample_smu.get_measurement(True)

            self.sig1DScanPointFinished.emit()

            if self._stop_request:
                break

        
        stop_time_scan = datetime.datetime.now()
        scan_duration = (stop_time_scan-start_time_scan).total_seconds()

        if self._stop_request:
            self.log.info(f'Measurement stopped at {int(scan_duration)}s.')
        else:
            self.log.info(f'Measurement finished at {int(scan_duration)}s. Yeehaa!')

        for entry in self._transport_1D_array:
            self._transport_1D_array[entry]['params']['Measurement stop'] = stop_time_scan.isoformat()
            self._transport_1D_array[entry]['params']['Total measurement time (s)'] = scan_duration

        self.reset_outputs()
        self.sigScanFinished.emit()
        self.sigScanAutoSave.emit()
        return self._transport_1D_array
    
    def start_timetrace_DC_transport(self,timestep = 1, measure_temperature = False,
                                   use_DC_sample_current = True, DC_sample_current = 0, use_DC_sample_voltage = False, DC_sample_voltage = 0, use_DC_backgate_voltage = False, DC_backgate_voltage = 0,
                                   backgate_voltage_ramp_speed= 0.1, backgate_voltage_autorange = False, sample_voltage_ramp_speed = 0.1, sample_current_ramp_speed = 0.01, sample_transport_autorange = False,
                                   sens_fnc = 'R_S', sens_autorange = False, sens_autozero = False, sens_four_port = False, sens_achange = False, sens_delay = 0, sens_int_time = 0.1):
        if self.check_thread_active() or self.timetrace_loop_running:
            self.log.error("A measurement is currently running, stop it first!")
            self.sigScanFinished.emit()
            return
        
        if not use_DC_sample_current and not use_DC_sample_voltage:
            self.log.error(f"Sample current or sample voltage should be applied for timetrace transport measurement. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        if (DC_sample_current == 0 and use_DC_sample_current) or (DC_sample_voltage == 0 and use_DC_sample_voltage):
            self.log.error(f"Sample current or sample voltage should be not zero for timetrace transport measurement. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        if (use_DC_sample_current and sens_fnc == 'I_S') or (use_DC_sample_voltage and sens_fnc == 'V_S'):
            self.log.error(f"Applying sample current or voltage and measure sample current or voltage does not make sense. Measurement is not started!")
            self.sigScanFinished.emit()
            return
        
        fnt_target = self.measure_timetrace_DC_transport
        args = (timestep, measure_temperature, use_DC_sample_current, DC_sample_current, use_DC_sample_voltage, DC_sample_voltage, use_DC_backgate_voltage, DC_backgate_voltage,
                backgate_voltage_ramp_speed, backgate_voltage_autorange, sample_voltage_ramp_speed, sample_current_ramp_speed, sample_transport_autorange,
                sens_fnc, sens_autorange, sens_autozero, sens_four_port, sens_achange, sens_delay, sens_int_time)
        
        if self._USE_THREADED:
            self._worker_thread = WorkerThread(target=fnt_target,
                                            args=args,
                                            name='timetrace_DC_transport')
            self.threadpool.start(self._worker_thread)

        else:
            self.sigScanFinished.emit()
            self.log.warning('Use threaded instead...')

    def measure_timetrace_DC_transport(self, timestep, measure_temperature, use_DC_sample_current, DC_sample_current, use_DC_sample_voltage, DC_sample_voltage, use_DC_backgate_voltage, DC_backgate_voltage,
                                        backgate_voltage_ramp_speed, backgate_voltage_autorange, sample_voltage_ramp_speed, sample_current_ramp_speed, sample_transport_autorange,
                                        sens_fnc, sens_autorange, sens_autozero, sens_four_port, sens_achange, sens_delay, sens_int_time):
        self._stop_request = False
        
        #setup measurement arrays
        self._transport_timetrace_array = self.initialize_transport_timetrace_array([sens_fnc])
        self.timetrace_loop_sens_fnc_key = list(self._transport_timetrace_array.keys())[0]

        self._curr_scan_params = list(self._transport_timetrace_array.keys())

        #setup sample source
        self.reset_outputs()
        if use_DC_sample_voltage and not use_DC_sample_current:
            if DC_sample_voltage == 0:
                self.log.error('Sample voltage should not be zero. DC timetrace did not started!')
                self.sigScanFinished.emit()
                return self._transport_timetrace_array
            self._sample_smu.set_source_volt_ramp_speed(sample_voltage_ramp_speed)
            ret_val = self.set_sample_DC_voltage(DC_sample_voltage, sample_transport_autorange)
            if not ret_val:
                self.log.error('Sample voltage was not set. DC timetrace scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_timetrace_array
            self._sample_smu.output_on()
            time.sleep(0.5)
        elif use_DC_sample_current and not use_DC_sample_voltage:
            if DC_sample_current == 0:
                self.log.error('Sample current should not be zero. DC timetrace scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_timetrace_array
            self._sample_smu.set_source_curr_ramp_speed(sample_current_ramp_speed)
            ret_val = self.set_sample_DC_current(DC_sample_current, sample_transport_autorange)
            if not ret_val:
                self.log.error('Sample current was not set. DC timetrace scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_timetrace_array
            self._sample_smu.output_on()
            time.sleep(0.5)
        else:
            self.log.error('No sample voltage or current applied. DC timetrace scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_timetrace_array
        
        #setup gate source
        if use_DC_backgate_voltage:
            self._gate_voltage_source.set_source_volt_ramp_speed(backgate_voltage_ramp_speed)
            ret_val = self.set_backgate_DC_voltage(DC_backgate_voltage, backgate_voltage_autorange)
            if not ret_val:
                self.log.error('Backgate voltage was not set. DC timetrace scan did not started!')
                self.sigScanFinished.emit()
                return self._transport_timetrace_array
            self._gate_voltage_source.output_on()
            time.sleep(0.5)

        #setup sensing
        if sens_fnc == 'V_S':
            sens_function = 0
        elif sens_fnc == 'I_S':
            sens_function = 1
        elif sens_fnc == 'R_S':
            sens_function = 2
        else:
            self.log.error('Sensing function is not supported for this scan. DC timetrace scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_timetrace_array
        _, _, _, actual_delay, _, _, _, actual_integration_time = self._sample_smu.setup_sensing(sens_function, sens_autorange, sens_autozero, sens_delay, sens_achange, sens_four_port, 1, sens_int_time)

        if (actual_integration_time+actual_delay)>timestep:
            self.reset_outputs()
            self.log.error('Actual integration time + actual sensing delay is larger than timetrace timestep. DC timetrace scan did not started!')
            self.sigScanFinished.emit()
            return self._transport_timetrace_array

        self.timetrace_start_time = datetime.datetime.now()
        for entry in self._transport_timetrace_array:
            self._transport_timetrace_array[entry]['params']['Parameters for'] = 'DC timetrace transport measurement'
            self._transport_timetrace_array[entry]['params']['X axis name'] = 'Time'
            if use_DC_sample_voltage:
                self._transport_timetrace_array[entry]['params']['DC sample voltage (V)'] = DC_sample_voltage
            if use_DC_sample_current:
                self._transport_timetrace_array[entry]['params']['DC sample current (A)'] = DC_sample_current
            if use_DC_backgate_voltage:
                self._transport_timetrace_array[entry]['params']['DC backgate voltage (V)'] = DC_backgate_voltage
            self._transport_timetrace_array[entry]['params']['Sensed quantity'] = sens_fnc
            self._transport_timetrace_array[entry]['params']['Sensing autorange'] = sens_autorange
            self._transport_timetrace_array[entry]['params']['Sensing autozero'] = sens_autozero
            self._transport_timetrace_array[entry]['params']['Sensing delay'] = sens_delay
            self._transport_timetrace_array[entry]['params']['Sensing Achange'] = sens_achange
            self._transport_timetrace_array[entry]['params']['Sensing four port'] = sens_four_port
            self._transport_timetrace_array[entry]['params']['Sensing integration time (s)'] = actual_integration_time
            self._transport_timetrace_array[entry]['params']['Measurement start'] = self.timetrace_start_time.isoformat()
            
        #start sensing and outputs
        self._sample_smu.sensing_on()
        self.timetrace_timestep = timestep-actual_integration_time-actual_delay
        self.timetrace_measure_temperature = measure_temperature
        self.sigTimetraceStarted.emit()

    def start_timetrace_loop(self):
        self.timetrace_loop_running = True
        self.timetrace_timer.setSingleShot(True)
        self.timetrace_timer.setInterval(self.timetrace_timestep * 1000)  # in ms
        self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['data'][0] = self._sample_smu.get_measurement(True)
        if self.timetrace_measure_temperature:
            self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['temperature_data'][0] = self._controller.get_sample_temp()
        else:
            self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['temperature_data'][0] = 0
        self.sigTimetracePointFinished.emit()
        self.timetrace_timer.start()


    def timetrace_loop(self):
        current_time = datetime.datetime.now()
        scan_duration = (current_time-self.timetrace_start_time).total_seconds()
        self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['x_axis'] = np.append(self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['x_axis'], scan_duration)
        self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['data'] = np.append(self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['data'], self._sample_smu.get_measurement(True))
        if self.timetrace_measure_temperature:
            self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['temperature_data'] = np.append(self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['temperature_data'], self._controller.get_sample_temp())
        else:
            self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['temperature_data'] = np.append(self._transport_timetrace_array[self.timetrace_loop_sens_fnc_key]['temperature_data'], 0)
        self.sigTimetracePointFinished.emit()
        if self._stop_request:
            self.log.info(f'Measurement stopped at {int(scan_duration)}s.')

            for entry in self._transport_timetrace_array:
                self._transport_timetrace_array[entry]['params']['Measurement stop'] = current_time.isoformat()
                self._transport_timetrace_array[entry]['params']['Total measurement time (s)'] = scan_duration

            self.reset_outputs()
            self.timetrace_loop_running = False
            self.sigScanFinished.emit()
            self.sigScanAutoSave.emit()
            return self._transport_timetrace_array
        
        else:
            self.timetrace_timer.start()

    def set_gate_voltage_limits(self, gate_voltage_lower_limit, gate_voltage_upper_limit):
        self.axis_units['V_G']['upper_limit'] = gate_voltage_upper_limit
        self.axis_units['V_G']['lower_limit'] = gate_voltage_lower_limit
        self._gate_voltage_source.set_voltage_limit(gate_voltage_lower_limit, gate_voltage_upper_limit)

    def set_sample_voltage_limits(self, sample_voltage_lower_limit, sample_voltage_upper_limit):
        self.axis_units['V_S']['upper_limit'] = sample_voltage_upper_limit
        self.axis_units['V_S']['lower_limit'] = sample_voltage_lower_limit
        self._sample_smu.set_voltage_limit(sample_voltage_lower_limit, sample_voltage_upper_limit)

    def set_sample_current_limits(self, sample_current_lower_limit, sample_current_upper_limit):
        self.axis_units['I_S']['upper_limit'] = sample_current_upper_limit
        self.axis_units['I_S']['lower_limit'] = sample_current_lower_limit
        self._sample_smu.set_current_limit(sample_current_lower_limit, sample_current_upper_limit)

    def get_sample_source_limits(self):
        return self._sample_smu.get_limits()
    
    def get_gate_source_limits(self):
        return self._gate_voltage_source.get_limits()
    
    def set_sample_DC_current(self, current, autorange = False):
        lower_current_limit, upper_current_limit = self._sample_smu.get_current_limit()
        if current<lower_current_limit or current>upper_current_limit:
            self.log.error('Sample DC current is outside the setted voltage limits. DC current is not setted.')
            return False
        self._sample_smu.set_DC_current(current, autorange)
        return True
    
    def set_sample_DC_voltage(self, voltage, autorange = False):
        lower_voltage_limit, upper_voltage_limit = self._sample_smu.get_voltage_limit()
        if voltage<lower_voltage_limit or voltage>upper_voltage_limit:
            self.log.error('Sample DC voltage is outside the setted voltage limits. DC voltage is not setted.')
            return False
        self._sample_smu.set_DC_voltage(voltage, autorange)
        return True

    def set_backgate_DC_voltage(self, voltage, autorange = False):
        lower_voltage_limit, upper_voltage_limit = self._gate_voltage_source.get_voltage_limit()
        if voltage<lower_voltage_limit or voltage>upper_voltage_limit:
            self.log.error('Backgate DC voltage is outside the setted voltage limits. DC voltage is not setted.')
            return False
        self._gate_voltage_source.set_DC_voltage(voltage, autorange)
        return True

    def outputs_on(self):
        self._sample_smu.output_on()
        self._gate_voltage_source.output_on()

    def reset_outputs(self):
        self._sample_smu.output_off()
        self._gate_voltage_source.output_off()
        self._sample_smu.set_current_level(0)
        self._sample_smu.set_voltage_level(0)
        self._gate_voltage_source.set_voltage_level(0)

    def check_thread_active(self):
        """ Check whether current worker thread is running. """

        if hasattr(self, '_worker_thread'):
            if self._worker_thread.is_running():
                return True
        return False
    
    def save_transport_data(self, tag=None, save_to_gwyddion = False):

        scan_params = self._curr_scan_params
        
        if scan_params == []:
            self.log.warning('Nothing measured to be saved for the transport measurement. Save routine skipped.')
            self.sigDataSaved.emit()
            return

        save_path =  self._save_logic.get_path_for_module(module_name='Transport')

        timestamp = datetime.datetime.now()

        if '1D' in scan_params[0]:
            data = self.get_1D_data()

            empty_array = np.ones(len(scan_params))

            for index, entry in enumerate(scan_params):
                parameters = {}
                parameters.update(data[entry]['params'])
                nice_name = data[entry]['data_info']['nice_name']
                unit = data[entry]['data_info']['si_units']

                parameters['Name of measured signal'] = nice_name
                parameters['Units of measured signal'] = unit

                figure_data = data[entry]['data']
                axis_data = data[entry]['x_axis']

                # check whether figure has only zeros as data, skip this then
                if not np.any(figure_data):
                    self.log.debug(f'The data array "{entry}" contains only zeros and will be not saved.')
                    empty_array[index] = 0
                    continue

                x_axis_nice_name = data[entry]['x_axis_info']['nice_name']
                x_axis_unit = data[entry]['x_axis_info']['si_units']

                parameters['Name of X axis'] = x_axis_nice_name
                parameters['Units of X axis'] = x_axis_unit

                cbar_range = data[entry]['display_range']

                parameters['display_range'] = cbar_range

                fig = self.draw_1D_figure(figure_data, axis_data, scan_axis=x_axis_nice_name, scan_axis_unit =x_axis_unit,
                                            signal_name=nice_name, signal_unit=unit)

                image_data = {}
                image_data[f'1D transport scan image of a {nice_name} measurement without axis.\n'
                        f'Signal is in {unit}:'] = figure_data

                filelabel = f'1D_transport_{entry}'

                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'
                
                fig.suptitle(f'{save_path}\{filelabel}', fontsize=8)

                fig = self._save_logic.save_data(image_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        plotfig=fig)

                # prepare the full raw data in an OrderedDict:

                signal_name = data[entry]['data_info']['nice_name']
                units_signal = data[entry]['data_info']['si_units']

                raw_data = {}
                raw_data[x_axis_nice_name + ' ('+ x_axis_unit +')'] = data[entry]['x_axis'].flatten()
                raw_data[f'{signal_name} ({units_signal})'] = data[entry]['data'].flatten()

                filelabel = filelabel + '_raw'

                self._save_logic.save_data(raw_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t')
                
            if np.any(empty_array):
                filelabel = '1D_transport_array_raw'
                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'

                filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '.pickle')
                pickle_fname = os.path.join(save_path,filename)

                try:
                    with open(pickle_fname, 'wb') as f:
                        pickle.dump(data, f, protocol=4)
                except:
                    self.log.info('1D transport data to large for pickel. Trying out joblib pickling instead.')
                    try:
                        filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '_joblib.pickle')
                        joblib_fname = os.path.join(save_path,filename)
                        with open(joblib_fname, 'wb') as f:
                            joblib.dump(data, f, compress = 3)
                    except:
                        self.log.error('Joblib pickle failed. 1D transport data is not saved as pickle. Data has to be saved saparetly.')

        if 'Timetrace' in scan_params[0]:
            data = self.get_timetrace_data()

            empty_array = np.ones(len(scan_params))

            for index, entry in enumerate(scan_params):
                parameters = {}
                parameters.update(data[entry]['params'])
                nice_name = data[entry]['data_info']['nice_name']
                unit = data[entry]['data_info']['si_units']

                parameters['Name of measured signal'] = nice_name
                parameters['Units of measured signal'] = unit

                figure_data = data[entry]['data']
                axis_data = data[entry]['x_axis']

                # check whether figure has only zeros as data, skip this then
                if not np.any(figure_data):
                    self.log.debug(f'The data array "{entry}" contains only zeros and will be not saved.')
                    empty_array[index] = 0
                    continue

                x_axis_nice_name = data[entry]['x_axis_info']['nice_name']
                x_axis_unit = data[entry]['x_axis_info']['si_units']

                parameters['Name of X axis'] = x_axis_nice_name
                parameters['Units of X axis'] = x_axis_unit

                cbar_range = data[entry]['display_range']

                parameters['display_range'] = cbar_range

                fig = self.draw_1D_figure(figure_data, axis_data, scan_axis=x_axis_nice_name, scan_axis_unit =x_axis_unit,
                                            signal_name=nice_name, signal_unit=unit)

                image_data = {}
                image_data[f'Timetrace transport image of a {nice_name} measurement without axis.\n'
                        f'Signal is in {unit}:'] = figure_data

                filelabel = f'Timetrace_transport_{entry}'

                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'
                
                fig.suptitle(f'{save_path}\{filelabel}', fontsize=8)

                fig = self._save_logic.save_data(image_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        plotfig=fig)

                # prepare the full raw data in an OrderedDict:

                signal_name = data[entry]['data_info']['nice_name']
                units_signal = data[entry]['data_info']['si_units']

                raw_data = {}
                raw_data[x_axis_nice_name + ' ('+ x_axis_unit +')'] = data[entry]['x_axis'].flatten()
                raw_data[f'{signal_name} ({units_signal})'] = data[entry]['data'].flatten()

                filelabel = filelabel + '_raw'

                self._save_logic.save_data(raw_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t')
                
                #save temperature data
                parameters = {}
                parameters.update(data[entry]['params'])
                nice_name = data[entry]['temperature_info']['nice_name']
                unit = data[entry]['temperature_info']['si_units']

                parameters['Name of measured signal'] = nice_name
                parameters['Units of measured signal'] = unit

                figure_data = data[entry]['temperature_data']
                axis_data = data[entry]['x_axis']

                # check whether figure has only zeros as data, skip this then
                if not np.any(figure_data):
                    self.log.debug(f'The data array "{entry}_temperature" contains only zeros and will be not saved.')
                    empty_array[index] = 0
                    continue

                x_axis_nice_name = data[entry]['x_axis_info']['nice_name']
                x_axis_unit = data[entry]['x_axis_info']['si_units']

                parameters['Name of X axis'] = x_axis_nice_name
                parameters['Units of X axis'] = x_axis_unit

                cbar_range = data[entry]['display_range']

                parameters['display_range'] = cbar_range

                fig = self.draw_1D_figure(figure_data, axis_data, scan_axis=x_axis_nice_name, scan_axis_unit =x_axis_unit,
                                            signal_name=nice_name, signal_unit=unit)

                image_data = {}
                image_data[f'Timetrace temperature image of a {nice_name} measurement without axis.\n'
                        f'Signal is in {unit}:'] = figure_data

                filelabel = f'Timetrace_temperature_{entry}'

                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'
                
                fig.suptitle(f'{save_path}\{filelabel}', fontsize=8)

                fig = self._save_logic.save_data(image_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        plotfig=fig)

                # prepare the full raw data in an OrderedDict:

                signal_name = data[entry]['temperature_info']['nice_name']
                units_signal = data[entry]['temperature_info']['si_units']

                raw_data = {}
                raw_data[x_axis_nice_name + ' ('+ x_axis_unit +')'] = data[entry]['x_axis'].flatten()
                raw_data[f'{signal_name} ({units_signal})'] = data[entry]['temperature_data'].flatten()

                filelabel = filelabel + '_raw'

                self._save_logic.save_data(raw_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t')
                
            if np.any(empty_array):
                filelabel = 'Timetrace_transport_array_raw'
                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'

                filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '.pickle')
                pickle_fname = os.path.join(save_path,filename)

                try:
                    with open(pickle_fname, 'wb') as f:
                        pickle.dump(data, f, protocol=4)
                except:
                    self.log.info('Timetrace transport data to large for pickel. Trying out joblib pickling instead.')
                    try:
                        filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '_joblib.pickle')
                        joblib_fname = os.path.join(save_path,filename)
                        with open(joblib_fname, 'wb') as f:
                            joblib.dump(data, f, compress = 3)
                    except:
                        self.log.error('Joblib pickle failed. Timetrace transport data is not saved as pickle. Data has to be saved saparetly.')

        else:
            data = self.get_2D_data()

            empty_array = np.ones(len(scan_params))

            for index, entry in enumerate(scan_params):
                parameters = {}
                parameters.update(data[entry]['params'])
                nice_name = data[entry]['data_info']['nice_name']
                unit = data[entry]['data_info']['si_units']

                parameters['Name of measured signal'] = nice_name
                parameters['Units of measured signal'] = unit

                figure_data = data[entry]['data']

                # check whether figure has only zeros as data, skip this then
                if not np.any(figure_data):
                    self.log.debug(f'The data array "{entry}" contains only zeros and will be not saved.')
                    empty_array[index] = 0
                    continue

                image_extent = [data[entry]['x_axis'][0],
                                data[entry]['x_axis'][-1],
                                data[entry]['y_axis'][0],
                                data[entry]['y_axis'][-1]]

                x_axis_nice_name = data[entry]['x_axis_info']['nice_name']
                x_axis_unit = data[entry]['x_axis_info']['si_units']
                y_axis_nice_name = data[entry]['y_axis_info']['nice_name']
                y_axis_unit = data[entry]['y_axis_info']['si_units']
                axes = [x_axis_nice_name, y_axis_nice_name]
                axes_units = [x_axis_unit, y_axis_unit]

                parameters['Name of X axis'] = x_axis_nice_name
                parameters['Units of X axis'] = x_axis_unit
                parameters['Name of Y axis'] = y_axis_nice_name
                parameters['Units of Y axis'] = y_axis_unit

                cbar_range = data[entry]['display_range']

                parameters['display_range'] = cbar_range

                fig = self.draw_2D_figure(figure_data, image_extent, scan_axis=axes, scan_axis_unit =axes_units, cbar_range=cbar_range,
                                            signal_name=nice_name, signal_unit=unit)

                image_data = {}
                image_data[f'2D transport scan image of a {nice_name} measurement without axis.\n'
                        'The upper left entry represents the signal at the upper left pixel position.\n'
                        'A pixel-line in the image corresponds to a row '
                        f'of entries where the Signal is in {unit}:'] = figure_data

                filelabel = f'2D_transport_{entry}'

                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'
                
                fig.suptitle(f'{save_path}\{filelabel}', fontsize=8)

                fig = self._save_logic.save_data(image_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        plotfig=fig)

                # prepare the full raw data in an OrderedDict:

                signal_name = data[entry]['data_info']['nice_name']
                units_signal = data[entry]['data_info']['si_units']

                raw_data = {}
                raw_data[x_axis_nice_name + ' ('+ x_axis_unit +')'] = np.tile(data[entry]['x_axis'], len(data[entry]['x_axis']))
                raw_data[y_axis_nice_name + ' ('+ y_axis_unit +')'] = np.repeat(data[entry]['y_axis'], len(data[entry]['y_axis']))
                raw_data[f'{signal_name} ({units_signal})'] = data[entry]['data'].flatten()

                filelabel = filelabel + '_raw'

                self._save_logic.save_data(raw_data,
                                        filepath=save_path,
                                        timestamp=timestamp,
                                        parameters=parameters,
                                        filelabel=filelabel,
                                        fmt='%.6e',
                                        delimiter='\t')

            #Save array in pickle
            if np.any(empty_array):
                filelabel = '2D_transport_array_raw'
                if tag is not None:
                    filelabel = f'{tag}_{filelabel}'

                filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '.pickle')
                pickle_fname = os.path.join(save_path,filename)

                try:
                    with open(pickle_fname, 'wb') as f:
                        pickle.dump(data, f, protocol=4)
                except:
                    self.log.info('2D transport data to large for pickel. Trying out joblib pickling instead.')
                    try:
                        filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '_joblib.pickle')
                        joblib_fname = os.path.join(save_path,filename)
                        with open(joblib_fname, 'wb') as f:
                            joblib.dump(data, f, compress = 3)
                    except:
                        self.log.error('Joblib pickle failed. 2D transport data is not saved as pickle. Data has to be saved saparetly.')

            if save_to_gwyddion:
                filename = timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + tag + '_2D_transport.gwy') 

                # threaded
                self.start_save_to_gwyddion(dataobj=data, timestamp=timestamp,
                                            gwyobjtype='2D_transport',filename=os.path.join(save_path,filename))
        
        self.sigDataSaved.emit()

    def draw_1D_figure(self, figure_data, axis_data, scan_axis=None, scan_axis_unit =None,
                                            signal_name='', signal_unit=''):
        prefix = { -4: 'p', -3: 'n',         # prefix to use for powers of 1000
                   -2: r'$\mathrm{\mu}$', -1: 'm', 
                    0: '', 1:'k', 
                    2: 'M', 3: 'G', 
                    4: 'T'}

        if scan_axis is None:
            scan_axis = 'X'

        if scan_axis_unit is None:
            scan_axis_unit = 'a.u.'

        image_data = figure_data.copy()
            
        # Scale data, determine SI prefix 
        value_range =  [np.nanmin(image_data), np.nanmax(image_data)]
        n = floor(log10(max([abs(v) for v in value_range])))  // 3     # 1000^n 
        scale_fac = 1 / 1000**n

        # scale the data
        scaled_data = image_data*scale_fac
        c_prefix = prefix[n]    # data prefix

        # ------------------
        # coordinate scaling
        # ------------------
        # Scale axes values using SI prefix
        #prefix[-2] = 'u'  # use simple ascii for axes with 1000^-2
        image_dimension = [axis_data[0], axis_data[-1]]

        if np.allclose(image_dimension, np.zeros_like(image_dimension), atol=0.0):
            n = 0
        else:
            n = floor(log10(max([abs(v) for v in image_dimension])))  // 3     # 1000^n 

        axis_data = [v / 1000**n for v in axis_data]
        x_prefix = prefix[n]

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, ax = plt.subplots()

        prop_cycle = self._save_logic.mpl_qd_style['axes.prop_cycle']
        colors = {}
        for i, color_setting in enumerate(prop_cycle):
            colors[i] = color_setting['color']
        
        ax.plot(axis_data, scaled_data, '-o', linestyle=':', linewidth=0.5, color=colors[0])

        ax.set_xlabel(scan_axis + ' (' + x_prefix + scan_axis_unit + ')')
        ax.set_ylabel(signal_name + ' (' + c_prefix + signal_unit + ')')
        ax.set_xlim(np.min(axis_data), np.max(axis_data))
        
        return fig
    

    def draw_2D_figure(self, image_data_in, image_extent, scan_axis=None, scan_axis_unit = None, cbar_range=None, signal_name='', signal_unit=''):

        # Prefix definition for SI units measurement, powers of 1000
        prefix = { -4: 'p', -3: 'n',         # prefix to use for powers of 1000
                   -2: r'$\mathrm{\mu}$', -1: 'm', 
                    0: '', 1:'k', 
                    2: 'M', 3: 'G', 
                    4: 'T'}

        if scan_axis is None:
            scan_axis = ['X', 'Y']

        if scan_axis_unit is None:
            scan_axis_unit = ['a.u.', 'a.u.']

        image_data = image_data_in.copy()
            
        # Scale data, determine SI prefix 
        value_range =  [np.nanmin(image_data), np.nanmax(image_data)]
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

        image_dimension_x = image_dimension[:2]
        if np.allclose(image_dimension_x, np.zeros_like(image_dimension_x), atol=0.0):
            n = 0
        else:
            n = floor(log10(max([abs(v) for v in image_dimension_x])))  // 3     # 1000^n 

        image_dimension_x = [v / 1000**n for v in image_dimension_x]
        x_prefix = prefix[n]

        image_dimension_y = image_dimension[2:]
        if np.allclose(image_dimension_y, np.zeros_like(image_dimension_y), atol=0.0):
            n = 0
        else:
            n = floor(log10(max([abs(v) for v in image_dimension_y])))  // 3     # 1000^n 

        image_dimension_y = [v / 1000**n for v in image_dimension_y]
        y_prefix = prefix[n]

        image_dimension = image_dimension_x+image_dimension_y

        self.log.debug(('image_dimension: ', image_dimension))

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, ax = plt.subplots()

        # Create image plot
        color_map = 'bwr'
        
        cfimage = ax.imshow(scaled_data,
                            cmap=plt.get_cmap(color_map), # reference the right place in qd
                            origin="lower",
                            vmin=draw_cb_range[0],
                            vmax=draw_cb_range[1],
                            interpolation='none',
                            extent=image_dimension
                            )

        ax.set_aspect(1)
        ax.set_xlabel(scan_axis[0] + ' (' + x_prefix + scan_axis_unit[0] + ')')
        ax.set_ylabel(scan_axis[1] + ' (' + y_prefix + scan_axis_unit[1] + ')')
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

        self._save_to_gwyddion(dataobj, gwyobjtype, savefilename, datakeys)

    def _save_to_gwyddion(self, dataobj, gwyobjtype=None, filename=None, datakeys=None):
        """ 'save_data' method selector (called in thread) 
            - method depends on gwytype specified
        """

        if gwyobjtype in self._gwyobjecttypes['imgobjects']:
            self._save_obj_to_gwyddion(dataobj=dataobj,filename=filename,datakeys=datakeys,gwytypes=['image'])
        # elif gwyobjtype in self._gwyobjecttypes['graphobjects']:
        #     self._save_esr_to_gwyddion(dataobj=dataobj,filename=filename,datakeys=datakeys)
        else:
            self.log.error(f"SaveLogicGwyddion(): unknown gwyobjtype specified: {gwyobjtype}")

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
            if not {'x_axis','y_axis','data'}.issubset(set(meas.keys())):
                continue 

            # check that there is non-trivial data (skip empty measurements)
            if np.sum(meas['data']) == 0.0:
                continue

            # transform data
            #scalefactor = meas['scale_fac']
            coord0 = meas['x_axis']
            coord1 = meas['y_axis']
            data_si = meas['data'] #* scalefactor
            xyz_data = np.array([x for j in range(coord1.shape[0]) 
                                for i in range(coord0.shape[0]) 
                                for x in (coord0[i], coord1[j], data_si[j,i])]) 

            params = meas['params']

            coord0_start = next(k for k in params.keys() if k.startswith('X axis start'))
            coord0_stop = next(k for k in params.keys() if k.startswith('X axis stop'))
            coord1_start = next(k for k in params.keys() if k.startswith('Y axis start'))
            coord1_stop = next(k for k in params.keys() if k.startswith('Y axis stop'))

            xy_units = 'a.u.'
            z_units = meas['data_info']['si_units']
            measname = datak + ":" + meas['data_info']['nice_name']
            
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
                objout['/' + str(dataki) + '/base/palette'] = 'Sky'
                objout[basekey] = img
                # comment meta data
                if meas['params']:
                    d = {key: str(val) for key, val in meas['params'].items()}
                    meta = gwy.objects.GwyContainer(d)
                    objout['/' + str(dataki) + '/meta'] = meta
                
            if 'xyz' in gwytypes:
                # xyz types
                basekey = '/surface/' + str(dataki) 
                objout[basekey + '/title'] = measname
                objout[basekey] = xyz
                objout[basekey + '/preview'] = img
                objout[basekey + '/visible'] = True
                if meas['params']:
                    d = {key: str(val) for key, val in meas['params'].items()}
                    meta = gwy.objects.GwyContainer(d)
                    objout[basekey + '/meta'] = meta

            

        # write out file    
        if objout:
            objout.tofile(filename)

    def set_color_map(self, cmap_name):
        """  Sets the color map to be used in the 'display_figures' routine
            This information is set from the Gui definition of the color map

        @param str cmap_name:  color map name (from Matplotlib) to be used for save figures
        """
        self._color_map = cmap_name