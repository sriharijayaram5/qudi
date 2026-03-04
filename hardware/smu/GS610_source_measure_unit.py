# -*- coding: utf-8 -*-
"""
Author: Malik Lenger
Code for Yokogawa GS610 source measure unit.

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

from core.module import Base
from core.configoption import ConfigOption
from interface.smu_interface import SMUInterface
from interface.smu_interface import SMULimits
import visa
import time
import math

class GS610sourcemeasureunit(Base, SMUInterface):
    """ Read human readable numbers from serial port.

    Example config for copy-paste:

    smu_GS610:
        module.Class: 'GS610_source_measure_unit.GS610sourcemeasureunit'
        serial_port: 'USB0::0x0B21::0x001E::90Z931989C::INSTR'

    """
    serial_port = ConfigOption('serial_port', 'COM1', missing='warn')
    integration_times = [20e-3, 100e-3, 200e-3]

    def on_activate(self):
        """ Activate module.
        """
        self.rm = visa.ResourceManager()
        try:
            self._connection = self.rm.open_resource(self.serial_port)
        except:
            self.log.error('Connection to the GS610 source measure unit failed. Could not connect to the address >>{}<<.'.format(self.serial_port))
            raise
        
        model = self._query('*IDN?').split(',')[1]
        self.log.info('GS610 source measure unit {} initialised and connected.'.format(model))
        self._command_wait('*CLS')
        self._command_wait('*RST')
        self._command_wait(':SYST:REM')

    def on_deactivate(self):
        """ Deactivate module.
        """
        self._connection.write(':SYST:LOC')
        self.rm.close()
        return
    
    def _command_wait(self, command_str):
        """
        Writes the command in command_str via ressource manager and waits until the device has finished
        processing it.

        @param command_str: The command to be written
        """
        self._connection.write(command_str)
        self._connection.write('*WAI')
        while int(float(self._query('*OPC?'))) != 1:
            time.sleep(0.01)
        return
    
    def _query(self, query_str):
        answer = self._connection.query(query_str)
        return answer.rstrip()
    
    def get_limits(self):
        limits = SMULimits()
        limits.min_voltage = -1*self._query(':SOUR:VOLT:RANG? MAX')
        limits.max_voltage = self._query(':SOUR:VOLT:RANG? MAX')

        limits.min_current = -1*self._query(':SOUR:CURR:RANG? MAX')
        limits.max_current = self._query(':SOUR:CURR:RANG? MAX')

        limits.min_sens_delay = self._query(':SENS:DEL? MIN')
        limits.max_sens_delay = self._query(':SENS:DEL? MAX')
        return limits

    def get_status(self):
        output_status = self.get_output_status()

        src_func = self.get_source_function()
        src_shape = self.get_source_shape()
        src_mode = self.get_source_mode()

        sensing = self.get_sense_state()
        sense_func = self.get_sense_function()
        four_port = self.get_sense_four_port_state()

        return output_status, src_func, src_shape, src_mode, sensing, sense_func, four_port

    def get_output_status(self):
        output_status = self._query(':OUTP:STAT?')
        if output_status == '1' or output_status == 'ZERO':
            return True
        else:
            return False

    def output_on(self):
        state = self.get_output_status()
        if not state:
            self._command_wait(':OUTP:STAT ON')
            return self.get_output_status()
        return state

    def output_off(self):
        state = self.get_output_status()
        if state:
            self._command_wait(':OUTP:STAT OFF')
            return self.get_output_status()
        return state
        
    def get_source_function(self):
        source_func = self._query(':SOUR:FUNC?')
        if source_func == 'VOLT':
            return 0
        elif source_func == 'CURR':
            return 1
        else:
            return -1
    
    def set_source_function(self, function):
        curr_function = self.get_source_function()
        if curr_function == function:
            return curr_function
        elif function == 0:
            self._command_wait(':SOUR:FUNC VOLT')
            return self.get_source_function()
        elif function == 1:
            self._command_wait(':SOUR:FUNC CURR')
            return self.get_source_function()
        else:
            self.log.error('Unknown source function. Allowed functions are 0 (Voltage) and 1 (Current).')
            return self.get_source_function()

    def get_source_shape(self):
        source_shape = self._query(':SOUR:SHAP?')
        if source_shape == 'DC':
            return 0
        elif source_shape == 'PULS':
            return 1
        else:
            return -1
    
    def set_source_shape(self, shape):
        curr_shape = self.get_source_shape()
        if curr_shape == shape:
            return curr_shape
        elif shape == 0:
            self._command_wait(':SOUR:SHAP DC')
            return self.get_source_shape()
        elif shape == 1:
            self._command_wait(':SOUR:MODE PULS')
            return self.get_source_shape()
        else:
            self.log.error('Unknown source mode. Allowed modes are 0 (DC) and 1 (Pulsed).')
            return self.get_source_shape()

    def get_source_mode(self):
        source_mode = self._query(':SOUR:MODE?')
        if source_mode == 'FIX':
            return 0
        elif source_mode == 'SWE':
            return 1
        elif source_mode == 'LIST':
            return 2
        else:
            return -1
    
    def set_source_mode(self, mode):
        curr_mode = self.get_source_mode()
        if curr_mode == mode:
            return curr_mode
        elif mode == 0:
            self._command_wait(':SOUR:MODE FIX')
            return self.get_source_mode()
        elif mode == 1:
            self._command_wait(':SOUR:MODE SWE')
            return self.get_source_mode()
        elif mode == 2:
            self._command_wait(':SOUR:MODE LIST')
            return self.get_source_mode()
        else:
            self.log.error('Unknown source mode. Allowed modes are 0 (FIX), 1 (Sweep) and 2 (List).')
            return self.get_source_mode()

    def get_source_volt_autorange(self):
        return bool(int(float(self._query(':SOUR:VOLT:RANG:AUTO?'))))
    
    def set_source_volt_autorange(self, autorange):
        curr_auto = self.get_source_volt_autorange()
        if curr_auto == autorange:
            return curr_auto
        elif autorange:
            self._command_wait(':SOUR:VOLT:RANG:AUTO ON')
            return self.get_source_volt_autorange()
        else:
            self._command_wait(':SOUR:VOLT:RANG:AUTO OFF')
            return self.get_source_volt_autorange()
        
    def get_source_volt_range(self):
        return self._query(':SOUR:VOLT:RANG?')
    
    def set_source_volt_range(self, range):
        self._command_wait(f':SOUR:VOLT:RANG {range}')
        return self.get_source_volt_range()
    
    def get_source_volt_ramp_speed(self):
        return 1

    def set_source_volt_ramp_speed(self, ramp_speed):
        self.log.warning('This SMU does not support different ramping speeds.')
        return self.get_source_volt_ramp_speed()

    def get_source_curr_autorange(self):
        return bool(int(float(self._query(':SOUR:CURR:RANG:AUTO?'))))
    
    def set_source_curr_autorange(self, autorange):
        curr_auto = self.get_source_curr_autorange()
        if curr_auto == autorange:
            return curr_auto
        elif autorange:
            self._command_wait(':SOUR:CURR:RANG:AUTO ON')
            return self.get_source_curr_autorange()
        else:
            self._command_wait(':SOUR:CURR:RANG:AUTO OFF')
            return self.get_source_curr_autorange()
        
    def get_source_curr_range(self):
        return self._query(':SOUR:CURR:RANG?')
    
    def set_source_curr_range(self, range):
        self._command_wait(f':SOUR:CURR:RANG {range}')
        return self.get_source_curr_range()
    
    def get_source_curr_ramp_speed(self):
        return 1

    def set_source_curr_ramp_speed(self, ramp_speed):
        self.log.warning('This SMU does not support different ramping speeds.')
        return self.get_source_curr_ramp_speed()
    
    def set_voltage_level(self, voltage):
        self._command_wait(f':SOUR:VOLT:LEV {voltage}')
        return self.get_voltage()

    def set_DC_voltage(self, voltage, autorange = False):
        self.set_source_function(0)
        self.set_source_shape(0)
        self.set_source_mode(0)
        autorange = self.set_source_volt_autorange(autorange)
        if not autorange:
            self.set_source_volt_range(abs(voltage))
        return self.set_voltage_level(voltage)

    def get_voltage(self):
        return self._query(':SOUR:VOLT:LEV?')
    
    def set_current_level(self, current):
        self._command_wait(f':SOUR:CURR:LEV {current}')
        return self.get_current()

    def set_DC_current(self, current, autorange = False):
        self.set_source_function(1)
        self.set_source_shape(0)
        self.set_source_mode(0)
        autorange = self.set_source_curr_autorange(autorange)
        if not autorange:
            self.set_source_curr_range(abs(current))
        return self.set_current_level(current)

    def get_current(self):
        return self._query(':SOUR:CURR:LEV?')

    def set_voltage_limit(self, low_lim, up_lim):
        self._command_wait(f':SOUR:VOLT:PROT:LLIM {low_lim}')
        self._command_wait(f':SOUR:VOLT:PROT:ULIM {up_lim}')
        return self.get_voltage_limit()

    def get_voltage_limit(self):
        return self._query(':SOUR:VOLT:PROT:LLIM?'), self._query(':SOUR:VOLT:PROT:ULIM?')

    def set_current_limit(self, low_lim, up_lim):
        self._command_wait(f':SOUR:CURR:PROT:LLIM {low_lim}')
        self._command_wait(f':SOUR:CURR:PROT:ULIM {up_lim}')
        return self.get_current_limit()

    def get_current_limit(self):
        return self._query(':SOUR:CURR:PROT:LLIM?'), self._query(':SOUR:CURR:PROT:ULIM?')

    def get_sense_state(self):
        return bool(int(float(self._query(':SENS:STAT?'))))
    
    def set_sense_state(self, state):
        curr_state = self.get_sense_state()
        if curr_state == state:
            return curr_state
        elif state:
            self._command_wait(':SENS:STAT ON')
            return self.get_sense_state()
        else:
            self._command_wait(':SENS:STAT OFF')
            return self.get_sense_state()
        
    def sensing_on(self):
        return self.set_sense_state(True)

    def sensing_off(self):
        return self.set_sense_state(False)

    def get_sense_function(self):
        sense_func = self._query(':SENS:FUNC?')
        if sense_func == 'VOLT':
            return 0
        elif sense_func == 'CURR':
            return 1
        elif sense_func == 'RES':
            return 2
        else:
            return -1

    def set_sense_function(self, function):
        curr_function = self.get_sense_function()
        if curr_function == function:
            return curr_function
        elif function == 0:
            self._command_wait(':SENS:FUNC VOLT')
            return self.get_sense_function()
        elif function == 1:
            self._command_wait(':SENS:FUNC CURR')
            return self.get_sense_function()
        elif function == 2:
            self._command_wait(':SENS:FUNC RES')
            return self.get_sense_function()
        else:
            self.log.error('Unknown sense function. Allowed functions are 0 (Voltage), 1 (Current) and 2 (Resistance).')
            return self.get_sense_function()

    def get_sense_autorange(self):
        return bool(int(float(self._query(':SENS:RANG:AUTO?'))))
    
    def set_sense_autorange(self, autorange):
        curr_auto = self.get_sense_autorange()
        if curr_auto == autorange:
            return curr_auto
        elif autorange:
            self._command_wait(':SENS:RANG:AUTO ON')
            return self.get_sense_autorange()
        else:
            self._command_wait(':SENS:RANG:AUTO OFF')
            return self.get_sense_autorange()

    def get_sense_int_time(self):
        return self._query(':SENS:ITIM?')
    
    def set_sense_int_time(self, int_time):
        #power freqeuncy 50 Hz: 1ms, 4ms, 20ms, 100ms, 200ms
        #power freqeuncy 60 Hz: 1ms, 4ms, 16.6ms, 100ms, 200ms
        self._command_wait(f':SENS:ITIM {int_time}')
        return self.get_sense_int_time()
    
    def get_sense_delay(self):
        return self._query(':SENS:DEL?')
    
    def set_sense_delay(self, delay_time):
        self._command_wait(f':SENS:DEL {delay_time}')
        return self.get_sense_delay()
    
    def get_sense_autozero(self):
        return bool(int(float(self._query(':SENS:AZER:STAT?'))))
    
    def set_sense_autozero(self, autozero):
        curr_autozero = self.get_sense_autozero()
        if curr_autozero == autozero:
            return curr_autozero
        elif autozero:
            self._command_wait(':SENS:AZER:STAT ON')
            return self.get_sense_autozero()
        else:
            self._command_wait(':SENS:AZER:STAT OFF')
            return self.get_sense_autozero()
        
    def get_sense_average_state(self):
        return bool(int(float(self._query(':SENS:AVER:STAT?'))))
    
    def set_sense_average_state(self, state):
        curr_state = self.get_sense_average_state()
        if curr_state == state:
            return curr_state
        elif state:
            self._command_wait(':SENS:AVER:STAT ON')
            return self.get_sense_average_state()
        else:
            self._command_wait(':SENS:AVER:STAT OFF')
            return self.get_sense_average_state()
        
    def get_sense_average_mode(self):
        average_mode = self._query(':SENS:AVER:MODE?') #1 == block, 0 == moving
        if average_mode == 'MOV':
            return 0
        elif average_mode == 'BLOC':
            return 1
        else:
            return -1
    
    def set_sense_average_mode(self, mode):
        curr_state = self.get_sense_average_mode()
        if curr_state == mode:
            return curr_state
        elif mode == 1:
            self._command_wait(':SENS:AVER:MODE BLOC')
            return self.get_sense_average_mode()
        elif mode == 0:
            self._command_wait(':SENS:AVER:MODE MOV')
            return self.get_sense_average_mode()
        else:
            self.log.error('Unknown sense average mode. Allowed functions are 0 (MOVING) and 1 (BLOCK).')
            return self.get_sense_average_mode()
        
    def get_sense_average_counts(self):
        return self._query(':SENS:AVER:COUNT?')
    
    def set_sense_average_counts(self, counts):
        self._command_wait(f':SENS:AVER:COUNT {int(counts)}')
        return self.get_sense_average_counts()
    
    def get_sense_achange_state(self):
        return bool(int(float(self._query(':SENS:ACH?'))))
    
    def set_sense_achange_state(self, state):
        curr_state = self.get_sense_achange_state()
        if curr_state == state:
            return curr_state
        elif state:
            self._command_wait(':SENS:ACH ON')
            return self.get_sense_achange_state()
        else:
            self._command_wait(':SENS:ACH OFF')
            return self.get_sense_achange_state()

    def get_sense_four_port_state(self):
        return bool(int(float(self._query(':SENS:RSEN?'))))

    def set_sense_four_port_state(self, state = False):
        curr_state =  self.get_sense_four_port_state()
        if curr_state == state:
            return curr_state
        elif state:
            self._command_wait(':SENS:RSEN ON')
            return self.get_sense_four_port_state()
        else:
            self._command_wait(':SENS:RSEN OFF')
            return self.get_sense_four_port_state()
        
    def get_trigger_source(self):
        trig_source = self._query(':TRIG:SOUR?')
        if trig_source == 'TIM':
            return 0
        elif trig_source == 'EXT':
            return 1
        elif trig_source == 'IMM':
            return 2
        else:
            return -1
    
    def set_trigger_source(self, source):
        curr_source = self.get_trigger_source()
        if curr_source == source:
            return curr_source
        elif source == 0:
            self._command_wait(':TRIG:SOUR TIM')
            return self.get_trigger_source()
        elif source == 1:
            self._command_wait(':TRIG:SOUR EXT')
            return self.get_trigger_source()
        elif source == 2:
            self._command_wait(':TRIG:SOUR IMM')
            return self.get_trigger_source()
        else:
            self.log.error('Unknown trigger source. Allowed sources are 0 (Timer), 1 (External) and 2 (Immediate).')
            return self.get_trigger_source()
    
    def setup_sensing(self, sens_fnc, autorange, autozero, delay, achange, four_port, trigger, integration_time):
        setted_sens_fnc = self.set_sense_function(sens_fnc)
        setted_sens_autorange = self.set_sense_autorange(autorange)
        setted_sens_autozero = self.set_sense_autozero(autozero)
        setted_sens_delay = self.set_sense_delay(delay)
        setted_sens_achange = self.set_sense_achange_state(achange)
        setted_sens_four_port = self.set_sense_four_port_state(four_port)
        setted_sens_trigger = self.set_trigger_source(trigger)
        setted_sens_integration_time = self.setup_averaging(integration_time)
        return setted_sens_fnc, setted_sens_autorange, setted_sens_autozero, setted_sens_delay, setted_sens_achange, setted_sens_four_port, setted_sens_trigger, setted_sens_integration_time

    def setup_averaging(self, integration_time):
        for idx, int_time in enumerate(self.integration_times):
            if idx == 0:
                int_time_diff = integration_time % int_time
                actual_int_time = int_time
            else:
                if int_time_diff >= integration_time % int_time:
                    int_time_diff = integration_time % int_time
                    actual_int_time = int_time

        actual_int_time = float(self.set_sense_int_time(actual_int_time))

        if integration_time - actual_int_time == 0:
            self.set_sense_average_state(False)
            actual_counts = 1
        else:
            self.set_sense_average_state(True)
            self.set_sense_average_mode(1) #Block for now
            counts = math.floor(integration_time/actual_int_time)
            actual_counts = int(self.set_sense_average_counts(counts))

        return actual_counts*actual_int_time

    def get_measurement(self, ext_triggered = False):
        if ext_triggered:
            self._command_wait(':INIT')
            self._command_wait('*TRG')
            return self._query(':FETC?')
        else:
            return self._query(':READ?')
        
        
        
        
        