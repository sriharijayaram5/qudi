# -*- coding: utf-8 -*-

"""
This file contains the GUI for magnet control.

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

import datetime
from hashlib import new
import numpy as np
import os
import pyqtgraph as pg
import pyqtgraph.exporters
from qtpy import uic

import matplotlib as mpl
from matplotlib import cm
import pyqtgraph.opengl as gl
from core.connector import Connector
from core.statusvariable import StatusVar
from gui.colordefs import ColorScaleViridis
from gui.guibase import GUIBase
from gui.guiutils import ColorBar
from qtpy import QtCore, QtGui
from qtpy import QtWidgets
from qtwidgets.scientific_spinbox import ScienDSpinBox
from qtwidgets.scan_plotwidget import ScanImageItem


class CrossLine(pg.InfiniteLine):

    """ Construct one line for the Crosshair in the plot.

    @param float pos: optional parameter to set the position
    @param float angle: optional parameter to set the angle of the line
    @param dict pen: Configure the pen.

    For additional options consider the documentation of pyqtgraph.InfiniteLine
    """

    def __init__(self, **args):
        pg.InfiniteLine.__init__(self, **args)
#        self.setPen(QtGui.QPen(QtGui.QColor(255, 0, 255),0.5))

    def adjust(self, extroi):
        """
        Run this function to adjust the position of the Crosshair-Line

        @param object extroi: external roi object from pyqtgraph
        """
        if self.angle == 0:
            self.setValue(extroi.pos()[1] + extroi.size()[1] * 0.5)
        if self.angle == 90:
            self.setValue(extroi.pos()[0] + extroi.size()[0] * 0.5)


class MagnetMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_magnet_vector_gui.ui')

        # Load it
        super(MagnetMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()


class MagnetSettingsWindow(QtWidgets.QDialog):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_magnet_settings.ui')

        # Load it
        super(MagnetSettingsWindow, self).__init__()

        uic.loadUi(ui_file, self)


class MagnetGui(GUIBase):
    """ Main GUI for the magnet. """

    # declare connectors
    magnetlogic1 = Connector(interface='MagnetLogic')
    savelogic = Connector(interface='SaveLogic')

    # status var
    _alignment_2d_cb_label = StatusVar('alignment_2d_cb_GraphicsView_text', 'Fluorescence')
    _alignment_2d_cb_units = StatusVar('alignment_2d_cb_GraphicsView_units', 'counts/s')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self._continue_2d_fluorescence_alignment = False

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """
        self._magnet_logic = self.magnetlogic1()
        self._save_logic = self.savelogic()

        self._mw = MagnetMainWindow()
        self._2d_alignment_ImageItem = None
        self._mw.curr_pos_get_pos_PushButton.clicked.connect(self.update_pos)
        self._mw.curr_pos_stop_PushButton.clicked.connect(self.stop_movement)
        self._mw.move_abs_PushButton.clicked.connect(self.move_abs)
        self._mw.move_abs_PushButton.clicked.connect(self.update_roi_from_abs_movement)
        self._create_move_rel_control()
        self._create_move_abs_control()
        self.last_pos = {'rho':0.0}

        # Configuring the dock widgets
        # Use the class 'MagnetMainWindow' to create the GUI window

        self._mw.align_2d_axis0_name_ComboBox.clear()
        self._mw.align_2d_axis0_name_ComboBox.addItems(['theta', 'phi'])
        self._mw.align_2d_axis0_name_ComboBox.setCurrentIndex(0)
        self._mw.align_2d_axis0_name_ComboBox.setEnabled(False)

        self._mw.align_2d_axis1_name_ComboBox.clear()
        self._mw.align_2d_axis1_name_ComboBox.addItems(['phi', 'theta'])
        self._mw.align_2d_axis1_name_ComboBox.setCurrentIndex(0)
        self._mw.align_2d_axis1_name_ComboBox.setEnabled(False)

        # Setup dock widgets
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)
        self.set_default_view_main_window()

        self._interactive_mode = True
        self._activate_magnet_settings()

        # connect the actions of the toolbar:
        self._mw.magnet_settings_Action.triggered.connect(self.open_magnet_settings)
        self._mw.default_view_Action.triggered.connect(self.set_default_view_main_window)

        curr_pos = self.update_pos()
        # update the values also of the absolute movement display:
        for axis_label in curr_pos:
            if axis_label in ['x','y','z']:
                continue
            dspinbox_move_abs_ref = self.get_ref_move_abs_ScienDSpinBox(axis_label)
            dspinbox_move_abs_ref.setValue(curr_pos[axis_label])
            slider_move_abs_ref = self.get_ref_move_abs_Slider(axis_label)
            slider_move_abs_ref.setValue(curr_pos[axis_label])

        self._magnet_logic.sigPosChanged.connect(self.update_pos)
        self._mw.fitFluorescence_pushButton.clicked.connect(self._magnet_logic._set_optimized_xy_from_fit)

        # Connect alignment GUI elements:

        self._magnet_logic.sigMeasurementFinished.connect(self._change_display_to_stop_2d_alignment)

        self._mw.align_2d_axis0_name_ComboBox.currentIndexChanged.connect(self._update_limits_axis0)
        self._mw.align_2d_axis1_name_ComboBox.currentIndexChanged.connect(self._update_limits_axis1)

        self._mw.alignment_2d_cb_min_centiles_DSpinBox.valueChanged.connect(self._update_2d_graph_data)
        self._mw.alignment_2d_cb_max_centiles_DSpinBox.valueChanged.connect(self._update_2d_graph_data)
        self._mw.alignment_2d_cb_low_centiles_DSpinBox.valueChanged.connect(self._update_2d_graph_data)
        self._mw.alignment_2d_cb_high_centiles_DSpinBox.valueChanged.connect(self._update_2d_graph_data)

        self._update_limits_axis0()
        self._update_limits_axis1()

        self._2d_alignment_ImageItem = ScanImageItem(image=self._magnet_logic.get_2d_data_matrix())
        self._mw.alignment_2d_GraphicsView.addItem(self._2d_alignment_ImageItem)
        axis0, axis1 = self._magnet_logic.get_2d_axis_arrays()
        step0 = axis0[1] - axis0[0]
        step1 = axis1[1] - axis1[0]
        self._2d_alignment_ImageItem.set_image_extent([[axis0[0]-step0/2, axis0[-1]+step0/2],
                                                       [axis1[0]-step1/2, axis1[-1]+step1/2]])
        
        my_colors = ColorScaleViridis()
        self._2d_alignment_ImageItem.setLookupTable(my_colors.lut)

        # Set initial position for the crosshair, default is current magnet position
        current_position = curr_pos
        current_2d_array = self._magnet_logic.get_2d_axis_arrays()
        ini_pos_x_crosshair = current_position[self._magnet_logic.align_2d_axis0_name]
        ini_pos_y_crosshair = current_position[self._magnet_logic.align_2d_axis1_name]

        ini_width_crosshair = [
            (current_2d_array[0][-1] - current_2d_array[0][0]) / len(current_2d_array[0]),
            (current_2d_array[1][-1] - current_2d_array[1][0]) / len(current_2d_array[1])]
        self._mw.alignment_2d_GraphicsView.toggle_crosshair(True, movable=True)
        self._mw.alignment_2d_GraphicsView.set_crosshair_pos((ini_pos_x_crosshair, ini_pos_y_crosshair))
        self._mw.alignment_2d_GraphicsView.set_crosshair_size(ini_width_crosshair)
        self._mw.alignment_2d_GraphicsView.sigCrosshairDraggedPosChanged.connect(
            self.update_from_roi_magnet)

        # Configuration of Colorbar:
        self._2d_alignment_cb = ColorBar(my_colors.cmap_normed, 100, 0, 100000)

        self._mw.alignment_2d_cb_GraphicsView.addItem(self._2d_alignment_cb)
        self._mw.alignment_2d_cb_GraphicsView.hideAxis('bottom')
        self._mw.alignment_2d_cb_GraphicsView.hideAxis('left')

        self._mw.alignment_2d_cb_GraphicsView.addItem(self._2d_alignment_cb)

        self._mw.alignment_2d_cb_GraphicsView.setLabel('right',
            self._alignment_2d_cb_label,
            units=self._alignment_2d_cb_units)

        self.measurement_type = 'fluorescence'

        self._magnet_logic.sig2DAxisChanged.connect(self._update_2d_graph_axis)
        self._magnet_logic.sig2DMatrixChanged.connect(self._update_2d_graph_data)

        # Connect the buttons and inputs for the odmr colorbar
        self._mw.alignment_2d_manual_RadioButton.clicked.connect(self._update_2d_graph_data)
        self._mw.alignment_2d_centiles_RadioButton.clicked.connect(self._update_2d_graph_data)

        self._update_2d_graph_data()
        self._update_2d_graph_cb()

        self._mw.alignment_2d_cb_high_centiles_DSpinBox.setValue(100)

        # Add save file tag input box
        self._mw.alignment_2d_nametag_LineEdit = QtWidgets.QLineEdit(self._mw)
        self._mw.alignment_2d_nametag_LineEdit.setMaximumWidth(200)
        self._mw.alignment_2d_nametag_LineEdit.setToolTip('Enter a nametag which will be\n'
                                                          'added to the filename.')

        self._mw.save_ToolBar.addWidget(self._mw.alignment_2d_nametag_LineEdit)
        self._mw.save_Action.triggered.connect(self.save_2d_plots_and_data)

        self._mw.run_stop_2d_alignment_Action.triggered.connect(self.run_stop_2d_alignment)
        self._mw.continue_2d_alignment_Action.triggered.connect(self.continue_stop_2d_alignment)

        # connect the signals:
        # --------------------

        # relative movement:

        constraints=self._magnet_logic.get_hardware_constraints()

        for axis_label in list(constraints):
            if axis_label in ['x','y','z']:
                continue
            self.get_ref_move_rel_ScienDSpinBox(axis_label).setValue(self._magnet_logic.move_rel_dict[axis_label])
            self.get_ref_move_rel_ScienDSpinBox(axis_label).editingFinished.connect(self.move_rel_para_changed)

        # General 2d alignment:
        # index = self._mw.align_2d_axis0_name_ComboBox.findText(self._magnet_logic.align_2d_axis0_name)
        # self._mw.align_2d_axis0_name_ComboBox.setCurrentIndex(index)
        # self._mw.align_2d_axis0_name_ComboBox.currentIndexChanged.connect(self.align_2d_axis0_name_changed)
        self._mw.align_2d_axis0_range_DSpinBox.setValue(self._magnet_logic.align_2d_axis0_range)
        self._mw.align_2d_axis0_range_DSpinBox.editingFinished.connect(self.align_2d_axis0_range_changed)
        self._mw.align_2d_axis0_range_DSpinBox.editingFinished.connect(self.update_roi_from_range)
        self._mw.align_2d_axis0_step_DSpinBox.setValue(self._magnet_logic.align_2d_axis0_step)
        self._mw.align_2d_axis0_step_DSpinBox.editingFinished.connect(self.align_2d_axis0_step_changed)

        # index = self._mw.align_2d_axis1_name_ComboBox.findText(self._magnet_logic.align_2d_axis1_name)
        # self._mw.align_2d_axis1_name_ComboBox.setCurrentIndex(index)
        # self._mw.align_2d_axis1_name_ComboBox.currentIndexChanged.connect(self.align_2d_axis1_name_changed)
        self._mw.align_2d_axis1_range_DSpinBox.setValue(self._magnet_logic.align_2d_axis1_range)
        self._mw.align_2d_axis1_range_DSpinBox.editingFinished.connect(self.align_2d_axis1_range_changed)
        self._mw.align_2d_axis1_range_DSpinBox.editingFinished.connect(self.update_roi_from_range)
        self._mw.align_2d_axis1_step_DSpinBox.setValue(self._magnet_logic.align_2d_axis1_step)
        self._mw.align_2d_axis1_step_DSpinBox.editingFinished.connect(self.align_2d_axis1_step_changed)

        # for fluorescence alignment:
        self._mw.align_2d_fluorescence_optimize_freq_SpinBox.setValue(self._magnet_logic.get_optimize_pos_freq())
        self._mw.align_2d_fluorescence_integrationtime_DSpinBox.setValue(self._magnet_logic.get_fluorescence_integration_time())
        self._mw.align_2d_fluorescence_optimize_freq_SpinBox.editingFinished.connect(self.optimize_pos_freq_changed)
        self._mw.align_2d_fluorescence_integrationtime_DSpinBox.editingFinished.connect(self.fluorescence_integration_time_changed)

        # process signals from magnet_logic

        self._magnet_logic.sigMoveRelChanged.connect(self.update_move_rel_para)

        self._magnet_logic.sig2DAxis0NameChanged.connect(self.update_align_2d_axis0_name)
        self._magnet_logic.sig2DAxis0RangeChanged.connect(self.update_align_2d_axis0_range)
        self._magnet_logic.sig2DAxis0StepChanged.connect(self.update_align_2d_axis0_step)

        self._magnet_logic.sig2DAxis1NameChanged.connect(self.update_align_2d_axis1_name)
        self._magnet_logic.sig2DAxis1RangeChanged.connect(self.update_align_2d_axis1_range)
        self._magnet_logic.sig2DAxis1StepChanged.connect(self.update_align_2d_axis1_step)

        self._magnet_logic.sigOptPosFreqChanged.connect(self.update_optimize_pos_freq)
        self._magnet_logic.sigFluoIntTimeChanged.connect(self.update_fluorescence_integration_time)

        self.restoreWindowPos(self._mw)
        return 0

    def _activate_magnet_settings(self):
        """ Activate magnet settings.
        """
        self._ms = MagnetSettingsWindow()
        # default config is normal_mode
        self._ms.normal_mode_checkBox.setChecked(True)
        self._ms.z_mode_checkBox.setChecked(False)
        # make sure the buttons are exclusively checked
        self._ms.normal_mode_checkBox.stateChanged.connect(self.trig_wrapper_normal_mode)
        self._ms.z_mode_checkBox.stateChanged.connect(self.trig_wrapper_z_mode)

        #self._ms.z_mode_checkBox.stateChanged.connect(self._ms.normal_mode_checkBox.toggle)
        self._ms.accepted.connect(self.update_magnet_settings)
        self._ms.rejected.connect(self.keep_former_magnet_settings)
        self._ms.ButtonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.update_magnet_settings)

        self.keep_former_magnet_settings()
        return

    def trig_wrapper_normal_mode(self):
        if not self._ms.normal_mode_checkBox.isChecked() and not self._ms.z_mode_checkBox.isChecked():
            self._ms.z_mode_checkBox.toggle()
        elif self._ms.normal_mode_checkBox.isChecked() and self._ms.z_mode_checkBox.isChecked():
            self._ms.z_mode_checkBox.toggle()

    def trig_wrapper_z_mode(self):
        if not self._ms.normal_mode_checkBox.isChecked() and not self._ms.z_mode_checkBox.isChecked():
            self._ms.normal_mode_checkBox.toggle()
        elif self._ms.normal_mode_checkBox.isChecked() and self._ms.z_mode_checkBox.isChecked():
            self._ms.normal_mode_checkBox.toggle()

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        self._alignment_2d_cb_label =  self._mw.alignment_2d_cb_GraphicsView.plotItem.axes['right']['item'].labelText
        self._alignment_2d_cb_units = self._mw.alignment_2d_cb_GraphicsView.plotItem.axes['right']['item'].labelUnits
        self.saveWindowGeometry(self._mw)
        self._mw.close()

    def show(self):
        """Make window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def set_default_view_main_window(self):
        """ Establish the default dock Widget configuration. """

        # connect all widgets to the main Window
        self._mw.curr_pos_DockWidget.setFloating(False)
        self._mw.move_rel_DockWidget.setFloating(False)
        self._mw.move_abs_DockWidget.setFloating(False)
        self._mw.alignment_DockWidget.setFloating(False)

        # QtCore.Qt.LeftDockWidgetArea        0x1
        # QtCore.Qt.RightDockWidgetArea       0x2
        # QtCore.Qt.TopDockWidgetArea         0x4
        # QtCore.Qt.BottomDockWidgetArea      0x8
        # QtCore.Qt.AllDockWidgetAreas        DockWidgetArea_Mask
        # QtCore.Qt.NoDockWidgetArea          0

        # align the widget
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(1),
                               self._mw.curr_pos_DockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(1),
                               self._mw.move_rel_DockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(1),
                               self._mw.move_abs_DockWidget)

        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2),
                               self._mw.alignment_DockWidget)

    def open_magnet_settings(self):
        """ This method opens the settings menu. """
        self._ms.exec_()

    def update_magnet_settings(self):
        """ Apply the set configuration in the Settings Window. """

        if self._ms.interactive_mode_CheckBox.isChecked():
            self._interactive_mode = True
        else:
            self._interactive_mode = False
        if self._ms.z_mode_checkBox.isChecked() and not self._ms.normal_mode_checkBox.isChecked():
            self.log.warning("dum dum")

        if self._ms.normal_mode_checkBox.isChecked() and not self._ms.z_mode_checkBox.isChecked():
            self.log.warning("dam dam")

        if self._ms.interactive_mode_CheckBox.isChecked():
            self._interactive_mode = True
        else:
            self._interactive_mode = False
        if self._ms.z_mode_checkBox.isChecked():
            self._z_mode = True
            self._magnet_logic._magnet_device.mode = 'z_mode'
        else:
            self._z_mode = False
            self._magnet_logic._magnet_device.mode = 'normal_mode'

        if self._ms.normal_mode_checkBox.isChecked():
            self._normal_mode = True
            self._magnet_logic._magnet_device.mode = 'normal_mode'
        else:
            self._normal_mode = False
            self._magnet_logic._magnet_device.mode = 'z_mode'

    def keep_former_magnet_settings(self):

        self._ms.interactive_mode_CheckBox.setChecked(self._interactive_mode)
        
    def _create_move_rel_control(self):
        """ Create all the gui elements to control a relative movement.

        The generic variable name for a created QLable is:
            move_rel_axis_{0}_Label
        The generic variable name for a created ScienDSpinBox is:
            move_rel_axis_{0}_ScienDSpinBox
        The generic variable name for a created QPushButton in negative dir is:
            move_rel_axis_{0}_m_PushButton
        The generic variable name for a created QPushButton in positive dir is:
            move_rel_axis_{0}_p_PushButton

        DO NOT CALL THESE VARIABLES DIRECTLY! USE THE DEDICATED METHOD INSTEAD!
        Use the method get_ref_move_rel_ScienDSpinBox with the appropriated
        label, otherwise you will break the generality.
        """

        constraints = self._magnet_logic.get_hardware_constraints()

        # set the axis_labels in the curr_pos_DockWidget:
        for axis_label in constraints:
            if axis_label in ['x','y','z']:
                continue

            # Set the ScienDSpinBox according to the grid
            # this is the name prototype for the relative movement display
            dspinbox_ref_name = 'move_rel_{0}_ScienDSpinBox'.format(axis_label)
            dspinbox_ref = getattr(self._mw, dspinbox_ref_name)

            dspinbox_ref.setMaximum(constraints[axis_label]['pos_max'])
            dspinbox_ref.setMinimum(constraints[axis_label]['pos_min'])
            dspinbox_ref.setSuffix(constraints[axis_label]['unit'])

            # this is the name prototype for the relative movement minus button
            func_name = 'move_rel_axis_{0}_m'.format(axis_label)
            # create a method and assign it as attribute:
            setattr(self, func_name, self._function_builder_move_rel(func_name,axis_label,-1) )
            move_rel_m_ref =  getattr(self, func_name)  # get the reference

            # the change of the PushButton is connected to the previous method.
            button_var_name = 'move_rel_{0}_m_PushButton'.format(axis_label)
            button_var = getattr(self._mw, button_var_name)
            button_var.clicked.connect(move_rel_m_ref, type=QtCore.Qt.QueuedConnection)

            # this is the name prototype for the relative movement plus button
            func_name = 'move_rel_{0}_p'.format(axis_label)
            setattr(self, func_name, self._function_builder_move_rel(func_name,axis_label,1) )
            move_rel_p_ref = getattr(self, func_name)

            # the change of the PushButton is connected to the previous method.
            button_var_name = 'move_rel_{0}_p_PushButton'.format(axis_label)
            button_var = getattr(self._mw, button_var_name)
            button_var.clicked.connect(move_rel_p_ref, type=QtCore.Qt.QueuedConnection)

    def _create_move_abs_control(self):
        """ Create all the GUI elements to control a relative movement.
        """
        constraints = self._magnet_logic.get_hardware_constraints()

        for axis_label in constraints:
            if axis_label in ['x','y','z']:
                continue

            slider = 'move_abs_{0}_Slider'.format(axis_label)
            slider = getattr(self._mw, slider) # get the reference

            dspinbox = 'move_abs_{0}_DoubleSpinBox'.format(axis_label)
            dspinbox = getattr(self._mw, dspinbox) # get the reference

            dspinbox.setMaximum(constraints[axis_label]['pos_max'])
            dspinbox.setMinimum(constraints[axis_label]['pos_min'])

            slider.setMaximum(constraints[axis_label]['pos_max']/constraints[axis_label]['pos_step'])
            slider.setMinimum(constraints[axis_label]['pos_min']/constraints[axis_label]['pos_step'])
            
            # build a function to change the dspinbox value and connect a
            # slidermove event to it:
            func_name = '_update_move_abs_{0}_dspinbox'.format(axis_label)
            setattr(self, func_name, self._function_builder_update_viewbox(func_name, axis_label, dspinbox))
            update_func_dspinbox_ref = getattr(self, func_name)
            slider.valueChanged.connect(update_func_dspinbox_ref)

            # build a function to change the slider value and connect a
            # spinbox value change event to it:
            func_name = '_update_move_abs_{0}_slider'.format(axis_label)
            setattr(self, func_name, self._function_builder_update_slider(func_name, axis_label, slider))
            update_func_slider_ref = getattr(self, func_name)
            dspinbox.valueChanged.connect(update_func_slider_ref)

    def _function_builder_move_rel(self, func_name, axis_label, direction):
        """ Create a function/method, which gets executed for pressing move_rel.

        @param str func_name: name how the function should be called.
        @param str axis_label: label of the axis you want to create a control
                               function for.
        @param int direction: either 1 or -1 depending on the relative movement.
        @return: function with name func_name

        A routine to construct a method on the fly and attach it as attribute
        to the object, so that it can be used or so that other signals can be
        connected to it. That means the return value is already fixed for a
        function name.
        """

        def func_dummy_name():
            self.move_rel(axis_label, direction)

        func_dummy_name.__name__ = func_name
        return func_dummy_name


    def _function_builder_update_viewbox(self, func_name, axis_label,
                                         ref_dspinbox):
        """ Create a function/method, which gets executed for pressing move_rel.

        @param str func_name: name how the function should be called.
        @param str axis_label: label of the axis you want to create a control
                               function for.
        @param object ref_dspinbox: a reference to the dspinbox object, which
                                    will actually apply the changed within the
                                    created method.

        @return: function with name func_name
        """

        def func_dummy_name(slider_val):
            """
            @param int slider_val: The current value of the slider, will be an
                                   integer value between
                                       [0,(pos_max - pos_min)/pos_step] of the corresponding axis label. Now convert this value back to a viewbox value like:
                                       pos_min + slider_step*pos_step
            """

            constraints = self._magnet_logic.get_hardware_constraints()
            # set the resolution of the slider to nanometer precision, that is
            # better for the display behaviour. In the end, that will just make
            # everything smoother but not actually affect the displayed number:

            # max_step_slider = 10**int(np.log10(constraints[axis_label]['pos_step']) -1)
            max_step_slider = constraints[axis_label]['pos_step']

            actual_pos = (constraints[axis_label]['pos_min'] + slider_val * max_step_slider)
            ref_dspinbox.setValue(actual_pos)
            ref_dspinbox.setDecimals(3)

        func_dummy_name.__name__ = func_name
        return func_dummy_name

    def _function_builder_update_slider(self, func_name, axis_label, ref_slider):
        """ Create a function/method, which gets executed for pressing move_rel.

        Create a function/method, which gets executed for pressing move_rel.

        @param str func_name: name how the function should be called.
        @param str axis_label: label of the axis you want to create a control
                               function for.
        @param object ref_slider: a reference to the slider object, which
                                  will actually apply the changed within the
                                  created method.

        @return: function with name func_name

        A routine to construct a method on the fly and attach it as attribute
        to the object, so that it can be used or so that other signals can be
        connected to it. The connection of a signal to this method must appear
        outside of the present function.
        """

        def func_dummy_name(viewbox_val):
            """
            @param int slider_step: The current value of the slider, will be an
                                    integer value between
                                        [0,(pos_max - pos_min)/pos_step]
                                    of the corresponding axis label.
                                    Now convert this value back to a viewbox
                                    value like:
                                        pos_min + slider_step*pos_step
            """

            # dspinbox_obj = self.get_ref_move_abs_ScienDSpinBox(axis_label)
            # viewbox_val = dspinbox_obj.value()
            constraints = self._magnet_logic.get_hardware_constraints()
            # set the resolution of the slider to nanometer precision, that is
            # better for the display behaviour. In the end, that will just make
            # everything smoother but not actually affect the displayed number:

            # max_step_slider = 10**int(np.log10(constraints[axis_label]['pos_step']) -1)
            max_step_slider = constraints[axis_label]['pos_step']

            slider_val = abs(viewbox_val - constraints[axis_label]['pos_min'])/max_step_slider
            ref_slider.setValue(slider_val)

        func_dummy_name.__name__ = func_name
        return func_dummy_name

    def move_rel(self, axis_label, direction):
        """ Move relative by the axis with given label an direction.

        @param str axis_label: tells which axis should move.
        @param int direction: either 1 or -1 depending on the relative movement.

        That method get called from methods, which are created on the fly at
        runtime during the activation of that module (basically from the
        methods with the generic name move_rel_axis_{0}_p or
        move_rel_axis_{0}_m with the appropriate label).
        """
        #constraints = self._magnet_logic.get_hardware_constraints()
        dspinbox = self.get_ref_move_rel_ScienDSpinBox(axis_label)

        movement = dspinbox.value() * direction

        self._magnet_logic.move_rel({axis_label: movement})
        if self._interactive_mode:
            self.update_pos()
        return axis_label, direction

    def move_abs(self, param_dict=None):
        """ Perform an absolute movement.

        @param param_dict: with {<axis_label>:<position>}, can of course
                           contain many entries of the same kind.

        Basically all the axis can be controlled at the same time.
        """

        if (param_dict is not None) and (type(param_dict) is not bool):
            self._magnet_logic.move_abs(param_dict)
        else:
            constraints = self._magnet_logic.get_hardware_constraints()

            # create the move_abs dict
            move_abs = {}
            for label in constraints:
                if label in ['x','y','z']:
                    continue
                move_abs[label] = self.get_ref_move_abs_ScienDSpinBox(label).value()

            self._magnet_logic.move_abs(move_abs)

        if self._interactive_mode:
            self.update_pos()
            return param_dict

    def get_ref_curr_pos_DoubleSpinBox(self, label):
        """ Get the reference to the double spin box for the passed label. """

        dspinbox_name = 'curr_pos_{0}_DoubleSpinBox'.format(label)
        dspinbox_ref = getattr(self._mw, dspinbox_name)
        return dspinbox_ref

    def get_ref_move_rel_ScienDSpinBox(self, label):
        """ Get the reference to the double spin box for the passed label. """

        dspinbox_name = 'move_rel_{0}_ScienDSpinBox'.format(label)
        dspinbox_ref = getattr(self._mw, dspinbox_name)
        return dspinbox_ref

    def get_ref_move_abs_ScienDSpinBox(self, label):
        """ Get the reference to the double spin box for the passed label. """

        dspinbox_name = 'move_abs_{0}_DoubleSpinBox'.format(label)
        dspinbox_ref = getattr(self._mw, dspinbox_name)
        return dspinbox_ref

    def get_ref_move_abs_Slider(self, label):
        """ Get the reference to the slider for the passed label. """

        slider_name = 'move_abs_{0}_Slider'.format(label)
        slider_ref = getattr(self._mw, slider_name)
        return slider_ref

    def move_rel_para_changed(self):
        """ Pass the current GUI value to the logic

        @return dict: Passed move relative parameter
        """
        return_dict = dict()
        axes = list(self._magnet_logic.get_hardware_constraints())
        for axis_label in axes:
            if axis_label in ['x','y','z']:
                continue
            dspinbox = self.get_ref_move_rel_ScienDSpinBox(axis_label)
            return_dict[axis_label]=dspinbox.value()
        self._magnet_logic.set_move_rel_para(return_dict)
        return return_dict

    def align_2d_axis0_name_changed(self):
        """ Pass the current GUI value to the logic

        @return str: Passed axis name
        """
        axisname = self._mw.align_2d_axis0_name_ComboBox.currentText()
        self._magnet_logic.set_align_2d_axis0_name(axisname)
        return axisname

    def align_2d_axis0_range_changed(self):
        """ Pass the current GUI value to the logic

        @return float: Passed range
        """
        axis_range = self._mw.align_2d_axis0_range_DSpinBox.value()
        self._magnet_logic.set_align_2d_axis0_range(axis_range)
        return axis_range


    def align_2d_axis0_step_changed(self):
        """ Pass the current GUI value to the logic

        @return float: Passed step
        """
        step = self._mw.align_2d_axis0_step_DSpinBox.value()
        self._magnet_logic.set_align_2d_axis0_step(step)
        return step


    def align_2d_axis1_name_changed(self):
        """ Pass the current GUI value to the logic

        @return str: Passed axis name
        """
        axisname = self._mw.align_2d_axis1_name_ComboBox.currentText()
        self._magnet_logic.set_align_2d_axis1_name(axisname)
        return axisname

    def align_2d_axis1_range_changed(self):
        """ Pass the current GUI value to the logic

        @return float: Passed range
        """
        axis_range = self._mw.align_2d_axis1_range_DSpinBox.value()
        self._magnet_logic.set_align_2d_axis1_range(axis_range)
        return axis_range

    def align_2d_axis1_step_changed(self):
        """ Pass the current GUI value to the logic

        @return float: Passed step size
        """
        step = self._mw.align_2d_axis1_step_DSpinBox.value()
        self._magnet_logic.set_align_2d_axis1_step(step)
        return step


    def optimize_pos_freq_changed(self):
        """ Pass the current GUI value to the logic

        @return float: Passed frequency
         """
        freq = self._mw.align_2d_fluorescence_optimize_freq_SpinBox.value()
        self._magnet_logic.set_optimize_pos_freq(freq)
        return freq

    def fluorescence_integration_time_changed(self):
        """ Pass the current GUI value to the logic

        @return float: Passed integration time
         """
        time = self._mw.align_2d_fluorescence_integrationtime_DSpinBox.value()
        self._magnet_logic.set_fluorescence_integration_time(time)
        return time

    def stop_movement(self):
        """ Invokes an immediate stop of the hardware.

        MAKE SURE THAT THE HARDWARE CAN BE CALLED DURING AN ACTION!
        If the parameter _interactive_mode is set to False no stop can be done
        since the device would anyway not respond to a method call.
        """

        if self._interactive_mode:
            self._magnet_logic.stop_movement()
        else:
            self.log.warning('Movement cannot be stopped during a movement '
                    'anyway! Set the interactive mode to True in the Magnet '
                    'Settings! Otherwise this method is useless.')

    def update_pos(self, param_list=None):
        """ Update the current position.

        @param list param_list: optional, if specific positions needed to be
                                updated.

        If no value is passed, the current position is retrieved from the
        logic and the display is changed.
        """
        
        if not type(param_list) is dict:
            constraints = self._magnet_logic.get_hardware_constraints()
            curr_pos = self._magnet_logic.get_pos(list(constraints.keys()))
            self.last_pos = curr_pos
        else:
            curr_pos = param_list
            self.last_pos = curr_pos

        for axis_label in curr_pos:
            # update the values of the current position viewboxes:
            try:
                dspinbox_pos_ref = self.get_ref_curr_pos_DoubleSpinBox(axis_label)
                dspinbox_pos_ref.setValue(round(curr_pos[axis_label],3))
            except:
                pass
        
        return curr_pos

    def run_stop_2d_alignment(self, is_checked):
        """ Manage what happens if 2d magnet scan is started/stopped

        @param bool is_checked: state if the current scan, True = started,
                                False = stopped
        """

        if is_checked:
            self.start_2d_alignment_clicked()

        else:
            self.abort_2d_alignment_clicked()

    def _change_display_to_stop_2d_alignment(self):
        """ Changes every display component back to the stopped state. """

        self._mw.run_stop_2d_alignment_Action.blockSignals(True)
        self._mw.run_stop_2d_alignment_Action.setChecked(False)

        self._mw.continue_2d_alignment_Action.blockSignals(True)
        self._mw.continue_2d_alignment_Action.setChecked(False)

        self._mw.run_stop_2d_alignment_Action.blockSignals(False)
        self._mw.continue_2d_alignment_Action.blockSignals(False)

    def start_2d_alignment_clicked(self):
        """ Start the 2d alignment. """

        if self.measurement_type == '2d_fluorescence':
            self._magnet_logic.curr_alignment_method = self.measurement_type

            self._magnet_logic.fluorescence_integration_time = self._mw.align_2d_fluorescence_integrationtime_DSpinBox.value()
            self._mw.alignment_2d_cb_GraphicsView.setLabel('right', 'Fluorescence', units='c/s')

        self._magnet_logic.start_2d_alignment(continue_meas=self._continue_2d_fluorescence_alignment)

        self._continue_2d_fluorescence_alignment = False

    def continue_stop_2d_alignment(self, is_checked):
        """ Manage what happens if 2d magnet scan is continued/stopped

        @param bool is_checked: state if the current scan, True = continue,
                                False = stopped
        """

        if is_checked:
            self.continue_2d_alignment_clicked()
        else:
            self.abort_2d_alignment_clicked()

    def continue_2d_alignment_clicked(self):

        self._continue_2d_fluorescence_alignment = True
        self.start_2d_alignment_clicked()

    def abort_2d_alignment_clicked(self):
        """ Stops the current Fluorescence alignment. """

        self._change_display_to_stop_2d_alignment()
        self._magnet_logic.stop_alignment()

    def _update_limits_axis0(self):
        """ Whenever a new axis name was chosen in axis0 config, the limits of the
            viewboxes will be adjusted.
        """

        constraints = self._magnet_logic.get_hardware_constraints()
        axis0_name = self._mw.align_2d_axis0_name_ComboBox.currentText()

        # set the range constraints:
        self._mw.align_2d_axis0_range_DSpinBox.setMinimum(0)
        self._mw.align_2d_axis0_range_DSpinBox.setMaximum(constraints[axis0_name]['pos_max'])
        # self._mw.align_2d_axis0_range_DSpinBox.setSingleStep(constraints[axis0_name]['pos_step'],
        #                                                      dynamic_stepping=False)
        self._mw.align_2d_axis0_range_DSpinBox.setSuffix(constraints[axis0_name]['unit'])

        # set the step constraints:
        self._mw.align_2d_axis0_step_DSpinBox.setMinimum(0)
        self._mw.align_2d_axis0_step_DSpinBox.setMaximum(constraints[axis0_name]['pos_max'])
        # self._mw.align_2d_axis0_step_DSpinBox.setSingleStep(constraints[axis0_name]['pos_step'],
        #                                                     dynamic_stepping=False)
        self._mw.align_2d_axis0_step_DSpinBox.setSuffix(constraints[axis0_name]['unit'])


    def _update_limits_axis1(self):
        """ Whenever a new axis name was chosen in axis0 config, the limits of the
            viewboxes will be adjusted.
        """

        constraints = self._magnet_logic.get_hardware_constraints()
        axis1_name = self._mw.align_2d_axis1_name_ComboBox.currentText()

        self._mw.align_2d_axis1_range_DSpinBox.setMinimum(0)
        self._mw.align_2d_axis1_range_DSpinBox.setMaximum(constraints[axis1_name]['pos_max'])
        # self._mw.align_2d_axis1_range_DSpinBox.setSingleStep(constraints[axis1_name]['pos_step'],
        #                                                      dynamic_stepping=False)
        self._mw.align_2d_axis1_range_DSpinBox.setSuffix(constraints[axis1_name]['unit'])

        self._mw.align_2d_axis1_step_DSpinBox.setMinimum(0)
        self._mw.align_2d_axis1_step_DSpinBox.setMaximum(constraints[axis1_name]['pos_max'])
        # self._mw.align_2d_axis1_step_DSpinBox.setSingleStep(constraints[axis1_name]['pos_step'],
        #                                                     dynamic_stepping=False)
        self._mw.align_2d_axis1_step_DSpinBox.setSuffix(constraints[axis1_name]['unit'])


    def _update_2d_graph_axis(self):

        constraints = self._magnet_logic.get_hardware_constraints()

        axis0_name = self._mw.align_2d_axis0_name_ComboBox.currentText()
        axis0_unit = constraints[axis0_name]['unit']
        axis1_name = self._mw.align_2d_axis1_name_ComboBox.currentText()
        axis1_unit = constraints[axis1_name]['unit']

        axis0_array, axis1_array = self._magnet_logic.get_2d_axis_arrays()

        step0 = axis0_array[1] - axis0_array[0]
        step1 = axis1_array[1] - axis1_array[0]

        self._2d_alignment_ImageItem.set_image_extent([[axis0_array[0]-step0/2, axis0_array[-1]+step0/2],
                                                       [axis1_array[0]-step1/2, axis1_array[-1]+step1/2]])

        self._mw.alignment_2d_GraphicsView.setLabel('bottom', 'Absolute Position, Axis0: ' + axis0_name, units=axis0_unit)
        self._mw.alignment_2d_GraphicsView.setLabel('left', 'Absolute Position, Axis1: '+ axis1_name, units=axis1_unit)

    def _update_2d_graph_cb(self):
        """ Update the colorbar to a new scaling.

        That function alters the color scaling of the colorbar next to the main
        picture.
        """
        if self._mw.alignment_2d_centiles_RadioButton.isChecked():

            low_centile = self._mw.alignment_2d_cb_low_centiles_DSpinBox.value()
            high_centile = self._mw.alignment_2d_cb_high_centiles_DSpinBox.value()

            if np.isclose(low_centile, 0.0):
                low_centile = 0.0

            # mask the array such that the arrays will be
            masked_image = np.ma.masked_equal(self._2d_alignment_ImageItem.image, 0.0)

            if len(masked_image.compressed()) == 0:
                cb_min = np.percentile(self._2d_alignment_ImageItem.image, low_centile)
                cb_max = np.percentile(self._2d_alignment_ImageItem.image, high_centile)
            else:
                cb_min = np.percentile(masked_image.compressed(), low_centile)
                cb_max = np.percentile(masked_image.compressed(), high_centile)

        else:
            cb_min = self._mw.alignment_2d_cb_min_centiles_DSpinBox.value()
            cb_max = self._mw.alignment_2d_cb_max_centiles_DSpinBox.value()
        
        cb_min = 0 if cb_min>cb_max else cb_min

        self._2d_alignment_cb.refresh_colorbar(cb_min, cb_max)
        self._mw.alignment_2d_cb_GraphicsView.update()

    def _update_2d_graph_data(self):
        """ Refresh the 2D-matrix image. """
        matrix_data = self._magnet_logic.get_2d_data_matrix()
        axis0_array, axis1_array = self._magnet_logic.get_2d_axis_arrays()

        if self._mw.alignment_2d_centiles_RadioButton.isChecked():

            low_centile = self._mw.alignment_2d_cb_low_centiles_DSpinBox.value()
            high_centile = self._mw.alignment_2d_cb_high_centiles_DSpinBox.value()

            if np.isclose(low_centile, 0.0):
                low_centile = 0.0

            # mask the array in order to mark the values which are zeros with
            # True, the rest with False:
            masked_image = np.ma.masked_equal(matrix_data, 0.0)

            # compress the 2D masked array to a 1D array where the zero values
            # are excluded:
            if len(masked_image.compressed()) == 0:
                cb_min = np.percentile(matrix_data, low_centile)
                cb_max = np.percentile(matrix_data, high_centile)
            else:
                cb_min = np.percentile(masked_image.compressed(), low_centile)
                cb_max = np.percentile(masked_image.compressed(), high_centile)
        else:
            cb_min = self._mw.alignment_2d_cb_min_centiles_DSpinBox.value()
            cb_max = self._mw.alignment_2d_cb_max_centiles_DSpinBox.value()

        cb_min = 0 if cb_min>cb_max else cb_min

        self._2d_alignment_ImageItem.setImage(matrix=matrix_data, levels=(cb_min, cb_max))
        self._update_2d_graph_axis()

        self._update_2d_graph_cb()

        # get data from logic

    def save_2d_plots_and_data(self):
        """ Save the sum plot, the scan marix plot and the scan data """
        timestamp = datetime.datetime.now()
        filetag = self._mw.alignment_2d_nametag_LineEdit.text()
        filepath = self._save_logic.get_path_for_module(module_name='Magnet')

        if len(filetag) > 0:
            filename = os.path.join(filepath, '{0}_{1}_Magnet'.format(timestamp.strftime('%Y%m%d-%H%M-%S'), filetag))
        else:
            filename = os.path.join(filepath, '{0}_Magnet'.format(timestamp.strftime('%Y%m%d-%H%M-%S'),))

        exporter_graph = pyqtgraph.exporters.SVGExporter(self._mw.alignment_2d_GraphicsView.plotItem.scene())
        #exporter_graph = pg.exporters.ImageExporter(self._mw.odmr_PlotWidget.plotItem)
        exporter_graph.export(filename  + '.svg')

        self._magnet_logic.save_2d_data(filetag, timestamp)

    def set_measurement_type(self):
        """ According to the selected Radiobox a measurement type will be chosen."""

        #FIXME: the measurement type should actually be set and saved in the logic

        if self._mw.meas_type_fluorescence_RadioButton.isChecked():
            self.measurement_type = '2d_fluorescence'
        else:
            self.log.error('No measurement type specified in Magnet GUI!')

    def update_from_roi_magnet(self, pos):
        """The user manually moved the XY ROI, adjust all other GUI elements accordingly

        @params object roi: PyQtGraph ROI object
        """
        x_pos = pos.x()
        y_pos = pos.y()

        if hasattr(self._magnet_logic, '_axis0_name') and hasattr(self._magnet_logic, '_axis1_name'):
            axis0_name = self._magnet_logic._axis0_name
            axis1_name = self._magnet_logic._axis1_name
        else:
            axis0_name = 'theta'
            axis1_name = 'phi'

        self._mw.pos_label.setText('({0}, {1})'.format(axis0_name, axis1_name))
        self._mw.pos_show.setText('({0:.6f}, {1:.6f})'.format(x_pos, y_pos))
        self._mw.move_abs_theta_DoubleSpinBox.setValue(round(x_pos,3))
        self._mw.move_abs_phi_DoubleSpinBox.setValue(round(y_pos,3))

    def update_roi_from_abs_movement(self):
        """
        User changed magnetic field through absolute movement, therefore the roi has to be adjusted.
        @return:
        """
        axis0_name = self._mw.align_2d_axis0_name_ComboBox.currentText()
        axis1_name = self._mw.align_2d_axis1_name_ComboBox.currentText()
        self.log.debug('get the axis0_name: {0}'.format(axis0_name))
        self.log.debug('get the axis0_name: {0}'.format(axis1_name))
        axis0_value = self.get_ref_move_abs_ScienDSpinBox(axis0_name).value()
        axis1_value = self.get_ref_move_abs_ScienDSpinBox(axis1_name).value()
        self._mw.alignment_2d_GraphicsView.set_crosshair_pos([axis0_value, axis1_value])
        return 0

    def update_move_rel_para(self, parameters):
        """ The GUT is updated taking dict into account. Thereby no signal is triggered!

        @params dictionary: Dictionary containing the values to update

        @return dictionary: Dictionary containing the values to update
         """
        for axis_label in parameters:
            dspinbox = self.get_ref_move_rel_ScienDSpinBox(axis_label)
            dspinbox.blockSignals(True)
            dspinbox.setValue(round(parameters[axis_label],3))
            dspinbox.blockSignals(False)
        return parameters

    def update_roi_from_range(self):
        """
        User changed scan range and therefore the rectangular should be adjusted
        @return:
        """
        # first get the size of axis0 and axis1 range
        x_range = self._mw.align_2d_axis0_range_DSpinBox.value()
        y_range = self._mw.align_2d_axis1_range_DSpinBox.value()
        self._mw.alignment_2d_GraphicsView.set_crosshair_size([x_range/100, y_range/100])

    def update_align_2d_axis0_name(self,axisname):
        """ The GUT is updated taking axisname into account. Thereby no signal is triggered!

        @params str: Axis name to update

        @return str: Axis name to update
         """
        self._mw.align_2d_axis0_name_ComboBox.blockSignals(True)
        index = self._mw.align_2d_axis0_name_ComboBox.findText(axisname)
        self._mw.align_2d_axis0_name_ComboBox.setCurrentIndex(index)
        self._mw.align_2d_axis0_name_ComboBox.blockSignals(False)
        return axisname

    def update_align_2d_axis0_range(self, axis_range):
        """ The GUT is updated taking range into account. Thereby no signal is triggered!

        @params float: Range to update

        @return float: Range to update
         """
        self._mw.align_2d_axis0_range_DSpinBox.blockSignals(True)
        self._mw.align_2d_axis0_range_DSpinBox.setValue(axis_range)
        self._mw.align_2d_axis0_range_DSpinBox.blockSignals(False)
        return axis_range

    def update_align_2d_axis0_step(self, step):
        """ The GUT is updated taking step into account. Thereby no signal is triggered!

        @params float: Step to update in m

        @return float: Step to update in m
         """
        self._mw.align_2d_axis0_step_DSpinBox.blockSignals(True)
        self._mw.align_2d_axis0_step_DSpinBox.setValue(step)
        self._mw.align_2d_axis0_step_DSpinBox.blockSignals(False)
        return step

    def update_align_2d_axis1_name(self, axisname):
        """ The GUT is updated taking axisname into account. Thereby no signal is triggered!

        @params str: Axis name to update

        @return str: Axis name to update
         """
        self._mw.align_2d_axis1_name_ComboBox.blockSignals(True)
        index = self._mw.align_2d_axis1_name_ComboBox.findText(axisname)
        self._mw.align_2d_axis1_name_ComboBox.setCurrentIndex(index)
        self._mw.align_2d_axis1_name_ComboBox.blockSignals(False)
        return index

    def update_align_2d_axis1_range(self, axis_range):
        """ The GUT is updated taking range into account. Thereby no signal is triggered!

        @params float: Range to update

        @return float: Range to update
         """
        self._mw.align_2d_axis1_range_DSpinBox.blockSignals(True)
        self._mw.align_2d_axis1_range_DSpinBox.setValue(axis_range)
        self._mw.align_2d_axis1_range_DSpinBox.blockSignals(False)
        return axis_range

    def update_align_2d_axis1_step(self, step):
        """ The GUT is updated taking step into account. Thereby no signal is triggered!

        @params float: Step to update in m

        @return float: Step to update in m
         """
        self._mw.align_2d_axis1_step_DSpinBox.blockSignals(True)
        self._mw.align_2d_axis1_step_DSpinBox.setValue(step)
        self._mw.align_2d_axis1_step_DSpinBox.blockSignals(False)
        return step


    def update_optimize_pos_freq(self, freq):
        """ The GUT is updated taking freq into account. Thereby no signal is triggered!

        @params float: Frequency to update

        @return float: Frequency to update
         """
        self._mw.align_2d_fluorescence_optimize_freq_SpinBox.blockSignals(True)
        self._mw.align_2d_fluorescence_optimize_freq_SpinBox.setValue(freq)
        self._mw.align_2d_fluorescence_optimize_freq_SpinBox.blockSignals(False)
        return freq

    def update_fluorescence_integration_time(self, time):
        """ The GUT is updated taking time into account. Thereby no signal is triggered!

        @params float: Integration time to update

        @return float: Integration time to update
         """
        self._mw.align_2d_fluorescence_integrationtime_DSpinBox.blockSignals(True)
        self._mw.align_2d_fluorescence_integrationtime_DSpinBox.setValue(time)
        self._mw.align_2d_fluorescence_integrationtime_DSpinBox.blockSignals(False)
        return time
    