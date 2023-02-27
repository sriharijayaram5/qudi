# -*- coding: utf-8 -*-
"""
This file contains the Qudi GUI module for ODMR control.

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
import os
import pyqtgraph as pg

from core.connector import Connector
from core.module import Connector, StatusVar
from core.util import units
from gui.guibase import GUIBase
from gui.guiutils import ColorBar
from gui.colordefs import ColorScaleInferno
from gui.colordefs import QudiPalettePale as palette
from gui.fitsettings import FitSettingsDialog, FitSettingsComboBox
from qtpy import QtCore
from qtpy import QtCore, QtWidgets, uic
from qtwidgets.scientific_spinbox import ScienDSpinBox
from qtpy import uic
from functools import partial


class ODMRMainWindow(QtWidgets.QMainWindow):
    """ The main window for the ODMR measurement GUI.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_odmrgui.ui')

        # Load it
        super(ODMRMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()


# class ODMRSettingDialog(QtWidgets.QDialog):
#     """ The settings dialog for ODMR measurements.
#     """

#     def __init__(self):
#         # Get the path to the *.ui file
#         this_dir = os.path.dirname(__file__)
#         ui_file = os.path.join(this_dir, 'ui_odmr_settings.ui')

#         # Load it
#         super(ODMRSettingDialog, self).__init__()
#         uic.loadUi(ui_file, self)


class ODMRGui(GUIBase):
    """
    This is the GUI Class for ODMR measurements
    """

    # declare connectors
    odmrlogic1 = Connector(interface='ODMRLogic')
    savelogic = Connector(interface='SaveLogic')

    sigStartOdmrScan = QtCore.Signal()
    sigStopOdmrScan = QtCore.Signal()
    sigContinueOdmrScan = QtCore.Signal()
    sigClearData = QtCore.Signal()
    # sigCwMwOn = QtCore.Signal()
    sigMwOff = QtCore.Signal()
    sigMwPowerChanged = QtCore.Signal(float)
    # sigMwCwParamsChanged = QtCore.Signal(float, float)
    sigMwSweepParamsChanged = QtCore.Signal(list, list, list, float)
    sigClockFreqChanged = QtCore.Signal(float)
    sigOversamplingChanged = QtCore.Signal(int)
    sigLockInChanged = QtCore.Signal(bool)
    sigFitChanged = QtCore.Signal(str)
    sigNumberOfLinesChanged = QtCore.Signal(int)
    sigRuntimeChanged = QtCore.Signal(float)
    sigDoFit = QtCore.Signal(str, object, object, int, int)
    sigSaveMeasurement = QtCore.Signal(str)
    sigAverageLinesChanged = QtCore.Signal(int)
    pi_half = StatusVar('pi_half', default=0)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition, configuration and initialisation of the ODMR GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        """

        self._odmr_logic = self.odmrlogic1()
        self._fitlogic = self._odmr_logic.fitlogic()

        # Use the inherited class 'Ui_ODMRGuiUI' to create now the GUI element:
        self._mw = ODMRMainWindow()
        self.restoreWindowPos(self._mw)
        pass #self._sd = ODMRSettingDialog()
        self.vis_arr = np.zeros(100)

        # Create a QSettings object for the mainwindow and store the actual GUI layout
        self.mwsettings = QtCore.QSettings("QUDI", "ODMR")
        self.mwsettings.setValue("geometry", self._mw.saveGeometry())
        self.mwsettings.setValue("windowState", self._mw.saveState())

        # Get hardware constraints to set limits for input widgets
        constraints = self._odmr_logic.get_hw_constraints()

        # Adjust range of scientific spinboxes above what is possible in Qt Designer
        # self._mw.cw_frequency_DoubleSpinBox.setMaximum(constraints.max_frequency)
        # self._mw.cw_frequency_DoubleSpinBox.setMinimum(constraints.min_frequency)
        # self._mw.cw_power_DoubleSpinBox.setMaximum(constraints.max_power)
        # self._mw.cw_power_DoubleSpinBox.setMinimum(constraints.min_power)
        self._mw.sweep_power_DoubleSpinBox.setMaximum(constraints.max_power)
        self._mw.sweep_power_DoubleSpinBox.setMinimum(constraints.min_power)

        # Add grid layout for ranges
        groupBox = QtWidgets.QGroupBox(self._mw.dockWidgetContents_3)
        groupBox.setAlignment(QtCore.Qt.AlignLeft)
        groupBox.setTitle('Scanning Ranges')
        gridLayout = QtWidgets.QGridLayout(groupBox)
        for row in range(self._odmr_logic.ranges):
            # start
            start_label = QtWidgets.QLabel(groupBox)
            start_label.setText('Start:')
            setattr(self._mw.odmr_control_DockWidget, 'start_label_{}'.format(row), start_label)
            start_freq_DoubleSpinBox = ScienDSpinBox(groupBox)
            start_freq_DoubleSpinBox.setSuffix('Hz')
            start_freq_DoubleSpinBox.setMaximum(constraints.max_frequency)
            start_freq_DoubleSpinBox.setMinimum(constraints.min_frequency)
            start_freq_DoubleSpinBox.setMinimumSize(QtCore.QSize(80, 0))
            start_freq_DoubleSpinBox.setValue(self._odmr_logic.mw_starts[row])
            start_freq_DoubleSpinBox.setMinimumWidth(75)
            start_freq_DoubleSpinBox.setMaximumWidth(100)
            setattr(self._mw.odmr_control_DockWidget, 'start_freq_DoubleSpinBox_{}'.format(row),
                    start_freq_DoubleSpinBox)
            gridLayout.addWidget(start_label, row, 1, 1, 1)
            gridLayout.addWidget(start_freq_DoubleSpinBox, row, 2, 1, 1)
            start_freq_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
            # step
            step_label = QtWidgets.QLabel(groupBox)
            step_label.setText('Step:')
            setattr(self._mw.odmr_control_DockWidget, 'step_label_{}'.format(row), step_label)
            step_freq_DoubleSpinBox = ScienDSpinBox(groupBox)
            step_freq_DoubleSpinBox.setSuffix('Hz')
            step_freq_DoubleSpinBox.setMaximum(100e9)
            step_freq_DoubleSpinBox.setMinimumSize(QtCore.QSize(80, 0))
            step_freq_DoubleSpinBox.setValue(self._odmr_logic.mw_steps[row])
            step_freq_DoubleSpinBox.setMinimumWidth(75)
            step_freq_DoubleSpinBox.setMaximumWidth(100)
            step_freq_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
            setattr(self._mw.odmr_control_DockWidget, 'step_freq_DoubleSpinBox_{}'.format(row),
                    step_freq_DoubleSpinBox)
            gridLayout.addWidget(step_label, row, 3, 1, 1)
            gridLayout.addWidget(step_freq_DoubleSpinBox, row, 4, 1, 1)

            # stop
            stop_label = QtWidgets.QLabel(groupBox)
            stop_label.setText('Stop:')
            setattr(self._mw.odmr_control_DockWidget, 'stop_label_{}'.format(row), stop_label)
            stop_freq_DoubleSpinBox = ScienDSpinBox(groupBox)
            stop_freq_DoubleSpinBox.setSuffix('Hz')
            stop_freq_DoubleSpinBox.setMaximum(constraints.max_frequency)
            stop_freq_DoubleSpinBox.setMinimum(constraints.min_frequency)
            stop_freq_DoubleSpinBox.setMinimumSize(QtCore.QSize(80, 0))
            stop_freq_DoubleSpinBox.setValue(self._odmr_logic.mw_stops[row])
            stop_freq_DoubleSpinBox.setMinimumWidth(75)
            stop_freq_DoubleSpinBox.setMaximumWidth(100)
            stop_freq_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
            setattr(self._mw.odmr_control_DockWidget, 'stop_freq_DoubleSpinBox_{}'.format(row),
                    stop_freq_DoubleSpinBox)
            gridLayout.addWidget(stop_label, row, 5, 1, 1)
            gridLayout.addWidget(stop_freq_DoubleSpinBox, row, 6, 1, 1)


        self._mw.fit_range_SpinBox.setMaximum(self._odmr_logic.ranges - 1)
        setattr(self._mw.odmr_control_DockWidget, 'ranges_groupBox', groupBox)
        self._mw.dockWidgetContents_3_grid_layout = self._mw.dockWidgetContents_3.layout()
        self._mw.fit_range_SpinBox.valueChanged.connect(self.change_fit_range)
        # (QWidget * widget, int row, int column, Qt::Alignment alignment = Qt::Alignment())

        self._mw.dockWidgetContents_3_grid_layout.addWidget(groupBox, 8, 0, 1, 6)

        # Add save file tag input box
        self._mw.save_tag_LineEdit = QtWidgets.QLineEdit(self._mw)
        self._mw.save_tag_LineEdit.setMaximumWidth(500)
        self._mw.save_tag_LineEdit.setMinimumWidth(200)
        self._mw.save_tag_LineEdit.setToolTip('Enter a nametag which will be\n'
                                              'added to the filename.')
        self._mw.save_ToolBar.addWidget(self._mw.save_tag_LineEdit)

        # Set up and connect channel combobox
        self.display_channel = 0
        odmr_channels = self._odmr_logic.get_odmr_channels()
        for n, ch in enumerate(odmr_channels):
            self._mw.odmr_channel_ComboBox.addItem(str(ch), n)

        self._mw.odmr_channel_ComboBox.activated.connect(self.update_channel)

        self.odmr_image = pg.PlotDataItem(self._odmr_logic.odmr_plot_x,
                                          self._odmr_logic.odmr_plot_y[self.display_channel],
                                          pen=pg.mkPen(palette.c1, style=QtCore.Qt.DotLine),
                                          symbol='o',
                                          symbolPen=palette.c1,
                                          symbolBrush=palette.c1,
                                          symbolSize=7)

        self.signal_image_error_bars = pg.ErrorBarItem(x=self._odmr_logic.odmr_plot_x,
                                                       y= self._odmr_logic.odmr_plot_y[self.display_channel],
                                                       top=0.,
                                                       bottom=0.,
                                                       pen=palette.c2)

        self.odmr_fit_image = pg.PlotDataItem(self._odmr_logic.odmr_fit_x,
                                              self._odmr_logic.odmr_fit_y,
                                              pen=pg.mkPen(palette.c2))
        
        self.odmr_slope_line = pg.PlotDataItem(self._odmr_logic.odmr_fit_x,
                                              self._odmr_logic.odmr_fit_y,
                                              pen={'color': palette.c4, 'width': 2, 'dash' : [2.0,2.0]})

        # Add the display item to the xy and xz ViewWidget, which was defined in the UI file.
        self._mw.odmr_PlotWidget.addItem(self.odmr_image)
        self._mw.odmr_PlotWidget.setLabel(axis='left', text='Counts', units='Counts/s')
        self._mw.odmr_PlotWidget.setLabel(axis='bottom', text='Frequency', units='Hz')
        self._mw.odmr_PlotWidget.showGrid(x=True, y=True, alpha=0.8)
        
        self._mw.odmr_PlotWidget.addItem(self.signal_image_error_bars)

        self.sweep_start_line = pg.InfiniteLine(pos=0,
                                              pen={'color': palette.c3, 'width': 1},
                                              movable=True)
        self.sweep_end_line = pg.InfiniteLine(pos=0,
                                            pen={'color': palette.c3, 'width': 1},
                                            movable=True)
        
        self.slope_start_line = pg.InfiniteLine(pos=0,
                                              pen={'color': palette.c4, 'width': 1},
                                              movable=True)
        
        self._mw.odmr_PlotWidget.addItem(self.sweep_start_line)
        self._mw.odmr_PlotWidget.addItem(self.sweep_end_line)

        self.sweep_start_line.sigPositionChangeFinished.connect(self.sweep_settings_changed)
        self.sweep_end_line.sigPositionChangeFinished.connect(self.sweep_settings_changed)

        self.slope_start_line.sigPositionChangeFinished.connect(self.slope_fit_changed)



        # Get the colorscales at set LUT
        my_colors = ColorScaleInferno()
        self._mw.sweep_power_DoubleSpinBox.setValue(self._odmr_logic.sweep_mw_power)

        # self._mw.runtime_DoubleSpinBox.setValue(self._odmr_logic.run_time)
        self._mw.elapsed_time_DisplayWidget.display(int(np.rint(self._odmr_logic.elapsed_time)))
        self._mw.elapsed_sweeps_DisplayWidget.display(self._odmr_logic.elapsed_sweeps)
        self._mw.average_level_SpinBox.setValue(self._odmr_logic.lines_to_average)

        # fit settings
        self._fsd = FitSettingsDialog(self._odmr_logic.fc)
        self._fsd.sigFitsUpdated.connect(self._mw.fit_methods_ComboBox.setFitFunctions)
        self._fsd.applySettings()
        self._mw.action_FitSettings.triggered.connect(self._fsd.show)

        ########################################################################
        #                       Connect signals                                #
        ########################################################################
        # Internal user input changed signals

        self._mw.sweep_power_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
        self._mw.average_level_SpinBox.valueChanged.connect(self.average_level_changed)
        # Internal trigger signals
        self._mw.action_run_stop.triggered.connect(self.run_stop_odmr)
        self._mw.action_Save.triggered.connect(self.save_data)
        self._mw.action_RestoreDefault.triggered.connect(self.restore_defaultview)
        self._mw.do_fit_PushButton.clicked.connect(self.do_fit)
        self._mw.fit_range_SpinBox.editingFinished.connect(self.update_fit_range)
        self._mw.actionAWG_Mode.toggled.connect(self._odmr_logic.change_MW_mode)
        self._mw.actionAWG_Mode.toggle()
        # Control/values-changed signals to logic
        self.sigMwOff.connect(self._odmr_logic.mw_off, QtCore.Qt.QueuedConnection)
        self.sigClearData.connect(self._odmr_logic.clear_odmr_data, QtCore.Qt.QueuedConnection)
        self.sigStartOdmrScan.connect(self._odmr_logic.start_odmr_scan, QtCore.Qt.QueuedConnection)
        self.sigStopOdmrScan.connect(self._odmr_logic.stop_odmr_scan, QtCore.Qt.QueuedConnection)
        self.sigDoFit.connect(self._odmr_logic.do_fit, QtCore.Qt.QueuedConnection)
        self.sigMwSweepParamsChanged.connect(self._odmr_logic.set_sweep_parameters,
                                             QtCore.Qt.QueuedConnection)
        self.sigSaveMeasurement.connect(self._odmr_logic.save_odmr_data, QtCore.Qt.QueuedConnection)
        self.sigAverageLinesChanged.connect(self._odmr_logic.set_average_length,
                                            QtCore.Qt.QueuedConnection)

        # Update signals coming from logic:
        self._odmr_logic.sigParameterUpdated.connect(self.update_parameter,
                                                     QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOutputStateUpdated.connect(self.update_status,
                                                       QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrPlotsUpdated.connect(self.update_plots, QtCore.Qt.QueuedConnection)
        self._mw.odmr_derivative_radioButton.toggled.connect(self.update_for_derivative_plot, QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrLaserDataUpdated.connect(self.update_laser_data, QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrFitUpdated.connect(self.update_fit, QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrElapsedTimeUpdated.connect(self.update_elapsedtime,
                                                           QtCore.Qt.QueuedConnection)

        self._activate_extraction_ui()
        self._connect_extraction_tab_signals()
        self._odmr_logic.sigAnalysisSettingsUpdated.connect(self.analysis_settings_updated)
        self.analysis_settings_updated(self._odmr_logic.pulsed_analysis_settings)
        self._mw.pi_half_DoubleSpinBox.setValue(self.pi_half)

        # Show the Main ODMR GUI:
        self.show()

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        self.pi_half = self._mw.pi_half_DoubleSpinBox.value()
        # Disconnect signals
        self._odmr_logic.sigParameterUpdated.disconnect()
        self._odmr_logic.sigOutputStateUpdated.disconnect()
        self._odmr_logic.sigOdmrPlotsUpdated.disconnect()
        self._odmr_logic.sigOdmrLaserDataUpdated.disconnect()
        self._odmr_logic.sigOdmrFitUpdated.disconnect()
        self._odmr_logic.sigOdmrElapsedTimeUpdated.disconnect()
        self.sigMwOff.disconnect()
        self.sigClearData.disconnect()
        self.sigStartOdmrScan.disconnect()
        self.sigStopOdmrScan.disconnect()
        self.sigDoFit.disconnect()
        self.sigMwSweepParamsChanged.disconnect()

        self.sigSaveMeasurement.disconnect()
        self.sigAverageLinesChanged.disconnect()
        self._mw.action_run_stop.triggered.disconnect()
        self._mw.action_Save.triggered.disconnect()
        self._mw.action_RestoreDefault.triggered.disconnect()
        self._mw.do_fit_PushButton.clicked.disconnect()
        dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
        for identifier_name in dspinbox_dict:
            dspinbox_type_list = dspinbox_dict[identifier_name]
            [dspinbox_type.editingFinished.disconnect() for dspinbox_type in dspinbox_type_list]

        self._mw.sweep_power_DoubleSpinBox.editingFinished.disconnect()
        self._mw.average_level_SpinBox.valueChanged.disconnect()
        self._fsd.sigFitsUpdated.disconnect()
        self._mw.fit_range_SpinBox.editingFinished.disconnect()
        self._mw.action_FitSettings.triggered.disconnect()
        self._disconnect_extraction_tab_signals()
        self._odmr_logic.sigAnalysisSettingsUpdated.disconnect()
        self.saveWindowGeometry(self._mw)
        self._mw.close()
        return 0

    def show(self):
        """Make window visible and put it above all other windows. """
        self._mw.show()
        self._mw.activateWindow()
        self._mw.raise_()

    def _menu_settings(self):
        """ Open the settings menu """
        pass #self._sd.exec_()
    
    def _activate_extraction_ui(self):
        # Configure the lasertrace plot display:
        self.sig_start_line = pg.InfiniteLine(pos=0,
                                              pen={'color': palette.c3, 'width': 1},
                                              movable=True)
        self.sig_end_line = pg.InfiniteLine(pos=0,
                                            pen={'color': palette.c3, 'width': 1},
                                            movable=True)
        self.ref_start_line = pg.InfiniteLine(pos=0,
                                              pen={'color': palette.c4, 'width': 1},
                                              movable=True)
        self.ref_end_line = pg.InfiniteLine(pos=0,
                                            pen={'color': palette.c4, 'width': 1},
                                            movable=True)
        self.lasertrace_image = pg.PlotDataItem(np.arange(10), np.zeros(10), pen=palette.c1)
        self._mw.odmr_matrix_PlotWidget.addItem(self.lasertrace_image)
        self._mw.odmr_matrix_PlotWidget.addItem(self.sig_start_line)
        self._mw.odmr_matrix_PlotWidget.addItem(self.sig_end_line)
        self._mw.odmr_matrix_PlotWidget.addItem(self.ref_start_line)
        self._mw.odmr_matrix_PlotWidget.addItem(self.ref_end_line)
        self._mw.odmr_matrix_PlotWidget.setLabel(axis='bottom', text='time', units='s')
        self._mw.odmr_matrix_PlotWidget.setLabel(axis='left', text='events', units='#')
        self._odmr_logic._initialize_odmr_plots()
    
    def update_laser_data(self, data):
        """

        @return:
        """
        self.log.debug(data)
        if np.isnan(data).any():
            return
        laser_data = data
        y_data = np.sum(laser_data, axis=0)

        # Calculate the x-axis of the laser plot here
        bin_width = self._odmr_logic.bin_width_s
        x_data = np.arange(y_data.size, dtype=float) * bin_width
        mn = x_data.min()
        mx = x_data.max()
        self.sig_start_line.setBounds((mn,mx))
        self.sig_end_line.setBounds((mn,mx))
        self.ref_start_line.setBounds((mn,mx))
        self.ref_end_line.setBounds((mn,mx))

        # Plot data
        try:
            self.lasertrace_image.setData(x=x_data, y=y_data)
        except:
            self.log.warning(f'Data shape might be invalid: {y_data}')
        return
    
    def _connect_extraction_tab_signals(self):
        # Connect pulse extraction tab signals
        self.sig_start_line.sigPositionChangeFinished.connect(self.analysis_settings_changed)
        self.sig_end_line.sigPositionChangeFinished.connect(self.analysis_settings_changed)
        self.ref_start_line.sigPositionChangeFinished.connect(self.analysis_settings_changed)
        self.ref_end_line.sigPositionChangeFinished.connect(self.analysis_settings_changed)
        return

    
    def _disconnect_extraction_tab_signals(self):
        # Connect pulse extraction tab signals
        self.sig_start_line.sigPositionChangeFinished.disconnect()
        self.sig_end_line.sigPositionChangeFinished.disconnect()
        self.ref_start_line.sigPositionChangeFinished.disconnect()
        self.ref_end_line.sigPositionChangeFinished.disconnect()
        return
    
    def sweep_settings_changed(self):
        settings_dict = dict()
        sig_start = self.sweep_start_line.value()
        sig_end = self.sweep_end_line.value()
        settings_dict['signal_start'] = sig_start if sig_start <= sig_end else sig_end
        settings_dict['signal_end'] = sig_end if sig_end >= sig_start else sig_start

        object_dict = self.get_objects_from_groupbox_row(0)
        for object_name in object_dict:
            if "DoubleSpinBox" in object_name:
                if "start" in object_name:
                    object_dict[object_name].setValue(settings_dict['signal_start'])
                elif "stop" in object_name:
                    object_dict[object_name].setValue(settings_dict['signal_end'])

        self.change_sweep_params()
        
        return

    def slope_fit_changed(self):
        x = self._odmr_logic.odmr_plot_x
        def find_nearest(array, value):
            array = np.asarray(array)
            idx = (np.abs(array - value)).argmin()
            return idx
        idx = find_nearest(x, self.slope_start_line.value())
        m = np.gradient(self.vis_arr, x)[int(idx)]
        self._odmr_logic.vis_slope = m
        self._mw.slope_label.setText('{:.2e}'.format(m))
        y = m*x + (-m*(x[int(idx)]))
        self.odmr_slope_line.setData(x,y)
        vb = self.odmr_image.getViewBox()
        vb.setRange(xRange=(x.min(), x.max()), yRange=(self.vis_arr.min(), self.vis_arr.max()))
        

    @QtCore.Slot()
    def analysis_settings_changed(self):
        """

        @return:
        """
        settings_dict = dict()

        sig_start = self.sig_start_line.value()
        sig_end = self.sig_end_line.value()
        ref_start = self.ref_start_line.value()
        ref_end = self.ref_end_line.value()
        settings_dict['signal_start'] = sig_start if sig_start <= sig_end else sig_end
        settings_dict['signal_end'] = sig_end if sig_end >= sig_start else sig_start
        settings_dict['norm_start'] = ref_start if ref_start <= ref_end else ref_end
        settings_dict['norm_end'] = ref_end if ref_end >= ref_start else ref_start

        # odmrlogic set params
        self._odmr_logic.pulsed_analysis_settings = settings_dict
        if self._odmr_logic.module_state() != 'locked':
            self._odmr_logic.analyse_pulsed_meas(self._odmr_logic.pulsed_analysis_settings, self._odmr_logic.laser_data)

        return
    
    @QtCore.Slot(dict)
    def analysis_settings_updated(self, settings_dict):
        """

        @param dict settings_dict: dictionary with parameters to update
        @return:
        """

        # block signals
        self.sig_start_line.blockSignals(True)
        self.sig_end_line.blockSignals(True)
        self.ref_start_line.blockSignals(True)
        self.ref_end_line.blockSignals(True)

        if 'signal_start' in settings_dict:
            self.sig_start_line.setValue(settings_dict['signal_start'])
        if 'norm_start' in settings_dict:
            self.ref_start_line.setValue(settings_dict['norm_start'])
        if 'signal_end' in settings_dict:
            self.sig_end_line.setValue(settings_dict['signal_end'])
        if 'norm_end' in settings_dict:
            self.ref_end_line.setValue(settings_dict['norm_end'])

        # unblock signals
        self.sig_start_line.blockSignals(False)
        self.sig_end_line.blockSignals(False)
        self.ref_start_line.blockSignals(False)
        self.ref_end_line.blockSignals(False)
        return

    def add_ranges_gui_elements_clicked(self):
        """
        When button >>add range<< is pushed add some buttons to the gui and connect accordingly to the
        logic.
        :return:
        """
        # make sure the logic keeps track
        groupBox = self._mw.odmr_control_DockWidget.ranges_groupBox
        gridLayout = groupBox.layout()
        constraints = self._odmr_logic.get_hw_constraints()

        insertion_row = self._odmr_logic.ranges
        # start
        start_label = QtWidgets.QLabel(groupBox)
        start_label.setText('Start:')
        setattr(self._mw.odmr_control_DockWidget, 'start_label_{}'.format(insertion_row), start_label)
        start_freq_DoubleSpinBox = ScienDSpinBox(groupBox)
        start_freq_DoubleSpinBox.setSuffix('Hz')
        start_freq_DoubleSpinBox.setMaximum(constraints.max_frequency)
        start_freq_DoubleSpinBox.setMinimum(constraints.min_frequency)
        start_freq_DoubleSpinBox.setMinimumSize(QtCore.QSize(80, 0))
        start_freq_DoubleSpinBox.setValue(self._odmr_logic.mw_starts[0])
        start_freq_DoubleSpinBox.setMinimumWidth(75)
        start_freq_DoubleSpinBox.setMaximumWidth(100)
        start_freq_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
        setattr(self._mw.odmr_control_DockWidget, 'start_freq_DoubleSpinBox_{}'.format(insertion_row),
                start_freq_DoubleSpinBox)
        gridLayout.addWidget(start_label, insertion_row, 1, 1, 1)
        gridLayout.addWidget(start_freq_DoubleSpinBox, insertion_row, 2, 1, 1)

        # step
        step_label = QtWidgets.QLabel(groupBox)
        step_label.setText('Step:')
        setattr(self._mw.odmr_control_DockWidget, 'step_label_{}'.format(insertion_row), step_label)
        step_freq_DoubleSpinBox = ScienDSpinBox(groupBox)
        step_freq_DoubleSpinBox.setSuffix('Hz')
        step_freq_DoubleSpinBox.setMaximum(100e9)
        step_freq_DoubleSpinBox.setMinimumSize(QtCore.QSize(80, 0))
        step_freq_DoubleSpinBox.setValue(self._odmr_logic.mw_steps[0])
        step_freq_DoubleSpinBox.setMinimumWidth(75)
        step_freq_DoubleSpinBox.setMaximumWidth(100)
        step_freq_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
        setattr(self._mw.odmr_control_DockWidget, 'step_freq_DoubleSpinBox_{}'.format(insertion_row),
                step_freq_DoubleSpinBox)
        gridLayout.addWidget(step_label, insertion_row, 3, 1, 1)
        gridLayout.addWidget(step_freq_DoubleSpinBox, insertion_row, 4, 1, 1)

        # stop
        stop_label = QtWidgets.QLabel(groupBox)
        stop_label.setText('Stop:')
        setattr(self._mw.odmr_control_DockWidget, 'stop_label_{}'.format(insertion_row), stop_label)
        stop_freq_DoubleSpinBox = ScienDSpinBox(groupBox)
        stop_freq_DoubleSpinBox.setSuffix('Hz')
        stop_freq_DoubleSpinBox.setMaximum(constraints.max_frequency)
        stop_freq_DoubleSpinBox.setMinimum(constraints.min_frequency)
        stop_freq_DoubleSpinBox.setMinimumSize(QtCore.QSize(80, 0))
        stop_freq_DoubleSpinBox.setValue(self._odmr_logic.mw_stops[0])
        stop_freq_DoubleSpinBox.setMinimumWidth(75)
        stop_freq_DoubleSpinBox.setMaximumWidth(100)
        stop_freq_DoubleSpinBox.editingFinished.connect(self.change_sweep_params)
        setattr(self._mw.odmr_control_DockWidget, 'stop_freq_DoubleSpinBox_{}'.format(insertion_row),
                stop_freq_DoubleSpinBox)

        gridLayout.addWidget(stop_label, insertion_row, 5, 1, 1)
        gridLayout.addWidget(stop_freq_DoubleSpinBox, insertion_row, 6, 1, 1)

        starts = self.get_frequencies_from_spinboxes('start')
        stops = self.get_frequencies_from_spinboxes('stop')
        steps = self.get_frequencies_from_spinboxes('step')
        power = self._mw.sweep_power_DoubleSpinBox.value()

        self.sigMwSweepParamsChanged.emit(starts, stops, steps, power)
        self._mw.fit_range_SpinBox.setMaximum(self._odmr_logic.ranges)
        # self._mw.odmr_control_DockWidget.matrix_range_SpinBox.setMaximum(self._odmr_logic.ranges)
        self._odmr_logic.ranges += 1

        # remove stuff that remained from the old range that might have been in place there
        key = 'channel: {0}, range: {1}'.format(self.display_channel, self._odmr_logic.ranges - 1)
        if key in self._odmr_logic.fits_performed:
            self._odmr_logic.fits_performed.pop(key)
        return

    def remove_ranges_gui_elements_clicked(self):
        if self._odmr_logic.ranges == 1:
            return

        remove_row = self._odmr_logic.ranges - 1

        groupBox = self._mw.odmr_control_DockWidget.ranges_groupBox
        gridLayout = groupBox.layout()

        object_dict = self.get_objects_from_groupbox_row(remove_row)

        for object_name in object_dict:
            if 'DoubleSpinBox' in object_name:
                object_dict[object_name].editingFinished.disconnect()
            object_dict[object_name].hide()
            gridLayout.removeWidget(object_dict[object_name])
            del self._mw.odmr_control_DockWidget.__dict__[object_name]

        starts = self.get_frequencies_from_spinboxes('start')
        stops = self.get_frequencies_from_spinboxes('stop')
        steps = self.get_frequencies_from_spinboxes('step')
        power = self._mw.sweep_power_DoubleSpinBox.value()
        self.sigMwSweepParamsChanged.emit(starts, stops, steps, power)

        # in case the removed range is the one selected for fitting right now adjust the value
        self._odmr_logic.ranges -= 1
        max_val = self._odmr_logic.ranges - 1
        self._mw.fit_range_SpinBox.setMaximum(max_val)
        if self._odmr_logic.range_to_fit > max_val:
            self._odmr_logic.range_to_fit = max_val

        self._mw.fit_range_SpinBox.setMaximum(max_val)
        return

    def get_objects_from_groupbox_row(self, row):
        # get elements from the row
        # first strings

        start_label_str = 'start_label_{}'.format(row)
        step_label_str = 'step_label_{}'.format(row)
        stop_label_str = 'stop_label_{}'.format(row)

        # get widgets
        start_freq_DoubleSpinBox_str = 'start_freq_DoubleSpinBox_{}'.format(row)
        step_freq_DoubleSpinBox_str = 'step_freq_DoubleSpinBox_{}'.format(row)
        stop_freq_DoubleSpinBox_str = 'stop_freq_DoubleSpinBox_{}'.format(row)

        # now get the objects
        start_label = getattr(self._mw.odmr_control_DockWidget, start_label_str)
        step_label = getattr(self._mw.odmr_control_DockWidget, step_label_str)
        stop_label = getattr(self._mw.odmr_control_DockWidget, stop_label_str)

        start_freq_DoubleSpinBox = getattr(self._mw.odmr_control_DockWidget, start_freq_DoubleSpinBox_str)
        step_freq_DoubleSpinBox = getattr(self._mw.odmr_control_DockWidget, step_freq_DoubleSpinBox_str)
        stop_freq_DoubleSpinBox = getattr(self._mw.odmr_control_DockWidget, stop_freq_DoubleSpinBox_str)

        return_dict = {start_label_str: start_label, step_label_str: step_label,
                       stop_label_str: stop_label,
                       start_freq_DoubleSpinBox_str: start_freq_DoubleSpinBox,
                       step_freq_DoubleSpinBox_str: step_freq_DoubleSpinBox,
                       stop_freq_DoubleSpinBox_str: stop_freq_DoubleSpinBox
                       }

        return return_dict

    def get_freq_dspinboxes_from_groubpox(self, identifier):
        dspinboxes = []
        for name in self._mw.odmr_control_DockWidget.__dict__:
            box_name = identifier + '_freq_DoubleSpinBox'
            if box_name in name:
                freq_DoubleSpinBox = getattr(self._mw.odmr_control_DockWidget, name)
                dspinboxes.append(freq_DoubleSpinBox)

        return dspinboxes

    def get_all_dspinboxes_from_groupbox(self):
        identifiers = ['start', 'step', 'stop']

        all_spinboxes = {}
        for identifier in identifiers:
            all_spinboxes[identifier] = self.get_freq_dspinboxes_from_groubpox(identifier)

        return all_spinboxes

    def get_frequencies_from_spinboxes(self, identifier):
        dspinboxes = self.get_freq_dspinboxes_from_groubpox(identifier)
        freqs = [dspinbox.value() for dspinbox in dspinboxes]
        return freqs

    def run_stop_odmr(self, is_checked):
        """ Manages what happens if odmr scan is started/stopped. """
        if is_checked:
            # change the axes appearance according to input values:
            self._mw.odmr_PlotWidget.removeItem(self.odmr_fit_image)
            self._mw.sweep_power_DoubleSpinBox.setEnabled(False)

            dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
            for identifier_name in dspinbox_dict:
                dspinbox_type_list = dspinbox_dict[identifier_name]
                [dspinbox_type.setEnabled(False) for dspinbox_type in dspinbox_type_list]

            self._odmr_logic.pi_half_pulse = self._mw.pi_half_DoubleSpinBox.value()
            self.sigStartOdmrScan.emit()
        else:
            self.sigStopOdmrScan.emit()
        return


    def update_status(self, mw_mode, is_running):
        """
        Update the display for a change in the microwave status (mode and output).

        @param str mw_mode: is the microwave output active?
        @param bool is_running: is the microwave output active?
        """
        # Block signals from firing
        self._mw.action_run_stop.blockSignals(True)

        # Update measurement status (activate/deactivate widgets/actions)
        if is_running:
            dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
            for identifier_name in dspinbox_dict:
                dspinbox_type_list = dspinbox_dict[identifier_name]
                [dspinbox_type.setEnabled(True) for dspinbox_type in dspinbox_type_list]

        else:
            self._mw.sweep_power_DoubleSpinBox.setEnabled(True)

            dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
            for identifier_name in dspinbox_dict:
                dspinbox_type_list = dspinbox_dict[identifier_name]
                [dspinbox_type.setEnabled(True) for dspinbox_type in dspinbox_type_list]

            self._mw.action_run_stop.setChecked(False)

        # Unblock signal firing
        self._mw.action_run_stop.blockSignals(False)

        return

    def clear_odmr_data(self):
        """ Clear the ODMR data. """
        self.sigClearData.emit()
        return

    def update_for_derivative_plot(self):
        try:
            self.update_plots(self._odmr_logic.odmr_plot_x, self._odmr_logic.odmr_plot_y, self._odmr_logic.odmr_plot_xy, self._odmr_logic.odmr_plot_y_err)
        except:
            self.log.warning('Measurement data shape incorrect for derivative. Repeat measurement.')
        return

    def update_plots(self, odmr_data_x, odmr_data_y, odmr_matrix, odmr_data_y_err):
        """ Refresh the plot widgets with new data. """
        # Update mean signal plot
        x_data = odmr_data_x
        mn = x_data.min()
        mx = x_data.max()
        self.sweep_start_line.setPos(mn)
        self.sweep_end_line.setPos(mx)
        if self._mw.odmr_derivative_radioButton.isChecked():
            def vis(lm, param, res, delta):
                c2, c1 = lm.eval(param, x = np.array([res-delta, res+delta]))
                return (c1-c2)/(c1+c2)
            
            fit = self._fitlogic.make_lorentzian_fit(x_data,odmr_data_y[self.display_channel],estimator=self._fitlogic.estimate_lorentzian_dip)
            self.vis_arr = np.array([vis(fit.model, fit.params, x, fit.params['fwhm'].value/2) for x in x_data])

            self._mw.odmr_PlotWidget.setLabel(axis='left', text='ODMR visibility', units='Counts/s²')
            self._mw.odmr_PlotWidget.setLabel(axis='bottom', text='Frequency', units='Hz')
            # dx = odmr_data_x[1] - odmr_data_x[0]
            # dy = np.gradient(odmr_data_y[self.display_channel], dx)
            self.odmr_image.setData(odmr_data_x, self.vis_arr)
            self.slope_start_line.setPos(odmr_data_x[int(len(odmr_data_x)/2)])
            
            self._mw.odmr_PlotWidget.removeItem(self.signal_image_error_bars)
            self._mw.odmr_PlotWidget.removeItem(self.odmr_fit_image)
            self._mw.odmr_PlotWidget.addItem(self.odmr_slope_line)
            self._mw.odmr_PlotWidget.addItem(self.slope_start_line)
            self.slope_fit_changed()
            
        else:
            self._mw.odmr_PlotWidget.setLabel(axis='left', text='Counts', units='Counts/s')
            self._mw.odmr_PlotWidget.setLabel(axis='bottom', text='Frequency', units='Hz')
            self.odmr_image.setData(odmr_data_x, odmr_data_y[self.display_channel])
            
            tmp_array = x_data[1:] - x_data[:-1]
            if len(tmp_array) > 0:
                beamwidth = tmp_array.min() if tmp_array.min() > 0 else tmp_array.max()
            else:
                beamwidth = 0
            del tmp_array
            beamwidth /= 3
            self._mw.odmr_PlotWidget.addItem(self.signal_image_error_bars)
            self._mw.odmr_PlotWidget.removeItem(self.odmr_slope_line)
            self._mw.odmr_PlotWidget.removeItem(self.slope_start_line)
            self._mw.slope_label.setText('{:.2e}'.format(0))
            self.signal_image_error_bars.setData(x=x_data,
                                                y=odmr_data_y[self.display_channel],
                                                top=odmr_data_y_err,
                                                bottom=odmr_data_y_err,
                                                beam=beamwidth)

    def update_channel(self, index):
        self.display_channel = int(
            self._mw.odmr_channel_ComboBox.itemData(index, QtCore.Qt.UserRole))
        self.update_plots(
            self._odmr_logic.odmr_plot_x,
            self._odmr_logic.odmr_plot_y,
            self._odmr_logic.odmr_plot_xy)

    def average_level_changed(self):
        """
        Sends to lines to average to the logic
        """
        self.sigAverageLinesChanged.emit(self._mw.average_level_SpinBox.value())
        return

    def colorscale_changed(self):
        """
        Updates the range of the displayed colorscale in both the colorbar and the matrix plot.
        """
        cb_range = self.get_matrix_cb_range()
        self.update_colorbar(cb_range)
        # matrix_image = self.odmr_matrix_image.image
        # self.odmr_matrix_image.setImage(image=matrix_image, levels=(cb_range[0], cb_range[1]))
        return


    def restore_defaultview(self):
        self._mw.restoreGeometry(self.mwsettings.value("geometry", ""))
        self._mw.restoreState(self.mwsettings.value("windowState", ""))

    def update_elapsedtime(self, elapsed_time, scanned_lines):
        """ Updates current elapsed measurement time and completed frequency sweeps """
        self._mw.elapsed_time_DisplayWidget.display(int(np.rint(elapsed_time)))
        self._mw.elapsed_sweeps_DisplayWidget.display(scanned_lines)
        return

    def update_settings(self):
        """ Write the new settings from the gui to the file. """
        return

    def reject_settings(self):
        """ Keep the old settings and restores the old settings in the gui. """
        return

    def do_fit(self):
        fit_function = self._mw.fit_methods_ComboBox.getCurrentFit()[0]
        if self._mw.odmr_derivative_radioButton.isChecked():
            odmr_data_x  = self._odmr_logic.odmr_plot_x
            odmr_data_y = self._odmr_logic.odmr_plot_y
            dx = odmr_data_x[1] - odmr_data_x[0]
            dy = np.gradient(odmr_data_y[self.display_channel], dx)
            x = odmr_data_x
            y = dy
        else:
            x = None
            y = None
        self.sigDoFit.emit(fit_function, x, y, self._mw.odmr_channel_ComboBox.currentIndex(),
                           self._mw.fit_range_SpinBox.value())
        return

    def update_fit(self, x_data, y_data, result_str_dict, current_fit):
        """ Update the shown fit. """
        if current_fit != 'No Fit':
            # display results as formatted text
            self._mw.odmr_fit_results_DisplayWidget.clear()
            try:
                formated_results = units.create_formatted_output(result_str_dict)
            except:
                formated_results = 'this fit does not return formatted results'
            self._mw.odmr_fit_results_DisplayWidget.setPlainText(formated_results)

        self._mw.fit_methods_ComboBox.blockSignals(True)
        self._mw.fit_methods_ComboBox.setCurrentFit(current_fit)
        self._mw.fit_methods_ComboBox.blockSignals(False)

        # check which Fit method is used and remove or add again the
        # odmr_fit_image, check also whether a odmr_fit_image already exists.
        if current_fit != 'No Fit':
            self.odmr_fit_image.setData(x=x_data, y=y_data)
            if self.odmr_fit_image not in self._mw.odmr_PlotWidget.listDataItems():
                self._mw.odmr_PlotWidget.addItem(self.odmr_fit_image)
        else:
            if self.odmr_fit_image in self._mw.odmr_PlotWidget.listDataItems():
                self._mw.odmr_PlotWidget.removeItem(self.odmr_fit_image)

        self._mw.odmr_PlotWidget.getViewBox().updateAutoRange()
        return

    def update_fit_range(self):
        self._odmr_logic.range_to_fit = self._mw.fit_range_SpinBox.value()
        return

    def update_parameter(self, param_dict):
        """ Update the parameter display in the GUI.

        @param param_dict:
        @return:

        Any change event from the logic should call this update function.
        The update will block the GUI signals from emitting a change back to the
        logic.
        """
        param = param_dict.get('sweep_mw_power')
        if param is not None:
            self._mw.sweep_power_DoubleSpinBox.blockSignals(True)
            self._mw.sweep_power_DoubleSpinBox.setValue(param)
            self._mw.sweep_power_DoubleSpinBox.blockSignals(False)

        mw_starts = param_dict.get('mw_starts')
        mw_steps = param_dict.get('mw_steps')
        mw_stops = param_dict.get('mw_stops')

        if mw_starts is not None:
            start_frequency_boxes = self.get_freq_dspinboxes_from_groubpox('start')
            for mw_start, start_frequency_box in zip(mw_starts, start_frequency_boxes):
                start_frequency_box.blockSignals(True)
                start_frequency_box.setValue(mw_start)
                start_frequency_box.blockSignals(False)

        if mw_steps is not None:
            step_frequency_boxes = self.get_freq_dspinboxes_from_groubpox('step')
            for mw_step, step_frequency_box in zip(mw_steps, step_frequency_boxes):
                step_frequency_box.blockSignals(True)
                step_frequency_box.setValue(mw_step)
                step_frequency_box.blockSignals(False)

        if mw_stops is not None:
            stop_frequency_boxes = self.get_freq_dspinboxes_from_groubpox('stop')
            for mw_stop, stop_frequency_box in zip(mw_stops, stop_frequency_boxes):
                stop_frequency_box.blockSignals(True)
                stop_frequency_box.setValue(mw_stop)
                stop_frequency_box.blockSignals(False)

        param = param_dict.get('average_length')
        if param is not None:
            self._mw.average_level_SpinBox.blockSignals(True)
            self._mw.average_level_SpinBox.setValue(param)
            self._mw.average_level_SpinBox.blockSignals(False)
        return

    ############################################################################
    #                           Change Methods                                 #
    ############################################################################

    def change_sweep_params(self):
        """ Change start, stop and step frequency of frequency sweep """
        starts = []
        steps = []
        stops = []

        num = self._odmr_logic.ranges

        for counter in range(num):
            # construct strings
            start, stop, step = self.get_frequencies_from_row(counter)

            starts.append(start)
            steps.append(step)
            stops.append(stop)

        power = self._mw.sweep_power_DoubleSpinBox.value()
        self.sweep_start_line.setPos(starts[0])
        self.sweep_end_line.setPos(stops[0])
        self.sigMwSweepParamsChanged.emit(starts, stops, steps, power)
        return

    def change_fit_range(self):
        self._odmr_logic.fit_range = self._mw.fit_range_SpinBox.value()
        return

    def get_frequencies_from_row(self, row):
        object_dict = self.get_objects_from_groupbox_row(row)
        for object_name in object_dict:
            if "DoubleSpinBox" in object_name:
                if "start" in object_name:
                    start = object_dict[object_name].value()
                elif "step" in object_name:
                    step = object_dict[object_name].value()
                elif "stop" in object_name:
                    stop = object_dict[object_name].value()

        return start, stop, step


    def save_data(self):
        """ Save the sum plot, the scan marix plot and the scan data """
        filetag = self._mw.save_tag_LineEdit.text()
        self.sigSaveMeasurement.emit(filetag)
        return
