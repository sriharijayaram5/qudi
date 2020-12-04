# -*- coding: utf-8 -*-
"""
Hardware module for communication with cobolt lasers.

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

from core.module import Base, ConfigOption
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

        self._dev = CoboltLaserStandalone(self._com_port)

        self.shutter = ShutterState.CLOSED
        self.power_setpoint = 0
        self.current_setpoint = 0

        self.mode = ControlMode.POWER # This is the default mode
        #Setting the laser to its default mode
        self.set_control_mode(self.mode)
        
        self.get_laser_state()  # get current laser state

        self.current_setpoint = 80 #Starting at a low current in mA
        self.power_setpoint = 0.005 #Starting at a low power in Watts

    def on_deactivate(self):

        self.off()
        self._dev.disconnect_laser()


    def get_power_range(self):
        """ Return laser power

        @return tuple(p1, p2): Laser power range (min, max) in watts
        """
        return (0, 0.080)

    def get_power(self):
        """ Return laser power independent of the mode.

        @return float: Actual laser power in Watts (W).
        """
        if self.mode.value == 1:  
            return self._dev.get_power()

        if self.mode.value == 2:
            return self._dev.get_outputpower()

        if self.mode.value == 3:
            return self._dev.get_modulation_power()

        if self.mode.value == 4:
            return self._dev.get_modulation_power()

    def set_power(self, power):
        """ Set laser power in watts

        @param float power: laser power setpoint in watts

        @return float: laser power setpoint in watts
        """
        #If you are ever trying to set a power while in Current mode
        #This will help not create problems.
        if self.get_control_mode() == ControlMode.CURRENT:
            self.set_control_mode(ControlMode.POWER)
            self.power_setpoint = power
            self.power_setpoint = self._dev.set_power(power) 
        
        if self.get_control_mode() == ControlMode.POWER:
            self.power_setpoint = power
            self.power_setpoint = self._dev.set_power(power)

        if self.get_control_mode() == ControlMode.MODULATION_DIGITAL:
            self.power_setpoint = power
            self.power_setpoint = self._dev.set_modulation_power(power)
        
        return self.get_power()

    def get_power_setpoint(self):
        """ Return laser power setpoint

        @return float: Laser power setpoint in watts
        """
        return self.power_setpoint 

    def get_current_unit(self):
        """ Return laser current unit

        @return str: unit, currently only percent
        """
        return 'mA'

    def get_current(self):
        """ Return laser current

        @return float: actual laser current as ampere or percentage of maximum current
        """
        return self._dev.get_current()

    def get_current_range(self):
        """ Return laser current range

        @return tuple(c1, c2): Laser current range (min, max) in current units
        """
        #A current of 250 mA gives around 80 mW of power.
        return (0, 250)

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
        #If you are ever trying to set a current while in any Power mode
        #This will help not create problems.
        if self.get_control_mode() != ControlMode.CURRENT:
            self.set_control_mode(ControlMode.CURRENT)

        self.current_setpoint = current
        self.current_setpoint = self._dev.set_current(current)
        return self.get_current()

    def allowed_control_modes(self):
        """ Get available control mode of laser

        @return list: list with enum control modes
        """
        return [ControlMode.POWER, ControlMode.CURRENT, ControlMode.MODULATION_DIGITAL, ControlMode.MODULATION_ANALOG]

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

                if self.mode.value == 1: 
                    self._dev.enter_constant_power()

                if self.mode.value == 2:
                    self._dev.enter_constant_current()

                if self.mode.value == 3:
                    self._dev.enter_modulation_mode()
                    self._dev.set_analog_modulation(0)
                    self._dev.set_digital_modulation(True)

                if self.mode.value == 4:
                    self._dev.enter_modulation_mode()
                    self._dev.set_digital_modulation(False)
                    self._dev.set_analog_modulation(1)

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

        Turning the laser on depends on if autostart is enabled (True) or disabled (False).

        However, to get around the manual issue, getting into its mode will try and see if
        the key position is in the correct place. 

        """
        
        #This is for when autostart is Disabled
        #self._dev.set_laser_output(LaserState.ON.value)
        #return self.get_laser_state()

        if self._dev.get_autostart():
            self._dev.restart_laser()
        else:
            self._dev.set_laser_output(bool(LaserState.ON.value))
        
        #self.set_control_mode(self.get_control_mode())
        #self.log.warning('The Laser state is OFF, because the Key switch trigger is required!')
        return self.get_laser_state()

    def off(self):
        """ Turn off laser. Does not close shutter if one is present.
        
        @return enum LaserState: actual laser state
        """

        #FIXME: Is this waiting time really required???
        self._dev.set_laser_output(LaserState.OFF.value)
        return self.get_laser_state()

    def get_laser_state(self):
        """ Get laser state.

        Specific for Cobolt_06_MLD due to some issues with the l? command.
        
        @return enum LaserState: laser state
        """

        laser_operating_mode = self._dev.get_operatingmode()

        if laser_operating_mode == 0:
            self.lstate = LaserState.OFF

        elif laser_operating_mode == 1:
            self.log.warning('The Laser state is OFF, because the Key switch trigger is required!')
            
            self.lstate = LaserState.OFF

        elif laser_operating_mode == 2:
            self.lstate = LaserState.ON

        elif laser_operating_mode == 3:
            self.lstate = LaserState.ON

        elif laser_operating_mode == 4:
            self.lstate = LaserState.ON

        elif laser_operating_mode == 5:
            self.log.warning('There is a fault in the laser, please check!')
            self.lstate = LaserState.OFF

        elif laser_operating_mode == 6:
            self.log.warning('The operating mode of the laser is OFF, everything is Aborted.')
            self.lstate = LaserState.OFF

        else:
            self.log.error('No possible laser state could be detected, turning the laser OFF.')
            self._dev.set_laser_output(bool(LaserState.OFF.value))

        return self.lstate


    def set_laser_state(self, state):
        """ Set laser state.
        
        @param enum state: desired laser state
        
        @return enum LaserState: actual laser state
        """
        curr_state = self._dev.set_laser_output(bool(state))

        if curr_state:
            self.lstate = LaserState.ON
        else:
            self.lstate = LaserState.OFF

        return self.lstate

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

        return str(self._dev.extra_info)

