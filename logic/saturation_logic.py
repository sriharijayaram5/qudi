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

    power_start = StatusVar('power_start', 1/1000)
    power_stop = StatusVar('power_stop', 22/1000)
    number_of_points = StatusVar('number_of_points', 15)
    time_per_point = StatusVar('time_per_point', 5)
    #creating a fit container
    fc = StatusVar('fits', None)

    #For OOP measurement:
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
    OOP_nametag = StatusVar('OOP_nametag', '')

    sigRefresh = QtCore.Signal()
    sigUpdateButton = QtCore.Signal()
    sigAbortedMeasurement = QtCore.Signal()
    sigSaturationFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict)
    sigOOPStarted = QtCore.Signal()
    sigOOPStopped = QtCore.Signal()
    sigOOPUpdateData = QtCore.Signal()
    sigParameterUpdated = QtCore.Signal()
    sigDataAvailableUpdated = QtCore.Signal(list)

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
        count_frequency = self._counterlogic.get_count_frequency()
        counter_points = int(count_frequency*time_per_point)
        self._counterlogic.set_count_length(counter_points)

        if self.get_laser_state() == LaserState.OFF:

            self.sigAbortedMeasurement.emit()
            self.sigUpdateButton.emit()
            self.log.warning('Measurement Aborted. Laser is not ON.')
            return

        # time.sleep(time_per_point)
        counts = np.zeros(num_of_points)
        std_dev = np.zeros(num_of_points)

        self._counterlogic.startCount()

        self.sigUpdateButton.emit()

        for i in range(len(laser_power)):

            if self._stop_request:
                break

            #For later when you actually use the counter.
            self._dev.set_power(laser_power[i])
            # time.sleep(time_per_point)

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

            self.set_saturation_data(laser_power, counts, std_dev, i + 1)

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

        @params np.array x_data: optional, laser power values. By default, values stored in self._data.
        @params np.array y_data: optional, fluorescence values. By default, values stored in self._data.

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


    def initialize_odmr_data(self, laser_power_start, laser_power_stop, laser_power_num,
                                  mw_power_start, mw_power_stop, mw_power_num,
                                  freq_start, freq_stop, freq_num):

        meas_dict = {'data': np.zeros((laser_power_num, mw_power_num, freq_num)),
                     # FIXME: get the odmr data std
                     # 'data_std': np.zeros((laser_power_num, mw_power_num, freq_num)),
                     'fit_results': np.zeros((laser_power_num, mw_power_num), dtype = lmfit.model.ModelResult),
                     'saturation_data': np.zeros(laser_power_num),
                     'saturation_data_std': np.zeros(laser_power_num),
                     'background_data': np.zeros(laser_power_num),
                     'background_data_std': np.zeros(laser_power_num),
                     'fit_params': {},
                     'coord0_arr': np.linspace(laser_power_start, laser_power_stop, laser_power_num, endpoint=True),
                     'coord1_arr': np.linspace(mw_power_start, mw_power_stop, mw_power_num, endpoint=True),
                     'coord2_arr': np.linspace(freq_start, freq_stop, freq_num, endpoint=True),
                     'units': 'c/s',
                     'nice_name': 'Fluorescence',
                     'params': {'Parameters for': 'Optimize operating point measurement',
                                'axis name for coord0': 'Laser power',
                                'axis name for coord1': 'Microwave power',
                                'axis name for coord2': 'Microwave frequency',
                                'coord0_start (W)': laser_power_start,
                                'coord0_stop (W)': laser_power_stop,
                                'coord0_num (#)': laser_power_num,
                                'coord1_start (dBm)': mw_power_start,
                                'coord1_stop (dBm)': mw_power_stop,
                                'coord1_num (#)': mw_power_num,
                                'coord2_start (Hz)': freq_start,
                                'coord2_stop (Hz)': freq_stop,
                                'coord2_num (#)': freq_num
                                },  # !!! here are all the measurement parameter saved
                     'display_range': None, # what is it ?
                    }  

        self._odmr_data = meas_dict

        return self._odmr_data




    def perform_measurement(self, laser_power_start=1/1000, laser_power_stop=22/1000, laser_power_num=17, 
                                 final_power=3/1000, mw_power_start=20, mw_power_stop=40, mw_power_num=5,
                                 freq_start=2_800_000_000, freq_stop=2_950_000_000, freq_num=100, 
                                 channel=0, odmr_runtime=60, counter_runtime=3, 
                                 fit_function='Two Lorentzian dips', optimize=False, 
                                 name_tag='', save_after_meas=True, stabilization_time=1):

        #Setting up the stopping mechanism.
        self._OOP_stop_request = False
        self.sigOOPStarted.emit()

        self._odmr_data = self.initialize_odmr_data(laser_power_start, laser_power_stop, laser_power_num,
                                  mw_power_start, mw_power_stop, mw_power_num,
                                  freq_start, freq_stop, freq_num)

        # Save the measurement parameter
        self._odmr_data['params']['ODMR runtime (s)'] = odmr_runtime
        self._odmr_data['params']['Fit function'] = fit_function
        
       
        # Create the lists of powers for the measurement
        laser_power = np.linspace(laser_power_start, laser_power_stop, laser_power_num, endpoint=True)
        mw_power = np.linspace(mw_power_start, mw_power_stop, mw_power_num, endpoint=True)

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
        freq_step = (freq_stop - freq_start) / (freq_num - 1)

        for i in range(len(laser_power)):

            #Stopping mechanism
            if self._OOP_stop_request:
                break

            self._dev.set_power(laser_power[i])

            time.sleep(stabilization_time)
            
            # Optimize the position
            if optimize:
                self.afm_scanner_logic().default_optimize()

            time.sleep(stabilization_time)

            counts_array  = self._counterlogic.request_counts(counter_num_of_points)[channel]
            counts = counts_array.mean()
            std_dev = counts_array.std(ddof=1)

            self._odmr_data['saturation_data'][i] = counts
            self._odmr_data['saturation_data_std'][i] = std_dev          

            self.set_saturation_data(laser_power, self._odmr_data['saturation_data'], self._odmr_data['saturation_data_std'], i + 1)          

            for j in range(len(mw_power)):

                #Stopping mechanism
                if self._OOP_stop_request:
                    break
            
                error, odmr_plot_x, odmr_plot_y, odmr_fit_result = self._odmr_logic.perform_odmr_measurement(
                                     freq_start, freq_step, freq_stop, mw_power[j], channel, odmr_runtime,
                                     fit_function, save_after_meas=False, name_tag='')

                if error:
                    self.log.warning('Optimal operation point measurement aborted')
                    self.sigOOPStopped.emit()
                    return

                odmr_plot_y  = odmr_plot_y[channel, :]

                self._odmr_data['data'][i][j] = odmr_plot_y
                self._odmr_data['fit_results'][i][j] = odmr_fit_result
                self.update_fit_params(i, j, fit_function, laser_power_num, mw_power_num)                
                self.sigOOPUpdateData.emit()

        #TODO: do we need a final power ? Or should we turn the laser off ?
        self._dev.set_power(final_power)

        if save_after_meas :
            self.save_odmr_data(tag=name_tag)
            self.do_fit()
            self.save_saturation_data(tag=name_tag)

        self.sigOOPStopped.emit()

        return self._odmr_data
        

    def save_odmr_data(self, tag=None):

        timestamp = datetime.datetime.now()

        if tag is None:
            tag = ''
        
        #Path and label to save the Saturation data
        filepath = self._save_logic.get_path_for_module(module_name='Optimal operating point')

        if len(tag) > 0:
                filelabel = '{0}_ODMR_data'.format(tag)
        else:
                filelabel = 'ODMR_data'

        
        data = self._odmr_data

        parameters = {}
        parameters.update(data['params'])
        nice_name = data['nice_name']
        unit = data['units']

        parameters['Name of measured signal'] = nice_name
        parameters['Units of measured signal'] = unit

        figure_data = data['data']
        # Add this line if the odmr data standart deviation is recorded. 
        # std_err_data = data['data_std']

        # check whether figure has only zeros as data, skip this then
        if not np.any(figure_data):
            self.log.debug('The data array contains only zeros and will be not saved.')
            return

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

        # Add these lines to save the odmr data standart deviation if it's recorded 

        # image_data_std = {}
        # # reshape the image before sending out to save logic.
        # image_data_std[f'ESR scan std measurements with {nice_name} signal without axis.\n'
        #             'The save data contain directly the fluorescence\n'
        #            f'signals of the esr spectrum in {unit}. Each i-th spectrum\n'
        #             'was taken with laser and microwave power (laser_power_i,\n' 
        #             'mw_power_j), where the top most data correspond to\n'
        #             '(laser_power_start, mw_power_start). For the next spectrum\n'
        #             'the microwave power will be incremented until it reaches \n'
        #             'mw_power_stop. Then the laser power is incremented and the\n'
        #             'microwave power starts again from mw_power_start.'] = std_err_data.reshape(rows*columns, entries)

        # filelabel_std = filelabel + '_std'
        # self._save_logic.save_data(image_data_std, parameters=parameters,
        #                                filepath=filepath,
        #                                filelabel=filelabel_std,
        #                                fmt='%.6e',
        #                                delimiter='\t',
        #                                timestamp=timestamp)
        

        # Save fit result if they are computed

        if self._odmr_data['fit_results'].any():
            if 'Contrast' in self._odmr_data['fit_params']:
                contrast_data = {'Contrast from the fit (%)': self._odmr_data['fit_params']['Contrast']}
                contrast_std_data = {'Error for the contrast from the fit (%)': self._odmr_data['fit_params']['Contrast error']}
                fwhm_data = {'FWHM from the fit (Hz)': self._odmr_data['fit_params']['FWHM']}
                fwhm_std_data = {'Error for FWHM from the fit (Hz)': self._odmr_data['fit_params']['FWHM error']}
            elif 'Contrast 0' in self._odmr_data['fit_params']:
                contrast_data = {'Contrast from the fit (%)': self._odmr_data['fit_params']['Contrast 0']}
                contrast_std_data = {'Error for the contrast from the fit (%)': self._odmr_data['fit_params']['Contrast 0 error']}
                fwhm_data = {'FWHM from the fit (Hz)': self._odmr_data['fit_params']['FWHM 0']}
                fwhm_std_data = {'Error for FWHM from the fit (Hz)': self._odmr_data['fit_params']['FWHM 0 error']}
            filelabel_contrast = filelabel + '_Contrast'
            filelabel_contrast_std = filelabel + '_Contrast_stddev'
            filelabel_fwhm = filelabel + '_FWHM'
            filelabel_fwhm_std = filelabel + '_FWHM_stddev'

            self._save_logic.save_data(contrast_data, parameters=parameters,
                                        filepath=filepath,
                                        filelabel=filelabel_contrast,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        timestamp=timestamp)

            self._save_logic.save_data(contrast_std_data, parameters=parameters,
                                        filepath=filepath,
                                        filelabel=filelabel_contrast_std,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        timestamp=timestamp)
                                        
            self._save_logic.save_data(fwhm_data, parameters=parameters,
                                        filepath=filepath,
                                        filelabel=filelabel_fwhm,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        timestamp=timestamp)

            self._save_logic.save_data(fwhm_std_data, parameters=parameters,
                                        filepath=filepath,
                                        filelabel=filelabel_fwhm_std,
                                        fmt='%.6e',
                                        delimiter='\t',
                                        timestamp=timestamp)

        if len(tag) > 0:
            filelabel_sat = '{0}_Saturation_data'.format(tag)
        else:
            filelabel_sat = 'Saturation_data'

        sat_data = {}
        sat_data['Laser power'] = data['coord0_arr']
        sat_data['Fluorescence'] = data['saturation_data']
        sat_data['Stddev'] = data['saturation_data_std']
        sat_data['Background'] = data['background_data']
        sat_data['Background stddev'] = data['background_data_std']

        self._save_logic.save_data(sat_data, parameters=parameters,
                                       filepath=filepath,
                                       filelabel=filelabel_sat,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp)

        self.log.info('ODMR data saved to:\n{0}'.format(filepath))

        return

    def start_OOP_measurement(self):

        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error("A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.perform_measurement,
                                            args=(self.laser_power_start, 
                                                  self.laser_power_stop, 
                                                  self.laser_power_num,                                                  
                                                  self.laser_power_start, 
                                                  self.mw_power_start, 
                                                  self.mw_power_stop, 
                                                  self.mw_power_num,
                                                  self.freq_start, 
                                                  self.freq_stop, 
                                                  self.freq_num,
                                                  self.channel, 
                                                  self.odmr_runtime, 
                                                  self.counter_runtime,
                                                  self.odmr_fit_function,
                                                  self.optimize,
                                                  self.OOP_nametag),
                                                  name='operation_point_measurement') 

        self.threadpool.start(self._worker_thread)

    def stop_OOP_measurement(self):
        self._OOP_stop_request = True

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
                  'OOP_nametag': self.OOP_nametag}
        return params

    def set_OOP_laser_params(self, laser_power_start, laser_power_stop, 
                             laser_power_num):
        #TODO: check if the module is locked or not before changing the params
        lpr = self.laser_power_range
        if isinstance(laser_power_start, (int, float)):
            self.laser_power_start = units.in_range(laser_power_start, lpr[0], lpr[1])
        if isinstance(laser_power_stop, (int, float)):
            if laser_power_stop < laser_power_start:
                laser_power_stop = laser_power_start
            self.laser_power_stop =  units.in_range(laser_power_stop, lpr[0], lpr[1])
        if isinstance(laser_power_num, int):
            self.laser_power_num = laser_power_num
        self.sigParameterUpdated.emit()
        return self.laser_power_start, self.laser_power_stop, self.laser_power_num

    def set_OOP_mw_params(self, mw_power_start, mw_power_stop, 
                             mw_power_num):
        #TODO: check if the module is locked or not before changing the params
        limits = self.get_odmr_constraints()
        if isinstance(mw_power_start, (int, float)):
            self.mw_power_start = limits.power_in_range(mw_power_start)
        if isinstance(mw_power_stop, (int, float)):
            if mw_power_stop < mw_power_start:
                mw_power_stop = mw_power_start
            self.mw_power_stop =  limits.power_in_range(mw_power_stop)
        if isinstance(mw_power_num, int):
            self.mw_power_num = mw_power_num
        self.sigParameterUpdated.emit()
        return self.mw_power_start, self.mw_power_stop, self.mw_power_num

    def set_OOP_freq_params(self, freq_start, freq_stop, 
                             freq_num):
        #TODO: check if the module is locked or not before changing the params
        limits = self.get_odmr_constraints()
        if isinstance(freq_start, (int, float)):
            self.freq_start = limits.frequency_in_range(freq_start)
        if isinstance(freq_stop, (int, float)):
            if freq_stop < freq_start:
                freq_stop = freq_start
            self.freq_stop =  limits.frequency_in_range(freq_stop)
        if isinstance(freq_num, int):
            self.freq_num = freq_num
        self.sigParameterUpdated.emit()
        return self.freq_start, self.freq_stop, self.freq_num

    def set_OOP_runtime_params(self, counter_runtime, odmr_runtime):
        #TODO: check if the module is locked or not before changing the params
        if isinstance(counter_runtime, (int, float)):
            self.counter_runtime = counter_runtime
        if isinstance(odmr_runtime, (int, float)):
            self.odmr_runtime = odmr_runtime
        self.sigParameterUpdated.emit()
        return self.counter_runtime, odmr_runtime

    #FIXME: check whether the channel exists or not
    def set_OOP_channel(self, channel):
        self.channel = channel
        self.sigParameterUpdated.emit()
        return self.channel

    def set_OOP_optimize(self, boolean):
        self.optimize = boolean
        self.sigParameterUpdated.emit()
        return self.optimize 

    def get_odmr_fits(self):
        fit_list = self._odmr_logic.fc.fit_list.keys()
        return fit_list

    def set_odmr_fit(self, fit_name):
        if fit_name in self.get_odmr_fits():
            self.odmr_fit_function = fit_name
        self.sigParameterUpdated.emit()
        return self.odmr_fit_function

    def set_OOP_nametag(self, nametag):
        self.OOP_nametag = nametag
        self.sigParameterUpdated.emit()
        return self.OOP_nametag

    def update_fit_params(self, i, j, fit_function, laser_power_num, mw_power_num):
        if fit_function != 'No fit':
            if not hasattr(self._odmr_data['fit_results'][0][0], 'result_str_dict'):
                self.log.warning("The selected fit does not allow to access the fit parameters. Please chose another fit.")
                return

            param_dict = self._odmr_data['fit_results'][i][j].result_str_dict
            if (i, j) == (0, 0):
                for param_name in param_dict.keys():
                    self._odmr_data['fit_params'][param_name] = np.zeros((laser_power_num, mw_power_num))
                    if 'error' in param_dict[param_name]:
                        self._odmr_data['fit_params'][param_name + ' error'] = np.zeros((laser_power_num, mw_power_num))
                #self.sigDataAvailableUpdated.emit(list(self._odmr_data['fit_params'].keys()))
                self.sigDataAvailableUpdated.emit(list(param_dict.keys()))
            for param_name in param_dict:
                self._odmr_data['fit_params'][param_name][i][j] = param_dict[param_name]['value']
                if 'error' in param_dict[param_name]:
                    self._odmr_data['fit_params'][param_name + ' error'][i][j] = param_dict[param_name]['error']

    def get_data(self, data_name):
        if data_name in self._odmr_data['fit_params']:
            return self._odmr_data['fit_params'][data_name]
        else:
            self.log.warning("This data is not available from the fit, sorry!")
            return np.array([[0]])

    def get_data_unit(self, data_name):
        if hasattr(self._odmr_data['fit_results'][0][0], 'result_str_dict'):
            param_dict = self._odmr_data['fit_results'][0][0].result_str_dict
            if data_name in  param_dict:
                return param_dict[data_name]['unit']
        return ''