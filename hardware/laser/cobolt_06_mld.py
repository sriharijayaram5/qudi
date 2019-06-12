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


class CoboltLaserMLD(Base, SimpleLaserInterface):
    """ Control class for a cobolt 06-01 MLD laser.

    Example config for copy-paste:

    cobolt:
        module.Class: 'laser.cobolt_06_mld.CoboltLaserMLD'

    """
    _dev = None

    _modclass = 'simple'
    _modtype = 'hardware'

    def on_activate(self):
        self._dev = CoboltLaserStandalone()

        self.shutter = ShutterState.CLOSED
        self.power_setpoint = 0
        self.current_setpoint = 0

        self.mode = ControlMode.POWER
        self.lstate = LaserState.OFF

        self.current_setpoint = 0
        self.power_setpoint = 0


    def on_deactivate(self):
        pass

    def get_power_range(self):
        """ Return laser power
        @return tuple(p1, p2): Laser power range in watts
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
        @return str: unit
        """
        return '%'

    def get_current(self):
        """ Return laser current
        @return float: actual laser current as ampere or percentage of maximum current
        """
        return self._dev.get_current()

    def get_current_range(self):
        """ Return laser current range
        @return tuple(c1, c2): Laser current range in current units
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
        self.mode = control_mode
        return self.mode

    def on(self):
        """ Turn on laser. Does not open shutter if one is present.
          @return enum LaserState: actual laser state
        """
        time.sleep(1)
        self.lstate = LaserState.ON
        return self.lstate

    def off(self):
        """ Turn ooff laser. Does not close shutter if one is present.
          @return enum LaserState: actual laser state
        """
        time.sleep(1)
        self.lstate = LaserState.OFF
        return self.lstate

    def get_laser_state(self):
        """ Get laser state.
          @return enum LaserState: laser state
        """
        self._dev.get_state().strip()
        return self._dev.get_state().strip()


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
    
    def test_method(self):
        return "test"

    def __init__(self):
        self.rm = visa.ResourceManager()
        self.connect_laser()
        
    def connect_laser(self):
        self._device = self.rm.open_resource('ASRL3::INSTR')
        self.set_autostart(False)
        
    def disconnect_laser(self):
        self._device.close()
        
    def query(self, question):
        return self._device.query(question)
    
    def write(self, message):
        self._device.write(message)
        self._device.clear()
        
    def get_state(self):
        return self.query("l?")
    
    def set_state(self, state):
        self.write("l{0}".format(state))
        
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
        
    def get_operatingmode(self):
        return self.query("gom?")



