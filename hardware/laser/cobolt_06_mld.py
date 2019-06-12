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

import logging

import numpy as np
import visa
import serial
import time
import math
import random

from core.module import Base
from interface.simple_laser_interface import ControlMode
from interface.simple_laser_interface import ShutterState
from interface.simple_laser_interface import LaserState
from interface.simple_laser_interface import SimpleLaserInterface


logger = logging.getLogger(__name__)



class CoboltLaserMLD(Base, SimpleLaserInterface):
    """ Control class for a cobolt 06-01 MLD laser.

    Example config for copy-paste:

    cobolt:
        module.Class: 'laser.cobolt_06_mld.CoboltLaserMLD'
        com_port: 'COM3'  # or something like 'ASRL3::INSTR'

    """

    _dev = None

    _modclass = 'CoboltLaserMLD'
    _modtype = 'hardware'

    _com_port = ConfigOption('com_port', missing='error')


    def on_activate(self):
        self._dev = CoboltLaserStandalone()

        self.shutter = ShutterState.CLOSED
        self.power_setpoint = 0
        self.current_setpoint = 0

        self.mode = ControlMode.POWER # This is the default mode
        self.get_laser_state()  # get current laser state

        self.current_setpoint = 0
        self.power_setpoint = 0

    def on_deactivate(self):
        self._dev.disconnect_laser()


    def get_power_range(self):
        """ Return laser power

        @return tuple(p1, p2): Laser power range (min, max) in watts
        """
        return (0, 0.080)

    def get_power(self):
        """ Return laser power

        @return float: Actual laser power in watts
        """
        return self._dev.get_power()

    def set_power(self, power):
        """ Set laer power ins watts

        @param float power: laser power setpoint in watts

        @return float: laser power setpoint in watts
        """
        self.power_setpoint = power
        self.power_setpoint = self._dev.set_power(power)
        return self.power_setpoint

    def get_power_setpoint(self):
        """ Return laser power setpoint

        @return float: Laser power setpoint in watts
        """
        return self.power_setpoint 

    def get_current_unit(self):
        """ Return laser current unit

        @return str: unit, currently only percent
        """
        return '%'

    def get_current(self):
        """ Return laser current

        @return float: actual laser current as ampere or percentage of maximum current
        """
        return self._dev.get_current()

    def get_current_range(self):
        """ Return laser current range

        @return tuple(c1, c2): Laser current range (min, max) in current units
        """
        return (0, 100)

    def get_current_setpoint(self):
        """ Return laser current

        @return float: Laser current setpoint in amperes
        """
        return self.current_setpoint

    def set_current(self, current):
        """ Set laser current

        @param float current: Laser current setpoint in amperes

        @return float: Laser current setpoint in amperes
        """
        self.current_setpoint = current
        return self._dev.set_current(current)

    def allowed_control_modes(self):
        """ Get available control mode of laser

        @return list: list with enum control modes
        """
        return [ControlMode.POWER, ControlMode.CURRENT]

    def get_control_mode(self):
        """ Get control mode of laser

        @return enum ControlMode: control mode
        """
        return self.mode

    def set_control_mode(self, control_mode):
        """ Set laser control mode.
        
        @param enum control_mode: desired control mode
        
        @return enum ControlMode: actual control mode
        """

        if isinstance(control_mode, ControlMode):

            if control_mode in self.allowed_control_modes():
                self.mode = control_mode
            else:
                self.log.error(f'Cannot set to desired control mode'
                               f'"{control_mode}". It is not an allowed mode!')

        else:
            self.log.error(f'Cannot set to desired control mode '
                           f'"{control_mode}". It is not a valid parameter. '
                           f'Current mode "{self.mode}" will remain.')
        return self.mode

    def on(self):
        """ Turn on laser. Does not open shutter if one is present.
        
        @return enum LaserState: actual laser state
        """
        
        self._dev.get_laser_output(bool(LaserState.ON.value))   
        return self.get_state()

    def off(self):
        """ Turn off laser. Does not close shutter if one is present.
        
        @return enum LaserState: actual laser state
        """

        #FIXME: Is this waiting time really required???
        self._dev.get_laser_output(bool(LaserState.OFF.value))
        return self.get_state()

    def get_laser_state(self):
        """ Get laser state.
        
        @return enum LaserState: laser state
        """



        if self._dev.get_laser_state():
            self.lstate = LaserState.ON
        else:
            self.lstate = LaserState.OFF

        return self.lstate


    def set_laser_state(self, state):
        """ Set laser state.
        
        @param enum state: desired laser state
        
        @return enum LaserState: actual laser state
        """

        time.sleep(1)
        self.lstate = state
        return self._dev.set_state(state)

    def get_shutter_state(self):
        """ Get shutter state. Has a state for no shutter present.
        
        @return enum ShutterState: actual shutter state
        """
        return self.shutter

    def set_shutter_state(self, state):
        """ Set shutter state.
        
        @param enum state: desired shutter state
        
        @return enum ShutterState: actual shutter state
        """

        time.sleep(1)
        self.shutter = state
        return self.shutter

    def get_temperatures(self):
        """ Get all available temperatures from laser.
        
        @return dict: dict of name, value for temperatures
        """
        return {
            'psu': 0 ,
            'head': 0
            }

    def get_temperature_setpoints(self):
        """ Get all available temperature setpoints from laser.
        
        @return dict: dict of name, value for temperature setpoints
        """
        return {'psu': 0, 'head': 0}

    def set_temperatures(self, temps):
        """ Set laser temperatures.
        
        @param temps: dict of name, value to be set
        
        @return dict: dict of name, value of temperatures that were set
        """
        
        return {}


    def get_extra_info(self):
        """ Show dianostic information about lasers.
          @return str: diagnostic info as a string
        """

        return "Dummy laser v0.9.9\nnot used very much\nvery cheap price very good quality"

