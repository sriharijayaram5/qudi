# -*- coding: utf-8 -*-

"""
This file contains the Qudi Logic module base class.

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

from qtpy import QtCore
from collections import OrderedDict
from interface.microwave_interface import MicrowaveMode
from interface.microwave_interface import TriggerEdge
import numpy as np
import time
import datetime
import matplotlib.pyplot as plt

from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
from core.connector import Connector
from core.configoption import ConfigOption
from core.statusvariable import StatusVar

from optbayesexpt import OptBayesExpt
from numba import njit, float64
from PIL import Image
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

class ODMRLogic(GenericLogic):
    """This is the Logic class for ODMR."""

    # declare connectors
    odmrcounter = Connector(interface='ODMRCounterInterface')
    fitlogic = Connector(interface='FitLogic')
    microwave1 = Connector(interface='MicrowaveInterface')
    savelogic = Connector(interface='SaveLogic')
    taskrunner = Connector(interface='TaskRunner')

    clock_frequency = StatusVar('clock_frequency', 200)
    cw_mw_frequency = StatusVar('cw_mw_frequency', 2870e6)
    cw_mw_power = StatusVar('cw_mw_power', -30)
    fit_range = StatusVar('fit_range', 0)
    mw_starts = StatusVar('mw_starts', [2800e6])
    mw_stops = StatusVar('mw_stops', [2950e6])
    mw_steps = StatusVar('mw_steps', [2e6])
    run_time = StatusVar('run_time', 60)
    number_of_lines = StatusVar('number_of_lines', 50)
    ranges = StatusVar('ranges', 1)
    fc = StatusVar('fits', None)
    lines_to_average = StatusVar('lines_to_average', 0)
    _oversampling = StatusVar('oversampling', default=10)
    _lock_in_active = StatusVar('lock_in_active', default=False)

    # Internal signals
    sigNextLine = QtCore.Signal()

    # Update signals, e.g. for GUI module
    sigParameterUpdated = QtCore.Signal(dict)
    sigOutputStateUpdated = QtCore.Signal(str, bool)
    sigOdmrPlotsUpdated = QtCore.Signal(np.ndarray, np.ndarray)
    sigOdmrFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict, str)
    sigOdmrElapsedTimeUpdated = QtCore.Signal(float, int)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadlock = Mutex()

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        # Get connectors
        self._mw_device = self.microwave1()
        self._fit_logic = self.fitlogic()
        self._odmr_counter = self.odmrcounter()
        self._save_logic = self.savelogic()
        self._taskrunner = self.taskrunner()

        # Get hardware constraints
        limits = self.get_hw_constraints()

        # Set/recall microwave source parameters
        self.cw_mw_power = limits.power_in_range(self.cw_mw_power)

        # Elapsed measurement time and number of sweeps
        self.elapsed_time = 0.0
        self.elapsed_sweeps = 0
        self.fits_performed = {}

        self.frequency_lists = []
        self.final_freq_list = []
        # Set flags
        # for stopping a measurement
        self._stopRequested = False
        # for clearing the ODMR data during a measurement
        self._clearOdmrData = False
        self.opt_bay_params = None
        self.fit_dict = None
        self.optimum = False
        self.pickiness = 19

        # Initalize the ODMR data arrays (mean signal and sweep matrix)
        self.lines_to_average = 1
        if self.mw_starts == [] or self.mw_steps == [] or self.mw_stops == []:
           self.mw_starts = [2.86e9]
           self.mw_stops = [2.88e9]
           self.mw_steps = [500e3] 

        self._initialize_odmr_plots()
        # Raw data array
        # Switch off microwave and set CW frequency and power
        self.mw_off()
        self.fake_center = 1.87e9

        # Connect signals
        self.sigNextLine.connect(self._scan_odmr_line, QtCore.Qt.QueuedConnection)
        return

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        # Stop measurement if it is still running
        if self.module_state() == 'locked':
            self.stop_odmr_scan()
        timeout = 30.0
        start_time = time.time()
        while self.module_state() == 'locked':
            time.sleep(0.5)
            timeout -= (time.time() - start_time)
            if timeout <= 0.0:
                self.log.error('Failed to properly deactivate odmr logic. Odmr scan is still '
                               'running but can not be stopped after 30 sec.')
                break
        # Switch off microwave source for sure (also if CW mode is active or module is still locked)
        self._mw_device.off()
        # Disconnect signals
        self.sigNextLine.disconnect()

    @fc.constructor
    def sv_set_fits(self, val):
        # Setup fit container
        fc = self.fitlogic().make_fit_container('ODMR sum', '1d')
        fc.set_units(['Hz', 'c/s'])
        if isinstance(val, dict) and len(val) > 0:
            fc.load_from_dict(val)
        else:
            d1 = OrderedDict()
            d1['Lorentzian dip'] = {
                'fit_function': 'lorentzian',
                'estimator': 'dip'
            }
            d1['Two Lorentzian dips'] = {
                'fit_function': 'lorentziandouble',
                'estimator': 'dip'
            }
            d1['N14'] = {
                'fit_function': 'lorentziantriple',
                'estimator': 'N14'
            }
            d1['N15'] = {
                'fit_function': 'lorentziandouble',
                'estimator': 'N15'
            }
            d1['Two Gaussian dips'] = {
                'fit_function': 'gaussiandouble',
                'estimator': 'dip'
            }
            default_fits = OrderedDict()
            default_fits['1d'] = d1
            fc.load_from_dict(default_fits)
        return fc

    @fc.representer
    def sv_get_fits(self, val):
        """ save configured fits """
        if len(val.fit_list) > 0:
            return val.save_to_dict()
        else:
            return None

    def _initialize_odmr_plots(self):
        """ Initializing the ODMR plots (line and matrix). """

        final_freq_list = []
        self.frequency_lists = []
        for mw_start, mw_stop, mw_step in zip(self.mw_starts, self.mw_stops, self.mw_steps):
            freqs = np.arange(mw_start, mw_stop + mw_step, mw_step)
            final_freq_list.extend(freqs)
            self.frequency_lists.append(freqs)

        if type(self.final_freq_list) == list:
            self.final_freq_list = np.array(final_freq_list)

        self.odmr_plot_x = np.array(self.final_freq_list)
        self.odmr_plot_y = np.zeros(self.odmr_plot_x.size)

        self.odmr_fit_x = np.arange(self.mw_starts[0],
                                    self.mw_stops[0] + self.mw_steps[0],
                                    self.mw_steps[0])

        self.odmr_fit_y = np.zeros(self.odmr_fit_x.size)

        self.sigOdmrPlotsUpdated.emit(self.odmr_plot_x, self.odmr_plot_y)
        current_fit = self.fc.current_fit
        # self.sigOdmrFitUpdated.emit(self.odmr_fit_x, self.odmr_fit_y, {}, current_fit)
        return

    def set_trigger(self, trigger_pol, frequency):
        """
        Set trigger polarity of external microwave trigger (for list and sweep mode).

        @param object trigger_pol: one of [TriggerEdge.RISING, TriggerEdge.FALLING]
        @param float frequency: trigger frequency during ODMR scan

        @return object: actually set trigger polarity returned from hardware
        """
        return TriggerEdge.RISING

    def set_average_length(self, lines_to_average):
        """
        Sets the number of lines to average for the sum of the data

        @param int lines_to_average: desired number of lines to average (0 means all)

        @return int: actually set lines to average
        """
        self.lines_to_average = int(lines_to_average)

        self.sigParameterUpdated.emit({'average_length': self.lines_to_average})
        return self.lines_to_average 

    def set_clock_frequency(self, clock_frequency):
        """
        Sets the frequency of the counter clock

        @param int clock_frequency: desired frequency of the clock

        @return int: actually set clock frequency
        """
        # checks if scanner is still running
        if self.module_state() != 'locked' and isinstance(clock_frequency, (int, float)):
            self.clock_frequency = int(clock_frequency)
        else:
            self.log.warning('set_clock_frequency failed. Logic is either locked or input value is '
                             'no integer or float.')

        update_dict = {'clock_frequency': self.clock_frequency}
        self.sigParameterUpdated.emit(update_dict)
        return self.clock_frequency
    
    def set_opt_bay_settings(self, params):
        """
        Sets the frequency of the counter clock

        @param int clock_frequency: desired frequency of the clock

        @return int: actually set clock frequency
        """
        # checks if scanner is still running
        if self.module_state() != 'locked':
            self.opt_bay_params = params
        else:
            self.log.warning('set failed. Logic is  locked')

        return self.opt_bay_params

    @property
    def oversampling(self):
        return self._oversampling

    @oversampling.setter
    def oversampling(self, oversampling):
        """
        Sets the frequency of the counter clock

        @param int oversampling: desired oversampling per frequency step
        """
        # checks if scanner is still running
        if self.module_state() != 'locked' and isinstance(oversampling, (int, float)):
            self._oversampling = int(oversampling)
            self._odmr_counter.oversampling = self._oversampling
        else:
            self.log.warning('setter of oversampling failed. Logic is either locked or input value is '
                             'no integer or float.')

        update_dict = {'oversampling': self._oversampling}
        self.sigParameterUpdated.emit(update_dict)

    def set_oversampling(self, oversampling):
        self.oversampling = oversampling
        return self.oversampling

    @property
    def lock_in(self):
        return self._lock_in_active

    @lock_in.setter
    def lock_in(self, active):
        """
        Sets the frequency of the counter clock

        @param bool active: specify if signal should be detected with lock in
        """
        # checks if scanner is still running
        if self.module_state() != 'locked' and isinstance(active, bool):
            self._lock_in_active = active
            self._odmr_counter.lock_in_active = self._lock_in_active
        else:
            self.log.warning('setter of lock in failed. Logic is either locked or input value is no boolean.')

        update_dict = {'lock_in': self._lock_in_active}
        self.sigParameterUpdated.emit(update_dict)

    def set_lock_in(self, active):
        self.lock_in = active
        return self.lock_in

    def set_matrix_line_number(self, number_of_lines):
        """
        Sets the number of lines in the ODMR matrix

        @param int number_of_lines: desired number of matrix lines

        @return int: actually set number of matrix lines
        """
        return 0

    def set_runtime(self, runtime):
        """
        Sets the runtime for ODMR measurement

        @param float runtime: desired runtime in seconds

        @return float: actually set runtime in seconds
        """
        if isinstance(runtime, (int, float)):
            self.run_time = runtime
        else:
            self.log.warning('set_runtime failed. Input parameter runtime is no integer or float.')

        update_dict = {'run_time': self.run_time}
        self.sigParameterUpdated.emit(update_dict)
        return self.run_time

    def set_cw_parameters(self, power):
        """ Set the desired new cw mode parameters.

        @param float frequency: frequency to set in Hz
        @param float power: power to set in dBm

        @return (float, float): actually set frequency in Hz, actually set power in dBm
        """
        if self.module_state() != 'locked' and isinstance(power, (int, float)):
            constraints = self.get_hw_constraints()
            power_to_set = constraints.power_in_range(power)
        else:
            self.log.warning('set_cw_frequency failed. Logic is either locked or input value is '
                             'no integer or float.')

        return self.cw_mw_power

    def set_sweep_parameters(self, starts, stops, steps, power):
        """ Set the desired frequency parameters for list and sweep mode

        @param list starts: list of start frequencies to set in Hz
        @param list stops: list of stop frequencies to set in Hz
        @param list steps: list of step frequencies to set in Hz
        @param list power: mw power to set in dBm

        @return list, list, list, float: current start_freq, current stop_freq,
                                            current freq_step, current power
        """
        limits = self.get_hw_constraints()
        # as everytime all the elements are read when editing of a box is finished
        # also need to reset the lists in this case
        self.mw_starts = []
        self.mw_steps = []
        self.mw_stops = []

        if self.module_state() != 'locked':
            for start, step, stop in zip(starts, steps, stops):
                if isinstance(start, (int, float)):
                    self.mw_starts.append(limits.frequency_in_range(start))
                if isinstance(stop, (int, float)) and isinstance(step, (int, float)):
                    if stop <= start:
                        stop = start + step
                    self.mw_stops.append(limits.frequency_in_range(stop))
                    if limits.sweep_minstep < step:
                        self.mw_steps.append(step) 

            if isinstance(power, (int, float)):
                self.cw_mw_power = limits.power_in_range(power)
        else:
            self.log.warning('set_sweep_parameters failed. Logic is locked.')

        param_dict = {'mw_starts': self.mw_starts, 'mw_stops': self.mw_stops, 'mw_steps': self.mw_steps,
                      'sweep_mw_power': self.cw_mw_power}
        self.sigParameterUpdated.emit(param_dict)
        return self.mw_starts, self.mw_stops, self.mw_steps, self.cw_mw_power

    def mw_cw_on(self):
        """
        Switching on the mw source in cw mode.

        @return str, bool: active mode ['cw', 'list', 'sweep'], is_running
        """
        mode, is_running = self._mw_device.get_status()
        return mode, is_running

    def mw_sweep_on(self):
        """
        Switching on the mw source in list/sweep mode.

        @return str, bool: active mode ['cw', 'list', 'sweep'], is_running
        """
        mode, is_running = self._mw_device.get_status()
        self.sigOutputStateUpdated.emit(mode, is_running)
        return mode, is_running

    def reset_sweep(self):
        """
        Resets the list/sweep mode of the microwave source to the first frequency step.
        """

        return

    def mw_off(self):
        """ Switching off the MW source.

        @return str, bool: active mode ['cw', 'list', 'sweep'], is_running
        """
        error_code = self._mw_device.off()
        if error_code < 0:
            self.log.error('Switching off microwave source failed.')

        mode, is_running = self._mw_device.get_status()
        self.sigOutputStateUpdated.emit(mode, is_running)
        return mode, is_running

    def _start_odmr_counter(self):
        """
        Starting the ODMR counter and set up the clock for it.

        @return int: error code (0:OK, -1:error)
        """

        clock_status = self._odmr_counter.set_up_odmr_clock(clock_frequency=self.clock_frequency)

        if clock_status < 0:
            return -1

        counter_status = self._odmr_counter.set_up_odmr()
        if counter_status < 0:
            self._odmr_counter.close_odmr_clock()
            return -1

        return 0

    def _stop_odmr_counter(self):
        """
        Stopping the ODMR counter.

        @return int: error code (0:OK, -1:error)
        """

        ret_val1 = self._odmr_counter.close_odmr()
        if ret_val1 != 0:
            self.log.error('ODMR counter could not be stopped!')
        ret_val2 = self._odmr_counter.close_odmr_clock()
        if ret_val2 != 0:
            self.log.error('ODMR clock could not be stopped!')

        # Check with a bitwise or:
        return ret_val1 | ret_val2

    def start_odmr_scan(self):
        """ Starting an ODMR scan.

        @return int: error code (0:OK, -1:error)
        """
        with self.threadlock:
            if self.module_state() == 'locked':
                self.log.error('Can not start ODMR scan. Logic is already locked.')
                return -1

            self.module_state.lock()
            self._clearOdmrData = False
            self.stopRequested = False
            self.fc.clear_result()

            self.elapsed_sweeps = 0
            self.elapsed_time = 0.0
            self._startTime = time.time()
            self.sigOdmrElapsedTimeUpdated.emit(self.elapsed_time, self.elapsed_sweeps)

            odmr_status = self._start_odmr_counter()
            start, stop = (self.mw_starts[0], self.mw_stops[0])
            points = int((stop-start)/self.mw_steps[0])

            amp, background, background_noise, fwhm, self.err_margin_x0, self.err_margin_offset, self.err_margin_amp, n_samples = self.opt_bay_params['params']
            params = self.setup_obe(start, stop, points, amp, background, background_noise, fwhm/2, n_samples)

            my_model_function, settings, parameters, constants, scale, use_jit = params
            self.my_obe = OptBayesExpt(my_model_function, settings, parameters, constants, scale=scale, use_jit=use_jit)

            self.bay_x = []
            self.bay_y = []

            self.err = (np.inf, np.inf, np.inf)
            self.err_counter = 0
            
            if odmr_status < 0:
                mode, is_running = self._mw_device.get_status()
                self.sigOutputStateUpdated.emit(mode, is_running)
                self.module_state.unlock()
                return -1

            self._initialize_odmr_plots()
            self._odmr_counter.set_odmr_length(self.lines_to_average)
            self.sigNextLine.emit()
            return 0

    def continue_odmr_scan(self):
        """ Continue ODMR scan.

        @return int: error code (0:OK, -1:error)
        """
        with self.threadlock:
            if self.module_state() == 'locked':
                self.log.error('Can not start ODMR scan. Logic is already locked.')
                return -1

            self.module_state.lock()
            self.stopRequested = False
            self.fc.clear_result()

            self._startTime = time.time() - self.elapsed_time
            self.sigOdmrElapsedTimeUpdated.emit(self.elapsed_time, self.elapsed_sweeps)

            odmr_status = self._start_odmr_counter()
            if odmr_status < 0:
                mode, is_running = self._mw_device.get_status()
                self.sigOutputStateUpdated.emit(mode, is_running)
                self.module_state.unlock()
                return -1

            self.sigNextLine.emit()
            return 0

    def stop_odmr_scan(self):
        """ Stop the ODMR scan.

        @return int: error code (0:OK, -1:error)
        """
        with self.threadlock:
            if self.module_state() == 'locked':
                self.stopRequested = True
        return 0

    def clear_odmr_data(self):
        """¨Set the option to clear the curret ODMR data.

        The clear operation has to be performed within the method
        _scan_odmr_line. This method just sets the flag for that. """
        with self.threadlock:
            if self.module_state() == 'locked':
                self._clearOdmrData = True
        return

    def _scan_odmr_line(self):
        """ Scans one line in ODMR

        (from mw_start to mw_stop in steps of mw_step)
        """
        with self.threadlock:
            # If the odmr measurement is not running do nothing
            if self.module_state() != 'locked':
                return

            # Stop measurement if stop has been requested
            if self.stopRequested:
                self.stopRequested = False
                self.mw_off()
                self._stop_odmr_counter()
                self.module_state.unlock()
                return

            # if during the scan a clearing of the ODMR data is needed:
            if self._clearOdmrData:
                self.elapsed_sweeps = 0
                self._startTime = time.time()
                       
            if self.err[0]<self.err_margin_x0 and self.err[0]<self.err_margin_amp and self.err[0]<self.err_margin_offset:
                self.err_counter +=1
                if self.err_counter>5:
                    self.stopRequested = True
            try:
                if self.optimum:
                    xmeas = self.my_obe.opt_setting()
                else:
                    xmeas = self.my_obe.good_setting(pickiness = self.pickiness)
                
                xmeas_fail = xmeas
            except:
                xmeas = xmeas_fail
            self._mw_device.set_cw(xmeas[0], self.cw_mw_power)
            self._mw_device.cw_on()
            # Acquire count data
            error, new_counts = self._odmr_counter.count_odmr(length=self.lines_to_average)
        
            esr_meas = np.mean(new_counts)
            # Fake data
            fx = np.array([xmeas[0]])
            esr_meas = self.physical_lorentzian(x=fx, center=self.fake_center, sigma=7e6/2, amp=-30000, offset=100e3) + np.random.random()*5e3
            
            ymeasure = np.mean(esr_meas)
            noise = 5e3
            self.bay_x.append(xmeas[0])
            self.bay_y.append(ymeasure)

            measurement = (xmeas, ymeasure, noise)
            # self.log.debug(f'measurement {measurement}')
            
            # OptBayesExpt does Bayesian inference
            try:
                self.my_obe.pdf_update(measurement)
            except:
                self.log.warning(f'Opt Update maybe failed.')

            # OptBayesExpt provides statistics to track progress
            sigma = self.my_obe.std()
            err = sigma

            self.fit_dict = {'bay_x': self.bay_x,
                            'bay_y': self.bay_y,
                            'amp': self.opt_bay_params['params'][0],
                            'offset': self.opt_bay_params['params'][1],
                            'fwhm': self.opt_bay_params['params'][3]}

            if error:
                self.stopRequested = True
                self.sigNextLine.emit()
                return

            ind = np.argsort(np.asarray(self.bay_x))
            self.odmr_plot_x = np.asarray(self.bay_x)[ind].flatten()
            self.odmr_plot_y = np.asarray(self.bay_y)[ind].flatten()
            
            # Update elapsed time/sweeps
            self.elapsed_sweeps += 1
            self.elapsed_time = time.time() - self._startTime
            if self.elapsed_time >= self.run_time:
                self.stopRequested = True
            # Fire update signals
            self.sigOdmrElapsedTimeUpdated.emit(self.elapsed_time, self.elapsed_sweeps)
            self.sigOdmrPlotsUpdated.emit(self.odmr_plot_x, self.odmr_plot_y)
            self.sigNextLine.emit()
            return

    
    def setup_obe(self, start, stop, points, amp, background, background_noise, sigma, n_samples):
        
        #Lorentzian model for OptBay
        # @njit(cache=True)
        def my_model_function(sets, pars, cons):
            """ Evaluates a trusted model of the experiment's output

            The equivalent of a fit function. The argument structure is
            required by OptBayesExpt. In this example, the model function is a
            Lorentzian peak.

            Args:
                sets: A tuple of setting values, or a tuple of settings arrays
                pars: A tuple of parameter arrays or a tuple of parameter values
                cons: A tuple of floats

            Returns:  the evaluated function
            """
            # unpack the settings
            x, = sets
            # unpack model parameters
            x0, a, b = pars
            # unpack model constants
            d, = cons

            # calculate the Lorentzian
            return (np.power(d, 2) / (np.power((x0 - x), 2) + np.power(d, 2))) * a + b

        
        rng = np.random.default_rng() 
        ## Measurement loop: Quit measuring after ``n_measure`` measurement iterations
        # Define the allowed measurement settings
        #
        # 200 values between 1.5 and 4.5 (GHz)
        xvals = np.linspace(start, stop, points)
        # sets, pars, cons are all expected to be tuples
        settings = (xvals,)

        # Define the prior probability distribution of the parameters
        #
        # resonance center x0 -- a flat prior around 3 # times 100 for a better defined prob. dist

        x0_min, x0_max = (start, stop)
        x0_samples = rng.uniform(x0_min, x0_max, n_samples)
        # amplitude parameter a -- flat prior
        a_samples = rng.normal(amp, abs(amp/2), n_samples)
        # background parameter b -- a gaussian prior around 250000
        b_mean, b_sigma = (background, background_noise)
        b_samples = rng.normal(b_mean, abs(b_sigma), n_samples)
        # Pack the parameters into a tuple.
        # Note that the order must correspond to how the values are unpacked in
        # the model_function.
        parameters = (x0_samples, a_samples, b_samples)
        param_labels = ['Center', 'Amplitude', 'Background']
        # Define Constants
        #
        dtrue = sigma
        constants = (dtrue,)
        scale = False
        use_jit = False
        return my_model_function, settings, parameters, constants, scale, use_jit

    def physical_lorentzian(self, x, center, sigma, amp, offset):
        """ Function of a Lorentzian with unit height at center.

        @param numpy.array x: independent variable - e.g. frequency
        @param float center: center around which the distributions will be
        @param float sigma: half length at half maximum

        @return: numpy.array with length equals to input x and with the values
                of a lorentzian.
        """
        return (np.power(sigma, 2) / (np.power((center - x), 2) + np.power(sigma, 2))) * amp + offset
    
    def get_odmr_channels(self):
        return self._odmr_counter.get_odmr_channels()

    def get_hw_constraints(self):
        """ Return the names of all ocnfigured fit functions.
        @return object: Hardware constraints object
        """
        constraints = self._mw_device.get_limits()
        return constraints

    def get_fit_functions(self):
        """ Return the hardware constraints/limits
        @return list(str): list of fit function names
        """
        return list(self.fc.fit_list)

    def do_fit(self, fit_function=None, x_data=None, y_data=None, channel_index=0, fit_range=0):
        """
        Execute the currently configured fit on the measurement data. Optionally on passed data
        """

        x_data = self.odmr_plot_x
        y_data = self.odmr_plot_y
        if fit_function is not None and isinstance(fit_function, str):
            if fit_function in self.get_fit_functions():
                self.fc.set_current_fit(fit_function)
            else:
                self.fc.set_current_fit('No Fit')
                if fit_function != 'No Fit':
                    self.log.warning('Fit function "{0}" not available in ODMRLogic fit container.'
                                     ''.format(fit_function))

        if fit_function == 'Lorentzian dip' and self.fit_dict:
            mod,add_params = self.fitlogic().make_lorentzian_model()
            add_params['sigma'].set(value=self.fit_dict['fwhm']/2, vary=True, min=0)
            add_params['amplitude'].set(value=self.fit_dict['amp'], vary=True, max=0)
            add_params['offset'].set(value=self.fit_dict['offset'], vary=True, max=self.fit_dict['offset']*5) # maybe too arbitrary
            add_params['center'].set(value=self.odmr_plot_x[np.argmin(self.odmr_plot_y)], vary=True)
            self.fc.use_settings = add_params
        else:
            self.fc.use_settings = None

        self.odmr_fit_x, self.odmr_fit_y, result = self.fc.do_fit(x_data, y_data)
        key = 'channel: {0}, range: {1}'.format(channel_index, fit_range)
        if fit_function != 'No Fit':
            self.fits_performed[key] = (self.odmr_fit_x, self.odmr_fit_y, result, self.fc.current_fit)
        else:
            if key in self.fits_performed:
                self.fits_performed.pop(key)

        if result is None:
            result_str_dict = {}
        else:
            result_str_dict = result.result_str_dict
        self.sigOdmrFitUpdated.emit(
            self.odmr_fit_x, self.odmr_fit_y, result_str_dict, self.fc.current_fit)
        return

    def save_odmr_data(self, tag=None, colorscale_range=None, percentile_range=None):
        """ Saves the current ODMR data to a file."""
        timestamp = datetime.datetime.now()
        filepath = self._save_logic.get_path_for_module(module_name='ODMR')

        if tag is None:
            tag = ''

        for nch, channel in enumerate(self.get_odmr_channels()):
            # first save raw data for each channel
            if len(tag) > 0:
                filelabel_raw = '{0}_ODMR_data_ch{1}_raw'.format(tag, nch)
            else:
                filelabel_raw = 'ODMR_data_ch{0}_raw'.format(nch)

            data_raw = OrderedDict()
            data_raw['count data (counts/s)'] = self.odmr_raw_data[:self.elapsed_sweeps, nch, :]
            parameters = OrderedDict()
            parameters['Microwave Sweep Power (dBm)'] = self.cw_mw_power
            parameters['Run Time (s)'] = self.run_time
            parameters['Number of frequency sweeps (#)'] = self.elapsed_sweeps
            parameters['Start Frequencies (Hz)'] = self.mw_starts
            parameters['Stop Frequencies (Hz)'] = self.mw_stops
            parameters['Step sizes (Hz)'] = self.mw_steps
            parameters['Clock Frequencies (Hz)'] = self.clock_frequency
            parameters['Channel'] = '{0}: {1}'.format(nch, channel)
            self._save_logic.save_data(data_raw,
                                       filepath=filepath,
                                       parameters=parameters,
                                       filelabel=filelabel_raw,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       timestamp=timestamp)

            # now create a plot for each scan range
            data_start_ind = 0
            for ii, frequency_arr in enumerate(self.frequency_lists):
                if len(tag) > 0:
                    filelabel = '{0}_ODMR_data_ch{1}_range{2}'.format(tag, nch, ii)
                else:
                    filelabel = 'ODMR_data_ch{0}_range{1}'.format(nch, ii)

                # prepare the data in a dict or in an OrderedDict:
                data = OrderedDict()
                data['frequency (Hz)'] = frequency_arr

                num_points = len(frequency_arr)
                data_end_ind = data_start_ind + num_points
                data['count data (counts/s)'] = self.odmr_plot_y[nch][data_start_ind:data_end_ind]
                data_start_ind += num_points

                parameters = OrderedDict()
                parameters['Microwave Sweep Power (dBm)'] = self.cw_mw_power
                parameters['Run Time (s)'] = self.run_time
                parameters['Number of frequency sweeps (#)'] = self.elapsed_sweeps
                parameters['Start Frequency (Hz)'] = frequency_arr[0]
                parameters['Stop Frequency (Hz)'] = frequency_arr[-1]
                parameters['Step size (Hz)'] = frequency_arr[1] - frequency_arr[0]
                parameters['Clock Frequencies (Hz)'] = self.clock_frequency
                parameters['Channel'] = '{0}: {1}'.format(nch, channel)
                parameters['frequency range'] = str(ii)

                key = 'channel: {0}, range: {1}'.format(nch, ii)
                if key in self.fits_performed.keys():
                    parameters['Fit function'] = self.fits_performed[key][3]
                    for name, param in self.fits_performed[key][2].params.items():
                        parameters[name] = str(param)
                # add all fit parameter to the saved data:

                fig = self.draw_figure(nch, ii,
                                       cbar_range=colorscale_range,
                                       percentile_range=percentile_range)

                self._save_logic.save_data(data,
                                           filepath=filepath,
                                           parameters=parameters,
                                           filelabel=filelabel,
                                           fmt='%.6e',
                                           delimiter='\t',
                                           timestamp=timestamp,
                                           plotfig=fig)

        self.log.info('ODMR data saved to:\n{0}'.format(filepath))
        return

    def draw_figure(self, channel_number, freq_range, cbar_range=None, percentile_range=None):
        """ Draw the summary figure to save with the data.

        @param: list cbar_range: (optional) [color_scale_min, color_scale_max].
                                 If not supplied then a default of data_min to data_max
                                 will be used.

        @param: list percentile_range: (optional) Percentile range of the chosen cbar_range.

        @return: fig fig: a matplotlib figure object to be saved to file.
        """
        key = 'channel: {0}, range: {1}'.format(channel_number, freq_range)
        freq_data = self.frequency_lists[freq_range]
        lengths = [len(freq_range) for freq_range in self.frequency_lists]
        cumulative_sum = list()
        tmp_val = 0
        cumulative_sum.append(tmp_val)
        for length in lengths:
            tmp_val += length
            cumulative_sum.append(tmp_val)

        ind_start = cumulative_sum[freq_range]
        ind_end = cumulative_sum[freq_range + 1]
        count_data = self.odmr_plot_y[channel_number][ind_start:ind_end]
        fit_freq_vals = self.frequency_lists[freq_range]
        if key in self.fits_performed:
            fit_count_vals = self.fits_performed[key][2].eval()
        else:
            fit_count_vals = 0.0
        
        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, (ax_mean, ax_matrix) = plt.subplots(nrows=2, ncols=1)

        ax_mean.plot(freq_data, count_data, linestyle=':', linewidth=0.5)

        # Do not include fit curve if there is no fit calculated.
        if hasattr(fit_count_vals, '__len__'):
            ax_mean.plot(fit_freq_vals, fit_count_vals, marker='None')

      
        # Adjust subplots to make room for colorbar
        fig.subplots_adjust(right=0.8)

        return fig

    def select_odmr_matrix_data(self, odmr_matrix, nch, freq_range):
        odmr_matrix_dp = odmr_matrix[:, nch]
        x_data = self.frequency_lists[freq_range]
        x_data_full_length = np.zeros(len(self.final_freq_list))
        mw_starts = [freq_arr[0] for freq_arr in self.frequency_lists]
        start_pos = np.where(np.isclose(self.final_freq_list,
                                        mw_starts[freq_range]))[0][0]
        x_data_full_length[start_pos:(start_pos + len(x_data))] = x_data
        y_args = np.array([ind_list[0] for ind_list in np.argwhere(x_data_full_length)])
        odmr_matrix_range = odmr_matrix_dp[:, y_args]
        return odmr_matrix_range

    def perform_odmr_measurement(self, freq_start, freq_step, freq_stop, power, channel, runtime,
                                 fit_function='No Fit', save_after_meas=True, name_tag=''):
        """ An independant method, which can be called by a task with the proper input values
            to perform an odmr measurement.

        @return
        """
        timeout = 30
        start_time = time.time()
        while self.module_state() != 'idle':
            time.sleep(0.5)
            timeout -= (time.time() - start_time)
            if timeout <= 0:
                self.log.error('perform_odmr_measurement failed. Logic module was still locked '
                               'and 30 sec timeout has been reached.')
                return tuple()

        # set all relevant parameter:
        self.set_sweep_parameters(freq_start, freq_stop, freq_step, power)
        self.set_runtime(runtime)

        # start the scan
        self.start_odmr_scan()

        # wait until the scan has started
        while self.module_state() != 'locked':
            time.sleep(1)
        # wait until the scan has finished
        while self.module_state() == 'locked':
            time.sleep(1)

        # Perform fit if requested
        if fit_function != 'No Fit':
            self.do_fit(fit_function, channel_index=channel)
            fit_params = self.fc.current_fit_param
        else:
            fit_params = None

        # Save data if requested
        if save_after_meas:
            self.save_odmr_data(tag=name_tag)

        return self.odmr_plot_x, self.odmr_plot_y, fit_params
