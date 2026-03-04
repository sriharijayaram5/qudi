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
from interface.voltage_source_interface import VolatgeSourceInterface
from interface.voltage_source_interface import VSLimits
import visa
import time
import math

class Keithley6487voltagesource(Base, VolatgeSourceInterface):
    """ Read human readable numbers from serial port.

    Example config for copy-paste:

    smu_Keithley6487:
        module.Class: 'keithley_6487_voltage_scource.Keithley6487voltagesource'
        serial_port: 'USB0::0x0B21::0x001E::90Z931989C::INSTR'

    """
    serial_port = ConfigOption('serial_port', 'COM1', missing='warn')

    def on_activate(self):
        """ Activate module.
        """
        self.rm = visa.ResourceManager()
        try:
            self._connection = self.rm.open_resource(self.serial_port)
        except:
            self.log.error('Connection to the Keithley 6487 voltage source failed. Could not connect to the address >>{}<<.'.format(self.serial_port))
            raise
        
        self._command_wait(':SYST:REM')
        model = self._query('*IDN?').split(',')[1]
        self.log.info('Keithley 6487 voltage source {} initialised and connected.'.format(model))
        self._command_wait('*CLS')
        self._command_wait('*RST')

        self._lower_voltage_limit = -500.0
        self._upper_voltage_limit = 500.0
        

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

    def get_status(self):
        """ Gets the current status of the VS

        @return 
        """
        output_status = self.get_output_status()

        return output_status

    def get_limits(self):
        """ Return the device-specific limits in a nested dictionary.

          @return VSLimits: VS limits object
        """
        limits = VSLimits()
        limits.min_voltage = -500.0
        limits.max_voltage = 500.0

        return limits

    def get_output_status(self):
        output_status = self._query(':SOUR:VOLT:STAT?')
        if output_status == '1':
            return True
        else:
            return False

    def output_on(self):
        state = self.get_output_status()
        if not state:
            self._command_wait(':SOUR:VOLT:STAT ON')
            return self.get_output_status()
        return state

    def output_off(self):
        state = self.get_output_status()
        if state:
            self._command_wait(':SOUR:VOLT:STAT OFF')
            return self.get_output_status()
        return state

    def get_source_function(self): 
        return 0 #0 for voltage
    
    def set_source_function(self, function): 
        return self.get_source_function()

    def get_source_shape(self): 
        return 0 #0 for DC
    
    def set_source_shape(self, shape): 
        return self.get_source_shape()

    def get_source_mode(self):
        return 0 #0 for normal/fixxed. This VS suports also sweep mode, which is not implemented here.
    
    def set_source_mode(self, mode):
        return self.get_source_mode()

    def get_source_volt_autorange(self):
        return False #VS is not supporting autorange for voltage
    
    def set_source_volt_autorange(self, autorange):
        self.log.warning('This VS does not support voltage autoranging.')
        return self.get_source_volt_autorange()
        
    def get_source_volt_range(self): #
        return self._query(':SOUR:VOLT:RANG?')
    
    def set_source_volt_range(self, range):
        self._command_wait(f':SOUR:VOLT:RANG {range}')
        return self.get_source_volt_range()

    def get_source_volt_ramp_speed(self):
        return 1 #Not supported

    def set_source_volt_ramp_speed(self, ramp_speed):
        self.log.warning('This VS does not support different ramping speeds.')
        return self.get_source_volt_ramp_speed()
    
    def set_voltage_level(self, voltage):
        self._command_wait(f':SOUR:VOLT:LEV:AMPL {voltage}')
        return self.get_voltage()

    def set_DC_voltage(self, voltage, autorange = False): 
        self.set_source_function(0)
        self.set_source_shape(0)
        self.set_source_mode(0)
        autorange =self.set_source_volt_autorange(autorange)
        if not autorange:
            self.set_source_volt_range(abs(voltage))
        return self.set_voltage_level(voltage)

    def get_voltage(self):
        return self._query(':SOUR:VOLT:LEV:AMPL?')

    def set_voltage_limit(self, low_lim, up_lim): 
        self._lower_voltage_limit = low_lim
        self._upper_voltage_limit = up_lim
        return self.get_voltage_limit()

    def get_voltage_limit(self): 
        return self._lower_voltage_limit, self._upper_voltage_limit
    
    #This VS also supports current limiting, but this is not implemented here.