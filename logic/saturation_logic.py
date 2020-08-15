#-*- coding: utf-8 -*-
"""
Laser management.

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

from collections import OrderedDict
from core.util import units
import time
import numpy as np
import random
import datetime
from qtpy import QtCore
import matplotlib.pyplot as plt
import numpy as np
import copy
import lmfit.model
from bayes_opt import BayesianOptimization, UtilityFunction

from core.module import Connector, ConfigOption, StatusVar
from logic.generic_logic import GenericLogic
from interface.simple_laser_interface import ControlMode, ShutterState, LaserState

class WorkerThread(QtCore.QRunnable):
    """ Create a simple Worker Thread class, with a similar usage to a python
    Thread object. This Runnable Thread object is indented to be run from a
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


class LaserLogic(GenericLogic):
    """ Logic module agreggating multiple hardware switches.
    """
    _modclass = 'laser'
    _modtype = 'logic'

    # waiting time between queries im milliseconds
    laser_conn = Connector(interface='SimpleLaserInterface')
    counter_logic = Connector(interface='CounterLogic')
    savelogic = Connector(interface='SaveLogic')
    fitlogic = Connector(interface='FitLogic')
    odmrlogic = Connector(interface='ODMRLogic')
    afm_scanner_logic = Connector(interface='AFMConfocalLogic')

    queryInterval = ConfigOption('query_interval', 100)

    #creating a fit container
    fc = StatusVar('fits', None)

    #For OOP measurement:
    final_power = StatusVar('final_power', 0.005)
    power_start = StatusVar('power_start', 0.001)
    power_stop = StatusVar('power_stop', 0.022)
    number_of_points = StatusVar('number_of_points', 15)
    time_per_point = StatusVar('time_per_points', 5)
    laser_power_start = StatusVar('laser_power_start', 0.001)
    laser_power_stop = StatusVar('laser_power_stop', 0.022)
    laser_power_num = StatusVar('laser_power_num', 5)
    mw_power_start = StatusVar('mw_power_start', 0)
    mw_power_stop = StatusVar('mw_power_stop', 29)
    mw_power_num = StatusVar('mw_power_num', 4)
    freq_start = StatusVar('freq_start', 2.8e9)
    freq_stop = StatusVar('freq_stop', 2.95e9)
    freq_num = StatusVar('freq_num', 100)
    counter_runtime = StatusVar('counter_runtime', 5)
    odmr_runtime = StatusVar('odmr_runtime', 10)
    channel = StatusVar('channel', 0)    
    optimize = StatusVar('optimize', False)
    odmr_fit_function = StatusVar('odmr_fit_function', 'No fit')
    bayopt_num_meas = StatusVar('bayopt_num_meas', 30)
    bayopt_alpha = StatusVar('bayopt_alpha', 0.15)
    bayopt_random_percentage = StatusVar('bayopt_random_percentage', 35)
    bayopt_xi = StatusVar('bayopt_xi', 0.1)

    sigRefresh = QtCore.Signal()
    sigLaserStateChanged = QtCore.Signal()
    sigControlModeChanged = QtCore.Signal()
    sigPowerSet = QtCore.Signal(float)
    sigSaturationStarted = QtCore.Signal()
    sigSaturationStopped = QtCore.Signal()
    # sigAbortedMeasurement = QtCore.Signal()
    sigSaturationFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict)
    sigDoubleFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict)
    sigSaturationParameterUpdated = QtCore.Signal()
    sigOOPStarted = QtCore.Signal()
    sigOOPStopped = QtCore.Signal()
    sigOOPUpdateData = QtCore.Signal()
    sigParameterUpdated = QtCore.Signal()
    sigDataAvailableUpdated = QtCore.Signal(list)
    sigBayoptStarted = QtCore.Signal()
    sigBayoptStopped = QtCore.Signal()
    sigBayoptUpdateData = QtCore.Signal(int)

    # make a dummy worker thread:
    _worker_thread = WorkerThread(print)


    def on_activate(self):
        """ Prepare logic module for work.
        """
        self._dev = self.laser_conn()
        self._counterlogic = self.counter_logic()
        self._save_logic = self.savelogic()
        self._odmr_logic = self.odmrlogic()
        self._stop_request = False
        self._OOP_stop_request = False
        self._bayopt_stop_request = False
        
        #start in cw mode
        if self._dev.get_control_mode() != ControlMode.POWER:
            self._dev.set_control_mode(ControlMode.POWER)
    
        # get laser capabilities
        self.mode = self._dev.get_control_mode()
        self.laser_state = self._dev.get_laser_state()
        self.laser_power_range = self._dev.get_power_range()
        self.laser_current_range = self._dev.get_current_range()
        self.laser_power_setpoint = self._dev.get_power_setpoint()
        self.laser_current_setpoint = self._dev.get_current_setpoint()
        self.laser_extra = self._dev.get_extra_info()
        self.laser_can_power = ControlMode.POWER in self._dev.allowed_control_modes()
        self.laser_can_current = ControlMode.CURRENT in self._dev.allowed_control_modes()
        self.laser_can_analog_mod = ControlMode.MODULATION_ANALOG in self._dev.allowed_control_modes()
        self.laser_can_digital_mod = ControlMode.MODULATION_DIGITAL in self._dev.allowed_control_modes()
        self.laser_control_mode = self._dev.get_control_mode()
        self.has_shutter = self._dev.get_shutter_state() != ShutterState.NOSHUTTER
        #Create data containers
        self._saturation_data = {}
        self._background_data = {}
        # TODO: rename _odmr_data 
        self._odmr_data = {}
        self._bayopt_data = {}
        self.is_background = False

        # in this threadpool our worker thread will be run
        self.threadpool = QtCore.QThreadPool()

        pass

    def on_deactivate(self):
        """ Deactivate module.
        """
        pass

    @fc.constructor
    def sv_set_fits(self, val):
        #Setup fit container
        fc = self.fitlogic().make_fit_container('saturation_curve', '1d')
        fc.set_units(['W', 'c/s'])
        if isinstance(val, dict) and len(val) > 0:
            fc.load_from_dict(val)
        else:
            d1 = {}
            d1['Hyperbolic_saturation'] = {'fit_function': 'hyperbolicsaturation', 'estimator': '2'}
            d2 = {}
            d2['1d'] = d1
            fc.load_from_dict(d2)            
        return fc

    @fc.representer
    def sv_get_fits(self, val):
        """ save configured fits """
        if len(val.fit_list) > 0:
            return val.save_to_dict()
        else:
            return None

    def on(self):
        """ Turn on laser. Does not open shutter if one is present.
        
        @return enum LaserState: actual laser state
        """
        self._dev.on()
        self.sigLaserStateChanged.emit()
        return self.get_laser_state()

    def off(self):
        """ Turn off laser. Does not close shutter if one is present.
        
        @return enum LaserState: actual laser state
        """
        self._dev.off()
        self.sigLaserStateChanged.emit()
        return self.get_laser_state()

    def get_power(self):
        """ Return laser power independent of the mode.

        @return float: Actual laser power in Watts (W).
        """
        
        return self._dev.get_power()

    def set_power(self, power):
        """ Set laser power in watts

        @param float power: laser power setpoint in watts

        @return float: laser power setpoint in watts
        """
        if self.get_control_mode() == ControlMode.CURRENT:
            self.set_control_mode(ControlMode.POWER)
            self.laser_power_setpoint = power
            self.laser_power_setpoint = self._dev.set_power(power) 
        
        if self.get_control_mode() == ControlMode.POWER:
            self.laser_power_setpoint = power
            self.laser_power_setpoint = self._dev.set_power(power)

        if self.get_control_mode() == ControlMode.MODULATION_DIGITAL:
            self.laser_power_setpoint = power
            self.laser_power_setpoint = self._dev.set_modulation_power(power)

        if self.get_control_mode() == ControlMode.MODULATION_ANALOG:
            self.laser_power_setpoint = power
            self.laser_power_setpoint = self._dev.set_modulation_power(power)

        self.sigPowerSet.emit(self.get_power())
        
        return self.get_power()

    def get_current(self):
        """ Return laser current

        @return float: actual laser current as ampere or percentage of maximum current
        """
        return self._dev.get_current()


    def set_current(self, current):
        """ Set laser current

        @param float current: Laser current setpoint in amperes

        @return float: Laser current setpoint in amperes
        """
        self.laser_current_setpoint = current
        self._dev.set_current(current)

        self.sigPowerSet.emit(self.get_current())

        return self.get_current()

    def set_control_mode(self,control_mode):
        """ Set laser control mode.
        
        @param enum control_mode: desired control mode
        
        @return enum ControlMode: actual control mode
        """
        self._dev.set_control_mode(control_mode)
        self.sigControlModeChanged.emit()

    def get_control_mode(self):
        """ Get control mode of laser

        @return enum ControlMode: control mode
        """

        return self._dev.get_control_mode()

    def get_laser_state(self):
        """ Get laser state.
        
        @return enum LaserState: laser state
        """

        return self._dev.get_laser_state()
    
    def set_saturation_params(self, power_start, power_stop, number_of_points,
                              time_per_point):
        lpr = self.laser_power_range
        if isinstance(power_start, (int, float)):
            self.power_start = units.in_range(power_start, lpr[0], lpr[1])
        if isinstance(power_stop, (int, float)):
            if power_stop < power_start:
                power_stop = power_start + 0.001
            self.power_stop =  units.in_range(power_stop, lpr[0], lpr[1])
        if isinstance(number_of_points, int):
            self.number_of_points = number_of_points
        if isinstance(time_per_point, (int, float)):
            self.time_per_point = time_per_point
        self.sigSaturationParameterUpdated.emit()
        return self.power_start, self.power_stop, self.number_of_points, self.time_per_point

    def get_saturation_parameters(self):
        params = {'power_start': self.power_start,
                  'power_stop': self.power_stop,
                  'number_of_points': self.number_of_points,
                  'time_per_point': self.time_per_point
        }       
        return params

    def get_saturation_data(self, is_background=False):
        """ Get recorded data.

        @return dict: contains an np.array with the measured or computed values for each data field
        (e.g. 'Fluorescence', 'Power') .
        """
        if is_background:
            data_copy = copy.deepcopy(self._background_data)
        else:
            data_copy = copy.deepcopy(self._saturation_data)
        return data_copy

    def set_saturation_data(self, xdata, ydata, std_dev=None, num_of_points=None, is_background=False):
        #TODO: Modify documentation
        """Set the data.

        @params np.array xdata: laser power values
        @params np.array ydata: fluorescence values
        @params np.array std_dev: optional, standard deviation values
        @params np.array num_of_points: optional, number of data points. The default value is len(xdata)
        """

        if num_of_points is None:
            num_of_points = len(xdata)
            
        #Setting up the list for data
        if is_background:
            data_dict = self._background_data
        else:
            data_dict = self._saturation_data

        data_dict['Power'] = np.zeros(num_of_points)
        data_dict['Fluorescence'] = np.zeros(num_of_points)
        data_dict['Stddev'] = np.zeros(num_of_points)

        for i in range(num_of_points):
            data_dict['Power'][i] = xdata[i]
            data_dict['Fluorescence'][i] = ydata[i]
            if std_dev is not None:
                data_dict['Stddev'][i] = std_dev[i]

        self.sigRefresh.emit()


    def saturation_curve_data(self, time_per_point, start_power, stop_power,
                            num_of_points, final_power, is_background=False):
        """ Obtain all necessary data to create a saturation curve

        @param int time_per_point: acquisition time of counts per each laser power in seconds.
        @param int start_power: starting power in Watts.
        @param int stop_power:  stoping power in Watts.
        @param int num_of_points: number of points for the measurement.
        
        @return enum ControlMode: control mode
        """

        #Setting up the stopping mechanism.
        self._stop_request = False
        self.sigSaturationStarted.emit()

        #Creating the list of powers for the measurement.
        power_calibration = np.zeros(num_of_points)
        laser_power = np.zeros(num_of_points)

        if num_of_points == 1:
            laser_power[0] = start_power
        else:
            step = (stop_power-start_power)/(num_of_points-1)
            for i in range(len(laser_power)):
                laser_power[i] = start_power+i*step

        #For later when you actually use the counter.
        count_frequency = self._counterlogic.get_count_frequency()
        counter_points = int(count_frequency*time_per_point)
        self._counterlogic.set_count_length(counter_points)

        if self.get_laser_state() == LaserState.OFF:

             # self.sigAbortedMeasurement.emit()
            self.log.warning('Measurement Aborted. Laser is not ON.')
            self.sigSaturationStopped.emit()
            return

        # time.sleep(time_per_point)
        counts = np.zeros(num_of_points)
        std_dev = np.zeros(num_of_points)

        self._counterlogic.startCount()

        for i in range(len(laser_power)):

            if self._stop_request:
                break

            #For later when you actually use the counter.
            self.set_power(laser_power[i])
            time.sleep(1)

            #For testing only.
            # time.sleep(1)
            # counts[i] = random.random()
            # std_dev[i] = random.random()

            #For later when you actually use the counter.
            # counts[i] = self._counterlogic.countdata[0].mean()
            # std_dev[i] = self._counterlogic.countdata[0].std(ddof=1)
            counts_array  = self._counterlogic.request_counts(counter_points)[0]
            counts[i] = counts_array.mean()
            std_dev[i] = counts_array.std(ddof=1)

            self.set_saturation_data(laser_power, counts, std_dev, i + 1, is_background)

        self._counterlogic.stopCount()

        self.set_power(final_power)

        self.sigSaturationStopped.emit()

        array_of_data = np.vstack((counts,laser_power,power_calibration)).transpose()

        return array_of_data

    def start_saturation_curve_data(self):
        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            self.sigSaturationStopped.emit()
            return

        self._worker_thread = WorkerThread(target=self.saturation_curve_data,
                                            args=(self.time_per_point,self.power_start,
                                                  self.power_stop, self.number_of_points,
                                                  self.final_power, self.is_background),
                                            name='saturation_curve_points') 

        self.threadpool.start(self._worker_thread)

    def stop_saturation_curve_data(self):
        """ Set a flag to request stopping counting.
        """
        if self._counterlogic.module_state() == 'locked':
            self._stop_request = True
        else:
            self._stop_request = True

        return

    def save_saturation_data(self, tag=None):
        """ Save the current Saturation data to a file, including the figure."""
        timestamp = datetime.datetime.now()

        if tag is None:
            tag = ''
        
        #Path and label to save the Saturation data
        filepath = self._save_logic.get_path_for_module(module_name='Saturation')

        if len(tag) > 0:
                filelabel = '{0}_Saturation_data'.format(tag)
        else:
                filelabel = 'Saturation_data'

        #The data is already prepared in a dict so just calling the data.
        data = self._saturation_data

        if data == OrderedDict():
            self.log.warning('Sorry, there is no data to save. Start a measurement first.')
            return

        # Include fit parameters if a fit has been calculated
        parameters = OrderedDict()
        if hasattr(self, 'result_str_dict'):
            parameters = self.result_str_dict

        #Drawing the figure
        fig = self.draw_figure()

        self._save_logic.save_data(data,
                                       filepath=filepath,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp,
                                       plotfig=fig)
        
        if hasattr(self, 'saturation_fit_x'):
            data_fit = {'Power': self.saturation_fit_x, 
                        'Fluorescence fit': self.saturation_fit_y}
            filelabel_fit = filelabel + '_fit'
            self._save_logic.save_data(data_fit,
                                       filepath=filepath,
                                       parameters=parameters,
                                       filelabel=filelabel_fit,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp)


        self.log.info('Saturation data saved to:\n{0}'.format(filepath))

        return

    def draw_figure(self):
        """ Draw the summary figure to save with the data.

        @return fig fig: a matplotlib figure object to be saved to file.
        """     
    
        counts = self._saturation_data['Fluorescence']
        stddev = self._saturation_data['Stddev']
        laser_power = self._saturation_data['Power']
        #For now there is no power calibration, this should change in the future.
        power_calibration = self._saturation_data['Power']

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig = plt.figure()
        plt.errorbar(power_calibration,counts,yerr=stddev)

        # Do not include fit curve if there is no fit calculated.
        if hasattr(self, 'saturation_fit_x'):
            plt.plot(self.saturation_fit_x, self.saturation_fit_y, marker='None')

        #Set the labels
        plt.ylabel('Fluorescence (cts/s)')
        plt.xlabel('Laser Power (uW)')

        return fig

    def check_thread_active(self):
        """ Check whether current worker thread is running. """

        if hasattr(self, '_worker_thread'):
            if self._worker_thread.is_running():
                return True
        return False

    def do_fit(self, x_data=None, y_data=None):
        """
        Execute the fit (configured in the fc object) on the measurement data. Optionally on passed 
        data.

        @params np.array x_data: optional, laser power values. By default, values stored in self._saturation_data.
        @params np.array y_data: optional, fluorescence values. By default, values stored in self._saturation_data.

        Create 3 class attributes
            np.array self.saturation_fit_x: 1D arrays containing the x values of the fitting function
            np.array self.saturation_fit_y: 1D arrays containing the y values of the fitting function
            lmfit.model.ModelResult self.fit_result: the result object of lmfit. If additional information
                                        is needed from the fit, then they can be obtained from this 
                                        object. 
        """
        self.fc.current_fit = 'Hyperbolic_saturation'

        if (x_data is None) or (y_data is None):
            if 'Power' in self._saturation_data:
                x_data = self._saturation_data['Power']
                y_data = self._saturation_data['Fluorescence']
            else:
                self.log.warning('There is no data points. Fitting aborted.')
                return
        
        if len(x_data) < 3:
            self.log.warning('There is not enough data points to fit the curve. Fitting aborted.')
            return

        self.saturation_fit_x, self.saturation_fit_y, self.fit_result = self.fc.do_fit(x_data, y_data)
        if self.fit_result is None:
            self.result_str_dict = {}
        else:
            self.result_str_dict = self.fit_result.result_str_dict
        self.sigSaturationFitUpdated.emit(self.saturation_fit_x, self.saturation_fit_y, self.result_str_dict)
        return
    
    def do_double_fit(self, x_saturation=None, y_saturation=None, 
                               x_background=None, y_background=None):

        """
        Execute the double fit (with the background) on the measurement data. Optionally on passed 
        data.

        @params np.array x_saturation: optional, laser power values for the saturation measurement (on the NV center). 
                                       By default, values stored in self._saturation_data.
        @params np.array y_saturation: optional, fluorescence values for the saturation measurement (on the NV center). 
                                       By default, values stored in self._saturation_data.
        @params np.array x_background: optional, laser power values for the background measurement. 
                                       By default, values stored in self._background_data.
        @params np.array y_background: optional, fluorescence values for the background measurement. 
                                       By default, values stored in self._background_data.
        @return (np.array, np.array, lmfit.model.ModelResult): 
            2D array containing the x values of the fitting functions: the first row correspond to 
                the NV saturation curve and the second row to the background curve.
            2D array containing the y values of the fitting functions: the first row correspond to 
                the NV saturation curve and the second row to the background curve.
            result object of lmfit. If additional information is needed from the fit, then they can be obtained from this 
                                        object. 
        """

        if x_saturation is None or y_saturation is None or \
           x_background is None or y_background is None:

            if 'Power' in self._saturation_data and 'Power' in self._background_data:
                x_saturation = self._saturation_data['Power']
                y_saturation = self._saturation_data['Fluorescence']
                x_background = self._background_data['Power']
                y_background = self._background_data['Fluorescence']
            else:
                self.log.warning('You must record saturation curves on the NV center \
                and on the background to do this fit')
                return
            
        if len(x_saturation) < 3 or len(x_background) < 2:
            self.log.warning('There is not enough data points to fit the curve. Fitting aborted.')
            return

        x_axis = []
        x_axis.append(x_saturation)
        x_axis.append(x_background)
        x_axis = np.array(x_axis)

        data = []
        data.append(y_saturation)
        data.append(y_background)
        data = np.array(data)

        fit_x, fit_y, result = self.fitlogic().make_hyperbolicsaturation_fit_with_background(x_axis, data, 
                        self.fitlogic().estimate_hyperbolicsaturation_with_background, units=['W', 'c/s'])
        self.sigDoubleFitUpdated.emit(fit_x, fit_y, result.result_str_dict)
        return fit_x, fit_y, result
        

    ###########################################################################
    #              Optimal operation point measurement methods                #
    ###########################################################################

    def get_odmr_channels(self):
        return self._odmr_logic.get_odmr_channels()

    def perform_measurement(self, stabilization_time=1, **kwargs):

        for param, value in kwargs.items():
            try:
                func = getattr(self, 'set_' + param)
            except AttributeError:
                self.log.error("perform_measurement has no argument" + param)
            func(value)

        #Setting up the stopping mechanism.
        self._OOP_stop_request = False
        self.sigOOPStarted.emit()
       
        self.set_saturation_params(self.laser_power_start, self.laser_power_stop, self.laser_power_num, self.counter_runtime)
        # Create the lists of powers for the measurement
        laser_power = np.linspace(self.laser_power_start, self.laser_power_stop, self.laser_power_num, endpoint=True)
        mw_power = np.linspace(self.mw_power_start, self.mw_power_stop, self.mw_power_num, endpoint=True)

        #TODO: Check if we need to turn laser on (or should it be done manually ?)
        if self.get_laser_state() == LaserState.OFF:
            self.log.warning('Measurement Aborted. Laser is not ON.')
            self.sigOOPStopped.emit()
            return

        if self._counterlogic.module_state() == 'locked':
            self.log.warning('Another measurement is running, stop it first!')
            self.sigOOPStopped.emit()
            return

        count_frequency = self._counterlogic.get_count_frequency()
        counter_num_of_points = int(count_frequency * self.counter_runtime)
        freq_step = (self.freq_stop - self.freq_start) / (self.freq_num - 1)

        self._odmr_data = self.initialize_odmr_data()

        for i in range(len(laser_power)):

            #Stopping mechanism
            if self._OOP_stop_request:
                break

            self.set_power(laser_power[i])

            time.sleep(stabilization_time)
            
            # Optimize the position
            if self.optimize:
                self.afm_scanner_logic().default_optimize()

            time.sleep(stabilization_time)

            counts_array  = self._counterlogic.request_counts(counter_num_of_points)[self.channel]

            #To avoid crash
            time.sleep(stabilization_time)

            counts = counts_array.mean()
            std_dev = counts_array.std(ddof=1)

            self._odmr_data['saturation_data'][i] = counts
            self._odmr_data['saturation_data_std'][i] = std_dev          

            self.set_saturation_data(laser_power, self._odmr_data['saturation_data'], self._odmr_data['saturation_data_std'], i + 1)          

            for j in range(len(mw_power)):

                #Stopping mechanism
                if self._OOP_stop_request:
                    break

                if self.optimize:
                    self.afm_scanner_logic().default_optimize()
            
                error, odmr_plot_x, odmr_plot_y, odmr_fit_result = self._odmr_logic.perform_odmr_measurement(
                                     self.freq_start, freq_step, self.freq_stop, mw_power[j], self.channel, self.odmr_runtime,
                                     self.odmr_fit_function, save_after_meas=False, name_tag='')

                if error:
                    self.log.warning('Optimal operation point measurement aborted')
                    self.sigOOPStopped.emit()
                    return

                odmr_plot_y  = odmr_plot_y[self.channel, :]

                self._odmr_data['data'][i][j] = odmr_plot_y
                self._odmr_data['fit_results'][i][j] = odmr_fit_result
                self.update_fit_params(i, j)                
                self.sigOOPUpdateData.emit()

        #TODO: do we need a final power ? Or should we turn the laser off ?
        #FIXME: replace laser_power_start by final power
        self.off()

        self.sigOOPStopped.emit()

        return self._odmr_data
        
    def initialize_odmr_data(self):

        meas_dict = {'data': np.zeros((self.laser_power_num, self.mw_power_num, self.freq_num)),
                     # FIXME: get the odmr data std
                     # 'data_std': np.zeros((self.laser_power_num, self.mw_power_num, self.freq_num)),
                     #TODO : replace np array by list
                     'saturation_data': np.zeros(self.laser_power_num),
                     'saturation_data_std': np.zeros(self.laser_power_num),
                     # 'background_data': np.zeros(self.laser_power_num),
                     # 'background_data_std': np.zeros(self.laser_power_num),
                     'fit_results': np.zeros((self.laser_power_num, self.mw_power_num), dtype = lmfit.model.ModelResult),
                     'fit_params': {},
                     'coord0_arr': np.linspace(self.laser_power_start, self.laser_power_stop, self.laser_power_num, endpoint=True),
                     'coord1_arr': np.linspace(self.mw_power_start, self.mw_power_stop, self.mw_power_num, endpoint=True),
                     'coord2_arr': np.linspace(self.freq_start, self.freq_stop, self.freq_num, endpoint=True),
                     'units': 'c/s',
                     'nice_name': 'Fluorescence',
                     'params': {'Parameters for': 'Optimize operating point measurement',
                                'axis name for coord0': 'Laser power',
                                'axis name for coord1': 'Microwave power',
                                'axis name for coord2': 'Microwave frequency',
                                'coord0_start (W)': self.laser_power_start,
                                'coord0_stop (W)': self.laser_power_stop,
                                'coord0_num (#)': self.laser_power_num,
                                'coord1_start (dBm)': self.mw_power_start,
                                'coord1_stop (dBm)': self.mw_power_stop,
                                'coord1_num (#)': self.mw_power_num,
                                'coord2_start (Hz)': self.freq_start,
                                'coord2_stop (Hz)': self.freq_stop,
                                'coord2_num (#)': self.freq_num,
                                'ODMR runtime (s)': self.odmr_runtime,
                                'Counter runtime (s)': self.counter_runtime,
                                'Fit function': self.odmr_fit_function,
                                'Channel': self.channel,
                                },  # !!! here are all the measurement parameter saved
                    }  

        self._odmr_data = meas_dict

        return self._odmr_data

    def update_fit_params(self, i, j):
        if self.odmr_fit_function != 'No fit':
            if not hasattr(self._odmr_data['fit_results'][0][0], 'result_str_dict'):
                self.log.warning("The selected fit does not allow to access the fit parameters. Please chose another fit.")
                return

            param_dict = self._odmr_data['fit_results'][i][j].result_str_dict
            if (i, j) == (0, 0):
                for param_name in param_dict.keys():
                    if not 'slope' in param_name :
                        self._odmr_data['fit_params'][param_name] = {}
                        self._odmr_data['fit_params'][param_name]['values'] = np.zeros((self.laser_power_num, self.mw_power_num))
                        if 'error' in param_dict[param_name]:
                            self._odmr_data['fit_params'][param_name]['errors'] = np.zeros((self.laser_power_num, self.mw_power_num))
                        self._odmr_data['fit_params'][param_name]['unit'] = param_dict[param_name]['unit']
                self.sigDataAvailableUpdated.emit(list(self._odmr_data['fit_params'].keys()))
                #self.sigDataAvailableUpdated.emit(list(param_dict.keys()))
            for param_name in param_dict:
                if not 'slope' in param_name:
                    self._odmr_data['fit_params'][param_name]['values'][i][j] = param_dict[param_name]['value']
                    if 'error' in param_dict[param_name]:
                        self._odmr_data['fit_params'][param_name]['errors'][i][j] = param_dict[param_name]['error']

    def save_scan_data(self, nametag):
        
        data = self._odmr_data

        # check whether data has only zeros, skip this then
        if not 'data' in data or not np.any(data['data']):
            self.log.warning('The data array contains only zeros and will be not saved.')
            return

        # Save saturation data
        self.do_fit()
        self.save_saturation_data(nametag)

        timestamp = datetime.datetime.now()

        if nametag is None:
            nametag = ''
        
        #Path and label to save the Saturation data
        filepath = self._save_logic.get_path_for_module(module_name='Optimal operating point')

        if len(nametag) > 0:
                filelabel = '{0}_ODMR_data'.format(nametag)
        else:
                filelabel = 'ODMR_data'


        parameters = {}
        parameters.update(data['params'])
        nice_name = data['nice_name']
        unit = data['units']

        parameters['Name of measured signal'] = nice_name
        parameters['Units of measured signal'] = unit

        figure_data = data['data']


        rows, columns, entries = figure_data.shape

        image_data = {}
        # reshape the image before sending out to save logic.
        image_data[f'ESR scan measurements with {nice_name} signal without axis.\n'
                    'The save data contain directly the fluorescence\n'
                   f'signals of the esr spectrum in {unit}. Each i-th spectrum\n'
                    'was taken with laser and microwave power (laser_power_i,\n' 
                    'mw_power_j), where the top most data correspond to\n'
                    '(laser_power_start, mw_power_start). For the next spectrum\n'
                    'the microwave power will be incremented until it reaches \n'
                    'mw_power_stop. Then the laser power is incremented and the\n'
                    'microwave power starts again from mw_power_start.'] = figure_data.reshape(rows*columns, entries)

        self._save_logic.save_data(image_data, parameters=parameters,
                                       filepath=filepath,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp)

        laser_power_column = np.zeros(rows * columns * entries)
        mw_power_column = np.zeros(rows * columns * entries)
        freq_column = np.zeros(rows * columns * entries)
        fluorescence_column = np.zeros(rows * columns * entries)

        ind = 0
        for i in range(rows):
            for j in range(columns):
                for k in range(entries):
                    rows + j * columns + k * entries
                    laser_power_column[ind] = data['coord0_arr'][i]
                    mw_power_column[ind] = data['coord1_arr'][j]
                    freq_column[ind] = data['coord2_arr'][k]
                    fluorescence_column[ind] = figure_data[i][j][k]
                    ind += 1
                    

        image_data_2 = {'Laser power': laser_power_column,
                        'Microwave power': mw_power_column,
                        'Frequency': freq_column,
                        'Fluorescence': fluorescence_column}

        filelabel_2 = filelabel + '_2'

        self._save_logic.save_data(image_data_2, parameters=parameters,
                                       filepath=filepath,
                                       filelabel=filelabel_2,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp)

        # Save fit result if they are computed
        if self._odmr_data['fit_results'].any():
            for param_name in self._odmr_data['fit_params']:
                data_matrix, unit = self.get_data(param_name)
                data_dict = {param_name + ' (' + unit + ')': data_matrix}
                data_filelabel = filelabel + '_' + param_name
                fig = self.draw_matrix_figure(param_name)
                self._save_logic.save_data(data_dict, parameters=parameters,
                                        filepath=filepath,
                                        filelabel=data_filelabel,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        timestamp=timestamp,
                                        plotfig=fig)
                if 'errors' in self._odmr_data['fit_params'][param_name]:
                    std_matrix = self._odmr_data['fit_params'][param_name]['errors']                       
                    std_dict = {param_name + ' Error (' + unit + ')': std_matrix}
                    std_filelabel = filelabel + '_' + param_name + '_stddev'
                    self._save_logic.save_data(std_dict, parameters=parameters,
                                            filepath=filepath,
                                            filelabel=std_filelabel,
                                            fmt='%.6e',
                                            delimiter='\t',
                                            timestamp=timestamp)

        self.log.info('ODMR data saved to:\n{0}'.format(filepath))

        return

    def draw_matrix_figure(self, data_name):
        if data_name  not in self._odmr_data['fit_params']:
            fig = None
            return fig
        
        matrix, unit = self.get_data(data_name)
        scale_fact = units.ScaledFloat(np.max(matrix)).scale_val
        unit_prefix = units.ScaledFloat(np.max(matrix)).scale
        matrix_scaled = matrix / scale_fact
        matrix_scaled_nonzero = matrix_scaled[np.nonzero(matrix_scaled)]
        cb_min = np.percentile(matrix_scaled_nonzero, 5)
        cb_max = np.percentile(matrix_scaled_nonzero, 95)
        cbar_range = [cb_min, cb_max]
        unit_scaled = unit_prefix + unit

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        #fig = plt.figure()
        fig, (ax_matrix) = plt.subplots(nrows=1, ncols=1)
        matrixplot = ax_matrix.imshow(matrix_scaled,
                                cmap=plt.get_cmap('viridis'),  # reference the right place in qd
                                origin='lower',
                                vmin=cbar_range[0],
                                vmax=cbar_range[1],
                                extent=[self.mw_power_start,
                                    self.mw_power_stop,
                                    self.laser_power_start,
                                    self.laser_power_stop
                                    ],
                                aspect='auto',
                                interpolation='nearest')

        ax_matrix.set_xlabel('MW power (dBm)')
        ax_matrix.set_ylabel('Laser power (W)')

        # Adjust subplot to make room for colorbar
        fig.subplots_adjust(right=0.8)

        # Add colorbar axis to figure
        cbar_ax = fig.add_axes([0.85, 0.15, 0.02, 0.7])

        # Draw colorbar
        cbar = fig.colorbar(matrixplot, cax=cbar_ax)
        cbar.set_label(data_name + ' (' + unit_scaled + ')')

        return fig

    ##########################
    #  Start/stop functions  #
    ##########################

    def start_OOP_measurement(self):

        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.perform_measurement,
                                            args=(),
                                            name='operation_point_measurement') 

        self.threadpool.start(self._worker_thread)

    def stop_OOP_measurement(self):
        self._OOP_stop_request = True

    ########################
    #       Getters        #
    ########################

    def get_odmr_constraints(self):
        return self._odmr_logic.get_hw_constraints()

    def get_OOP_parameters(self):
        params = {'laser_power_start': self.laser_power_start,
                  'laser_power_stop': self.laser_power_stop,
                  'laser_power_num': self.laser_power_num,
                  'mw_power_start': self.mw_power_start,
                  'mw_power_stop': self.mw_power_stop,
                  'mw_power_num': self.mw_power_num,
                  'freq_start': self.freq_start,
                  'freq_stop': self.freq_stop, 
                  'freq_num': self.freq_num,
                  'counter_runtime': self.counter_runtime,
                  'odmr_runtime': self.odmr_runtime,
                  'channel': self.channel,
                  'optimize': self.optimize,
                  'odmr_fit_function': self.odmr_fit_function,
                  'bayopt_num_meas': self.bayopt_num_meas}
        return params

    def get_odmr_fits(self):
        fit_list = self._odmr_logic.fc.fit_list.keys()
        return fit_list

    def get_data(self, data_name):
        if data_name in self._odmr_data['fit_params']:
            param_dict = self._odmr_data['fit_params'][data_name]
            return param_dict['values'], param_dict['unit']
        else:
            self.log.warning("This data is not available from the fit, sorry!")
            return np.array([[0]]), ''

    ########################
    #       Setters        #
    ########################

    #TODO: check if the module is locked or not before changing the params

    def set_laser_power_start(self, laser_power_start):
        lpr = self.laser_power_range
        if isinstance(laser_power_start, (int, float)):
            self.laser_power_start = units.in_range(laser_power_start, lpr[0], lpr[1])
        self.sigParameterUpdated.emit()
        return self.laser_power_start


    def set_laser_power_stop(self, laser_power_stop):
        #FIXME: Prevent laser_power_stop being equal to laser_power_start:
        # that causes a bug.
        lpr = self.laser_power_range
        if isinstance(laser_power_stop, (int, float)):
            if laser_power_stop < self.laser_power_start:
                laser_power_stop = self.laser_power_start
            self.laser_power_stop =  units.in_range(laser_power_stop, lpr[0], lpr[1])
            self.sigParameterUpdated.emit()
            return self.laser_power_stop

    def set_laser_power_num(self, laser_power_num):
        if isinstance(laser_power_num, int):
            self.laser_power_num = laser_power_num
        self.sigParameterUpdated.emit()
        return self.laser_power_num

    def set_mw_power_start(self, mw_power_start):
        limits = self.get_odmr_constraints()
        if isinstance(mw_power_start, (int, float)):
            self.mw_power_start = limits.power_in_range(mw_power_start)
        self.sigParameterUpdated.emit()
        return self.mw_power_start
    
    def set_mw_power_stop(self, mw_power_stop):
        limits = self.get_odmr_constraints()
        if isinstance(mw_power_stop, (int, float)):
            if mw_power_stop < self.mw_power_start:
                mw_power_stop = self.mw_power_start
            self.mw_power_stop =  limits.power_in_range(mw_power_stop)
        self.sigParameterUpdated.emit()
        return self.mw_power_stop

    def set_mw_power_num(self, mw_power_num):
        if isinstance(mw_power_num, int):
            self.mw_power_num = mw_power_num
        self.sigParameterUpdated.emit()
        return self.mw_power_num

    def set_freq_start(self, freq_start):
        limits = self.get_odmr_constraints()
        if isinstance(freq_start, (int, float)):
            self.freq_start = limits.frequency_in_range(freq_start)
        self.sigParameterUpdated.emit()
        return self.freq_start

    def set_freq_stop(self, freq_stop):
        limits = self.get_odmr_constraints()
        if isinstance(freq_stop, (int, float)):
            if freq_stop < self.freq_start:
                freq_stop = self.freq_start
            self.freq_stop =  limits.frequency_in_range(freq_stop)
        self.sigParameterUpdated.emit()
        return self.freq_stop

    def set_freq_num(self, freq_num):
        if isinstance(freq_num, int):
            self.freq_num = freq_num
        self.sigParameterUpdated.emit()
        return self.freq_num

    def set_counter_runtime(self, counter_runtime):
        if isinstance(counter_runtime, (int, float)):
            self.counter_runtime = counter_runtime
        self.sigParameterUpdated.emit()
        return self.counter_runtime

    def set_odmr_runtime(self, odmr_runtime):
        if isinstance(odmr_runtime, (int, float)):
            self.odmr_runtime = odmr_runtime
        self.sigParameterUpdated.emit()
        return self.odmr_runtime

    #FIXME: check whether the channel exists or not
    def set_OOP_channel(self, channel):
        odmr_channels = self.get_odmr_channels()
        num = len(odmr_channels)
        if isinstance(channel, int) and channel < num:
            self.channel = channel
            self.sigParameterUpdated.emit()
        else:
            self.log.error('Channel must be an int inferior or equal to {0:d}'.format(num - 1))
        return self.channel

    def set_OOP_optimize(self, boolean):
        self.optimize = boolean
        self.sigParameterUpdated.emit()
        return self.optimize 

    def set_odmr_fit(self, fit_name):
        if fit_name in self.get_odmr_fits():
            self.odmr_fit_function = fit_name
        self.sigParameterUpdated.emit()
        return self.odmr_fit_function

    def set_bayopt_num_meas(self, num_meas):
        self.bayopt_num_meas = num_meas
        self.sigParameterUpdated.emit()
        return self.bayopt_num_meas

    ###########################################################################
    #              Bayesian optimization methods                              #
    ###########################################################################
        
    def initialize_optimizer(self):
        pbounds = {'x': (0, 1), 'y': (0, 1)}
        self.optimizer = BayesianOptimization(
            f=None,
            pbounds=pbounds,
            verbose=0
        ) 
        self.optimizer.set_gp_params(alpha=self.bayopt_alpha)

        return self.optimizer

    def measure_sensitivity(self, laser_power, mw_power):
        self.set_power(laser_power)
        time.sleep(1)

        freq_step = (self.freq_stop - self.freq_start) / (self.freq_num - 1)

        error, odmr_plot_x, odmr_plot_y, odmr_fit_result = self._odmr_logic.perform_odmr_measurement(
                                    self.freq_start, freq_step, self.freq_stop, mw_power, self.channel, self.odmr_runtime,
                                    self.odmr_fit_function, save_after_meas=False, name_tag='')

        if error:
            self.log.warning('Error occured during ODMR measurement.')
            return error, 0, np.array([]), np.array([])

        if 'Sensitivity' in odmr_fit_result.result_str_dict:
            val = odmr_fit_result.result_str_dict['Sensitivity']['value']
            if 'error' in odmr_fit_result.result_str_dict['Sensitivity']:
                std = odmr_fit_result.result_str_dict['Sensitivity']['error']
            else:
                std = -1
        elif 'Sensitivity 0' in odmr_fit_result.result_str_dict:
            val = odmr_fit_result.result_str_dict['Sensitivity 0']['value']
            if 'error' in odmr_fit_result.result_str_dict['Sensitivity 0']:
                std = odmr_fit_result.result_str_dict['Sensitivity 0']['error']
            else:
                std = -1
        else:
            self.log.warning("Sensitivity is not available from the fit chosen. Please choose another fit (e.g. Lorentzian dip)")
            error = -1
            return error, 0, np.array([]), np.array([])

        return error, val, std, odmr_plot_x, odmr_plot_y

    def bayesian_optimization(self, resume=False):

        #Setting up the stopping mechanism.
        self._bayopt_stop_request = False
        self.sigBayoptStarted.emit()

        if self.get_laser_state() == LaserState.OFF:
            self.log.warning('Measurement Aborted. Laser is not ON.')
            self.sigBayoptStopped.emit()
            return

        if self._counterlogic.module_state() == 'locked':
            self.log.warning('Another measurement is running, stop it first!')
            self.sigBayoptStopped.emit()
            return

        self.initialize_optimizer()
        self.initialize_bayopt_data(resume)

    
        old_num_points = np.count_nonzero(self._bayopt_data['measured_sensitivity'])
        for n in range(old_num_points):
            target = self._bayopt_data['measured_sensitivity'][n] * -1e5
            x = (self._bayopt_data['laser_power_list'][n] - self.laser_power_start) / (self.laser_power_stop - self.laser_power_start)
            y = (self._bayopt_data['mw_power_list'][n] - self.mw_power_start) / (self.mw_power_stop - self.mw_power_start)
            self.optimizer.register(params={'x': x, 'y': y}, target=target)
        
        utility = UtilityFunction(kind='ei', xi=self.bayopt_xi, kappa=1)

        init_points = int((self.bayopt_num_meas - old_num_points) * self.bayopt_random_percentage / 100)

        for n in range(old_num_points, self.bayopt_num_meas):

            #Stopping mechanism
            if self._bayopt_stop_request:
                break

            if n < old_num_points + init_points :
                x = np.random.random()
                y = np.random.random()
            else:
                try:
                    next_point = self.optimizer.suggest(utility)
                    x = next_point['x']
                    y = next_point['y']
                except ValueError:
                    x = np.random.random()
                    y = np.random.random()

            las_pw = self.laser_power_start + (self.laser_power_stop - self.laser_power_start) * x
            mw_pw = self.mw_power_start + (self.mw_power_stop - self.mw_power_start) * y
            
            error, value, std, odmr_plot_x, odmr_plot_y = self.measure_sensitivity(las_pw, mw_pw)
            if error:
                self.log.warning("Optimal operation search aborted")
                self.sigBayoptStopped.emit()
                return

            target = value * -1e5
            self.optimizer.register(params={'x': x, 'y': y}, target=target)
            try:
                self.optimizer._gp.fit(self.optimizer._space.params, self.optimizer._space.target)
            except ValueError:
                pass
            self._bayopt_data['measured_sensitivity'][n] = value
            self._bayopt_data['measured_sensitivity_std'][n] = std
            self._bayopt_data['laser_power_list'][n] = las_pw
            self._bayopt_data['mw_power_list'][n] = mw_pw
            self._bayopt_data['odmr_data'][n] = np.array([odmr_plot_x, odmr_plot_y[self.channel]])
            X = np.linspace(0, 1, 100)
            Y = np.linspace(0, 1, 100)
            try: 
                for i in range(100):
                    for j in range(100):
                        self._bayopt_data['predicted_sensitivity'][i][j] = float(self.optimizer._gp.predict([[X[i], Y[j]]])) * -1e-5
            except AttributeError:
                pass
            self.sigBayoptUpdateData.emit(n)

        self.sigBayoptStopped.emit()
        return

    def stop_bayopt(self):
        self._bayopt_stop_request = True

    def start_bayopt(self):
        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.bayesian_optimization,
                                            args=(),
                                            name='bayopt') 

        self.threadpool.start(self._worker_thread)
    
    def resume_bayopt(self):
        
        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return
            
        self._worker_thread = WorkerThread(target=self.bayesian_optimization,
                                            kwargs={'resume': True},
                                            name='bayopt') 

        self.threadpool.start(self._worker_thread)

    def initialize_bayopt_data(self, resume=False):
        
        old_num_points = 0
        if resume:
            old_dict = self._bayopt_data
            old_num_points = np.count_nonzero(old_dict['measured_sensitivity'])
            if self.bayopt_num_meas <= old_num_points:
                self.set_bayopt_num_meas(old_num_points + 1)

        meas_dict = {'measured_sensitivity': np.zeros(self.bayopt_num_meas),
                     'measured_sensitivity_std': np.zeros(self.bayopt_num_meas),
                     'laser_power_list': np.zeros(self.bayopt_num_meas),
                     'mw_power_list': np.zeros(self.bayopt_num_meas),
                     'odmr_data': np.zeros((self.bayopt_num_meas, 2, self.freq_num)),
                     'predicted_sensitivity': np.zeros((100, 100)),
                     'coord0_arr': np.linspace(self.laser_power_start, self.laser_power_stop, 100, endpoint=False),
                     'coord1_arr': np.linspace(self.mw_power_start, self.mw_power_stop, 100, endpoint=False),
                     'units': 'T/sqrt(Hz)',
                     'nice_name': 'Sensitivity',
                     'params': {'Parameters for': 'Optimize operating point search',
                                'laser_power_min (W)': self.laser_power_start,
                                'laser_power_max (W)': self.laser_power_stop,
                                'mw_power_min (dBm)': self.mw_power_start,
                                'mw_power_max (dBm)': self.mw_power_stop,
                                'freq_start (Hz)': self.freq_start,
                                'freq_stop (Hz)': self.freq_stop,
                                'freq_num (#)': self.freq_num,
                                'Number of points (#)': self.bayopt_num_meas,
                                'ODMR runtime (s)': self.odmr_runtime,
                                'Fit function': self.odmr_fit_function,
                                'Channel': self.channel,
                                },  # !!! here are all the measurement parameter saved
                    }

        for n in range(old_num_points):
            meas_dict['measured_sensitivity'][n] = old_dict['measured_sensitivity'][n]
            meas_dict['measured_sensitivity_std'][n] = old_dict['measured_sensitivity_std'][n]
            meas_dict['laser_power_list'][n] = old_dict['laser_power_list'][n]
            meas_dict['mw_power_list'][n] = old_dict['mw_power_list'][n]
            # FIXME: If the number of points for the odmr measurement changes, they can not be 
            # stored in the data array.
            if meas_dict['odmr_data'][n].shape == old_dict['odmr_data'][n]:
                meas_dict['odmr_data'][n] = old_dict['odmr_data'][n]

        self._bayopt_data = meas_dict
        return self._bayopt_data
    
    def get_bayopt_data(self):
        return self._bayopt_data

    def save_bayopt_data(self, tag=None):

        timestamp = datetime.datetime.now()

        if tag is None:
            tag = ''
        
        #Path and label to save the Saturation data
        filepath = self._save_logic.get_path_for_module(module_name='Sensitivity optimization')

        if len(tag) > 0:
                filelabel = '{0}_measures'.format(tag)
        else:
                filelabel = 'measures'

        
        if not 'measured_sensitivity' in self._bayopt_data or not np.any(self._bayopt_data['measured_sensitivity']):
            self.log.warning('The data array is empty and will be not saved.')
            return

        parameters = {}
        parameters.update(self._bayopt_data['params'])
        nice_name = self._bayopt_data['nice_name']
        unit = self._bayopt_data['units']
        parameters['Name of measured signal'] = nice_name
        parameters['Units of measured signal'] = unit

        data = {}
        data['Laser_power (W)'] = self._bayopt_data['laser_power_list']
        data['MW power (dBm)'] = self._bayopt_data['mw_power_list']
        data['Sensitivity (T/sqrt(Hz))'] = self._bayopt_data['measured_sensitivity']
        data['Stddev (T/sqrt(Hz))'] = self._bayopt_data['measured_sensitivity_std']

        fig = self.draw_optimization_figure()
        self._save_logic.save_data(data, parameters=parameters,
                                       filepath=filepath,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp,
                                       plotfig=fig)

        self.log.info('Optimization data saved to:\n{0}'.format(filepath))

        return

    def draw_optimization_figure(self):
        
        matrix = self._bayopt_data['predicted_sensitivity']
        unit = 'T/sqrt(Hz)'
        scale_fact = units.ScaledFloat(np.max(matrix)).scale_val
        unit_prefix = units.ScaledFloat(np.max(matrix)).scale
        matrix_scaled = matrix / scale_fact
        cbar_range = np.array([np.min(matrix_scaled), np.max(matrix_scaled)])
        unit_scaled = unit_prefix + unit

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, (ax_matrix) = plt.subplots(nrows=1, ncols=1)

        ax_matrix.set_xlim(self.mw_power_start, self.mw_power_stop)
        ax_matrix.set_ylim(self.laser_power_start, self.laser_power_stop)

        matrixplot = ax_matrix.imshow(matrix_scaled,
                                cmap=plt.get_cmap('viridis'),  # reference the right place in qd
                                origin='lower',
                                vmin=cbar_range[0],
                                vmax=cbar_range[1],
                                extent=[self.mw_power_start,
                                    self.mw_power_stop,
                                    self.laser_power_start,
                                    self.laser_power_stop
                                    ],
                                aspect='auto',
                                interpolation='nearest')

        n = np.count_nonzero(self._bayopt_data['measured_sensitivity'])
        ax_matrix.plot(self._bayopt_data['mw_power_list'][:n], self._bayopt_data['laser_power_list'][:n], linestyle='', marker='o', color='cyan')

        index_min = np.argmin(self._bayopt_data['measured_sensitivity'][:n])
        min_mw_power = self._bayopt_data['mw_power_list'][index_min]
        min_laser_power = self._bayopt_data['laser_power_list'][index_min]
        ax_matrix.axvline(x=min_mw_power, color='darkorange', linewidth=1)
        ax_matrix.axhline(y=min_laser_power, color='darkorange', linewidth=1)

        ax_matrix.set_xlabel('MW power (dBm)')
        ax_matrix.set_ylabel('Laser power (W)')

        # Adjust subplot to make room for colorbar
        fig.subplots_adjust(right=0.8)

        # Add colorbar axis to figure
        cbar_ax = fig.add_axes([0.85, 0.15, 0.02, 0.7])

        # Draw colorbar
        cbar = fig.colorbar(matrixplot, cax=cbar_ax)
        cbar.set_label('Sensitivity (' + unit_scaled + ')')

        return fig

    def set_bayopt_parameters(self, alpha, xi, percent):
        self.bayopt_alpha = alpha
        self.bayopt_xi = xi
        if percent > 100:
            percent = 100
        elif percent < 0:
            percent = 0
        self.bayopt_random_percentage = percent
