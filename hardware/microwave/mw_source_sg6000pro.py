# -*- coding: utf-8 -*-

"""
This file contains the Qudi Hardware module for DS Instruments SG6000PRO

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

import visa
import numpy as np
import time

from core.module import Base, ConfigOption
from interface.microwave_interface import MicrowaveInterface
from interface.microwave_interface import MicrowaveLimits
from interface.microwave_interface import MicrowaveMode
from interface.microwave_interface import TriggerEdge


class MicrowaveSG6000PRO(Base, MicrowaveInterface):
    """ The hardware control for the device from DS Instrumentation of type SG6000PRO.

    The command structure has been tested for type SG6000Pro

    Example config for copy-paste:

    mw_source_sg6000pro:
        module.Class: 'microwave.mw_source_sg6000pro.MicrowaveSG6000PRO'
        visa_address: 'ASRL4::INSTR'
        visa_timeout: 10

    """

    _modclass = 'MicrowaveSG6000PRO'
    _modtype = 'hardware'

    _visa_address = ConfigOption('visa_address', missing='error')
    _visa_timeout = ConfigOption('visa_timeout', 10, missing='warn')

    # Indicate how fast frequencies within a list or sweep mode can be changed:
    _FREQ_SWITCH_SPEED = 0.001  # Frequency switching speed in s (acc. to specs)

    def on_activate(self):
        """ Initialisation performed during activation of the module. """


        self._LIST_DWELL = 10e-3    # Dwell time for list mode to set how long
                                    # the device should stay at one list entry.
                                    # here dwell time can be between 1ms and 1s
        self._SWEEP_DWELL = 10e-3   # Dwell time for sweep mode to set how long
                                    # the device should stay at one list entry.
                                    # here dwell time can be between 10ms and 5s

        # trying to load the visa connection to the module
        self.rm = visa.ResourceManager()
        try:
            # such a stupid stuff, the timeout is specified here in ms not in
            # seconds any more, take that into account.
            self._visa_connection = self.rm.open_resource(
                                        self._visa_address,
                                        timeout=self._visa_timeout*1000)

            self._visa_connection.write_termination = "\n"
            #self._visa_connection.read_termination = None
            self._visa_connection.baud_rate = 115200
            self._visa_connection.parity = visa.constants.Parity.none
            self._visa_connection.stop_bits = visa.constants.StopBits.one

            self.log.info('SG6000PRO: initialised and connected to hardware.')
        except:
             self.log.error('SG6000PRO: could not connect to the VISA '
                            'address "{0}".'.format(self._visa_address))

        #DOTO: setup the device correctly and set all the status variable correctly

        self._FREQ_MAX = 6.8e9 # in Hz
        self._FREQ_MIN = 60e6 # in Hz
        self._POWER_MAX = 10 # in dBm
        self._POWER_MIN = -50 # in dBm

        # although it is the step mode, this number should be the same for the
        # list mode:
        self._LIST_FREQ_STEP_MIN = 1e3 # in Hz
        self._LIST_FREQ_STEP_MAX = 3e9 # in Hz

        self._SWEEP_FREQ_STEP_MIN = self._LIST_FREQ_STEP_MIN
        self._SWEEP_FREQ_STEP_MAX = self._LIST_FREQ_STEP_MAX

        self._MAX_LIST_ENTRIES = 2000
        # FIXME: Not quite sure about this:
        self._MAX_SWEEP_ENTRIES = 10000

        # need to track the mode of the device, as it cannot be asked.
        self._mode = 'cw' # needs to be from the list: ['cw', 'list', 'sweep']
        self.off()

        self._freq_sweep_start = None
        self._freq_sweep_stop = None
        self._freq_sweep_step = None
        self._freq_list = []


        # get the info from the device:
        message = self._ask('*IDN?').strip().split(',')
        self._BRAND = message[0]
        self._MODEL = message[1]
        self._SERIALNUMBER = message[2]
        self._FIRMWARE_VERSION = message[3]

        self.log.info(f'Load the device model "{self._MODEL}" from '
                      f'"{self._BRAND}" with the serial number '
                      f'"{self._SERIALNUMBER}" and the firmware version '
                      f'"{self._FIRMWARE_VERSION}" successfully.')

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module. """

        self.off()  # turn the device off in case it is running
        # self._visa_connection.close()   # close the gpib connection
        # self.rm.close()                 # close the resource manager
        return

    def get_limits(self):
        """ Retrieve the limits of the device.

        @return: object MicrowaveLimits: Serves as a container for the limits
                                         of the microwave device.
        """
        limits = MicrowaveLimits()
        limits.supported_modes = (MicrowaveMode.CW, MicrowaveMode.LIST)
        # the sweep mode seems not to work properly, comment it out:
                                  #MicrowaveMode.SWEEP)

        limits.min_frequency = self._FREQ_MIN
        limits.max_frequency = self._FREQ_MAX
        limits.min_power = self._POWER_MIN
        limits.max_power = self._POWER_MAX

        limits.list_minstep = self._LIST_FREQ_STEP_MIN
        limits.list_maxstep = self._LIST_FREQ_STEP_MAX
        limits.list_maxentries = self._MAX_LIST_ENTRIES

        limits.sweep_minstep = self._SWEEP_FREQ_STEP_MIN
        limits.sweep_maxstep = self._SWEEP_FREQ_STEP_MAX
        limits.sweep_maxentries = self._MAX_SWEEP_ENTRIES
        return limits

    def off(self):
        """ Switches off any microwave output.
        Must return AFTER the device is actually stopped.

        @return int: error code (0:OK, -1:error)
        """
        mode, is_running = self.get_status()
        if not is_running:
            return 0

        self._write('OUTP:STAT OFF')
        return 0

    def get_status(self):
        """ Get the current status of the MW source, i.e. the mode
        (cw, list or sweep) and the output state (stopped, running).

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        state = self._ask('OUTP:STAT?').strip()

        if state == 'ON':
            is_running = True
        else:
            is_running = False

        return self._mode, is_running

    def get_power(self):
        """ Gets the microwave output power.

        @return float: the power set at the device in dBm
        """

        return float(self._ask('POWER?').strip().strip('dBm'))

    def get_frequency(self):
        """  Gets the frequency of the microwave output.

        @return float|list: frequency(s) currently set for this device in Hz

        Returns single float value if the device is in cw mode.
        Returns list like [start, stop, step] if the device is in sweep mode.
        Returns list of frequencies if the device is in list mode.
        """

        # THIS AMBIGUITY IN THE RETURN VALUE TYPE IS NOT GOOD AT ALL!!!
        # FIXME: Correct that as soon as possible in the interface!!!

        mode, is_running = self.get_status()

        # need to ask twice here
        self._ask('FREQ:CW?')

        if 'cw' in mode:
            return_val = float(self._ask('FREQ:CW?').strip().strip('HZ'))
        elif 'sweep' in mode:
            start = self._freq_sweep_start
            stop = self._freq_sweep_stop
            step = self._freq_sweep_step
            return_val = [start+step, stop, step]
        elif 'list' in mode:
            return_val = self._freq_list
        else:
            self.log.error('Mode Unknown! Cannot determine Frequency!')
        return return_val

    def cw_on(self):
        """ Switches on cw microwave output.

        @return int: error code (0:OK, -1:error)

        Must return AFTER the device is actually running.
        """
        current_mode, is_running = self.get_status()

        if is_running:
            if current_mode == 'cw':
                return 0
            else:
                self.off()
                self._mode = 'cw'
        else:
            self._mode = 'cw'   # demand just that the mode has to be cw

        self._write('SWE:MODE LIST')

        return self._on()

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
        mode, is_running = self.get_status()
        if is_running:
            self.off()

        # Activate CW mode
        if mode != 'cw':
            self._mode = 'cw'

        # Set CW frequency
        if frequency is not None:
            self._set_frequency(frequency)

        # Set CW power
        if power is not None:
            self._write('POWER {0:.3f}'.format(power))

        # Return actually set values
        mode, _ = self.get_status()
        actual_freq = self.get_frequency()
        actual_power = self.get_power()

        return actual_freq, actual_power, mode

    def list_on(self):
        """
        Switches on the list mode microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """

        current_mode, is_running = self.get_status()
        if is_running:
            if current_mode == 'list':
                return 0
            else:
                self.off()
                self._mode = 'list'
        else:
            self._mode = 'list'


        self._write('SWE:MODE LIST')

        return self._on()

    def set_list(self, frequency=None, power=None):
        """
        Configures the device for list-mode and optionally sets frequencies and/or power

        @param list frequency: list of frequencies in Hz
        @param float power: MW power of the frequency list in dBm

        @return tuple(list, float, str):
            current frequencies in Hz,
            current power in dBm,
            current mode
        """

        mode, is_running = self.get_status()
        if is_running:
            self.off()

        # Bug in the micro controller of SMR20:
        # check the amount of entries, since the timeout is not working properly
        # and the SMR20 overwrites for too big entries the device-internal
        # memory such that the current firmware becomes corrupt. That is an
        # extreme annoying bug. Therefore catch too long lists.

        if len(frequency) > self._MAX_LIST_ENTRIES:
            self.log.error('The frequency list exceeds the hardware limitation '
                           'of {0} list entries. Aborting creation of a list.'
                           ''.format(self._MAX_LIST_ENTRIES))

        else:

            self._write('SWE:MODE LIST')

            # It seems that we have to set a DWEL for the device, but it is not so
            # clear why it is necessary. At least there was a hint in the manual for
            # that and the instrument displays an error, when this parameter is not
            # set in the list mode (even it should be set by default):
            self._write('SWE:DWELL {0}'.format(int(self._LIST_DWELL*1000))) # in ms


            self._write('LIST:CLEAR')

            for f in frequency:
                self._write('LIST:ADD {0:d}'.format(int(f)))

            self._freq_list = frequency

        self._write('TRIG:STEP')
        self.reset_listpos()

        # THIS AMBIGUITY IN THE RETURN VALUE TYPE IS NOT GOOD AT ALL!!!
        # FIXME: Ahh this is so shitty with the return value!!!
        actual_power = self.get_power()
        mode, _ = self.get_status()

        return frequency, actual_power, mode

    def reset_listpos(self):
        """ Reset of MW List Mode position to start from first given frequency

        @return int: error code (0:OK, -1:error)
        """

        self._visa_connection.write('ABORT')    # do not use _write command to reduce the amount of calls

        return 0

    def sweep_on(self):
        """ Switches on the sweep mode.

        @return int: error code (0:OK, -1:error)
        """
        mode, is_running = self.get_status()
        if is_running:
            if mode == 'sweep':
                return 0
            else:
                self.off()

        if mode != 'sweep':
            self._write('SOUR:FREQ:MODE SWE')

        self._write(':OUTP:STAT ON')
        dummy, is_running = self.get_status()
        while not is_running:
            time.sleep(0.2)
            dummy, is_running = self.get_status()
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
        mode, is_running = self.get_status()

        if is_running:
            self.off()

        if mode != 'sweep':

            self._mode = 'sweep'

        self._write('SWE:MODE SCAN')  # set the sweep mode.
        self._write('SWE:DWELL {0:d}'.format(int(self._SWEEP_DWELL * 1000)))  # set the dwell time

        if (start is not None) and (stop is not None) and (step is not None):
            self._write('FREQ:START {0:d}HZ'.format(int(start)))
            self._write('FREQ:STOP {0:d}HZ'.format(int(stop)))

            sweep_points = int((stop - start)/step) + 1
            self._write('SWE:POINTS {0:d}'.format(sweep_points))

            self.log.info(f'sweeppoints: {sweep_points}')

            self._freq_sweep_start = start
            self._freq_sweep_stop = stop
            self._freq_sweep_step = step

        if power is not None:
            self._set_power(power)

        self._write('TRIG:STEP')
        self.reset_sweeppos()

        actual_power = self.get_power()
        freq_list = self.get_frequency()
        mode, dummy = self.get_status()

        self.reset_sweeppos()

        return freq_list[0], freq_list[1], freq_list[2], actual_power, mode

    def reset_sweeppos(self):
        """
        Reset of MW sweep mode position to start (start frequency)

        @return int: error code (0:OK, -1:error)
        """
        self._visa_connection.write('ABORT')
        return 0

    def set_ext_trigger(self, pol, timing):
        """ Set the external trigger for this device with proper polarization.

        @param float timing: estimated time between triggers
        @param TriggerEdge pol: polarisation of the trigger (basically rising edge or falling edge)

        @return object, float: current trigger polarity [TriggerEdge.RISING, TriggerEdge.FALLING],
            trigger timing
        """
        if pol == TriggerEdge.RISING:
            edge = 'POS'
        elif pol == TriggerEdge.FALLING:
            edge = 'NEG'
        else:
            self.log.warning('No valid trigger polarity passed to microwave hardware module.')
            edge = None

        self._write(':TRIG1:LIST:SOUR EXT')
        self._write(':TRIG1:SLOP NEG')

        if edge is not None:
            self._write(':TRIG1:SLOP {0}'.format(edge))

        polarity = self._ask(':TRIG1:SLOP?')
        if 'NEG' in polarity:
            return TriggerEdge.FALLING, timing
        else:
            return TriggerEdge.RISING, timing

    # ================== Non interface commands: ==================

    def _on(self):
        """ Switches on any microwave output.
        Must return AFTER the device is actually turned on.

        @return int: error code (0:OK, -1:error)
        """
        mode, is_running = self.get_status()
        if is_running:
            return 0

        self._write('OUTP:STAT ON')

        # break after 10 tries
        tries = 0
        while not is_running or (tries > 10):
            time.sleep(0.2)
            dummy, is_running = self.get_status()
            tries += 1

        if tries > 10:
            self.log.error("Could not switch on the device, something went "
                           "wrong...giving up.")
            return -1
        return 0


    def _set_power(self, power):
        """ Sets the microwave output power.

        @param float power: the power (in dBm) set for this device

        @return float: actual power set (in dBm)
        """


        self._write('POWER {0:f};'.format(power))
        actual_power = self.get_power()
        return actual_power

    def _set_frequency(self, freq):
        """ Sets the frequency of the microwave output.

        @param float freq: the frequency (in Hz) set for this device

        @return int: error code (0:OK, -1:error)
        """

        # every time a single frequency is set, the CW mode is activated!
        self._write('FREQ:CW {0:d}'.format(int(freq)))
        # {:e} means a representation in float with exponential style
        return 0

    def trigger(self):
        """ Trigger the next element in the list or sweep mode programmatically.

        @return int: error code (0:OK, -1:error)

        Ensure that the Frequency was set AFTER the function returns, or give
        the function at least a save waiting time.
        """

        self._visa_connection.write('INIT:IMM')
        time.sleep(self._FREQ_SWITCH_SPEED)  # that is the switching speed
        return 0

    def reset_device(self):
        """ Resets the device and sets the default values."""
        self._write('*RST')
        self._write('OUTP:STAT OFF')
        return 0

    def _ask(self, question):
        """ Ask wrapper.

        @param str question: a question to the device

        @return: the received answer
        """
        self._visa_connection.query(question)
        return self._visa_connection.query(question)

    def _write(self, command, wait=True):
        """ Write wrapper.

        @param str command: a command to the device
        @param bool wait: optional, is the wait statement should be skipped.

        @return: str: the statuscode of the write command.
        """

        statuscode = self._visa_connection.write(command)

        # reuse the wait argument for check, whether last write statement
        # produces any errors.
        if wait:
            mess = self._ask('SYST:ERR?').strip()
            if not mess == '0,No error':
                self.log.error(f'The current command "{command}" is invalid! '
                               f'The return error message is: {mess}')
            # self._visa_connection.write('*WAI') # no wait visa implementation

        return statuscode
