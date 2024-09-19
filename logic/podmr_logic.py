
"""
-*- coding: utf-8 -*-
2024-01-30 created by Sreehari Jayaram and Malik Lenger
This modul runs a PODMR measurement based on the following MW path setup:
1. Local Osciallator connected to an IQ mixer for frequency sweeping
2. AWG as master of the measurement. Analog outputs are connected to the I and Q ports of the IQ mixer and device which sweeps the frequency.
    It also takes care of the main Trigger events of other devices like the pulsestreamer.
3. Pulsestreamer takes over the read out part. Thus, it gets triggered by the AWG and is connected to the laser and the Timetagger.
"""
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
from core.util import units
from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
from core.connector import Connector
from core.configoption import ConfigOption
from core.statusvariable import StatusVar
from interface.simple_pulse_objects import PulseBlock, PulseSequence
from logic.pulsed.sampling_functions import SamplingFunctions as SF
import logic.pulsed.pulse_objects as po
import os

class ODMRLogic(GenericLogic):
    """This is the Logic class for ODMR."""

    # declare connectors
    odmrcounter = Connector(interface='ODMRCounterInterface')
    fitlogic = Connector(interface='FitLogic')
    microwave1 = Connector(interface='MicrowaveInterface')
    savelogic = Connector(interface='SaveLogic')
    taskrunner = Connector(interface='TaskRunner')
    pulsed_master_AWG = Connector(interface='PulsedMasterLogic')
    pulse_creator = Connector(interface='GenericLogic')

    sweep_mw_power = StatusVar('sweep_mw_power', -20)
    laser_power_voltage = StatusVar('laser_power_voltage_podmr',0.5)
    fit_range = StatusVar('fit_range', 0)
    mw_starts = StatusVar('mw_starts', [2800e6])
    mw_stops = StatusVar('mw_stops', [2950e6])
    mw_steps = StatusVar('mw_steps', [2e6])
    number_of_lines = StatusVar('number_of_lines', 50)
    ranges = StatusVar('ranges', 1)
    fc = StatusVar('fits', None)
    lines_to_average = StatusVar('lines_to_average', 0)
    _lock_in_active = StatusVar('lock_in_active', default=False)
    pulsed_analysis_settings = StatusVar('pulsed_analysis_settings', default={'signal_start': 0,
                                                                                'signal_end': 0,
                                                                                'norm_start': 0,
                                                                                'norm_end': 0})

    # Internal signals
    sigNextLine = QtCore.Signal()

    # Update signals, e.g. for GUI module
    sigParameterUpdated = QtCore.Signal(dict)
    sigOutputStateUpdated = QtCore.Signal(str, bool)
    sigOdmrPlotsUpdated = QtCore.Signal(np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    sigOdmrLaserDataUpdated = QtCore.Signal(object)
    sigOdmrFitUpdated = QtCore.Signal(np.ndarray, np.ndarray, dict, str)
    sigOdmrElapsedTimeUpdated = QtCore.Signal(float, str)
    sigAnalysisSettingsUpdated = QtCore.Signal(dict)

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
        self._pulsed_master_AWG = self.pulsed_master_AWG()
        self._pulse_creator = self.pulse_creator()

        # Get hardware constraints
        limits = self.get_hw_constraints()

        # Set/recall microwave source parameters
        self.sweep_mw_power = limits.power_in_range(self.sweep_mw_power)

        if self.laser_power_voltage > 1:
            self.laser_power_voltage = 1
        elif self.laser_power_voltage < 0:
            self.laser_power_voltage = 0
        else:
            self.laser_power_voltage = self.laser_power_voltage

        self._odmr_counter.lock_in_active = self._lock_in_active

        # Elapsed measurement time and number of sweeps
        self.elapsed_time = 0.0
        self.elapsed_sweeps = 0

        self.range_to_fit = 0
        self.matrix_range = 0
        self.fits_performed = {}

        self.frequency_lists = []
        self.final_freq_list = []

        self.bin_width_s = 1e-9
        self.record_length_s = 3e-6

        # Set flags
        # for stopping a measurement
        self._stopRequested = False
        # for clearing the ODMR data during a measurement
        self._clearOdmrData = False

        # Initalize the ODMR data arrays (mean signal and sweep matrix)
        
        self.sigAnalysisSettingsUpdated.emit(self.pulsed_analysis_settings)
        # Raw data array
        

        # Switch off microwave and set CW frequency and power
        self.mw_off()

        # Connect signals
        self.sigNextLine.connect(self._scan_odmr_line, QtCore.Qt.QueuedConnection)
        self.sigNextLineTimer = QtCore.QTimer()
        self.sigNextLineTimer.timeout.connect(self._scan_odmr_line)
        self._initialize_odmr_plots()
        self.odmr_raw_data = np.zeros(
            [self.odmr_plot_x.size,
             int(self.record_length_s/self.bin_width_s),
             ]
        )
        self.vis_slope = 0
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
        self.sigNextLineTimer.stop()

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
        self.odmr_plot_y = np.zeros([len(self.get_odmr_channels()), self.odmr_plot_x.size])

        self.odmr_plot_xy = np.zeros(
            [self.number_of_lines, len(self.get_odmr_channels()), self.odmr_plot_x.size])

        range_to_fit = self.range_to_fit

        self.odmr_fit_x = np.arange(self.mw_starts[range_to_fit],
                                    self.mw_stops[range_to_fit] + self.mw_steps[range_to_fit],
                                    self.mw_steps[range_to_fit])

        self.odmr_fit_y = np.zeros(self.odmr_fit_x.size)

        self.sigOdmrPlotsUpdated.emit(self.odmr_plot_x, self.odmr_plot_y, np.array([np.nan]), np.zeros_like(self.odmr_plot_y[0]))
        self.laser_data = np.zeros((1,int(self.record_length_s/self.bin_width_s)))
        self.sigOdmrLaserDataUpdated.emit(self.laser_data)
        current_fit = self.fc.current_fit
        self.sigOdmrFitUpdated.emit(self.odmr_fit_x, self.odmr_fit_y, {}, current_fit)
        return

    def set_average_length(self, lines_to_average):
        """
        Sets the number of lines to average for the sum of the data

        @param int lines_to_average: desired number of lines to average (0 means all)

        @return int: actually set lines to average
        """
        self.lines_to_average = int(lines_to_average)
        self.sigParameterUpdated.emit({'average_length': self.lines_to_average})
        return self.lines_to_average
   
    def set_sweep_parameters(self, starts, stops, steps, power, laser_power_voltage):
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
                    self.mw_steps.append(limits.sweep_step_in_range(step))

            if isinstance(power, (int, float)):
                self.sweep_mw_power = limits.power_in_range(power)

            if isinstance(laser_power_voltage, (int, float)):
                if laser_power_voltage > 1:
                    self.laser_power_voltage = 1
                elif laser_power_voltage < 0:
                    self.laser_power_voltage = 0
                else:
                    self.laser_power_voltage = laser_power_voltage
                    self._pulse_creator.pulser._pulsed_laser_power_voltage = laser_power_voltage

        else:
            self.log.warning('set_sweep_parameters failed. Logic is locked.')

        param_dict = {'mw_starts': self.mw_starts, 'mw_stops': self.mw_stops, 'mw_steps': self.mw_steps,
                      'sweep_mw_power': self.sweep_mw_power, 'laser_power_voltage': self.laser_power_voltage}
        self.sigParameterUpdated.emit(param_dict)
        return self.mw_starts, self.mw_stops, self.mw_steps, self.sweep_mw_power, self.laser_power_voltage

    def mw_sweep_on(self):
        
        limits = self.get_hw_constraints()

        if self.ranges == 1:
            mw_stop = self.mw_stops[0]
            mw_step = self.mw_steps[0]
            mw_start = self.mw_starts[0]

            if np.abs(mw_stop - mw_start) / mw_step >= limits.sweep_maxentries:
                self.log.warning('Number of frequency steps too large for microwave device. '
                                    'Lowering resolution to fit the maximum length.')
                mw_step = np.abs(mw_stop - mw_start) / (limits.list_maxentries - 1)
                self.sigParameterUpdated.emit({'mw_steps': [mw_step]})

            var_list, self.sweep_mw_power = self.set_AWG_sweep(
                mw_start, mw_stop, mw_step, self.sweep_mw_power)

            param_dict = {'mw_starts': [var_list[0]], 'mw_stops': [var_list[-1]],
                            'mw_steps': [var_list[1]-var_list[0]], 'sweep_mw_power': self.sweep_mw_power, 'laser_power_voltage': self.laser_power_voltage}
            self.final_freq_list = var_list
            self.log.debug(f'{self.final_freq_list}')
        else:
            self.log.error('sweep mode only works for one frequency range.')

        self.sigParameterUpdated.emit(param_dict)

        err_code = self._mw_device.cw_on()
        if err_code < 0:
            self.log.error('Activation of microwave output failed.')

        mode, is_running = self._mw_device.get_status()
        self.sigOutputStateUpdated.emit(mode, is_running)
        return mode, is_running

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

    def _start_odmr_counter(self, laser_pulses):
        """
        Starting the ODMR counter and set up the clock for it.

        @return int: error code (0:OK, -1:error)
        """

        # TODO make it a variabe

        ret_val = self._odmr_counter._sc_device.configure_recorder(
                        mode=11, # pulsed mode
                        params={'laser_pulses': laser_pulses,
                                'bin_width_s': self.bin_width_s,
                                'record_length_s': self.record_length_s,
                                'max_counts': 0 } )

        self._odmr_counter._sc_device.start_recorder(arm=True)

        return 0

    def _stop_odmr_counter(self):
        """
        Stopping the ODMR counter.

        @return int: error code (0:OK, -1:error)
        """
        return 0

    def start_odmr_scan(self):
        """ Starting an ODMR scan.

        @return int: error code (0:OK, -1:error)
        """
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
        self.sigOdmrElapsedTimeUpdated.emit(self.elapsed_time, str(self.elapsed_sweeps))

        self.mw_sweep_on() #Contains the setup of the pulsestreamer and the AWG
        laser_pulses = len(self.final_freq_list)
        self._start_odmr_counter(laser_pulses) #Timetagger setup

        self._initialize_odmr_plots()

        if self.module_state() != 'locked':
            return

        self._pulsed_master_AWG.toggle_pulse_generator(True)

        # initialize raw_data array
        self.odmr_raw_data = np.zeros(
            [self.odmr_plot_x.size,
             int(self.record_length_s/self.bin_width_s),
             ])

        self.sigNextLineTimer.start(1000)

    def stop_odmr_scan(self):
        """ Stop the ODMR scan.

        @return int: error code (0:OK, -1:error)
        """
        if self.module_state() == 'locked':
            self.stopRequested = True
            self.sigNextLineTimer.stop()
            self._odmr_counter._pulser.pulser_off()
            self._pulsed_master_AWG.toggle_pulse_generator(False)
            self.mw_off()
            self.module_state.unlock()
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
        # If the odmr measurement is not running do nothing
        if self.module_state() != 'locked':
            return
        
        if self.stopRequested:
            self.stopRequested = False
            self.sigNextLineTimer.stop()
            self.mw_off()
            self._stop_odmr_counter()
            self._odmr_counter._pulser.pulser_off()
            self._pulsed_master_AWG.toggle_pulse_generator(False)
            self.module_state.unlock()
            return
            
        # Acquire count data
        self.laser_data = self._odmr_counter._sc_device.get_measurements()[0]
        self.analyse_pulsed_meas(self.pulsed_analysis_settings, self.laser_data)

        # Update elapsed time/sweeps
        self.elapsed_sweeps = self._odmr_counter._sc_device.recorder.getCounts()
        self.elapsed_time = time.time() - self._startTime
        if self.elapsed_sweeps >= self.lines_to_average and self.lines_to_average!=0:
            self.stopRequested = True
        # Fire update signals
        self.sigOdmrElapsedTimeUpdated.emit(self.elapsed_time, f'{self.elapsed_sweeps}')


        return

    def get_odmr_channels(self):
        return self._odmr_counter.get_odmr_channels()

    def get_hw_constraints(self):
        """ Return the names of all ocnfigured fit functions.
        @return object: Hardware constraints object
        """
        constraints = self._mw_device.get_limits()
        return constraints

    def set_AWG_sweep(self, mw_start, mw_stop, mw_step, sweep_mw_power, pi_pulse=None):
        """
        Sets up the AWG sweep, the pulsestreamer and the MW Source CW . The AWG is the master.
        """
        # upload the IQ signal for + and - delta frequencies. Should be triggerable. Only the CW MW will change during scan
        pp = pi_pulse if not pi_pulse == None else self.pi_length_pulse

        num_steps = int(np.rint((mw_stop - mw_start) / mw_step))
        end_freq = mw_start + num_steps * mw_step
        var_range =  end_freq-mw_start
        var_list = np.linspace(mw_start, end_freq, num_steps + 1)
        name = f'podmr-({var_range},{mw_step},{pp})'
        check_name = 'Jupyter-ensemble-'+name
        cw_freq = end_freq + 100e6

        if len(self._pulse_creator.AWG._current_uploaded_ensembles) == 1 and check_name in self._pulse_creator.AWG._current_uploaded_ensembles:
            self._pulse_creator.initialize_ensemble(laser_power_voltage = self.laser_power_voltage, pi_pulse = pp, read_out_time = self.record_length_s, LO_freq_0 = cw_freq, target_freq_0 = mw_start, power_0 = sweep_mw_power, printing = False, set_up_measurement = False)
            self._pulse_creator.sample_load_ready_pulsestreamer(name='read_out_jptr')

        elif check_name in self._pulsed_master_AWG.sequencegeneratorlogic()._saved_pulse_block_ensembles.keys():
            self._pulse_creator.initialize_ensemble(laser_power_voltage = self.laser_power_voltage, pi_pulse = pp, read_out_time = self.record_length_s, LO_freq_0 = cw_freq, target_freq_0 = mw_start, power_0 = sweep_mw_power, printing = False, set_up_measurement = False)
            ensemble_list = [check_name]
            sequence_step_list = []
            for idx, ensemble in enumerate(ensemble_list):
                step = {"step_index" : idx,
                        "step_segment" : ensemble,
                        "step_loops" : 1,
                        "next_step_index" : idx+1 if idx<len(ensemble_list)-1 else 0,
                        "step_end_cond" : 'always'
                        }
                sequence_step_list.append(step)
            self._pulse_creator.AWG_MW_reset()
            self._pulse_creator.AWG.load_ready_sequence_mode(sequence_step_list)
            self._pulse_creator.sample_load_ready_pulsestreamer(name='read_out_jptr')
            
        else:
            self._pulse_creator.initialize_ensemble(laser_power_voltage = self.laser_power_voltage, pi_pulse = pp, read_out_time = self.record_length_s, LO_freq_0 = cw_freq, target_freq_0 = mw_start, power_0 = sweep_mw_power, printing = False, set_up_measurement = False)
            ensemble_list, sequence_step_list, name, var_list, alternating, freq_sweep = self._pulse_creator.PODMR(mw_start, mw_stop, mw_step, name) #Preparing Pulsestreamer and AWG without setting up the pulse measurement GUI or Timetagger

        self._mw_device.set_cw(cw_freq, sweep_mw_power)

        return var_list, sweep_mw_power

    def analyse_pulsed_meas(self, analysis_settings, pulsed_meas):

        analysis_method = self.analyse_mean_norm_new
        args = [pulsed_meas, analysis_settings['signal_start'], analysis_settings['signal_end'], analysis_settings['norm_start'], analysis_settings['norm_end']]
           
        try:
            data, err, ref_data, ref_time = analysis_method(*args)
        except:
            self.log.warning('Something went wrong with the laser data. Run measurement again.')
            return (0,0)

        # shift data in the array "up" and add new data at the "bottom"
        self.odmr_raw_data = pulsed_meas

        self.odmr_plot_y = data.reshape(1, len(data))
        self.odmr_plot_y_err = err
        self.sigOdmrLaserDataUpdated.emit(self.laser_data)
        self.sigOdmrPlotsUpdated.emit(self.odmr_plot_x, self.odmr_plot_y, self.odmr_plot_xy, self.odmr_plot_y_err)
      
        return (data, err)
    
    def analyse_mean_norm(self, laser_data, signal_start=0.0, signal_end=200e-9, norm_start=300e-9,
                          norm_end=500e-9):
        """

        @param laser_data:
        @param signal_start:
        @param signal_end:
        @param norm_start:
        @param norm_end:
        @return:
        """
        # Get number of lasers
        num_of_lasers = laser_data.shape[0]
        # Get counter bin width
        bin_width = self.bin_width_s

        if not isinstance(bin_width, float):
            return np.zeros(num_of_lasers), np.zeros(num_of_lasers)

        # Convert the times in seconds to bins (i.e. array indices)
        signal_start_bin = round(signal_start / bin_width)
        signal_end_bin = round(signal_end / bin_width)
        norm_start_bin = round(norm_start / bin_width)
        norm_end_bin = round(norm_end / bin_width)

        # initialize data arrays for signal and measurement error
        signal_data = np.empty(num_of_lasers, dtype=float)
        error_data = np.empty(num_of_lasers, dtype=float)

        # loop over all laser pulses and analyze them
        for ii, laser_arr in enumerate(laser_data):
            # calculate the sum and mean of the data in the normalization window
            tmp_data = laser_arr[norm_start_bin:norm_end_bin]
            reference_sum = np.sum(tmp_data)
            reference_mean = (reference_sum / len(tmp_data)) if len(tmp_data) != 0 else 0.0

            # calculate the sum and mean of the data in the signal window
            tmp_data = laser_arr[signal_start_bin:signal_end_bin]
            signal_sum = np.sum(tmp_data)
            signal_mean = (signal_sum / len(tmp_data)) if len(tmp_data) != 0 else 0.0

            # Calculate normalized signal while avoiding division by zero
            if reference_mean > 0 and signal_mean >= 0:
                signal_data[ii] = signal_mean / reference_mean
            else:
                signal_data[ii] = 0.0

            # Calculate measurement error while avoiding division by zero
            if reference_sum > 0 and signal_sum > 0:
                # calculate with respect to gaussian error 'evolution'
                error_data[ii] = signal_data[ii] * np.sqrt(1 / signal_sum + 1 / reference_sum)
            else:
                error_data[ii] = 0.0

        return signal_data, error_data
    
    def analyse_mean_norm_new(self, laser_data, signal_start=0.0, signal_end=200e-9, norm_start=300e-9,
                          norm_end=500e-9):
        """

        @param laser_data:
        @param signal_start:
        @param signal_end:
        @param norm_start:
        @param norm_end:
        @return:
        """
        # Get number of lasers
        num_of_lasers = laser_data.shape[0]
        # Get counter bin width
        bin_width = self.bin_width_s

        if not isinstance(bin_width, float):
            return np.zeros(num_of_lasers), np.zeros(num_of_lasers)

        # Convert the times in seconds to bins (i.e. array indices)
        signal_start_bin = round(signal_start / bin_width)
        signal_end_bin = round(signal_end / bin_width)
        norm_start_bin = round(norm_start / bin_width)
        norm_end_bin = round(norm_end / bin_width)

        # loop over all laser pulses and analyze them
        tmp_ref = laser_data[:,norm_start_bin:norm_end_bin]
        tmp_signal = laser_data[:,signal_start_bin:signal_end_bin]
        if np.count_nonzero(tmp_signal):
            signal_data = np.mean(tmp_signal, axis=1)/np.mean(tmp_ref, axis=1)
            ref_data = np.sum(tmp_ref, axis=1)
            error_data = signal_data * np.sqrt(1/np.sum(tmp_signal, axis=1) + 1/np.sum(tmp_ref, axis=1))
        else:
            signal_data = np.zeros(num_of_lasers)
            error_data = np.zeros(num_of_lasers)
            ref_data = np.zeros(num_of_lasers)
        ref_time = (norm_end_bin*bin_width-norm_start_bin*bin_width)
        return signal_data, error_data, ref_data, ref_time
    
    def get_fit_functions(self):
        """ Return the hardware constraints/limits
        @return list(str): list of fit function names
        """
        return list(self.fc.fit_list)

    def do_fit(self, fit_function=None, x_data=None, y_data=None, channel_index=0, fit_range=0):
        """
        Execute the currently configured fit on the measurement data. Optionally on passed data
        """
        if (x_data is None) or (y_data is None):
            if fit_range >= 0:
                x_data = self.frequency_lists[fit_range]
                x_data_full_length = np.zeros(len(self.final_freq_list))
                # how to insert the data at the right position?
                start_pos = np.where(np.isclose(self.final_freq_list, self.mw_starts[fit_range]))[0][0]
                x_data_full_length[start_pos:(start_pos + len(x_data))] = x_data
                y_args = np.array([ind_list[0] for ind_list in np.argwhere(x_data_full_length)])
                y_data = self.odmr_plot_y[channel_index][y_args]
            else:
                x_data = self.final_freq_list
                y_data = self.odmr_plot_y[channel_index]
        if fit_function is not None and isinstance(fit_function, str):
            if fit_function in self.get_fit_functions():
                self.fc.set_current_fit(fit_function)
            else:
                self.fc.set_current_fit('No Fit')
                if fit_function != 'No Fit':
                    self.log.warning('Fit function "{0}" not available in ODMRLogic fit container.'
                                     ''.format(fit_function))

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
        filepath = self._save_logic.get_path_for_module(module_name='PODMR')

        if tag is None:
            tag = ''

        for nch, channel in enumerate(self.get_odmr_channels()):
            # first save raw data for each channel
            if len(tag) > 0:
                filelabel_raw = '{0}_ODMR_data_ch{1}_raw'.format(tag, nch)
            else:
                filelabel_raw = 'ODMR_data_ch{0}_raw'.format(nch)

            data_raw = OrderedDict()
            data_raw['count data (count events)'] = self.odmr_raw_data
            parameters = OrderedDict()
            parameters['Microwave Sweep Power (dBm)'] = self.sweep_mw_power
            parameters['Laser Power Votage (V)'] = self.laser_power_voltage
            parameters['Run Time (s)'] = self.elapsed_time
            parameters['Number of frequency sweeps (#)'] = self.elapsed_sweeps
            parameters['Start Frequencies (Hz)'] = self.mw_starts
            parameters['Stop Frequencies (Hz)'] = self.mw_stops
            parameters['Step sizes (Hz)'] = self.mw_steps
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
                data['count data (arb.u.)'] = self.odmr_plot_y[nch][data_start_ind:data_end_ind]
                data['count data error (arb.u.)'] = self.odmr_plot_y_err
                data_start_ind += num_points

                parameters = OrderedDict()
                parameters['Microwave Sweep Power (dBm)'] = self.sweep_mw_power
                parameters['Laser Power Votage (V)'] = self.laser_power_voltage
                parameters['Run Time (s)'] = self.elapsed_time
                parameters['Number of frequency sweeps (#)'] = self.elapsed_sweeps
                parameters['Start Frequency (Hz)'] = frequency_arr[0]
                parameters['Stop Frequency (Hz)'] = frequency_arr[-1]
                parameters['Step size (Hz)'] = frequency_arr[1] - frequency_arr[0]
                parameters['frequency range'] = str(ii)

                key = 'channel: {0}, range: {1}'.format(0, -1)
                try:
                    if len(self.fits_performed[key][0])!=0:
                        result_str = units.create_formatted_output(self.fits_performed[key][2].result_str_dict)
                        parameters['Fit result'] = result_str
                    parameters.update(self.pulsed_analysis_settings)

                    key = 'channel: {0}, range: {1}'.format(nch, ii)
                    if key in self.fits_performed.keys():
                        parameters['Fit function'] = self.fits_performed[key][3]
                        for name, param in self.fits_performed[key][2].params.items():
                            parameters[name] = str(param)
                except:
                    self.log.warning('Fit key failed.')
                # add all fit parameter to the saved data:
                # hard coded in the nchannel and range index for drawing the fit into the figure! oopsie
                fig = self.draw_figure(0, -1,
                                       cbar_range=colorscale_range,
                                       percentile_range=percentile_range)

                fig.suptitle(f'{filepath}\{filelabel}', fontsize=8)
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
        count_data = self.odmr_plot_y[channel_number]
        fit_freq_vals = self.frequency_lists[freq_range]
        fit_freq_vals = np.linspace(fit_freq_vals.min(), fit_freq_vals.max(), len(fit_freq_vals)*10)
        if key in self.fits_performed:
            fit_count_vals = self.fits_performed[key][2].eval(x=fit_freq_vals)
        else:
            fit_count_vals = 0.0

        # Rescale matrix counts data with SI prefix

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, ax_mean = plt.subplots(nrows=1, ncols=1)

        prop_cycle = self.savelogic().mpl_qd_style['axes.prop_cycle']
        colors = {}
        for i, color_setting in enumerate(prop_cycle):
            colors[i] = color_setting['color']
        ax_mean.errorbar(freq_data, count_data, yerr=self.odmr_plot_y_err, fmt='-o',
                                 linestyle=':', linewidth=0.5, color=colors[0],
                                 ecolor=colors[1], capsize=3, capthick=0.9,
                                 elinewidth=1.2, label='data trace 1')

        # Do not include fit curve if there is no fit calculated.
        if hasattr(fit_count_vals, '__len__'):
            ax_mean.plot(fit_freq_vals, fit_count_vals, marker='None')
            result_str = units.create_formatted_output(self.fits_performed[key][2].result_str_dict)
        else:
            result_str = ''
        # add then the fit result to the plot:

        # Parameters for the text plot:
        # The position of the text annotation is controlled with the
        # relative offset in x direction and the relative length factor
        # rel_len_fac of the longest entry in one column
        rel_offset = 0.02
        rel_len_fac = 0.011
        entries_per_col = 24

        # do reverse processing to get each entry in a list
        entry_list = result_str.split('\n')
        # slice the entry_list in entries_per_col
        chunks = [entry_list[x:x+entries_per_col] for x in range(0, len(entry_list), entries_per_col)]

        is_first_column = True  # first entry should contain header or \n

        for column in chunks:

            max_length = max(column, key=len)   # get the longest entry
            column_text = ''

            for entry in column:
                column_text += entry + '\n'

            column_text = column_text[:-1]  # remove the last new line

            heading = ''
            if is_first_column:
                heading = 'Fit results:'

            column_text = heading + '\n' + column_text

            ax_mean.text(1.00 + rel_offset, 0.99, column_text,
                        verticalalignment='top',
                        horizontalalignment='left',
                        transform=ax_mean.transAxes,
                        fontsize=12)

            # the rel_offset in position of the text is a linear function
            # which depends on the longest entry in the column
            rel_offset += rel_len_fac * len(max_length)

            is_first_column = False

        ax_mean.set_ylabel('Norm. counts')
        ax_mean.set_xlim(np.min(freq_data), np.max(freq_data))

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
                                 fit_function='No Fit', save_after_meas=True, name_tag='', laser_power_voltage=0.1):
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
        self.set_sweep_parameters(freq_start, freq_stop, freq_step, power, laser_power_voltage)

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
