# -*- coding: utf-8 -*-
"""
Author: Malik Lenger
Code for Attodry 2200 cryostat controller.

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
from atto_device import attoDry2100
from interface.cryo_controller_interface import CryoControllerInterface

class CryoControllerAttoDry2200(Base, CryoControllerInterface):
    """ Read human readable numbers from serial port.

    Example config for copy-paste:

    attodry2200:
        module.Class: 'cryo_controller.cryo_controller_Attodry2200.CryoControllerAttoDry2200'
        address: '192.168.1.1'

    """

    _address = ConfigOption('address', missing='error')

    def on_activate(self):
        """ Activate module.
        """
        try:
            self._connection = attoDry2100.Device(self._address)
            self._connection.connect()
        except:
            self.log.error('Could not connect to the address >>{}<<.'.format(self._address))
            raise
        self.log.info('AttoDry2200 controller initialised and connected.')
        
        
    def on_deactivate(self):
        """ Deactivate module.
        """
        self._connection.close()

    #Methods for sample temperature/heater subsystem
    def get_sample_temp_setpoint(self):
        return self._connection.sample.getSetPoint()
    
    def get_sample_temp(self):
        try:
            temp = self._connection.sample.getTemperature()
        except:
            self.log.warning('Sample temperature sensor is not connected.')
            temp = -1
        return temp
    
    def get_sample_temp_control_status(self):
        return self._connection.sample.getTempControlStatus()
    
    def get_sample_heater_power(self):
        return self._connection.sample.getHeaterPower()
    
    #Methods for vti temperature/heater subsystem
    def get_vti_temp_setpoint(self):
        return self._connection.vti.getSetPoint()
    
    def get_vti_temp(self):
        try:
            temp = self._connection.vti.getTemperature()
        except:
            self.log.warning('VTI temperature sensor is not connected.')
            temp = -1
        return temp
    
    def get_vti_temp_control_status(self):
        return self._connection.vti.getTempControlStatus()
    
    def get_vti_heater_power(self):
        return self._connection.vti.getHeaterPower()
    
    #Methods for condenser/reservior subsystem
    def get_reservoir_temp_setpoint(self):
        return self._connection.condenser.getSetPoint()
    
    def get_reservoir_temp(self):
        try:
            temp = self._connection.condenser.getTemperature()
        except:
            self.log.warning('Reservior temperature sensor is not connected.')
            temp = -1
        return temp
    
    def get_reservoir_temp_control_status(self):
        return self._connection.condenser.getTempControlStatus()
    
    def get_reservoir_heater_power(self):
        return self._connection.condenser.getHeaterPower()
    
    #Methods for magnet subsystem
    def get_magnet_temp(self):
        try:
            temp = self._connection.magnet.getTemperature()
        except:
            self.log.warning('Magnet temperature sensor is not connected.')
            temp = -1
        return temp
    
    #Methods for pressure sensors subsystem
    def get_cryo_in_pressure(self):
        try:
            temp = self._connection.pressures.getCryoInPressure()
        except:
            self.log.warning('Cryo In pressure sensor is not connected.')
            temp = -1
        return temp
    
    def get_cryo_out_pressure(self):
        try:
            temp = self._connection.pressures.getCryoOutPressure()
        except:
            self.log.warning('Cryo Out pressure sensor is not connected.')
            temp = -1
        return temp
    
    def get_dump_pressure(self):
        try:
            temp = self._connection.pressures.getDumpPressure()
        except:
            self.log.warning('Dump pressure sensor is not connected.')
            temp = -1
        return temp
        
        
        
        
        