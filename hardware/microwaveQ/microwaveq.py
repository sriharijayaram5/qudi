# -*- coding: utf-8 -*-
"""
Dummy implementation for simple data acquisition.

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
from qtpy import QtCore

import threading
import numpy as np
import time
import struct

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from interface.slow_counter_interface import SlowCounterInterface, SlowCounterConstraints, CountingMode
from .microwaveq_py.microwaveQ import microwaveQ

from interface.microwave_interface import MicrowaveInterface
from interface.microwave_interface import MicrowaveLimits
from interface.microwave_interface import MicrowaveMode
from interface.microwave_interface import TriggerEdge



class MicrowaveQ(Base, SlowCounterInterface):
    """ A simple Data generator dummy.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'simple_data_dummy.SimpleDummy'
        ip_address: '192.168.2.10'
        port: 55555
        unlock_key: <your obtained key, either in hex or number> e.g. of the form: 58293468969010369791345065897427835159

    """

    _modclass = 'MicrowaveQ'
    _modtype = 'hardware'

    __version__ = '0.1.1'

    _CLK_FREQ_FPGA = 153.6e6 # is used to obtain the correct mapping of signals.

    ip_address = ConfigOption('ip_address', default='192.168.2.10')
    port = ConfigOption('port', default=55555, missing='info')
    unlock_key = ConfigOption('unlock_key', missing='error')



    sigNewData = QtCore.Signal(tuple)

    sigLineFinished = QtCore.Signal()

    sigNewESRData = QtCore.Signal(np.ndarray) # indicate whether new ESR data is present.

    _threaded = True

    result_available = threading.Event()

    _CONSTRAINTS = SlowCounterConstraints()

    _meas_mode = 'pixel'  # measurement modes: counter, pixel, esr
    _meas_mode_available = ['counter', 'pixel', 'esr']

    _device_status = 'idle'  # can be idle, armed or running
    _meas_running = False

    # measurement variables
    _DEBUG_MODE = True
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
    _mw_gain = 0.4 # not exposed to interface!!!

    #FIXME: quick and dirty implementation for the iso-B mode
    _use_iso_b = False
    _iso_b_freq = 500e6 # in MHz
    _iso_b_gain = 0.2 # linear gain for iso b mode.

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
        try:
            self._dev = microwaveQ.MicrowaveQ(self.ip_address,
                                             self.port,
                                             self.streamCb,
                                             self._CLK_FREQ_FPGA)
            self._dev.ctrl.unlock(self.unlock_key)
            self._dev.initialize()
        except Exception as e:
            self.log.error(f'Cannot establish connection to MicrowaveQ due to {str(e)}.')


        self._create_constraints()

        # locking mechanism for thread safety. Use it like
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.


        self.threadlock = Mutex()

        self._esr_process_lock = Mutex()
        self._esr_process_cond = QtCore.QWaitCondition()

        self.cond = QtCore.QWaitCondition()
        self._cond_waiting = False



        self.meas_thread = threading.Thread(target=self._measure_counts,
                                            name='meas_thread')

        self._current_esr_meas = []

        # set the main RF port (RF OUT 2H) to on
        self._dev.gpio.rfswitch.set(1)

    def on_deactivate(self):
        self.disconnect_mq()

    # ==========================================================================
    # Enhance the current module by threading capabilities:
    # ==========================================================================

    @QtCore.Slot(QtCore.QThread)
    def moveToThread(self, thread):
        super().moveToThread(thread)


    def connect_mq(self):

        if hasattr(self, '_dev'):
            if self.is_connected():
                self.disconnect_mq()


        try:
            self._dev = microwaveQ.MicrowaveQ(self.ip_address,
                                             self.port,
                                             self.streamCb,
                                             self._CLK_FREQ_FPGA)
            self._dev.ctrl.unlock(self.unlock_key)
            self._dev.initialize()
        except Exception as e:
            self.log.error(f'Cannot establish connection to MicrowaveQ due to {str(e)}.')

    def is_connected(self):
        if hasattr(self._dev.com.conn, 'axiConn'):
            return self._dev.com.conn.isConnected()
        else:
            return False

    def reconnect_mq(self):
        self.disconnect_mq()
        self.connect_mq()
        #FIXME: This should be removed later on!
        self.prepare_pixelclock()

    def disconnect_mq(self):
        self._dev.disconnect()


    def get_device_mode(self):
        return self._meas_mode


    def getModuleThread(self):
        """ Get the thread associated to this module.

          @return QThread: thread with qt event loop associated with this module
        """
        return self._manager.tm._threads['mod-hardware-' + self._name].thread


    def _create_constraints(self):
        self._CONSTRAINTS.max_detectors = 1
        self._CONSTRAINTS.min_count_frequency = 1e-3
        self._CONSTRAINTS.max_count_frequency = 1e+3
        self._CONSTRAINTS.counting_mode = [CountingMode.CONTINUOUS]

    # ==========================================================================
    #                 Begin: Slow Counter Interface Implementation
    # ==========================================================================

    def get_constraints(self):
        """ Retrieve the hardware constrains from the counter device.

        @return SlowCounterConstraints: object with constraints for the counter
        """

        return self._CONSTRAINTS

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

        return self.prepare_counter(counting_window)

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

        self._device_status = 'running'
        self._dev.ctrl.start(cnt_num_actual)
        # self.meas_thread = threading.Thread(target=self._measure_counts,
        #                                     name='meas_thread')
        # self.meas_thread.start()
        # self.meas_thread.join()

        #while self._meas_running:
        #   time.sleep(0.001)

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
        return 0

    # ==========================================================================
    #                 End: Slow Counter Interface Implementation
    # ==========================================================================

    def resetMeasurements(self):
        self.__measurements = 0

    def getMeasurements(self):
        return self.__measurements

    def get_meas_method(self):
        return self._meas_method

    def get_meas_method_name(self):
        return self._meas_method.__name__

    def set_meas_method(self, meas_method):

        if not callable(meas_method):
            if hasattr(self, meas_method):
                meas_method = getattr(self, meas_method)
            else:
                self.log.warning('No proper measurement method found. Call skipped.')
                return
        self._meas_method = meas_method


    def streamCb(self, frame):
        """ The Stream Callback function, which gets called by the FPGA upon the
            arrival of new data.

        @param bytes frame: The received data are a byte array containing the
                            results. This function will be called from
                            unsolicited by the device, whenever there is new
                            data available.
        """

        if self.skip_data:
            return

        frame_int = self._decode_frame(frame)

        if self._DEBUG_MODE:
            self._curr_frame.append(frame)  # just to keep track of the latest frame
            self._curr_frame_int = frame_int
            self._curr_frame_int_arr.append(frame_int)

        self.meas_method(frame_int)


    def meas_method(self, frame_int):
        """ this measurement methods becomes overwritten by the required mode. """
        pass

    def _measure_counts(self):

        self._dev.ctrl.start(self._count_number)
        self.result_available.wait()


    def prepare_counter(self, counting_window=0.001):

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

        self._dev.configureCW(frequency=500e6, countingWindowLength=self._counting_window)
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
                #print(f'Count index: {self._count_ext_index}')

                return

        else:

            self.__counts_temp = frame_int[1]

        #print(f'Finished yeah!: {self.__counts_temp}')
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

        self._meas_res[self._counted_pulses] = (frame_int[0], frame_int[1], time.time())


        if self._counted_pulses > (self._total_pulses - 2):
            self._meas_running = False
            self.cond.wakeAll()
            self.skip_data = True

        self._counted_pulses += 1
        #print(frame_int)
        #self.log.info(f'Frame_int: {frame_int}')

    def meas_esr(self, frame_int):

        #self.log.info('result')
        # print(f' frame_int:{frame_int}')

        self._meas_esr_res[self._esr_counter][0] = time.time()
        self._meas_esr_res[self._esr_counter][1:] = frame_int

        self._current_esr_meas.append(self._meas_esr_res[self._esr_counter][2:])

        self.sigNewESRData.emit(self._meas_esr_res[self._esr_counter][2:])



        if self._esr_counter > (len(self._meas_esr_res) - 2):
            self._meas_running = False
            self.cond.wakeAll()
            self.skip_data = True

        self._esr_counter += 1

        # wake up on every cycle
        self._esr_process_cond.wakeAll()


    def meas_stream_out(self, frame_int):
        self.sigNewData.emit(frame_int)
        return frame_int

    def prepare_pixelclock(self):

        self._meas_mode = 'pixel'

        self.meas_method = self.meas_method_PixelClock

        self._dev.configureCW_PIX(frequency=self._iso_b_freq)

        if self._use_iso_b:
            self._dev.rfpulse.setGain(self._iso_b_gain)
        else:
            self._dev.rfpulse.setGain(0.0)

        self._dev.resultFilter.set(0)

        return 0


    def arm_device(self, pulses=100):

        self._meas_mode = 'pixel'
        self._device_status = 'armed'

        self._dev.ctrl.start(pulses)
        self._total_pulses = pulses
        self._counted_pulses = 0

        self._curr_frame = []
        self._meas_res = np.zeros((pulses),
              dtype=[('count_num', '<i4'),
                     ('counts', '<i4'),
                     ('time_rec', '<f8')])

        self._meas_running = True
        self.skip_data = False

    def get_line(self):

        if self._meas_running:
            with self.threadlock:
                self._cond_waiting = True
                self.cond.wait(self.threadlock)
                self._cond_waiting = False

        self._device_status = 'idle'
        self.skip_data = True
        #self.sigLineFinished.emit()
        return self._meas_res['counts']


    def _decode_frame(self, frame):
        """ Decode the byte array with little endian encoding and 4 byte per
            number, i.e. a 32 bit number will be expected. """
        return struct.unpack('<' + 'i' * (len(frame)//4), frame)

    def stop_measurement(self):

        self._dev.ctrl.stop()
        self.cond.wakeAll()
        self.skip_data = True
        self._device_status = 'idle'

        self._esr_process_cond.wakeAll()

    #===========================================================================
    #       ESR measurements: ODMRCounterInterface Implementation
    #===========================================================================

    def prepare_cw_esr(self, freq_list, count_freq=100, gain=0.4):
        """ Prepare the CW ESR to obtain ESR frequency scans

        @param list freq_list: containing the frequency list entries
        @param float count_freq: count frequency in Hz
        """

        self._meas_mode = 'esr'

        self._esr_count_frequency = count_freq

        if isinstance(freq_list, np.ndarray):
            freq_list = freq_list.tolist()

        count_window = 1 / count_freq
        self._dev.configureCW_ESR(frequencies=freq_list,
                                  countingWindowLength=count_window)

        self._dev.rfpulse.setGain(gain)

        # the extra two numbers are for the current number of measurement run
        # and the time
        self._meas_esr_line = np.zeros(len(freq_list)+2)

        self.meas_method = self.meas_esr

    def start_esr(self, num_meas):

        self._esr_counter = 0
        self._meas_esr_res = np.zeros((num_meas, len(self._meas_esr_line)))
        self._current_esr_meas = []

        self._device_status = 'running'
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
                self._cond_waiting = True
                self.cond.wait(self.threadlock)
                self._cond_waiting = False

        self._meas_esr_res[:, 2:] = self._meas_esr_res[:, 2:] * self._esr_count_frequency

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
            self._esr_count_frequency = clock_frequency

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
                    return False,  self._current_esr_meas.pop(0)*self._esr_count_frequency

            else:
                with self._esr_process_lock:
                    #FIXME: make it a multiple of the expected count time per line
                    timeout = 15 # in seconds
                    self._esr_process_cond.wait(self._esr_process_lock, timeout*1000)

                return False,  self._current_esr_meas.pop(0)*self._esr_count_frequency

        else:
            return True, np.zeros(length)


    def close_odmr(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        self._dev.ctrl.stop()
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
        self._mw_running = False
        self._dev.rfpulse.setGain(0.0)
        self._dev.ctrl.stop()

        return 0


    def get_status(self):
        """
        Gets the current status of the MW source, i.e. the mode (cw, list or sweep) and
        the output state (stopped, running)

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        return self._mw_mode, self._mw_running

    def get_power(self):
        """
        Gets the microwave output power for the currently active mode.

        @return float: the output power in dBm
        """
        pass 

    def get_frequency(self):
        """
        Gets the frequency of the microwave output.
        Returns single float value if the device is in cw mode.
        Returns list like [start, stop, step] if the device is in sweep mode.
        Returns list of frequencies if the device is in list mode.

        @return [float, list]: frequency(s) currently set for this device in Hz
        """
        pass

    def cw_on(self):
        """
        Switches on cw microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """

        self._mw_mode = 'cw'

        #FIXME: power is set arbitrary

        self._dev.configureCW(frequency=self._mw_cw_frequency, countingWindowLength=0.5)
        self._dev.rfpulse.setGain(0.1)

        self._mw_running = True

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

        self._mw_mode = 'cw'

        if power is not None:
            self._mw_cw_power = power

        if frequency is not None:
            self._mw_cw_frequency = frequency

        return self._mw_cw_frequency, self._mw_cw_power,  self._mw_mode


    def list_on(self):
        """
        Switches on the list mode microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """

        self.start_esr(1000)
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

        if frequency is not None:
            self._mw_freq_list = frequency
            self.prepare_cw_esr(self._mw_freq_list, self._esr_count_frequency, self._mw_gain)
        
        #FIXME: use a separate variable for this!
        if power is not None:
            self._mw_cw_power = power


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
        limits.max_power = 30

        limits.list_minstep = 1
        limits.list_maxstep = 1e9
        limits.list_maxentries = 2000

        limits.sweep_minstep = 1
        limits.sweep_maxstep = 1e8
        limits.sweep_maxentries = 2000
        return limits

class MeasThread(QtCore.QThread):

    def __init__(self):
        QtCore.QThread.__init__(self)

    def __del__(self):
        self.wait()

    def run(self):
    # your logic here
        pass
