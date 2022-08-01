# -*- coding: utf-8 -*-

"""
This file contains the general logic for magnet control.

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

import datetime
import numpy as np
import time

from collections import OrderedDict
from core.connector import Connector
from core.statusvariable import StatusVar
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from interface.slow_counter_interface import CountingMode
import matplotlib as mpl
import matplotlib.pyplot as plt


class MagnetLogic(GenericLogic):
    """ A general magnet logic to control an magnetic stage with an arbitrary
        set of axis.

    DISCLAIMER:
    ===========

    The current status of the magnet logic is highly experimental and not well
    tested. The implementation has some considerable imperfections. The state of
    this module is considered to be UNSTABLE.

    This module has two major issues:
        - a lack of proper documentation of all the methods
        - usage of tasks is not implemented and therefore direct connection to
          all the modules is used (I tried to compress as good as possible all
          the part, where access to other modules occurs so that a later
          replacement would be easier and one does not have to search throughout
          the whole file.)

    However, the 'high-level state maschine' for the alignment should be rather
    general and very powerful to use. The different state were divided in
    several consecutive methods, where each method can be implemented
    separately and can be extended for custom needs. (I have drawn a diagram,
    which is much more telling then the documentation I can write down here.)

    I am currently working on that and will from time to time improve the status
    of this module. So if you want to use it, be aware that there might appear
    drastic changes.

    ---
    """

    # declare connectors
    magnetstage = Connector(interface='MagnetInterface')
    counterlogic = Connector(interface='CounterLogic')
    savelogic = Connector(interface='SaveLogic')
    fitlogic = Connector(interface='FitLogic')
    qafmlogic = Connector(interface='GenericLogic')

    align_2d_axis0_name = StatusVar('align_2d_axis0_name', 'theta')
    align_2d_axis1_name = StatusVar('align_2d_axis1_name', 'phi')
    align_2d_axis2_name = StatusVar('align_2d_axis2_name', 'rho')
    align_2d_axis0_range = StatusVar('align_2d_axis0_range', 2*np.pi)
    align_2d_axis0_step = StatusVar('align_2d_axis0_step', 1e-3)
    align_2d_axis0_vel = StatusVar('align_2d_axis0_vel', 10e-6)
    align_2d_axis1_range = StatusVar('align_2d_axis1_range', 2*np.pi)
    align_2d_axis1_step = StatusVar('align_2d_axis1_step', 1e-3)
    align_2d_axis1_vel = StatusVar('align_2d_axis1_vel', 10e-6)
    align_2d_axis2_range = StatusVar('align_2d_axis2_range', 10e-3)
    align_2d_axis2_step = StatusVar('align_2d_axis2_step', 1e-3)
    align_2d_axis2_vel = StatusVar('align_2d_axis2_vel', 10e-6)
    curr_2d_pathway_mode = StatusVar('curr_2d_pathway_mode', 'snake-wise')

    _checktime = StatusVar('_checktime', 2.5)
    _1D_axis0_data = StatusVar('_1D_axis0_data', default=np.arange(3))
    _2D_axis0_data = StatusVar('_2D_axis0_data', default=np.arange(3))
    _2D_axis1_data = StatusVar('_2D_axis1_data', default=np.arange(2))
    _3D_axis0_data = StatusVar('_3D_axis0_data', default=np.arange(2))
    _3D_axis1_data = StatusVar('_3D_axis1_data', default=np.arange(2))
    _3D_axis2_data = StatusVar('_3D_axis2_data', default=np.arange(2))

    _2D_data_matrix = StatusVar('_2D_data_matrix', np.zeros((3, 2)))
    _3D_data_matrix = StatusVar('_3D_data_matrix', np.zeros((2, 2, 2)))

    curr_alignment_method = StatusVar('curr_alignment_method', '2d_fluorescence')
    _optimize_pos_freq = StatusVar('_optimize_pos_freq', 1)

    _fluorescence_integration_time = StatusVar('_fluorescence_integration_time', 5)
    
    # General Signals, used everywhere:
    sigIdleStateChanged = QtCore.Signal(bool)
    sigPosChanged = QtCore.Signal(dict)

    sigMeasurementStarted = QtCore.Signal()
    sigMeasurementContinued = QtCore.Signal()
    sigMeasurementStopped = QtCore.Signal()
    sigMeasurementFinished = QtCore.Signal()

    # Signals for making the move_abs, move_rel and abort independent:
    sigMoveAbs = QtCore.Signal(dict)
    sigMoveRel = QtCore.Signal(dict)
    sigAbort = QtCore.Signal()
    sigVelChanged = QtCore.Signal(dict)

    # Alignment Signals, remember do not touch or connect from outer logic or
    # GUI to the leading underscore signals!
    _sigStepwiseAlignmentNext = QtCore.Signal()
    _sigContinuousAlignmentNext = QtCore.Signal()
    _sigInitializeMeasPos = QtCore.Signal(bool)  # signal to go to the initial measurement position
    sigPosReached = QtCore.Signal()

    # signals if new data are writen to the data arrays (during measurement):
    sig1DMatrixChanged = QtCore.Signal()
    sig2DMatrixChanged = QtCore.Signal()
    sig3DMatrixChanged = QtCore.Signal()

    # signals if the axis for the alignment are changed/renewed (before a measurement):
    sig1DAxisChanged = QtCore.Signal()
    sig2DAxisChanged = QtCore.Signal()
    sig3DAxisChanged = QtCore.Signal()

    # signals for 2d alignemnt general
    sig2DAxis0NameChanged = QtCore.Signal(str)
    sig2DAxis0RangeChanged = QtCore.Signal(float)
    sig2DAxis0StepChanged = QtCore.Signal(float)
    sig2DAxis0VelChanged = QtCore.Signal(float)

    sig2DAxis1NameChanged = QtCore.Signal(str)
    sig2DAxis1RangeChanged = QtCore.Signal(float)
    sig2DAxis1StepChanged = QtCore.Signal(float)
    sig2DAxis1VelChanged = QtCore.Signal(float)

    sigMoveRelChanged = QtCore.Signal(dict)

    # signals for fluorescence alignment
    sigFluoIntTimeChanged = QtCore.Signal(float)
    sigOptPosFreqChanged = QtCore.Signal(float)
    sigFitFinished = QtCore.Signal(dict)

    sigTest = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self._stop_measure = False

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """
        self._magnet_device = self.magnetstage()
        self._save_logic = self.savelogic()
        self._fit_logic = self.fitlogic()
        self._qafm_logic = self.qafmlogic()

        # FIXME: THAT IS JUST A TEMPORARY SOLUTION! Implement the access on the
        #       needed methods via the TaskRunner!
        self._counter_logic = self.counterlogic()

        # connect now directly signals to the interface methods, so that
        # the logic object will be not blocks and can react on changes or abort
        self.sigMoveAbs.connect(self._magnet_device.move_abs)
        self.sigMoveRel.connect(self._magnet_device.move_rel)
        self.sigAbort.connect(self._magnet_device.abort)
        self.sigVelChanged.connect(self._magnet_device.set_velocity)

        # signal connect for alignment:

        self._sigInitializeMeasPos.connect(self._move_to_curr_pathway_index)
        self._sigStepwiseAlignmentNext.connect(self._stepwise_loop_body,
                                               QtCore.Qt.QueuedConnection)

        self.pathway_modes = ['spiral-in', 'spiral-out', 'snake-wise', 'diagonal-snake-wise']

        # relative movement settings

        constraints = self._magnet_device.get_constraints()
        self.move_rel_dict = {}

        for axis_label in constraints:
            if ('move_rel_' + axis_label) in self._statusVariables:
                self.move_rel_dict[axis_label] = self._statusVariables[('move_rel_' + axis_label)]
            else:
                self.move_rel_dict[axis_label] = 1e-3

        # 2D alignment settings

        if 'align_2d_axis0_name' in self._statusVariables:
            self.align_2d_axis0_name = self._statusVariables['align_2d_axis0_name']
        else:
            axes = list(self._magnet_device.get_constraints())
            self.align_2d_axis0_name = axes[0]
        if 'align_2d_axis1_name' in self._statusVariables:
            self.align_2d_axis1_name = self._statusVariables['align_2d_axis1_name']
        else:
            axes = list(self._magnet_device.get_constraints())
            self.align_2d_axis1_name = axes[1]
        if 'align_2d_axis2_name' in self._statusVariables:
            self.align_2d_axis2_name = self._statusVariables['align_2d_axis2_name']
        else:
            axes = list(self._magnet_device.get_constraints())
            self.align_2d_axis2_name = axes[2]

        # self.sigTest.connect(self._do_premeasurement_proc)

        if '_1D_add_data_matrix' in self._statusVariables:
            self._1D_add_data_matrix = self._statusVariables['_1D_add_data_matrix']
        else:
            self._1D_add_data_matrix = np.zeros(shape=np.shape(self._1D_axis0_data), dtype=object)

        if '_2D_add_data_matrix' in self._statusVariables:
            self._2D_add_data_matrix = self._statusVariables['_2D_add_data_matrix']
        else:
            self._2D_add_data_matrix = np.zeros(shape=np.shape(self._2D_data_matrix), dtype=object)

        if '_3D_add_data_matrix' in self._statusVariables:
            self._3D_add_data_matrix = self._statusVariables['_3D_add_data_matrix']
        else:
            self._3D_add_data_matrix = np.zeros(shape=np.shape(self._3D_data_matrix), dtype=object)

        self.alignment_methods = ['2d_fluorescence', '2d_odmr', '2d_nuclear']

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        constraints = self.get_hardware_constraints()
        for axis_label in constraints:
            self._statusVariables[('move_rel_' + axis_label)] = self.move_rel_dict[axis_label]

        self._statusVariables['align_2d_axis0_name'] = self.align_2d_axis0_name
        self._statusVariables['align_2d_axis1_name'] = self.align_2d_axis1_name
        self._statusVariables['align_2d_axis2_name'] = self.align_2d_axis2_name
        return 0

    def get_hardware_constraints(self):
        """ Retrieve the hardware constraints.

        @return dict: dict with constraints for the magnet hardware. The keys
                      are the labels for the axis and the items are again dicts
                      which contain all the limiting parameters.
        """
        return self._magnet_device.get_constraints()

    def move_rel(self, param_dict):
        """ Move the specified axis in the param_dict relative with an assigned
            value.

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters. E.g., for a movement of an axis
                                labeled with 'x' by 23 the dict should have the
                                form:
                                    param_dict = { 'x' : 23 }
        @return param dict: dictionary, which passes all the relevant
                                parameters. E.g., for a movement of an axis
                                labeled with 'x' by 23 the dict should have the
                                form:
                                    param_dict = { 'x' : 23 }
        """

        self.sigMoveRel.emit(param_dict)
        # self._check_position_reached_loop(start_pos, end_pos)
        # self.sigPosChanged.emit(param_dict)
        return param_dict

    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement)

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <a-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.

        @return param dict: dictionary, which passes all the relevant
                                parameters. E.g., for a movement of an axis
                                labeled with 'x' by 23 the dict should have the
                                form:
                                    param_dict = { 'x' : 23 }
        """
        # self._magnet_device.move_abs(param_dict)
        # start_pos = self.get_pos(list(param_dict))
        self.sigMoveAbs.emit(param_dict)

        # self._check_position_reached_loop(start_pos, param_dict)

        # self.sigPosChanged.emit(param_dict)
        return param_dict

    def get_pos(self, param_list=None):
        """ Gets current position of the stage.

        @param list param_list: optional, if a specific position of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                position is asked.

        @return dict: with keys being the axis labels and item the current
                      position.
        """

        pos_dict = self._magnet_device.get_pos(param_list)
        return pos_dict

    def get_status(self, param_list=None):
        """ Get the status of the position

        @param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        @return dict: with the axis label as key and  a tuple of a status
                     number and a status dict as the item.
        """
        status = self._magnet_device.get_status(param_list)
        return status

    def stop_movement(self):
        """ Stops movement of the stage. """
        self._stop_measure = True
        self.sigAbort.emit()
        return self._stop_measure

    def set_velocity(self, param_dict):
        """ Write new value for velocity.

        @param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <the-velocity-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.
        """
        self.sigVelChanged.emit()
        return param_dict

    def _create_1d_pathway(self, axis_name, axis_range, axis_step, axis_vel):
        """  Create a path along with the magnet should move with one axis

        @param str axis_name:
        @param float axis_range:
        @param float axis_step:

        @return:

        Here you can also create fancy 1D pathways, not only linear but also
        in any kind on nonlinear fashion.
        """
        pass

    def _create_2d_pathway(self, axis0_name, axis0_range, axis0_step,
                           axis1_name, axis1_range, axis1_step, init_pos,
                           axis0_vel=None, axis1_vel=None):
        """ Create a path along with the magnet should move.

        @param str axis0_name:
        @param float axis0_range:
        @param float axis0_step:
        @param str axis1_name:
        @param float axis1_range:
        @param float axis1_step:

        @return array: 1D np.array, which has dictionary as entries. In this
                       dictionary, it will be specified, how the magnet is going
                       from the present point to the next.

        That should be quite a general function, which maps from a given matrix
        and axes information a 2D array into a 1D path with steps being the
        relative movements.

        All kind of standard and fancy pathways through the array should be
        implemented here!
        The movement is not restricted to relative movements!
        The entry dicts have the following structure:

           pathway =  [ dict1, dict2, dict3, ...]

        whereas the dictionary can only have one or two key entries:
             dict1[axis0_name] = {'move_rel': 123, 'move_vel': 3 }
             dict1[axis1_name] = {'move_abs': 29.5}

        Note that the entries may either have a relative OR an absolute movement!
        Never both! Absolute movement will be taken always before relative
        movement. Moreover you can specify in each movement step the velocity
        and the acceleration of the movement.
        E.g. if no velocity is specified, then nothing will be changed in terms
        of speed during the move.
        """

        # calculate number of steps (those are NOT the number of points!)
        axis0_num_of_steps = int(axis0_range / axis0_step)
        axis1_num_of_steps = int(axis1_range / axis1_step)

        # make an array of movement steps
        axis0_steparray = [axis0_step] * axis0_num_of_steps
        axis1_steparray = [axis1_step] * axis1_num_of_steps

        pathway = []

        # FIXME: create these path modes:
        if self.curr_2d_pathway_mode == 'spiral-in':
            self.log.error('The pathway creation method "{0}" through the '
                           'matrix is not implemented yet!\nReturn an empty '
                           'patharray.'.format(self.curr_2d_pathway_mode))
            return [], []

        elif self.curr_2d_pathway_mode == 'spiral-out':
            self.log.error('The pathway creation method "{0}" through the '
                           'matrix is not implemented yet!\nReturn an empty '
                           'patharray.'.format(self.curr_2d_pathway_mode))
            return [], []

        elif self.curr_2d_pathway_mode == 'diagonal-snake-wise':
            self.log.error('The pathway creation method "{0}" through the '
                           'matrix is not implemented yet!\nReturn an empty '
                           'patharray.'.format(self.current_2d_pathway_mode))
            return [], []

        elif self.curr_2d_pathway_mode == 'selected-points':
            self.log.error('The pathway creation method "{0}" through the '
                           'matrix is not implemented yet!\nReturn an empty '
                           'patharray.'.format(self.current_2d_pathway_mode))
            return [], []

        # choose the snake-wise as default for now.
        else:

            # create a snake-wise stepping procedure through the matrix:
            self.log.debug(axis0_name)
            self.log.debug(axis0_range)
            self.log.debug(init_pos[axis0_name])
            axis0_pos = round(init_pos[axis0_name] - axis0_range / 2, 7)
            axis1_pos = round(init_pos[axis1_name] - axis1_range / 2, 7)

            # append again so that the for loop later will run once again
            # through the axis0 array but the last value of axis1_steparray will
            # not be performed.
            axis1_steparray.append(axis1_num_of_steps)

            # step_config is the dict containing the commands for one pathway
            # entry. Move at first to start position:
            step_config = dict()

            if axis0_vel is None:
                step_config[axis0_name] = {'move_abs': axis0_pos}
            else:
                step_config[axis0_name] = {'move_abs': axis0_pos, 'move_vel': axis0_vel}

            if axis1_vel is None:
                step_config[axis1_name] = {'move_abs': axis1_pos}
            else:
                step_config[axis1_name] = {'move_abs': axis1_pos, 'move_vel': axis1_vel}

            pathway.append(step_config)

            path_index = 0

            # these indices should be used to facilitate the mapping to a 2D
            # array, since the
            axis0_index = 0
            axis1_index = 0

            # that is a map to transform a pathway index value back to an
            # absolute position and index. That will be important for saving the
            # data corresponding to a certain path_index value.
            back_map = dict()
            back_map[path_index] = {axis0_name: axis0_pos,
                                    axis1_name: axis1_pos,
                                    'index': (axis0_index, axis1_index)}

            path_index += 1
            # axis0_index += 1

            go_pos_dir = True
            for step_in_axis1 in axis1_steparray:

                if go_pos_dir:
                    go_pos_dir = False
                    direction = +1
                else:
                    go_pos_dir = True
                    direction = -1

                for step_in_axis0 in axis0_steparray:

                    axis0_index += direction
                    # make move along axis0:
                    step_config = dict()

                    # relative movement:
                    # step_config[axis0_name] = {'move_rel': direction*step_in_axis0}

                    # absolute movement:
                    axis0_pos = round(axis0_pos + direction * step_in_axis0, 7)

                    # if axis0_vel is None:
                    #     step_config[axis0_name] = {'move_abs': axis0_pos}
                    #     step_config[axis1_name] = {'move_abs': axis1_pos}
                    # else:
                    #     step_config[axis0_name] = {'move_abs': axis0_pos,
                    #                                'move_vel': axis0_vel}
                    if axis1_vel is None and axis0_vel is None:
                        step_config[axis0_name] = {'move_abs': axis0_pos}
                        step_config[axis1_name] = {'move_abs': axis1_pos}
                    else:
                        step_config[axis0_name] = {'move_abs': axis0_pos}
                        step_config[axis1_name] = {'move_abs': axis1_pos}

                        if axis0_vel is not None:
                            step_config[axis0_name] = {'move_abs': axis0_pos, 'move_vel': axis0_vel}

                        if axis1_vel is not None:
                            step_config[axis1_name] = {'move_abs': axis1_pos, 'move_vel': axis1_vel}

                    # append to the pathway
                    pathway.append(step_config)
                    back_map[path_index] = {axis0_name: axis0_pos,
                                            axis1_name: axis1_pos,
                                            'index': (axis0_index, axis1_index)}
                    path_index += 1

                if (axis1_index + 1) >= len(axis1_steparray):
                    break

                # make a move along axis1:
                step_config = dict()

                # relative movement:
                # step_config[axis1_name] = {'move_rel' : step_in_axis1}

                # absolute movement:
                axis1_pos = round(axis1_pos + step_in_axis1, 7)

                if axis1_vel is None and axis0_vel is None:
                    step_config[axis0_name] = {'move_abs': axis0_pos}
                    step_config[axis1_name] = {'move_abs': axis1_pos}
                else:
                    step_config[axis0_name] = {'move_abs': axis0_pos}
                    step_config[axis1_name] = {'move_abs': axis1_pos}

                    if axis0_vel is not None:
                        step_config[axis0_name] = {'move_abs': axis0_pos, 'move_vel': axis0_vel}

                    if axis1_vel is not None:
                        step_config[axis1_name] = {'move_abs': axis1_pos, 'move_vel': axis1_vel}

                pathway.append(step_config)
                axis1_index += 1
                back_map[path_index] = {axis0_name: axis0_pos,
                                        axis1_name: axis1_pos,
                                        'index': (axis0_index, axis1_index)}
                path_index += 1

        return pathway, back_map

    def _create_2d_cont_pathway(self, pathway):

        # go through the passed 1D path and reduce the whole movement just to
        # corner points

        pathway_cont = dict()

        return pathway_cont

    def _prepare_2d_graph(self, axis0_start, axis0_range, axis0_step,
                          axis1_start, axis1_range, axis1_step):
        # set up a matrix where measurement points are save to
        # general method to prepare 2d images, and their axes.

        # that is for the matrix image. +1 because number of points and not
        # number of steps are needed:
        num_points_axis0 = int(axis0_range / axis0_step) + 1
        num_points_axis1 = int(axis1_range / axis1_step) + 1
        matrix = np.zeros((num_points_axis0, num_points_axis1))

        # Decrease/increase lower/higher bound of axes by half of the step length
        # in order to display the rectangles in the 2d plot in the gui such that the
        # measurement position is in the center of the rectangle.
        # data axis0:
        data_axis0 = np.linspace(axis0_start, axis0_start + (num_points_axis0 - 1) * axis0_step, num_points_axis0)

        # data axis1:
        data_axis1 = np.linspace(axis1_start, axis1_start + (num_points_axis1 - 1) * axis1_step, num_points_axis1)

        return matrix, data_axis0, data_axis1

    def _prepare_1d_graph(self, axis_range, axis_step):
        pass

    def start_1d_alignment(self, axis_name, axis_range, axis_step, axis_vel,
                           stepwise_meas=True, continue_meas=False):

        # actual measurement routine, which is called to start the measurement


        if not continue_meas:

            # to perform the '_do_measure_after_stop' routine from the beginning
            # (which means e.g. an optimize pos)

            self._prepare_1d_graph()

            self._pathway = self._create_1d_pathway()

            if stepwise_meas:
                # just make it to an empty dict
                self._pathway_cont = dict()

            else:
                # create from the path_points the continoues points
                self._pathway_cont = self._create_1d_cont_pathway(self._pathway)

        else:
            # tell all the connected instances that measurement is continuing:
            self.sigMeasurementContinued.emit()

        # run at first the _move_to_curr_pathway_index method to go to the
        # index position:
        self._sigInitializeMeasPos.emit(stepwise_meas)

    def start_2d_alignment(self, stepwise_meas=True, continue_meas=False):

        # before starting the measurement you should convince yourself that the
        # passed traveling range is possible. Otherwise the measurement will be
        # aborted and an error is raised.
        #
        # actual measurement routine, which is called to start the measurement

        # start measurement value



        self._start_measurement_time = datetime.datetime.now()
        self._stop_measurement_time = None

        self._stop_measure = False

        # self.align_2d_axis0_name = axis0_name
        # self.align_2d_axis1_name = axis1_name

        # get name of other axis to control their values
        self._control_dict = {}
        pos_dict = self.get_pos()
        key_set1 = set(pos_dict.keys())
        key_set2 = set([self.align_2d_axis1_name, self.align_2d_axis0_name])
        key_complement = key_set1 - key_set2
        self._control_dict = {key: pos_dict[key] for key in key_complement}

        # additional values to save
        self._2d_error = []
        self._2d_measured_fields = []
        self._2d_intended_fields = []

        # save only the position of the axis, which are going to be moved
        # during alignment, the return will be a dict!
        self._saved_pos_before_align = self.get_pos([self.align_2d_axis0_name, self.align_2d_axis1_name])

        if not continue_meas:

            self.sigMeasurementStarted.emit()

            # the index, which run through the _pathway list and selects the
            # current measurement point
            self._pathway_index = 0

            self._pathway, self._backmap = self._create_2d_pathway(self.align_2d_axis0_name,
                                                                   self.align_2d_axis0_range,
                                                                   self.align_2d_axis0_step,
                                                                   self.align_2d_axis1_name,
                                                                   self.align_2d_axis1_range,
                                                                   self.align_2d_axis1_step,
                                                                   self._saved_pos_before_align,
                                                                   self.align_2d_axis0_vel,
                                                                   self.align_2d_axis1_vel)

            # determine the start point, either relative or absolute!
            # Now the absolute position will be used:
            axis0_start = self._backmap[0][self.align_2d_axis0_name]
            axis1_start = self._backmap[0][self.align_2d_axis1_name]

            prepared_graph = self._prepare_2d_graph(
                axis0_start,
                self.align_2d_axis0_range,
                self.align_2d_axis0_step,
                axis1_start,
                self.align_2d_axis1_range,
                self.align_2d_axis1_step)

            self._2D_data_matrix, self._2D_axis0_data, self._2D_axis1_data = prepared_graph

            self._2D_add_data_matrix = np.zeros(shape=np.shape(self._2D_data_matrix), dtype=object)

            if stepwise_meas:
                # just make it to an empty dict
                self._pathway_cont = dict()

            else:
                # create from the path_points the continuous points
                self._pathway_cont = self._create_2d_cont_pathway(self._pathway)

        # TODO: include here another mode, where a new defined pathway can be
        #       created, along which the measurement should be repeated.
        #       You have to follow the procedure:
        #           - Create for continuing the measurement just a proper
        #             pathway and a proper back_map in self._create_2d_pathway,
        #       => Then the whole measurement can be just run with the new
        #          pathway and back_map, and you do not have to adjust other
        #          things.

        else:
            # tell all the connected instances that measurement is continuing:
            self.sigMeasurementContinued.emit()

        # run at first the _move_to_curr_pathway_index method to go to the
        # index position:
        self._sigInitializeMeasPos.emit(stepwise_meas)
        return 0

    def _move_to_curr_pathway_index(self, stepwise_meas):

        # move to the passed pathway index in the list _pathway and start the
        # proper loop for that:

        # move absolute to the index position, which is currently given

        move_dict_vel, \
        move_dict_abs, \
        move_dict_rel = self._move_to_index(self._pathway_index, self._pathway)

        self.log.debug("I'm in _move_to_curr_pathway_index: {0}".format(move_dict_abs))
        # self.set_velocity(move_dict_vel)
        self._magnet_device.move_abs(move_dict_abs)
        # self.move_rel(move_dict_rel)
        while self._check_is_moving():
            time.sleep(self._checktime)
            self.log.debug("Went into while loop in _move_to_curr_pathway_index")

        # this function will return to this function if position is reached:
        start_pos = self._saved_pos_before_align
        end_pos = dict()
        for axis_name in self._saved_pos_before_align:
            end_pos[axis_name] = self._backmap[self._pathway_index][axis_name]

        self.log.debug("(first movement) magnet moving ? {0}".format(self._check_is_moving()))

        if stepwise_meas:
            # start the Stepwise alignment loop body self._stepwise_loop_body:
            self._sigStepwiseAlignmentNext.emit()
        else:
            # start the continuous alignment loop body self._continuous_loop_body:
            self._sigContinuousAlignmentNext.emit()

    def _stepwise_loop_body(self):
        """ Go one by one through the created path
        @return:
        The loop body goes through the 1D array
        """

        if self._stop_measure:
            self._end_alignment_procedure()
            return

        self._do_premeasurement_proc()
        pos = self._magnet_device.get_pos()
        end_pos = self._pathway[self._pathway_index]
        self.log.debug('end_pos {0}'.format(end_pos))
        differences = []
        for key in end_pos:
            differences.append((pos[key] - end_pos[key]['move_abs']) ** 2)

        for key in self._control_dict:
            differences.append((pos[key] - self._control_dict[key]) ** 2)

        distance = 0
        for difference in differences:
            distance += difference

        # this is not the actual distance (in a physical sense), just some sort of mean of the
        # variation of the measurement variables. ( Don't know which coordinates are used ... spheric, cartesian ... )
        distance = np.sqrt(distance)
        self._2d_error.append(distance)
        self._2d_measured_fields.append(pos)
        # the desired field
        act_pos = {key: self._pathway[self._pathway_index][key]['move_abs'] for key in
                   self._pathway[self._pathway_index]}
        # wanted_pos = {**self._control_dict, **act_pos}
        # Workaround for Python 3.4.4
        self._control_dict.update(act_pos)
        wanted_pos = self._control_dict

        self._2d_intended_fields.append(wanted_pos)

        self.log.debug("Distance from desired position: {0}".format(distance))
        # perform here one of the chosen alignment measurements
        meas_val, add_meas_val = self._do_alignment_measurement()

        # set the measurement point to the proper array and the proper position:
        # save also all additional measurement information, which have been
        # done during the measurement in add_meas_val.
        self._set_meas_point(meas_val, add_meas_val, self._pathway_index, self._backmap)

        # increase the index
        self._pathway_index += 1

        if self._pathway_index < len(self._pathway):

            #
            self._do_premeasurement_proc()
            move_dict_vel, \
            move_dict_abs, \
            move_dict_rel = self._move_to_index(self._pathway_index, self._pathway)

            # commenting this out for now, because it is kind of useless for us
            # self.set_velocity(move_dict_vel)
            self._magnet_device.move_abs(move_dict_abs)

            while self._check_is_moving():
                time.sleep(self._checktime)
                self.log.debug("Went into while loop in stepwise_loop_body")

            self.log.debug("stepwise_loop_body reports magnet moving ? {0}".format(self._check_is_moving()))

            # this function will return to this function if position is reached:
            start_pos = dict()
            end_pos = dict()
            for axis_name in self._saved_pos_before_align:
                start_pos[axis_name] = self._backmap[self._pathway_index - 1][axis_name]
                end_pos[axis_name] = self._backmap[self._pathway_index][axis_name]

            # rerun this loop again
            self._sigStepwiseAlignmentNext.emit()

        else:
            self._end_alignment_procedure()
        return

    def _continuous_loop_body(self):
        """ Go as much as possible in one direction

        @return:

        The loop body goes through the 1D array
        """
        pass

    def stop_alignment(self):
        """ Stops any kind of ongoing alignment measurement by setting a flag.
        """

        self._stop_measure = True

        # abort the movement or check whether immediate abortion of measurement
        # was needed.

        # check whether an alignment measurement is currently going on and send
        # a signal to stop that.

    def _end_alignment_procedure(self):

        # 1 check if magnet is moving and stop it

        # move back to the first position before the alignment has started:
        #
        constraints = self.get_hardware_constraints()

        last_pos = dict()
        for axis_name in self._saved_pos_before_align:
            last_pos[axis_name] = self._backmap[self._pathway_index - 1][axis_name]

        self._magnet_device.move_abs(self._saved_pos_before_align)

        while self._check_is_moving():
            time.sleep(self._checktime)

        self.sigMeasurementFinished.emit()

        self._pathway_index = 0
        self._stop_measurement_time = datetime.datetime.now()

        self.log.info('Alignment Complete!')

        pass

    def _check_position_reached_loop(self, start_pos_dict, end_pos_dict):
        """ Perform just a while loop, which checks everytime the conditions

        @param dict start_pos_dict: the position in this dictionary must be
                                    absolute positions!
        @param dict end_pos_dict:
        @param float checktime: the checktime in seconds

        @return:

        Whenever the magnet has passed 95% of the way, the method will return.

        Check also whether the difference in position increases again, and if so
        stop the measurement and raise an error, since either the velocity was
        too fast or the magnet does not move further.
        """

        distance_init = 0.0
        constraints = self.get_hardware_constraints()
        minimal_distance = 0.0
        for axis_label in start_pos_dict:
            distance_init = (end_pos_dict[axis_label] - start_pos_dict[axis_label]) ** 2
            minimal_distance = minimal_distance + (constraints[axis_label]['pos_step']) ** 2
        distance_init = np.sqrt(distance_init)
        minimal_distance = np.sqrt(minimal_distance)

        # take 97% distance tolerance:
        distance_tolerance = 0.03 * distance_init

        current_dist = 0.0

        while True:
            time.sleep(self._checktime)

            curr_pos = self.get_pos(list(end_pos_dict))

            for axis_label in start_pos_dict:
                current_dist = (end_pos_dict[axis_label] - curr_pos[axis_label]) ** 2

            current_dist = np.sqrt(current_dist)

            self.sigPosChanged.emit(curr_pos)

            if (current_dist <= distance_tolerance) or (current_dist <= minimal_distance) or self._stop_measure:
                self.sigPosReached.emit()

                break

                # return either pos reached signal of check position

    def _check_is_moving(self):
        """

        @return bool: True indicates the magnet is moving, False the magnet stopped movement
        """
        # get axis names
        axes = list(self._magnet_device.get_constraints().keys())
        state = self._magnet_device.get_status()

        return not (state[axes[0]] and state[axes[1]] and state[axes[2]])

    def _set_meas_point(self, meas_val, add_meas_val, pathway_index, back_map):

        # is it point for 1d meas or 2d meas?

        # map the point back to the position in the measurement array
        index_array = back_map[pathway_index]['index']

        # then index_array is actually no array, but just a number. That is the
        # 1D case:
        if np.shape(index_array) == ():

            # FIXME: Implement the 1D save

            self.sig1DMatrixChanged.emit()

        elif np.shape(index_array)[0] == 2:

            self._2D_data_matrix[index_array] = meas_val
            self._2D_add_data_matrix[index_array] = add_meas_val

            # self.log.debug('Data "{0}", saved at intex "{1}"'.format(meas_val, index_array))

            self.sig2DMatrixChanged.emit()

        elif np.shape(index_array)[0] == 3:

            # FIXME: Implement the 3D save
            self.sig3DMatrixChanged.emit()
        else:
            self.log.error('The measurement point "{0}" could not be set in '
                           'the _set_meas_point routine, since either a 1D, a 2D or '
                           'a 3D index array was expected, but an index array "{1}" '
                           'was given in the passed back_map. Correct the '
                           'back_map creation in the routine '
                           '_create_2d_pathway!'.format(meas_val, index_array))

        pass

    def _do_premeasurement_proc(self):
        # do a selected pre measurement procedure, like e.g. optimize position.


        # first attempt of an optimizer usage:
        # Trying to implement that a user can adjust the frequency
        # at which he wants to refocus.
        freq = self._optimize_pos_freq
        ii = self._pathway_index

        if freq >= 1:
            freq = int(np.round(freq))
            for ii in range(freq):
                self._do_optimize_pos()

        elif 0 < freq < 1:
            freq = int(np.round(1 / freq))
            if not ii % freq:
                self._do_optimize_pos()

        elif freq < 0:
            self.log.error('No refocus happend, because negative frequency was given')

        # If frequency is 0, then no refocus will happen at all, which is intended.
        return
    
    def _do_optimize_pos(self):
        self._qafm_logic.default_optimize(run_in_thread=False)
        return 0


    def _do_alignment_measurement(self):
        """ That is the main method which contains all functions with measurement routines.

        Each measurement routine has to output the measurement value, but can
        also provide a dictionary with additional measurement parameters, which
        have been measured either as a pre-requisition for the measurement or
        are results of the measurement.

        Save each measured value as an item to a keyword string, i.e.
            {'ODMR frequency (MHz)': <the_parameter>, ...}
        The save routine will handle the additional information and save them
        properly.


        @return tuple(float, dict): the measured value is of type float and the
                                    additional parameters are saved in a
                                    dictionary form.
        """

        # self.alignment_methods = ['fluorescence_pointwise',
        #                           'fluorescence_continuous',
        #                           'odmr_splitting',
        #                           'odmr_hyperfine_splitting',
        #                           'nuclear_spin_measurement']

        if self.curr_alignment_method == '2d_fluorescence':
            data, add_data = self._perform_fluorescence_measure()

        # data, add_data = self._perform_odmr_measure(11100e6, 1e6, 11200e6, 5, 10, 'Lorentzian', False,'')


        return data, add_data

    def _perform_fluorescence_measure(self):

        # FIXME: that should be run through the TaskRunner! Implement the call
        #       by not using this connection!

        if self._counter_logic.get_counting_mode() != CountingMode.CONTINUOUS:
            self._counter_logic.set_counting_mode(mode=CountingMode.CONTINUOUS)

        self._counter_logic.start_saving()
        time.sleep(self._fluorescence_integration_time)
        data_array, parameters = self._counter_logic.save_data(to_file=False)

        data_array = np.array(data_array)[:, 1]

        return data_array.mean(), parameters

   
    def _run_gated_counter(self):

        self._gc_logic.startCount()
        time.sleep(2)

        # wait until the gated counter is done
        while self._gc_logic.module_state() != 'idle' and not self._stop_measure:
            # print('in SSR measure')
            time.sleep(1)

    def _pulser_on(self):
        """ Switch on the pulser output. """

        self._set_channel_activation(active=True, apply_to_device=True)
        self._seq_gen_logic.pulser_on()

    def _pulser_off(self):
        """ Switch off the pulser output. """

        self._set_channel_activation(active=False, apply_to_device=False)
        self._seq_gen_logic.pulser_off()


    def save_1d_data(self):

        # save also all kinds of data, which are the results during the
        # alignment measurements

        pass

    def save_2d_data(self, tag=None, timestamp=None):
        """ Save the data of the  """

        filepath = self._save_logic.get_path_for_module(module_name='Magnet')

        if timestamp is None:
            timestamp = datetime.datetime.now()

        # if tag is not None and len(tag) > 0:
        #     filelabel = tag + '_magnet_alignment_data'
        #     filelabel2 = tag + '_magnet_alignment_add_data'
        # else:
        #     filelabel = 'magnet_alignment_data'
        #     filelabel2 = 'magnet_alignment_add_data'

        if tag is not None and len(tag) > 0:
            filelabel = tag + '_magnet_alignment_data'
            filelabel2 = tag + '_magnet_alignment_add_data'
            filelabel3 = tag + '_magnet_alignment_data_table'
            filelabel4 = tag + '_intended_field_values'
            filelabel5 = tag + '_reached_field_values'
            filelabel6 = tag + '_error_in_field'
        else:
            filelabel = 'magnet_alignment_data'
            filelabel2 = 'magnet_alignment_add_data'
            filelabel3 = 'magnet_alignment_data_table'
            filelabel4 = 'intended_field_values'
            filelabel5 = 'reached_field_values'
            filelabel6 = 'error_in_field'

        # prepare the data in a dict or in an OrderedDict:

        # here is the matrix saved
        matrix_data = OrderedDict()

        # here are all the parameters, which are saved for a certain matrix
        # entry, mainly coming from all the other logic modules except the magnet logic:
        add_matrix_data = OrderedDict()

        # here are all supplementary information about the measurement, mainly
        # from the magnet logic
        supplementary_data = OrderedDict()

        axes_names = list(self._saved_pos_before_align)

        matrix_data['Alignment Matrix'] = self._2D_data_matrix

        parameters = OrderedDict()
        parameters['Measurement start time'] = self._start_measurement_time
        if self._stop_measurement_time is not None:
            parameters['Measurement stop time'] = self._stop_measurement_time
        parameters['Time at Data save'] = timestamp
        parameters['Pathway of the magnet alignment'] = 'Snake-wise steps'

        for index, entry in enumerate(self._pathway):
            parameters['index_' + str(index)] = entry

        parameters['Backmap of the magnet alignment'] = 'Index wise display'

        for entry in self._backmap:
            parameters['related_intex_' + str(entry)] = self._backmap[entry]

        self._save_logic.save_data(matrix_data, filepath=filepath, parameters=parameters,
                                   filelabel=filelabel, timestamp=timestamp)

        self.log.debug('Magnet 2D data saved to:\n{0}'.format(filepath))

        figure_data = matrix_data['Alignment Matrix']
        
        image_extent = [self._2D_axis0_data.min(),
                        self._2D_axis0_data.max(),
                        self._2D_axis1_data.min(),
                        self._2D_axis1_data.max()]
        axes = ['phi', 'theta']

        figs = self.draw_figure(data=figure_data,
                                     image_extent=image_extent,
                                     scan_axis=axes,
                                     cbar_range=None,
                                     percentile_range=None,
                                     crosshair_pos=None)

        # Save the image data and figure
        image_data = OrderedDict()
        image_data['Alignment image data without axis.\n'
            'The upper left entry represents the signal at the upper left pixel position.\n'
            'A pixel-line in the image corresponds to a row '
            'of entries where the Signal is in counts/s:'] = figure_data

        filelabel = 'alignment_image'
        self._save_logic.save_data(image_data,
                                    filepath=filepath,
                                    timestamp=timestamp,
                                    parameters=parameters,
                                    filelabel=filelabel,
                                    fmt='%.6e',
                                    delimiter='\t',
                                    plotfig=figs)

        # prepare the data in a dict or in an OrderedDict:
        add_data = OrderedDict()
        axis0_data = np.zeros(len(self._backmap))
        axis1_data = np.zeros(len(self._backmap))
        param_data = np.zeros(len(self._backmap), dtype='object')

        for backmap_index in self._backmap:
            axis0_data[backmap_index] = self._backmap[backmap_index][self.align_2d_axis0_name]
            axis1_data[backmap_index] = self._backmap[backmap_index][self.align_2d_axis1_name]
            param_data[backmap_index] = str(self._2D_add_data_matrix[self._backmap[backmap_index]['index']])

        constr = self.get_hardware_constraints()
        units_axis0 = constr[self.align_2d_axis0_name]['unit']
        units_axis1 = constr[self.align_2d_axis1_name]['unit']

        add_data['{0} values ({1})'.format(self.align_2d_axis0_name, units_axis0)] = axis0_data
        add_data['{0} values ({1})'.format(self.align_2d_axis1_name, units_axis1)] = axis1_data
        # add_data['all measured additional parameter'] = param_data

        self._save_logic.save_data(add_data, filepath=filepath, filelabel=filelabel2,
                                   timestamp=timestamp)
        # save the data table

        count_data = self._2D_data_matrix
        x_val = self._2D_axis0_data
        y_val = self._2D_axis1_data
        save_dict = OrderedDict()
        axis0_key = '{0} values ({1})'.format(self.align_2d_axis0_name, units_axis0)
        axis1_key = '{0} values ({1})'.format(self.align_2d_axis1_name, units_axis1)
        counts_key = 'counts (c/s)'
        save_dict[axis0_key] = []
        save_dict[axis1_key] = []
        save_dict[counts_key] = []

        for ii, columns in enumerate(count_data):
            for jj, col_counts in enumerate(columns):
                # x_list = [x_val[ii]] * len(countlist)
                save_dict[axis0_key].append(x_val[ii])
                save_dict[axis1_key].append(y_val[jj])
                save_dict[counts_key].append(col_counts)
        save_dict[axis0_key] = np.array(save_dict[axis0_key])
        save_dict[axis1_key] = np.array(save_dict[axis1_key])
        save_dict[counts_key] = np.array(save_dict[counts_key])

        # making saveable dictionaries

        self._save_logic.save_data(save_dict, filepath=filepath, filelabel=filelabel3,
                                   timestamp=timestamp, fmt='%.6e')
        keys = self._2d_intended_fields[0].keys()
        intended_fields = OrderedDict()
        for key in keys:
            field_values = [coord_dict[key] for coord_dict in self._2d_intended_fields]
            intended_fields[key] = field_values

        self._save_logic.save_data(intended_fields, filepath=filepath, filelabel=filelabel4,
                                   timestamp=timestamp)

        measured_fields = OrderedDict()
        for key in keys:
            field_values = [coord_dict[key] for coord_dict in self._2d_measured_fields]
            measured_fields[key] = field_values

        self._save_logic.save_data(measured_fields, filepath=filepath, filelabel=filelabel5,
                                   timestamp=timestamp)

        error = OrderedDict()
        error['quadratic error'] = self._2d_error

        self._save_logic.save_data(error, filepath=filepath, filelabel=filelabel6,
                                   timestamp=timestamp)

    def draw_figure(self, data, image_extent, scan_axis=None, cbar_range=None, percentile_range=None,  crosshair_pos=None):
        """ Create a 2-D color map figure of the scan image.

        @param: array data: The NxM array of count values from a scan with NxM pixels.

        @param: list image_extent: The scan range in the form [hor_min, hor_max, ver_min, ver_max]

        @param: list axes: Names of the horizontal and vertical axes in the image

        @param: list cbar_range: (optional) [color_scale_min, color_scale_max].  If not supplied then a default of
                                 data_min to data_max will be used.

        @param: list percentile_range: (optional) Percentile range of the chosen cbar_range.

        @param: list crosshair_pos: (optional) crosshair position as [hor, vert] in the chosen image axes.

        @return: fig fig: a matplotlib figure object to be saved to file.
        """
        if scan_axis is None:
            scan_axis = ['X', 'Y']

        # If no colorbar range was given, take full range of data
        if cbar_range is None:
            cbar_range = [np.min(data), np.max(data)]

        # Scale color values using SI prefix
        prefix = ['', 'k', 'M', 'G']
        prefix_count = 0
        image_data = data
        draw_cb_range = np.array(cbar_range)
        image_dimension = image_extent.copy()

        while draw_cb_range[1] > 1000:
            image_data = image_data/1000
            draw_cb_range = draw_cb_range/1000
            prefix_count = prefix_count + 1

        c_prefix = prefix[prefix_count]


        # Scale axes values using SI prefix
        axes_prefix = ['', 'm', r'$\mathrm{\mu}$', 'n']
        x_prefix_count = 0
        y_prefix_count = 0

        while np.abs(image_dimension[1]-image_dimension[0]) < 1:
            image_dimension[0] = image_dimension[0] * 1000.
            image_dimension[1] = image_dimension[1] * 1000.
            x_prefix_count = x_prefix_count + 1

        while np.abs(image_dimension[3] - image_dimension[2]) < 1:
            image_dimension[2] = image_dimension[2] * 1000.
            image_dimension[3] = image_dimension[3] * 1000.
            y_prefix_count = y_prefix_count + 1

        x_prefix = axes_prefix[x_prefix_count]
        y_prefix = axes_prefix[y_prefix_count]

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, ax = plt.subplots()

        # Create image plot
        cfimage = ax.imshow(image_data,
                            cmap=plt.get_cmap('viridis'), # reference the right place in qd
                            origin="lower",
                            vmin=draw_cb_range[0],
                            vmax=draw_cb_range[1],
                            interpolation='none',
                            extent=image_dimension
                            )

        ax.set_aspect(1)
        ax.set_xlabel(scan_axis[0] + ' (' + x_prefix + 'rad)')
        ax.set_ylabel(scan_axis[1] + ' (' + y_prefix + 'rad)')
        ax.spines['bottom'].set_position(('outward', 10))
        ax.spines['left'].set_position(('outward', 10))
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.get_xaxis().tick_bottom()
        ax.get_yaxis().tick_left()

        # draw the crosshair position if defined
        if crosshair_pos is not None:
            trans_xmark = mpl.transforms.blended_transform_factory(
                ax.transData,
                ax.transAxes)

            trans_ymark = mpl.transforms.blended_transform_factory(
                ax.transAxes,
                ax.transData)

            ax.annotate('', xy=(crosshair_pos[0]*np.power(1000,x_prefix_count), 0),
                        xytext=(crosshair_pos[0]*np.power(1000,x_prefix_count), -0.01), xycoords=trans_xmark,
                        arrowprops=dict(facecolor='#17becf', shrink=0.05),
                        )

            ax.annotate('', xy=(0, crosshair_pos[1]*np.power(1000,y_prefix_count)),
                        xytext=(-0.01, crosshair_pos[1]*np.power(1000,y_prefix_count)), xycoords=trans_ymark,
                        arrowprops=dict(facecolor='#17becf', shrink=0.05),
                        )

        # Draw the colorbar
        cbar = plt.colorbar(cfimage, shrink=0.8)#, fraction=0.046, pad=0.08, shrink=0.75)
        cbar.set_label('Fluorescence (' + c_prefix + 'c/s)')

        # remove ticks from colorbar for cleaner image
        cbar.ax.tick_params(which=u'both', length=0)

        # If we have percentile information, draw that to the figure
        if percentile_range is not None:
            cbar.ax.annotate(str(percentile_range[0]),
                             xy=(-0.3, 0.0),
                             xycoords='axes fraction',
                             horizontalalignment='right',
                             verticalalignment='center',
                             rotation=90
                             )
            cbar.ax.annotate(str(percentile_range[1]),
                             xy=(-0.3, 1.0),
                             xycoords='axes fraction',
                             horizontalalignment='right',
                             verticalalignment='center',
                             rotation=90
                             )
            cbar.ax.annotate('(percentile)',
                             xy=(-0.3, 0.5),
                             xycoords='axes fraction',
                             horizontalalignment='right',
                             verticalalignment='center',
                             rotation=90
                             )

        return fig

    def _move_to_index(self, pathway_index, pathway):

        # make here the move and set also for the move the velocity, if
        # specified!

        move_commmands = pathway[pathway_index]

        move_dict_abs = dict()
        move_dict_rel = dict()
        move_dict_vel = dict()

        for axis_name in move_commmands:

            if move_commmands[axis_name].get('vel') is not None:
                move_dict_vel[axis_name] = move_commmands[axis_name]['vel']

            if move_commmands[axis_name].get('move_abs') is not None:
                move_dict_abs[axis_name] = move_commmands[axis_name]['move_abs']
            elif move_commmands[axis_name].get('move_rel') is not None:
                move_dict_rel[axis_name] = move_commmands[axis_name]['move_rel']

        return move_dict_vel, move_dict_abs, move_dict_rel

    def set_pos_checktime(self, checktime):
        if not np.isclose(0, checktime) and checktime > 0:
            self._checktime = checktime
        else:
            self.log.warning('Could not set a new value for checktime, since '
                             'the passed value "{0}" is either zero or negative!\n'
                             'Choose a proper checktime value in seconds, the old '
                             'value will be kept!')
    
    def _set_optimized_xy_from_fit(self):
        """Fit the completed xy optimizer scan and set the optimized xy position."""
        fit_x, fit_y = np.meshgrid(self._2D_axis0_data, self._2D_axis1_data)
        xy_fit_data = self._2D_data_matrix.ravel()
        axes = np.empty((len(self._2D_axis0_data) * len(self._2D_axis1_data), 2))
        axes = (fit_x.flatten(), fit_y.flatten())
        result_2D_gaus = self._fit_logic.make_twoDgaussian_fit(
            xy_axes=axes,
            data=xy_fit_data,
            estimator=self._fit_logic.estimate_twoDgaussian_MLE
        )
        self.fit_result = result_2D_gaus
        # print(result_2D_gaus.fit_report())
        curr_pos = self.get_pos()
        self._initial_pos_x, self._initial_pos_y = curr_pos['theta'], curr_pos['phi']
        if result_2D_gaus.success is False:
            self.log.error('Error: 2D Gaussian Fit was not successfull!.')
            print('2D gaussian fit not successfull')
            self.optim_pos_x = self._initial_pos_x
            self.optim_pos_y = self._initial_pos_y
            self.optim_sigma_x = 0.
            self.optim_sigma_y = 0.
        else:
            if result_2D_gaus.best_values['center_x']>2*np.pi:
                result_2D_gaus.best_values['center_x'] -= 2*np.pi
            if result_2D_gaus.best_values['center_y']>2*np.pi:
                result_2D_gaus.best_values['center_y'] -= 2*np.pi
            if result_2D_gaus.best_values['center_x']<2*np.pi:
                result_2D_gaus.best_values['center_x'] += 2*np.pi
            if result_2D_gaus.best_values['center_y']<2*np.pi:
                result_2D_gaus.best_values['center_y'] += 2*np.pi
            self.optim_pos_x = result_2D_gaus.best_values['center_x']
            self.optim_pos_y = result_2D_gaus.best_values['center_y']
            self.optim_sigma_x = result_2D_gaus.best_values['sigma_x']
            self.optim_sigma_y = result_2D_gaus.best_values['sigma_y']

        # emit image updated signal so crosshair can be updated from this fit
        self.sigFitFinished.emit({'rho':curr_pos['rho'], 'theta':self.optim_pos_x, 'phi':self.optim_pos_y, 'fit_result':result_2D_gaus.fit_report(show_correl=False)})

    def get_2d_data_matrix(self):
        return self._2D_data_matrix

    def get_2d_axis_arrays(self):
        return self._2D_axis0_data, self._2D_axis1_data

    def set_move_rel_para(self, parameters):
        """ Set the move relative parameters according to dict

        @params dict: Dictionary with new values

        @return dict: Dictionary with new values
        """
        for axis_label in parameters:
            self.move_rel_dict[axis_label] = parameters[axis_label]
            self.sigMoveRelChanged.emit(parameters)
        return self.move_rel_dict

    def get_move_rel_para(self, param_list=None):
        """ Get the move relative parameters

        @params list: Optional list with axis names

        @return dict: Dictionary with new values
        """
        if param_list is None:
            return self.move_rel_dict
        else:
            return_dict = dict()
            for axis_label in param_list:
                return_dict[axis_label] = self.move_rel_dict[axis_label]
            return return_dict

    def set_optimize_pos_freq(self, freq):
        """ Set the optimization frequency """
        self._optimize_pos_freq = freq
        self.sigOptPosFreqChanged.emit(self._optimize_pos_freq)
        return freq

    def get_optimize_pos_freq(self):
        """ Get the optimization frequency

        @return float: Optimization frequency in 1/steps"""
        return self._optimize_pos_freq

    def get_optimize_pos(self):
        """ Retrieve whether the optimize position is set.

        @return bool: whether the optimize_pos is set or not.
        """
        return self._optimize_pos

    def set_fluorescence_integration_time(self, integration_time):
        """ Set the integration time """
        self._fluorescence_integration_time = integration_time
        self.sigFluoIntTimeChanged.emit(self._fluorescence_integration_time)
        return integration_time

    def get_fluorescence_integration_time(self):
        """ Get the fluorescence integration time.

        @return float: Integration time in seconds
        """
        return self._fluorescence_integration_time

    ##### 2D alignment settings

    # TODO: Check hardware constraints

    def set_align_2d_axis0_name(self, axisname):
        """Set the specified value """
        self.align_2d_axis0_name = axisname
        self.sig2DAxis0NameChanged.emit(axisname)
        return axisname

    def set_align_2d_axis0_range(self, axis_range):
        """Set the specified value """
        self.align_2d_axis0_range = axis_range
        self.sig2DAxis0RangeChanged.emit(axis_range)
        return axis_range

    def set_align_2d_axis0_step(self, step):
        """Set the specified value """
        self.align_2d_axis0_step = step
        self.sig2DAxis0StepChanged.emit(step)
        return step

    def set_align_2d_axis0_vel(self, vel):
        """Set the specified value """
        self.align_2d_axis0_vel = vel
        self.sig2DAxis0VelChanged.emit(vel)
        return vel

    def set_align_2d_axis1_name(self, axisname):
        """Set the specified value """
        self.align_2d_axis1_name = axisname
        self.sig2DAxis1NameChanged.emit(axisname)
        return axisname

    def set_align_2d_axis1_range(self, axis_range):
        """Set the specified value """
        self.align_2d_axis1_range = axis_range
        self.sig2DAxis1RangeChanged.emit(axis_range)
        return axis_range

    def set_align_2d_axis1_step(self, step):
        """Set the specified value """
        self.align_2d_axis1_step = step
        self.sig2DAxis1StepChanged.emit(step)
        return step

    def set_align_2d_axis1_vel(self, vel):
        """Set the specified value """
        self._2d_align_axis1_vel = vel
        self.sig2DAxis1VelChanged.emit(vel)
        return vel
    
    def set_align_2d_axis2_range(self, axis_range):
        """Set the specified value """
        self.align_2d_axis2_range = axis_range
        self.sig2DAxis2RangeChanged.emit(axis_range)
        return axis_range

    def get_align_2d_axis0_name(self):
        """Return the current value"""
        return self.align_2d_axis0_name

    def get_align_2d_axis0_range(self):
        """Return the current value"""
        return self.align_2d_axis0_range

    def get_align_2d_axis0_step(self):
        """Return the current value"""
        return self.align_2d_axis0_step

    def get_align_2d_axis0_vel(self):
        """Return the current value"""
        return self.align_2d_axis0_vel

    def get_align_2d_axis1_name(self):
        """Return the current value"""
        return self.align_2d_axis1_name

    def get_align_2d_axis1_range(self):
        """Return the current value"""
        return self.align_2d_axis1_range

    def get_align_2d_axis1_step(self):
        """Return the current value"""
        return self.align_2d_axis1_step

    def get_align_2d_axis1_vel(self):
        """Return the current value"""
        return self.align_2d_axis1_vel
    
    def get_align_2d_axis2_range(self):
        """Return the current value"""
        return self.align_2d_axis2_range



