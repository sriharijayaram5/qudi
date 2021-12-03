# -*- coding: utf-8 -*-

"""
This file contains the Qudi hardware module to use TimeTagger as a counter.

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

import TimeTagger as tt
import time
import numpy as np

from core.module import Base
from core.configoption import ConfigOption
from interface.slow_counter_interface import SlowCounterInterface
from interface.slow_counter_interface import SlowCounterConstraints
from interface.slow_counter_interface import CountingMode

from interface.recorder_interface import RecorderInterface, RecorderConstraints, RecorderState, RecorderMode

class TimeTaggerMode(RecorderMode):
    # starting methods
    UNCONFIGURED             = 0
    DUMMY                    = 1

    # pixel clock counting methods
    PIXELCLOCK               = 2
    PIXELCLOCK_SINGLE_ISO_B  = 3
    PIXELCLOCK_N_ISO_B       = 4
    PIXELCLOCK_TRACKED_ISO_B = 5

    # continous counting methods
    CW_MW                    = 6
    ESR                      = 7
    COUNTER                  = 8
    CONTINUOUS_COUNTING      = 9

    # advanced measurement mode
    PULSED_ESR               = 10
    GENERAL_PULSED           = 11

    @classmethod
    def name(cls,val):
        return { v:k for k,v in dict(vars(cls)).items() if isinstance(v,int)}.get(val, None) 
    
class TimeTaggerMeasurementMode(namedtuple('TimeTaggerMeasurementMode', 'value name movement'), Enum):
    DUMMY                   = -1, 'DUMMY', 'null'
    COUNTER                 = 0, 'COUNTER', 'null'
    PIXELCLOCK              = 1, 'PIXELCLOCK', 'line' 
    PIXELCLOCK_SINGLE_ISO_B = 2, 'PIXELCLOCK_SINGLE_ISO_B', 'line'
    PIXELCLOCK_N_ISO_B      = 3, 'PIXELCLOCK_N_ISO_B', 'line'
    ESR                     = 4, 'ESR', 'point'
    PULSED_ESR              = 5, 'PULSED_ESR', 'point'
    GENERAL_PULSED          = 6, 'GENERAL_PULSED', 'point'

    def __str__(self):
        return self.name

    def __int__(self):
        return self.value

class TimeTaggerCounter(Base, SlowCounterInterface, RecorderInterface):
    """ Using the TimeTagger as a slow counter.

    Example config for copy-paste:

    timetagger_slowcounter:
        module.Class: 'timetagger_counter.TimeTaggerCounter'
        timetagger_channel_apd_0: 0
        timetagger_channel_apd_1: 1
        timetagger_sum_channels: 2

    """

    _channel_apd_0 = ConfigOption('timetagger_channel_apd_0', missing='error')
    _channel_apd_1 = ConfigOption('timetagger_channel_apd_1', None, missing='warn')
    _sum_channels = ConfigOption('timetagger_sum_channels', False)
    _recorder_constraints = RecorderConstraints()

    def on_activate(self):
        """ Start up TimeTagger interface
        """
        self._tagger = tt.createTimeTagger()
        self._count_frequency = 50  # Hz

        self._curr_mode = TimeTaggerMode.UNCONFIGURED
        self._curr_state = RecorderState.UNLOCKED

        if self._sum_channels and self._channel_apd_1 is None:
            self.log.error('Cannot sum channels when only one apd channel given')

        ## self._mode can take 3 values:
        # 0: single channel, no summing
        # 1: single channel, summed over apd_0 and apd_1
        # 2: dual channel for apd_0 and apd_1
        if self._sum_channels:
            self._mode = 1
        elif self._channel_apd_1 is None:
            self._mode = 0
        else:
            self._mode = 2

    def on_deactivate(self):
        """ Shut down the TimeTagger.
        """
        tt.freeTimeTagger(self._tagger)

    def set_up_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the TimeTagger for timing

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock

        @return int: error code (0:OK, -1:error)
        """

        self._count_frequency = clock_frequency
        return 0

    def set_up_counter(self,
                       counter_channels=None,
                       sources=None,
                       clock_channel=None,
                       counter_buffer=None):
        """ Configures the actual counter with a given clock.

        @param str counter_channel: optional, physical channel of the counter
        @param str photon_source: optional, physical channel where the photons
                                  are to count from
        @param str counter_channel2: optional, physical channel of the counter 2
        @param str photon_source2: optional, second physical channel where the
                                   photons are to count from
        @param str clock_channel: optional, specifies the clock channel for the
                                  counter
        @param int counter_buffer: optional, a buffer of specified integer
                                   length, where in each bin the count numbers
                                   are saved.

        @return int: error code (0:OK, -1:error)
        """

        # currently, parameters passed to this function are ignored -- the channels used and clock frequency are
        # set at startup
        if self._mode == 1:
            channel_combined = tt.Combiner(self._tagger, channels = [self._channel_apd_0, self._channel_apd_1])
            self._channel_apd = channel_combined.getChannel()

            self.counter = tt.Counter(
                self._tagger,
                channels=[self._channel_apd],
                binwidth=int((1 / self._count_frequency) * 1e12),
                n_values=1
            )
        elif self._mode == 2:
            self.counter0 = tt.Counter(
                self._tagger,
                channels=[self._channel_apd_0],
                binwidth=int((1 / self._count_frequency) * 1e12),
                n_values=1
            )

            self.counter1 = tt.Counter(
                self._tagger,
                channels=[self._channel_apd_1],
                binwidth=int((1 / self._count_frequency) * 1e12),
                n_values=1
            )
        else:
            self._channel_apd = self._channel_apd_0
            self.counter = tt.Counter(
                self._tagger,
                channels=[self._channel_apd],
                binwidth=int((1 / self._count_frequency) * 1e12),
                n_values=1
            )
        
        self._curr_mode = TimeTaggerMode.COUNTER
        self._curr_state = RecorderState.IDLE

        self.log.info('set up counter with {0}'.format(self._count_frequency))
        return 0

    def get_counter_channels(self):
        if self._mode < 2:
            return self._channel_apd
        else:
            return [self._channel_apd_0, self._channel_apd_1]

    def get_constraints(self):
        """ Get hardware limits the device

        @return SlowCounterConstraints: constraints class for slow counter

        FIXME: ask hardware for limits when module is loaded
        """
        constraints = SlowCounterConstraints()
        constraints.max_detectors = 2
        constraints.min_count_frequency = 1e-3
        constraints.max_count_frequency = 10e9
        constraints.counting_mode = [CountingMode.CONTINUOUS]
        return constraints

    def get_counter(self, samples=None):
        """ Returns the current counts per second of the counter.

        @param int samples: if defined, number of samples to read in one go

        @return numpy.array(uint32): the photon counts per second
        """

        time.sleep(2 / self._count_frequency)
        if self._mode < 2:
            return self.counter.getData() * self._count_frequency
        else:
            return np.array([self.counter0.getData() * self._count_frequency,
                             self.counter1.getData() * self._count_frequency])

    def close_counter(self):
        """ Closes the counter and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        self._tagger.reset()
        self._curr_state = RecorderState.UNLOCKED
        return 0

    def close_clock(self):
        """ Closes the clock and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return 0
    
    # ==========================================================================
    #                 Recorder Interface Implementation
    # ==========================================================================

    def _create_recorder_constraints(self):

        rc = self._recorder_constraints

        rc.max_detectors = 1

        rc.recorder_mode_params = {}

        rc.recorder_modes = [TimeTaggerMode.UNCONFIGURED]

        rc.recorder_mode_states[TimeTaggerMode.UNCONFIGURED] = [RecorderState.LOCKED, RecorderState.UNLOCKED]

        rc.recorder_mode_params[TimeTaggerMode.UNCONFIGURED] = {}

        rc.recorder_mode_measurements = {TimeTaggerMode.UNCONFIGURED: TimeTaggerMeasurementMode.DUMMY}

        # feature set 1 = 'Counting'
        rc.recorder_modes.append(TimeTaggerMode.COUNTER)

        # configure possible states in a mode
        rc.recorder_mode_states[TimeTaggerMode.COUNTER] = [RecorderState.IDLE, RecorderState.BUSY]

        # configure required paramaters for a mode
        rc.recorder_mode_params[TimeTaggerMode.COUNTER] = {'count_frequency': 100}

        # configure default parameter for mode
        rc.recorder_mode_params_defaults[TimeTaggerMode.COUNTER] = {}  # no defaults

        # configure required measurement method
        rc.recorder_mode_measurements[TimeTaggerMode.COUNTER] = TimeTaggerMeasurementMode.COUNTER

        # feature set 2 = 'Continuous ESR'
        rc.recorder_modes.append(TimeTaggerMode.ESR)
        
        # configure possible states in a mode
        rc.recorder_mode_states[TimeTaggerMode.ESR] = [RecorderState.IDLE, RecorderState.BUSY]

        # configure required paramaters for a mode
        rc.recorder_mode_params[TimeTaggerMode.ESR] = {'mw_frequency_list': [],
                                                        'mw_power': -30,
                                                        'count_frequency': 100,
                                                        'num_meas': 100}

        # configure defaults for mode
        rc.recorder_mode_params_defaults[TimeTaggerMode.ESR] = {}     # no defaults

        # configure measurement method
        rc.recorder_mode_measurements[TimeTaggerMode.ESR] = TimeTaggerMeasurementMode.ESR

        # feature set 16 = 'Pixel Clock'
        rc.recorder_modes.append(TimeTaggerMode.PIXELCLOCK)
        rc.recorder_modes.append(TimeTaggerMode.PIXELCLOCK_SINGLE_ISO_B)
        
        # configure possible states in a mode
        rc.recorder_mode_states[TimeTaggerMode.PIXELCLOCK] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]
        rc.recorder_mode_states[TimeTaggerMode.PIXELCLOCK_SINGLE_ISO_B] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]

        # configure required paramaters for a mode
        rc.recorder_mode_params[TimeTaggerMode.PIXELCLOCK] = {'mw_frequency': 2.8e9,
                                                            'num_meas': 100}
        rc.recorder_mode_params[TimeTaggerMode.PIXELCLOCK_SINGLE_ISO_B] = {'mw_frequency': 2.8e9,
                                                                            'mw_power': -30,
                                                                            'num_meas': 100}

        # configure defaults for mode
        rc.recorder_mode_params_defaults[TimeTaggerMode.PIXELCLOCK] = {}               # no defaults
        rc.recorder_mode_params_defaults[TimeTaggerMode.PIXELCLOCK_SINGLE_ISO_B] = {}  # no defaults

        rc.recorder_mode_measurements[TimeTaggerMode.PIXELCLOCK] = TimeTaggerMeasurementMode.PIXELCLOCK
        rc.recorder_mode_measurements[TimeTaggerMode.PIXELCLOCK_SINGLE_ISO_B] = TimeTaggerMeasurementMode.PIXELCLOCK

    def get_recorder_constraints(self):
        """ Retrieve the hardware constrains from the recorder device.

        @return RecorderConstraints: object with constraints for the recorder
        """
        return self._recorder_constraints

    def configure_recorder(self, mode, params):
        """ Configures the recorder mode for current measurement. 

        @param MicrowaveQMode mode: mode of recorder, as available from 
                                  MicrowaveQMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """
        dev_state = self._curr_state
        curr_mode = self._curr_mode

        if (dev_state == RecorderState.BUSY): 
            # on the fly configuration (in BUSY state) is only allowed in CW_MW mode.
            self.log.error(f'TimeTagger cannot be configured in the '
                           f'requested mode "{TimeTaggerMode.name(mode)}", since the device '
                           f'state is in "{dev_state}". Stop ongoing '
                           f'measurements and make sure that the device is '
                           f'connected to be able to configure if '
                           f'properly.')
            return -1
            

        # check at first if mode is available
        limits = self.get_recorder_constraints()

        if mode not in limits.recorder_modes:
            self.log.error(f'Requested mode "{TimeTaggerMode.name(mode)}" not available.')
            return -1

        ret_val = 0
        # the associated error message for a -1 return value should come from 
        # the method which was called (with a reason, why configuration could 
        # not happen).

        # after all the checks are successful, delegate the call to the 
        # appropriate preparation function.
        if mode == TimeTaggerMode.UNCONFIGURED:
            # not sure whether it makes sense to configure the device 
            # deliberately in an unconfigured state, it sounds like a 
            # contradiction in terms, but it might be important if device is reset
            pass

        elif mode == TimeTaggerMode.PIXELCLOCK:
            ret_val = self._prepare_pixelclock(freq=params['mw_frequency'])

        elif mode == TimeTaggerMode.PIXELCLOCK_SINGLE_ISO_B:
            #TODO: make proper conversion of power to mw gain
            ret_val = self._prepare_pixelclock_single_iso_b(freq=params['mw_frequency'], 
                                                           power=params['mw_power'])

        elif mode == TimeTaggerMode.COUNTER:
            ret_val = self._prepare_counter(counting_window=1/params['count_frequency'])

        elif mode == MicrowaveQMode.ESR:
            ret_val = self._prepare_cw_esr(freq_list=params['mw_frequency_list'], 
                                          count_freq=params['count_frequency'],
                                          power=params['mw_power'])

        if ret_val == -1:
            self._curr_mode = TimeTaggerMode.UNCONFIGURED
        else:
            self._curr_mode = mode
            self._curr_state = RecorderState.IDLE

        return ret_val

    
