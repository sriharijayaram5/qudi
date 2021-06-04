# -*- coding: utf-8 -*-
"""
Hardware implementation of generic hardware control device microwaveq.

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

from datetime import datetime
from deprecation import deprecated
from qtpy import QtCore
import threading
import numpy as np
import time
import struct
from enum import Enum

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from interface.slow_counter_interface import SlowCounterInterface, SlowCounterConstraints, CountingMode
from interface.recorder_interface import RecorderInterface, RecorderMode, RecorderConstraints, \
                                         RecorderState, RecorderStateMachine 
from interface.microwave_interface import MicrowaveInterface, MicrowaveLimits, MicrowaveMode, TriggerEdge
from interface.odmr_counter_interface import ODMRCounterInterface

from .microwaveq_py.microwaveQ import microwaveQ


class MicrowaveQFeatures(Enum):
    """ Prototype class, to be fulfilled at time of use
        Currently, these values are defined by the microwaveQ/microwaveQ.py deployment interface
        Note:  This is a manual transcription of MicrowaveQ features from the microwaveq/microwaveQ.py interface
               They are transcribed here since this is specific to ProteusQ implementation.  This 
               requires periodic update with the MicrowaveQ defintions
    """
    UNCONFIGURED              = 0
    CONTINUOUS_COUNTING       = 1
    CONTINUOUS_ESR            = 2
    RABI                      = 4
    PULSED_ESR                = 8
    PIXEL_CLOCK               = 16
    EXT_TRIGGERED_MEASUREMENT = 32
    ISO                       = 64

    def __int__(self):
        return self.value


class MicrowaveQ(Base, SlowCounterInterface, RecorderInterface):
    """ Hardware module implementation for the microwaveQ device.

    Example config for copy-paste:

    mq:
        module.Class: 'microwaveQ.microwaveq.MicrowaveQ'
        ip_address: '192.168.2.10'
        port: 55555
        unlock_key: <your obtained key, either in hex or number> e.g. of the form: 51233412369010369791345065897427812359


    Implementation Idea:
        This hardware module implements 4 interface methods, the
            - RecorderInterface
            - MicrowaveInterface
            - ODMRCounterInterface
            - SlowCounterInterface
        For the main purpose of the microwaveQ device, the interface 
        RecorderInterface contains the major methods. The other 3 remaining 
        interfaces have been implemented to use this device with different
        logic module.
        The main state machinery is use from the RecorderInterface, i.e. 
        whenever calling from a different interface than the RecorderInterface
        make sure to either recycle the methods from the RecorderInterface and
        to use the state machinery of the RecorderInterface.

        At the very end, the all the interface methods are responsible to set 
        and check the state of the device.


    TODO: implement signal for state transition in the RecorderState (emit a 
          signal in the method self._set_current_device_state)
    """

    _modclass = 'MicrowaveQ'
    _modtype = 'hardware'

    __version__ = '0.1.2'

    _CLK_FREQ_FPGA = 153.6e6 # is used to obtain the correct mapping of signals.

    ip_address = ConfigOption('ip_address', default='192.168.2.10')
    port = ConfigOption('port', default=55555, missing='info')
    unlock_key = ConfigOption('unlock_key', missing='error')
    gain_cali_name = ConfigOption('gain_cali_name', default='')

    sigNewData = QtCore.Signal(tuple)
    sigLineFinished = QtCore.Signal()

    #_threaded = True 
    _threaded = False  # for debugging 

    _mq_state = RecorderStateMachine()
    _mq_state.set_allowed_transitions(
        transitions={RecorderState.DISCONNECTED: [RecorderState.LOCKED],
                     RecorderState.LOCKED: [RecorderState.UNLOCKED, RecorderState.DISCONNECTED],
                     RecorderState.UNLOCKED: [RecorderState.IDLE, RecorderState.DISCONNECTED],
                     RecorderState.IDLE: [RecorderState.ARMED, RecorderState.BUSY, RecorderState.DISCONNECTED],
                     RecorderState.ARMED: [RecorderState.IDLE, RecorderState.BUSY, RecorderState.DISCONNECTED], 
                     RecorderState.BUSY: [RecorderState.IDLE, RecorderState.DISCONNECTED]
                     }, 
                     initial_state=RecorderState.DISCONNECTED
                    )

    _mq_curr_mode = RecorderMode.UNCONFIGURED
    _mq_curr_mode_params = {} # store here the current configuration


    #FIXME: remove threading components and use Qt Threads instead!
    result_available = threading.Event()

    _SLOW_COUNTER_CONSTRAINTS = SlowCounterConstraints()
    _RECORDER_CONSTRAINTS = RecorderConstraints()

    #DGC _meas_mode = 'pixel'  # measurement modes: counter, pixel, esr
    #DGC _meas_mode_available = ['dummy', 'counter', 'pixel', 'esr', 'single-isob', 'n-isob']

    #DGC _device_status = 'idle'  # can be idle, armed or running
    _meas_running = False   # this variable will be set whenever a measurement has stopped

    _stop_request = False   # this variable will be internally set to request a stop

    # measurement variables
    _DEBUG_MODE = False
    _curr_frame = []
    _curr_frame_int = None
    _curr_frame_int_arr = []

    # variables for ESR measurement
    _esr_counter = 0
    _esr_count_frequency = 100 # in Hz

    # for MW interface:

    _mw_running = False
    _mw_mode = 'cw'
    _mw_cw_frequency = 2.89e9 # in Hz
    #FIXME: Power not used so far
    _mw_cw_power = -30 # in dBm
    _mw_freq_list = []
    _mw_power = -25 # not exposed to interface!!!

    # settings for iso-B mode
    _iso_b_freq_list = [500e6] # in MHz
    _iso_b_power = -30.0 # physical power for iso b mode.


    def on_activate(self):

        # prepare for data acquisition:
        self._data = [[0, 0]] * 1
        self._arr_counter = 0
        self.skip_data = True
        self.result_available.clear()  # set the flag to false

        self._count_extender = 1  # used to artificially prolong the counting
        self._count_ext_index = 0 # the count extender index
        self._counting_window = 0.01 # the counting window in seconds

        self.__measurements = 0
        # try:
        self._dev = self.connect_mq(ip_address= self.ip_address,
                                  port=self.port,
                                  streamCb=self.streamCb,
                                  clock_freq_fpga=self._CLK_FREQ_FPGA)

        self.unlock_mq(self.unlock_key)

        self._dev.initialize()
        # except Exception as e:
        #     self.log.error(f'Cannot establish connection to MicrowaveQ due to {str(e)}.')


        self._create_slow_counter_constraints()
        self._create_recorder_constraints()

        # locking mechanism for thread safety. Use it like
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.


        self.threadlock = Mutex()

        self._esr_process_lock = Mutex()
        self._esr_process_cond = QtCore.QWaitCondition()

        self.meas_cond = QtCore.QWaitCondition()

        self._current_esr_meas = []

        # set the main RF port (RF OUT 2H) to on
        self._dev.gpio.rfswitch.set(1)

        # test gain compensation:
        if self.gain_cali_name != '':
            self._dev._setGainCalibration(self.gain_cali_name)

    def on_deactivate(self):
        self.stop_measurement()
        self.disconnect_mq()


    def trf_off(self):
        """ Turn completely off the local oscillator for rf creation. 

        Usually, the local oscillator is running in the background and leaking
        through the microwaveQ. The amount of power leaking through is quite 
        small, but still, if desired, then the trf can be also turned off 
        completely. """

        self._dev.spiTrf.write(4, 0x440e400)


    def vco_off(self):
        """Turn off completely the Voltage controlled oscillator.

        NOTE: By turning this off, you need to make sure that you turn it on 
        again if you start a measurement, otherwise nothing will be outputted.
        """
        self._dev.spiTrf.write(4, 0x440e404)

    # ==========================================================================
    # Enhance the current module by Qudi threading capabilities:
    # ==========================================================================

    @QtCore.Slot(QtCore.QThread)
    def moveToThread(self, thread):
        super().moveToThread(thread)

    def connect_mq(self, ip_address=None, port=None, streamCb=None, clock_freq_fpga=None):
        """ Establish a connection to microwaveQ. """
        # handle legacy calls
        if ip_address is None:      ip_address = self.ip_address
        if port is None:            port = self.port
        if streamCb is None:        streamCb = self.streamCb
        if clock_freq_fpga is None: clock_freq_fpga = self._CLK_FREQ_FPGA

        if hasattr(self, '_dev'):
            if self.is_connected():
                self.disconnect_mq()
        
        if self._mq_state.set_state(RecorderState.LOCKED) > 0:
            # this was a transition from disconnected-->locked
            pass   # all was ok
        else:
            cs = self._mq_state.get_state()
            self.log.error(f'MicrowaveQ {RecorderState.LOCKED} state change not allowed, curr_state={cs}')

        try:
            dev = microwaveQ.MicrowaveQ(ip_address, port, streamCb,clock_freq_fpga)
        except Exception as e:
            self.log.error(f'Cannot establish connection to MicrowaveQ due to {str(e)}.')

        return dev

    def unlock_mq(self, unlock_key=None):
        if hasattr(self, '_dev'):
            if unlock_key is None:
                unlock_key = self.unlock_key 
        
        status = self._mq_state.is_legal_transition(RecorderState.UNLOCKED) 
        if status > 0:
            try:
                self._dev.ctrl.unlock(unlock_key)
                self._dev.initialize()
            except Exception as e:
                self.log.error(f'Cannot unlock MicrowaveQ due to {str(e)}.')
            status = self._mq_state.set_state(RecorderState.UNLOCKED)

        if status <= 0:
            cs = self._mq_state.get_state()
            self.log.error(f'MQ {RecorderState.UNLOCKED} state change not allowed, curr_state={cs}')


    def is_connected(self):
        """Check whether connection protocol is initialized and ready. """
        if hasattr(self._dev.com.conn, 'axiConn'):
            return self._dev.com.conn.isConnected()
        else:
            return False

    def reconnect_mq(self):
        """ Reconnect to the microwaveQ. """
        self.disconnect_mq()
        self.connect_mq()
        #FIXME: This should be removed later on!
        self._prepare_pixelclock()  #DGCcheck

    def disconnect_mq(self):
        self._dev.disconnect()
        self._mq_state.set_state(RecorderState.DISCONNECTED)

    @deprecated("Use 'get_current_device_mode()' instead")
    def get_device_mode(self):
        if hasattr(self,'_RECORDER_CONSTRAINTS'):
            return self._mq_curr_mode 
        else:
            return RecorderMode.UNCONFIGURED 



    def getModuleThread(self):
        """ Get the thread associated to this module.

          @return QThread: thread with qt event loop associated with this module
        """
        return self._manager.tm._threads['mod-hardware-' + self._name].thread


    # ==========================================================================
    #                 power setting handling
    # ==========================================================================



    # ==========================================================================
    #                 GPIO handling
    # ==========================================================================

    # counting of GPIO ports starts on the hardware from 1 and not from 0, 
    # follow this convention here.

    @property
    def gpi1(self):
        return bool(self._dev.gpio.input0.get())

    @property
    def gpi2(self):
        return bool(self._dev.gpio.input1.get())

    @property
    def gpi3(self):
        return bool(self._dev.gpio.input2.get())

    @property
    def gpi4(self):
        return bool(self._dev.gpio.input3.get())

    @property
    def gpo1(self):
        return bool(self._dev.gpio.output0.get())

    @gpo1.setter
    def gpo1(self, state):
        if isinstance(state, bool) or isinstance(state, int):
            return self._dev.gpio.output0.set(int(state))
        else:
            self.log.warning('Incorrect state of the GPO-1 port, will be ignored.')

    @property
    def gpo2(self):
        return bool(self._dev.gpio.output1.get())

    @gpo2.setter
    def gpo2(self, state):
        if isinstance(state, bool) or isinstance(state, int):
            return self._dev.gpio.output1.set(int(state))
        else:
            self.log.warning('Incorrect state of the GPO-2 port, will be ignored.')

    @property
    def gpo3(self):
        return bool(self._dev.gpio.output2.get())

    @gpo3.setter
    def gpo3(self, state):
        if isinstance(state, bool) or isinstance(state, int):
            return self._dev.gpio.output2.set(int(state))
        else:
            self.log.warning('Incorrect state of the GPO-3 port, will be ignored.')

    @property
    def gpo4(self):
        return bool(self._dev.gpio.output3.get())

    @gpo4.setter
    def gpo4(self, state):
        if isinstance(state, bool) or isinstance(state, int):
            return self._dev.gpio.output3.set(int(state))
        else:
            self.log.warning('Incorrect state of the GPO-4 port, will be ignored.')


    def is_measurement_running(self):
        return self._meas_running


    # ==========================================================================
    #                 Begin: Slow Counter Interface Implementation
    # ==========================================================================

    def _create_slow_counter_constraints(self):
        self._SLOW_COUNTER_CONSTRAINTS.max_detectors = 1
        self._SLOW_COUNTER_CONSTRAINTS.min_count_frequency = 1e-3
        self._SLOW_COUNTER_CONSTRAINTS.max_count_frequency = 1e+3
        self._SLOW_COUNTER_CONSTRAINTS.counting_mode = [CountingMode.CONTINUOUS]

    def get_constraints(self):
        """ Retrieve the hardware constrains from the counter device.

        @return SlowCounterConstraints: object with constraints for the counter
        """

        return self._SLOW_COUNTER_CONSTRAINTS

    def set_up_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of the clock
        @param string clock_channel: if defined, this is the physical channel of the clock
        @return int: error code (0:OK, -1:error)
        """

        if self._meas_running:
            self.log.error('A measurement is still running (presumably a scan). Stop it first.')
            return -1

        counting_window = 1/clock_frequency # in seconds

        ret_val = self.configure_recorder(mode=RecorderMode.COUNTER,
                                          params={'count_frequency': clock_frequency} )
        #DGC ret_val = self._prepare_counter(counting_window)  
        return ret_val

        # if counting_window > 1.0:

        #     # try to perform counting as close as possible to 1s, then split
        #     # the count interval in equidistant pieces of measurements and
        #     # perform these amount of measurements to obtain the requested count
        #     # array. You will pay this request by a slightly longer waiting time
        #     # since the function call will be increased. The waiting time
        #     # increase is marginal and is roughly (with 2.8ms as call overhead
        #     # time) np.ceil(counting_window) * 0.0028.
        #     self._count_extender = int(np.ceil(counting_window))

        #     counting_window = counting_window/self._count_extender

        # else:
        #     self._count_extender = 1

        # self._counting_window = counting_window

        # self._dev.configureCW(frequency=500e6, countingWindowLength=self._counting_window)
        # self._dev.rfpulse.setGain(0.0)

        # return 0

    def set_up_counter(self,
                       counter_channels=None,
                       sources=None,
                       clock_channel=None,
                       counter_buffer=None):
        """ Configures the actual counter with a given clock.

        @param list(str) counter_channels: optional, physical channel of the counter
        @param list(str) sources: optional, physical channel where the photons
                                   photons are to count from
        @param str clock_channel: optional, specifies the clock channel for the
                                  counter
        @param int counter_buffer: optional, a buffer of specified integer
                                   length, where in each bin the count numbers
                                   are saved.

        @return int: error code (0:OK, -1:error)

        There need to be exactly the same number sof sources and counter channels and
        they need to be given in the same order.
        All counter channels share the same clock.
        """

        # Nothing needs to be done here.
        return 0

    def get_counter(self, samples=1):
        """ Returns the current counts per second of the counter.

        @param int samples: if defined, number of samples to read in one go

        @return numpy.array((n, uint32)): the photon counts per second for n channels
        """

        self.result_available.clear()   # clear any pre-set flag
        self._meas_running = True

        self.num = [[0, 0]] * samples  # the array to store the number of counts
        self.count_data = np.zeros((1, samples))

        cnt_num_actual = samples * self._count_extender

        self._count_number = cnt_num_actual    # the number of counts you want to get
        self.__counts_temp = 0  # here are the temporary counts stored

        self._array_num = 0 # current number of count index


        self._count_ext_index = 0   # count extender index

        self.skip_data = False  # do not record data unless it is necessary

        self._mq_state.set_state(RecorderState.BUSY)
        #DGC self._device_status = 'running'
        self._dev.ctrl.start(cnt_num_actual)

       # with self.threadlock:
       #     self.meas_cond.wait(self.threadlock)

        self.result_available.wait()
        self.skip_data = True

        return self.count_data/self._counting_window

    def get_counter_channels(self):
        """ Returns the list of counter channel names.

        @return list(str): channel names

        Most methods calling this might just care about the number of channels, though.
        """
        return ['counter_channel']

    def close_counter(self):
        """ Closes the counter and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return 0

    def close_clock(self):
        """ Closes the clock and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        self._dev.ctrl.stop()
        self.stop_measurement()
        return 0

    # ==========================================================================
    #                 End: Slow Counter Interface Implementation
    # ==========================================================================

    def resetMeasurements(self):
        self.__measurements = 0

    def getMeasurements(self):
        return self.__measurements


    #FIXME: USE THIS FUNCTIONALITY, RIGHT NOW NOT USED!!!!
    def get_meas_method(self):
        return self.meas_method

    def get_meas_method_name(self):
        return self.meas_method.__name__

    def set_meas_method(self, meas_method):

        if not callable(meas_method):
            if hasattr(self, meas_method):
                meas_method = getattr(self, meas_method)
            else:
                self.log.warning('No proper measurement method found. Call skipped.')
                return
        self.meas_method = meas_method


    def streamCb(self, frame):
        """ The Stream Callback function, which gets called by the FPGA upon the
            arrival of new data.

        @param bytes frame: The received data are a byte array containing the
                            results. This function will be called unsolicitedly
                            by the device, whenever there is new data available.
        """

        if self.skip_data:
            return

        frame_int = self._decode_frame(frame)

        if self._DEBUG_MODE:
            self._curr_frame.append(frame)  # just to keep track of the latest frame
            self._curr_frame_int = frame_int
            self._curr_frame_int_arr.append(frame_int)

        self.meas_method(frame_int)

    def meas_method_dummy(self, frame_int):
        pass

    def meas_method(self, frame_int):
        """ This measurement methods becomes overwritten by the required mode. 
            Just here as a placeholder.
        """
        pass

    def _prepare_dummy(self):
        self._meas_mode = 'dummy'
        self.meas_method = self.meas_method_dummy
        return 0

    def _prepare_counter(self, counting_window=0.001):

        if self._meas_running:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

        self._meas_mode = 'counter'

        if counting_window > 1.0:

            # try to perform counting as close as possible to 1s, then split
            # the count interval in equidistant pieces of measurements and
            # perform these amount of measurements to obtain the requested count
            # array. You will pay this request by a slightly longer waiting time
            # since the function call will be increased. The waiting time
            # increase is marginal and is roughly (with 2.8ms as call overhead
            # time) np.ceil(counting_window) * 0.0028.
            self._count_extender = int(np.ceil(counting_window))

            counting_window = counting_window/self._count_extender

        else:
            self._count_extender = 1

        self._counting_window = counting_window

        # for just the counter, set the gain to zero.
        self._dev.configureCW(frequency=500e6, 
                              countingWindowLength=self._counting_window)
        self._dev.rfpulse.setGain(0.0)

        self.meas_method = self.meas_method_SlowCounting
        
        return 0

    def meas_method_SlowCounting(self, frame_int):

        timestamp = datetime.now()

        if self._count_extender > 1:

            self.__counts_temp += frame_int[1]
            self._count_ext_index += 1

            # until here it is just counting upwards
            if self._count_ext_index < self._count_extender:
                return

        else:
            self.__counts_temp = frame_int[1]

        self._count_ext_index = 0

        self.num[self._array_num] = [timestamp, self.__counts_temp]
        self.count_data[0][self._array_num] = self.__counts_temp

        self.__counts_temp = 0
        self._array_num += 1

        if self._count_number/self._count_extender <= self._array_num:
            #print('Cancelling the waiting loop!')
            self.result_available.set()
            self._meas_running = False


    def meas_method_PixelClock(self, frame_int):
        """ Process the received pixelclock data and store to array. """

        self._meas_res[self._counted_pulses] = (frame_int[0],  # 'count_num'
                                                frame_int[1],  # 'counts' 
                                                0,             # 'counts2'
                                                0,             # 'counts_diff' 
                                                time.time())   # 'time_rec'

        if self._counted_pulses > (self._total_pulses - 2):
            self._meas_running = False
            self.meas_cond.wakeAll()
            self.skip_data = True

        self._counted_pulses += 1

    def meas_method_n_iso_b(self,frame_int):
        """ Process the received data for dual_iso_b and store to array"""

        counts_diff = frame_int[2] - frame_int[1]
        self._meas_res[self._counted_pulses] = (frame_int[0],  # 'count_num'
                                                frame_int[1],  # 'counts' 
                                                frame_int[2],  # 'counts2'
                                                counts_diff,   # 'counts_diff' 
                                                time.time())   # 'time_rec'

        #self.log.info("was meas_method_n_iso_b was called")
        if self._counted_pulses > (self._total_pulses - 2):
            self._meas_running = False
            self.meas_cond.wakeAll()
            self.skip_data = True

        self._counted_pulses += 1


    def meas_method_esr(self, frame_int):
        """ Process the received esr data and store to array."""

        self._meas_esr_res[self._esr_counter][0] = time.time()
        self._meas_esr_res[self._esr_counter][1:] = frame_int

        self._current_esr_meas.append(self._meas_esr_res[self._esr_counter][2:])

        #self.sigNewESRData.emit(self._meas_esr_res[self._esr_counter][2:])

        if self._esr_counter > (len(self._meas_esr_res) - 2):
            self._meas_running = False
            self.meas_cond.wakeAll()
            self.skip_data = True

        self._esr_counter += 1

        # wake up on every cycle
        self._esr_process_cond.wakeAll()


    def meas_stream_out(self, frame_int):
        self.sigNewData.emit(frame_int)
        return frame_int

    def _prepare_pixelclock(self, freq):
        """ Setup the device to count upon an external clock. """

        if self._meas_running:   #DGCcheck
            self.log.error('A measurement is still running. Stop it first.')
            return -1

        self._meas_mode = 'pixel'

        self.meas_method = self.meas_method_PixelClock

        self._dev.configureCW_PIX(frequency=freq)
        
        # pixel clock is configured with zero power at start 
        # power is set during recorder_start()
        self._dev.rfpulse.setGain(0.0)            
        self._dev.resultFilter.set(0)

        return 0

    def _prepare_pixelclock_single_iso_b(self, freq, power):
        """ Setup the device for a single frequency output. 

        @param float freq: the frequency in Hz to be applied during the counting.
        @param float power: the physical power of the device in dBm

        """
        if self._meas_running:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

        self._meas_mode = 'single-isob'

        self.meas_method = self.meas_method_PixelClock

        self._iso_b_freq_list = [freq]
        self._iso_b_power = power
        self._dev.configureCW_PIX(frequency=self._iso_b_freq_list[0])

        self._dev.set_freq_power(freq, power)
        self._dev.resultFilter.set(0)

        return 0

    def _prepare_pixelclock_n_iso_b(self, freq_list, pulse_lengths, power, laserCooldownLength=10e-6):
        """ Setup the device for n-frequency output. 

        @param list(float) freq_list: a list of frequencies to apply 
        @param float power: the physical power of the device in dBm
        @param pulse_margin_frac: fraction of pulse margin to leave as dead time

        """
        if self._meas_running:
            self.log.error('A measurement is still running. Stop it first.')
            return -1
        
        self._meas_mode = 'n-isob'

        self.meas_method = self.meas_method_n_iso_b

        self._iso_b_freq_list = freq_list if isinstance(freq_list, list) else [freq_list]
        self._iso_b_power = power

        base_freq = freq_list[0]
        ncoWords = [freq - base_freq for freq in freq_list]

        self._dev.configureISO(frequency=base_freq,
                               pulseLengths=pulse_lengths,
                               ncoWords=ncoWords,
                               laserCooldownLength=laserCooldownLength)

        self._dev.set_freq_power(base_freq, power)
        self._dev.resultFilter.set(0)

        return 0

    #DGC
    """
    def arm_device(self, pulses=100):

        #self._meas_mode = 'pixel'
        #DGC self._device_status = 'armed'

        self._dev.ctrl.start(pulses)
        self._total_pulses = pulses
        self._counted_pulses = 0

        self._curr_frame = []
        self._meas_res = np.zeros((pulses),
              dtype=[('count_num', '<i4'),
                     ('counts', '<i4'),
                     ('counts2', '<i4'),
                     ('counts_diff', '<i4'),
                     ('time_rec', '<f8')])

        self._meas_running = True
        self.skip_data = False
    """

    def get_line(self,meas='counts'):
        """ get line, blocking method: waits for measurement of line to complete
            called from pixel clock activated modes
        """

        if self._meas_running:
            self._mq_state.set_state(RecorderState.BUSY)  #
            with self.threadlock:
                #self._cond_waiting = True
                #self.cond.wait(self.threadlock)
                #self._cond_waiting = False
                self.meas_cond.wait(self.threadlock)


        self._mq_state.set_state(RecorderState.IDLE)
        #DGC self._device_status = 'idle'
        self.skip_data = True
        return self._meas_res[meas]


    def _decode_frame(self, frame):
        """ Decode the byte array with little endian encoding and 4 byte per
            number, i.e. a 32 bit number will be expected. """
        return struct.unpack('<' + 'i' * (len(frame)//4), frame)

    def stop_measurement(self):

        self._dev.ctrl.stop()
        self.meas_cond.wakeAll()
        self.skip_data = True
        self._mq_state.set_state(RecorderState.IDLE)
        #DGC self._device_status = 'idle'

        self._esr_process_cond.wakeAll()
        self._meas_running = False

        #FIXME, just temporarily, needs to be fixed in a different way
        time.sleep(2)

    #===========================================================================
    #       ESR measurements: ODMRCounterInterface Implementation
    #===========================================================================

    def _prepare_cw_esr(self, freq_list, count_freq=100, power=-25):
        """ Prepare the CW ESR to obtain ESR frequency scans

        @param list freq_list: containing the frequency list entries
        @param float count_freq: count frequency in Hz
        """

        if self._meas_running:
            self.log.error('A measurement is still running . Stop it first.')
            return -1


        self._meas_mode = 'esr'

        self._esr_count_frequency = count_freq  #DGCcheck

        if isinstance(freq_list, np.ndarray):
            freq_list = freq_list.tolist()

        count_window = 1 / count_freq
        self._dev.configureCW_ESR(frequencies=freq_list,
                                  countingWindowLength=count_window)

        # take the mean frequency from the list for the power.
        #FIXME: all frequencies should be normalized.
        self._dev.set_freq_power(np.mean(freq_list), power)

        # the extra two numbers are for the current number of measurement run
        # and the time
        self._meas_esr_line = np.zeros(len(freq_list)+2)

        self.meas_method = self.meas_method_esr

        return 0

    def start_esr(self, num_meas=1000):
        """ Start esr.

        @param int num_meas: number of measurement runs, zero means infinity.
        """

        self._esr_counter = 0
        self._meas_esr_res = np.zeros((num_meas, len(self._meas_esr_line)))
        self._current_esr_meas = []

        self._mq_state.set_state(RecorderState.BUSY)
        #DGC self._device_status = 'running'
        self._meas_running = True
        self.skip_data = False

        self._dev.ctrl.start(num_meas)

    def get_available_esr_res(self):
        """ Non blocking function, get just the available results from ESR"""
        return self._meas_esr_res[:self._esr_counter]

    def get_esr_meas(self):
        """ Blocking function, will only return, whenever the"""

        if self._meas_running:
            with self.threadlock:
                self.meas_cond.wait(self.threadlock)

        self._meas_esr_res[:, 2:] = self._meas_esr_res[:, 2:] * self._esr_count_frequency  #DGCcheck, can be mode param

        return self._meas_esr_res

# ==============================================================================
# ODMR Interface methods
# ==============================================================================

    def set_up_odmr_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of the
                                      clock
        @param str clock_channel: if defined, this is the physical channel of
                                  the clock

        @return int: error code (0:OK, -1:error)
        """

        if clock_frequency is not None:
            self._esr_count_frequency = clock_frequency    #DGCcheck can be mode param

        if self._meas_running:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

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
        pass


    def count_odmr(self, length=100):
        """ Sweeps the microwave and returns the counts on that sweep.

        @param int length: length of microwave sweep in pixel

        @return (bool, float[]): tuple: was there an error, the photon counts per second
        """

        if self._meas_running:

            if self._current_esr_meas != []:
                # remove the first element from the list
                with self._esr_process_lock:
                    return False,  np.array( [self._current_esr_meas.pop(0)*self._esr_count_frequency] )

            else:
                with self._esr_process_lock:
                    #FIXME: make it a multiple of the expected count time per line
                    timeout = 15 # in seconds
                    self._esr_process_cond.wait(self._esr_process_lock, timeout*1000)

                return False,  np.array( [self._current_esr_meas.pop(0)*self._esr_count_frequency] )

        else:
            return True, np.zeros((1, length))


    def close_odmr(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        self._dev.ctrl.stop()
        self._meas_running = False
        self.stop_measurement()
        return 0

    def close_odmr_clock(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return 0

    def get_odmr_channels(self):
        """ Return a list of channel names.

        @return list(str): channels recorded during ODMR measurement
        """
        return ['ch0']

    @property
    def oversampling(self):
        return False

    @oversampling.setter
    def oversampling(self, val):
        pass

    @property
    def lock_in_active(self):
        return False

    @lock_in_active.setter
    def lock_in_active(self, val):
        pass

# ==============================================================================
# MW Interface
# ==============================================================================

    def off(self):
        """
        Switches off any microwave output.
        Must return AFTER the device is actually stopped.

        @return int: error code (0:OK, -1:error)
        """

        dev_state = self.get_current_device_state()
        mode, _ = self.get_current_device_mode()
        
        # allow to run this method in the unconfigured mode, it is more a 
        if (mode == RecorderMode.CW_MW) or (mode == RecorderMode.ESR) or (mode == RecorderMode.UNCONFIGURED):
            self._mw_running = False
            self._dev.rfpulse.setGain(0.0)
            self._dev.ctrl.stop()
            self.trf_off()
            self._dev.rfpulse.stopRF()
            #self.vco_off()
            self.stop_measurement()

            # allow the state transition only in the proper state.
            if dev_state == RecorderState.BUSY:
                self._set_current_device_state(RecorderState.IDLE)
            
            return 0
        else:
            self.log.warning(f'MicrowaveQ cannot be stopped from the '
                             f'MicrowaveInterface method since the currently '
                             f'configured mode "{mode}" is not "ESR" or "CW_MW". '
                             f'Stop the microwaveQ in its proper measurement '
                             f'mode.')
            return -1


    def get_status(self):
        """
        Gets the current status of the MW source, i.e. the mode (cw, list or sweep) and
        the output state (stopped, running)

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        return self._mw_mode, self._mw_running

    def get_power(self):
        """ Gets the microwave output power for the currently active mode.

        @return float: the output power in dBm
        """
        _, power = self._dev.get_freq_power()

        return power

    def get_frequency(self):
        """ Gets the frequency of the microwave output.

        Returns single float value if the device is in cw mode.
        Returns list like [start, stop, step] if the device is in sweep mode.
        Returns list of frequencies if the device is in list mode.

        @return [float, list]: frequency(s) currently set for this device in Hz
        """

        #FIXME: implement the return value properly, dependent on the current state
        freq, _ = self._dev.get_freq_power()

        return freq

    def cw_on(self):
        """
        Switches on cw microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """

        #self.prepare_dummy()

        mode, _ = self.get_current_device_mode()

        if mode == RecorderMode.CW_MW:
            self._mw_mode = 'cw'

            self._rfpulse.startRF()
            self._mw_running = True

            self._set_current_device_state(RecorderState.BUSY)
            return 0
        else:
            self.log.warning(f'The current mode "{mode}" of MicrowaveQ is not '
                             f'property configured for "{RecorderMode.CW_MW}".')
            
            self._mw_mode = 'INVALID'
            self._mw_running = False
            return -1

    def _configure_cw_mw(self, frequency, power):
        """ General configure method for cw mw, not specific to interface. 

        @param float frequency: frequency to set in Hz
        @param float power: power to set in dBm

        @return int: error code (0:OK, -1:error)
        """

        # if in the mode unconfigured or cw mw, then this method can be applied.
        self._dev.set_freq_power(frequency, power)
        
        return 0

    def set_cw(self, frequency=None, power=None):
        """
        Configures the device for cw-mode and optionally sets frequency and/or power

        @param float frequency: frequency to set in Hz
        @param float power: power to set in dBm

        @return tuple(float, float, str): with the relation
            current frequency in Hz,
            current power in dBm,
            current mode
        """

        # take the previously set power or frequency
        if power is None:
            power = self._mw_cw_power
        if frequency is None:
            frequency = self._mw_cw_frequency

        params = {'mw_frequency':frequency, 'mw_power':power}

        # reuse the recorder interface, it will take care of the proper state setting
        ret_val = self.configure_recorder(mode=RecorderMode.CW_MW, params=params)

        self._mw_cw_frequency, self._mw_cw_power = self._dev.get_freq_power()

        if ret_val == -1:
            # this will cause a deliberate error
            self._mw_mode = 'INVALID'
        else:
            self._mw_mode = 'cw'

        return self._mw_cw_frequency, self._mw_cw_power,  self._mw_mode


    def list_on(self):
        """
        Switches on the list mode microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """

        self.start_esr()
        self._mw_running = True

        return 0

    def set_list(self, frequency=None, power=None):
        """
        Configures the device for list-mode and optionally sets frequencies and/or power

        @param list frequency: list of frequencies in Hz
        @param float power: MW power of the frequency list in dBm

        @return list, float, str: current frequencies in Hz, current power in dBm, current mode
        """

        self._mw_mode = 'list'

        mean_freq = None

        if frequency is not None:
            #FIXME: the power setting is a bit confusing. It is mainly done in 
            # this way in case no power value was provided
            params = {'mw_frequency_list': self._mw_freq_list,
                      'count_frequency':   self._esr_count_frequency,
                      'mw_power':          self._mw_power }
            self.configure_recorder(mode=RecorderMode.ESR, params=params)

            mean_freq = np.mean(self._mw_freq_list)

        if power is None:
            # take the currently set power
            _, power = self._dev.get_freq_power()

        self._dev.set_freq_power(mean_freq, power)
        self._mw_power = power

        _, self._mw_cw_power = self._dev.get_freq_power()

        return self._mw_freq_list, self._mw_cw_power, self._mw_mode

    def reset_listpos(self):
        """
        Reset of MW list mode position to start (first frequency step)

        @return int: error code (0:OK, -1:error)
        """
        return 0


    def sweep_on(self):
        """ Switches on the sweep mode.

        @return int: error code (0:OK, -1:error)
        """
        return 0

    def set_sweep(self, start=None, stop=None, step=None, power=None):
        """
        Configures the device for sweep-mode and optionally sets frequency start/stop/step
        and/or power

        @return float, float, float, float, str: current start frequency in Hz,
                                                 current stop frequency in Hz,
                                                 current frequency step in Hz,
                                                 current power in dBm,
                                                 current mode
        """
        pass       

    def reset_sweeppos(self):
        """
        Reset of MW sweep mode position to start (start frequency)

        @return int: error code (0:OK, -1:error)
        """
        pass

    def set_ext_trigger(self, pol, timing):
        """ Set the external trigger for this device with proper polarization.

        @param TriggerEdge pol: polarisation of the trigger (basically rising edge or falling edge)
        @param timing: estimated time between triggers

        @return object, float: current trigger polarity [TriggerEdge.RISING, TriggerEdge.FALLING],
            trigger timing as queried from device
        """
        return pol, timing

    def trigger(self):
        """ Trigger the next element in the list or sweep mode programmatically.

        @return int: error code (0:OK, -1:error)

        Ensure that the Frequency was set AFTER the function returns, or give
        the function at least a save waiting time corresponding to the
        frequency switching speed.
        """
        pass

    def get_limits(self):
        """ Retrieve the limits of the device.

        @return: object MicrowaveLimits: Serves as a container for the limits
                                         of the microwave device.
        """
        limits = MicrowaveLimits()
        limits.supported_modes = (MicrowaveMode.CW, MicrowaveMode.LIST)
        # the sweep mode seems not to work properly, comment it out:
                                  #MicrowaveMode.SWEEP , MicrowaveMode.LIST)

        # FIXME: these are just values for cosmetics, to make the interface happy
        limits.min_frequency = 2.5e9
        limits.max_frequency = 3.5e9
        limits.min_power = -50
        limits.max_power = 35

        limits.list_minstep = 1
        limits.list_maxstep = 1e9
        limits.list_maxentries = 2000

        limits.sweep_minstep = 1
        limits.sweep_maxstep = 1e8
        limits.sweep_maxentries = 2000
        return limits


    # ==========================================================================
    #                 Begin: Recorder Interface Implementation
    # ==========================================================================


    def _create_recorder_constraints(self):

        rc = self._RECORDER_CONSTRAINTS

        rc.max_detectors = 1
        features = self._dev.get_unlocked_features()

        rc.recorder_mode_params = {}

        rc.recorder_modes = [RecorderMode.UNCONFIGURED, 
                            RecorderMode.DUMMY]

        rc.recorder_mode_states[RecorderMode.UNCONFIGURED] = [RecorderState.LOCKED, RecorderState.UNLOCKED]

        rc.recorder_mode_params[RecorderMode.UNCONFIGURED] = {}
        rc.recorder_mode_params[RecorderMode.DUMMY] = {}

        if features.get(MicrowaveQFeatures.PIXEL_CLOCK.value) is not None:
            rc.recorder_modes.append()
            rc.recorder_modes.append(RecorderMode.PIXELCLOCK_SINGLE_ISO_B)
            rc.recorder_modes.append(RecorderMode.PIXELCLOCK_N_ISO_B)
            
            # configure possible states in a mode
            rc.recorder_mode_states[RecorderMode.PIXELCLOCK] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]
            rc.recorder_mode_states[RecorderMode.PIXELCLOCK_SINGLE_ISO_B] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]
            rc.recorder_mode_states[RecorderMode.PIXELCLOCK_N_ISO_B] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[RecorderMode.PIXELCLOCK] = {'mw_frequency': 2.8e9,
                                                                'num_meas': 100}
            rc.recorder_mode_params[RecorderMode.PIXELCLOCK_SINGLE_ISO_B] = {'mw_frequency_list': [2.8e9],
                                                                              'mw_power': -30,
                                                                              'num_meas': 100}
            rc.recorder_mode_params[RecorderMode.PIXELCLOCK_N_ISO_B] = {'mw_frequency_list': [2.8e9, 2.81e9],
                                                                         'mw_pulse_lengths': [10e-3, 10e-3],
                                                                         'mw_power': -30,
                                                                         'mw_laser_cooldown_time': 10e-6,
                                                                         'num_meas': 100}

        if features.get(MicrowaveQFeatures.CONTINUOUS_ESR.value) is not None:
            rc.recorder_modes.append(RecorderMode.CW_MW)
            rc.recorder_modes.append(RecorderMode.ESR)
            
            # configure possible states in a mode
            rc.recorder_mode_states[RecorderMode.CW_MW] = [RecorderState.IDLE, RecorderState.BUSY]
            rc.recorder_mode_states[RecorderMode.ESR] = [RecorderState.IDLE, RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[RecorderMode.CW_MW] = {'mw_frequency': 2.8e9,
                                                            'mw_power': -30}
            rc.recorder_mode_params[RecorderMode.ESR] = {'mw_frequency_list': [],
                                                          'mw_power': -30,
                                                          'count_frequency': 100,
                                                          'num_meas': 100}

        if features.get(MicrowaveQFeatures.CONTINUOUS_COUNTING.value) is not None:
            rc.recorder_modes.append(RecorderMode.COUNTER)
            rc.recorder_modes.append(RecorderMode.CONTINUOUS_COUNTING)

            # configure possible states in a mode
            rc.recorder_mode_states[RecorderMode.COUNTER] = [RecorderState.IDLE, RecorderState.BUSY]
            rc.recorder_mode_states[RecorderMode.CONTINUOUS_COUNTING] = [RecorderState.IDLE, RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[RecorderMode.COUNTER] = {'count_frequency': 100}
            rc.recorder_mode_params[RecorderMode.CONTINUOUS_COUNTING] = {'count_frequency': 100}


    def get_recorder_constraints(self):
        """ Retrieve the hardware constraints from the recorder device.

        @return RecorderConstraints: object with constraints for the recorder
        """

        return self._RECORDER_CONSTRAINTS


    def _check_params_for_mode(self, mode, params):
        """ Make sure that all the parameters are present for the current mode.
        
        @param RecorderMode mode: mode of recorder, as available from 
                                  RecorderMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        return bool:
                True: Everything is fine
                False: parameters are missing. Missing parameters will be 
                       indicated in the error log/message.

        This method assumes that the passed mode is in the available options,
        no need to double check if mode is present it available modes.
        """

        is_ok = True
        limits = self.get_recorder_constraints() 
        allowed_modes = limits.recorder_modes
        required_params = limits.recorder_mode_params[mode]

        if mode not in allowed_modes:
            is_ok = False
            return is_ok

        for entry in required_params:
            if params.get(entry) is None:
                self.log.warning(f'Parameter "{entry}" not specified for mode '
                                 f'"{mode}". Correct this!')
                is_ok = False

        return is_ok


    def configure_recorder(self, mode, params):
        """ Configures the recorder mode for current measurement. 

        @param RecorderMode mode: mode of recorder, as available from 
                                  RecorderMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """

        #FIXME: Transfer the checking methods in the underlying config methods?
        #       But then you need to know how to operate these methods.

        
        # check at first whether mode can be changed based on the state of the 
        # device, only from the idle mode it can be configured.

        dev_state = self._mq_state.get_state()
        curr_mode, _ = self.get_current_device_mode()

        if (dev_state == RecorderState.BUSY) and (curr_mode != RecorderMode.CW_MW): 
            # on the fly configuration (in BUSY state) is only allowed in CW_MW mode.
            self.log.error(f'MicrowaveQ cannot be configured in the '
                           f'requested mode "{mode}", since the device '
                           f'state is in "{dev_state}". Stop ongoing '
                           f'measurements and make sure that the device is '
                           f'connected to be able to configure if '
                           f'properly.')
            return -1
            

        # check at first if mode is available
        limits = self.get_recorder_constraints()

        if mode not in limits.recorder_modes:
            self.log.error(f'Requested mode "{mode}" not available in '
                            'microwaveQ. Configuration stopped.')
            return -1

        is_ok = self._check_params_for_mode(mode, params)
        if not is_ok:
            self.log.error(f'Parameters are not correct for mode "{mode}". '
                           f'Configuration stopped.')
            return -1

        ret_val = 0
        # the associated error message for a -1 return value should come from 
        # the method which was called (with a reason, why configuration could 
        # not happen).

        # after all the checks are successful, delegate the call to the 
        # appropriate preparation function.
        if mode == RecorderMode.UNCONFIGURED:
            # not sure whether it makes sense to configure the device 
            # deliberately in an unconfigured state, it sounds like a 
            # contradiction in terms, but it might be important if device is 
            # e.g. reseted.
            pass

        elif mode == RecorderMode.DUMMY:
            ret_val = self._prepare_dummy()
        elif mode == RecorderMode.PIXELCLOCK:
            ret_val = self._prepare_pixelclock(freq=params['mw_frequency'])
        elif mode == RecorderMode.PIXELCLOCK_SINGLE_ISO_B:
            #TODO: make proper conversion of power to mw gain
            ret_val = self._prepare_pixelclock_single_iso_b(freq=params['mw_frequency'], 
                                                           power=params['mw_power'])
        elif mode == RecorderMode.COUNTER:
            ret_val = self._prepare_counter(counting_window=1/params['count_frequency'])
        elif mode == RecorderMode.CONTINUOUS_COUNTING:
            #TODO: implement this mode
            self.log.error(f"Configure recorder: mode {mode} currently not implemented")
        elif mode == RecorderMode.CW_MW:
            ret_val = self._configure_cw_mw(frequency=params['mw_frequency'],
                                            power=params['mw_power'])
        elif mode == RecorderMode.ESR:
            #TODO: replace gain by power (and the real value)
            ret_val = self._prepare_cw_esr(freq_list=params['mw_frequency_list'], 
                                          count_freq=params['count_frequency'],
                                          power=params['mw_power'])
        if ret_val == -1:
            self._set_current_device_mode(mode=RecorderMode.UNCONFIGURED, 
                                          params={})
        else:
            self._set_current_device_mode(mode=mode, 
                                          params=params)

        return ret_val


    def start_recorder(self, arm=False):
        """ Start recorder 
        start recorder with mode as configured 
        If pixel clock based methods, will begin on first trigger
        If not first configured, will cause an error
        
        @param bool: arm: specifies armed state with regard to pixel clock trigger
        
        @return bool: success of command
        """

        if self._mq_state.get_state() != RecorderState.IDLE:
            self.log.warning('MicrowaveQ is not in Idle mode to start the measurement.')
            return False 

        if self._mq_state.get_state() == RecorderMode.UNCONFIGURED:
            self.log.warning('MicrowaveQ not properly configured to start a measurement.')
            return  False

        mode, params = self.get_current_device_mode()

        num_meas = params['num_meas']

        if arm and mode.activation != 'trigger':
            self.log.warning('MicrowaveQ: attempt to set ARMED state for a continuous measurement mode')
            return False 

        # Pixel clock modes
        if mode.activation == 'trigger':
            self._mq_state.set_state(RecorderState.ARMED)
            self._total_pulses = num_meas 
            self._counted_pulses = 0

            self._curr_frame = []
            self._meas_res = np.zeros((num_meas),
              dtype=[('count_num', '<i4'),
                     ('counts', '<i4'),
                     ('counts2', '<i4'),
                     ('counts_diff', '<i4'),
                     ('time_rec', '<f8')])

        elif mode.activation == 'continuous':
            self._mq_state.set_state(RecorderState.BUSY)
            self._meas_esr_res = np.zeros((num_meas, len(self._meas_esr_line)))
            self._esr_counter = 0
            self._current_esr_meas = []

        else:
            self.log.error(f'MicrowaveQ: method {mode.name}, activation={mode.activation} not implemented yet')
            return False 

        self._meas_running = True
        self.skip_data = False
        self._dev.ctrl.start(num_meas)
        return True 


    def get_measurement(self):
        """ get measurement
        returns the measurement array in integer format

        @return int_array: array of measurement as tuple elements
        """
        pass

    # def stop_measurement(self):
    #     """ Stops all on-going measurements, returns device to idle state
        
    #     @return int: error code (0:OK, -1:error)
    #     """

    #     self._mq_curr_mode = RecorderState.IDLE
    #     return 0

    #FIXME: this might be a redundant method and can be replaced by get_recorder_limits
    def get_parameter_for_modes(self, mode=None):
        """ Returns the required parameters for the modes

        @param RecorderMode mode: specifies the mode for sought parameters
                                  If mode=None, all modes with their parameters 
                                  are returned. Otherwise specific mode 
                                  parameters are returned  

        @return dict: containing as keys the RecorderMode.mode and as values a
                      dictionary with all parameters associated to the mode.
                      
                      Example return with mode=RecorderMode.CW_MW:
                            {RecorderMode.CW_MW: {'countwindow': 10,
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

    def get_current_device_mode(self):
        """ Get the current device mode with its configuration parameters

        @return: (mode, params)
                RecorderMode.mode mode: the current recorder mode 
                dict params: the current configuration parameter
        """
        return self._mq_curr_mode, self._mq_curr_mode_params

    def _set_current_device_mode(self, mode, params):
        """ Set the current device mode. 
        
        @param RecorderMode mode: mode of recorder, as available from 
                                  RecorderMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        private function, only used inside this file, hence no checking routine.
        To set and configure the device properly, use the configure_recorder 
        method.
        """
        self._mq_curr_mode = mode
        self._mq_curr_mode_params = params

    def get_current_device_state(self):
        """  get_current_device_state
        returns the current device state

        @return RecorderState.state
        """
        return self._mq_state.get_state() 

    def _set_current_device_state(self, state):
        """ Set the current device state. 

        @param RecorderState state: state of recorder

        generic and private function, only used inside this file, hence no 
        checking routine.
        """
        return self._mq_state.set_state(state) 
       
