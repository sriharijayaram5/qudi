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
from interface.recorder_interface import RecorderInterface
from logic.generic_logic import GenericLogic
from interface.odmr_counter_interface import ODMRCounterInterface
from interface.pulser_interface import PulserInterface

class PulseSequence:
    '''
    A pulse sequence to be loaded that is made of PulseBlock instances. The pulse blocks can be repeated
    as well and multiple can be added.
    '''
    def __init__(self):
        self.pulse_dict = {0:[], 1:[], 2:[], 3:[], 4:[], 5:[], 6:[], 7:[]}

    def append(self, block_list):
        '''
        append a list of tuples of type: 
        [(PulseBlock_instance_1, n_repetitions), (PulseBlock_instance_2, n_repetitions)]
        '''
        for block, n in block_list:
            for i in range(n):
                for key in block.block_dict.keys():
                    self.pulse_dict[key].extend(block.block_dict[key]/1e-9)

    
class PulseBlock:
    '''
    Small repeating pulse blocks that can be appended to a PulseSequence instance
    '''
    def __init__(self):
        self.block_dict = {0:[], 1:[], 2:[], 3:[], 4:[], 5:[], 6:[], 7:[]}
    
    def append(self, init_length, channels, repetition):
        '''
        init_length in s; will be converted by sequence class to ns
        channels are digital channels of PS in swabian language
        '''
        tf = {True:1, False:0}
        for i in range(repetition):
            for chn in channels.keys():
                self.block_dict[chn].extend([(init_length, tf[channels[chn]])])    

class ODMRCounterInterfuse(GenericLogic, ODMRCounterInterface, PulserInterface, RecorderInterface):
    """ This is the Interfuse class supplies the controls for a simple ODMR with counter and pulser."""


    slowcounter = Connector(interface='RecorderInterface')
    pulser = Connector(interface='PulserInterface')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._odmr_length = 100

    def on_activate(self):
        """ Initialisation performed during activation of the module."""
        self._pulser = self.pulser()
        self._sc_device = self.slowcounter()  # slow counter device

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

        d_ch = {0: False , 1: False , 2: False , 3: False , 4: False , 5: False , 6: False , 7: False }
        clear = lambda x: {i:False for i in x.keys()}
        
        seq = PulseSequence()
            
        block_1 = PulseBlock()

        d_ch = clear(d_ch)
        d_ch[self._pulser._mw_trig] = True
        d_ch[self._pulser._laser] = True
        d_ch[self._pulser._mw_switch] = True
        d_ch[self._pulser._pixel_start] = True
        block_1.append(init_length = 1/clock_frequency, channels = d_ch, repetition = 1)

        d_ch = clear(d_ch)
        d_ch[self._pulser._pixel_stop] = True
        block_1.append(init_length = 1e-6, channels = d_ch, repetition = 1)

        seq.append([(block_1, 1)])

        pulse_dict = seq.pulse_dict

        self._pulser.load_swabian_sequence(pulse_dict)
        return 0

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

    def count_odmr(self, length = 100):
        """ Sweeps the microwave and returns the counts on that sweep.

        @param int length: length of microwave sweep in pixel

        @return float[]: the photon counts per second
        """
        self._sc_device.start_recorder()
        counts = np.zeros((len(self.get_odmr_channels()), length))

        self._pulser.pulser_on(n=length)
        counts[:, i] = self._sc_device.get_measurements('counts')[0]

        return False, counts

    def close_odmr(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return self._sc_device.stop_measurement()

    def close_odmr_clock(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return self._sc_device.stop_measurement()

    def get_odmr_channels(self):
        """ Return a list of channel names.

        @return list(str): channels recorded during ODMR measurement
        """
        return ['APD0']