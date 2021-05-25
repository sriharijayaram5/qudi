# -*- coding: utf-8 -*-

"""
This file contains the Qudi Hardware file to control the Pi3 stepper motor.

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
import serial
import time
from collections import OrderedDict

from core.module import Base
from core.configoption import ConfigOption
from interface.motor_interface import MotorInterface

class MotorPi3(Base, MotorInterface):
    """ This file contains the Qudi Hardware file to control the Pi3 stepper motor.
    """
    _com = ConfigOption('COM', 'COM5', missing='info')

    ON     = "1"
    OFF    = "0"
    
    STEPS  = "steps"
    DEGREE = "deg"
    PI     = "pi"
    
    CW     = "CW"
    CCW    = "CCW"
    STOP   = "STOP"

    def get_constraints(self):
        """ Retrieve the hardware constrains from the motor device.

        @return dict: dict with constraints for the magnet hardware. These
                      constraints will be passed via the logic to the GUI so
                      that proper display elements with boundary conditions
                      could be made.

        Provides all the constraints for each axis of a motorized stage
        (like total travel distance, velocity, ...)
        Each axis has its own dictionary, where the label is used as the
        identifier throughout the whole module. The dictionaries for each axis
        are again grouped together in a constraints dictionary in the form

            {'<label_axis0>': axis0 }

        where axis0 is again a dict with the possible values defined below. The
        possible keys in the constraint are defined here in the interface file.
        If the hardware does not support the values for the constraints, then
        insert just None. If you are not sure about the meaning, look in other
        hardware files to get an impression.

        Example of how a return dict with constraints might look like:
        ==============================================================

        constraints = {}

        axis0 = {}
        axis0['label'] = 'x'    # it is very crucial that this label coincides
                                # with the label set in the config.
        axis0['unit'] = 'm'     # the SI units, only possible m or degree
        axis0['ramp'] = ['Sinus','Linear'], # a possible list of ramps
        axis0['pos_min'] = 0,
        axis0['pos_max'] = 100,  # that is basically the traveling range
        axis0['pos_step'] = 100,
        axis0['vel_min'] = 0,
        axis0['vel_max'] = 100,
        axis0['vel_step'] = 0.01,
        axis0['acc_min'] = 0.1
        axis0['acc_max'] = 0.0
        axis0['acc_step'] = 0.0

        axis1 = {}
        axis1['label'] = 'phi'   that axis label should be obtained from config
        axis1['unit'] = 'degree'        # the SI units
        axis1['ramp'] = ['Sinus','Trapez'], # a possible list of ramps
        axis1['pos_min'] = 0,
        axis1['pos_max'] = 360,  # that is basically the traveling range
        axis1['pos_step'] = 100,
        axis1['vel_min'] = 1,
        axis1['vel_max'] = 20,
        axis1['vel_step'] = 0.1,
        axis1['acc_min'] = None
        axis1['acc_max'] = None
        axis1['acc_step'] = None

        # assign the parameter container for x to a name which will identify it
        constraints[axis0['label']] = axis0
        constraints[axis1['label']] = axis1
        """
        constraints = {}
        axis0 = {}
        axis0['label'] = 'phi'   #that axis label should be obtained from config
        axis0['unit'] = 'degree'        # the SI units
        axis0['ramp'] = [], # a possible list of ramps
        axis0['pos_min'] = 0,
        axis0['pos_max'] = 360,  # that is basically the traveling range
        axis0['pos_step'] = 1,
        axis0['vel_min'] = 1,
        axis0['vel_max'] = 20,
        axis0['vel_step'] = 0.1,
        axis0['acc_min'] = None
        axis0['acc_max'] = None
        axis0['acc_step'] = None
        constraints['axis0'] = axis0
        
        return constraints   
    # --------------------------------------------------------------------------
    def on_activate(self):                               #it was /dev/ttyUSB0 and i put COM4 santo
        self.ser = serial.Serial(
            port = self._com,
            baudrate = 57600,
        bytesize = serial.EIGHTBITS,
            parity = serial.PARITY_NONE,
            stopbits = serial.STOPBITS_ONE,
            timeout = 5,      
        xonxoff = 0,
        rtscts = 0,
        dsrdtr = 0,
        writeTimeout = 5
        )
        self.ser.close()
        self.ser.open()
        time.sleep(0.5)
        
    # --------------------------------------------------------------------------
    def on_deactivate(self):
        if self.ser.isOpen():
            self.ser.close()

    def __checkMotor(self, motor):
        if not isinstance(motor, int):
            print("error: motor number must be an integer.")
            return False
        if motor > 3:
            print("maximum motor is 3")
            return False
        if motor < 0:
            print("minimum motor is 0")
            return False
        
        return True
  
    # --------------------------------------------------------------------------
    def __checkUnit(self, unit):
        if unit == self.STEPS or unit == self.DEGREE or unit == self.PI:
            return True
        else:
            return False

    def __sendCommand(self, cmd):    
        ack = "A"
        maxtries = 0
        self.ser.flushOutput()
        
        while ord(ack) != 6 and maxtries < 10:
        #print cmd
            self.ser.write((cmd + '\n').encode('ascii'))
            self.ser.flush()
            time.sleep(0.05)
            maxtries += 1
            while self.ser.inWaiting() == 0:
                pass
            
            if self.ser.inWaiting() > 0:
                ack = self.ser.read(1)
            
        if maxtries == 9:
            print("error: unable to send command: " + cmd)
        
        self.ser.flushOutput()
        return
    
    # --------------------------------------------------------------------------
    def __readResponse(self):
        out = ""    
        while self.ser.inWaiting() > 0:
            c = self.ser.read(1).decode('ascii')
            if c != '\n':
                out += c
        
        self.ser.flushInput()
        return out
        
    # --------------------------------------------------------------------------
    # command implementation
    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    def reset(self):
        self.__sendCommand("STOPALL")
        self.__sendCommand("*RST")
        return
        
    # --------------------------------------------------------------------------
    def getIDN(self):
        self.__sendCommand("*IDN?")
        return str(self.__readResponse())
    
    # --------------------------------------------------------------------------
    def setIDN(self, id):
        if not isinstance(id, basestring):
            print("ID is not a string.")
            return
        
        if len(id) > 20:
            print("IDN too long. max: 20 characters")
            return
        
        if len(id) == 0:
            print("IDN too short. min: 1 character")
            return
        
        self.__sendCommand("*IDN " + id)
        return
        

    def move_rel(self,  param_dict):
        """ Moves stage in given direction (relative movement)

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <the-abs-pos-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.

        A smart idea would be to ask the position after the movement.

        @return int: error code (0:OK, -1:error)
        """
        m = [*param_dict.keys()][0]
        motors = {'phi': 0, 'x': 1, 'y' :2, 'z': 3}
        motor = motors[m]
        pos = param_dict[m]
        unit = param_dict['unit']

        if unit is self.STEPS and not isinstance(pos, int):
            print ("err: unit is STEPS, so position must be an integer")
            return -1
        
        if self.__checkMotor(motor) and self.__checkUnit(unit):
            cmd = "MOVEREL " + str(motor) + " " + str(pos) + " " + unit
            self.__sendCommand(cmd)
        return 0

    def move_abs(self, param_dict):
        m = [*param_dict.keys()][0]
        motors = {'phi': 0, 'x': 1, 'y' :2, 'z': 3}
        motor = motors[m]
        pos = param_dict[m]
        unit = param_dict['unit']

        if unit is self.STEPS and not isinstance(pos, int):
            print("err: unit is STEPS, so position must be an integer")
            return
            
        if pos < 0:
            print("position must be a positive value")
            return
            
        if self.__checkMotor(motor) and self.__checkUnit(unit):
            cmd = "MOVEABS " + str(motor) + " " + str(pos) + " " + unit
            self.__sendCommand(cmd)
            return

    def zeroMotor(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("ZERORUN " + str(motor))
            return
        
    # --------------------------------------------------------------------------
    def turnOnMotor(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("ENABLE " + str(motor) + " " + self.ON)
            return

    # --------------------------------------------------------------------------
    def turnOffMotor(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("ENABLE " + str(motor) + " " + self.OFF)


    def abort(self):
        """ Stops movement of the stage

        @return int: error code (0:OK, -1:error)
        """
        self.__sendCommand("STOPALL")
        return  

    def get_pos(self, param_list=None):
        """ Gets current position of the stage arms

        @param list param_list: axes to check

        @return dict: with keys being the axis labels and item the current
                      position.
        """
        m = param_list[0]
        motors = {'phi': 0, 'x': 1, 'y' :2, 'z': 3}
        motor = motors[m]
        unit = self.STEPS
        if self.__checkMotor(motor) and self.__checkUnit(unit):    
            self.__sendCommand("GETPOS " + str(motor) + " " + unit)
            # print(self.__readResponse())
            return float(self.__readResponse())
        return

    def get_status(self, param_list=None):
        """ Get the status of the position

        @param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        @return dict: with the axis label as key and the status number as item.
        """
        m = param_list[0]
        motors = {'phi': 0, 'x': 1, 'y' :2, 'z': 3}
        motor = motors[m]
        if self.__checkMotor(motor):
            self.__sendCommand("ISMOVING " + str(motor))
            resp = self.__readResponse()
            if resp == "1":
                return True
            else:
                return False
        return

    def calibrate(self, param_list=None):
        """ Calibrates the stage.

        @param dict param_list: param_list: optional, if a specific calibration
                                of an axis is desired, then the labels of the
                                needed axis should be passed in the param_list.
                                If nothing is passed, then all connected axis
                                will be calibrated.

        @return int: error code (0:OK, -1:error)

        After calibration the stage moves to home position which will be the
        zero point for the passed axis. The calibration procedure will be
        different for each stage.
        """
        pass

    def get_velocity(self, param_list=None):
        """ Gets the current velocity for all connected axes.

        @param dict param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        @return dict : with the axis label as key and the velocity as item.
        """
        pass

    def set_velocity(self, param_dict):
        """ Write new value for velocity.

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <the-velocity-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.

        @return int: error code (0:OK, -1:error)
        """
        pass

    def getAnalogValue(self, channel=0):
        if self.__checkMotor(channel):
            self.__sendCommand("GETANALOG " + str(channel))
            return int(self.__readResponse())
        return    
  
    # --------------------------------------------------------------------------
    def getOpticalZeroPosition(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("GETOPTZEROPOS " + str(motor))
            return int(self.__readResponse())
        return
    
    # --------------------------------------------------------------------------
    def setOpticalZeroPosition(self, motor=0, position=0):
        if not isinstance(position, int):
            print("optical zero position must be given in steps, integer.")
            return
        
        if self.__checkMotor(motor):
            cmd = "SETOPTZEROPOS " + str(motor) + " " + str(position)
            self.__sendCommand(cmd)
        return
        
    # --------------------------------------------------------------------------
    def getGearRatio(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("GETGEARRATIO " + str(motor))
            return float(self.__readResponse())
        return
    
    # --------------------------------------------------------------------------
    def setGearRatio(self, motor=0, ratio=60.0/18.0):
        if self.__checkMotor(motor):
            cmd = "SETGEARRATIO " + str(motor) + " " + str(ratio)
            self.__sendCommand(cmd)
        return
        
    # --------------------------------------------------------------------------
    def getStepsPerFullRotation(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("GETFULLROT " + str(motor))
            return int(self.__readResponse())
        return

    # --------------------------------------------------------------------------
    def setStepsPerFullRotation(self, motor=0, steps=400):
        if not isinstance(steps, int):
            print("must be given as integer number")
            return
        
        if steps != 200.0 and steps != 400.0:
            print("steps must be either 200 or 400.")
            return
        
        if self.__checkMotor(motor):
            cmd = "SETFULLROT " + str(motor) + " " + str(steps)
            self.__sendCommand(cmd)
        return
        
    # --------------------------------------------------------------------------
    def getSubSteps(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("GETSUBSTEPS " + str(motor))
            return int(self.__readResponse())
        return

    # --------------------------------------------------------------------------
    def setSubSteps(self, motor=0, substeps=4):
        if not isinstance(substeps, int):
            print("must be given as integer number")
            return
        
        if substeps != 0 and ((substeps and (substeps - 1)) == 0):
            print("substeps must be a power of two")
            return
        
        if substeps < 1 or substeps > 16:
            print("substeps must be a positive number")
            return
        
        if self.__checkMotor(motor):
            cmd = "SETSUBSTEPS " + str(motor) + " " + str(substeps)
            self.__sendCommand(cmd)
        return

    # --------------------------------------------------------------------------
    def getWaitTimeBetweenSteps(self, motor=0):
        if self.__checkMotor(motor):
            self.__sendCommand("GETWAITTIME " + str(motor))
            return int(self.__readResponse())
        return

    # --------------------------------------------------------------------------
    def setWaitTimeBetweenSteps(self, motor=0, waittime=3):
        if not isinstance(waittime, int):
            print("waittime must be given as integer number")
            return
        
        if waittime < 1:
            print("waittime must be >= 1")
            return
        
        if self.__checkMotor(motor):
            cmd = "SETWAITTIME " + str(motor) + " " + str(waittime)
            self.__sendCommand(cmd)
        return

    # --------------------------------------------------------------------------
    def setConstAngularVelocity(self, motor=0, direction=CW, time=10.0):
        if time < 5.0:
            print("time must be >= 5.0 seconds")
            return
        
        if self.__checkMotor(motor):
            cmd = "SETCONSTSPEED " + str(motor) + " " + direction + " " + str(time)
            self.__sendCommand(cmd)
        return
        
    # --------------------------------------------------------------------------
    def factoryReset(self):
        self.__sendCommand("FACTORYRESET")
        return
    