class CoboltLaserStandalone():

    MODEL = '06-MLD 515nm'
    BRAND = 'Cobolt'
    SERIAL_NUM = 0
    BAUD_RATE = 115200

    # Laser safety:
    OD_NUM = '3 OD' # optical density number
    LASER_CLASS = 'III B'
    extra_info = {}

    log = logger
    _is_connected = False

    def __init__(self, comport):
        """ Initialize the laser connection.

        @param str comport: the name of the comport, e.g. 'ASRL3::INSTR' or 'COM3'
        """
        self.rm = visa.ResourceManager()
        self.connect_laser(comport)

    def __del__(self):
        """ Handle what happens if object is distroyed. """
        self.disconnect_laser()

    def connect_laser(self, comport, timeout=2.0):
        """ Connect method for the laser.

        @param str comport: comport name, e.g. 'ASRL3::INSTR' or 'COM3'
        @param float timeout: timeout of a communication request in seconds
        """

        self._device = self.rm.open_resource(comport, open_timeout=int(timeout*1000))
        # super stupid, new implementation of the timeout parameter in visa library
        # specifies the timeout now in milliseconds and should be an integer!
        # Hence, make sure to pass the right convertion!
        self._is_connected = True

        self._device.baud_rate = self.BAUD_RATE
        self.SERIAL_NUM = self.get_serialnumber()

        self.extra_info = {'brand': self.BRAND, 'model': self.MODEL, 
                           'serial_number': self.SERIAL_NUM, 
                           'required OD goggles': self.OD_NUM,
                           'laser_class': self.LASER_CLASS}

        self.log.info(f'Initialized Laser from {self.BRAND} of model '
                      f'{self.MODEL} with S/N: {self.SERIAL_NUM}.\n'
                      f'Current operation hours: {self.get_operatinghours()}h.')

        self.log.warning(f'Be aware! It is a Class {self.LASER_CLASS} laser, '
                         f'so wear Laser protection with Optical Density '
                         f'number {self.OD_NUM}!')

        #FIXME do not set the autostart to false
        #self.set_autostart(False)
        
    def disconnect_laser(self):
        """ Disconnect the laser."""
        if self._is_connected:
            self._device.close()
            self._is_connected = False
        
    def query(self, question):
        """ General method for query questions from laser. 
        
        @param str question: refer to the manual of the laser for further info.
        
        @return str: the raw response of the laser.
        """

        # VERY IMPORTANT!! before asking, clear buffer
        self._device.clear() 
        return self._device.query(question)

    def write(self, message):
        """General method to write messages to laser. 

        @param str message: message to the laser.
        """
        self._device.write(message)
        
    def get_laser_output(self):
        """ Ask whether laser output is on. 

        @return bool: 
            False=laser is off, 
            True=laser is on."""

        return bool(int(self.query('l?').strip()))
    
    def set_laser_output(self, state):
        """ Switch the output of the laser on or off.

        @param bool state: False=OFF, True=ON
        """
        self.write(f'l{int(state)}')

        curr_state = self.get_laser_output()

        if curr_state != state:
            self.log.warning(f'Laser state could not be changed in the desired state {state}, remaining in {curr_state}.')
        return curr_state
        

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
        return int(self.query('gom?').strip())


    def restart_laser(self):
        """ Method for restarting the laser, which forces the laser
            to be on without checking if autostart is enabled. 
        
        @return str: indicates the state of the laser, 'OK' = all fine
        """

        self.write('@cob1')
        return self.get_last_errormessage()
        
    def get_operatinghours(self):
        """Method for getting the operating hours of the laser. 
        
        @return float: the indicated operating hours.
        """
        return float(self.query('hrs?'))
    
    def get_power(self):
        """ Get the setpoint power of the laser. 
        
        @return float: the indicated power in Watts (W).
        """
        return float(self.query('p?').strip())

    def get_outputpower(self):
        """ Used in current mode, get the output power of the laser. 
        
        @return float: the indicated output power in Watts (W).
        """
        return float(self.query('pa?'))
    
    def set_power(self, power):
        """ Set the power of the laser. 
        
        @param float power: The power shall be a float in Watts (W).
        
        @return float: the indicated power in Watts (W).
        """
        self.write("p {0}".format(power))
        return self.get_power()
    
    def get_current(self):
        """Method for getting the current of the laser. 
        
        @return float: the indicated current in milliAmps (mA).
        """
        return float(self.query('i?').strip())
    
    def set_current(self,current):
        """Method for setting the current of the laser. 
        
        @param float current: The current shall be a float in milliAmps (mA).
        
        @return float: the indicated current in milliAmps (mA).
        """
        self.write('slc {0}'.format(current))
        return self.get_current()
    
    def enter_constant_power(self):
        """ Method for entering constant power mode."""
        self.write('cp')
        
    def enter_constant_current(self):
        """ Method for entering constant current mode."""
        self.write('ci')
    
    def get_interlock_state(self):
        """Method for obtaining the interlock state. 
        
        @return int: with the following meaning:
                        True = interlock open
                        False = OK
        """
        return bool(not int(self.query("ilk?").strip()))

    def get_autostart(self):
        """Method for obtaining the autostart state. 
        
        @return bool: with the following meaning:
                        False = OFF
                        True = ON
        """
        return bool(int(self._device.query("@cobas?").strip()))
    
    def set_autostart(self, state):
        """Method for setting the autostart state. 
        
        @param bool: with the following meaning:
                        False = OFF
                        True = ON
        @return bool: returns the current state of the autostart
        """
        self.write(f"@cobas {int(state)}")
        self.query('?') # this seems to be a bug in the controller, whenever
                        # autostart is changed, the buffer has to be manually
                        # cleared after the request.
        return self.get_autostart()

    def get_serialnumber(self):
        """Method for obtaining the serial number of the laser. 
        
        @return int: 32-bit unassigned integer.
        """
        return int(self.query("gsn?").strip())

    def enter_modulation_mode(self):
        """Method for entering modulation mode."""
        self.write("em")

    def set_digital_modulation(self, state):
        """ Set the state of the digital modulation mode. 
        
        @param bool state: with the following meaning:
                        False = disable
                        True = enable
        """
        self.write(f'sdmes {state}')
        return self.get_digital_modulation()

    def get_digital_modulation(self):
        """ Get the state of the digital modulation mode. 
        
        @return bool state: with the following meaning:
                        False = disable
                        True = enable
        """
        return bool(int(self.query("gdmes?").strip()))
    
    def set_analog_modulation(self, state):
        """ Set the state of the analog modulation mode. 
        
        @param bool state: with the following meaning:
                        False = disable
                        True = enable
        """
        self.write(f'sames {state}')
        return self.get_analog_modulation()

    def get_analog_modulation(self):
        """ Get the state of the analog modulation mode. 
        
        @return int state: with the following meaning:
                        False = disable
                        True = enable
        """
        return bool(int(self.query('games?').strip()))

    def set_modulation_power(self, power):
        """Method for setting the power of the laser in modulation mode. 
        
        @param float power: The power shall be a float in milliWatts (mW).
        
        @return float: the indicated power in Watts (W).
        """
        self.write(f'slmp {power*1000}')
        return self.get_modulation_power()

    def get_modulation_power(self):
        """Method for getting the setpoint power of the laser in modulation mode. 
        
        @return float: the indicated power in Watts (W).
        """
        return  float(self.query('glmp?').strip())/1000

    def is_keyswitch_turned(self):
        """ Obtaining the key switch state, either ON or OFF. 

        @return bool: 
                False = key switch is OFF
                True = key switch is ON
        """
        return bool(int(self.query('@cobasks?').strip()))

    def get_last_errormessage(self):
        """ Obtain the last error message. 

        @return str: the text of the message, will output 'OK' if all is fine.
        """
        return self.query('cf').strip()