class CoboltLaserStandalone():

    MODEL = '06-MLD 515nm'
    BRAND = 'Cobolt'
    SERIAL_NUM = 0

    # Laser safety:
    OD_NUM = '3 OD' # optical density number
    LASER_CLASS = 'III B'
    extra_info = {}

    log = logger
    
    def test_method(self):
        return "test"

    def __init__(self, comport):
        """ Initialize the laser connection.

        @param str comport: the name of the comport, e.g. 'ASRL3::INSTR' or 'COM3'
        """

        self.rm = visa.ResourceManager()
        self.connect_laser(comport)
        
    def connect_laser(self, comport):
        """ Connect method for the laser.

        @param str comport: comport name, e.g. 'ASRL3::INSTR' or 'COM3'
        """
        self._device = self.rm.open_resource(comport)

        self.SERIAL_NUM = self.get_serialnumber()

        self.extra_info = {'brand': self._dev.BRAND, 'model': self._dev.MODEL, 
                           'serial_number': self._dev.SERIAL_NUM, 
                           'required OD goggles': self._dev.OD_NUM,
                           'laser_class': self._dev.LASER_CLASS}

        self.log.info(f'Initialized Laser from {self.BRAND} of model '
                      f'{self.MODEL} with S/N: {self.SERIAL_NUM}.\n'
                      f'Current operation hours: {self.get_operatinghours()}h.')

        self.log.warning(f'Be aware! It is a Class {self.LASER_CLASS} laser, '
                         f'so wear Laser protection with Optical Density '
                         f'number {self.OD_NUM}!')

        self.set_autostart(False)
        
    def disconnect_laser(self):
        """ Disconnect the laser."""
        self._device.close()
        
    def query(self, question):
        """ General method for query questions from laser. 
        
        @param str question: refer to the manual of the laser for further info.
        
        @return str: the raw response of the laser.
        """
        return self._device.query(question)
    
    def write(self, message):
        """General method to write messages to laser. 

        @param str message: message to the laser.
        """
        self._device.write(message)
        self._device.clear()
        
    def get_laser_output(self):
        """ Ask whether laser output is on. 

        @return bool: True=laser is on, False=laser is off."""
        return bool(int(self.query("l?").strip()))
    
    def set_laser_output(self, state):
        """ Switch the output of the laser on or off.

        @param bool state: False=OFF, True=ON
        """
        self.write("l{0}".format(int(state)))
        return self.get_laser_output()
        

    def get_operatingmode(self):
        """ Obtain the current operation mode set to the device. 

        @return int: with the following meaning:
                        0 = OFF
                        1 = Waiting for key
                        2 = Continous
                        3 = ON/OFF Modulation
                        4 = Modulation
                        5 = Fault
                        6 = Aborted
        """
        return int(self.query("gom?").strip())

    def restart_laser(self):
        self.write("@cob1")
        
    def get_operatinghours(self):
        return float(self.query("hrs?"))
    
    def get_power(self):
        return float(self.query("p?").strip())

    def get_outputpower(self):
        return float (self.query("pa?"))
    
    def set_power(self, power):
        self.write("p {0}".format(power))
        return self.get_power()
    
    def get_current(self):
        return float(self.query("i?"))
    
    def set_current(self,current):
        self.write("slc {0}".format(current))
        return self.get_current()
    
    def set_constant_power(self):
        self.write("cp")
        
    def set_constant_current(self):
        self.write("ci")
    
    def get_interlock(self):
        return bool(int(self.query("ilk?").strip()))

    def get_autostart(self):
        return bool(int(self._device.query("@cobas?").strip()))
    
    def set_autostart(self, state):
        self.write(f"@cobas {int(state)}")

    def get_serialnumber(self):
        return int(self.query("gsn?").strip())


