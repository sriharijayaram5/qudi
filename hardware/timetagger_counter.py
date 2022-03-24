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
from collections import namedtuple
from enum import Enum

from core.module import Base
from core.configoption import ConfigOption
from interface.slow_counter_interface import SlowCounterInterface
from interface.slow_counter_interface import SlowCounterConstraints
from interface.slow_counter_interface import CountingMode

from interface.recorder_interface import RecorderInterface, RecorderConstraints, RecorderState, RecorderMode

class HWRecorderMode(RecorderMode):
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
    _pixelclock_begin_chn = ConfigOption('pixelclock_begin_chn', 2, missing='error')
    _pixelclock_click_chn = ConfigOption('pixelclock_click_chn', 1, missing='error')
    _pixelclock_end_chn = ConfigOption('pixelclock_end_chn', 3, missing='error')
    _recorder_constraints = RecorderConstraints()

    def on_activate(self):
        """ Start up TimeTagger interface
        """
        self._tagger = tt.createTimeTagger()
        self._count_frequency = 50  # Hz

        self._curr_mode = HWRecorderMode.UNCONFIGURED
        self._curr_state = RecorderState.UNLOCKED
        self._create_recorder_constraints()
        self.is_measurement_running = False

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
            self._channel_apd = self._channel_apd_0
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
        
        self._curr_mode = HWRecorderMode.COUNTER
        self._curr_state = RecorderState.ARMED

        self.log.info('set up counter with {0}'.format(self._count_frequency))
        return 0

    def get_counter_channels(self):
        if self._mode < 2:
            return [self._channel_apd]
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

        rc.recorder_modes = [HWRecorderMode.UNCONFIGURED]

        rc.recorder_mode_states[HWRecorderMode.UNCONFIGURED] = [RecorderState.LOCKED, RecorderState.UNLOCKED]

        rc.recorder_mode_params[HWRecorderMode.UNCONFIGURED] = {}

        rc.recorder_mode_measurements = {HWRecorderMode.UNCONFIGURED: TimeTaggerMeasurementMode.DUMMY}

        # feature set 1 = 'Counting'
        rc.recorder_modes.append(HWRecorderMode.COUNTER)

        # configure possible states in a mode
        rc.recorder_mode_states[HWRecorderMode.COUNTER] = [RecorderState.IDLE, RecorderState.BUSY]

        # configure required paramaters for a mode
        rc.recorder_mode_params[HWRecorderMode.COUNTER] = {'count_frequency': 100}

        # configure default parameter for mode
        rc.recorder_mode_params_defaults[HWRecorderMode.COUNTER] = {}  # no defaults

        # configure required measurement method
        rc.recorder_mode_measurements[HWRecorderMode.COUNTER] = TimeTaggerMeasurementMode.COUNTER

        # feature set 2 = 'Continuous ESR'
        rc.recorder_modes.append(HWRecorderMode.ESR)
        
        # configure possible states in a mode
        rc.recorder_mode_states[HWRecorderMode.ESR] = [RecorderState.IDLE, RecorderState.BUSY]

        # configure required paramaters for a mode
        rc.recorder_mode_params[HWRecorderMode.ESR] = {'mw_frequency_list': [],
                                                        'mw_power': -30,
                                                        'count_frequency': 100,
                                                        'num_meas': 100}

        # configure defaults for mode
        rc.recorder_mode_params_defaults[HWRecorderMode.ESR] = {}     # no defaults

        # configure measurement method
        rc.recorder_mode_measurements[HWRecorderMode.ESR] = TimeTaggerMeasurementMode.ESR

        # feature set 16 = 'Pixel Clock'
        rc.recorder_modes.append(HWRecorderMode.PIXELCLOCK)
        rc.recorder_modes.append(HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B)
        
        # configure possible states in a mode
        rc.recorder_mode_states[HWRecorderMode.PIXELCLOCK] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]
        rc.recorder_mode_states[HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]

        # configure required paramaters for a mode
        rc.recorder_mode_params[HWRecorderMode.PIXELCLOCK] = {}
        rc.recorder_mode_params[HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B] = {'mw_frequency': 2.8e9,
                                                                            'mw_power': -30,
                                                                            'num_meas': 100}

        # configure defaults for mode
        rc.recorder_mode_params_defaults[HWRecorderMode.PIXELCLOCK] = {}               # no defaults
        rc.recorder_mode_params_defaults[HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B] = {}  # no defaults

        rc.recorder_mode_measurements[HWRecorderMode.PIXELCLOCK] = TimeTaggerMeasurementMode.PIXELCLOCK
        rc.recorder_mode_measurements[HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B] = TimeTaggerMeasurementMode.PIXELCLOCK

    def get_recorder_constraints(self):
        """ Retrieve the hardware constrains from the recorder device.

        @return RecorderConstraints: object with constraints for the recorder
        """
        return self._recorder_constraints

    def configure_recorder(self, mode, params):
        """ Configures the recorder mode for current measurement. 

        @param HWRecorderMode mode: mode of recorder, as available from 
                                  HWRecorderMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """
        dev_state = self._curr_state
        curr_mode = self._curr_mode
        self._curr_meas_params = params

        if (dev_state == RecorderState.BUSY): 
            # on the fly configuration (in BUSY state) is only allowed in CW_MW mode.
            self.log.error(f'TimeTagger cannot be configured in the '
                           f'requested mode "{HWRecorderMode.name(mode)}", since the device '
                           f'state is in "{dev_state}". Stop ongoing '
                           f'measurements and make sure that the device is '
                           f'connected to be able to configure if '
                           f'properly.')
            return -1
            

        # check at first if mode is available
        limits = self.get_recorder_constraints()

        if mode not in limits.recorder_modes:
            self.log.error(f'Requested mode "{HWRecorderMode.name(mode)}" not available.')
            return -1

        ret_val = 0
        # the associated error message for a -1 return value should come from 
        # the method which was called (with a reason, why configuration could 
        # not happen).

        # after all the checks are successful, delegate the call to the 
        # appropriate preparation function.
        if mode == HWRecorderMode.UNCONFIGURED:
            # not sure whether it makes sense to configure the device 
            # deliberately in an unconfigured state, it sounds like a 
            # contradiction in terms, but it might be important if device is reset
            pass

        elif mode == HWRecorderMode.PIXELCLOCK or HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B:
            ret_val = self._prepare_pixelclock(pixelclock_begin_chn=self._pixelclock_begin_chn,
                                                pixelclock_click_chn=self._pixelclock_click_chn,
                                                pixelclock_end_chn=self._pixelclock_end_chn,
                                                num_meas=params['num_meas'])

        elif mode == HWRecorderMode.COUNTER:
            ret_val = self._prepare_counter(counting_window=1/params['count_frequency'])

        elif mode == HWRecorderMode.ESR:
            ret_val = self._prepare_cw_esr(freq_list=params['mw_frequency_list'], 
                                          num_esr_runs=params['num_meas'])

        if ret_val == -1:
            self._curr_mode = HWRecorderMode.UNCONFIGURED
        else:
            self._curr_mode = mode
            self._curr_state = RecorderState.IDLE

        return ret_val
    
    def _prepare_pixelclock(self, pixelclock_begin_chn, pixelclock_click_chn, pixelclock_end_chn, num_meas):
        self.cbm_counter = tt.CountBetweenMarkers(
                    self._tagger,
                    click_channel=self._pixelclock_click_chn,
                    begin_channel=self._pixelclock_begin_chn,
                    end_channel=self._pixelclock_end_chn,
                    n_values=num_meas
                )
        self.recorder = self.cbm_counter
        return 0
    
    def _prepare_cw_esr(self, freq_list, num_esr_runs):
        self.cbm_counter = tt.CountBetweenMarkers(
                    self._tagger,
                    click_channel=self._pixelclock_click_chn,
                    begin_channel=self._pixelclock_begin_chn,
                    end_channel=self._pixelclock_end_chn,
                    n_values=len(freq_list)*num_esr_runs
                )

        self.recorder = self.cbm_counter
        return 0

    def start_recorder(self, arm=False):
        """ Start recorder 
        start recorder with mode as configured 
        If pixel clock based methods, will begin on first trigger
        If not first configured, will cause an error
        
        @param bool: arm: specifies armed state with regard to pixel clock trigger
        
        @return bool: success of command
        """
        mode, params = self._curr_mode, self._curr_meas_params
        self._curr_mode_params = params
        state = self._curr_state
        meas_type = self._recorder_constraints.recorder_mode_measurements[self._curr_mode]
        
        if state == RecorderState.LOCKED:
            self.log.warning('TT has not been unlocked.')
            return False 

        elif mode == HWRecorderMode.UNCONFIGURED:
            self.log.warning('TT has not been configured.')
            return  False

        elif (state != RecorderState.IDLE) and (state != RecorderState.IDLE_UNACK):
            self.log.warning('TimeTagger is not in Idle mode to start the measurement.')
            return False 

        num_meas = params['num_meas']

        if arm and meas_type.movement  != 'line':
            self.log.warning('TimeTagger: attempt to set ARMED state for a continuous measurement mode')
            return False 
        
        # data format
        # Pixel clock (line methods)
        if meas_type.movement == 'line':
            if mode == HWRecorderMode.PIXELCLOCK or HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B:
                self._total_pulses = num_meas 
                self._counted_pulses = 0

                self._curr_frame = []
                self._meas_res = np.zeros((num_meas))
                
                self.recorder.clear()

                self._curr_state = RecorderState.ARMED

        # Esr, Pulsed (point methods)
        elif meas_type.movement == 'point':
            if mode == HWRecorderMode.ESR:
                self._meas_esr_res = np.zeros((num_meas, len(self._curr_meas_params['mw_frequency_list'])))
                self._esr_counter = 0
                self._current_esr_meas = []

                self.recorder.clear()

                self._curr_state = RecorderState.ARMED

            elif mode == HWRecorderMode.GENERAL_PULSED:
                #self._meas_pulsed_res = None    # method for indeterminate size arrays

                self._meas_pulsed_res = np.zeros((num_meas, self._meas_length_pulse + 1),  #include frame_num
                                                  dtype='<i4')
                self._total_pulses = num_meas 

                self._dev.ctrl.measurementLength.set(self._meas_length_pulse - 1)
                self._pulsed_counter = 0
                self._current_pulsed_meas = []

            else:
                self.log.error('TimeTagger configuration error; inconsistent modality')

        else:
            self.log.error(f'TimeTagger: method {mode}, movement_type={meas_type.movement}'
                            ' not implemented yet')
            return False 

        self.skip_data = False

        # Pulsed method
        if mode == HWRecorderMode.GENERAL_PULSED:
            # General pulsed mode operates through ddr4 controller
            # number of measurments set in configure_recorder method
            pass

        else:
            # all other methods
            self.recorder.start()
            self.is_measurement_running = True

        return True 

    def get_measurements(self, meas_keys=None):
        """ get measurements
        returns the measurement array in integer format, (blocking, changes state)

        @param (list): meas_keys:  list of measurement keys to be returned;
                                   keys which do not exist in measurment object are returned as None;
                                   If None is passed, only 'counts' is returned 

        @return int_array: array of measurement as tuple elements, format depends upon 
                           current mode setting
        """
        ret = {'counts':None, 'int_time':None, 'counts2':None, 'counts_diff': None}
        
        if self._curr_mode == HWRecorderMode.PIXELCLOCK or HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B:
            while True:
                if self.recorder.ready():
                    break

            # ['counts', 'int_time', 'counts2', 'counts_diff']
            data = self.recorder.getData()
            ret['counts'] = data

            data = self.recorder.getBinWidths()
            ret['int_time'] = data/1e12 # returns in ps
        
        if self._curr_mode == HWRecorderMode.ESR:
            while True:
                if self.recorder.ready():
                    break

            # ['counts', 'int_time', 'counts2', 'counts_diff']
            data = self.recorder.getData().reshape(self._curr_meas_params['num_meas'], len(self._curr_meas_params['mw_frequency_list']))
            ret['counts'] = data

            data = self.recorder.getBinWidths().reshape(self._curr_meas_params['num_meas'], len(self._curr_meas_params['mw_frequency_list']))
            ret['int_time'] = data/1e12 # returns in ps
            ret['counts'] = np.divide(ret['counts'].astype(float), ret['int_time'])
            

        # released
        self._curr_state = RecorderState.IDLE
        ret_list = [ret[i] for i in meas_keys]
        
        return ret_list
    
    def get_available_measurements(self, meas_keys=None):
        ret_list = []

        if self._curr_mode == HWRecorderMode.PIXELCLOCK or HWRecorderMode.PIXELCLOCK_SINGLE_ISO_B:
            # ['counts', 'int_time', 'counts2', 'counts_diff']
            data = self.recorder.getData()
            ret_list.append(data)

            data = self.recorder.getBinWidths()
            ret_list.append(data)

            ret_list.append(None)
            ret_list.append(None)

        if self._curr_mode == HWRecorderMode.ESR:
            # ['counts', 'int_time', 'counts2', 'counts_diff']
            data = self.recorder.getData().reshape(self._curr_meas_params['num_meas'], len(self._curr_meas_params['mw_frequency_list']))
            ret_list.append(data)

            data = self.recorder.getBinWidths().reshape(self._curr_meas_params['num_meas'], len(self._curr_meas_params['mw_frequency_list']))
            ret_list.append(data)

            ret_list.append(None)
            ret_list.append(None)
    
    def get_current_device_mode(self):
        """ Get the current device mode with its configuration parameters

        @return: (mode, params)
                HWRecorderMode.mode mode: the current recorder mode 
                dict params: the current configuration parameter
        """
        return self._curr_mode, None
    
    def get_current_device_state(self):
        """  get_current_device_state
        returns the current device state

        @return RecorderState.state
        """
        return self._curr_state
    
    def get_measurement_methods(self):
        """ gets the possible measurement methods
        """
        return None
    
    def get_parameters_for_modes(self, mode=None):
        """ Returns the required parameters for the modes

        @param HWRecorderMode mode: specifies the mode for sought parameters
                                  If mode=None, all modes with their parameters 
                                  are returned. Otherwise specific mode 
                                  parameters are returned  

        @return dict: containing as keys the HWRecorderMode.mode and as values a
                      dictionary with all parameters associated to the mode.
                      
                      Example return with mode=HWRecorderMode.CW_MW:
                            {HWRecorderMode.CW_MW: {'countwindow': 10,
                                                  'mw_power': -30}}  
        """

        #TODO: think about to remove this interface method and put the content 
        #      of this method into self.get_recorder_limits() 

        # note, this output should coincide with the recorder_modes from 
        # get_recorder_constraints()
        
        rc = self.get_recorder_constraints()

        if mode not in rc.recorder_modes:
            self.log.warning(f'Requested mode "{mode}" is not in the available '
                             f'modes of the ProteusQ. Request skipped.')
            return {}

        if mode is None:
            return rc.recorder_mode_params
        else:
            return {mode: rc.recorder_mode_params[mode]}
        
    def stop_measurement(self):
        self.recorder.stop()
        self.is_measurement_running = False
    
    def get_current_measurement_method_name(self):
        """ gets the name of the measurment method currently in use
        
        @return string
        """
        curr_mm = self.get_current_measurement_method()
        return curr_mm.name
    
    def get_current_measurement_method(self):
        """ get the current measurement method
        (Note: the measurment method cannot be set directly, it is an aspect of the measurement mode)

        @return MicrowaveQMeasurementMode
        """
        rc = self._recorder_constraints
        return rc.recorder_mode_measurements[self._curr_mode]