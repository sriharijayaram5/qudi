# -*- coding: utf-8 -*-
"""
Interface file for lasers where current and power can be set.

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

from enum import Enum
from core.module import Base
from core.configoption import ConfigOption
from interface.simple_laser_interface import SimpleLaserInterface
from interface.simple_laser_interface import ControlMode
from interface.simple_laser_interface import ShutterState
from interface.simple_laser_interface import LaserState
import serial
import time
import numpy as np


class LaserQuantumLaser(Base, SimpleLaserInterface):
    """ This interface can be used to control an Opus 532 laser via RS232. It handles power control, temperature readout and simple on/off only.

    This interface is useful for a standard, fixed wavelength laser that you can find in a lab.
    It handles power control via constant power or constant current mode, a shutter state if the hardware has a shutter
    and a temperature regulation control.

    """
    com_port = ConfigOption('COM', 'COM4', missing='error')
    maxpower = ConfigOption('maxpower', 1.000, missing='warn')

    def on_activate(self):
        self.ser = serial.Serial(
        port=self.com_port,
        baudrate=19200
        )
    
    def on_deactivate(self):
        self.ser.close()
    
    def talk(self, text):
        self.ser.write((text+'\r').encode('ascii'))
        out = ''
        # let's wait one second before reading output (let's give device time to answer)
        time.sleep(0.5)
        while self.ser.inWaiting() > 0:
        	out += self.ser.read(1).decode('ascii')

        if out != '':
        	return out
        else:
            return np.nan

    def get_power_range(self):
        """ Return laser power
        @return tuple(p1, p2): Laser power range in watts
        """
        return (0.020, self.maxpower)

    
    def get_power(self):
        """ Return laser power
        @return float: Actual laser power in watts
        """
        return float(self.talk('POWER?')[:-4])*1e-3

    
    def set_power(self, power):
        """ Set laer power ins watts
          @param float power: laser power setpoint in watts

          @return float: laser power setpoint in watts
        """
        if power>self.maxpower:
            self.log.warning('Power setpoint greater than max permissible power. Setting to minimum.')
            power = 0.020
        self.talk(f'POWER={power*1e3}')
        return power

    
    def get_power_setpoint(self):
        """ Return laser power setpoint
        @return float: Laser power setpoint in watts
        """
        return float(self.talk('POWER?')[:-4])*1e-3

    
    def get_current_unit(self):
        """ Return laser current unit
        @return str: unit
        """
        return ''

    
    def get_current(self):
        """ Return laser current
        @return float: actual laser current as ampere or percentage of maximum current
        """
        return 0.0

    
    def get_current_range(self):
        """ Return laser current range
        @return tuple(c1, c2): Laser current range in current units
        """
        return (0,100)

    
    def get_current_setpoint(self):
        """ Return laser current
        @return float: Laser current setpoint in amperes
        """
        return 0.0

    
    def set_current(self, current):
        """ Set laser current
        @param float current: Laser current setpoint in amperes
        @return float: Laser current setpoint in amperes
        """
        return 0.0

    
    def allowed_control_modes(self):
        """ Get available control mode of laser
          @return list: list with enum control modes
        """
        return [ControlMode.POWER]

    
    def get_control_mode(self):
        """ Get control mode of laser
          @return enum ControlMode: control mode
        """
        return ControlMode

    
    def set_control_mode(self, control_mode):
        """ Set laser control mode.
          @param enum control_mode: desired control mode
          @return enum ControlMode: actual control mode
        """
        return self.talk('CONTROL=POWER')

    
    def on(self):
        """ Turn on laser. Does not open shutter if one is present.
          @return enum LaserState: actual laser state
        """
        self.talk('ON')
        return LaserState.ON
    
    def off(self):
        """ Turn ooff laser. Does not close shutter if one is present.
          @return enum LaserState: actual laser state
        """
        self.talk('OFF')
        return LaserState.OFF

    
    def get_laser_state(self):
        """ Get laser state.
          @return enum LaserState: laser state
        """
        if self.talk('STATUS?') == 'ENABLED\r\n':
            return LaserState.ON
        else:
            return LaserState.OFF
    
    def set_laser_state(self, state):
        """ Set laser state.
          @param enum state: desired laser state
          @return enum LaserState: actual laser state
        """
        return LaserQuantumLaser.UNKNOWN

    
    def get_shutter_state(self):
        """ Get shutter state. Has a state for no shutter present.
          @return enum ShutterState: actual shutter state
        """
        return ShutterState.OPEN

    
    def set_shutter_state(self, state):
        """ Set shutter state.
          @param enum state: desired shutter state
          @return enum ShutterState: actual shutter state
        """
        return ShutterState.OPEN 

    
    def get_temperatures(self):
        """ Get all available temperatures from laser.
          @return dict: dict of name, value for temperatures
        """
        las_temp = float(self.talk('LASTEMP?')[:-3])
        psu_temp = float(self.talk('PSUTEMP?')[:-3])
        return {'laser_temp_celsius': las_temp,
                'psu_temp_celsius': psu_temp}

    
    def get_temperature_setpoints(self):
        """ Get all available temperature setpoints from laser.
          @return dict: dict of name, value for temperature setpoints
        """
        return  {'laser_temp_celsius': 0.0,
                'psu_temp_celsius': 0.0}

    
    def set_temperatures(self, temps):
        """ Set laser temperatures.
          @param temps: dict of name, value to be set
          @return dict: dict of name, value of temperatures that were set
        """
        return {'laser_temp_celsius': 0.0,
                'psu_temp_celsius': 0.0}

    
    def get_extra_info(self):
        """ Show dianostic information about lasers.
          @return str: diagnostic info as a string
        """
        return self.talk('TIMERS?')
