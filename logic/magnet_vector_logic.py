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
    ---
    """

    # declare connectors
    magnetstage = Connector(interface='MagnetInterface')
    counterlogic = Connector(interface='CounterLogic')
    savelogic = Connector(interface='SaveLogic')
    fitlogic = Connector(interface='FitLogic')

    align_2d_axis0_name = StatusVar('align_2d_axis0_name', 'theta')
    align_2d_axis1_name = StatusVar('align_2d_axis1_name', 'phi')
    align_2d_axis2_name = StatusVar('align_2d_axis2_name', 'rho')

    align_2d_axis2_range = StatusVar('align_2d_axis2_range', 0.1)
    align_2d_axis2_step = StatusVar('align_2d_axis2_step', 1e-3)
    
    align_2d_axis0_range = StatusVar('align_2d_axis0_range', 180)
    align_2d_axis0_step = StatusVar('align_2d_axis0_step', 0.1)
    
    align_2d_axis1_range = StatusVar('align_2d_axis1_range', 360)
    align_2d_axis1_step = StatusVar('align_2d_axis1_step', 0.1)
    
    curr_2d_pathway_mode = StatusVar('curr_2d_pathway_mode', 'snake-wise')

    _checktime = StatusVar('_checktime', 0.1)
    
    _2D_axis0_data = StatusVar('_2D_axis0_data', default=np.arange(3))
    _2D_axis1_data = StatusVar('_2D_axis1_data', default=np.arange(2))

    _2D_data_matrix = StatusVar('_2D_data_matrix', np.zeros((3, 2)))


    curr_alignment_method = StatusVar('curr_alignment_method', '2d_fluorescence')

    _fluorescence_integration_time = StatusVar('_fluorescence_integration_time', 1)
    
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

    _sigStepwiseAlignmentNext = QtCore.Signal()
    _sigContinuousAlignmentNext = QtCore.Signal()
    _sigInitializeMeasPos = QtCore.Signal(bool)  # signal to go to the initial measurement position
    sigPosReached = QtCore.Signal()

    # signals if new data are writen to the data arrays (during measurement):
    sig2DMatrixChanged = QtCore.Signal()

    # signals if the axis for the alignment are changed/renewed (before a measurement):
    sig2DAxisChanged = QtCore.Signal()

    # signals for 2d alignemnt general
    sig2DAxis0NameChanged = QtCore.Signal(str)
    sig2DAxis0RangeChanged = QtCore.Signal(float)
    sig2DAxis0StepChanged = QtCore.Signal(float)
    
    sig2DAxis1NameChanged = QtCore.Signal(str)
    sig2DAxis1RangeChanged = QtCore.Signal(float)
    sig2DAxis1StepChanged = QtCore.Signal(float)

    sigMoveRelChanged = QtCore.Signal(dict)

    # signals for fluorescence alignment
    sigFluoIntTimeChanged = QtCore.Signal(float)
    sigOptPosFreqChanged = QtCore.Signal(float)
    sigFitFinished = QtCore.Signal(dict)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self._stop_measure = False

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """
        self._magnet_device = self.magnetstage()
        self._save_logic = self.savelogic()
        self._fit_logic = self.fitlogic()
        self._counter_logic = self.counterlogic()

        self.sigMoveAbs.connect(self._magnet_device.move_abs)
        self.sigMoveRel.connect(self._magnet_device.move_rel)
        self.sigAbort.connect(self._magnet_device.abort)

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

        axes = list(self._magnet_device.get_constraints())
        self.align_2d_axis0_name = axes[3]
        self.align_2d_axis1_name = axes[4]
        self.align_2d_axis2_name = axes[5]

        if '_2D_add_data_matrix' in self._statusVariables:
            self._2D_add_data_matrix = self._statusVariables['_2D_add_data_matrix']
        else:
            self._2D_add_data_matrix = np.zeros(shape=np.shape(self._2D_data_matrix), dtype=object)


        self.alignment_methods = ['2d_fluorescence']
        self._optimize_pos_freq = 0

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

        self.sigMoveAbs.emit(param_dict)
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

    def _create_2d_pathway(self, axis0_name, axis0_range, axis0_step,
                           axis1_name, axis1_range, axis1_step, init_pos, axis0_vel=None, axis1_vel=None):
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

        step_config[axis0_name] = {'move_abs': axis0_pos}
        step_config[axis1_name] = {'move_abs': axis1_pos}

        pathway.append(step_config)

        path_index = 0

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

                # absolute movement:
                axis0_pos = round(axis0_pos + direction * step_in_axis0, 7)

                step_config[axis0_name] = {'move_abs': axis0_pos}
                step_config[axis1_name] = {'move_abs': axis1_pos}

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

            # absolute movement:
            axis1_pos = round(axis1_pos + step_in_axis1, 7)

            step_config[axis0_name] = {'move_abs': axis0_pos}
            step_config[axis1_name] = {'move_abs': axis1_pos}

            pathway.append(step_config)
            axis1_index += 1
            back_map[path_index] = {axis0_name: axis0_pos,
                                    axis1_name: axis1_pos,
                                    'index': (axis0_index, axis1_index)}
            path_index += 1

        return pathway, back_map
    

    def _prepare_2d_graph(self, axis0_start, axis0_range, axis0_step,
                          axis1_start, axis1_range, axis1_step):
     
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

  
    def start_2d_alignment(self, stepwise_meas=True, continue_meas=False):

        # start measurement value
        self._start_measurement_time = datetime.datetime.now()
        self._stop_measurement_time = None

        self._stop_measure = False

        # get name of other axis to control their values
        pos_dict = self.get_pos()
        self._control_dict = {'rho': pos_dict['rho'], 'theta': pos_dict['theta'], 'phi': pos_dict['phi']}

        # additional values to save
        self._2d_error = []
        self._2d_measured_fields = []
        self._2d_intended_fields = []

        self._saved_pos_before_align = {key: pos_dict[key] for key in [self.align_2d_axis0_name, self.align_2d_axis1_name]}

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
                                                                   self._saved_pos_before_align)

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

        else:
            # tell all the connected instances that measurement is continuing:
            self.sigMeasurementContinued.emit()

        # run at first the _move_to_curr_pathway_index method to go to the
        # index position:
        self._sigInitializeMeasPos.emit(stepwise_meas)
        return 0

    def _move_to_curr_pathway_index(self, stepwise_meas):
        # move absolute to the index position, which is currently given

        move_dict_abs = self._move_to_index(self._pathway_index, self._pathway)
        self.log.debug(f'Move to index: {move_dict_abs}')
        ret = self._magnet_device.move_abs(move_dict_abs)
        if ret == -1:
            self._stop_measure = True
        self.log.debug('Done move to index')

        # while self._check_is_moving():
        #     time.sleep(self._checktime)
        #     self.log.debug("Went into while loop in _move_to_curr_pathway_index")

        # this function will return to this function if position is reached:
        self.time_prev = time.monotonic()
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
        self.log.debug('Entered stepwise loop body')
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
            self._do_premeasurement_proc()
            move_dict_abs = self._move_to_index(self._pathway_index, self._pathway)

            ret = self._magnet_device.move_abs(move_dict_abs)
            if ret == -1:
                self._stop_measure = True

            while self._check_is_moving():
                time.sleep(self._checktime)
                # self.log.debug("Went into while loop in stepwise_loop_body")

            self.log.info(f'Position: {self._pathway_index+1}/{len(self._pathway)} ({(self._pathway_index+1)/len(self._pathway)*100:.2f}%)')
            time_now = time.monotonic()
            total_time = round((time_now - self.time_prev)/(self._pathway_index + 1) * (len(self._pathway))/60/60,3)
            time_rem = round(total_time - (time_now - self.time_prev)/60/60,3)
            
            self.log.info(f'Time remaining: {time_rem}/{total_time}hrs')
            curr_pos = self.get_pos(['x','y','z',self.align_2d_axis0_name, self.align_2d_axis1_name, self.align_2d_axis2_name])
            self.sigPosChanged.emit(curr_pos)

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


    def stop_alignment(self):
        """ Stops any kind of ongoing alignment measurement by setting a flag.
        """
        self._stop_measure = True
        
        return 

    def _end_alignment_procedure(self):
        last_pos = dict()
        try:
            for axis_name in self._saved_pos_before_align:
                last_pos[axis_name] = self._backmap[self._pathway_index - 1][axis_name]

            ret = self._magnet_device.move_abs(self._saved_pos_before_align)
            if ret == -1:
                self._stop_measure = True
        except:
            self.log.debug('Stopped too quick. Missed something here.')

        while self._check_is_moving():
            time.sleep(self._checktime)

        self.sigMeasurementFinished.emit()
        self._pathway_index = 0
        self._stop_measurement_time = datetime.datetime.now()
        self.log.info('Alignment Complete!')
        
        return

    def _check_is_moving(self):
        """

        @return bool: True indicates the magnet is moving, False the magnet stopped movement
        """
        # get axis names
        axes = list(self._magnet_device.get_constraints().keys())
        state = self._magnet_device.get_status()

        return not (state[axes[0]] and state[axes[1]] and state[axes[2]])

    def _set_meas_point(self, meas_val, add_meas_val, pathway_index, back_map):

        # map the point back to the position in the measurement array
        index_array = back_map[pathway_index]['index']

        if np.shape(index_array)[0] == 2:

            self._2D_data_matrix[index_array] = meas_val
            self._2D_add_data_matrix[index_array] = add_meas_val

            self.sig2DMatrixChanged.emit()

        else:
            self.log.error('The measurement point "{0}" could not be set in '
                           'the _set_meas_point routine'.format(pathway_index))

        return

    def _do_premeasurement_proc(self):
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
        # self._qafm_logic.default_optimize(run_in_thread=False)
        return 0

    def _do_alignment_measurement(self):
        """ That is the main method which contains all functions with measurement routines.
        Save each measured value as an item to a keyword string, i.e.
            {'ODMR frequency (MHz)': <the_parameter>, ...}
        The save routine will handle the additional information and save them
        properly.
        @return tuple(float, dict): the measured value is of type float and the
                                    additional parameters are saved in a
                                    dictionary form.
        """

        # self.alignment_methods = ['fluorescence_pointwise', 'fluorescence_continuous', 'odmr_splitting', 'odmr_hyperfine_splitting', 'nuclear_spin_measurement']
        if self.curr_alignment_method == '2d_fluorescence':
            data, add_data = self._perform_fluorescence_measure()
        
        return data, add_data

    def _perform_fluorescence_measure(self):

        measurement = self._counter_logic._counting_device.countrate
        measurement.startFor(int(self._fluorescence_integration_time*1e12)) # using timetaggers inbuilt start for particular duration function. 
        measurement.waitUntilFinished()
        
        data_array = measurement.getData()
        return data_array.mean(), {'Integration time (s)' : self._fluorescence_integration_time}

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
        axes = ['theta', 'phi']

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
        # add_data = OrderedDict()
        # axis0_data = np.zeros(len(self._backmap))
        # axis1_data = np.zeros(len(self._backmap))
        # param_data = np.zeros(len(self._backmap), dtype='object')

        # for backmap_index in self._backmap:
        #     axis0_data[backmap_index] = self._backmap[backmap_index][self.align_2d_axis0_name]
        #     axis1_data[backmap_index] = self._backmap[backmap_index][self.align_2d_axis1_name]
        #     param_data[backmap_index] = str(self._2D_add_data_matrix[self._backmap[backmap_index]['index']])

        # constr = self.get_hardware_constraints()
        # units_axis0 = constr[self.align_2d_axis0_name]['unit']
        # units_axis1 = constr[self.align_2d_axis1_name]['unit']

        # add_data['{0} values ({1})'.format(self.align_2d_axis0_name, units_axis0)] = axis0_data
        # add_data['{0} values ({1})'.format(self.align_2d_axis1_name, units_axis1)] = axis1_data
        # # add_data['all measured additional parameter'] = param_data

        # self._save_logic.save_data(add_data, filepath=filepath, filelabel=filelabel2,
        #                            timestamp=timestamp)
        # save the data table

        # count_data = self._2D_data_matrix
        # x_val = self._2D_axis0_data
        # y_val = self._2D_axis1_data
        # save_dict = OrderedDict()
        # axis0_key = '{0} values ({1})'.format(self.align_2d_axis0_name, units_axis0)
        # axis1_key = '{0} values ({1})'.format(self.align_2d_axis1_name, units_axis1)
        # counts_key = 'counts (c/s)'
        # save_dict[axis0_key] = []
        # save_dict[axis1_key] = []
        # save_dict[counts_key] = []

        # for ii, columns in enumerate(count_data):
        #     for jj, col_counts in enumerate(columns):
        #         # x_list = [x_val[ii]] * len(countlist)
        #         save_dict[axis0_key].append(x_val[ii])
        #         save_dict[axis1_key].append(y_val[jj])
        #         save_dict[counts_key].append(col_counts)
        # save_dict[axis0_key] = np.array(save_dict[axis0_key])
        # save_dict[axis1_key] = np.array(save_dict[axis1_key])
        # save_dict[counts_key] = np.array(save_dict[counts_key])

        # # making saveable dictionaries

        # self._save_logic.save_data(save_dict, filepath=filepath, filelabel=filelabel3,
        #                            timestamp=timestamp, fmt='%.6e')
        keys = self._2d_intended_fields[0].keys()
        intended_fields = OrderedDict()
        for key in keys:
            field_values = [coord_dict[key] for coord_dict in self._2d_intended_fields]
            intended_fields[key] = field_values

        self._save_logic.save_data(intended_fields, filepath=filepath, filelabel=filelabel4,
                                   timestamp=timestamp)

        # measured_fields = OrderedDict()
        # for key in keys:
        #     field_values = [coord_dict[key] for coord_dict in self._2d_measured_fields]
        #     measured_fields[key] = field_values

        # self._save_logic.save_data(measured_fields, filepath=filepath, filelabel=filelabel5,
        #                            timestamp=timestamp)

        # error = OrderedDict()
        # error['quadratic error'] = self._2d_error

        # self._save_logic.save_data(error, filepath=filepath, filelabel=filelabel6,
        #                            timestamp=timestamp)

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
            cbar_range = [np.min(data)-np.min(data)*0.005, np.max(data)+np.max(data)*0.005]

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

        ax.set_aspect('auto')
        ax.set_xlabel(scan_axis[0] + ' (' + x_prefix + 'deg)')
        ax.set_ylabel(scan_axis[1] + ' (' + y_prefix + 'deg)')
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

        move_commmands = pathway[pathway_index]
        move_commmands[self.align_2d_axis2_name] = {'move_abs' : self._control_dict[self.align_2d_axis2_name]}
        move_dict_abs = dict()

        for axis_name in move_commmands:
            if move_commmands[axis_name].get('move_abs') is not None:
                move_dict_abs[axis_name] = move_commmands[axis_name]['move_abs']

        return move_dict_abs

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
        fit_x, fit_y = np.meshgrid(self._2D_axis1_data, self._2D_axis0_data)
        xy_fit_data = self._2D_data_matrix.ravel()

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
        #     if result_2D_gaus.best_values['center_x']>2*np.pi:
        #         result_2D_gaus.best_values['center_x'] -= 2*np.pi
        #     if result_2D_gaus.best_values['center_y']>2*np.pi:
        #         result_2D_gaus.best_values['center_y'] -= 2*np.pi
        #     if result_2D_gaus.best_values['center_x']<0:
        #         result_2D_gaus.best_values['center_x'] += 2*np.pi
        #     if result_2D_gaus.best_values['center_y']<0:
        #         result_2D_gaus.best_values['center_y'] += 2*np.pi
            self.optim_pos_x = result_2D_gaus.best_values['center_y']
            self.optim_pos_y = result_2D_gaus.best_values['center_x']
            self.optim_sigma_x = result_2D_gaus.best_values['sigma_y']
            self.optim_sigma_y = result_2D_gaus.best_values['sigma_x']

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
        return 0

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

    def get_align_2d_axis1_name(self):
        """Return the current value"""
        return self.align_2d_axis1_name

    def get_align_2d_axis1_range(self):
        """Return the current value"""
        return self.align_2d_axis1_range

    def get_align_2d_axis1_step(self):
        """Return the current value"""
        return self.align_2d_axis1_step
    
    def get_align_2d_axis2_range(self):
        """Return the current value"""
        return self.align_2d_axis2_range



