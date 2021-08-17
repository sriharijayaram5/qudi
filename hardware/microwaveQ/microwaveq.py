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
import subprocess
import numpy as np
import time
import struct
from enum import Enum
from collections import namedtuple

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from interface.slow_counter_interface import SlowCounterInterface, SlowCounterConstraints, CountingMode
from interface.recorder_interface import RecorderInterface, RecorderConstraints, RecorderState, RecorderMode
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
    UNCONFIGURED               = 0
    CONTINUOUS_COUNTING        = 1
    CONTINUOUS_ESR             = 2
    RABI                       = 4
    PULSED_ESR                 = 8
    PIXEL_CLOCK                = 16
    EXT_TRIGGERED_MEASUREMENT  = 32
    ISO                        = 64
    TRACKING                   = 128
    GENERAL_PULSED_MODE        = 256
    APD_TO_GPO                 = 512
    PARALLEL_STREAMING_CHANNEL = 1024
    MICROSD_WRITE_ACCESS       = 2048


    def __int__(self):
        return self.value

class MicrowaveQMeasurementConstraints:
    """ Defines the measurement data formats for the recorder
    """

    def __init__(self):
        # recorder data mode
        self.meas_modes = [] 
        # recorder data format, returns the structure of expected format
        self.meas_formats = {}
        # recorder measurement processing function 
        self.meas_method = {}


class MicrowaveQMode(RecorderMode):
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


class MicrowaveQMeasurementMode(namedtuple('MicrowaveQMeasurementMode', 'value name movement'), Enum):
    DUMMY = -1, 'DUMMY', 'null'
    COUNTER = 0, 'COUNTER', 'null'
    PIXELCLOCK = 1, 'PIXELCLOCK', 'line' 
    PIXELCLOCK_SINGLE_ISO_B = 2, 'PIXELCLOCK_SINGLE_ISO_B', 'line'
    PIXELCLOCK_N_ISO_B = 3, 'PIXELCLOCK_N_ISO_B', 'line'
    ESR = 4, 'ESR', 'point'
    PULSED_ESR = 5, 'PULSED_ESR', 'point'
    GENERAL_PULSED = 6, 'GENERAL_PULSED', 'point'

    def __str__(self):
        return self.name

    def __int__(self):
        return self.value


