# -*- coding: utf-8 -*-
"""
Hardware file for the Superconducting Magnet (SCM)

QuDi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

QuDi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with QuDi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""


import socket
import serial
from core.module import Base
from core.configoption import ConfigOption
import numpy as np
from interface.magnet_interface import MagnetInterface
from collections import OrderedDict
import re
import itertools

class Magnet(Base, MagnetInterface):
    """ Magnet positioning software for superconducting magnet.

    Enables precise positioning of the magnetic field in spherical coordinates
    with the angle theta, phi and the radius rho.
    The superconducting magnet has three coils, one in x, y and z direction respectively.
    The current through these coils is used to compute theta, phi and rho.
    The alignment can be done manually as well as automatically via fluorescence alignment.

    Example config for copy-paste:

    sc_magnet:
        module.Class: 'sc_magnet.magnet.Magnet'
        magnet_port: 3000
        magnet_IP_address_x: 192.168.0.12
        magnet_IP_address_y: 129.69.46.186
        magnet_IP_address_z: 192.168.0.14
        magnet_waitingtime: 0.01 # in seconds
        magnet_x_constr: 1.0
        magnet_y_constr: 2.0
        magnet_z_constr: 3.0
        magnet_rho_constr: 1.2

    """
    # config opts
    port = ConfigOption('magnet_port', missing='error')

    addr_zx = ConfigOption('magnet_address_zx', missing='error')
    addr_y = ConfigOption('magnet_address_y', missing='error')

    # default waiting time of the pc after a message was sent to the magnet
    waitingtime = ConfigOption('magnet_waitingtime', 0.01)

    # Constraints of the superconducting magnet in T
    # Normally you should get and set constraints in the
    # function get_constraints(). The problem is here that
    # the constraint rho is no constant and is dependent on the
    # current theta and phi value.
    x_constr = ConfigOption('magnet_x_constr', 1e-3)
    y_constr = ConfigOption('magnet_y_constr', 1e-3)
    z_constr = ConfigOption('magnet_z_constr', 1e-3)
    rho_constr = ConfigOption('magnet_rho_constr', 1e-3)

    def __init__(self, **kwargs):
        """Here the connections to the power supplies and to the counter are established"""
        super().__init__(**kwargs)
        socket.setdefaulttimeout(1)
        try:
            self.soc_y = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.timeout:
            self.log.error("socket timeout for coil in y-direction")

        # This is saves in which interval the input theta was in the last movement
        self._inter = 1

        # this is a new thing. "normal_mode"
        # allows one to set magnetic fields up to 1 T along each axis
        # and the magnetic field vector can't be larger than 1.2 T
        # In z_mode you are allowed to move in a 5° solid angle along the z-axis
        # with a maximum field of 3 T.
        # For more documentation or how to change the mode look into
        # the function switch_mode
        self.mode = "normal_mode"

    def on_activate(self):
        """
        loads the config file and extracts the necessary configurations for the
        superconducting magnet

        @return int: (0: Ok, -1:error)
        """
        self.ser_zx = serial.Serial(port=self.addr_zx, baudrate=9600, bytesize=8, timeout=2, stopbits=serial.STOPBITS_ONE)
        self.soc_y.connect((self.addr_y, self.port))

        self.x_dir = 'ZERO'
        self.y_dir = 'ZERO'
        self.z_dir = 'ZERO'

        self.tell({'x':'REMOTE', 'y':'REMOTE', 'z':'REMOTE'})

#       sending a signal to all coils to receive an answer to cut off the
#       useless welcome message.
        ask_dict = {'x': "*IDN?", 'y': "*IDN?"}
        answ_dict = self.ask(ask_dict)
        self.log.info("Magnets: {0}".format(answ_dict))


    def on_deactivate(self):
        self.ser_zx.close()
        self.soc_y.close()

    def utf8_to_byte(self, myutf8):
        """
        Convenience function for code refactoring
        @param string myutf8 the message to be encoded
        @return the encoded message in bytes
        """
        return myutf8.encode('utf-8')

    def byte_to_utf8(self, mybytes):
        """
        Convenience function for code refactoring
        @param bytes mybytes the byte message to be decoded
        @return the decoded string in uni code
        """
        return mybytes.decode()

# =========================== Magnet Functionality Core ====================================

    def get_constraints(self):
        """ Retrieve the hardware constraints from the magnet driving device.

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
        possible keys in the constraint are defined in the interface file.
        If the hardware does not support the values for the constraints, then
        insert just None. If you are not sure about the meaning, look in other
        hardware files to get an impression.
        """
        constraints = OrderedDict()
        pos_dict = self.get_pos()
        coord_list = [pos_dict['rho'], pos_dict['theta'], pos_dict['phi']]
        pos_max_dict = self.rho_pos_max({'rad': coord_list})

        # get the constraints for the x axis:
        axis0 = {'label': self._x_axis.label,
                 'unit': 'T',
                 'ramp': ['Linear'],
                 'pos_min': -self.x_constr,
                 'pos_max': self.x_constr,
                 'pos_step': 0.001e-3,
                 'vel_min': 0,
                 'vel_max': 1e-3,
                 'vel_step': 0.01e-3,
                 'acc_min': 0.1e-3,
                 'acc_max': 0.0,
                 'acc_step': 0.0}

        axis1 = {'label': self._y_axis.label,
                 'unit': 'T',
                 'ramp': ['Linear'],
                 'pos_min': -self.y_constr,
                 'pos_max': self.y_constr,
                 'pos_step': 0.001e-3,
                 'vel_min': 0,
                 'vel_max': 1e-3,
                 'vel_step': 0.01e-3,
                 'acc_min': 0.1e-3,
                 'acc_max': 0.0,
                 'acc_step': 0.0}

        axis2 = {'label': self._z_axis.label,
                 'unit': 'T',
                 'ramp': ['Linear'],
                 'pos_min': -self.z_constr,
                 'pos_max': self.z_constr,
                 'pos_step': 0.001e-3,
                 'vel_min': 0,
                 'vel_max': 1e-3,
                 'vel_step': 0.01e-3,
                 'acc_min': 0.1e-3,
                 'acc_max': 0.0,
                 'acc_step': 0.0}

        axis3 = {'label': self._phi_axis.label,
                 'unit': 'rad',
                 'ramp': ['Sinus'],
                 'pos_min': 0,
                 'pos_max': 2*np.pi,
                 'pos_step': 2*np.pi/1000,
                 'vel_min': 0,
                 'vel_max': 1,
                 'vel_step': 1e-6,
                 'acc_min': None,
                 'acc_max': None,
                 'acc_step': None}
        
        axis4 = {'label': 'rho', 'unit': 'T', 'pos_min': 0, 'pos_max': self.rho_constr, 'pos_step': 1e-6,
                 'vel_min': 0, 'vel_max': 1, 'vel_step': 1e-6}

        # In fact position constraints for rho is dependent on theta and phi, which would need
        # the use of an additional function to calculate
        # going to change the return value to a function rho_max_pos which needs the current theta and
        # phi position
        # get the constraints for the x axis:
        axis5 = {'label': 'theta', 'unit': 'rad', 'pos_min': 0, 'pos_max': 2*np.pi, 'pos_step': 2*np.pi/1000, 'vel_min': 0,
                 'vel_max': 1, 'vel_step': 1e-6}

        # assign the parameter container for x to a name which will identify it

        # assign the parameter container for x to a name which will identify it
        constraints[axis0['label']] = axis0
        constraints[axis1['label']] = axis1
        constraints[axis2['label']] = axis2
        constraints[axis4['label']] = axis4
        constraints[axis5['label']] = axis5
        constraints[axis3['label']] = axis3

        return constraints

    def tell(self, param_dict):
        """Send a command string to the magnet.
        @param dict param_dict: has to have one of the following keys: 'x', 'y' or 'z'
                                      with an appropriate command for the magnet
        """
        internal_counter = 0
        self.log.debug(f'{param_dict}')
        if param_dict.get('x') is not None:
            if not param_dict['x'].endswith('\n'):
                param_dict['x'] += '\n'
            self.ser_zx.write(self.utf8_to_byte('CHAN 2\n'))
            self.ser_zx.readline().decode()
            self.ser_zx.write(self.utf8_to_byte(param_dict['x']))
            self.ser_zx.readline().decode()
            internal_counter += 1
        if param_dict.get('y') is not None:
            if not param_dict['y'].endswith('\n'):
                param_dict['y'] += '\n'
            self.soc_y.send(self.utf8_to_byte(param_dict['y']))
            internal_counter += 1
        if param_dict.get('z') is not None:
            if not param_dict['z'].endswith('\n'):
                param_dict['z'] += '\n'
            self.ser_zx.write(self.utf8_to_byte('CHAN 1\n'))
            self.ser_zx.readline().decode()
            self.ser_zx.write(self.utf8_to_byte(param_dict['z']))
            self.ser_zx.readline().decode()
            internal_counter += 1

        if internal_counter == 0:
            self.log.warning('no parameter_dict was given therefore the '
                    'function tell() call was useless')
            return -1
        else:
            return 0

    def ask(self, param_dict):
        """Asks the magnet a 'question' and returns an answer from it.
        @param dictionary param_dict: has to have one of the following keys: 'x', 'y' or 'z'
                                      the items have to be valid questions for the magnet.

        @return answer_dict: contains the same labels as the param_dict if it was set correct and the
                             corresponding items are the answers of the magnet (format is string), else
                             an empty dictionary is returned


        """

        answer_dict = {}
        if param_dict.get('x') is not None:
            if not param_dict['x'].endswith('\n'):
                param_dict['x'] += '\n'
                # repeat this block to get out crappy messages.
            self.ser_zx.write(self.utf8_to_byte('CHAN 2\n'))
            self.ser_zx.readline().decode()
            self.ser_zx.write(self.utf8_to_byte(param_dict['x']))
            self.ser_zx.readline().decode()
            # time.sleep(self.waitingtime)                   # you need to wait until magnet generating
            # an answer.
            answer_dict['x'] = self.byte_to_utf8(self.ser_zx.readline())  # receive an answer
            answer_dict['x'] = answer_dict['x'].replace('\r', '')
            answer_dict['x'] = answer_dict['x'].replace('\n', '')
        if param_dict.get('y') is not None:
            if not param_dict['y'].endswith('\n'):
                param_dict['y'] += '\n'
            self.soc_y.send(self.utf8_to_byte(param_dict['y']))
            # time.sleep(self.waitingtime)                   # you need to wait until magnet generating
            # an answer.
            answer_dict['y'] = self.byte_to_utf8(self.soc_y.recv(1024))  # receive an answer
            self.soc_y.send(self.utf8_to_byte(param_dict['y']))
            # time.sleep(self.waitingtime)                   # you need to wait until magnet generating
            # an answer.
            answer_dict['y'] = self.byte_to_utf8(self.soc_y.recv(1024))  # receive an answer
            answer_dict['y'] = answer_dict['y'].replace('\r', '')
            answer_dict['y'] = answer_dict['y'].replace('\n', '')
        if param_dict.get('z') is not None:
            if not param_dict['z'].endswith('\n'):
                param_dict['z'] += '\n'
            self.ser_zx.write(self.utf8_to_byte('CHAN 1\n'))
            self.ser_zx.readline().decode()
            self.ser_zx.write(self.utf8_to_byte(param_dict['z']))
            self.ser_zx.readline().decode()
            # time.sleep(self.waitingtime)                   # you need to wait until magnet generating
            # an answer.
            answer_dict['z'] = self.byte_to_utf8(self.ser_zx.readline())  # receive an answer
            answer_dict['z'] = answer_dict['z'].replace('\r', '')
            answer_dict['z'] = answer_dict['z'].replace('\n', '')

        if len(answer_dict) == 0:
            self.log.warning('no parameter_dict was given therefore the '
                             'function call ask() was useless')

        return answer_dict

    def get_status(self, param_list=None):
        """ Get the status of the position

        @param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        @return dict: with the axis label as key and the status number as item.
                      Possible states are { -1 : Error, 1: SCM doing something, 0: SCM doing nothing }
        """
        # I have chosen the numbers rather lightly and
        # an improvement is probably easily achieved.
        field_dict = self.get_current_field()
        if param_list is not None:
            status_plural = self.ask_status(param_list)
        else:
            status_plural = self.ask_status()
        status_dict = {}
        for axes in status_plural:
            curr_I = float(status_plural[axes][:-4])
            set_I = float(field_dict[axes][:-4])
            translated_status = 1 if np.isclose([curr_I],[set_I], atol=1e-4) else 0
            status_dict[axes] = translated_status

        return status_dict

    def target_field_setpoint(self, param_dict):
        """ Function to set the target field (in T), which will be reached through the
            function ramp(self, param_list).

            @param dict param_dict: Contains as keys the axes to be set e.g. 'x' or 'y'
            and the items are the float values for the new field generated by the coil of
            that axis.
            @return int: error code (0:OK, -1:error)
            """

        field_dict = self.get_current_field()
        old_dict = field_dict.copy()
        mode = self.mode

        if param_dict.get('x') is not None:
            field_dict['x'] = param_dict['x']
            unit = self.ask({'x':'UNIT?'})
            if 'G' not in unit['x']:
                self.log.warning('Check units of x axis!')
                return -1
        if param_dict.get('y') is not None:
            field_dict['y'] = param_dict['y']
            unit = self.ask({'y':'UNIT?'})
            if 'G' not in unit['y']:
                self.log.warning('Check units of y axis!')
                return -1
        if param_dict.get('z') is not None:
            field_dict['z'] = param_dict['z']
            unit = self.ask({'z':'UNIT?'})
            if 'G' not in unit['z']:
                self.log.warning('Check units of z axis!')
                return -1
        if param_dict.get('x') is None and param_dict.get('y') is None and param_dict.get('z') is None:
            self.log.warning('no valid axis was supplied in '
                    'target_field_setpoint')
            return -1

        new_coord = [field_dict['x'], field_dict['y'], field_dict['z']]
        check_var = self.check_constraints({mode: {'cart': new_coord}})
        if np.sqrt(new_coord[0]**2 + new_coord[1]**2 + new_coord[2]**2)>self.rho_constr: #T
            return -1
        # to kG
        param_dict = {i:param_dict[i]*10 for i in param_dict.keys()}

        if check_var:
            self.log.info(f'Setting: {param_dict}')
            if param_dict.get('x') is not None:
                lim = 'U' if old_dict['x']<field_dict['x'] else 'L'
                self.x_dir = 'UP' if lim=='U' else 'DOWN'
                cmd = self.utf8_to_byte(f"{lim}LIM " + str(param_dict['x']) + "\n")
                self.tell({'x':f'{cmd}'})
            if param_dict.get('y') is not None:
                lim = 'U' if old_dict['y']<field_dict['y'] else 'L'
                self.y_dir = 'UP' if lim=='U' else 'DOWN'
                cmd = self.utf8_to_byte(f"{lim}LIM " + str(param_dict['y']) + "\n")
                self.tell({'y':f'{cmd}'})
            if param_dict.get('z') is not None:
                lim = 'U' if old_dict['z']<field_dict['z'] else 'L'
                self.z_dir = 'UP' if lim=='U' else 'DOWN'
                cmd = self.utf8_to_byte(f"{lim}LIM " + str(param_dict['z']) + "\n")
                self.tell({'z':f'{cmd}'})

        else:
            self.log.warning('resulting field would be too high in '
                    'target_field_setpoint')
            return -1

        return 0

    def ramp(self, param_list=None):
        """ function to ramp the magnetic field in the direction(s)  to the target field values

            @param list param_list: This param is optional. If supplied it has to
            contain the labels for the axes, which should be ramped (only cartesian makes sense here),
            else all axes will be ramped.
            @return int: error code (0:OK, -1:error)
            """

        self.log.info(f'Ramping...')
        self.x_dir = 'ZERO'
        self.y_dir = 'ZERO'
        self.z_dir = 'ZERO'
        self.tell({'x':f'SWEEP {self.x_dir}', 'y':f'SWEEP {self.y_dir}', 'z':f'SWEEP {self.z_dir}'})

        return 0

    def ramp_to_zero(self, axis):
        """ Function to ramp down a specific coil to zero current

            @param axis: string axis: (allowed inputs 'x', 'y' and 'z')
            """

        self.tell({f'{axis}':'SWEEP ZERO'})

    def calibrate(self, param_list=None):
        """ Calibrates the stage. In the case of the super conducting magnet
            this just means moving all or a user specified coil to zero magnetic field.

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
        if not param_list:
            self.ramp_to_zero("x")
            self.ramp_to_zero("y")
            self.ramp_to_zero("z")
        else:
            if 'x' in param_list:
                self.ramp_to_zero("x")
            elif 'y' in param_list:
                self.ramp_to_zero("y")
            elif 'z' in param_list:
                self.ramp_to_zero("z")
            else:
                self.log.error('no valid axis was supplied')
                return -1

        return 0

    def set_coordinates(self, param_dict):
        """
        Function to set spherical coordinates ( keep in mind all is in radians)
        This function is intended to replace the old set functions ( set_magnitude,
        set_theta, set_phi ).

        @param dict param_dict: dictionary, which passes all the relevant
                                field values, that should be passed. Usage:
                                {'axis_label': <the-abs-pos-value>}.
                                'axis_label' must correspond to a label given
                                to one of the axis. In this case the axes are
                                labeled 'rho', 'theta' and 'phi'

        @return int: error code (0:OK, -1:error)
        """

        answ_dict = {}
        coord_list = []
        transform_dict = {'cart': {'rad': coord_list}}
        answ_dict = self.get_current_field()
        coord_list.append(answ_dict['x'])
        coord_list.append(answ_dict['y'])
        coord_list.append(answ_dict['z'])

        coord_list = self.transform_coordinates(transform_dict)
        label_list = ['rho', 'theta', 'phi']

        if param_dict.get('rho') is not None:
            coord_list[0] = param_dict['rho']
        if param_dict.get('theta') is not None:
            coord_list[1] = param_dict['theta']
        if param_dict.get('phi') is not None:
            coord_list[2] = param_dict['phi']
        for key in param_dict.keys():
                if key not in label_list:
                    self.log.warning("The key "+key+" provided is no valid key in set_coordinates.")
                    return -1

        transform_dict = {'rad': {'cart': coord_list}}
        coord_list = self.transform_coordinates(transform_dict)
        set_point_dict = {'x': coord_list[0], 'y': coord_list[1],
                          'z': coord_list[2]}

        check_val = self.target_field_setpoint(set_point_dict)

        return check_val

    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement)

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, that should be changed. Usage:
                                {'axis_label': <the-abs-pos-value>}.
                                'axis_label' must correspond to a label given
                                to one of the axis. In this case the axes are
                                labeled 'rho', 'theta' and 'phi'.

        @return int: error code (0:OK, -1:error)
        """

        # the problem here is, that check_coordinates needs a complete dictionary with all
        # labels while move_abs doesn't need it. I think it is better to extend this flexibility to
        # check_constraints than changing move_abs.

        coord_list = []
        mode = self.mode

        param_dict = self.update_coordinates(param_dict)
        coord_list.append(param_dict['rho'])
        coord_list.append(param_dict['theta'])
        coord_list.append(param_dict['phi'])

        # # lets adjust theta
        # theta = param_dict['theta']
        # phi = param_dict['phi']

        # # switch variable decides what has to be done ( in intervals [2*k*np.pi, 2k+1*np.pi] the movement would
        # # be ok ( no rotation in phi ). In the other intervals one has to see if there was a movement before this
        # # movement in one of these regions or not. If not just move, if there was shift to the interval [0, np.pi] and
        # # move there.
        # switch = np.ceil(theta / np.pi) % 2
        # inter1 = np.ceil(theta / np.pi)
        # inter1 = int(inter1)
        # # if inter1 > 0:
        # #     inter1 -= 1
        # # move the theta values in the right range
        # # for the constraints

        # # if in an even interval
        # if switch:
        #     theta -= np.pi * (inter1 - 1)
        # else:
        #     # get into the correct interval
        #     theta -= np.pi * (inter1 - 1)
        #     # now mirror at the center of the interval
        #     theta = np.pi/2 - (theta - np.pi/2)
        # # interval was correct
        # if switch:
        #     self._inter = inter1
        # # interval that needs rotation around z-axis in case it wasn't outside that interval before
        # else:
        #     # actually it isn't necessary to distinguish here. I initially thought it is necessary and it would
        #     # be if one would move the magnet based on the magnet field of previous values.
        #     # I will leave the code here for now, when somebody in the future wants to extend this function
        #     # to allow both behaviors he can use the existing code.
        #     # theta was in a correct interval before but isn't now ( change of interval )
        #     self.log.debug('need rotation around phi to adjust for negative theta value')
        #     self.log.debug('old int: {0}, new int: {1}'.format(self._inter, inter1))
        #     if int(np.abs(self._inter - inter1)) is 1:
        #         phi += np.pi

        #     # theta wasn't in a correct interval before and is still in the same interval ( in this case do nothing )
        #     elif int(np.abs(self._inter - inter1)) is 0:
        #         phi += np.pi

        #     else:
        #         self.log.warning("There was a difference in intervals larger "
        #                          "than one between two consecutive movements. This is not supported "
        #                          "yet.{0}".format(self._inter - inter1))
        #     self._inter = inter1

        # # adjust the phi values so they are in the right interval. They might be in the wrong interval
        # # due to user input or theta values
        # inter2 = np.ceil(phi / (2 * np.pi))
        # inter2 = int(inter2)
        # # if inter2 > 0:
        # #     inter2 -= 1

        # phi -= 2 * np.pi * (inter2 - 1)

        # self.log.debug('show old dictionary: {0}'.format(param_dict))
        # # set the corrected values
        # param_dict['theta'] = theta
        # param_dict['phi'] = phi
        constr_dict = {mode: {'rad': coord_list}}
        self.log.debug('show new dictionary: {0}'.format(param_dict))
        check_bool = self.check_constraints(constr_dict)
        if check_bool:
            check_1 = self.set_coordinates(param_dict)
            check_2 = self.ramp()
        else:
            self.log.warning("move_abs hasn't done anything, see check_constraints message why")
            return -1

        if check_1 is check_2:
            if check_1 is 0:
                return 0
        else:
            return -1

    def move_rel(self, param_dict):
        """ Moves stage in given direction (in spheric coordinates with theta and
            phi in radian)

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                {'axis_label': <the-abs-pos-value>}.
                                'axis_label' must correspond to a label given
                                to one of the axis.

        @return int: error code (0:OK, -1:error)
        """

        coord_list = []

        answ_dict = self.get_current_field()

        coord_list.append(answ_dict['x'])
        coord_list.append(answ_dict['y'])
        coord_list.append(answ_dict['z'])

        transform_dict = {'cart': {'rad': coord_list}}

        coord_list = self.transform_coordinates(transform_dict)
        label_list = ['rho', 'theta', 'phi']
        if param_dict.get('rho') is not None:
            coord_list[0] += param_dict['rho']
        if param_dict.get('theta') is not None:
            coord_list[1] += param_dict['theta']
        if param_dict.get('phi') is not None:
            coord_list[2] += param_dict['phi']

        for key in param_dict.keys():
            if key not in label_list:
                self.log.warning("The key "+key+" provided is no valid key in set_coordinates.")
                return -1
        new_coord_dict = {'rho': coord_list[0], 'theta': coord_list[1],
                          'phi': coord_list[2]}
        check_val = self.move_abs(new_coord_dict)
        return check_val

    def transform_coordinates(self, param_dict):
        """ Function for generic coordinate transformation.
            This is a refactoring to the old functions (4) to be
            replaced by just one function
            @param dict param_dict: contains a param_dict, which contains
            a list of values to be transformed. The transformation depends
            on the keys of the first and the second dictionary.
            Possible keys are: "deg", "rad", "cart"
            for example if the first key is deg and the second is cartesian
            then the values in the list will be transformed from deg to
            cartesian.

            Ordering of the values should be [x,y,z] (cartesian)
            or [rho, theta, phi] for deg or rad
            @return list containing the transformed values
        """

        # here all the possible cases for transformations
        # are checked
        if param_dict.get('deg') is not None:
            if param_dict['deg'].get('rad') is not None:
                try:
                    rho, theta, phi = param_dict['deg'].get('rad')
                except ValueError:
                    self.log.error('Supplied input list for transform_coordinates has to be of length 3: returning initial values')
                    return [-1, -1, -1]

                theta = theta*np.pi/180
                phi = phi*np.pi/180
                return_list = [rho, theta, phi]
                return return_list

            if param_dict['deg'].get('cart') is not None:
                cartesian_list = []
                try:
                    rho, theta, phi = param_dict['deg'].get('cart')
                except ValueError:
                    self.log.error('Supplied input list for transform_coordinates has to be of length 3: returning [-1,-1,-1]')
                    return [-1, -1, -1]
            # transformations that should probably be revisited.
            # They are there in case the theta and phi values
            # are not in the correct range.
                while theta >= 180:
                    phi += 180
                    theta = 360 - theta

                while theta < 0:
                    theta = -theta
                    phi += 180

                while phi >= 360:
                    phi += 360

                while phi < 0:
                    phi += 360

                cartesian_list.append(rho * np.sin(theta * 2 * np.pi / 360)
                                      * np.cos(phi * 2 * np.pi / 360))
                cartesian_list.append(rho * np.sin(theta * 2 * np.pi / 360)
                                      * np.sin(phi * 2 * np.pi / 360))
                cartesian_list.append(rho * np.cos(theta * 2 * np.pi / 360))

                return cartesian_list
        if param_dict.get('rad') is not None:
            if param_dict['rad'].get('deg') is not None:
                try:
                    rho, theta, phi = param_dict['rad']['deg']
                except ValueError:
                    self.log.error("Supplied input list for transform_coordinates has to be of length 3: returning [-1, -1, -1]")
                    return [-1,-1,-1]
                theta = 180*theta/np.pi
                phi = 180*phi/np.pi
                return_list = [rho, theta, phi]
                return return_list
            if param_dict['rad'].get('cart') is not None:
                try:
                    rho, theta, phi = param_dict['rad']['cart']
                except ValueError:
                    self.log.error("Supplied input list for transf has to be of length 3: returning [-1, -1, -1]")
                    return [-1,-1,-1]
                x_val = rho * np.sin(theta) * np.cos(phi)
                y_val = rho * np.sin(theta) * np.sin(phi)
                z_val = rho * np.cos(theta)
                return_list = [x_val, y_val, z_val]
                return return_list

        if param_dict.get('cart') is not None:
            if param_dict['cart'].get('deg') is not None:
                try:
                    x_val, y_val, z_val = param_dict['cart']['deg']
                except ValueError:
                    self.log.error("Supplied input list for transform_coordinates has to be of length 3: returning [-1, -1, -1]")
                    return [-1,-1,-1]
                rho = np.sqrt(x_val ** 2 + y_val ** 2 + z_val ** 2)
                if rho == 0:
                    theta = 0
                else:
                    theta = np.arccos(z_val/rho) * 360/(2 * np.pi)
                if x_val == 0 and y_val == 0:
                    phi = 0
                else:
                    phi = np.arctan2(y_val, x_val) * 360/(2 * np.pi)
                if phi < 0:
                    phi += 360
                return_list = [rho, theta, phi]
                return return_list

            if param_dict['cart'].get('rad') is not None:
                try:
                    x_val, y_val, z_val = param_dict['cart']['rad']
                except ValueError:
                    self.log.error("Supplied input list for transform_coordinates has to be of length 3: returning [-1, -1, -1]")
                    return [-1,-1,-1]
                rho = np.sqrt(x_val ** 2 + y_val ** 2 + z_val ** 2)
                if rho == 0:
                    theta = 0
                else:
                    theta = np.arccos(z_val/rho)

                if x_val == 0 and y_val == 0:
                    phi = 0
                else:
                    phi = np.arctan2(y_val, x_val)
                if phi < 0:
                    phi += 2 * np.pi
                return_list = [rho, theta, phi]
                return return_list

    def get_current_field(self):
        """ Function that asks the magnet for the current field strength in each direction

            @param:

            @param x : representing the field strength in x direction
            @param y : representing the field strength in y direction
                          float z : representing the field strength in z direction

            """
        ask_dict = {'x': "IOUT?\n", 'y': "IOUT?\n", 'z': "IOUT?\n"}
        answ_dict = self.ask(ask_dict)
        # having always a weird bug, where the response of the magnet
        # doesn't make sense, as it is always the same way I try to
        # catch these exceptions.

        # pattern to recognize decimal numbers ( There is one issue here e.g. (0.01940.01345) gives one match
        # with 0.01940. Don't think it will matter much.)

        my_pattern = re.compile('[-+]?[0-9][.][0-9]+')
        try:
            answ_dict['x'] = float(answ_dict['x'][:-4])/10
        except ValueError:
            match_list = re.findall(my_pattern, answ_dict['x'])
            answ_dict['x'] = float(match_list[0])
        try:
            answ_dict['y'] = float(answ_dict['y'][:-4])/10
        except ValueError:
            match_list = re.findall(my_pattern, answ_dict['y'])
            answ_dict['y'] = float(match_list[0])
        try:
            answ_dict['z'] = float(answ_dict['z'][:-4])/10
        except ValueError:
            match_list = re.findall(my_pattern, answ_dict['z'])
            answ_dict['z'] = float(match_list[0])

        return answ_dict

    def get_pos(self, param_list=None):
        """ Gets current position of the stage

        @param list param_list: optional, if a specific position of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                position is asked.

        @return dict mypos: with keys being the axis labels and item the current
                      position. Given in spheric coordinates with Units T, rad , rad.
        """




        mypos = {}
        mypos1 = {}

        answ_dict = self.get_current_field()
        coord_list = [answ_dict['x'], answ_dict['y'], answ_dict['z']]
        rho, theta, phi = self.transform_coordinates({'cart': {'rad': coord_list}})
        mypos1['rho'] = rho
        mypos1['theta'] = theta
        mypos1['phi'] = phi
        mypos1['x'] = answ_dict['x']
        mypos1['y'] = answ_dict['y']
        mypos1['z'] = answ_dict['z']

        mypos2['rho'] = rho
        mypos2['theta'] = theta
        mypos2['phi'] = phi

        if param_list is None:
            return mypos2

        else:
            return {i:mypos1[i] for i in param_list}

    def stop_hard(self, param_list=None):
        """ function that pauses the heating of a specific coil depending on
            the elements in param_list.

            @param list param_list: Can contain elements 'x', 'y' or 'z'. In the case no list is supplied the heating
            of all coils is stopped
            @return integer: 0 everything is ok and -1 an error occured.
            """
        if not param_list:
            ret = self.tell({'x':'SWEEP PAUSE', 'y':'SWEEP PAUSE', 'z':'SWEEP PAUSE'})
        else:
            for i in param_list:
                ret = self.tell({f'{i}':'SWEEP PAUSE'})

        return ret

    def abort(self):
        """ Stops movement of the stage

        @return int: error code (0:OK, -1:error)
        """
        # could think about possible exceptions here and
        # catch them and return -1 in case
        ab = self.stop_hard()

        return ab

    def ask_status(self, param_list = None):
        """ Function that returns the status of the coils ('x','y' and 'z') given in the
            param_dict

            @param list param_list: string (elements allowed  'x', 'y' and 'z')
            for which the status should be returned. Can be None, then
            the answer is the same as for the list ['x','y','z'].

            @return state: returns a string, which contains the number '1' to '10' representing
            the state, the magnet is in.

            For further information on the meaning of the numbers see
            translated_get_status()
            """
        ask_dict = {}

        if not param_list:
            ask_dict['x'] = "IOUT?\n"
            ask_dict['y'] = "IOUT?\n"
            ask_dict['z'] = "IOUT?\n"
        else:
            for axis in param_list:
                ask_dict[axis] = "IOUT?\n"

        answer_dict = self.ask(ask_dict)

        return answer_dict

    def translated_get_status(self, param_list=None):
        """ Just a translation of the numbers according to the
            manual supplied by American Magnets, Inc.

            @param list param_list: string (elements allowed  'x', 'y' and 'z')
            for which the translated status should be returned. Can be None, then
            the answer is the same as for the list ['x','y','z']

            @return dictionary status_dict: keys are the elements of param_list and the items contain the
            message for the user.
            """
        status_dict = self.ask_status(param_list)

        for myiter in status_dict.keys():
            stateval = status_dict[myiter]

            try:
                if int(stateval) > 10:
                    stateval = int(stateval)
                    while stateval > 10:
                        stateval //= 10
                    stateval = str(stateval)

                if stateval == '1':
                    translated_status = 'RAMPING to target field/current'
                elif stateval == '2':
                    translated_status = 'HOLDING at the target field/current'
                elif stateval == '3':
                    translated_status = 'PAUSED'
                elif stateval == '4':
                    translated_status = 'Ramping in MANUAL UP mode'
                elif stateval == '5':
                    translated_status = 'Ramping in MANUAL DOWN mode'
                elif stateval == '6':
                    translated_status = 'ZEROING CURRENT (in progress)'
                elif stateval == '7':
                    translated_status = 'Quench detected'
                elif stateval == '8':
                    translated_status = 'At ZERO current'
                elif stateval == '9':
                    translated_status = 'Heating persistent switch'
                elif stateval == '10':
                    translated_status = 'Cooling persistent switch'
                else:
                    self.log.warning('Something went wrong in ask_status as the statevalue was not between 1 and 10!')
                    return -1
            except ValueError:
                self.log.warning("Sometimes the magnet returns nonsense after a request")
                return -1
            status_dict[myiter] = translated_status

        return status_dict

    # This first version of set and get velocity will be very simple
    # Normally one can set up several ramping rates for different field
    # regions and so on. I also leave it to the user to find out how many
    # segments he has and so on. If nothing is changed the magnet should have
    # 1 segment and max_val should be the max_val that can be reached in that
    # direction.

    def set_velocity(self, param_dict):
        """ Function to change the ramp rate  in T/s (ampere per second)
            @param dict: contains as keys the different cartesian axes ('x', 'y', 'z')
                         and the dict contains list of parameters, that have to be supplied.
                         In this case this is segment, ramp_rate and maxval.
                         How does this work? The maxval for the current marks the endpoint
                         and in between you have several segments with differen ramp_rates.

            @return int: error code (0:OK, -1:error)

            """
        return -1
        tell_dict = {}
        return_val = 0
        internal_counter = 0
        constraint_dict = self.get_constraints()

        if param_dict.get('x') is not None:
            param_list = list()
            param_list.append(1)  # the segment
            param_list.append(param_dict['x'])
            param_list.append(1)  # the upper bound of the velocity

            constraint_x = constraint_dict['rho']['vel_max']
            if constraint_x > param_list[1]:
                # tell_dict['x'] = 'CONF:RAMP:RATE:FIELD:' + str(param_list[0]) + ", " + str(param_list[1]) + ", " + str(param_list[2])
                pass
            else:
                self.log.warning("constraint vel_max was violated in set_velocity with axis = 'x'")

            internal_counter += 1

        if param_dict.get('y') is not None:
            param_list = list()
            param_list.append(1)  # the segment
            param_list.append(param_dict['y'])
            param_list.append(1)  # the upper bound of the velocity

            constraint_y = constraint_dict['theta']['vel_max']
            if constraint_y > param_list[1]:
                # tell_dict['y'] = 'CONF:RAMP:RATE:FIELD:' + str(param_list[0]) + ", " + str(param_list[1]) + ", " + str(param_list[2])
                pass
            else:
                self.log.warning("constraint vel_max was violated in set_velocity with axis = 'y'")
            internal_counter += 1

        if param_dict.get('z') is not None:
            param_list = list()
            param_list.append(1)  # the segment
            param_list.append(param_dict['z'])
            param_list.append(3)  # the upper bound of the velocity

            constraint_z = constraint_dict['phi']['vel_max']
            if constraint_z > param_list[1]:
                # tell_dict['z'] = 'CONF:RAMP:RATE:FIELD:' + str(param_list[0]) + ", " + str(param_list[1]) + ", " + str(param_list[2])
                pass
            else:
                self.log.warning("constraint vel_max was violated in set_velocity with axis = 'z'")
            internal_counter += 1

        if internal_counter > 0:
            # self.tell(tell_dict)
            pass
        else:
            self.log.warning('There was no statement supplied in change_ramp_rate')
            return_val = -1

        return return_val

    def get_velocity(self, param_list=None):
        """ Gets the current velocity for all connected axes.

        @param dict param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        @return dict: with the axis label as key and the velocity as item.
        """
        ask_dict = {}
        return_dict = {}

        if param_list is None:
            ask_dict['x'] = "RATE? 0"
            ask_dict['y'] = "RATE? 0"
            ask_dict['z'] = "RATE? 0"
            answ_dict = self.ask(ask_dict)
            return_dict['x'] = float(answ_dict['x'][:-2])
            return_dict['y'] = float(answ_dict['y'][:-2])
            return_dict['z'] = float(answ_dict['z'][:-2])
        else:
            for axis in param_list:
                ask_dict[axis] = "RATE? 0"
            answ_dict = self.ask(ask_dict)
            for axis in param_list:
                return_dict[axis] = float(answ_dict[axis][:-2])

        return return_dict

    def check_constraints(self, param_dict):
        """
        Function that verifies if for a given configuration of field strength exerted through the coils
        the constraints of the magnet are violated.

        @param dictionary param_dict: the structure of the dictionary is as follows {'z_mode': {'cart': [a,b,c]}}
        with available keys 'z_mode' and 'normal_mode'. The dictionary inside the dictionary can contain the label
        'deg', 'cart' and 'rad'. The list contains then the new values and checks the
        constraints for them. z_mode means you can reach fields of 3 T in z-direction as long as the field vector
        is directed in z-direction within an accuracy of 5°. In this mode you should still be careful and the
        5° restriction is kind of arbitrary and not experimented with.
        @return: boolean check_var: True if the constraints are fulfilled and False otherwise
        """
        # First going to include a local function to check the constraints for cartesian coordinates
        # This helps to just reuse this function for the check of 'deg' and 'rad' cases.

        def check_cart_constraints(coord_list, mode):

            my_boolean = True
            try:
                x_val, y_val, z_val = coord_list
            except ValueError:
                self.log.error("In check_constraints list has not the right amount of elements (3).")
                return [-1, -1, -1]
            if mode == "normal_mode":
                if np.abs(x_val) > self.x_constr:
                    my_boolean = False

                if np.abs(y_val) > self.y_constr:
                    my_boolean = False

                if np.abs(z_val) > self.x_constr:

                    my_boolean = False

                field_magnitude = np.sqrt(x_val**2 + y_val**2 + z_val**2)
                if field_magnitude > self.rho_constr:
                    my_boolean = False
                
                def check_trans_field_magnitude(coord_list):
                    curr_field = self.get_current_field()
                    field_arr = np.array([coord_list,[curr_field['x'],curr_field['y'],curr_field['z']]]).T
                    cart_prod = itertools.product(*field_arr)
                    flag = False
                    for possibility in cart_prod:
                        if np.sqrt(possibility[0]**2 + possibility[1]**2 + possibility[2]**2) > self.rho_constr:
                            flag = True
                    return flag

                trans_field_magnitude_large = check_trans_field_magnitude(coord_list)
                if trans_field_magnitude_large:
                    self.log.warning('Vector magnitude may exceed constraint in transition from curr. field to setpoint!')
                    my_boolean = False

            elif mode == "z_mode":
                # Either in sphere on top of the cone
                # or in cone itself.
                my_boolean = False
                # angle 5° cone
                # 3T * cos(5°)
                height_cone = 2.9886

                if (np.abs(z_val) <= height_cone) and ((x_val**2 + y_val**2) <= z_val**2):
                    my_boolean = True
                elif x_val**2 + y_val**2 + (z_val - height_cone)**2 <= self.rho_constr:
                    my_boolean = True
                elif x_val**2 + y_val**2 + (z_val + height_cone)**2 <= self.rho_constr:
                    my_boolean = True

                if not my_boolean:
                    self.log.warning("In check_constraints your settings don't lie in the allowed cone. See the "
                                "function for more information")
            return my_boolean

        return_val = False


        if param_dict.get('normal_mode') is not None:
            if param_dict['normal_mode'].get("cart") is not None:
                return_val = check_cart_constraints(param_dict['normal_mode']["cart"], 'normal_mode')
            if param_dict['normal_mode'].get("rad") is not None:
                transform_dict = {'rad': {'cart': param_dict['normal_mode']["rad"]}}
                cart_coord = self.transform_coordinates(transform_dict)
                return_val = check_cart_constraints(cart_coord, 'normal_mode')

            # ok degree mode here won't work properly, because I don't check the move constraints
            if param_dict['normal_mode'].get("deg") is not None:
                transform_dict = {'deg': {'cart': param_dict['normal_mode']["deg"]}}
                cart_coord = self.transform_coordinates(transform_dict)
                return_val = check_cart_constraints(cart_coord, 'normal_mode')

        elif param_dict.get('z_mode') is not None:
            if param_dict['z_mode'].get("cart") is not None:
                return_val = check_cart_constraints(param_dict['z_mode']["cart"], 'z_mode')

            if param_dict['z_mode'].get("rad") is not None:
                transform_dict = {'rad':{'cart': param_dict['z_mode']["rad"]}}
                cart_coord = self.transform_coordinates(transform_dict)
                return_val = check_cart_constraints(cart_coord, 'z_mode')

            if param_dict['z_mode'].get("deg") is not None:
                transform_dict = {'deg': {'cart': param_dict['z_mode']["deg"]}}
                cart_coord = self.transform_coordinates(transform_dict)
                return_val = check_cart_constraints(cart_coord, 'z_mode')
        else:
            self.log.warning("no valid key was provided, therefore nothing happened in function check_constraints.")
        return return_val

    def rho_pos_max(self, param_dict):
        """
        Function that calculates the constraint for rho either given theta and phi values in degree
        or x, y and z in cartesian coordinates.

        @param dictionary param_dict: Has to be of the form {'rad': [rho, theta, phi]} supports also 'deg' and 'cart'
                                      option.

        @return float pos_max: the max position for given theta and phi values. Returns -1 in case of failure.
        """
        # so I'm going to rework this function. The answer in the case
        # of z_mode is easy. (Max value for r is constant 3 True)
        # For the "normal_mode" I decided to come up with a new
        # algorithm.
        # That algorithm can be summarized as follows:
        # Check if the vector  (r,theta,phi)
        # with length so that it is on the surface of the sphere. In case it conflicts with the
        # rectangular constraints given by the coils itself (x<=10, y<=10, z<=10)
        # we need to find the
        # intersection between the vector and the cube (Sadly this will need
        # 6 cases, just like a dice), else we are finished.
        pos_max_dict = {'rho': -1, 'theta': -1, 'phi': 2 * np.pi}
        param_dict = {self.mode: param_dict}

        if param_dict.get("z_mode") is not None:
            pos_max_dict['theta'] = np.pi*5/180  # 5° cone
            if self.check_constraints(param_dict):
                pos_max_dict['rho'] = self.z_constr
            else:
                pos_max_dict['rho'] = 0.0
        elif param_dict.get("normal_mode") is not None:
            pos_max_dict['theta'] = np.pi
            if param_dict["normal_mode"].get("cart") is not None:
                transform_dict = {'cart': {'rad': param_dict["normal_mode"].get("cart")}}
                coord_dict_rad = self.transform_coordinates(transform_dict)
                coord_dict_rad = {'rad': coord_dict_rad}
                coord_dict_rad['rad'][0] = self.rho_constr
                transform_dict = {'rad': {'cart': coord_dict_rad['rad']}}
                coord_dict_cart = self.transform_coordinates(transform_dict)
                coord_dict_cart = {'normal_mode': {'cart': coord_dict_cart}}


            elif param_dict["normal_mode"].get("rad") is not None:
                # getting the coord list and transforming the coordinates to
                # cartesian, so cart_constraints can make use of it
                # setting the radial coordinate, as only the angular coordinates
                # are of importance and e.g. a zero in the radial component would be
                # To set it to rho_constr is also important, as it allows a check
                # if the sphere is the valid constraint in the current direction.
                coord_list = param_dict["normal_mode"]["rad"]
                coord_dict_rad = param_dict["normal_mode"]
                coord_dict_rad['rad'][0] = self.rho_constr
                transform_dict = {'rad': {'cart': coord_dict_rad['rad']}}
                coord_dict_cart = self.transform_coordinates(transform_dict)
                coord_dict_cart = {'normal_mode': {'cart': coord_dict_cart}}

            elif param_dict["normal_mode"].get("deg") is not None:
                coord_list = param_dict["normal_mode"]["deg"]
                coord_dict_deg = param_dict["normal_mode"]
                coord_dict_deg['deg'][0] = self.rho_constr
                coord_dict_rad = self.transform_coordinates({'deg': {'rad': coord_dict_deg['deg']}})
                coord_dict_rad = {'rad': coord_dict_rad}
                transform_dict = {'rad': {'cart': coord_dict_rad['rad']}}
                coord_dict_cart = self.transform_coordinates(transform_dict)
                coord_dict_cart = {'normal_mode': {'cart': coord_dict_cart}}

            my_boolean = self.check_constraints(coord_dict_cart)

            if my_boolean:
                pos_max_dict['rho'] = self.rho_constr
            else:
                    # now I need to find out, which plane I need to check
                phi = coord_dict_rad['rad'][2]
                theta = coord_dict_rad['rad'][1]
                # Sides of the rectangular intersecting with position vector
                if (np.pi/4 <= theta) and (theta < np.pi - np.pi/4):
                    if (7*np.pi/4 < phi < 2*np.pi) or (0 <= phi <= np.pi/4):
                        pos_max_dict['rho'] = self.x_constr/(np.cos(phi)*np.sin(theta))
                    elif (np.pi/4 < phi) and (phi <= 3*np.pi/4):
                        pos_max_dict['rho'] = self.y_constr / (np.sin(phi)*np.sin(theta))
                    elif (3*np.pi/4 < phi) and (phi <= 5*np.pi/4):
                        pos_max_dict['rho'] = -self.x_constr/(np.cos(phi)*np.sin(theta))
                    elif (5*np.pi/4 < phi) and (phi <= 7*np.pi/4):
                        pos_max_dict['rho'] = -self.y_constr / (np.sin(phi)*np.sin(theta))
                    # Top and bottom of the rectangular
                elif (0 <= theta) and (theta < np.pi/4):
                    pos_max_dict['rho'] = self.x_constr / np.cos(theta)
                elif (3*np.pi/4 <= theta) and (theta <= np.pi):
                    pos_max_dict['rho'] = - self.x_constr / np.cos(theta)
        return pos_max_dict

    def update_coordinates(self, param_dict):
        """
        A small helper function that does make the functions set_coordinates, transform_coordinates compatible
        with the interface defined functions. The problem is, that in the interface functions each coordinate
        is item to an key which represents the axes of the current coordinate system. This function only
        makes the set of coordinates complete. E.g {'rho': 1.3} to {'rho': 1.3, 'theta': np.pi/2, 'phi': 0 }

        @param param_dict:  Contains the incomplete dictionary
        @return: the complete dictionary
        """
        current_coord_dict = self.get_pos()

        for key in current_coord_dict.keys():
            if param_dict.get(key) is None:
                param_dict[key] = current_coord_dict[key]

        return param_dict


    def set_magnet_idle_state(self, magnet_idle=True):
        """ Set the magnet to couple/decouple to/from the control.

        @param bool magnet_idle: if True then magnet will be set to idle and
                                 each movement command will be ignored from the
                                 hardware file. If False the magnet will react
                                 on movement changes of any kind.

        @return bool: the actual state which was set in the magnet hardware.
                        True = idle, decoupled from control
                        False = Not Idle, coupled to control
        """
        pass


    def get_magnet_idle_state(self):
        """ Retrieve the current state of the magnet, whether it is idle or not.

        @return bool: the actual state which was set in the magnet hardware.
                        True = idle, decoupled from control
                        False = Not Idle, coupled to control
        """
        pass
