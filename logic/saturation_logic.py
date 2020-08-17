# -*- coding: utf-8 -*-
"""
This file contains the logic for measuring a saturation curve, scanning the laser 
and microwave power space and optimizing the sensitivity.

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

from core.util import units
import time
import numpy as np
import random
import datetime
from qtpy import QtCore
import matplotlib.pyplot as plt
import copy
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

    # Declare connectors
    laser_conn = Connector(interface='SimpleLaserInterface')
    counter_logic = Connector(interface='CounterLogic')
    savelogic = Connector(interface='SaveLogic')
    fitlogic = Connector(interface='FitLogic')
    odmrlogic = Connector(interface='ODMRLogic')
    afm_scanner_logic = Connector(interface='AFMConfocalLogic')

    # Create a fit container
    fc = StatusVar('fits', None)

    # Status variable
    # For the saturation curve
    final_power = StatusVar('final_power', 0.005)
    power_start = StatusVar('power_start', 0.001)
    power_stop = StatusVar('power_stop', 0.022)
    number_of_points = StatusVar('number_of_points', 15)
    time_per_point = StatusVar('time_per_points', 5)
    # For the scan and bayesian optimization
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
    # For bayesian optimization
    bayopt_num_meas = StatusVar('bayopt_num_meas', 30)
    bayopt_alpha = StatusVar('bayopt_alpha', 0.15)
    bayopt_random_percentage = StatusVar('bayopt_random_percentage', 35)
    bayopt_xi = StatusVar('bayopt_xi', 0.1)

    # Update signals, e.g. for GUI module
    sigSaturationDataUpdated = QtCore.Signal()
    sigLaserStateChanged = QtCore.Signal()
    sigControlModeChanged = QtCore.Signal()
    sigPowerSet = QtCore.Signal(float)
    sigSaturationStarted = QtCore.Signal()
    sigSaturationStopped = QtCore.Signal()
    sigSaturationFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict)
    sigDoubleFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict)
    sigSaturationParameterUpdated = QtCore.Signal()
    sigScanStarted = QtCore.Signal()
    sigScanStopped = QtCore.Signal()
    sigScanUpdateData = QtCore.Signal()
    sigParameterUpdated = QtCore.Signal()
    sigDataAvailableUpdated = QtCore.Signal(list)
    sigBayoptStarted = QtCore.Signal()
    sigBayoptStopped = QtCore.Signal()
    sigBayoptUpdateData = QtCore.Signal(int)

    # Make a dummy worker thread
    _worker_thread = WorkerThread(print)

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        # Get connectors
        self._dev = self.laser_conn()
        self._counterlogic = self.counter_logic()
        self._save_logic = self.savelogic()
        self._odmr_logic = self.odmrlogic()

        # Start in cw mode
        if self._dev.get_control_mode() != ControlMode.POWER:
            self._dev.set_control_mode(ControlMode.POWER)

        # Get laser capabilities
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

        # Create data containers
        self._saturation_data = {}
        self._background_data = {}
        self._scan_data = {}
        self._bayopt_data = {}

        # Initialize attribute
        self.is_background = False
        self._stop_request = False
        self._scan_stop_request = False
        self._bayopt_stop_request = False
        self.fit_parameters_list = {'lorentzian': {'Count rate': ('offset', 'c/s'),
                                                   'Contrast': ('contrast', '%'),
                                                   'FWHM': ('fwhm', 'Hz'),
                                                   'Sensitivity': ('sensitivity', 'T/sqrt(Hz)'),
                                                   'Position': ('center', 'Hz')},
                                    'lorentziandouble': {'Count rate': ('offset', 'c/s'),
                                                         'Contrast 0': ('l0_contrast', '%'),
                                                         'Contrast 1': ('l1_contrast', '%'),
                                                         'FWHM 0': ('l0_fwhm', 'Hz'),
                                                         'FWHM 1': ('l1_fwhm', 'Hz'),
                                                         'Sensitvity 0': ('l0_sensitivity', 'T/sqrt(Hz)'),
                                                         'Sensitivity 1': ('l1_sensitivity', 'T/sqrt(Hz)')},
                                    'lorentziantriple': {'Count rate': ('offset', 'c/s'),
                                                         'Contrast 0': ('l0_contrast', '%'),
                                                         'Contrast 1': ('l1_contrast', '%'),
                                                         'Contrast 2': ('l2_contrast', '%'),
                                                         'FWHM 0': ('l0_fwhm', 'Hz'),
                                                         'FWHM 1': ('l1_fwhm', 'Hz'),
                                                         'FWHM 2': ('l2_fwhm', 'Hz'),
                                                         'Sensitvity 0': ('l0_sensitivity', 'T/sqrt(Hz)'),
                                                         'Sensitivity 1': ('l1_sensitivity', 'T/sqrt(Hz)'),
                                                         'Sensitivity 2': ('l2_sensitivity', 'T/sqrt(Hz)')},
                                    'gaussian': {'Count rate': ('offset', 'c/s'),
                                                 'Contrast': ('contrast', '%'),
                                                 'FWHM': ('fwhm', 'Hz'),
                                                 'Position': ('center', 'Hz')},
                                    'gaussiandouble': {'Count rate': ('offset', 'c/s'),
                                                       'Contrast 0': ('g0_contrast', '%'),
                                                       'Contrast 1': ('g1_contrast', '%'),
                                                       'FWHM 0': ('g0_fwhm', 'Hz'),
                                                       'FWHM 1': ('g1_fwhm', 'Hz')},
                                    'voigt': {'Count rate': ('offset', 'c/s'),
                                              'Contrast': ('contrast', '%'),
                                              'FWHM': ('fwhm', 'Hz'),
                                              'Sensitivity': ('sensitivity', 'T/sqrt(Hz)'),
                                              'Lorentzian fraction': ('fraction', '%'),
                                              'Position': ('center', 'Hz')},
                                    'voigtdouble': {'Count rate': ('v0_offset', 'c/s'),
                                                    'Contrast 0': ('v0_contrast', '%'),
                                                    'Contrast 1': ('v1_contrast', '%'),
                                                    'FWHM 0': ('v0_fwhm', 'Hz'),
                                                    'FWHM 1': ('v1_fwhm', 'Hz'),
                                                    'Sensitvity 0': ('v0_sensitivity', 'T/sqrt(Hz)'),
                                                    'Sensitivity 1': ('v1_sensitivity', 'T/sqrt(Hz)'),
                                                    'Lorentzian fraction 0': ('v0_fraction', '%'),
                                                    'Lorentzian fraction 1': ('v1_fraction', '%')},
                                    'voigtequalized': {'Count rate': ('offset', 'c/s'),
                                                       'Contrast': ('contrast', '%'),
                                                       'FWHM': ('fwhm', 'Hz'),
                                                       'Sensitvity': ('sensitivity', 'T/sqrt(Hz)'),
                                                       'Position': ('center', 'Hz')},
                                    'voigtdoubleequalized': {'Count rate': ('v0_offset', 'c/s'),
                                                             'Contrast 0': ('v0_contrast', '%'),
                                                             'Contrast 1': ('v1_contrast', '%'),
                                                             'FWHM 0': ('v0_fwhm', 'Hz'),
                                                             'FWHM 1': ('v1_fwhm', 'Hz'),
                                                             'Sensitvity 0': ('v0_sensitivity', 'T/sqrt(Hz)'),
                                                             'Sensitivity 1': ('v1_sensitivity', 'T/sqrt(Hz)')},
                                    'pseudovoigt': {'Count rate': ('offset', 'c/s'),
                                                    'Contrast': ('contrast', '%'),
                                                    'FWHM': ('fwhm', 'Hz'),
                                                    'Sensitivity': ('sensitivity', 'T/sqrt(Hz)'),
                                                    'Lorentzian fraction': ('fraction', '%'),
                                                    'Position': ('center', 'Hz')},
                                    'pseudovoigtdouble': {'Count rate': ('v0_offset', 'c/s'),
                                                          'Contrast 0': ('v0_contrast', '%'),
                                                          'Contrast 1': ('v1_contrast', '%'),
                                                          'FWHM 0': ('v0_fwhm', 'Hz'),
                                                          'FWHM 1': ('v1_fwhm', 'Hz'),
                                                          'Sensitvity 0': ('v0_sensitivity', 'T/sqrt(Hz)'),
                                                          'Sensitivity 1': ('v1_sensitivity', 'T/sqrt(Hz)'),
                                                          'Lorentzian fraction 0': ('v0_fraction', '%'),
                                                          'Lorentzian fraction 1': ('v1_fraction', '%')},
                                    }

        # Create threadpool where our worker thread will be run
        self.threadpool = QtCore.QThreadPool()

    def on_deactivate(self):
        """ Deactivate module.
        """
        # TODO: Stop measurement if it is still running
        pass

    @fc.constructor
    def sv_set_fits(self, val):
        # Setup fit container
        fc = self.fitlogic().make_fit_container('saturation_curve', '1d')
        fc.set_units(['W', 'c/s'])
        if isinstance(val, dict) and len(val) > 0:
            fc.load_from_dict(val)
        else:
            d1 = {}
            d1['Hyperbolic_saturation'] = {
                'fit_function': 'hyperbolicsaturation', 'estimator': '2'}
            d2 = {}
            d2['1d'] = d1
            fc.load_from_dict(d2)
        return fc

    @fc.representer
    def sv_get_fits(self, val):
        """ Save configured fits """
        if len(val.fit_list) > 0:
            return val.save_to_dict()
        else:
            return None

    def check_thread_active(self):
        """ Check whether current worker thread is running. """

        if hasattr(self, '_worker_thread'):
            if self._worker_thread.is_running():
                return True
        return False

    ###########################################################################
    #                             Laser methods                               #
    ###########################################################################

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

    def get_laser_state(self):
        """ Get laser state.

        @return enum LaserState: laser state
        """

        return self._dev.get_laser_state()

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

    def get_control_mode(self):
        """ Get control mode of laser.

        @return enum ControlMode: control mode
        """

        return self._dev.get_control_mode()

    def set_control_mode(self, control_mode):
        """ Set laser control mode.

        @param enum control_mode: desired control mode

        @return enum ControlMode: actual control mode
        """
        self._dev.set_control_mode(control_mode)
        self.sigControlModeChanged.emit()
        return self.get_control_mode()

    ###########################################################################
    #                     Saturation curve  methods                           #
    ###########################################################################

    def get_saturation_parameters(self):
        """ Get the parameters of the saturation curve.

        @return dict
        """
        params = {'power_start': self.power_start,
                  'power_stop': self.power_stop,
                  'number_of_points': self.number_of_points,
                  'time_per_point': self.time_per_point
                  }
        return params

    def set_saturation_params(self, power_start, power_stop, number_of_points,
                              time_per_point):
        """ Set the parameters for the saturation curve.

        @param float power_start: laser power for the first point in Watt
        @param float power_stop: laser power for the last point in Watt
        @param int number_of_points: number of measured points
        @param float time_per_point: counter runtime for each point in second
        """
        lpr = self.laser_power_range

        if isinstance(power_start, (int, float)):
            self.power_start = units.in_range(power_start, lpr[0], lpr[1])

        if isinstance(power_stop, (int, float)):
            self.power_stop = units.in_range(power_stop, lpr[0], lpr[1])

        if isinstance(number_of_points, int):
            self.number_of_points = number_of_points

        if isinstance(time_per_point, (int, float)):
            self.time_per_point = time_per_point

        self.sigSaturationParameterUpdated.emit()
        return self.power_start, self.power_stop, self.number_of_points, self.time_per_point

    def get_saturation_data(self, is_background=False):
        """ Get recorded data.

        @return dict: contains an np.array with the measured or computed values
        for each data field (e.g. 'Fluorescence', 'Power') .
        """
        if is_background:
            data_copy = copy.deepcopy(self._background_data)
        else:
            data_copy = copy.deepcopy(self._saturation_data)
        return data_copy

    def set_saturation_data(self, xdata, ydata, std_dev=None, num_of_points=None,
                            is_background=False):
        """Set the saturation curve data in the dedicated dictionary.

        @params np.array xdata: laser power values
        @params np.array ydata: fluorescence values
        @params np.array std_dev: optional, standard deviation values
        @params np.array num_of_points: optional, number of data points. The 
                default value is len(xdata)
        @params bool is_background: if True, the data is stored in _background_data. 
                Default is False.
        """

        if num_of_points is None:
            num_of_points = len(xdata)

        # Setting up the list for data
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

        self.sigSaturationDataUpdated.emit()

    def record_saturation_curve(self, time_per_point, start_power, stop_power,
                                num_of_points, final_power, is_background=False):
        """ Record all the point of the saturation curve

        @param float time_per_point: acquisition time of counts per each laser power in seconds.
        @param float start_power: starting power in Watt.
        @param float stop_power:  stoping power in Watt.
        @param int num_of_points: number of points for the measurement.
        @param float final_power: laser power set at the end of the saturation curve in Watt.
        @param bool is_background: Whether the saturation curve is recorded on the background.
        """

        # Set up the stopping mechanism.
        self._stop_request = False

        self.sigSaturationStarted.emit()

        # Create the list of powers for the measurement.
        laser_power = np.linspace(start_power, stop_power, num_of_points)
        # TODO: Add a list with calibrated power

        count_frequency = self._counterlogic.get_count_frequency()
        counter_points = int(count_frequency * time_per_point)
        self._counterlogic.set_count_length(counter_points)

        if self.get_laser_state() == LaserState.OFF:
            self.log.error('Measurement Aborted. Laser is not ON.')
            self.sigSaturationStopped.emit()
            return

        counts = np.zeros(num_of_points)
        std_dev = np.zeros(num_of_points)

        # FIXME: The counter should not have to be started and stopped but it's
        # done here because of a bug of counterlogic.request_counts otherwise.
        self._counterlogic.startCount()

        for i in range(len(laser_power)):

            if self._stop_request:
                break

            self.set_power(laser_power[i])
            time.sleep(1)

            counts_array = self._counterlogic.request_counts(counter_points)[
                self.channel]
            counts[i] = counts_array.mean()
            std_dev[i] = counts_array.std(ddof=1)

            self.set_saturation_data(
                laser_power, counts, std_dev, i + 1, is_background)

        # FIXME: The counter should not have to be started and stopped but it's
        # done here because of a bug of counterlogic.request_counts otherwise.
        self._counterlogic.stopCount()

        self.set_power(final_power)

        self.sigSaturationStopped.emit()

    def start_saturation_curve(self):
        """ Start a threaded measurement for the saturation curve.
        """
        if self.check_thread_active():
            self.log.error(
                "A measurement is currently running, stop it first!")
            self.sigSaturationStopped.emit()
            return

        self._worker_thread = WorkerThread(target=self.record_saturation_curve,
                                           args=(self.time_per_point, self.power_start,
                                                 self.power_stop, self.number_of_points,
                                                 self.final_power, self.is_background),
                                           name='saturation_curve')

        self.threadpool.start(self._worker_thread)

    def stop_saturation_curve(self):
        """ Set a flag to request stopping the saturation curve measurement.
        """
        self._stop_request = True

    def save_saturation_data(self, tag=None):
        """ Save the current saturation data to a text file and a figure.

        @param str tag: optional, tag added to the filename.
        """
        timestamp = datetime.datetime.now()

        if tag is None:
            tag = ''

        # Path and label to save the saturation data
        filepath = self._save_logic.get_path_for_module(
            module_name='Saturation curve')

        if len(tag) > 0:
            filelabel = '{0}_Saturation_data'.format(tag)
        else:
            filelabel = 'Saturation_data'

        # The data is already prepared in a dict
        data = self._saturation_data

        if not data:
            self.log.warning(
                'There is no data to save. Start a measurement first.')
            return

        # Include fit parameters if a fit has been calculated
        parameters = {}
        if hasattr(self, 'saturation_fit_params'):
            parameters = self.saturation_fit_params

        # Drawing the figure
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

    def draw_figure(self):
        """ Draw the figure to save with the data.

        @return matplotlib.figure.Figure fig: a matplotlib figure object to be 
        saved to file.
        """

        counts = self._saturation_data['Fluorescence']
        stddev = self._saturation_data['Stddev']
        laser_power = self._saturation_data['Power']

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig = plt.figure()
        plt.errorbar(laser_power, counts, yerr=stddev)

        # Include fit curve if there is a fit calculated
        if hasattr(self, 'saturation_fit_x'):
            plt.plot(self.saturation_fit_x,
                     self.saturation_fit_y, marker='None')

        # Set the labels
        plt.ylabel('Fluorescence (cts/s)')
        plt.xlabel('Laser Power (W)')

        return fig

    def do_fit(self, x_data=None, y_data=None):
        """
        Execute the fit (configured in the fc object) on the measurement data. 
        Optionally on passed data.

        @params np.array x_data: optional, laser power values. By default, values 
                                 stored in self._saturation_data.
        @params np.array y_data: optional, fluorescence values. By default, values 
                                 stored in self._saturation_data.

        Create 3 class attributes
            np.array self.saturation_fit_x: 1D arrays containing the x values 
                                            of the fitting function
            np.array self.saturation_fit_y: 1D arrays containing the y values 
                                            of the fitting function
            dict self.saturation_fit_params: Contains the parameters of the fit 
                                             ready to be displayed
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
            self.log.warning(
                'There is not enough data points to fit the curve. Fitting aborted.')
            return

        self.saturation_fit_x, self.saturation_fit_y, fit_result = self.fc.do_fit(
            x_data, y_data)
        if fit_result is None:
            self.saturation_fit_params = {}
        else:
            self.saturation_fit_params = fit_result.result_str_dict
        self.sigSaturationFitUpdated.emit(
            self.saturation_fit_x, self.saturation_fit_y, self.saturation_fit_params)
        return

    def do_double_fit(self, x_saturation=None, y_saturation=None,
                      x_background=None, y_background=None):
        """
        Execute the double fit (with the background) on the measurement data. 
        Optionally on passed data.

        @params np.array x_saturation: optional, laser power values for the saturation 
                                       measurement (on the NV center). By default, 
                                       values stored in self._saturation_data.
        @params np.array y_saturation: optional, fluorescence values for the saturation 
                                       measurement (on the NV center). By default, 
                                       values stored in self._saturation_data.
        @params np.array x_background: optional, laser power values for the background 
                                       measurement. By default, values stored in 
                                       self._background_data.
        @params np.array y_background: optional, fluorescence values for the background 
                                       measurement. By default, values stored in 
                                       self._background_data.
        @return (np.array, np.array, dict): 
            2D array containing the x values of the fitting functions: the first 
                row correspond to the NV saturation curve and the second row to 
                the background curve.
            2D array containing the y values of the fitting functions: the first 
                row correspond to the NV saturation curve and the second row to 
                the background curve.
            Dictionary Containing the parameters of the fit ready to be displayed
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
            self.log.warning(
                'There is not enough data points to fit the curve. Fitting aborted.')
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
                                                                                             self.fitlogic().estimate_hyperbolicsaturation_with_background,
                                                                                             units=['W', 'c/s'])
        self.sigDoubleFitUpdated.emit(fit_x, fit_y, result.result_str_dict)

    ###########################################################################
    #                    Optimal operation point methods                      #
    ###########################################################################

    ########################
    #       Getters        #
    ########################

    def get_OOP_parameters(self):
        """ Get the parameters of Optimal Operation Point measurement.

        @return dict
        """
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

    def get_odmr_constraints(self):
        """ Get the mw power and frequency constraints from the odmr logic.

        @return object: Hardware constraints object.
        """
        return self._odmr_logic.get_hw_constraints()

    def get_odmr_channels(self):
        """ Return the available channels.
        """
        return self._odmr_logic.get_odmr_channels()

    def get_odmr_fits(self):
        """ Get the fits available for fitting the ODMR spectra.

        @return list: List containing the names of the fit as string. 
        """
        fit_list = []
        available_fits = self._odmr_logic.fc.fit_list
        for fit in available_fits.keys():
            if available_fits[fit]['fit_name'] in self.fit_parameters_list:
                fit_list.append(fit)
        return fit_list

    def get_scan_data(self, data_name):
        """ Return the matrix with the actual values of a given data (e.g. Contrast, FWHM)
        for the scan and the associated unit

        @param str data_name: The name of the data for which the matrix will be returned. 

        @return (np.ndarray, str): the matrix and the associated unit.
        """
        if data_name in self._scan_data['fit_params']:
            param_dict = self._scan_data['fit_params'][data_name]
            return param_dict['values'], param_dict['unit']
        else:
            self.log.error("This data is not available from the fit, sorry!")
            return np.array([[0]]), ''

    def get_bayopt_data(self):
        """ Getter for the data dictionary.
        """
        return self._bayopt_data

    ########################
    #       Setters        #
    ########################

    # TODO: check if the module is locked or not before changing the params

    def set_laser_power_start(self, laser_power_start):
        """ Set the minimum laser power for the Optimal Operation Point scan and 
        Bayesian optimization. 

        @param float laser_power_start: minimum laser power in Watt
        """
        lpr = self.laser_power_range
        if isinstance(laser_power_start, (int, float)):
            self.laser_power_start = units.in_range(
                laser_power_start, lpr[0], lpr[1])
        self.sigParameterUpdated.emit()
        return self.laser_power_start

    def set_laser_power_stop(self, laser_power_stop):
        """ Set the maximum laser power for the Optimal Operation Point scan and 
        Bayesian optimization. 

        @param float laser_power_stop: maximum laser power in Watt
        """
        # FIXME: Prevent laser_power_stop being equal to laser_power_start:
        # that causes a bug.
        lpr = self.laser_power_range
        if isinstance(laser_power_stop, (int, float)):
            if laser_power_stop < self.laser_power_start:
                laser_power_stop = self.laser_power_start
            self.laser_power_stop = units.in_range(
                laser_power_stop, lpr[0], lpr[1])
            self.sigParameterUpdated.emit()
            return self.laser_power_stop

    def set_laser_power_num(self, laser_power_num):
        """ Set the number of laser powers for the Optimal Operation Point scan.

        @param int laser_power_num: number of laser power points 
        """
        if isinstance(laser_power_num, int):
            self.laser_power_num = laser_power_num
        self.sigParameterUpdated.emit()
        return self.laser_power_num

    def set_mw_power_start(self, mw_power_start):
        """ Set the minimum microwave power for the Optimal Operation Point scan and 
        Bayesian optimization. 

        @param float mw_power_start: minimum mw power in dBm
        """
        limits = self.get_odmr_constraints()
        if isinstance(mw_power_start, (int, float)):
            self.mw_power_start = limits.power_in_range(mw_power_start)
        self.sigParameterUpdated.emit()
        return self.mw_power_start

    def set_mw_power_stop(self, mw_power_stop):
        """ Set the maximum mw power for the Optimal Operation Point scan and 
        Bayesian optimization. 

        @param float mw_power_stop: maximum mw power in dBm
        """
        limits = self.get_odmr_constraints()
        if isinstance(mw_power_stop, (int, float)):
            if mw_power_stop < self.mw_power_start:
                mw_power_stop = self.mw_power_start
            self.mw_power_stop = limits.power_in_range(mw_power_stop)
        self.sigParameterUpdated.emit()
        return self.mw_power_stop

    def set_mw_power_num(self, mw_power_num):
        """ Set the number of mw powers for the Optimal Operation Point scan and 
        Bayesian optimization. 

        @param int mw_power_num: number of mw power points
        """
        if isinstance(mw_power_num, int):
            self.mw_power_num = mw_power_num
        self.sigParameterUpdated.emit()
        return self.mw_power_num

    def set_freq_start(self, freq_start):
        """ Set the minimum frequency for ODMR measurements. 

        @param float freq_start: starting frequency in Hz
        """
        limits = self.get_odmr_constraints()
        if isinstance(freq_start, (int, float)):
            self.freq_start = limits.frequency_in_range(freq_start)
        self.sigParameterUpdated.emit()
        return self.freq_start

    def set_freq_stop(self, freq_stop):
        """ Set the maximum frequency for ODMR measurements. 

        @param float freq_stop: stopping frequency in Hz
        """
        limits = self.get_odmr_constraints()
        if isinstance(freq_stop, (int, float)):
            if freq_stop < self.freq_start:
                freq_stop = self.freq_start
            self.freq_stop = limits.frequency_in_range(freq_stop)
        self.sigParameterUpdated.emit()
        return self.freq_stop

    def set_freq_num(self, freq_num):
        """ Set the number of points for ODMR measurements. 

        @param int freq_num: number of points
        """
        if isinstance(freq_num, int):
            self.freq_num = freq_num
        self.sigParameterUpdated.emit()
        return self.freq_num

    def set_counter_runtime(self, counter_runtime):
        """ Set the counter runtime for the saturation curve of the Optimal 
        Operation Point scan.

        @param float counter_runtime: runtime in s 
        """
        if isinstance(counter_runtime, (int, float)):
            self.counter_runtime = counter_runtime
        self.sigParameterUpdated.emit()
        return self.counter_runtime

    def set_odmr_runtime(self, odmr_runtime):
        """ Set the runtime for ODMR measurements. 

        @param float odmr_runtime: runtime in s
        """
        if isinstance(odmr_runtime, (int, float)):
            self.odmr_runtime = odmr_runtime
        self.sigParameterUpdated.emit()
        return self.odmr_runtime

    # FIXME: check whether the channel exists or not
    def set_channel(self, channel):
        """ Set the channel for ODMR measurements and saturation curve. 

        @param int channel: number of the channel (warning, channel are numbered
        from zero!)
        """
        odmr_channels = self.get_odmr_channels()
        num = len(odmr_channels)
        if isinstance(channel, int) and channel < num:
            self.channel = channel
            self.sigParameterUpdated.emit()
        else:
            self.log.error(
                'Channel must be an int inferior or equal to {0:d}'.format(num - 1))
        return self.channel

    def set_scan_optimize(self, boolean):
        """ Set whether or not to optimize the position during the scan.

        @param bool boolean
        """
        self.optimize = boolean
        self.sigParameterUpdated.emit()
        return self.optimize

    def set_odmr_fit(self, fit_name):
        """ Set the fit function used to fit the ODMR spectrum

        @param str fit_name: name of the fit
        """
        if fit_name in self.get_odmr_fits():
            self.odmr_fit_function = fit_name
        self.sigParameterUpdated.emit()
        return self.odmr_fit_function

    def set_bayopt_num_meas(self, num_meas):
        """ Set the number of measurement to be performed during Bayesian optimization

        @param int num_meas
        """
        self.bayopt_num_meas = num_meas
        self.sigParameterUpdated.emit()
        return self.bayopt_num_meas

    def set_bayopt_parameters(self, alpha, xi, percent):
        """ Set the hyperparameter used in the bayesian optimization algorithm.

        @param float alpha: noise level that can be handled by the Gaussian process
        @param float xi: exploration vs exploitation rate
        @param percent: percentage of random exploration

        See <https://github.com/fmfn/BayesianOptimization> for further explanation.
        """
        self.bayopt_alpha = alpha
        self.bayopt_xi = xi
        if percent > 100:
            percent = 100
        elif percent < 0:
            percent = 0
        self.bayopt_random_percentage = percent

    ###########################################################################
    #                  Optimal operation point scan methods                   #
    ###########################################################################

    def perform_OOP_scan(self, stabilization_time=1, **kwargs):
        """ Measure an ODMR spectrum for each combination of laser power and 
        microwave power. 

        @param float stabilization_time: waiting time added between function 
                                         call to avoid a crash of the program
        @param **kwargs: parameters of the measurement (e.g. laser_power_start, 
                         mw_power_num) can be passed as kwargs.

        The parameters of the measurement are defined in class attributes (e.g. 
        self.laser_power_start). For each laser power, count rate is first 
        recorded with no microwave power, in order to generate a saturation curve. 
        Then, for each microwave power, an ODMR spectrum is recorded and fitted 
        with the chosen fit function. The parameters of the fit defined in 
        self.fit_parameters_list are extracted and stored.
        """
        # If keyword arguments are passed to the function (e.g. laser_power_start)
        # it will call the associated setters.
        for param, value in kwargs.items():
            try:
                func = getattr(self, 'set_' + param)
            except AttributeError:
                self.log.error("perform_OOP_scan has no argument" + param)
            func(value)

        # Setting up the stopping mechanism.
        self._scan_stop_request = False

        self.sigScanStarted.emit()

        # A saturation curve is recorded during the scan, so update the saturation
        # parameters.
        self.set_saturation_params(self.laser_power_start, self.laser_power_stop,
                                   self.laser_power_num, self.counter_runtime)

        # Create the lists of powers for the measurement
        laser_power = np.linspace(
            self.laser_power_start, self.laser_power_stop, self.laser_power_num)
        mw_power = np.linspace(
            self.mw_power_start, self.mw_power_stop, self.mw_power_num)

        if self.get_laser_state() == LaserState.OFF:
            self.log.error('Measurement Aborted. Laser is not ON.')
            self.sigScanStopped.emit()
            return

        if self._counterlogic.module_state() == 'locked':
            self.log.error('Another measurement is running, stop it first!')
            self.sigScanStopped.emit()
            return

        # Deduce the number of points to request to counter from the parameter
        # self.counter_runtime
        count_frequency = self._counterlogic.get_count_frequency()
        counter_num_of_points = int(count_frequency * self.counter_runtime)
        freq_step = (self.freq_stop - self.freq_start) / (self.freq_num - 1)

        self._scan_data = self.initialize_scan_data()

        for i in range(len(laser_power)):

            # Stopping mechanism
            if self._scan_stop_request:
                break

            self.set_power(laser_power[i])

            time.sleep(stabilization_time)

            # Optimize the position
            if self.optimize:
                self.afm_scanner_logic().default_optimize()

            time.sleep(stabilization_time)

            # Record point for the saturation curve
            counts_array = self._counterlogic.request_counts(
                counter_num_of_points)[self.channel]

            # To avoid crash
            time.sleep(stabilization_time)

            # Saturation curve data
            counts = counts_array.mean()
            std_dev = counts_array.std(ddof=1)
            self._scan_data['saturation_data'][i] = counts
            self._scan_data['saturation_data_std'][i] = std_dev
            self.set_saturation_data(
                laser_power, self._scan_data['saturation_data'],
                self._scan_data['saturation_data_std'], i + 1)

            for j in range(len(mw_power)):

                # Stopping mechanism
                if self._scan_stop_request:
                    break

                # ODMR spectrum
                error, odmr_plot_x, odmr_plot_y, odmr_fit_result = self._odmr_logic.perform_odmr_measurement(
                    self.freq_start, freq_step, self.freq_stop, mw_power[
                        j], self.channel, self.odmr_runtime,
                    self.odmr_fit_function, save_after_meas=False, name_tag='')

                if error:
                    self.log.error(
                        'An error occured while recording ODMR. Scan aborted')
                    self.sigScanStopped.emit()
                    return

                odmr_plot_y = odmr_plot_y[self.channel, :]

                self._scan_data['odmr_data'][i][j] = odmr_plot_y
                self._scan_data['fit_results'][i][j] = odmr_fit_result
                self.update_fit_params(i, j)
                self.sigScanUpdateData.emit()

        self.set_power(self.final_power)

        self.sigScanStopped.emit()

    def initialize_scan_data(self):
        """ Initialize the dictionary where all the data of the Optimal Operation Point scan are stored.
        """

        meas_dict = {'odmr_data': np.zeros((self.laser_power_num, self.mw_power_num, self.freq_num)),
                     'saturation_data': np.zeros(self.laser_power_num),
                     'saturation_data_std': np.zeros(self.laser_power_num),
                     'fit_results': [[0] * self.mw_power_num for _ in range(self.laser_power_num)],
                     'fit_params': {},
                     'coord0_arr': np.linspace(self.laser_power_start, self.laser_power_stop, self.laser_power_num),
                     'coord1_arr': np.linspace(self.mw_power_start, self.mw_power_stop, self.mw_power_num),
                     'coord2_arr': np.linspace(self.freq_start, self.freq_stop, self.freq_num),
                     'units': 'c/s',
                     'nice_name': 'Fluorescence',
                     'params': {'Parameters for': 'Optimize operating point scan',
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
                                },
                     }

        if self.odmr_fit_function == 'No fit':
            self.log.warning(
                "No fit function has been chosen, no result will be displayed. Please choose a fit function")
            return

        available_fits = self._odmr_logic.fc.fit_list

        if self.odmr_fit_function not in available_fits:
            self.log.error(
                "The chosen fit function is unknown. Please chose another fit function.")
            return

        if not available_fits[self.odmr_fit_function]['fit_name'] in self.fit_parameters_list:
            self.log.error(
                "The selected fit function is not supported by this module. Please chose another fit function.")
            return

        fit_name = available_fits[self.odmr_fit_function]['fit_name']
        param_dict = self.fit_parameters_list[fit_name]

        # Initialize a dict where all the data to be displayed are stored as matrices
        for param_name in param_dict.keys():
            meas_dict['fit_params'][param_name] = {}
            meas_dict['fit_params'][param_name]['values'] = np.zeros(
                (self.laser_power_num, self.mw_power_num))
            meas_dict['fit_params'][param_name]['stderr'] = np.zeros(
                (self.laser_power_num, self.mw_power_num))
            meas_dict['fit_params'][param_name]['unit'] = param_dict[param_name][1]
        self.sigDataAvailableUpdated.emit(list(param_dict))

        self._scan_data = meas_dict

        return self._scan_data

    def update_fit_params(self, i, j):
        """ Update the values of the fit parameters for a given point of the scan.

        @param int i: index of the point along the laser power axis
        @param int j: index of the point along the microwave power axis

        The parameter of the fit (e.g. Contrast, FWHM) are taken from the fit 
        result object and stored in the dedicated matrix
        at the coordinates [i, j]. Same for the std of each parameter.
        """

        available_fits = self._odmr_logic.fc.fit_list

        if self.odmr_fit_function in available_fits \
                and available_fits[self.odmr_fit_function]['fit_name'] in self.fit_parameters_list:

            fit_name = available_fits[self.odmr_fit_function]['fit_name']
            # List of parameters of interest:
            param_dict = self.fit_parameters_list[fit_name]
            # Parameters of the fit:
            fit_params = self._scan_data['fit_results'][i][j].params
            # Whether the std has been calculated or not:
            is_error = self._scan_data['fit_results'][i][j].errorbars

            for param_name in param_dict.keys():
                param = param_dict[param_name][0]
                assert(param in fit_params), "The parameter {0} does not match \
                    any parameter of the fit. Please edit fit_parameters_list.".format(
                    param)
                # FIXME: The contrast has negative values. We take the absolute
                #  value of all the parameters for now.
                self._scan_data['fit_params'][param_name]['values'][i][j] = abs(
                    fit_params[param].value)
                if is_error:
                    self._scan_data['fit_params'][param_name]['stderr'][i][j] = fit_params[param].stderr

    ####################################
    #         Saving methods           #
    ####################################

    def save_scan_data(self, nametag):
        """ Save the data from the Optimal Operation Point scan to files and figures.
        The saturation curve is saved too. 
        """

        data = self._scan_data

        # check whether data has only zeros, skip this then
        if not 'odmr_data' in data or not np.any(data['odmr_data']):
            self.log.warning(
                'The data array contains only zeros and will be not saved.')
            return

        # Save saturation data
        self.do_fit()
        self.save_saturation_data(nametag)

        timestamp = datetime.datetime.now()

        if nametag is None:
            nametag = ''

        # Path and label to save the Saturation data
        filepath = self._save_logic.get_path_for_module(
            module_name='Optimal operating point scan')

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

        figure_data = data['odmr_data']

        rows, columns, entries = figure_data.shape

        image_data = {}
        # Reshape the image before sending out to save logic.
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

        # Another way to save the same data
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
        if self._scan_data['fit_params']:
            for param_name in self._scan_data['fit_params']:
                data_matrix, unit = self.get_scan_data(param_name)
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

                if 'stderr' in self._scan_data['fit_params'][param_name]:
                    std_matrix = self._scan_data['fit_params'][param_name]['stderr']
                    std_dict = {param_name +
                                ' Error (' + unit + ')': std_matrix}
                    std_filelabel = filelabel + '_' + param_name + '_stddev'
                    self._save_logic.save_data(std_dict, parameters=parameters,
                                               filepath=filepath,
                                               filelabel=std_filelabel,
                                               fmt='%.6e',
                                               delimiter='\t',
                                               timestamp=timestamp)

        self.log.info('ODMR data saved to:\n{0}'.format(filepath))

    def draw_matrix_figure(self, data_name):
        """ Draw the figure to save with the data.

        @param str data_name: the name of the parameter for which to draw the matrix.

        @return matplotlib.figure.Figure fig: a matplotlib figure object to be saved to file.
        """

        if data_name not in self._scan_data['fit_params']:
            fig = None
            return fig

        # Get the matrix and the unit and scale them
        matrix, unit = self.get_scan_data(data_name)
        scale_fact = units.ScaledFloat(np.max(matrix)).scale_val
        unit_prefix = units.ScaledFloat(np.max(matrix)).scale
        matrix_scaled = matrix / scale_fact
        unit_scaled = unit_prefix + unit
        # Define the color range for the colorbar
        matrix_scaled_nonzero = matrix_scaled[np.nonzero(matrix_scaled)]
        cb_min = np.percentile(matrix_scaled_nonzero, 5)
        cb_max = np.percentile(matrix_scaled_nonzero, 95)
        cbar_range = [cb_min, cb_max]

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure and draw matrix
        fig, (ax_matrix) = plt.subplots(nrows=1, ncols=1)
        matrixplot = ax_matrix.imshow(matrix_scaled,
                                      cmap=plt.get_cmap('viridis'),
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

    ########################################
    #          Start/stop functions        #
    ########################################

    def start_OOP_scan(self):
        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error(
                "A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.perform_OOP_scan,
                                           args=(),
                                           name='optimal_operation_point_scan')

        self.threadpool.start(self._worker_thread)

    def stop_OOP_scan(self):
        """ Set a flag to request stopping the OOP scan.
        """
        self._scan_stop_request = True

    ###########################################################################
    #                       Bayesian optimization methods                     #
    ###########################################################################

    def measure_sensitivity(self, laser_power, mw_power):
        """ Record an ODMR spectrum and fit it with the chosen function to 
        deduce the sensitivity.

        @param float laser_power: laser used for the measurement in Watt
        @param float mw_power: microwave power used for the measurement in dBm

        @return int error: -1 if a problem occured during the measurment, 0 otherwise
                float val: value of the sensitivity
                float std: std of the sensitivity
                np.ndarray odmr_plot_x: xaxis values of the odmr plot
                np.ndarra odmr_plot_y: yaxis values of the odmr plot
        """
        self.set_power(laser_power)
        time.sleep(1)

        freq_step = (self.freq_stop - self.freq_start) / (self.freq_num - 1)

        error, odmr_plot_x, odmr_plot_y, odmr_fit_result = self._odmr_logic.perform_odmr_measurement(
            self.freq_start, freq_step, self.freq_stop, mw_power, self.channel,
            self.odmr_runtime, self.odmr_fit_function, save_after_meas=False,
            name_tag='')

        if error:
            self.log.error('An error occured during ODMR measurement.')
            return error, 0, 0, np.array([]), np.array([])

        # Find the name of the sensitivity parameter
        fit_list = self._odmr_logic.fc.fit_list
        fit_name = fit_list[self.odmr_fit_function]['fit_name']
        param_dict = self.fit_parameters_list[fit_name]
        if 'Sensitivity' in param_dict:
            par = param_dict['Sensitivity'][0]
        elif 'Sensitivity 0' in param_dict:
            par = param_dict['Sensitivity 0'][0]
        else:
            self.log.error(
                "Sensitivity is not available from the fit chosen. Please choose \
                    another fit (e.g. Lorentzian dip)")
            error = -1
            return error, 0, 0, odmr_plot_x, odmr_plot_y

        # Check whether the stderr are computed
        is_error = odmr_fit_result.errorbars

        # Get the value of the sensitivity
        val = odmr_fit_result.params[par].value
        if is_error:
            std = odmr_fit_result.params[par].stderr
        else:
            std = -1

        return error, val, std, odmr_plot_x, odmr_plot_y

    def bayesian_optimization(self, resume=False):
        """ Execute a bayesian optimization algorithm to find the minimum of 
        sensitivity (optimal operation point).

        @param bool resume: whether to resume the last measurement or create a 
        new one.

        See <https://distill.pub/2020/bayesian-optimization/> if you want to 
        learn more about how bayesian optimization works.
        See <https://github.com/fmfn/BayesianOptimization> for information on 
        the library used.
        """
        # Sensitivity value should be multiplied by a negative factor because
        # the library used try to maximize the value instead of minimizing it.
        # Plus, the algorithm works better if the values are in the order of 1
        multiplication_factor = -1e5

        # Setting up the stopping mechanism.
        self._bayopt_stop_request = False
        self.sigBayoptStarted.emit()

        if self.get_laser_state() == LaserState.OFF:
            self.log.error('Measurement Aborted. Laser is not ON.')
            self.sigBayoptStopped.emit()
            return

        if self._counterlogic.module_state() == 'locked':
            self.log.error('Another measurement is running, stop it first!')
            self.sigBayoptStopped.emit()
            return

        self.initialize_optimizer()
        self.initialize_bayopt_data(resume)

        # If it resumes a measurement, load the data from the last measurement
        # into the optimizer
        old_num_points = np.count_nonzero(
            self._bayopt_data['measured_sensitivity'])
        for n in range(old_num_points):
            target = self._bayopt_data['measured_sensitivity'][n] * \
                multiplication_factor
            x = (self._bayopt_data['laser_power_list'][n] - self.laser_power_start) / (
                self.laser_power_stop - self.laser_power_start)
            y = (self._bayopt_data['mw_power_list'][n] - self.mw_power_start) / \
                (self.mw_power_stop - self.mw_power_start)
            self.optimizer.register(params={'x': x, 'y': y}, target=target)

        # Define the utility function (or acquiqition function)
        utility = UtilityFunction(kind='ei', xi=self.bayopt_xi, kappa=1)

        # How many steps of random exploration are performed
        init_points = int((self.bayopt_num_meas - old_num_points)
                          * self.bayopt_random_percentage / 100)

        for n in range(old_num_points, self.bayopt_num_meas):

            # Stopping mechanism
            if self._bayopt_stop_request:
                break

            # Choose next point to evaluate
            if n < old_num_points + init_points:
                x = np.random.random()
                y = np.random.random()
            else:
                try:
                    next_point = self.optimizer.suggest(utility)
                    x = next_point['x']
                    y = next_point['y']
                # catch a bug in the suggest function
                except ValueError:
                    x = np.random.random()
                    y = np.random.random()

            # Measure the sensitivity for this point
            las_pw = self.laser_power_start + \
                (self.laser_power_stop - self.laser_power_start) * x
            mw_pw = self.mw_power_start + \
                (self.mw_power_stop - self.mw_power_start) * y

            error, value, std, odmr_plot_x, odmr_plot_y = self.measure_sensitivity(
                las_pw, mw_pw)
            if error:
                self.log.error("Optimal operation point search aborted")
                self.sigBayoptStopped.emit()
                return

            target = value * multiplication_factor
            # Register the result into the optimizer
            self.optimizer.register(params={'x': x, 'y': y}, target=target)

            # Try to create a surrogate model + catch an error that happens when
            # there are not enough points for that
            try:
                self.optimizer._gp.fit(
                    self.optimizer._space.params, self.optimizer._space.target)
            except ValueError:
                pass

            # Store the data in the dedicated dict
            self._bayopt_data['measured_sensitivity'][n] = value
            self._bayopt_data['measured_sensitivity_std'][n] = std
            self._bayopt_data['laser_power_list'][n] = las_pw
            self._bayopt_data['mw_power_list'][n] = mw_pw
            self._bayopt_data['odmr_data'][n] = np.array(
                [odmr_plot_x, odmr_plot_y[self.channel]])
            # Prepare the plot that will be displayed
            X = np.linspace(0, 1, 100)
            Y = np.linspace(0, 1, 100)
            try:
                for i in range(100):
                    for j in range(100):
                        self._bayopt_data['predicted_sensitivity'][i][j] = float(
                            self.optimizer._gp.predict([[X[i], Y[j]]])) / multiplication_factor
            except AttributeError:
                pass
            self.sigBayoptUpdateData.emit(n)

        self.sigBayoptStopped.emit()

    def initialize_optimizer(self):
        """ Create an optimizer object for bayesian optimization.

        @return object: bayesian optimizer
        """
        pbounds = {'x': (0, 1), 'y': (0, 1)}
        self.optimizer = BayesianOptimization(
            f=None,
            pbounds=pbounds,
            verbose=0
        )
        self.optimizer.set_gp_params(alpha=self.bayopt_alpha)

        return self.optimizer

    def initialize_bayopt_data(self, resume=False):
        """" Initialize the dictionary where all the data of the bayesian 
        optimization are stored.

        @param bool resume: If True, re-load the data from the last measurement.
                            Default is False.
        """
        old_num_points = 0
        if resume:
            old_dict = self._bayopt_data
            old_num_points = np.count_nonzero(old_dict['measured_sensitivity'])
            # If there is no more point to measure, add a new one
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

        # Re-load the data
        for n in range(old_num_points):
            meas_dict['measured_sensitivity'][n] = old_dict['measured_sensitivity'][n]
            meas_dict['measured_sensitivity_std'][n] = old_dict['measured_sensitivity_std'][n]
            meas_dict['laser_power_list'][n] = old_dict['laser_power_list'][n]
            meas_dict['mw_power_list'][n] = old_dict['mw_power_list'][n]
            # FIXME: If the number of points for the odmr measurement has changed,
            # between the measurements, the old ones can not be stored in the new data array.
            if meas_dict['odmr_data'][n].shape == old_dict['odmr_data'][n].shape:
                meas_dict['odmr_data'][n] = old_dict['odmr_data'][n]

        self._bayopt_data = meas_dict
        return self._bayopt_data

    ####################################
    #         Saving methods           #
    ####################################

    def save_bayopt_data(self, tag=None):
        """ Save the data from Bayesian Optimization to files and figures.
        """

        timestamp = datetime.datetime.now()

        if tag is None:
            tag = ''

        # Path and label to save the Saturation data
        filepath = self._save_logic.get_path_for_module(
            module_name='Sensitivity optimization')

        if len(tag) > 0:
            filelabel = '{0}_measures'.format(tag)
        else:
            filelabel = 'measures'

        # Ensure that there are some data to be saved
        if not 'measured_sensitivity' in self._bayopt_data \
                or not np.any(self._bayopt_data['measured_sensitivity']):
            self.log.warning('The data array is empty and will be not saved.')
            return

        parameters = {}
        parameters.update(self._bayopt_data['params'])
        nice_name = self._bayopt_data['nice_name']
        unit = self._bayopt_data['units']
        parameters['Name of measured signal'] = nice_name
        parameters['Units of measured signal'] = unit

        n = np.count_nonzero(self._bayopt_data['measured_sensitivity'])
        index_min = np.argmin(self._bayopt_data['measured_sensitivity'][:n])
        min_mw_power = self._bayopt_data['mw_power_list'][index_min]
        min_laser_power = self._bayopt_data['laser_power_list'][index_min]
        parameters['Laser power of the minimum measured'] = min_laser_power
        parameters['MW power of the minimum measured'] = min_mw_power

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
        """ Draw the figure to save with the data.

        @return matplotlib.figure.Figure fig: a matplotlib figure object to be 
                                              saved to file.
        """
        # Matrix, unit and colorbar
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

        # Draw matrix
        matrixplot = ax_matrix.imshow(matrix_scaled,
                                      # reference the right place in qd
                                      cmap=plt.get_cmap('viridis'),
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

        # Draw measured points
        n = np.count_nonzero(self._bayopt_data['measured_sensitivity'])
        ax_matrix.plot(self._bayopt_data['mw_power_list'][:n],
                       self._bayopt_data['laser_power_list'][:n], linestyle='',
                       marker='o', color='cyan')

        # Draw a cross to indicate the minimum
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

    ################################################
    #      Start/stop bayesian optimization        #
    ################################################

    def start_bayopt(self):
        """ Starting a Threaded measurement.
        """
        if self.check_thread_active():
            self.log.error(
                "A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.bayesian_optimization,
                                           args=(),
                                           name='bayopt')

        self.threadpool.start(self._worker_thread)

    def stop_bayopt(self):
        """ Set a flag to request stopping the bayesian optimization.
        """
        self._bayopt_stop_request = True

    def resume_bayopt(self):
        """ Starting a Threaded measurement to resume the last measurement
        """
        if self.check_thread_active():
            self.log.error(
                "A measurement is currently running, stop it first!")
            return

        self._worker_thread = WorkerThread(target=self.bayesian_optimization,
                                           kwargs={'resume': True},
                                           name='bayopt')

        self.threadpool.start(self._worker_thread)
