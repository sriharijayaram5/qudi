# -*- coding: utf-8 -*-
"""
This file contains the Qudi counter logic class.

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
import numpy as np
import time
import matplotlib.pyplot as plt

from core.connector import Connector
from core.statusvariable import StatusVar
from logic.generic_logic import GenericLogic
from interface.slow_counter_interface import CountingMode
from core.util.mutex import Mutex

import logic.pulsed.pulse_objects as po
from logic.pulsed.sampling_functions import SamplingFunctions as SF


class PulsedJupyterLogic(GenericLogic):

    _pulsed_master = Connector(interface='GenericLogic')
    _pulsed_master_AWG = Connector(interface='GenericLogic')

    def __init__(self, config, **kwargs):
        """ 
        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)
        return
    
    def on_activate(self):
        self.pulsed_master = self._pulsed_master()
        self.pulser = self.pulsed_master.pulsedmeasurementlogic().pulsegenerator()
        self.pulsed_master_AWG = self._pulsed_master_AWG()
        self.AWG = self.pulsed_master_AWG.pulsedmeasurementlogic().pulsegenerator()
        self.mw = self.pulsed_master.pulsedmeasurementlogic().microwave()
        self.mw1 = self.pulsed_master.pulsedmeasurementlogic().microwave1()

        self.channel_names_PS = {'Laser': 'd_ch1',
                                 'TT_Start': 'd_ch2',
                                 'TT_Next': 'd_ch3'
                                }
        
        self.channel_names_AWG = {'PS_Trig': 'd_ch5',
                                 'ASC_Trig': 'd_ch4',
                                 'SMBV_I': 'a_ch0',
                                 'SMBV_Q': 'a_ch1',
                                 'SGS_I': 'a_ch2',
                                 'SGS_Q': 'a_ch3',
                                 'MW_0': False,
                                 'MW_1': False
                                }
        
        Sync_time = (16e-9+476.5/1.25e9)
        print("Sync",Sync_time)

        Rearm_time = (40/1.25e9)
        print("Rearm_time",Rearm_time)
        return

    def on_deactivate(self):
        return
    
    def initialize_ensemble(self, laser_power_voltage = 0.08, pi_pulse=1e-9, pi_half_pulse=1e-9, three_pi_half_pulse=1e-9, awg_sync_time=16e-9 + 476.5/1.25e9, 
                            laser_waiting_time=1.5e-6, mw_waiting_time=1e-6, read_out_time=3e-6,
                            LO_freq_0=3e9, target_freq_0=2.88e9, power_0=-20, LO_freq_1=3e9, target_freq_1=2.88e9, power_1=-100, printing = True, upload = True, set_up_measurement = True, check_current_sequence = False):
        
        self.pi_pulse = pi_pulse
        self.pi_half_pulse = pi_half_pulse
        self.three_pi_half_pulse = three_pi_half_pulse
        self.awg_sync_time = awg_sync_time #Has to be determined with sample clock
        self.laser_waiting_time = laser_waiting_time
        self.mw_waiting_time = mw_waiting_time
        self.read_out_time = read_out_time
        self.laser_volt = laser_power_voltage
        self.LO_freq_0 = LO_freq_0
        self.target_freq_0 = target_freq_0
        self.power_0 = power_0
        self.LO_freq_1 = LO_freq_1
        self.target_freq_1 = target_freq_1
        self.power_1 = power_1
        self.upload = upload
        self.set_up_measurement = set_up_measurement
        self.check_current_sequence = check_current_sequence
        
        if printing:
            self.log.info(f"Using laser voltage: {self.laser_volt}V")

        return
    
    def ElementPS(self, channels={}, length=1e-9, laser_power=None):
        """PulseBlock element list maker for PulseStreamer upload. Also makes the phase duration list for the AWG,
            which also includes the information about which MW frequency of the two LO is used.
        """
        a_ch = {'a_ch1': SF.DC(laser_power) if laser_power else SF.DC(self.laser_volt), 'a_ch2': SF.DC(0)}
        d_ch = { 'd_ch1': False, 'd_ch2': False, 'd_ch3': False, 'd_ch4': False, 'd_ch5': False, 'd_ch6': False, 'd_ch7': False, 'd_ch8': False}

        for key in channels:
            PSkey = self.channel_names_PS[key]
            if 'a_' in key:
                a_ch[PSkey] = channels[key]
            else:
                d_ch[PSkey] = channels[key]
        
        self.BlockPS.append(po.PulseBlockElement(init_length_s=length, pulse_function=a_ch, digital_high=d_ch))

    def ElementAWG(self, channels={}, length=1e-9, phase_0=0, phase_1=0, freq_0=None, freq_1=None):
        """PulseBlock element list maker for PulseStreamer upload. Also makes the phase duration list for the AWG,
            which also includes the information about which MW frequency of the two LO is used.
        """

        user_MW_0_true = False
        user_MW_1_true = False
        
        if 'MW_0' in channels.keys():
            user_MW_0_true = channels['MW_0']
            del channels['MW_0']
        if 'MW_1' in channels.keys():
            user_MW_1_true = channels['MW_1']
            del channels['MW_1']

        self.BlockAWG.append((phase_0, phase_1, length, user_MW_0_true, user_MW_1_true, freq_0, freq_1, channels))

    def find_unique_segments(self,sequence_step_list):
            """Convenience function to find unique segments in sequence step
            """
            segments = []
            for step in sequence_step_list:
                segments.append(step['step_segment'])
            segments = list(set(segments)) # gives only the unique items
            segment_and_index = {}
            for index, seg in enumerate(segments):
                segment_and_index[seg] = index
            return segment_and_index, segments

    def sample_load_ready_pulsestreamer(self, name = 'read_out_jptr'):
        
        self.pulser.pulser_off()
        self.BlockPS = []
        #Read out sequence
        self.ElementPS(channels={'TT_Next':True}, length=self.mw_waiting_time)
        self.ElementPS(channels={'Laser':True, 'TT_Start':True}, length=self.read_out_time)
        
        pulse_block = po.PulseBlock(name=name, element_list=self.BlockPS)
        self.pulsed_master.sequencegeneratorlogic().save_block(pulse_block)
        
        block_list = []
        block_list.append((pulse_block.name, 0))
        pulse_block_ensemble = po.PulseBlockEnsemble(name, block_list)
        
        self.pulsed_master.sequencegeneratorlogic().save_ensemble(pulse_block_ensemble)
        self.pulsed_master.sequencegeneratorlogic().sample_pulse_block_ensemble(name)
        self.pulsed_master.sequencegeneratorlogic().load_ensemble(name)
        self.pulser.pulser_on(trigger=True, n=1, rearm=False, final=self.pulser.AWG_master_final_state)

    def sample_load_ready_pulsestreamer_cw_odmr(self, meas_time, expand_time, name = 'read_out_cw_odmr_jptr'):
        
        self.pulser.pulser_off()
        self.BlockPS = []
        #Read out sequence
        self.ElementPS(channels={'Laser':True,'TT_Start':True}, length=meas_time, laser_power=self.pulser._laser_power_voltage)
        self.ElementPS(channels={'Laser':True, 'TT_Next':True}, length=expand_time, laser_power=self.pulser._laser_power_voltage)
        
        pulse_block = po.PulseBlock(name=name, element_list=self.BlockPS)
        self.pulsed_master.sequencegeneratorlogic().save_block(pulse_block)
        
        block_list = []
        block_list.append((pulse_block.name, 0))
        pulse_block_ensemble = po.PulseBlockEnsemble(name, block_list)
        
        self.pulsed_master.sequencegeneratorlogic().save_ensemble(pulse_block_ensemble)
        self.pulsed_master.sequencegeneratorlogic().sample_pulse_block_ensemble(name)
        self.pulsed_master.sequencegeneratorlogic().load_ensemble(name)
        self.pulser.pulser_on(trigger=True, n=1, rearm=False, final=self.pulser._final_state)
        return 0

    def run_IQ_DC(self, MW0 = True, MW1 = False):
        """
        Runs a simple constant voltage sequence in regular stream mode on the AWG. Just a convenience function for running measurements which need LO MW passthrough
        """
        self.AWG.pulser_off()
        self.AWG.instance.init_all_channels()
        amp = 0.5
        if MW0 and not MW1:
            ch = [
                {'name': 'a_ch0', 'amp': amp},
                {'name': 'a_ch1', 'amp': amp}
                ]
        elif not MW0 and MW1:
            ch = [
                {'name': 'a_ch2', 'amp': amp},
                {'name': 'a_ch3', 'amp': amp}
                ]
        elif MW0 and MW1:
            ch = [
                {'name': 'a_ch0', 'amp': amp},
                {'name': 'a_ch1', 'amp': amp},
                {'name': 'a_ch2', 'amp': amp},
                {'name': 'a_ch3', 'amp': amp}
                ]
        else:
            self.log.warning('Nothing was uploaded during run_IQ_DC')
            return -1
        ensemble_list = self.load_dc(channels = ch, dur = 10e-6, identifier = 'A')

        self.AWG.pulser_on()
        return 0, ensemble_list

    def load_dc(self, channels = [{'name': 'a_ch0', 'amp': 1.00}], dur=1e-6, identifier=''):
        """
        Load a sine waveform to be played simultaneously on the specified channels.
        """
        ele = []
        a_ch = {'a_ch0': SF.DC(0), 'a_ch1': SF.DC(0), 'a_ch2': SF.DC(0), 'a_ch3': SF.DC(0)}
        d_ch = {'d_ch0': False, 'd_ch1': False, 'd_ch2': False, 'd_ch4': False, 'd_ch3': False, 'd_ch5': False}
        for ch in channels:
            a_ch[ch['name']] = SF.DC(ch['amp'])
            
        ele.append(po.PulseBlockElement(init_length_s=dur,  pulse_function=a_ch, digital_high=d_ch))
        pulse_block = po.PulseBlock(name=f'DCAuto', element_list=ele)
        self.pulsed_master_AWG.sequencegeneratorlogic().save_block(pulse_block)

        block_list = []
        block_list.append((pulse_block.name, 0))
        auto_pulse_CW = po.PulseBlockEnsemble(f'DCAuto{identifier}', block_list)

        ensemble = auto_pulse_CW
        ensemblename = auto_pulse_CW.name
        self.pulsed_master_AWG.sequencegeneratorlogic().save_ensemble(ensemble)
        self.pulsed_master_AWG.sequencegeneratorlogic().sample_pulse_block_ensemble(ensemblename)
        self.pulsed_master_AWG.sequencegeneratorlogic().load_ensemble(ensemblename)

        return ensemblename

    def sample_load_ready_AWG(self, name, tau_arr, alternating, freq_sweep, change_freq = True, stop_AWG = False):
        """Function to loop through the PhaseDuration list defined with ElementPS/AWG for each measurement.
            A list of all these small steps are made into an ensemble by load_large_sine_seq and is ready to be 
            played by trigger.
            One big ensemble covering the entire tau sweep that is triggered once before every sweep. Not before every tau instance.
        """
        #Create large pulse block for the AWG

        large_seq = []
        use_MW_0 = False
        use_MW_1 = False

        for Element in self.BlockAWG:
            phase_0, phase_1, duration, user_MW_0_true, user_MW_1_true, freq_0, freq_1, channels = Element
            if user_MW_0_true:
                use_MW_0 = True
            if user_MW_1_true:
                use_MW_1 = True
            delta_0 = abs(self.LO_freq_0 - (self.target_freq_0 if freq_0 is None else freq_0))
            delta_1 = abs(self.LO_freq_1 - (self.target_freq_1 if freq_1 is None else freq_1))
            
            seq_part = {'channel_info' : [
                {'name': 'a_ch0', 'amp': 0.5 if user_MW_0_true else 0.0, 'freq': delta_0, 'phase': 0+phase_0},
                {'name': 'a_ch1', 'amp': 0.5 if user_MW_0_true else 0.0, 'freq': delta_0, 'phase': 100+phase_0},
                {'name': 'a_ch2', 'amp': 0.5 if user_MW_1_true else 0.0, 'freq': delta_1, 'phase': 0+phase_1},
                {'name': 'a_ch3', 'amp': 0.5 if user_MW_1_true else 0.0, 'freq': delta_1, 'phase': 100+phase_1}],
                'duration' : duration}
            for ch in channels:
                seq_part['channel_info'].append({'name': self.channel_names_AWG[ch], 'high': channels[ch]})
            large_seq.append(seq_part)
        
        ensemble_list = self.sample_ensembles(large_seq=[large_seq], identifier=[name])

        sequence_step_list = []
        if self.upload:
            for idx, ensemble in enumerate(ensemble_list):
                step = {"step_index" : idx,
                        "step_segment" : ensemble,
                        "step_loops" : 1,
                        "next_step_index" : idx+1 if idx<len(ensemble_list)-1 else 0,
                        "step_end_cond" : 'stop' if stop_AWG else 'always'
                        }
                sequence_step_list.append(step)
            self.AWG_MW_reset()
            self.AWG.load_ready_sequence_mode(sequence_step_list)

        if self.set_up_measurement:
            #Setup TimeTagger
            tau_num = len(tau_arr) * 2 if alternating else len(tau_arr)
            self.pulsed_master_AWG.set_fast_counter_settings(record_length=self.read_out_time, number_of_gates=tau_num)

            #Setup pulsed GUI
            self.pulsed_master_AWG.set_measurement_settings(invoke_settings=False, 
                                                controlled_variable=tau_arr,
                                                number_of_lasers=tau_num, 
                                                laser_ignore_list=[], 
                                                alternating=alternating, 
                                                units=('Hz' if freq_sweep else 's', 'arb. u.'))
            self.pulsed_master_AWG.pulsedmeasurementlogic().alternative_data_type = 'None'
            if use_MW_0:
                self.pulsed_master_AWG.set_ext_microwave_settings(use_ext_microwave=True, 
                                                frequency=self.LO_freq_0,
                                                power=self.power_0)
            #self.MW_start(change_freq,use_MW_0,use_MW_1)

        return ensemble_list, sequence_step_list
    
    def sample_load_ready_AWG_sequence(self, segments, sequence_step_list, tau_arr, alternating, freq_sweep, change_freq = True):
        """Function to loop through the PhaseDuration list defined with ElementPS/AWG for each measurement.
            A list of all these small steps are made into an ensemble by load_large_sine_seq and is ready to be 
            played by trigger.
            One big ensemble covering the entire tau sweep that is triggered once before every sweep. Not before every tau instance.
        """
        #Create large pulse block for the AWG
        ensemble_list = []
        use_MW_0 = False
        use_MW_1 = False

        sample_sequence = True
        ensemble_name_list = self.pulsed_master_AWG.sequencegeneratorlogic()._saved_pulse_block_ensembles.keys()

        if self.check_current_sequence: #Set this flag, if the last uploaded sequence and the memory of sampled pulse blocks shut be checked
            if sequence_step_list == self.AWG._current_uploaded_sequence_step_list:
                segment_and_index, ensemble_list = self.find_unique_segments(sequence_step_list)
                sample_sequence = False
                self.upload = False

        if sample_sequence:
            for key in segments.keys():
                name = key
                if 'Jupyter-ensemble-'+name in ensemble_name_list and self.check_current_sequence:
                    continue
                large_seq = []
                BlockAWG = segments[key]

                for Element in BlockAWG:
                    phase_0, phase_1, duration, user_MW_0_true, user_MW_1_true, freq_0, freq_1, channels = Element
                    if user_MW_0_true:
                        use_MW_0 = True
                    if user_MW_1_true:
                        use_MW_1 = True
                    delta_0 = abs(self.LO_freq_0 - (self.target_freq_0 if freq_0 is None else freq_0))
                    delta_1 = abs(self.LO_freq_1 - (self.target_freq_1 if freq_1 is None else freq_1))
                    
                    seq_part = {'channel_info' : [
                        {'name': 'a_ch0', 'amp': 0.5 if user_MW_0_true else 0.0, 'freq': delta_0, 'phase': 0+phase_0},
                        {'name': 'a_ch1', 'amp': 0.5 if user_MW_0_true else 0.0, 'freq': delta_0, 'phase': 100+phase_0},
                        {'name': 'a_ch2', 'amp': 0.5 if user_MW_1_true else 0.0, 'freq': delta_1, 'phase': 0+phase_1},
                        {'name': 'a_ch3', 'amp': 0.5 if user_MW_1_true else 0.0, 'freq': delta_1, 'phase': 100+phase_1}],
                        'duration' : duration}
                    for ch in channels:
                        seq_part['channel_info'].append({'name': self.channel_names_AWG[ch], 'high': channels[ch]})
                    large_seq.append(seq_part)
            
                ensemble_list.append(self.sample_ensembles(large_seq=[large_seq], identifier=[name]))

        if self.upload:
            self.AWG_MW_reset()
            self.AWG.load_ready_sequence_mode(sequence_step_list)

        if self.set_up_measurement:
            #Setup TimeTagger
            tau_num = len(tau_arr) * 2 if alternating else len(tau_arr)
            self.pulsed_master_AWG.set_fast_counter_settings(record_length=self.read_out_time, number_of_gates=tau_num)

            #Setup pulsed GUI
            self.pulsed_master_AWG.set_measurement_settings(invoke_settings=False, 
                                                controlled_variable=tau_arr,
                                                number_of_lasers=tau_num, 
                                                laser_ignore_list=[], 
                                                alternating=alternating, 
                                                units=('Hz' if freq_sweep else 's', 'arb. u.'))
            self.pulsed_master_AWG.pulsedmeasurementlogic().alternative_data_type = 'None'
            if use_MW_0:
                self.pulsed_master_AWG.set_ext_microwave_settings(use_ext_microwave=True, 
                                                frequency=self.LO_freq_0,
                                                power=self.power_0)
            #self.MW_start(change_freq,use_MW_0,use_MW_1)

        return ensemble_list, sequence_step_list
    
    def sample_ensembles(self, large_seq = [[{'name': 'a_ch0', 'amp': 1.00}]], identifier=['']):
            """
            Sample and save a large sequence to be played on the AWG.
            """
            ensemble_list = []
            for idx, ensemble in enumerate(large_seq):
                ele = []
                for step in ensemble:
                    # self.log.debug(step)
                    channels = step['channel_info']
                    dur = step['duration']

                    a_ch = {'a_ch0': SF.DC(0), 'a_ch1': SF.DC(0), 'a_ch2': SF.DC(0), 'a_ch3': SF.DC(0)}
                    d_ch = {'d_ch0': False, 'd_ch1': False, 'd_ch2': False, 'd_ch4': False, 'd_ch3': False, 'd_ch5': False}
                    for ch in channels:
                        if 'a_' in ch['name']:
                            a_ch[ch['name']] = SF.Sin(amplitude=ch['amp'], frequency=ch['freq'], phase=ch['phase'])
                        else:
                            d_ch[ch['name']] = ch['high']

                    ele.append(po.PulseBlockElement(init_length_s=dur,  pulse_function=a_ch, digital_high=d_ch))
                pulse_block = po.PulseBlock(name=f'Jupyter-block-{identifier[idx]}', element_list=ele)
                self.pulsed_master_AWG.sequencegeneratorlogic().save_block(pulse_block)

                block_list = []
                block_list.append((pulse_block.name, 0))
                auto_pulse_CW = po.PulseBlockEnsemble(f'Jupyter-ensemble-{identifier[idx]}', block_list)

                ensemble = auto_pulse_CW
                ensemblename = auto_pulse_CW.name
                self.pulsed_master_AWG.sequencegeneratorlogic().save_ensemble(ensemble)
                self.pulsed_master_AWG.sequencegeneratorlogic().sample_pulse_block_ensemble(ensemblename)
                ensemble_list.append(ensemblename)

            return ensemble_list              
        
    def AWG_MW_reset(self):
        """ Resets all pulsing
        """
        self.AWG.pulser_off()
        self.AWG.instance.init_all_channels()
        self.mw.off()
        self.mw1.off()
        
    def MW_start(self, change_freq = True ,user_MW_0_true = False, user_MW_1_true = False):
        """ Starts AWG in triggered mode, sets and starts LO
        """
        
        if user_MW_0_true:
            if change_freq:
                self.mw.set_cw(frequency=self.LO_freq_0, power=self.power_0)
            self.mw.cw_on()

        if user_MW_1_true:
            if change_freq:
                self.mw1.set_cw(frequency=self.LO_freq_1, power=self.power_1)
            self.mw1.cw_on()

    def start_measurement(self, measurement_type = 'test', tip_name = '', sample = '', temperature = '', b_field = '', contact = '', extra = '', printing = True):
        save_tag = measurement_type

        if tip_name:
            save_tag += '_'+tip_name
        if sample:
            save_tag += '_'+sample
        if temperature:
            save_tag += '_'+temperature
        if b_field:
            save_tag += '_'+b_field
        if contact:
            save_tag += '_'+contact
        if extra:
            save_tag += '_'+extra
        
        self.pulsed_master_AWG.sigUpdateSaveTag.emit(save_tag)
        self.pulsed_master_AWG.sigUpdateLoadedAssetLabel.emit('  '+measurement_type)
        self.pulsed_master_AWG.toggle_pulsed_measurement(start=True)
        if printing:
            self.log.info(save_tag)

