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

    queryInterval = ConfigOption('query_interval', 100)

    power_start = StatusVar('power_start', 1/1000)
    power_stop = StatusVar('power_stop', 22/1000)
    number_of_points = StatusVar('number_of_points', 15)
    time_per_point = StatusVar('time_per_point', 5)
    #creating a fit container
    fc = StatusVar('fits', None)

    sigRefresh = QtCore.Signal()
    sigUpdateButton = QtCore.Signal()
    sigAbortedMeasurement = QtCore.Signal()
    sigSaturationFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict)

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
        #These 3 are probably not needed afterwards with the data
        self._saturation_data = {}
        self._odmr_data = {}

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
        fc = self.fitlogic().make_fit_container('saturation_curve_agathe', '1d')
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
        return self.get_laser_state()

    def off(self):
        """ Turn off laser. Does not close shutter if one is present.
        
        @return enum LaserState: actual laser state
        """

        self._dev.off()
        return self.get_laser_state()

    def get_power(self):
        """ Return laser power independent of the mode.

        @return float: Actual laser power in Watts (W).
        """
        
        self._dev.get_power()

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

        return self.get_current()

    def set_control_mode(self,control_mode):
        """ Set laser control mode.
        
        @param enum control_mode: desired control mode
        
        @return enum ControlMode: actual control mode
        """
        self._dev.set_control_mode(control_mode)

    def get_control_mode(self):
        """ Get control mode of laser

        @return enum ControlMode: control mode
        """

        return self.mode

    def get_laser_state(self):
        """ Get laser state.
        
        @return enum LaserState: laser state
        """

        return self._dev.get_laser_state()

    def get_saturation_data(self):
        """ Get recorded data.

        @return dict: contains an np.array with the measured or computed values for each data field
        (e.g. 'Fluorescence', 'Power') .
        """
        data_copy = copy.deepcopy(self._saturation_data)
        return data_copy

    def set_saturation_data(self, xdata, ydata, std_dev=None, num_of_points=None):
        """Set the data.

        @params np.array xdata: laser power values
        @params np.array ydata: fluorescence values
        @params np.array std_dev: optional, standard deviation values
        @params np.array num_of_points: optional, number of data points. The default value is len(xdata)
        """

        if num_of_points is None:
            num_of_points = len(xdata)
            
        #Setting up the list for data
        self._saturation_data['Power'] = np.zeros(num_of_points)
        self._saturation_data['Fluorescence'] = np.zeros(num_of_points)
        if std_dev is not None:
            self._saturation_data['Stddev'] = np.zeros(num_of_points)

        for i in range(num_of_points):
            self._saturation_data['Power'][i] = xdata[i]
            self._saturation_data['Fluorescence'][i] = ydata[i]
            if std_dev is not None:
                self._saturation_data['Stddev'][i] = std_dev[i]

        self.sigRefresh.emit()


    def saturation_curve_data(self,time_per_point,start_power,stop_power,
                            num_of_points,final_power):
        """ Obtain all necessary data to create a saturation curve

        @param int time_per_point: acquisition time of counts per each laser power in seconds.
        @param int start_power: starting power in Watts.
        @param int stop_power:  stoping power in Watts.
        @param int num_of_points: number of points for the measurement.
        
        @return enum ControlMode: control mode
        """

        #Setting up the stopping mechanism.
        self._stop_request = False

        #Creating the list of powers for the measurement.
        power_calibration = np.zeros(num_of_points)
        laser_power = np.zeros(num_of_points)

        for i in range(len(laser_power)):
            step = (stop_power-start_power)/(num_of_points-1)
            laser_power[i] = start_power+i*step

        #For later when you actually use the counter.
        #average_time = time_per_point #time in seconds
        #count_frequency = self._counterlogic.get_count_frequency()
        #points = count_frequency*average_time
        #self._counterlogic.set_count_length(points)

        if self.get_laser_state() == LaserState.OFF:

            self.sigAbortedMeasurement.emit()
            self.sigUpdateButton.emit()
            self.log.warning('Measurement Aborted. Laser is not ON.')
            return

            #self._dev.on()

        time.sleep(time_per_point)
        counts = np.zeros(num_of_points)
        std_dev = np.zeros(num_of_points)

        self._counterlogic.startCount()

        self.sigUpdateButton.emit()

        for i in range(len(laser_power)):

            if self._stop_request:
                break

            #For later when you actually use the counter.
            #self._dev.set_power(laser_power[i])
            #time.sleep(time_per_point)

            #For testing only.
            time.sleep(1)
            counts[i] = random.random()
            std_dev[i] = random.random()

            #For later when you actually use the counter.
            #counts[i] = self._counterlogic.countdata[0].mean()
            #std_dev[i] = statistics.stdev(self._counterlogic.countdata[0])

            self.set_saturation_data(laser_power, counts, std_dev, i + 1)
            #self.set_data(laser_power, counts, std_dev, num_of_points)

        self._counterlogic.stopCount()

        self._dev.set_power(final_power)

        self.sigUpdateButton.emit()

        array_of_data = np.vstack((counts,laser_power,power_calibration)).transpose()

        return array_of_data

    def start_saturation_curve_data(self,time_per_point=4,start_power=1/1000,stop_power=22/1000,
                        num_of_points=17,final_power=3/1000):
        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.saturation_curve_data,
                                            args=(time_per_point,start_power,
                                                stop_power,num_of_points,final_power),
                                            name='saturation_curve_points') 

        self.threadpool.start(self._worker_thread)

    def stop_saturation_curve_data(self):
        """ Set a flag to request stopping counting.
        """
        if self._counterlogic.module_state() == 'locked':
            self._stop_request = True
        else:
            self._stop_request = True

        #self.sigUpdateButton.emit()
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

        #MISSING Fit parameters
        parameters = OrderedDict()

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

        #FIT STILL MISSING
        # Do not include fit curve if there is no fit calculated.

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

        @params np.array x_data: optional, laser power values. By default, values stored in self._data.
        @params np.array y_data: optional, fluorescence values. By default, values stored in self._data.

        Create 3 class attributes
            np.array self.saturation_fit_x: 1D arrays containing the x values of the fitting function
            np.array self.saturation_fit_y: 1D arrays containing the y values of the fitting function
            lmfit.model.ModelResult fit_result: the result object of lmfit. If additional information
                                        is needed from the fit, then they can be obtained from this 
                                        object. 
        """
        self.fc.current_fit = 'Hyperbolic_saturation'

        if 'Power' not in self._saturation_data or len(self._saturation_data['Power']) < 3:
            self.log.warning('There is not enough data points to fit the curve. Fitting aborted.')
            return

        if (x_data is None) or (y_data is None):
            x_data = self._saturation_data['Power']
            y_data = self._saturation_data['Fluorescence']

        self.saturation_fit_x, self.saturation_fit_y, self.fit_result = self.fc.do_fit(x_data, y_data)
        if self.fit_result is None:
            result_str_dict = {}
        else:
            result_str_dict = self.fit_result.result_str_dict
        self.sigSaturationFitUpdated.emit(self.saturation_fit_x, self.saturation_fit_y, result_str_dict)
        return

    def set_odmr_data(self, xdata, ydata, fit_params, laser_power, clear=False):

        if clear:
            self._odmr_data.clear()

        self._odmr_data[laser_power] = {}
        self._odmr_data[laser_power]['Frequency'] = xdata
        self._odmr_data[laser_power]['Fluorescence'] = ydata
        self._odmr_data[laser_power]['Fit'] = fit_params


    def perform_odmr_measurement(self, freq_start=2_800_000_000, freq_step=1_000_000, 
                                 freq_stop=2_950_000_000, mw_power=30, channel=0, runtime=60,
                                 fit_function='No Fit', save_after_meas=True, name_tag=''):

        odmr_plot_x, odmr_plot_y, odmr_fit_params = self._odmr_logic.perform_odmr_measurement(
                                     freq_start, freq_step, freq_stop, mw_power, channel, runtime,
                                     fit_function, save_after_meas, name_tag)

        return odmr_plot_x, odmr_plot_y[channel, :], odmr_fit_params

    def perform_measurement(self, start_power=1/1000, stop_power=22/1000, num_of_points=17, 
                                 final_power=3/1000, freq_start=2_800_000_000, freq_step=1_000_000,
                                 freq_stop=2_950_000_000, mw_power=30, channel=0, runtime=60, 
                                 fit_function='No Fit', save_after_meas=True, name_tag=''):

        #Creating the list of powers for the measurement.
        laser_power = np.zeros(num_of_points)
        
        if num_of_points == 1:
            laser_power[0] = start_power
        
        else:
            power_step = (stop_power - start_power) / (num_of_points - 1)
            for i in range(len(laser_power)):
                laser_power[i] = start_power + i * power_step

        if self.get_laser_state() == LaserState.OFF:
            self._dev.on()

        self._odmr_data.clear()

        for i in range(len(laser_power)):

            # if self._stop_request:
            #     break

            self._dev.set_power(laser_power[i])

            odmr_plot_x, odmr_plot_y, odmr_fit_params = self.perform_odmr_measurement(freq_start, 
                                                 freq_step, freq_stop, mw_power, channel, runtime, 
                                                 fit_function, save_after_meas, name_tag)

            self.set_odmr_data(odmr_plot_x, odmr_plot_y, odmr_fit_params, laser_power[i])

        self._dev.set_power(final_power)

        return self._odmr_data
        
    


        








