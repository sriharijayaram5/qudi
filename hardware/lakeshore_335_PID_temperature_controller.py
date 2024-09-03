# -*- coding: utf-8 -*-
"""
Author: Malik Lenger
Code for Lakeshore 335 temperature controller.

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
from interface.pid_controller_interface import PIDControllerInterface
from qtpy import QtCore
from lakeshore import Model335
import lakeshore


class temperaturecontroller335(Base, PIDControllerInterface):
    """ Communicate with the Lakeshore 335 temperature controller.
        The code is written for one close loop operation of PID temperature control using one input temperture sensor and one output for a heater.
        Make sure, that the device is connected to a proper USB port. Otherwise, timeout errors can occure.

    Example config for copy-paste:

    temperature_controller:
        module.Class: 'lakeshore_335_PID_temperature_controller.temperaturecontroller335'
        serial_port: 'COM1'
        output: 1 #Chose 1 or 2
        mode: 1 #0=off, 1=closed loop PID, 2=zone, 3=open loop, 4=monitor out, 5=warmup supply
        powerup: 0 #0=off, 1=on
        type: 0 #0=current, 1=voltage (valtage only for output 2 possible)
        resistance: 1 #1=25ohm, 2=50ohm of used heater
        max_current: 1 #0=user specified, 1=0.707A, 2=1A, 3=1.141A, 4=1.732A maximum heater output current
        max_current_user: 0 #specifies maximum heater output current for 0=user specified
        input: 'A' #Chose A or B
        sensor_type: 0 #0=Disabled, 1=Diode, 2=Platinum RTD, 3 =NTC RTD, 4 =Thermocouple
        autorange: 1 #0=off, 1=on
        range: 0 #range used when autorange is off. See manual for details
        compensation: 1 #0=off, 1=on
        units: 1 #1=Kelvin, 2=Celsius, 3=Sensor
        curve_number: 0 #Chose number of the used calibration curve.

    From Wikipedia : https://en.wikipedia.org/wiki/PID_controller
    A proportional–integral–derivative controller (PID controller or three-term controller) is a control loop mechanism
    employing feedback that is widely used in industrial control systems and a variety of other applications requiring
    continuously modulated control. A PID controller continuously calculates an error value e(t) as the difference
    between a desired setpoint (SP) and a measured process variable (PV) and applies a correction based on proportional,
    integral, and derivative terms (denoted P, I, and D respectively), hence the name.

    If the device is enabled, the control value is computed by the the PID system of the hardware. If the device is
    disabled, the control value is set by the manual value.

    """
    serial_port = ConfigOption('serial_port', 'COM1', missing='warn')
    output = ConfigOption('output', 1, missing='warn')
    mode = ConfigOption('mode', 1, missing='warn')
    powerup = ConfigOption('powerup', 0, missing='warn')
    type = ConfigOption('type', 0, missing='warn')
    resistance = ConfigOption('resistance', 2, missing='warn')
    max_current = ConfigOption('max_current', 1, missing='warn')
    max_current_user = ConfigOption('max_current_user', 0, missing='warn')
    input = ConfigOption('input', 'A', missing='warn')
    sensor_type = ConfigOption('sensor_type', '0', missing='warn')
    autorange = ConfigOption('autorange', '1', missing='warn')
    range = ConfigOption('range', '0', missing='warn')
    compensation = ConfigOption('compensation', '1', missing='warn')
    units = ConfigOption('units', '1', missing='warn')
    curve_number = ConfigOption('curve_number', '0', missing='warn')


    def on_activate(self):
        """ Activate module.
        """
        self.temp_controller = Model335(baud_rate = 57600, com_port = self.serial_port)
        try: #This test has to be done, as it sometimes causes an error for the first query after activation.
            self.temp_controller.query('*IDN?')
        except:
            self.log.warn('Something might went wrong with the connection to the Temperature controller.')

        self.setup_input()
        self.setup_output()
        self.set_printing(False) #Deactivates the priting of information after every query for better readability of the log.

    def on_deactivate(self):
        """ Deactivate module.
        """
        self.set_printing(True)
        self.temp_controller.disconnect_usb()

    def setup_input(self):
        """ Setup the input used for the PID controll loop with the parameters given from the config file.
        """
        str = f'INTYPE{self.input},{self.sensor_type},{self.autorange},{self.range},{self.compensation},{self.units}'
        self.temp_controller.command(str)
        str = f'INCRV{self.input},{self.curve_number}'
        self.temp_controller.command(str)

    def setup_output(self):
        """ Setup the output used for the PID controll loop with the parameters given from the config file.
        """
        if self.input == 'A':
            input = 1
        elif self.input == 'B':
            input = 2
        else:
            input = 0
        str = f'OUTMODE{self.output},{self.mode},{input},{self.powerup}'
        self.temp_controller.command(str)
        str = f'HTRSET{self.output},{self.type},{self.resistance},{self.max_current},{self.max_current_user},2'
        self.temp_controller.command(str)

    def set_printing(self, printing):
        """ Set the printing flag in the lakeshore GenericInstrument to turn on and off the logging information after every query.

         @param (boolean) printing: the printing flag
         """
        lakeshore.generic_instrument.GenericInstrument.printing = printing #The GenericInsturment file has to be changed for this.

    def get_kp(self):
        """ Get the coefficient associated with the proportional term

         @return (float): The current kp coefficient associated with the proportional term
         """
        str = f'PID?{self.output}'
        return float(self.temp_controller.query(str).split(',')[0])

    def set_kp(self, kp):
        """ Set the coefficient associated with the proportional term

         @param (float) kp: The new kp coefficient associated with the proportional term
         """
        str = f'PID?{self.output}'
        current_PID = self.temp_controller.query(str).split(',')
        ki = float(current_PID[1])
        kd = float(current_PID[2])
        str = f'PID{self.output},{kp},{ki},{kd}'
        self.temp_controller.command(str)

    def get_ki(self):
        """ Get the coefficient associated with the integral term

         @return (float): The current ki coefficient associated with the integral term
         """
        str = f'PID?{self.output}'
        return float(self.temp_controller.query(str).split(',')[1])

    def set_ki(self, ki):
        """ Set the coefficient associated with the integral term

         @param (float) ki: The new ki coefficient associated with the integral term
         """
        str = f'PID?{self.output}'
        current_PID = self.temp_controller.query(str).split(',')
        kp = float(current_PID[0])
        kd = float(current_PID[2])
        str = f'PID{self.output},{kp},{ki},{kd}'
        self.temp_controller.command(str)

    def get_kd(self):
        """ Get the coefficient associated with the derivative term

         @return (float): The current kd coefficient associated with the derivative term
         """
        str = f'PID?{self.output}'
        return float(self.temp_controller.query(str).split(',')[2])

    def set_kd(self, kd):
        """ Set the coefficient associated with the derivative term

         @param (float) kd: The new kd coefficient associated with the derivative term
         """
        str = f'PID?{self.output}'
        current_PID = self.temp_controller.query(str).split(',')
        kp = float(current_PID[0])
        ki = float(current_PID[1])
        str = f'PID{self.output},{kp},{ki},{kd}'
        self.temp_controller.command(str)

    def get_setpoint(self):
        """ Get the setpoint value of the hardware device

         @return (float): The current setpoint value
         """
        str = f'SETP?{self.output}'
        return float(self.temp_controller.query(str))

    def set_setpoint(self, setpoint):
        """ Set the setpoint value of the hardware device

        @param (float) setpoint: The new setpoint value
        """
        str = f'SETP{self.output},{setpoint}'
        self.temp_controller.command(str)

    def get_manual_value(self):
        """ Get the manual value, used if the device is disabled

        @return (float): The current manual value in %
        """
        str = f'MOUT?{self.output}'
        return float(self.temp_controller.query(str))

    def set_manual_value(self, manualvalue):
        """ Set the manual value, used if the device is disabled

        @param (float) manualvalue: The new manual value in %
        """
        str = f'MOUT{self.output},{manualvalue}'
        self.temp_controller.command(str)

    def get_enabled(self):
        """ Get if the PID is enabled (True) or if it is disabled (False) and the manual value is used

        @return (bool): True if enabled, False otherwise
        """
        str = f'RANGE?{self.output}'
        if int(self.temp_controller.query(str).split(',')[0]) == 0:
            return False
        else:
            return True

    def set_enabled(self, enabled):
        """ Set if the PID is enabled (True) or if it is disabled (False) and the manual value is used

        @param (bool) enabled: True to enabled, False otherwise
        """
        if enabled:
            str = f'RANGE{self.output},3'
            self.temp_controller.command(str)
        else:
            str = f'RANGE{self.output},0'
            self.temp_controller.command(str)


    def get_control_limits(self):
        """ Get the current limits of the control value as a tuple

        @return (tuple(float, float)): The current control limits
        """
        pass

    def set_control_limits(self, limits):
        """ Set the current limits of the control value as a tuple

        @param (tuple(float, float)) limits: The new control limits

        The hardware should check if these limits are within the maximum limits set by a config option.
        """
        pass

    def get_process_value(self):
        """ Get the current process value read

        @return (float): The current process value
        """
        str = f'KRDG?{self.input}'
        return float(self.temp_controller.query(str))

    def get_control_value(self):
        """ Get the current control value read

        @return (float): The current control value
        """
        str = f'HTR?{self.output}'
        return float(self.temp_controller.query(str))

    def get_extra(self):
        """ Get the P, I and D terms computed bu the hardware if available

         @return dict(): A dict with keys 'P', 'I', 'D' if available, an empty dict otherwise
         """
        return {}