####################################################################################################################
## Beginning of Measurement methods ##
####################################################################################################################

    def Single_Freq(self, MW_0=False, MW_0_freq = 2.88e9 , MW_0_power = -20, MW_1=False, MW_1_freq = 2.88e9, MW_1_power = -20):
        '''
        '''        
        alternating = False
        freq_sweep=False
        name = 'single_freq_jptr'
        self.tau_arr = []
        sequence_step_list = []

        status, ensemble_list = self.run_IQ_DC(self, MW0 = MW_0, MW1 = MW_1)
        if MW_0:
            self.mw.set_cw(MW_0_freq,MW_0_power)
        if MW_1:
            self.mw.set_cw(MW_1_freq,MW_1_power)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
    
    def CW_ODMR(self, mw_start, mw_stop, mw_step, clock_frequency=None, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇
        MW:               ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇
                                  freq-sweep   
        '''        
        if name is None:
            name = 'cw-odmr-juptr'

        alternating = False
        freq_sweep=True
        num_steps = int(np.rint((mw_stop - mw_start) / mw_step))
        end_freq = mw_start + num_steps * mw_step
        freq_range = end_freq-mw_start
        self.tau_arr = np.linspace(mw_start, end_freq, num_steps + 1)
        
        self.LO_freq_0 = end_freq + 100e6

        #Create pulse sequence for the AWG streamer
        self.segments = {}
        self.sequence_step_list = []

        #Define the number of loops played for each frequency step
        meas_time = 1/clock_frequency
        freq_segment_time = 10e-6
        expand_time = 1*freq_segment_time
        num_loops = int(np.rint(meas_time/freq_segment_time))
        num_loops_expand = int(np.rint(expand_time/freq_segment_time))
        new_meas_time = num_loops*freq_segment_time
        num_loops_total = num_loops+num_loops_expand

        #Define the PS trigger segment
        trig_dur = 500e-9 #If the time is to small (e.g. 50e-9), the upload will fail
        trig_name = name+'-PS_trig'
        self.BlockAWG = []
        self.ElementAWG(channels={'PS_Trig':True}, length=trig_dur) 
        self.segments[trig_name] = self.BlockAWG    

        for idx, tau in enumerate(self.tau_arr):
            self.BlockAWG = []
            freq_segment_name = name+f'-freq-({self.LO_freq_0-tau},{freq_segment_time})'
            #Playing current frequency
            self.ElementAWG(channels={'MW_0':True}, length=freq_segment_time, freq_0=tau)
            self.segments[freq_segment_name] = self.BlockAWG

            step = {"step_index" : 2*idx,
                        "step_segment" : 'Jupyter-ensemble-'+trig_name,
                        "step_loops" : 1,
                        "next_step_index" : 2*idx+1,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 2*idx+1,
                        "step_segment" : 'Jupyter-ensemble-'+freq_segment_name,
                        "step_loops" : num_loops_total,
                        "next_step_index" : 0 if tau == self.tau_arr[-1] else 2*idx+2,
                        "step_end_cond" : 'stop' if tau == self.tau_arr[-1] else 'always'
                        }
            self.sequence_step_list.append(step)
 
        self.sample_load_ready_pulsestreamer_cw_odmr(new_meas_time,expand_time/2, name = 'read_out_cw_odmr_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG_sequence(self.segments, self.sequence_step_list, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
    
    def PODMR(self, mw_start, mw_stop, mw_step, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▇PI▇▁▁▁▁▁▁▁
                                  freq-sweep   
        '''        
        if name is None:
            name = 'podmr-juptr'

        alternating = False
        freq_sweep=True
        num_steps = int(np.rint((mw_stop - mw_start) / mw_step))
        end_freq = mw_start + num_steps * mw_step
        self.tau_arr = np.linspace(mw_start, end_freq, num_steps + 1)
        
        self.LO_freq_0 = end_freq + 100e6

        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []

        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time) 
            #Pi pulse - reference
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, freq_0=tau)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)

        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep

    def Tracking(self, res_freq, delta_freq, change_freq = True, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▇PI▇▁▁▁▁▁▁▁
                                  freq-sweep   
        '''        
        
        if name is None:
            name = 'tracking-juptr'

        alternating = False
        freq_sweep=True
        left_freq = res_freq-delta_freq
        right_freq = res_freq+delta_freq
        self.tau_arr = [left_freq, right_freq]
        
        self.LO_freq_0 = res_freq + 100e6
        
        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []

        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time) 
            #Pi pulse - reference
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, freq_0=tau)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)

        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
    
    def Rabi(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▇▇▁▁▁▁▁▁▁
                                  tau-sweep             
        '''        
        if name is None:
            name = 'rabi-juptr'

        alternating = False
        freq_sweep=False
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num)
        
        #Create pulse sequence for the AWG
        self.BlockAWG = []

        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time) 
            #Pi pulse - reference
            self.ElementAWG(channels={'MW_0':True}, length=tau)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)

        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
    
    def T1_optical_exp(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                                      t             
        '''
        if name is None:    
            name = 't1-opti-exp-juptr'

        alternating = False
        freq_sweep=False
        self.tau_arr = np.logspace(np.log10(tau_start), np.log10(tau_stop), num=tau_num)
        
        #Create pulse sequence for the AWG streamer
        self.segments = {}
        self.sequence_step_list = []

        #Define read out segment
        self.BlockAWG = []
        read_out_name = name+'-read_out'
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.ElementAWG(channels={}, length=self.laser_waiting_time)
        self.segments[read_out_name] = self.BlockAWG

        #Define waiting Segment
        self.BlockAWG = []
        waiting_name = name+'-waiting'
        #It is recommended to use a multiple of 32, as the AWG only allows to upload sample size with modulus 32 == 0.
        #Otherwise it will fill up the segment with empty samples, making the waiting time not predictable.
        waiting_samples = 32*12
        if waiting_samples <32*12:
            print('!!!Given configuration of waiting samples results in an value, which cannot be uploaded to the AWG!!!')
            return
        waiting_time = waiting_samples/1.25e9
        self.ElementAWG(channels={}, length=waiting_time)
        self.segments[waiting_name] = self.BlockAWG

        #Define Sequence with sequence_step_list
        real_tau_arr = []
        for idx, tau in enumerate(self.tau_arr):
            num_waiting_loops = int(np.rint(tau/waiting_time))
            real_tau_arr.append(waiting_time*num_waiting_loops)

            step = {"step_index" : 2*idx,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 2*idx+1,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 2*idx+1,
                        "step_segment" : 'Jupyter-ensemble-'+read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 0 if tau == self.tau_arr[-1] else 2*idx+2,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)

        self.tau_arr = real_tau_arr
 
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG_sequence(self.segments, self.sequence_step_list, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
        
    def T1_alt_exp(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                                      t             
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                      X               t             
        '''        
        if name is None:    
            name = 't1-alt-exp-juptr'

        alternating = True
        freq_sweep=False
        self.tau_arr = np.logspace(np.log10(tau_start), np.log10(tau_stop), num=tau_num)

        #Create pulse sequence for the AWG streamer
        self.segments = {}
        self.sequence_step_list = []

        #Define Pi pulse segment
        self.BlockAWG = []
        pi_pulse_name = name+'-pi_pulse'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.laser_waiting_time)
        self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
        self.segments[pi_pulse_name] = self.BlockAWG

        #Define Pi pulse replacement segment for keeping the alternating measurement of the same duration
        self.BlockAWG = []
        replacement_name = name+'-replacement'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.laser_waiting_time+self.pi_pulse)
        self.segments[replacement_name] = self.BlockAWG

        #Define read out segment
        self.BlockAWG = []
        read_out_name = name+'-read_out'
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[read_out_name] = self.BlockAWG

        #Define waiting Segment
        self.BlockAWG = []
        waiting_name = name+'-waiting'
        #It is recommended to use a multiple of 32, as the AWG only allows to upload sample size with modulus 32 == 0.
        #Otherwise it will fill up the segment with empty samples, making the waiting time not predictable.
        waiting_samples = 32*12
        if waiting_samples <32*12:
            print('!!!Given configuration of waiting samples results in an value, which cannot be uploaded to the AWG!!!')
            return
        waiting_time = waiting_samples/1.25e9
        self.ElementAWG(channels={}, length=waiting_time)
        self.segments[waiting_name] = self.BlockAWG

        #Define Sequence with sequence_step_list
        real_tau_arr = []
        for idx, tau in enumerate(self.tau_arr):
            num_waiting_loops = int(np.rint(tau/waiting_time))
            real_tau_arr.append(waiting_time*num_waiting_loops)

            step = {"step_index" : 6*idx,
                        "step_segment" : 'Jupyter-ensemble-'+replacement_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+1,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+1,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+2,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+2,
                        "step_segment" : 'Jupyter-ensemble-'+read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+3,
                        "step_end_cond" : 'always'
                        }
            step = {"step_index" : 6*idx+3,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+4,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+4,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+5,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+5,
                        "step_segment" : 'Jupyter-ensemble-'+read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 0 if tau == self.tau_arr[-1] else 6*idx+6,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)

        self.tau_arr = real_tau_arr
 
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG_sequence(self.segments, self.sequence_step_list, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
        
    def T1_dark_init_alt_exp(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                    X(-1)             t             
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁
                                    X(-1)             t             X(-1)
        '''        
        if name is None:
            name = 't1-dark-init-alt-exp-juptr'

        alternating = True
        freq_sweep=False
        self.tau_arr = np.logspace(np.log10(tau_start), np.log10(tau_stop), num=tau_num)

        #Create pulse sequence for the AWG streamer
        self.segments = {}
        self.sequence_step_list = []

        #Define Pi pulse intitialzation segment
        self.BlockAWG = []
        pi_pulse_init_name = name+'-pi_pulse_init'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.laser_waiting_time)
        self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
        self.segments[pi_pulse_init_name] = self.BlockAWG

        #Define Pi pulse + read out segment 
        self.BlockAWG = []
        pi_pulse_read_out_name = name+'-pi_pulse_read_out'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[pi_pulse_read_out_name] = self.BlockAWG

        #Define Pi pulse replacement + read out segment 
        self.BlockAWG = []
        pi_pulse_replacement_read_out_name = name+'-pi_pulse_replacement_read_out'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.pi_pulse)
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[pi_pulse_replacement_read_out_name] = self.BlockAWG

        #Define waiting Segment
        self.BlockAWG = []
        waiting_name = name+'-waiting'
        #It is recommended to use a multiple of 32, as the AWG only allows to upload sample size with modulus 32 == 0.
        #Otherwise it will fill up the segment with empty samples, making the waiting time not predictable.
        waiting_samples = 32*12
        if waiting_samples <32*12:
            print('!!!Given configuration of waiting samples results in an value, which cannot be uploaded to the AWG!!!')
            return
        waiting_time = waiting_samples/1.25e9
        self.ElementAWG(channels={}, length=waiting_time)
        self.segments[waiting_name] = self.BlockAWG

        #Define Sequence with sequence_step_list
        real_tau_arr = []
        for idx, tau in enumerate(self.tau_arr):
            num_waiting_loops = int(np.rint(tau/waiting_time))
            real_tau_arr.append(waiting_time*num_waiting_loops)

            step = {"step_index" : 6*idx,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_init_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+1,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+1,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+2,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+2,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+3,
                        "step_end_cond" : 'always'
                        }
            step = {"step_index" : 6*idx+3,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_init_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+4,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+4,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+5,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+5,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_replacement_read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 0 if tau == self.tau_arr[-1] else 6*idx+6,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)

        self.tau_arr = real_tau_arr
 
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG_sequence(self.segments, self.sequence_step_list, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
        
    def T1_DQ_alt_exp(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁
                                    X(-1)             t             X(-1)
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁
                                    X(-1)             t             X(+1)
        '''        
        if name is None:
            name = 't1-DQ-alt-exp-juptr'

        alternating = True
        freq_sweep=False
        self.tau_arr = np.logspace(np.log10(tau_start), np.log10(tau_stop), num=tau_num)

        #Create pulse sequence for the AWG streamer
        self.segments = {}
        self.sequence_step_list = []

        #Define Pi pulse peak 0 (MW0) intitialzation segment
        self.BlockAWG = []
        pi_pulse_peak0_init_name = name+'-pi_pulse_peak0_init'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.laser_waiting_time)
        self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
        self.segments[pi_pulse_peak0_init_name] = self.BlockAWG

        #Define Pi pulse peak 0 (MW0) + read out segment 
        self.BlockAWG = []
        pi_pulse_peak0_read_out_name = name+'-pi_pulse_peak0_read_out'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[pi_pulse_peak0_read_out_name] = self.BlockAWG

        #Define Pi pulse peak 1 (MW1) + read out segment 
        self.BlockAWG = []
        pi_pulse_peak1_read_out_name = name+'-pi_pulse_peak1_read_out'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={'MW_1':True}, length=self.pi_pulse)
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[pi_pulse_peak1_read_out_name] = self.BlockAWG

        #Define waiting Segment
        self.BlockAWG = []
        waiting_name = name+'-waiting'
        #It is recommended to use a multiple of 32, as the AWG only allows to upload sample size with modulus 32 == 0.
        #Otherwise it will fill up the segment with empty samples, making the waiting time not predictable.
        waiting_samples = 32*12
        if waiting_samples <32*12:
            print('!!!Given configuration of waiting samples results in an value, which cannot be uploaded to the AWG!!!')
            return
        waiting_time = waiting_samples/1.25e9
        self.ElementAWG(channels={}, length=waiting_time)
        self.segments[waiting_name] = self.BlockAWG

        #Define Sequence with sequence_step_list
        real_tau_arr = []
        for idx, tau in enumerate(self.tau_arr):
            num_waiting_loops = int(np.rint(tau/waiting_time))
            real_tau_arr.append(waiting_time*num_waiting_loops)

            step = {"step_index" : 6*idx,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_peak0_init_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+1,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+1,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+2,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+2,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_peak0_read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+3,
                        "step_end_cond" : 'always'
                        }
            step = {"step_index" : 6*idx+3,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_peak0_init_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+4,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+4,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+5,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+5,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_peak1_read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 0 if tau == self.tau_arr[-1] else 6*idx+6,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)

        self.tau_arr = real_tau_arr
 
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG_sequence(self.segments, self.sequence_step_list, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
        
    def T1_SQ_alt_exp(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                                t                     
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁
                                                t                     X
        '''        
        if name is None:
            name = 't1-SQ-alt-exp-juptr'

        alternating = True
        freq_sweep=False
        self.tau_arr = np.logspace(np.log10(tau_start), np.log10(tau_stop), num=tau_num)

        #Create pulse sequence for the AWG streamer
        self.segments = {}
        self.sequence_step_list = []

        #Define laser waiting segment segment
        self.BlockAWG = []
        laser_waiting_name = name+'-laser_waiting'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.laser_waiting_time)
        self.segments[laser_waiting_name] = self.BlockAWG

        #Define Pi pulse + read out segment 
        self.BlockAWG = []
        pi_pulse_read_out_name = name+'-pi_pulse_read_out'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[pi_pulse_read_out_name] = self.BlockAWG

        #Define Pi pulse replacement + read out segment 
        self.BlockAWG = []
        pi_pulse_replacement_read_out_name = name+'-pi_pulse_replacement_read_out'
        #Adding the Laser waiting time to the segment to make sure that the segment will always be long enough independend on the pi pulse duration
        self.ElementAWG(channels={}, length=self.pi_pulse)
        self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        self.segments[pi_pulse_replacement_read_out_name] = self.BlockAWG

        #Define waiting Segment
        self.BlockAWG = []
        waiting_name = name+'-waiting'
        #It is recommended to use a multiple of 32, as the AWG only allows to upload sample size with modulus 32 == 0.
        #Otherwise it will fill up the segment with empty samples, making the waiting time not predictable.
        waiting_samples = 32*12
        if waiting_samples <32*12:
            print('!!!Given configuration of waiting samples results in an value, which cannot be uploaded to the AWG!!!')
            return
        waiting_time = waiting_samples/1.25e9
        self.ElementAWG(channels={}, length=waiting_time)
        self.segments[waiting_name] = self.BlockAWG

        #Define Sequence with sequence_step_list
        real_tau_arr = []
        for idx, tau in enumerate(self.tau_arr):
            num_waiting_loops = int(np.rint(tau/waiting_time))
            real_tau_arr.append(waiting_time*num_waiting_loops)

            step = {"step_index" : 6*idx,
                        "step_segment" : 'Jupyter-ensemble-'+laser_waiting_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+1,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+1,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+2,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+2,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_replacement_read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+3,
                        "step_end_cond" : 'always'
                        }
            step = {"step_index" : 6*idx+3,
                        "step_segment" : 'Jupyter-ensemble-'+laser_waiting_name,
                        "step_loops" : 1,
                        "next_step_index" : 6*idx+4,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+4,
                        "step_segment" : 'Jupyter-ensemble-'+waiting_name,
                        "step_loops" : num_waiting_loops,
                        "next_step_index" : 6*idx+5,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)
            step = {"step_index" : 6*idx+5,
                        "step_segment" : 'Jupyter-ensemble-'+pi_pulse_read_out_name,
                        "step_loops" : 1,
                        "next_step_index" : 0 if tau == self.tau_arr[-1] else 6*idx+6,
                        "step_end_cond" : 'always'
                        }
            self.sequence_step_list.append(step)

        self.tau_arr = real_tau_arr
 
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG_sequence(self.segments, self.sequence_step_list, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
    
    def Ramsey_alt_phased(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X                t                 X
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X                t                -X
        '''
        if name is None:
            name = 'ramsey-alt-phased-juptr'

        alternating = True
        freq_sweep=False
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num)

        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time - tau
            self.ElementAWG(channels={}, length=tau)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Second waiting time + tau
            self.ElementAWG(channels={}, length=tau)
            #Pi/2 pulse Phase change cause -pi/2 pulse - done by AWG
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
    
    def Hecho_alt_phased(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X        t/2       X        t/2        X
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X        t/2       X        t/2        -X
        '''
        if name is None:
            name = 'hecho-alt-phased-juptr'
        
        alternating = True
        freq_sweep= False
        if tau_start<self.pi_pulse:
            print('!!!Given configuration of pi-pulse duration, number of pulses and tau_start resulting in negativ values!!!')
            return
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num) - self.pi_pulse #Pi pulse duration is subtracted and thus total tau includes the Pi pulse

        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []

        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
            #Second waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
            #Second waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi/2 pulse Phase change cause -pi/2 pulse - done by AWG
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr + self.pi_pulse, alternating, freq_sweep #Pi pulse duration is subtracted and thus total tau includes the Pi pulse
    
    def Hecho_alt(self, tau_start, tau_stop, tau_num, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X        t/2       X        t/2        X
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X        t/2       X        t/2        -X
        '''
        if name is None:
            name = 'hecho-alt-juptr'

        alternating = True
        freq_sweep=False

        if tau_start<self.pi_pulse:
            print('!!!Given configuration of pi-pulse duration, number of pulses and tau_start resulting in negativ values!!!')
            return
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num) - self.pi_pulse
        
        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []

        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
            #Second waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #Pi pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
            #Second waiting time + tau/2
            self.ElementAWG(channels={}, length=tau/2)
            #3*Pi/2 pulse 
            self.ElementAWG(channels={'MW_0':True}, length=3*self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr+ self.pi_pulse, alternating, freq_sweep
        
    def DEER_alt_phased(self, tau_NV, pi_pulse_dark_spin, mw_start, mw_stop, mw_step, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X        t/2       X        t/2        X
        MW_DS:            ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                                          Freq_1 sweep
                                       
                                       
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi/2▇▁▁▁▁▁▁▁
                                       X        t/2       X        t/2        -X
        MW_DS:            ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
                                                          Freq_1 sweep
        '''
        if name is None:
            name = 'deer-alt-juptr'
        
        if pi_pulse_dark_spin>tau_NV/2:
            print('!!!Duration of tau_NV/2 is smaller than the pi_pulse_dark_spin length. Check the values!!!')
            return
        

        alternating = True
        freq_sweep=True
        num_steps = int(np.rint((mw_stop - mw_start) / mw_step))
        end_freq = mw_start + num_steps * mw_step
        self.tau_arr = np.linspace(mw_start, end_freq, num_steps + 1)
        
        self.LO_freq_1 = end_freq + 100e6
        
        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time + tau/2
            self.ElementAWG(channels={}, length=tau_NV/2)
            #Pi pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
            #Pi pulse for dark spin
            self.ElementAWG(channels={'MW_1':True}, length=pi_pulse_dark_spin, freq_1 = tau)
            #Second waiting time + tau/2
            self.ElementAWG(channels={}, length=tau_NV/2-pi_pulse_dark_spin)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #First waiting time + tau/2
            self.ElementAWG(channels={}, length=tau_NV/2)
            #Pi pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
            #Pi pulse for dark spin
            self.ElementAWG(channels={'MW_1':True}, length=pi_pulse_dark_spin, freq_1 = tau)
            #Second waiting time + tau/2
            self.ElementAWG(channels={}, length=tau_NV/2-pi_pulse_dark_spin)
            #-Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
        
    def CPMG_alt_phased(self, tau_start, tau_stop, tau_num, N, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    X
        Altern.
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    -X
        '''
        if name is None:
            name = 'cpmg-alt-phased-juptr'
        
        if tau_start<2*N*self.pi_pulse:
            print('!!!Given configuration of pi-pulse duration, number of pulses and tau_start resulting in negativ values!!!')
            return
        
        alternating = True
        freq_sweep=False
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num) - 2*N*self.pi_pulse #compensating the pi_pulse run time

        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            
            for i in range(N):
                #First waiting time + tau/2
                self.ElementAWG(channels={}, length=tau/(4*N))
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau/(2*N))
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau/(4*N))
                               
            #Pi/2 pulse Phase change cause -pi/2 pulse - done by AWG
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
                               
            for i in range(N):
                #First waiting time + tau/2
                self.ElementAWG(channels={}, length=tau/(4*N))
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau/(2*N))
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau/(4*N))
                               
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr + 2*N*self.pi_pulse, alternating, freq_sweep
        
    def DEER_CPMG_alt_phased(self, tau_NV, pi_pulse_dark_spin, mw_start, mw_stop, mw_step, N, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    X
        Altern.
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    -X
        '''
        if name is None:
            name = 'deer-cpmg-alt-phased-juptr'
        
        if pi_pulse_dark_spin>(tau_NV- 2*N*self.pi_pulse)/(2*N):
            print('!!!Duration of tau_NV/(2*N) is smaller than the pi_pulse_dark_spin length. Check the values!!!')
            return
        
        alternating = True
        freq_sweep=True
        num_steps = int(np.rint((mw_stop - mw_start) / mw_step))
        end_freq = mw_start + num_steps * mw_step
        self.tau_arr = np.linspace(mw_start, end_freq, num_steps + 1)
        
        self.LO_freq_1 = end_freq + 100e6
        
        tau_NV -= 2*N*self.pi_pulse
        
        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            
            for i in range(N):
                #First waiting time + tau/2
                self.ElementAWG(channels={}, length=tau_NV/(4*N))
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Pi pulse for dark spin
                self.ElementAWG(channels={'MW_1':True}, length=pi_pulse_dark_spin, freq_1 = tau)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau_NV/(2*N)-pi_pulse_dark_spin)
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau_NV/(4*N))
                               
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
                               
            for i in range(N):
                #First waiting time + tau/2
                self.ElementAWG(channels={}, length=tau_NV/(4*N))
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Pi pulse for dark spin
                self.ElementAWG(channels={'MW_1':True}, length=pi_pulse_dark_spin, freq_1 = tau)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau_NV/(2*N)-pi_pulse_dark_spin)
                #Pi pulse
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                #Second waiting time + tau/2
                self.ElementAWG(channels={}, length=tau_NV/(4*N))
                               
            #Pi/2 pulse Phase change cause -pi/2 pulse - done by AWG
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr, alternating, freq_sweep
        
    def XY4_alt_phased(self, tau_start, tau_stop, tau_num, N, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    X
        Altern.
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    -X
        '''
        if name is None:
            name = 'XY4-alt-phased-juptr'
        
        if tau_start<4*N*self.pi_pulse:
            print('!!!Given configuration of pi-pulse duration, number of pulses and tau_start resulting in negativ values!!!')
            return
        
        alternating = True
        freq_sweep=False
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num) - 4*N*self.pi_pulse #compensating the pi_pulse run time
        
        #Trigger AWG to play its sequence, which includes one complete sweep of all waiting times        
        self.ElementAWG(channels={'AWG_Trig':True}, length=self.awg_sync_time)
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            
            for i in range(N):       
                self.ElementAWG(channels={}, length=tau/(2*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(2*4*N))
                
            #-Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
                               
            for i in range(N):
                self.ElementAWG(channels={}, length=tau/(2*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*4*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(2*4*N))
                               
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr+ 4*N*self.pi_pulse, alternating, freq_sweep
    
    def XY8_alt_phased(self, tau_start, tau_stop, tau_num, N, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    X
        Altern.
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    -X
        '''
        if name is None:
            name = 'XY8-alt-phased-juptr'
        
        if tau_start<8*N*self.pi_pulse:
            print('!!!Given configuration of pi-pulse duration, number of pulses and tau_start resulting in negativ values!!!')
            return
        
        alternating = True
        freq_sweep=False
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num) - 8*N*self.pi_pulse #compensating the pi_pulse run time
        
        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            
            for i in range(N):       
                self.ElementAWG(channels={}, length=tau/(2*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(2*8*N))
                
            #-Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
                               
            for i in range(N):
                self.ElementAWG(channels={}, length=tau/(2*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*8*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(2*8*N))
                               
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr+ 8*N*self.pi_pulse, alternating, freq_sweep
        
    def XY16_alt_phased(self, tau_start, tau_stop, tau_num, N, name = None):
        '''
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    X
        Altern.
        Laser(532):       ▇▇▇▇▇▁▁▁▁▁▁|▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁|▁▁▁▁▁▁▁▇▇▇▇▇
        MW:               ▁▁▁▁▁▁▁▇pi/2▇▁|▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁▇pi▇▁▁▁▁▁▁▁▁▁▁|▁▇pi/2▇▁▁▁▁▁▁▁
                                       X    |   t/(4*N)     Y    t/(2*N)       Y    t/(4*N)    |**N    -X
        '''
        if name is None:
            name = 'XY16-alt-phased-juptr'
        
        if tau_start<16*N*self.pi_pulse:
            print('!!!Given configuration of pi-pulse duration, number of pulses and tau_start resulting in negativ values!!!')
            return
        
        alternating = True
        freq_sweep=False
        self.tau_arr = np.linspace(tau_start, tau_stop, num=tau_num) - 16*N*self.pi_pulse #compensating the pi_pulse run time
        
        #Create pulse sequence for the AWG streamer
        self.BlockAWG = []
        
        for tau in self.tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            
            for i in range(N):       
                self.ElementAWG(channels={}, length=tau/(2*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(2*16*N))
                
            #-Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2, phase_0=180)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
            
            #Alternating run
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time)
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
                               
            for i in range(N):
                self.ElementAWG(channels={}, length=tau/(2*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=180)
                self.ElementAWG(channels={}, length=tau/(1*16*N))
                self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, phase_0=90+180)
                self.ElementAWG(channels={}, length=tau/(2*16*N))
                               
            #Pi/2 pulse
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse/2)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        
        self.sample_load_ready_pulsestreamer(name='read_out_jptr')
        
        ensemble_list, sequence_step_list = self.sample_load_ready_AWG(name, self.tau_arr, alternating, freq_sweep, change_freq = True)

        return ensemble_list, sequence_step_list, name, self.tau_arr+ 16*N*self.pi_pulse, alternating, freq_sweep
    
    def sample_load_ready_AWG_for_SPM_tracking(self, res_freq, delta_freq, repetitions):

        def make_segment_block():
            large_seq = []

            for Element in self.BlockAWG:
                phase_0, phase_1, duration, user_MW_0_true, user_MW_1_true, freq_0, freq_1, channels = Element
                delta_0 = abs(self.LO_freq_0 - (self.target_freq_0 if freq_0 is None else freq_0))
                delta_1 = abs(self.LO_freq_1 - (self.target_freq_1 if freq_1 is None else freq_1))
                
                seq_part = {'channel_info' : [
                    {'name': 'a_ch0', 'amp': 0.5 if user_MW_0_true else 0.0, 'freq': delta_0, 'phase': 0+phase_0},
                    {'name': 'a_ch1', 'amp': 0.5 if user_MW_0_true else 0.0, 'freq': delta_0, 'phase': 100+phase_0},
                    {'name': 'a_ch2', 'amp': 0.5 if user_MW_1_true else 0.0, 'freq': delta_1, 'phase': 0+phase_1},
                    {'name': 'a_ch3', 'amp': 0.5 if user_MW_1_true else 0.0, 'freq': delta_1, 'phase': 100+phase_1}],
                    'duration' : duration}
                for ch in channels:
                    seq_part['channel_info'].append({'name': self.channel_names_AWG[ch], 'high': channels[ch]})
                large_seq.append(seq_part)
            return large_seq

        self.AWG_MW_reset()

        #################################################################################
        #Create large pulse block for the AWG
        explicit_steps_list = []
        ensemble_list_raw = []
        names = ["meas"]
        
        #Create pulse sequence for the AWG - measurement block
        self.BlockAWG = []
        left_freq = res_freq-delta_freq
        right_freq = res_freq+delta_freq
        self.LO_freq_0 = res_freq + 100e6
        tau_arr = [left_freq, right_freq]
        for tau in tau_arr:
            #Break after Initalisation/read out
            self.ElementAWG(channels={}, length=self.laser_waiting_time) 
            #Pi pulse - reference
            self.ElementAWG(channels={'MW_0':True}, length=self.pi_pulse, freq_0=tau)
            #Waiting time + read-out
            self.ElementAWG(channels={'PS_Trig':True}, length=self.mw_waiting_time + self.read_out_time)
        ensemble_list_raw.append(make_segment_block())
        explicit_steps_list.append({"step_index" : 0,
                    "step_segment" : "Jupyter-ensemble-"+names[0],
                    "step_loops" : repetitions,
                    "next_step_index" : 0,
                    "step_end_cond" : 'stop'
                    })
        #################################################################################

        ensemble_list = self.sample_ensembles(large_seq=ensemble_list_raw, identifier=names)
        self.debug_ensemble_list = ensemble_list
        sequence_step_list = explicit_steps_list
        self.debug_sequence_step_list = sequence_step_list
        self.AWG.load_ready_sequence_mode(sequence_step_list)
        return ensemble_list, sequence_step_list