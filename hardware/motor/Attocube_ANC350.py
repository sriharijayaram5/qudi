# -*- coding: utf-8 -*-
# Sreehari Jayaram 22/04/24
"""
This file contains the hardware file for ANC350v2(old device). Comm via
pylablib.

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

from collections import OrderedDict
import time

from core.module import Base
from interface.motor_interface import MotorInterface
from core.configoption import ConfigOption
import numpy as np
from pylablib.devices import Attocube

class MotorAxis:
    """ Generic dummy motor representing one axis. """
    def __init__(self, axis, dev):
        self.axis = axis # this will be the integer axis number
        self._dev = dev
    
    def move_abs(self, position):
        return self._dev.move_abs(self.axis, position)
    
    def move_step(self, step=1):
        return self._dev.move_by_steps(self.axis, step)
    
    def continuous(self, direction):
        """direction  can be "+" or "-".
        """
        return self._dev.jog(self.axis, direction)
    
    def stop(self):
        return self._dev.stop(self.axis)
    
    def stop(self):
        return self._dev.stop(self.axis)
    
    def get_position(self):
        return self._dev.get_position(self.axis)

    def get_velocity(self):
        return self._dev.get_frequency(self.axis)
    
    def set_velocity(self, velocity):
        return self._dev.set_frequency(self.axis, velocity)
    
    def set_voltage(self, voltage):
        return self._dev.set_voltage(self.axis, voltage)
    
    def get_voltage(self):
        return self._dev.get_voltage(self.axis)
    

class Positioner(Base, MotorInterface):
    """ This is class to move a single ANC350 dev with many axes.

    Example config for copy-paste:

    motor_dummy:
        module.Class: 'motor.motor_dummy.MotorDummy'

    """
    _axes = ConfigOption('axes_list', missing='warn', default={0:'x', 1: 'y', 2: 'z'})
    _dev_no = ConfigOption('device_no', missing='warn', default=0)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self.log.debug('The following configuration was found.')

        # checking for the right configuration
        for key in config.keys():
            self.log.info('{0}: {1}'.format(key,config[key]))

    def on_activate(self):

        # PLEASE REMEMBER: DO NOT CALL THE POSITION SIMPLY self.x SINCE IT IS
        # EXTREMLY DIFFICULT TO SEARCH FOR x GLOBALLY IN A FILE!
        # Same applies to all other axis. I.e. choose more descriptive names.
        # these label should be actually set by the config.
        try:
            self._dev = Attocube.ANC350(conn=self._dev_no)
        except Exception as err:
            self.log.warning(f'Unable to connect to device!!! Please check connection or ensure that all other backend connections are dead. Use Daisy to kill other backends. Error: {err}')
            self._dev = None
            return
        
        self._dev._update_axes(list(np.arange(len(self._axes.keys())))) # updates axis list based on how may keys are provided in the config

        self.positioner_axes = {}
        for axis in self._axes.keys():
            self.positioner_axes[axis] = MotorAxis(self._axes[axis], self._dev)
            self.positioner_axes[axis].label = axis
            self.positioner_axes[axis].vel = 1  #will be used to implement frequency of steps
            self.positioner_axes[axis].voltage = 1

        self._wait_after_movement = 1 #in seconds

    def on_deactivate(self):
        if self._dev:
            self._dev.close()
        return


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
        """
        constraints = OrderedDict()

        for axis in self.positioner_axes:
            axis0 = {'label':axis,
                    'unit': 'm',
                    'ramp': ['Sinus', 'Linear'],
                    'pos_min': -3e-3,
                    'pos_max': 3e-3,
                    'pos_step': 1e-9,
                    'vel_min': 1,
                    'vel_max': 1000,
                    'vel_step': 10,
                    'volt_min': 1,
                    'volt_max': 50}
            constraints[axis0['label']] = axis0
            # assign the parameter container for x to a name which will identify it

        return constraints

    def move_rel(self,  param_dict):
        """ Moves stage in given direction (relative movement)

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed.
                                With get_constraints() you can obtain all
                                possible parameters of that stage. According to
                                this parameter set you have to pass a dictionary
                                with keys that are called like the parameters
                                from get_constraints() and assign a SI value to
                                that. For a movement in x the dict should e.g.
                                have the form:
                                    dict = { 'x' : 23 }
                                where the label 'x' corresponds to the chosen
                                axis label.

        A smart idea would be to ask the position after the movement.
        """
        curr_pos_dict = self.get_pos()
        constraints = self.get_constraints()

        if param_dict.get(self._x_axis.label) is not None:
            move_x = param_dict[self._x_axis.label]
            curr_pos_x = curr_pos_dict[self._x_axis.label]

            if  (curr_pos_x + move_x > constraints[self._x_axis.label]['pos_max'] ) or\
                (curr_pos_x + move_x < constraints[self._x_axis.label]['pos_min']):

                self.log.warning('Cannot make further movement of the axis '
                        '"{0}" with the step {1}, since the border [{2},{3}] '
                        'was reached! Ignore command!'.format(
                            self._x_axis.label, move_x,
                            constraints[self._x_axis.label]['pos_min'],
                            constraints[self._x_axis.label]['pos_max']))
            else:
                self._make_wait_after_movement()
                self._x_axis.pos = self._x_axis.pos + move_x

        if param_dict.get(self._y_axis.label) is not None:
            move_y = param_dict[self._y_axis.label]
            curr_pos_y = curr_pos_dict[self._y_axis.label]

            if  (curr_pos_y + move_y > constraints[self._y_axis.label]['pos_max'] ) or\
                (curr_pos_y + move_y < constraints[self._y_axis.label]['pos_min']):

                self.log.warning('Cannot make further movement of the axis '
                        '"{0}" with the step {1}, since the border [{2},{3}] '
                        'was reached! Ignore command!'.format(
                            self._y_axis.label, move_y,
                            constraints[self._y_axis.label]['pos_min'],
                            constraints[self._y_axis.label]['pos_max']))
            else:
                self._make_wait_after_movement()
                self._y_axis.pos = self._y_axis.pos + move_y

        if param_dict.get(self._z_axis.label) is not None:
            move_z = param_dict[self._z_axis.label]
            curr_pos_z = curr_pos_dict[self._z_axis.label]

            if  (curr_pos_z + move_z > constraints[self._z_axis.label]['pos_max'] ) or\
                (curr_pos_z + move_z < constraints[self._z_axis.label]['pos_min']):

                self.log.warning('Cannot make further movement of the axis '
                        '"{0}" with the step {1}, since the border [{2},{3}] '
                        'was reached! Ignore command!'.format(
                            self._z_axis.label, move_z,
                            constraints[self._z_axis.label]['pos_min'],
                            constraints[self._z_axis.label]['pos_max']))
            else:
                self._make_wait_after_movement()
                self._z_axis.pos = self._z_axis.pos + move_z


        if param_dict.get(self._phi_axis.label) is not None:
            move_phi = param_dict[self._phi_axis.label]
            curr_pos_phi = curr_pos_dict[self._phi_axis.label]

            if  (curr_pos_phi + move_phi > constraints[self._phi_axis.label]['pos_max'] ) or\
                (curr_pos_phi + move_phi < constraints[self._phi_axis.label]['pos_min']):

                self.log.warning('Cannot make further movement of the axis '
                        '"{0}" with the step {1}, since the border [{2},{3}] '
                        'was reached! Ignore command!'.format(
                            self._phi_axis.label, move_phi,
                            constraints[self._phi_axis.label]['pos_min'],
                            constraints[self._phi_axis.label]['pos_max']))
            else:
                self._make_wait_after_movement()
                self._phi_axis.pos = self._phi_axis.pos + move_phi


    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement)

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <a-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.
        A smart idea would be to ask the position after the movement.
        """
        constraints = self.get_constraints()

        for param in param_dict:
            try:
                axis = self.positioner_axes[param]
                desired_pos = param_dict[param]
                constr = constraints[param]
            except KeyError:
                self.log.warning('Invalid axes given!')
                return -1
            
            if not(constr['pos_min'] <= desired_pos <= constr['pos_max']):
                self.log.warning('Cannot make absolute movement of the axis '
                        '"{0}" to possition {1}, since it exceeds the limits '
                        '[{2},{3}] ! Command is ignored!'.format(
                            param, desired_pos,
                            constr['pos_min'],
                            constr['pos_max']))
            else:
                axis.move_abs(desired_pos)
                axis.pos = desired_pos


    def abort(self):
        """Stops movement of the stage

        @return int: error code (0:OK, -1:error)
        """
        for axis in self.positioner_axes:
            self.positioner_axes[axis].stop()
        self.log.info('Positioner: Movement stopped!')
        return 0

    def get_pos(self, param_list=None):
        """ Gets current position of the stage arms

        @param list param_list: optional, if a specific position of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                position is asked.

        @return dict: with keys being the axis labels and item the current
                      position.
        """
        pos = {}
        if param_list is not None:
            for param in param_list:
                try:
                    axis = self.positioner_axes[param]
                    pos[axis.label] = axis.get_position()
                except KeyError:
                    self.log.warning('Inalid axes given!')
                    return -1
        else:
            for param in self.positioner_axes:
                axis = self.positioner_axes[param]
                pos[axis.label] = axis.get_position()

        return pos

    def get_status(self, param_list=None):
        """ Get the status of the position

        @param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        @return dict: with the axis label as key and the status number as item.
        """

        status = self._dev.get_full_info()
        return status


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
        return 0

    def get_velocity(self, param_list=None):
        """ Gets the current velocity for all connected axes.

        @param dict param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        @return dict : with the axis label as key and the velocity as item.
        """
        vel = {}
        if param_list is not None:
            for param in param_list:
                try:
                    axis = self.positioner_axes[param]
                    vel[axis.label] = axis.get_velocity()
                except KeyError:
                    self.log.warning('Inalid axes given!')
                    return -1
        else:
            for param in self.positioner_axes:
                axis = self.positioner_axes[param]
                vel[axis.label] = axis.get_velocity()

        return vel

    def set_velocity(self, param_dict=None):
        """ Write new value for velocity.

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <the-velocity-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.
        """
        constraints = self.get_constraints()

        for param in param_dict:
            try:
                axis = self.positioner_axes[param]
                desired_vel = param_dict[param]
                constr = constraints[param]
            except KeyError:
                self.log.warning('Invalid axes given!')
                return -1
            
            if not(constr['vel_min'] <= desired_vel <= constr['vel_max']):
                self.log.warning('Cannot make absolute movement of the axis '
                        '"{0}" to possition {1}, since it exceeds the limits '
                        '[{2},{3}] ! Command is ignored!'.format(
                            param, desired_vel,
                            constr['vel_min'],
                            constr['vel_max']))
            else:
                axis.set_velocity(desired_vel)
                axis.vel = desired_vel


    def _make_wait_after_movement(self):
        """ Define a time which the dummy should wait after each movement. """
        time.sleep(self._wait_after_movement)