class MicrowaveQStateMachine:
    """ Interface to mantain the recorder device state
        Enforcement of the state is set here
    """
    def __init__(self, enforce=False):
        self._enforce = enforce          # check state changes, warn if not allowed 
        self._last_update = None         # time when last updated
        self._allowed_transitions = {}   # dictionary of allowed state trasitions
        self._curr_state = None          # current state 
        self._lock = Mutex()             # thread lock
        self._log = None

    def set_allowed_transitions(self,transitions, initial_state=None):
        """ allowed transitions is a dictionary with { 'curr_state1': ['allowed_state1', 'allowed_state2', etc.],
                                                       'curr_state2': ['allowed_state3', etc.]}
        """
        status = -1 
        if isinstance(transitions,dict):
            self._allowed_transitions = transitions
            state = initial_state if initial_state is not None else list(transitions.keys())[0]
            status = self.set_state(state,initial_state=True)

        return status 

    def get_allowed_transitions(self):
        return self._allowed_trasitions

    def is_legal_transition(self, requested_state, curr_state=None):
        """ Checks for a legal transition of state
            @param requested_state:  the next state sought
            @param curr_state:  state to check from (can be hypothetical)

            @return int: error code (1: change OK, 0:could not change, -1:incorrect setting)
        """
        if self._allowed_transitions is None: 
            return -1       # was not configured

        if curr_state is None:
            curr_state = self._curr_state

        if (curr_state in self._allowed_transitions.keys()) and \
           (requested_state in self._allowed_transitions.keys()):

            if requested_state in self._allowed_transitions[curr_state]:
                return 1    # is possible to change
            else: 
                return 0    # is not possible to change
        else:
            return -1       # check your inputs, you asked the wrong question

    def get_state(self):
        return self._curr_state

    def set_state(self,requested_state, initial_state=False):
        """ performs state trasition, if allowed 

            @return int: error code (1: change OK, 0:could not change, -1:incorrect setting)
        """
        if self._allowed_transitions is None: 
            return -1       # was not configured

        if initial_state:
            # required only for initial state, otherwise should be set by transition 
            with self._lock:
                self._curr_state = requested_state
                self._last_update = datetime.now()
            return 1
        else:
            status = self.is_legal_transition(requested_state)
            if status > 0:
                with self._lock:
                    self._prior_state = self._curr_state
                    self._curr_state = requested_state
                    self._last_update = datetime.now()
                    return 1    # state transition was possible
            else:
                if self._enforce:
                    raise Exception(f'RecorderStateMachine: invalid change of state requested: {self._curr_state} --> {requested_state} ')
                return status   # state transition was not possible
        
    def get_last_change(self):
        """ returns the last change of state

            @return tuple: 
            - prior_state: what occured before the current
            - curr_state:  where we are now
            - last_update: when it happened
        """ 
        return self._prior_state, self._curr_state, self._last_update



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

    __version__ = '0.1.3'

    _CLK_FREQ_FPGA = 153.6e6 # is used to obtain the correct mapping of signals.
    _FPGA_version = 0        # must be obtained after connection to MQ

    ip_address = ConfigOption('ip_address', default='192.168.2.10')
    port = ConfigOption('port', default=55555, missing='info')
    unlock_key = ConfigOption('unlock_key', missing='error')
    gain_cali_name = ConfigOption('gain_cali_name', default='')

    sigNewData = QtCore.Signal(tuple)
    sigLineFinished = QtCore.Signal()

    _threaded = True 
    #_threaded = False  # for debugging 

    _mq_state = MicrowaveQStateMachine(enforce=False)
    _mq_state.set_allowed_transitions(
        transitions={RecorderState.DISCONNECTED: [RecorderState.LOCKED],
                     RecorderState.LOCKED: [RecorderState.UNLOCKED, RecorderState.DISCONNECTED],
                     RecorderState.UNLOCKED: [RecorderState.IDLE, RecorderState.DISCONNECTED],
                     RecorderState.IDLE: [RecorderState.ARMED, RecorderState.BUSY, RecorderState.IDLE, RecorderState.DISCONNECTED],
                     RecorderState.IDLE_UNACK: [RecorderState.ARMED, RecorderState.BUSY, RecorderState.IDLE, RecorderState.DISCONNECTED],
                     RecorderState.ARMED: [RecorderState.IDLE, RecorderState.IDLE_UNACK, RecorderState.BUSY, RecorderState.DISCONNECTED], 
                     RecorderState.BUSY: [RecorderState.IDLE, RecorderState.IDLE_UNACK, RecorderState.DISCONNECTED]
                     }, 
                     initial_state=RecorderState.DISCONNECTED
                    )

    _mq_curr_mode = MicrowaveQMode.UNCONFIGURED
    _mq_curr_mode_params = {} # store here the current configuration


    #FIXME: remove threading components and use Qt Threads instead!
    result_available = threading.Event()

    _SLOW_COUNTER_CONSTRAINTS = SlowCounterConstraints()
    _RECORDER_CONSTRAINTS = RecorderConstraints()
    _RECORDER_MEAS_CONSTRAINTS = MicrowaveQMeasurementConstraints()

    _stop_request = False   # this variable will be internally set to request a stop

    # measurement variables
    _DEBUG_MODE = False
    _curr_frame = []
    _curr_frame_int = None
    _curr_frame_int_arr = []

    # monitor variables
    _monitor_frame = []
    _monitor_frame_int = None
    _monitor_frame_int_arr = []

    # variables for ESR measurement
    _esr_counter = 0
    _esr_count_frequency = 100 # in Hz

    # variables for pulsed measurement
    _pulsed_counter = 0

    # for MW interface:
    _mw_cw_frequency = 2.89e9 # in Hz
    #FIXME: Power not used so far
    _mw_cw_power = -30 # in dBm
    _mw_freq_list = []
    _mw_power = -25 # not exposed to interface!!!

    # settings for iso-B mode
    _iso_b_freq_list = [500e6] # in MHz
    _iso_b_power = -30.0 # physical power for iso b mode.
    _iso_b_pulse_config_time = 12e-6   # time required to configure a pulse


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

        if not self.is_ip_address_reachable(self.ip_address):
            self.log.error(f"Cannot find MicrowaveQ at ip_address={self.ip_address}")
            return

        # try:
        self._dev = self.connect_mq(ip_address= self.ip_address,
                                  port=self.port,
                                  streamCb=self.streamCb,
                                  monitorCb=self.monitorCb, 
                                  clock_freq_fpga=self._CLK_FREQ_FPGA)

        self.unlock_mq(self.unlock_key)

        self._dev.initialize()
        # except Exception as e:
        #     self.log.error(f'Cannot establish connection to MicrowaveQ due to {str(e)}.')

        self._FPGA_version = self._dev.sys.fpgaVersion.get()

        self._create_slow_counter_constraints()
        self._create_recorder_constraints()
        self._create_recorder_meas_constraints()

        # locking mechanism for thread safety. Use it like
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.


        self.threadlock = Mutex()

        self._esr_process_lock = Mutex()
        self._esr_process_cond = QtCore.QWaitCondition()
        self._pulsed_process_cond = QtCore.QWaitCondition()

        self.meas_cond = QtCore.QWaitCondition()

        self._current_esr_meas = []
        self._current_pulsed_meas = []

        # set the main RF port (RF OUT 2H) to on
        self._dev.gpio.rfswitch.set(1)

        # test gain compensation:
        if self.gain_cali_name != '':
            self._dev._setGainCalibration(self.gain_cali_name)
        else:
            self.log.warn("MicrowaveQ: no gain calibration file specified")

    def on_deactivate(self):
        self.stop_measurement()
        self.disconnect_mq()


    def is_ip_address_reachable(self,ip_address=None):
        """ Determines if IP address is reachable using ping
            This is used primarily to check if the MicrowaveQ is reachable on the network
        """
        if ip_address is None:
            ip_address = self.ip_address

        status, _ = subprocess.getstatusoutput(f'ping -n 1 -w 500 {ip_address}')
        return not status      # status = 0 means OK; status = 1 means fail 


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
        again if you start a measurement, otherwise nothing will be output.
        """
        self._dev.spiTrf.write(4, 0x440e404)

    # ==========================================================================
    #                  Qudi threading 
    # ==========================================================================

    @QtCore.Slot(QtCore.QThread)
    def moveToThread(self, thread):
        super().moveToThread(thread)


    def connect_mq(self, ip_address=None, port=None, streamCb=None, monitorCb=None, clock_freq_fpga=None):
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
            dev = microwaveQ.MicrowaveQ(ip=ip_address, 
                                        local_port=port, 
                                        streamCb0=streamCb,
                                        streamCb1=monitorCb,
                                        cu_clk_freq=clock_freq_fpga)
            return dev
        except Exception as e:
            self.log.error(f'Cannot establish connection to MicrowaveQ due to {str(e)}.')
            return None


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
        self._prepare_pixelclock()  


    def disconnect_mq(self):
        self._dev.disconnect()
        self._mq_state.set_state(RecorderState.DISCONNECTED)


    @deprecated("Use 'get_current_device_mode()' instead")
    def get_device_mode(self):
        if hasattr(self,'_RECORDER_CONSTRAINTS'):
            return self._mq_curr_mode 
        else:
            return MicrowaveQMode.UNCONFIGURED 


    def getModuleThread(self):
        """ Get the thread associated to this module.

          @return QThread: thread with qt event loop associated with this module
        """
        return self._manager.tm._threads['mod-hardware-' + self._name].thread


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
        return self._mq_state.get_state() == RecorderState.BUSY


    # ==========================================================================
    #                 Slow Counter Interface Implementation
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
        if self._mq_state.get_state() == RecorderState.BUSY:
            self.log.error('A measurement is still running (presumably a scan). Stop it first.')
            return -1

        counting_window = 1/clock_frequency # in seconds

        ret_val = self.configure_recorder(mode=MicrowaveQMode.COUNTER,
                                          params={'count_frequency': clock_frequency} )
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
        self._mq_state.set_state(RecorderState.BUSY)

        self.num = [[0, 0]] * samples  # the array to store the number of counts
        self.count_data = np.zeros((1, samples))

        cnt_num_actual = samples * self._count_extender

        self._count_number = cnt_num_actual    # the number of counts you want to get
        self.__counts_temp = 0  # here are the temporary counts stored

        self._array_num = 0 # current number of count index


        self._count_ext_index = 0   # count extender index

        self.skip_data = False  # do not record data unless it is necessary

        self._dev.ctrl.start(cnt_num_actual)

       # with self.threadlock:
       #     self.meas_cond.wait(self.threadlock)

        self.result_available.wait()
        self._mq_state.set_state(RecorderState.IDLE_UNACK)
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
    #                 Measurement Methods 
    # ==========================================================================

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


    def monitorCb(self, frame):
        """ The monitor Callback function, which gets called by the FPGA upon the
            arrival of new data for the monitor stream.
            This only recieves continous feed back with reporting based on interval

        @param bytes frame: The received data are a byte array containing the
                            results. This function will be called unsolicitedly
                            by the device, whenever there is new data available.
        """

        if self.skip_data:
            return

        frame_int = self._decode_frame(frame)

        if self._DEBUG_MODE:
            self._monitor_frame.append(frame)  # just to keep track of the latest frame
            self._monitor_frame_int = frame_int
            self._monitor_frame_int_arr.append(frame_int)

        #self.meas_method(frame_int)  #TODO: this needs to be completed


    def _decode_frame(self, frame):
        """ Decode the byte array with little endian encoding and 4 byte per
            number, i.e. a 32 bit number will be expected. """
        return struct.unpack('<' + 'i' * (len(frame)//4), frame)


    def resetMeasurements(self):
        self.__measurements = 0


    def getMeasurements(self):
        return self.__measurements


    def stop_measurement(self):

        if hasattr(self,'_dev'):
            self._dev.ctrl.stop()

        self.meas_cond.wakeAll()
        self.skip_data = True

        self._esr_process_cond.wakeAll()
        self._pulsed_process_cond.wakeAll()
        self._mq_state.set_state(RecorderState.IDLE)

        #FIXME, just temporarily, needs to be fixed in a different way
        time.sleep(2)


    def _meas_method_dummy(self, frame_int):
        pass


    def _meas_method(self, frame_int):
        """ This measurement methods becomes overwritten by the required mode. 
            Just here as a placeholder.
        """
        pass


    def _meas_method_SlowCounting(self, frame_int):
        """Process the received counts until count buffer is full"""
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
            self._mq_state.set_state(RecorderState.IDLE_UNACK)


    def _meas_method_PixelClock(self, frame_int):
        """ Process the received pixelclock data and store to array. """
        if self._mq_state.get_state() == RecorderState.ARMED:
            self._mq_state.set_state(RecorderState.BUSY)

        if self._FPGA_version >= 13:
            # pixel clock header for FPGA v13+
            # [frame#,      clockCounts,  photonCounts, ...]
            # frame_int[0], frame_int[1], frame_int[2], ...
            pixel_time = frame_int[1] / self._CLK_FREQ_FPGA 

            self._meas_res[self._counted_pulses] = (frame_int[0],  # 'count_num'
                                                    frame_int[2],  # 'counts' 
                                                    0,             # 'counts2'
                                                    0,             # 'counts_diff' 
                                                    pixel_time)    # 'int_time'
        else:
            # pixel clock header for FPGA < v13
            # [frame#,      photonCounts, ...]
            # frame_int[0], frame_int[1], ...
            self._meas_res[self._counted_pulses] = (frame_int[0],  # 'count_num'
                                                    frame_int[1],  # 'counts' 
                                                    0,             # 'counts2'
                                                    0,             # 'counts_diff' 
                                                    time.time())   # 'time_rec'

        if self._counted_pulses > (self._total_pulses - 2):
            self.meas_cond.wakeAll()
            self._mq_state.set_state(RecorderState.IDLE_UNACK)
            self.skip_data = True

        self._counted_pulses += 1

    def _meas_method_n_iso_b(self,frame_int):
        """ Process the received data for dual_iso_b and store to array"""
        if self._mq_state.get_state() == RecorderState.ARMED:
            self._mq_state.set_state(RecorderState.BUSY)

        # for dual iso-b, there are n_freq_splits * 2 + 1 items in frame_int
        # frame_int[1:] contains the f1 and f2 frequency measurements in even/odd index pairs
        counts = frame_int[1:]
        counts1 = sum(counts[0::2])
        counts2 = sum(counts[1::2]) 

        counts_diff = counts2 - counts1 
        self._meas_res[self._counted_pulses] = (frame_int[0],  # 'count_num'
                                                counts1,  # 'counts' 
                                                counts2,  # 'counts2'
                                                counts_diff,   # 'counts_diff' 
                                                time.time())   # 'time_rec'

        if self._counted_pulses > (self._total_pulses - 2):
            self.meas_cond.wakeAll()
            self._mq_state.set_state(RecorderState.IDLE_UNACK)
            self.skip_data = True

        self._counted_pulses += 1

    
    def _meas_method_esr(self, frame_int):
        """ Process the received esr data and store to array."""

        self._meas_esr_res[self._esr_counter][0] = time.time()
        self._meas_esr_res[self._esr_counter][1:] = frame_int

        self._current_esr_meas.append(self._meas_esr_res[self._esr_counter][2:])

        #self.sigNewESRData.emit(self._meas_esr_res[self._esr_counter][2:])

        if self._esr_counter > (len(self._meas_esr_res) - 2):
            self.meas_cond.wakeAll()
            self._mq_state.set_state(RecorderState.IDLE_UNACK)
            self.skip_data = True

        self._esr_counter += 1

        # wake up on every cycle
        self._esr_process_cond.wakeAll()


    def _meas_method_pulsed(self,frame_int):
        """ Process the received pulse data"""
        self._meas_pulsed_res[self._pulsed_counter] = frame_int[-(self._meas_length_pulse+1):]

        # method for indeterminate size arrays
        #if self._meas_pulsed_res is None:
        #    self._meas_pulsed_res = np.array([ frame_int[:self._meas_length_pulse+1 ]],'<i4') 
        #else:
        #    self._meas_pulsed_res = np.append(self._meas_pulsed_res, [ frame_int[:self._meas_length_pulse+1 ]], axis=0)

        self._current_pulsed_meas.append(frame_int[-self._meas_length_pulse:])

        if self._pulsed_counter > (self._meas_pulsed_res.shape[0] - 2):
            self.meas_cond.wakeAll()
            self._mq_state.set_state(RecorderState.IDLE_UNACK)
            self.skip_data = True

        self._pulsed_counter += 1

        # wake up on every cycle
        self._pulsed_process_cond.wakeAll()


    def _meas_stream_out(self, frame_int):
        self.sigNewData.emit(frame_int)
        return frame_int

    # ==========================================================================
    #                 Prepare measurement routines 
    # ==========================================================================

    def _prepare_dummy(self):
        self.meas_method = self._meas_method_dummy 
        return 0

    def _prepare_counter(self, counting_window=0.001):

        if self._mq_state.get_state() == RecorderState.BUSY:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

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
                              countingWindowLength=self._counting_window,
                              accumulationMode=0)
        self._dev.rfpulse.setGain(0.0)
        self.meas_method = self._meas_method_SlowCounting 
        
        return 0


    def _prepare_pixelclock(self, freq):
        """ Setup the device to count upon an external clock. """

        if self._mq_state.get_state() == RecorderState.BUSY:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

        mm = self.get_measurement_methods()
        self.meas_method = mm.meas_method[MicrowaveQMeasurementMode.PIXELCLOCK] 

        if freq < 500e6:
            self.log.warn(f"MicrowaveQ: _prepare_pixelclock(): freq={freq}Hz"
                           " was below minimimum, resetting")

        freq = max(500e6, freq)
        self._dev.configureCW_PIX(frequency=freq, accumulationMode=0)
        
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
        if self._mq_state.get_state() == RecorderState.BUSY:
            self.log.error('A measurement is still running. Stop it first.')
            return -1

        mm = self.get_measurement_methods()
        self.meas_method = mm.meas_method[MicrowaveQMeasurementMode.PIXELCLOCK_SINGLE_ISO_B] 

        self._iso_b_freq_list = [freq]
        self._iso_b_power = power
        self._dev.configureCW_PIX(frequency=self._iso_b_freq_list[0], accumulationMode=0)

        self._dev.set_freq_power(freq, power)
        self._dev.resultFilter.set(0)

        return 0

    def _prepare_pixelclock_n_iso_b(self, freq_list, pulse_lengths, power, 
                                    n_freq_splits=1, laserCooldownLength=10e-6):
        """ Setup the device for n-frequency output. 

        @param list(float) freq_list: a list of frequencies to apply 
        @param list(float) pulse_lengths: list of pulse lengths to use 
        @param (float) power: the physical power of the device in dBm; 
                              this is re-applied as NCO gains to achieve a uniform power across all frequencies
        @param (int) n_sub_splits = number of sub splits of each frequency to be alternated in list
        @param pulse_margin_frac: fraction of pulse margin to leave as dead time

        """
        if self._mq_state.get_state() == RecorderState.BUSY:
            self.log.error('A measurement is still running. Stop it first.')
            return -1
        
        mm = self.get_measurement_methods()
        self.meas_method = mm.meas_method[MicrowaveQMeasurementMode.PIXELCLOCK_N_ISO_B] 

        self._iso_b_freq_list = freq_list if isinstance(freq_list, list) else [freq_list]
        self._iso_b_power = power

        # split list into stacked alternating frequencies in order to avoid topology bias
        freq_list = freq_list * n_freq_splits 
        pulse_lengths = [ pl / n_freq_splits for pl in pulse_lengths] * n_freq_splits

        base_freq = freq_list[0]
        ncoWords = [freq - base_freq for freq in freq_list]
        ncoGains = [self._dev.get_gain_for_freq_power(freq, power)[0] for freq in freq_list]

        self._dev.configureISO(frequency=base_freq,
                               pulseLengths=pulse_lengths,
                               ncoWords=ncoWords,
                               ncoGains=ncoGains,
                               laserCooldownLength=laserCooldownLength,
                               accumulationMode=0)

        self._dev.set_freq_power(base_freq, power)
        self._dev.resultFilter.set(0)

        return 0


    def _prepare_cw_esr(self, freq_list, count_freq=100, power=-25):
        """ Prepare the CW ESR to obtain ESR frequency scans

        @param list freq_list: containing the frequency list entries
        @param float count_freq: count frequency in Hz
        """
        if self._mq_state.get_state() == RecorderState.BUSY:
            self.log.error('A measurement is still running . Stop it first.')
            return -1

        if isinstance(freq_list, np.ndarray):
            freq_list = freq_list.tolist()

        count_window = 1 / count_freq
        self._dev.configureCW_ESR(frequencies=freq_list,
                                  countingWindowLength=count_window,
                                  accumulationMode=0)

        # take the mean frequency from the list for the power.
        #FIXME: all frequencies should be normalized.
        self._dev.set_freq_power(np.mean(freq_list), power)

        # the extra two numbers are for the current number of measurement run
        # and the time
        self._meas_esr_line = np.zeros(len(freq_list)+2)

        mm = self.get_measurement_methods()
        self.meas_method = mm.meas_method[MicrowaveQMeasurementMode.ESR] 

        return 0

    def _prepare_pulsed_mode(self, 
                             freq_list,                    # frequencies to be used
                             power,                        # baseline reference power
                             primary_seqCmds,              # primary sequence block 
                             n_reps=1,                     # number of repititions of primary block
                             pre_seqCmds=[],               # optional pre seqCmds
                             post_seqCmds=[],              # optional post seqCmds
                             sequence_offset=0,            # write offset for sequences 
                             update_sequence_size=True,    # update of length of sequence to given sequence
                             accumulationMode=True,        # use accumulationMode 
                             overrideMeasLength=None):     # forces measurement width return other than determined from seqCmds
        """ Prepare general pulsed mode

        @param list freq_list: list of frequencies used in pulse generation (referred to by index)
        @param float power: base value of power for initial sequence 
        @param list of dict: primary_seqCmds: primary block of repetitive sequences 
        @param int n_reps:  multiplier to build full sequence block
        @param list of dict: pre_seqCmds: seqCmd(s) prepend to the expanded block
        @param list of dict: post_seqCmds: seqCmd(s) prepend to the expanded block
        @param int sequence_offset : location to start writing sequence (overwrite existing, default=0)
        @param bool update_sequence : flag for automatically configuring sequence length register in DMA read module_size
        @param bool accumulationMode : flag to accumulate counts, this is default for pulsing 
        @param int overrideMeasLength : if not None, will specify the length of a measurement returned in frame_int 

        sequence_cmds example:
            [ {'RF_EN': 0,                 # RF_EN           -> 0 or 1 : Microwave off/on 
               'LS_EN': 0,                 # LS_EN           -> 0 or 1 : Laser off/on
               'CU_EN': 0,                 # CU_EN           -> 0 or 1 : Read out data off/on 
               'RF_RECONFIG_EN': 1,        # RF_RECONFIG_EN: -> 0 or 1 : Reconfigure MW frequency (required in seperate before RF_EN)
               'GPOS': 0,                  # GPOS:           -> 0 to 3 : Output sequence trigger to GPO output (0 = GPO1) 
               'RF_FREQ_SEL': 0,           # RF_FREQ_SEL:    -> 0 to n-1 freq : Index of frequency to configure (index of freq_list)
               'RF_GAIN': 1.0,             # RF_GAIN:        -> 0.0 to 1.0 : Gain applied during MW pulse
               'RF_PHASE': 0.0,            # RF_PHASE:       -> float : Starting phase angle of MW pulse (value in degrees)
               'DURATION': 1e-6 },         # DURATION:       -> float : Duration of sequence command (value in seconds)
              },
              { <repeat for next setting > }, 
            ]
        """
        updateSeqSizeReg = 1 if update_sequence_size else 0 
        accumulationMode = 1 if accumulationMode else 0 

        self._dev._setFrequencies(freq_list)
        self._dev.set_freq_power(np.mean(freq_list), power)

        # pre_seqCmds 
        if pre_seqCmds:
            #use only lists
            if isinstance(pre_seqCmds,dict): 
                pre_seqCmds = list(pre_seqCmds.values())

            self._validate_sequence_commands(pre_seqCmds,freq_list,location='pre')

            # pre_seqCmds cannot contain count events, otherwise return size is wrong
            if self._determine_count_events(pre_seqCmds):
                self.log.error("Invalid 'pre_seqCmds' given, as it contained 'CU_EN'=1 events")

        # post_seqCmds 
        if post_seqCmds:
            # use only lists
            if isinstance(post_seqCmds,dict): 
                post_seqCmds = list(post_seqCmds.values())

            self._validate_sequence_commands(post_seqCmds,freq_list, location='post')

            # post_seqCmds cannot contain count events, otherwise return size is wrong
            if self._determine_count_events(post_seqCmds):
                self.log.error("Invalid 'post_seqCmds' given, as it contained 'CU_EN'=1 events")

        # primary_seqCmds
        if isinstance(primary_seqCmds,dict): 
            # use only lists
            primary_seqCmds = list(primary_seqCmds.values())

        self._validate_sequence_commands(primary_seqCmds,freq_list,location='primary')

        # determine number of count events in the primary block
        # number of measurements is counted from 0
        if overrideMeasLength is None:
            meas_len = self._determine_count_events(primary_seqCmds)
        else:
            meas_len = overrideMeasLength   # only do this if you're sure on your return size

        self._meas_length_pulse = meas_len 
        self._dev.ctrl.measurementLength.set(meas_len-1)

        # build entire block
        full_seqCmds = pre_seqCmds + primary_seqCmds * n_reps + post_seqCmds
        self._validate_sequence_commands(full_seqCmds,freq_list,location='full')

        # make sure there is an even number of sequence commands, otherwise strang results
        if len(full_seqCmds) % 2:
            self.log.error( "Invalid sequence full_seqCmds:",
                           f" must contain an even number of instruction sets, got len={len(full_seqCmds)}")

        # assign sequences to registers
        self._dev.setGenSeqCmds(
            genSeqCmds = full_seqCmds,           # sequence commands 
            offset = sequence_offset,            # default value = 0
            updateSeqSizeReg = updateSeqSizeReg) # default value = 1

        # for pulsed measurements, accumulation is necessary otherwise values will underflow
        self._dev.ctrl.accumulationMode.set(accumulationMode)

        # loading sequence through DMA read to fpga
        # (this is required each time the sequence is started)
        self._dev.ddr4Ctrl.loadSeq() 

        # make sure we get the same number back as written
        len_given = sequence_offset + len(full_seqCmds)
        len_written = 2 * self._dev.ddr4Ctrl.size.get() 
        if len_given != len_written:
            self.log.error("Invalid sequence full_seqCmds:",
                           " did not get expected number of loaded commands, ",
                          f" specified len={len_given}, written len={len_written}")

        mm = self.get_measurement_methods()
        self.meas_method = mm.meas_method[MicrowaveQMeasurementMode.GENERAL_PULSED] 

        return 0


    @staticmethod
    def _determine_count_events(seqCmds):
        """ Given a primary sequence command block, determine number of 
            seperate count events caused by a rising or falling edge of the 'CU_EN'
        
        @param list of dict: primary_seqCmds: sequence command events
        """
        cu_count = 0
        current, previous = 0, 0
        for cmd in seqCmds:
            current = cmd.get('CU_EN', cmd.get('cu_en',None))
            if current is not None:
                if (current == 1) and (previous == 0):
                    cu_count += 1 
                    
                previous = current 

        return cu_count


    def _validate_sequence_commands(self, seqCmds, freq_list,location='primary'):
        """Determine validity of a primary sequence block 
        @param list of dict: seqCmds_primary : list of dictionaries with sequence commands
                                            sequence measurement list size is determined from 
                                            number of rising and falling edges of 'CU_EN'
        @param list: freq_list: a simple reference for sequences of frequencies, to check against size

        Note: this modifies names to be capitalized
        """
        valid_commands = {'RF_EN':int, 'LS_EN':int, 'CU_EN':int, 
                        'RF_RECONFIG_EN':int, 'GPOS':int, 'RF_FREQ_SEL':int,
                        'RF_GAIN':float, 'RF_PHASE':float, 'DURATION':float}
            
        # use only list formats
        if isinstance(seqCmds, dict):
            seqCmds = list(seqCmds.values())   # assume orderedDict
        
        # only deal with upper case command names
        seqCmds = [{k.upper(): v for k,v in cmd.items()} for cmd in seqCmds]
        
        # look for bad command names
        error_i, error_limit = 0, 10
        for i, cmd in enumerate(seqCmds):
            for k,v in cmd.items():
                if k not in valid_commands.keys():
                    self.log.warning(f'Invalid sequence {location}_command[{i}]: command {k} is not valid')
                    error_i += 1
                    
                if not isinstance(v,valid_commands[k]):
                    self.log.warning(f'Invalid sequence {location}_command[{i}]: {k} = {v},',
                                     f' value was not type={type(valid_commands[k])}')
                    error_i += 1
                    
            if error_i > error_limit: break  # too many errors, stop reporting
        
        # no point to continue if there's errors
        if error_i:
            self.log.error("Invalid sequence commands found, correct to continue")
            return False
        
        # check number of RF configurations engagements
        n_freq = len(freq_list)
        for i, cmd in enumerate(seqCmds):
            # referred to frequency indicies. This cannot exceed the freq_list len
            freq_i = cmd.get('RF_FREQ_SEL',0)
            if (freq_i < 0) or (freq_i > n_freq -1):
                self.log.error(f"Invalid sequence {location}_command[{i}]: ",
                               f"RF_FREQ_SEL = {freq_i} out of freq_list bounds")
                return False
            
        # check that frequency references are preceeded by a reconfigure
        # check that a frequency has been configured before use
        config_freq = None
        for i, cmd in enumerate(seqCmds):
            # make sure that a frequency index has been specified if there was a reconfigure
            if (cmd.get('RF_RECONFIG_EN') == 1) and (cmd.get('RF_FREQ_SEL',None) is None):
                self.log.error(f"Invalid sequence {location}_command[{i}]: ",
                                "'RF_RECONFIG_EN' was specified, but missing 'RF_FREQ_SEL'")
                return False
            
            if cmd.get('RF_RECONFIG_EN') == 1:
                config_freq = cmd['RF_FREQ_SEL']  
            else:
                curr_freq = cmd.get('RF_FREQ_SEL')
                if (curr_freq is not None) and (curr_freq != config_freq):
                    err_str = f"Invalid sequence {location}_command[{i}]: 'RF_FREQ_SEL' = {curr_freq}" + \
                              f" differs from config_freq_index={config_freq}, apply 'RF_RECONFIG_EN' first"
                    self.log.error(err_str)
                    return False
        
        # otherwise it was ok
        return True


# ==============================================================================
#                  ODMR Interface methods
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
            
            self._esr_count_frequency = clock_frequency    #FIXME: check can be mode param

        if self._mq_state.get_state() == RecorderState.BUSY:
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

        if self._mq_state.get_state() == RecorderState.BUSY:

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
        self._mq_state.set_state(RecorderState.IDLE)
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
#                  MW Interface
# ==============================================================================

    def off(self):
        """
        Switches off any microwave output.
        Must return AFTER the device is actually stopped.

        @return int: error code (0:OK, -1:error)
        """

        mode, _ = self.get_current_device_mode()
        
        # allow to run this method in the unconfigured mode, it is more a 
        if (mode == MicrowaveQMode.CW_MW) or (mode == MicrowaveQMode.ESR) or (mode == MicrowaveQMode.UNCONFIGURED):

            self._dev.rfpulse.setGain(0.0)
            self._dev.ctrl.stop()
            self.trf_off()
            self._dev.rfpulse.stopRF()
            #self.vco_off()
            self.stop_measurement()

            # allow the state transition only in the proper state.
            if self._mq_state.is_legal_transition(RecorderState.IDLE):
                self._mq_state.set_state(RecorderState.IDLE)
            
            return 0
        else:
            self.log.warning(f'MicrowaveQ cannot be stopped from the '
                             f'MicrowaveInterface method since the currently '
                             f'configured mode "{MicrowaveQMode.name(mode)}" is not "ESR" or "CW_MW". '
                             f'Stop the microwaveQ in its proper measurement '
                             f'mode.')
            return -1


    def get_status(self):
        """
        Gets the current status of the MW source, i.e. the mode (cw, list or sweep) and
        the output state (stopped, running)

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        mode, _ = self.get_current_device_mode()
        mode_str = { MicrowaveQMode.COUNTER: 'cw',
                     MicrowaveQMode.ESR:     'list'}.get(mode,'sweep')

        return mode_str, self.get_current_device_state() == RecorderState.BUSY 

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

        #FIXME: power is set arbitrary
        # this is a variant of self._prepare_counter, however with inconsitent modularity
        # this needs to be corrected to use self.configure_recorder() operations
        self._set_current_device_mode()

        self._dev.configureCW(frequency=self._mw_cw_frequency, 
                              countingWindowLength=0.5, accumulationMode=0)
        self._dev.ctrl.start(0)

        self._mq_state.set_state(RecorderState.BUSY)
        return 0


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
        ret_val = self.configure_recorder(mode=MicrowaveQMode.CW_MW, params=params)

        self._mw_cw_frequency, self._mw_cw_power = self._dev.get_freq_power()

        if ret_val == -1:
            # this will cause a deliberate error
            message = 'INVALID'
        else:
            message = 'cw'

        return self._mw_cw_frequency, self._mw_cw_power, message 


    def list_on(self):
        """
        Switches on the list mode microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """
        mode, _ = self.get_current_device_mode()
        if mode == MicrowaveQMode.ESR:
            self.start_recorder()
            #self._mq_state.set_state(RecorderState.BUSY)
            return 0
        else:
            # was not configured correctly 
            return -1

    def set_list(self, frequency=None, power=None):
        """
        Configures the device for list-mode and optionally sets frequencies and/or power

        @param list frequency: list of frequencies in Hz
        @param float power: MW power of the frequency list in dBm

        @return list, float, str: current frequencies in Hz, current power in dBm, current mode
        """

        mean_freq = None

        if frequency is not None:
            #FIXME: the power setting is a bit confusing. It is mainly done in 
            # this way in case no power value was provided
            self._mw_freq_list = frequency
            params = {'mw_frequency_list': frequency,
                      'count_frequency':   self._esr_count_frequency,
                      'mw_power':          self._mw_power,
                      'num_meas':          1000 }
            self.configure_recorder(mode=MicrowaveQMode.ESR, params=params)

            mean_freq = np.mean(self._mw_freq_list)

        if power is None:
            # take the currently set power
            _, power = self._dev.get_freq_power()

        self._dev.set_freq_power(mean_freq, power)
        self._mw_power = power

        _, self._mw_cw_power = self._dev.get_freq_power()

        return self._mw_freq_list, self._mw_cw_power, 'list' 

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
    #                 Recorder Interface Implementation
    # ==========================================================================


    def _create_recorder_constraints(self):

        rc = self._RECORDER_CONSTRAINTS

        rc.max_detectors = 1
        features = self._dev.get_unlocked_features()

        rc.recorder_mode_params = {}

        rc.recorder_modes = [MicrowaveQMode.UNCONFIGURED, 
                            MicrowaveQMode.DUMMY]

        rc.recorder_mode_states[MicrowaveQMode.UNCONFIGURED] = [RecorderState.LOCKED, RecorderState.UNLOCKED]

        rc.recorder_mode_params[MicrowaveQMode.UNCONFIGURED] = {}
        rc.recorder_mode_params[MicrowaveQMode.DUMMY] = {}

        rc.recorder_mode_measurements = {MicrowaveQMode.UNCONFIGURED: MicrowaveQMeasurementMode.DUMMY, 
                                         MicrowaveQMode.DUMMY: MicrowaveQMeasurementMode.DUMMY}

        # feature set 1 = 'Continous Counting'
        if features.get(MicrowaveQFeatures.CONTINUOUS_COUNTING.value) is not None:
            rc.recorder_modes.append(MicrowaveQMode.COUNTER)
            rc.recorder_modes.append(MicrowaveQMode.CONTINUOUS_COUNTING)

            # configure possible states in a mode
            rc.recorder_mode_states[MicrowaveQMode.COUNTER] = [RecorderState.IDLE, RecorderState.BUSY]
            rc.recorder_mode_states[MicrowaveQMode.CONTINUOUS_COUNTING] = [RecorderState.IDLE, RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[MicrowaveQMode.COUNTER] = {'count_frequency': 100}
            rc.recorder_mode_params[MicrowaveQMode.CONTINUOUS_COUNTING] = {'count_frequency': 100}

            # configure default parameter for mode
            rc.recorder_mode_params_defaults[MicrowaveQMode.COUNTER] = {}  # no defaults
            rc.recorder_mode_params_defaults[MicrowaveQMode.CONTINUOUS_COUNTING] = {}  # no defaults

            # configure required measurement method
            rc.recorder_mode_measurements[MicrowaveQMode.COUNTER] = MicrowaveQMeasurementMode.COUNTER
            rc.recorder_mode_measurements[MicrowaveQMode.CONTINUOUS_COUNTING] = MicrowaveQMeasurementMode.COUNTER

        # feature set 2 = 'Continuous ESR'
        if features.get(MicrowaveQFeatures.CONTINUOUS_ESR.value) is not None:
            rc.recorder_modes.append(MicrowaveQMode.CW_MW)
            rc.recorder_modes.append(MicrowaveQMode.ESR)
            
            # configure possible states in a mode
            rc.recorder_mode_states[MicrowaveQMode.CW_MW] = [RecorderState.IDLE, RecorderState.BUSY]
            rc.recorder_mode_states[MicrowaveQMode.ESR] = [RecorderState.IDLE, RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[MicrowaveQMode.CW_MW] = {'mw_frequency': 2.8e9,
                                                            'mw_power': -30}
            rc.recorder_mode_params[MicrowaveQMode.ESR] = {'mw_frequency_list': [],
                                                          'mw_power': -30,
                                                          'count_frequency': 100,
                                                          'num_meas': 100}

            # configure defaults for mode
            rc.recorder_mode_params_defaults[MicrowaveQMode.CW_MW] = {}   # no defaults
            rc.recorder_mode_params_defaults[MicrowaveQMode.ESR] = {}     # no defaults

            # configure measurement method
            rc.recorder_mode_measurements[MicrowaveQMode.CW_MW] = MicrowaveQMeasurementMode.ESR
            rc.recorder_mode_measurements[MicrowaveQMode.ESR] = MicrowaveQMeasurementMode.ESR

        # feature set 4 = 'Rabi'
        if features.get(MicrowaveQFeatures.RABI) is not None:
            # to be implemented
            pass

        # feature set 8 = 'Pulsed ESR'
        if features.get(MicrowaveQFeatures.PULSED_ESR) is not None:
            # to be implemented
            pass

        # feature set 16 = 'Pixel Clock'
        if features.get(MicrowaveQFeatures.PIXEL_CLOCK.value) is not None:
            rc.recorder_modes.append(MicrowaveQMode.PIXELCLOCK)
            rc.recorder_modes.append(MicrowaveQMode.PIXELCLOCK_SINGLE_ISO_B)
            
            # configure possible states in a mode
            rc.recorder_mode_states[MicrowaveQMode.PIXELCLOCK] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]
            rc.recorder_mode_states[MicrowaveQMode.PIXELCLOCK_SINGLE_ISO_B] = [RecorderState.IDLE, RecorderState.ARMED, RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[MicrowaveQMode.PIXELCLOCK] = {'mw_frequency': 2.8e9,
                                                                'num_meas': 100}
            rc.recorder_mode_params[MicrowaveQMode.PIXELCLOCK_SINGLE_ISO_B] = {'mw_frequency': 2.8e9,
                                                                              'mw_power': -30,
                                                                              'num_meas': 100}

            # configure defaults for mode
            rc.recorder_mode_params_defaults[MicrowaveQMode.PIXELCLOCK] = {}               # no defaults
            rc.recorder_mode_params_defaults[MicrowaveQMode.PIXELCLOCK_SINGLE_ISO_B] = {}  # no defaults

            rc.recorder_mode_measurements[MicrowaveQMode.PIXELCLOCK] = MicrowaveQMeasurementMode.PIXELCLOCK
            rc.recorder_mode_measurements[MicrowaveQMode.PIXELCLOCK_SINGLE_ISO_B] = MicrowaveQMeasurementMode.PIXELCLOCK

        # feature set 32 = 'Ext Triggered Measurement'
        if features.get(MicrowaveQFeatures.EXT_TRIGGERED_MEASUREMENT.value) is not None:
            # to be implemented
            pass

        # feature set 64 = 'ISO' (n iso-B)
        if features.get(MicrowaveQFeatures.ISO.value) is not None:
            rc.recorder_modes.append(MicrowaveQMode.PIXELCLOCK_N_ISO_B)

            # configure possible states in a mode
            rc.recorder_mode_states[MicrowaveQMode.PIXELCLOCK_N_ISO_B] = [RecorderState.IDLE, 
                                                                          RecorderState.ARMED, 
                                                                          RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[MicrowaveQMode.PIXELCLOCK_N_ISO_B] = {'mw_frequency_list': [2.8e9, 2.81e9],
                                                                         'mw_pulse_lengths': [10e-3, 10e-3],
                                                                         'mw_power': -30,
                                                                         'num_meas': 100}

            # configure defaults for mode
            rc.recorder_mode_params_defaults[MicrowaveQMode.PIXELCLOCK_N_ISO_B] = {'mw_n_freq_splits': 1, 
                                                                                   'mw_laser_cooldown_time': 10e-6 }

            rc.recorder_mode_measurements[MicrowaveQMode.PIXELCLOCK_N_ISO_B] = MicrowaveQMeasurementMode.PIXELCLOCK_N_ISO_B

        # feature set 128 = 'Tracking' (tracked n iso-B)
        if features.get(MicrowaveQFeatures.TRACKING.value) is not None:
            # to be implemented
            pass
        
        # feature set 256 = 'General Pulsed Mode'
        if features.get(MicrowaveQFeatures.GENERAL_PULSED_MODE.value) is not None:
            rc.recorder_modes.append(MicrowaveQMode.GENERAL_PULSED)

            # configure possible states in a mode
            rc.recorder_mode_states[MicrowaveQMode.GENERAL_PULSED] = [RecorderState.IDLE, 
                                                                      RecorderState.ARMED, 
                                                                      RecorderState.BUSY]

            # configure required paramaters for a mode
            rc.recorder_mode_params[MicrowaveQMode.GENERAL_PULSED] = {'mw_frequency_list': [2.8e9],   #DGCfix
                                                                      'mw_power': -30,
                                                                      'pulsed_primary_seqCmds': [
                                                                        {'RF_RECONFIG_EN':1,'RF_FREQ_SEL':0,'DURATION':0.0},    
                                                                        {'RF_EN':1,'RF_FREQ_SEL':0,'DURATION':0.0}    
                                                                       ]
                                                                      }

            # configure defaults for mode
            rc.recorder_mode_params_defaults[MicrowaveQMode.GENERAL_PULSED] = {'pulsed_pre_seqCmds': [],
                                                                               'pulsed_post_seqCmds': [],
                                                                               'pulsed_sequence_offset': 0,
                                                                               'pulsed_update_sequence_size': True,
                                                                               'pulsed_accumulationMode': True,
                                                                               'pulsed_override_meas_len': None
                                                                              }

            rc.recorder_mode_measurements[MicrowaveQMode.GENERAL_PULSED] = MicrowaveQMeasurementMode.GENERAL_PULSED

        # feature set 512 = 'APD to GPO'
        if features.get(MicrowaveQFeatures.APD_TO_GPO.value) is not None:
            # to be implemented
            pass

        # feature set 1024 = 'Parallel Streaming Channel'
        if features.get(MicrowaveQFeatures.PARALLEL_STREAMING_CHANNEL.value) is not None:
            # to be implemented
            pass

        # feature set 2048 = 'MicroSD Write Access'
        if features.get(MicrowaveQFeatures.MICROSD_WRITE_ACCESS.value) is not None:
            # is there something to implement here?  This is only an access flag 
            pass



    def get_recorder_constraints(self):
        """ Retrieve the hardware constraints from the recorder device.

        @return RecorderConstraints: object with constraints for the recorder
        """
        return self._RECORDER_CONSTRAINTS


    def _create_recorder_meas_constraints(self):
        rm = self._RECORDER_MEAS_CONSTRAINTS

        # Dummy method
        mmode = MicrowaveQMeasurementMode.DUMMY
        rm.meas_modes = [mmode]
        rm.meas_formats = {mmode : ()}
        rm.meas_method = {mmode : None}

        # Counter method
        mmode = MicrowaveQMeasurementMode.COUNTER
        rm.meas_modes.append(mmode)
        rm.meas_formats[mmode] = \
            [('count_num', '<i4'),
             ('counts', '<i4')]
        rm.meas_method[mmode] = self._meas_method_SlowCounting

        # Line methods
        # Pixelclock
        mmode = MicrowaveQMeasurementMode.PIXELCLOCK
        rm.meas_modes.append(mmode)

        #HACK: current work around to handle legacy FPGA codes
        rec_type = 'int_time' if self._FPGA_version >= 13 else 'time_rec'

        rm.meas_formats[mmode] = \
            [('count_num', '<i4'),  
             ('counts', '<i4'),
             ('blank2', '<i4'),                    # place holder
             ('blank3', '<i4'),                    # place holder
             (rec_type, '<f8')]
        rm.meas_method[mmode] = self._meas_method_PixelClock

        # Pixelclock single iso-B
        mmode = MicrowaveQMeasurementMode.PIXELCLOCK_SINGLE_ISO_B
        rm.meas_modes.append(mmode)
        rm.meas_formats[mmode] = \
            [('count_num', '<i4'),  
             ('counts', '<i4'),                    # place holder
             ('blank2', '<i4'),                    # place holder
             ('blank3', '<i4'),                    # place holder
             ('time_rec', '<f8')]
        rm.meas_method[mmode] = self._meas_method_PixelClock

        # n iso-B
        mmode = MicrowaveQMeasurementMode.PIXELCLOCK_N_ISO_B
        rm.meas_modes.append(mmode)
        rm.meas_formats[mmode] = \
            [('count_num', '<i4'),
             ('counts', '<i4'),
             ('counts2', '<i4'),
             ('counts_diff', '<i4'),
             ('time_rec', '<f8')]
        rm.meas_method[mmode] = self._meas_method_n_iso_b

        # esr 
        mmode = MicrowaveQMeasurementMode.ESR
        rm.meas_modes.append(mmode)
        rm.meas_formats[mmode] = \
            [('time_rec', '<f8'),
             ('count_num', '<i4'),
             ('data', np.dtype('<i4',(2,))) ]   # this is defined at the time of use
        rm.meas_method[mmode] = self._meas_method_esr

        # general pulsed mode 
        mmode = MicrowaveQMeasurementMode.GENERAL_PULSED
        rm.meas_modes.append(mmode)
        rm.meas_formats[mmode] = \
            [('time_rec', '<f8'),
             ('count_num', '<i4'),
             ('data', np.dtype('<i4',(2,))) ]   # this is defined at the time of use
        rm.meas_method[mmode] = self._meas_method_pulsed


    def get_recorder_meas_constraints(self):
        """ Retrieve the measurement recorder device.

        @return RecorderConstraints: object with constraints for the recorder
        """
        return self._RECORDER_MEAS_CONSTRAINTS

    def _check_params_for_mode(self, mode, params):
        """ Make sure that all the parameters are present for the current mode.
        
        @param MicrowaveQMode mode: mode of recorder, as available from 
                                  MicrowaveQMode types
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
                                 f'"{MicrowaveQMode.name(mode)}". Correct this!')
                is_ok = False

        return is_ok


    def configure_recorder(self, mode, params):
        """ Configures the recorder mode for current measurement. 

        @param MicrowaveQMode mode: mode of recorder, as available from 
                                  MicrowaveQMode types
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

        if (dev_state == RecorderState.BUSY) and (curr_mode != MicrowaveQMode.CW_MW): 
            # on the fly configuration (in BUSY state) is only allowed in CW_MW mode.
            self.log.error(f'MicrowaveQ cannot be configured in the '
                           f'requested mode "{MicrowaveQMode.name(mode)}", since the device '
                           f'state is in "{dev_state}". Stop ongoing '
                           f'measurements and make sure that the device is '
                           f'connected to be able to configure if '
                           f'properly.')
            return -1
            

        # check at first if mode is available
        limits = self.get_recorder_constraints()

        if mode not in limits.recorder_modes:
            self.log.error(f'Requested mode "{MicrowaveQMode.name(mode)}" not available in '
                            'microwaveQ. Check "mq._dev.get_unlocked_features()"; '
                            'Possibly incorrect MQ feature key. Configuration stopped.')
            return -1

        rc_defaults = limits.recorder_mode_params_defaults[mode]
        is_ok = self._check_params_for_mode(mode, params)
        if not is_ok:
            self.log.error(f'Parameters are not correct for mode "{MicrowaveQMode.name(mode)}". '
                           f'Configuration stopped.')
            return -1

        ret_val = 0
        # the associated error message for a -1 return value should come from 
        # the method which was called (with a reason, why configuration could 
        # not happen).

        # after all the checks are successful, delegate the call to the 
        # appropriate preparation function.
        if mode == MicrowaveQMode.UNCONFIGURED:
            # not sure whether it makes sense to configure the device 
            # deliberately in an unconfigured state, it sounds like a 
            # contradiction in terms, but it might be important if device is reset
            pass

        elif mode == MicrowaveQMode.DUMMY:
            ret_val = self._prepare_dummy()

        elif mode == MicrowaveQMode.PIXELCLOCK:
            ret_val = self._prepare_pixelclock(freq=params['mw_frequency'])

        elif mode == MicrowaveQMode.PIXELCLOCK_SINGLE_ISO_B:
            #TODO: make proper conversion of power to mw gain
            ret_val = self._prepare_pixelclock_single_iso_b(freq=params['mw_frequency'], 
                                                           power=params['mw_power'])

        elif mode == MicrowaveQMode.PIXELCLOCK_N_ISO_B:                                
            ret_val = self._prepare_pixelclock_n_iso_b(freq_list=params['mw_frequency_list'],
                                                       pulse_lengths=params['mw_pulse_lengths'],
                                                       power=params['mw_power'],
                                                       n_freq_splits=params.get('mw_n_freq_splits',
                                                                    rc_defaults['mw_n_freq_splits']),
                                                       laserCooldownLength=params.get('mw_laser_cooldown_time',
                                                                          rc_defaults['mw_laser_cooldown_time']))
        
        elif mode == MicrowaveQMode.GENERAL_PULSED:
            ret_val = self._prepare_pulsed_mode(freq_list=params['mw_frequency_list'],
                                                power=params['mw_power'],
                                                primary_seqCmds=params['pulsed_primary_seqCmds'],
                                                n_reps=params['num_meas'],
                                                pre_seqCmds=params.get('pulsed_pre_seqCmds',
                                                           rc_defaults['pulsed_pre_seqCmds']) ,
                                                post_seqCmds=params.get('pulsed_post_seqCmds',
                                                            rc_defaults['pulsed_post_seqCmds']),
                                                sequence_offset=params.get('pulsed_sequence_offset',
                                                               rc_defaults['pulsed_sequence_offset']),
                                                update_sequence_size=params.get('pulsed_update_sequence_size',
                                                                    rc_defaults['pulsed_update_sequence_size']),
                                                accumulationMode=params.get('pulsed_accumulationMode',
                                                                 rc_defaults['pulsed_accumulationMode']),
                                                overrideMeasLength=params.get('pulsed_override_meas_len',
                                                                  rc_defaults['pulsed_override_meas_len']))

        elif mode == MicrowaveQMode.COUNTER:
            ret_val = self._prepare_counter(counting_window=1/params['count_frequency'])

        elif mode == MicrowaveQMode.CONTINUOUS_COUNTING:
            #TODO: implement this mode
            self.log.error(f"Configure recorder: mode {mode} currently not implemented")

        elif mode == MicrowaveQMode.CW_MW:
            ret_val = self._configure_cw_mw(frequency=params['mw_frequency'],
                                            power=params['mw_power'])

        elif mode == MicrowaveQMode.ESR:
            #TODO: replace gain by power (and the real value)
            ret_val = self._prepare_cw_esr(freq_list=params['mw_frequency_list'], 
                                          count_freq=params['count_frequency'],
                                          power=params['mw_power'])

        if ret_val == -1:
            self._set_current_device_mode(mode=MicrowaveQMode.UNCONFIGURED, 
                                          params={})
        else:
            self._set_current_device_mode(mode=mode, 
                                          params=params)
            self._mq_state.set_state(RecorderState.IDLE)

        return ret_val


    def start_recorder(self, arm=False):
        """ Start recorder 
        start recorder with mode as configured 
        If pixel clock based methods, will begin on first trigger
        If not first configured, will cause an error
        
        @param bool: arm: specifies armed state with regard to pixel clock trigger
        
        @return bool: success of command
        """
        mode, params = self.get_current_device_mode()
        state = self.get_current_device_state()
        meas_type = self.get_current_measurement_method()
        meas_cons = self.get_recorder_meas_constraints()
        
        if state == RecorderState.LOCKED:
            self.log.warning('MicrowaveQ has not been unlocked.')
            return False 

        elif mode == MicrowaveQMode.UNCONFIGURED:
            self.log.warning('MicrowaveQ has not been configured.')
            return  False

        elif (state != RecorderState.IDLE) and (state != RecorderState.IDLE_UNACK):
            self.log.warning('MicrowaveQ is not in Idle mode to start the measurement.')
            return False 

        num_meas = params['num_meas']

        if arm and meas_type.movement  != 'line':
            self.log.warning('MicrowaveQ: attempt to set ARMED state for a continuous measurement mode')
            return False 
        
        # data format
        # Pixel clock (line methods)
        if meas_type.movement == 'line':
            self._total_pulses = num_meas 
            self._counted_pulses = 0

            self._curr_frame = []
            self._meas_res = np.zeros((num_meas),
              dtype= meas_cons.meas_formats[meas_type])

            self._mq_state.set_state(RecorderState.ARMED)

        # Esr, Pulsed (point methods)
        elif meas_type.movement == 'point':
            if mode == MicrowaveQMode.ESR:
                self._meas_esr_res = np.zeros((num_meas, len(self._meas_esr_line)))
                self._esr_counter = 0
                self._current_esr_meas = []

            elif mode == MicrowaveQMode.GENERAL_PULSED:
                #self._meas_pulsed_res = None    # method for indeterminate size arrays

                self._meas_pulsed_res = np.zeros((num_meas, self._meas_length_pulse + 1),  #include frame_num
                                                  dtype='<i4')
                self._total_pulses = num_meas 

                self._dev.ctrl.measurementLength.set(self._meas_length_pulse - 1)
                self._pulsed_counter = 0
                self._current_pulsed_meas = []

            else:
                self.log.error('MicrowaveQ configuration error; inconsistent modality')

            self._mq_state.set_state(RecorderState.BUSY)

        else:
            self.log.error(f'MicrowaveQ: method {mode}, movement_type={meas_type.movement}'
                            ' not implemented yet')
            return False 

        self.skip_data = False

        # Pulsed method
        if mode == MicrowaveQMode.GENERAL_PULSED:
            # General pulsed mode operates through ddr4 controller
            # number of measurments set in configure_recorder method
            self._dev.ddr4Ctrl.loadSeq() # loading sequence through DMA read to fpga
            self._dev.ctrl.startGenPulseMode() # starting general pulsed mode

        else:
            # all other methods
            self._dev.ctrl.start(num_meas)

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
        # block until measurement is done
        if self._mq_state.get_state() == RecorderState.BUSY or \
            self._mq_state.get_state() == RecorderState.ARMED:
                with self.threadlock:
                    self.meas_cond.wait(self.threadlock)

        # released
        self._mq_state.set_state(RecorderState.IDLE)
        self.skip_data = True

        return self.get_available_measurements(meas_keys=meas_keys)


    def get_available_measurements(self, meas_keys=None):
        """ get available measurement
        returns the measurement array in integer format (non-blocking, does not change state)

        @param (list): meas_keys:  list of measurement keys to be returned;
                                   keys which do not exist in measurment object are returned as None;
                                   If None is passed, only 'counts' is returned 

        @return int_array: array of measurement as tuple elements, format depends upon 
                           current mode setting
        """
        _, params = self.get_current_device_mode()
        meas_method_type = self.get_current_measurement_method()

        # pixel clock methods
        if meas_method_type == MicrowaveQMeasurementMode.PIXELCLOCK or \
            meas_method_type == MicrowaveQMeasurementMode.PIXELCLOCK_SINGLE_ISO_B or \
            meas_method_type == MicrowaveQMeasurementMode.PIXELCLOCK_N_ISO_B:

            if meas_keys is None: 
                meas_keys = ['counts']
            elif not isinstance(meas_keys,(list, tuple)):
                meas_keys = [meas_keys]

            res = []
            for meas_key in meas_keys:
                if meas_key in self._meas_res.dtype.names: 
                    res.append(self._meas_res[meas_key])
                else:
                    res.append(None)
            
            return res
           
        # ESR methods
        elif meas_method_type == MicrowaveQMeasurementMode.ESR:
            self._meas_esr_res[:, 2:] = self._meas_esr_res[:, 2:] * params['count_frequency']  
            return self._meas_esr_res

        elif meas_method_type == MicrowaveQMeasurementMode.GENERAL_PULSED:
            return self._meas_pulsed_res
        
        else:
            self.log.error(f'MicrowaveQ error: measurement method {meas_method_type} not implemented yet')
            return 0


    #FIXME: this might be a redundant method and can be replaced by get_recorder_limits
    def get_parameters_for_modes(self, mode=None):
        """ Returns the required parameters for the modes

        @param MicrowaveQMode mode: specifies the mode for sought parameters
                                  If mode=None, all modes with their parameters 
                                  are returned. Otherwise specific mode 
                                  parameters are returned  

        @return dict: containing as keys the MicrowaveQMode.mode and as values a
                      dictionary with all parameters associated to the mode.
                      
                      Example return with mode=MicrowaveQMode.CW_MW:
                            {MicrowaveQMode.CW_MW: {'countwindow': 10,
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
                MicrowaveQMode.mode mode: the current recorder mode 
                dict params: the current configuration parameter
        """
        return self._mq_curr_mode, self._mq_curr_mode_params


    def _set_current_device_mode(self, mode, params):
        """ Set the current device mode. 
        
        @param MicrowaveQMode mode: mode of recorder, as available from 
                                  MicrowaveQMode types
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
       

    def get_measurement_methods(self):
        """ gets the possible measurement methods
        """
        return self._RECORDER_MEAS_CONSTRAINTS


    def get_current_measurement_method(self):
        """ get the current measurement method
        (Note: the measurment method cannot be set directly, it is an aspect of the measurement mode)

        @return MicrowaveQMeasurementMode
        """
        rc = self._RECORDER_CONSTRAINTS
        return rc.recorder_mode_measurements[self._mq_curr_mode]


    def get_current_measurement_method_name(self):
        """ gets the name of the measurment method currently in use
        
        @return string
        """
        curr_mm = self.get_current_measurement_method()
        return curr_mm.name

