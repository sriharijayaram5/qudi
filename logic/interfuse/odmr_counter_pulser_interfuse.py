# -*- coding: utf-8 -*-
"""
This file contains the Qudi Interfuse file for ODMRCounter and Pulser.

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
from hardware.timetagger_counter import HWRecorderMode
from core.connector import Connector
from core.configoption import ConfigOption
from logic.generic_logic import GenericLogic
from interface.odmr_counter_interface import ODMRCounterInterface
import time
from interface.simple_pulse_objects import PulseBlock, PulseSequence

class ODMRCounterInterfuse(GenericLogic, ODMRCounterInterface):
    """ This is the Interfuse class supplies the controls for a simple ODMR with counter and pulser."""


    slowcounter = Connector(interface='RecorderInterface')
    pulser = Connector(interface='PulserInterface')
    AWG = Connector(interface='PulserInterface')
    pulse_creator = Connector(interface='GenericLogic')

    _IQ = ConfigOption('IQ_mixer', missing='error')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._odmr_length = 100

    def on_activate(self):
        """ Initialisation performed during activation of the module."""
        self._pulser = self.pulser()
        self._AWG =self.AWG()
        self._sc_device = self.slowcounter()  # slow counter device
        self._pulse_creator = self.pulse_creator()

        self._lock_in_active = False
        self._oversampling = 10
        self._odmr_length = 100

    def on_deactivate(self):
        pass

    ### ODMR counter interface commands

    def set_up_odmr_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of the
                                      clock
        @param str clock_channel: if defined, this is the physical channel of
                                  the clock

        @return int: error code (0:OK, -1:error)
        """
        if self._IQ:
            run_IQ_status, ensemblename =self._pulse_creator.run_IQ_DC()
            if run_IQ_status<0:
                return -1

        channels = {'d0': 0.0 , 'd1': 0.0 , 'd2': 0.0 , 'd3': 0.0 , 'd4': 0.0 , 'd5': 0.0 , 'd6': 0.0 , 'd7': 0.0 , 'a0': 0.0, 'a1': 0.0}
        clear = lambda x: {i:0.0 for i in x.keys()}
        d_ch = lambda x: f'd{x}'
        a_ch = lambda x: f'a{x}'

        seq = PulseSequence()
        block_1 = PulseBlock()

        channels = clear(channels)
        channels[d_ch(self._pulser._laser_channel)] = 1.0
        channels[a_ch(self._pulser._laser_analog_channel)] = self._pulser._laser_power_voltage
        block_1.append(init_length = 1e-6, channels = channels, repetition = 1)

        channels = clear(channels)
        channels[d_ch(self._pulser._laser_channel)] = 1.0
        channels[a_ch(self._pulser._laser_analog_channel)] = self._pulser._laser_power_voltage
        channels[d_ch(self._pulser._mw_switch)] = 1.0
        channels[d_ch(self._pulser._pixel_start)] = 1.0
        block_1.append(init_length = 1/clock_frequency, channels = channels, repetition = 1)

        channels = clear(channels)
        channels[d_ch(self._pulser._laser_channel)] = 1.0
        channels[a_ch(self._pulser._laser_analog_channel)] = self._pulser._laser_power_voltage
        channels[d_ch(self._pulser._mw_switch)] = 0.0
        channels[d_ch(self._pulser._pixel_stop)] = 1.0
        block_1.append(init_length = 1e-6, channels = channels, repetition = 1)

        channels = clear(channels)
        channels[d_ch(self._pulser._laser_channel)] = 1.0
        channels[a_ch(self._pulser._laser_analog_channel)] = self._pulser._laser_power_voltage
        channels[d_ch(self._pulser._mw_trig)] = 1.0
        block_1.append(init_length = 1e-6, channels = channels, repetition = 1)

        seq.append([(block_1, 1)])

        pulse_dict = seq.pulse_dict

        self._pulser.load_swabian_sequence(pulse_dict)
        return 0
    
    def set_up_odmr_AWG_sweep(self, mw_start, mw_stop, mw_step, clock_frequency=None):

        self._pulse_creator.AWG.print_log_info = False
        self._pulse_creator.pulsed_master_AWG.sequencegeneratorlogic().print_log_info = False
        self._pulse_creator.pulsed_master.sequencegeneratorlogic().print_log_info = False

        self._pulse_creator.initialize_ensemble(laser_power_voltage = self._pulser._laser_power_voltage, target_freq_0 = mw_start, printing = False, set_up_measurement = False, check_current_sequence = False)
        ensemble_list, sequence_step_list, name, var_list, alternating, freq_sweep = self._pulse_creator.CW_ODMR(mw_start, mw_stop, mw_step, clock_frequency) #Preparing Pulsestreamer and AWG without setting up the pulse measurement GUI or Timetagger
        
        self._pulse_creator.AWG.print_log_info = True
        self._pulse_creator.pulsed_master_AWG.sequencegeneratorlogic().print_log_info = True
        self._pulse_creator.pulsed_master.sequencegeneratorlogic().print_log_info = True

        return var_list

    def set_up_odmr(self, counter_channel=None, photon_source=None,
                    clock_channel=None, odmr_trigger_channel=None):
        """ Configures the actual counter with a given clock.

        @param str counter_channel: if defined, this is the physical channel of
                                    the counter
        @param str photon_source: if defined, this is the physical channel where
                                  the photons are to count from
        @param str clock_channel: if defined, this specifies the clock for the
                                  counter
        @param str odmr_trigger_channel: if defined, this specifies the trigger
                                         output for the microwave

        @return int: error code (0:OK, -1:error)
        """
        
        return 0

    def set_odmr_length(self, length=100):
        """Set up the trigger sequence for the ODMR and the triggered microwave.

        @param int length: length of microwave sweep in pixel

        @return int: error code (0:OK, -1:error)
        """
        self._sc_device.configure_recorder(
            mode=HWRecorderMode.ESR,
            params={'mw_frequency_list': np.zeros(length),
                    'num_meas': 1 } )

        self._odmr_length = length
        return 0

    def count_odmr_AWG(self):
        """ Sweeps the microwave and returns the counts on that sweep.

        @param int length: length of microwave sweep in pixel

        @return float[]: the photon counts per second
        """

        self._sc_device.start_recorder()
        self._AWG.pulser_on() # not sure why n=length fails
        time.sleep(0.1)
        counts = self._sc_device.get_measurements(['counts'])[0]

        return False, counts

    def count_odmr(self, length = 100):
        """ Sweeps the microwave and returns the counts on that sweep.

        @param int length: length of microwave sweep in pixel

        @return float[]: the photon counts per second
        """

        self._sc_device.start_recorder()
        self._pulser.pulser_on(n=self._odmr_length) # not sure why n=length fails
        counts = self._sc_device.get_measurements(['counts'])[0]
    
        return False, counts

    def close_odmr(self):
        """ Close the odmr and clean up afterwards.     

        @return int: error code (0:OK, -1:error)
        """
        self._sc_device.stop_measurement()
        self._pulser.pulser_off()
        self._AWG.pulser_off()
        return 0

    def close_odmr_clock(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        self._sc_device.stop_measurement()
        return 0

    def get_odmr_channels(self):
        """ Return a list of channel names.

        @return list(str): channels recorded during ODMR measurement
        """
        return ['APD0']
    
    @property
    def lock_in_active(self):
        return self._lock_in_active

    @lock_in_active.setter
    def lock_in_active(self, val):
        if not isinstance(val, bool):
            self.log.error('lock_in_active has to be boolean.')
        else:
            self._lock_in_active = val
            if self._lock_in_active:
                self.log.warn('Lock-In is not implemented')
    
    @property
    def oversampling(self):
        return self._oversampling

    @oversampling.setter
    def oversampling(self, val):
        if not isinstance(val, (int, float)):
            self.log.error('oversampling has to be int of float.')
        else:
            self._oversampling = int(val)