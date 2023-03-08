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

from core.connector import Connector, StatusVar
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


class ODMRSettingDialog(QtWidgets.QDialog):
    """ The settings dialog for ODMR measurements.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_odmr_settings.ui')

        # Load it
        super(ODMRSettingDialog, self).__init__()
        uic.loadUi(ui_file, self)


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
    sigCwMwOn = QtCore.Signal()
    sigMwOff = QtCore.Signal()
    sigMwPowerChanged = QtCore.Signal(float)
    sigMwCwParamsChanged = QtCore.Signal(float, float)
    sigMwSweepParamsChanged = QtCore.Signal(list, list, list, float)
    sigClockFreqChanged = QtCore.Signal(float)
    sigOptBaySettingsChanged = QtCore.Signal(dict)
    sigOversamplingChanged = QtCore.Signal(int)
    sigLockInChanged = QtCore.Signal(bool)
    sigFitChanged = QtCore.Signal(str)
    sigRuntimeChanged = QtCore.Signal(float)
    sigDoFit = QtCore.Signal(str, object, object, int, int)
    sigSaveMeasurement = QtCore.Signal(str)
    sigAverageLinesChanged = QtCore.Signal(int)

    clock_frequency = StatusVar('clock_frequency', default=100)
    contrast = StatusVar('contrast', default=30)
    offset = StatusVar('offset', default=100e3)
    amp_noise = StatusVar('amp_noise', default=5e3)
    esr_fwhm = StatusVar('esr_fwhm', default=7e6)
    err_margin_x0 = StatusVar('err_margin_x0', default=1e6)
    err_margin_offset = StatusVar('err_margin_offset', default=10e3)
    err_margin_contrast = StatusVar('err_margin_contrast', default=1)
    n_samples = StatusVar('n_samples', default=50e3)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition, configuration and initialisation of the ODMR GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        """

        self._odmr_logic = self.odmrlogic1()

        # Use the inherited class 'Ui_ODMRGuiUI' to create now the GUI element:
        self._mw = ODMRMainWindow()
        self.restoreWindowPos(self._mw)
        self._sd = ODMRSettingDialog()

        # Create a QSettings object for the mainwindow and store the actual GUI layout
        self.mwsettings = QtCore.QSettings("QUDI", "ODMR")
        self.mwsettings.setValue("geometry", self._mw.saveGeometry())
        self.mwsettings.setValue("windowState", self._mw.saveState())

        # Get hardware constraints to set limits for input widgets
        constraints = self._odmr_logic.get_hw_constraints()

        # Adjust range of scientific spinboxes above what is possible in Qt Designer
        self._mw.cw_power_DoubleSpinBox.setMaximum(constraints.max_power)
        self._mw.cw_power_DoubleSpinBox.setMinimum(constraints.min_power)

        # Add save file tag input box
        self._mw.save_tag_LineEdit = QtWidgets.QLineEdit(self._mw)
        self._mw.save_tag_LineEdit.setMaximumWidth(500)
        self._mw.save_tag_LineEdit.setMinimumWidth(200)
        self._mw.save_tag_LineEdit.setToolTip('Enter a nametag which will be\n'
                                              'added to the filename.')
        self._mw.save_ToolBar.addWidget(self._mw.save_tag_LineEdit)

        # Set up and connect channel combobox
        self.display_channel = 0

        self.odmr_image = pg.PlotDataItem(self._odmr_logic.odmr_plot_x,
                                          self._odmr_logic.odmr_plot_y,
                                          pen=pg.mkPen(palette.c1, style=QtCore.Qt.NoPen),
                                          symbol='o',
                                          symbolPen=palette.c1,
                                          symbolBrush=palette.c1,
                                          symbolSize=7)

        self.odmr_fit_image = pg.PlotDataItem(self._odmr_logic.odmr_fit_x,
                                              self._odmr_logic.odmr_fit_y,
                                              pen=pg.mkPen(palette.c2))

        # Add the display item to the xy and xz ViewWidget, which was defined in the UI file.
        self._mw.odmr_PlotWidget.addItem(self.odmr_image)
        self._mw.odmr_PlotWidget.setLabel(axis='left', text='Counts', units='Counts/s')
        self._mw.odmr_PlotWidget.setLabel(axis='bottom', text='Frequency', units='Hz')
        self._mw.odmr_PlotWidget.showGrid(x=True, y=True, alpha=0.8)


        ########################################################################
        #          Configuration of the various display Widgets                #
        ########################################################################
        # Take the default values from logic:
        self._mw.cw_power_DoubleSpinBox.setValue(self._odmr_logic.cw_mw_power)

        self._mw.runtime_DoubleSpinBox.setValue(self._odmr_logic.run_time)
        self._mw.elapsed_time_DisplayWidget.display(int(np.rint(self._odmr_logic.elapsed_time)))
        self._mw.elapsed_sweeps_DisplayWidget.display(self._odmr_logic.elapsed_sweeps)
        self._mw.average_level_SpinBox.setValue(self._odmr_logic.lines_to_average)

        self._sd.clock_frequency_DoubleSpinBox.setValue(self._odmr_logic.clock_frequency)

        # fit settings
        self._fsd = FitSettingsDialog(self._odmr_logic.fc)
        self._fsd.sigFitsUpdated.connect(self._mw.fit_methods_ComboBox.setFitFunctions)
        self._fsd.applySettings()
        self._mw.action_FitSettings.triggered.connect(self._fsd.show)

        ########################################################################
        #                       Connect signals                                #
        ########################################################################
        # Internal user input changed signals
        self._mw.cw_power_DoubleSpinBox.editingFinished.connect(self.change_cw_params)
        self._mw.runtime_DoubleSpinBox.editingFinished.connect(self.change_runtime)
        self._mw.average_level_SpinBox.valueChanged.connect(self.average_level_changed)
        self.average_level_changed()
        # Internal trigger signals
        self._mw.action_run_stop.triggered.connect(self.run_stop_odmr)
        self._mw.action_resume_odmr.triggered.connect(self.resume_odmr)
        self._mw.action_Save.triggered.connect(self.save_data)
        self._mw.action_RestoreDefault.triggered.connect(self.restore_defaultview)
        self._mw.do_fit_PushButton.clicked.connect(self.do_fit)

        # Control/values-changed signals to logic
        self.sigCwMwOn.connect(self._odmr_logic.mw_cw_on, QtCore.Qt.QueuedConnection)
        self.sigMwOff.connect(self._odmr_logic.mw_off, QtCore.Qt.QueuedConnection)
        self.sigStartOdmrScan.connect(self._odmr_logic.start_odmr_scan, QtCore.Qt.QueuedConnection)
        self.sigStopOdmrScan.connect(self._odmr_logic.stop_odmr_scan, QtCore.Qt.QueuedConnection)
        self.sigContinueOdmrScan.connect(self._odmr_logic.continue_odmr_scan,
                                         QtCore.Qt.QueuedConnection)
        self.sigDoFit.connect(self._odmr_logic.do_fit, QtCore.Qt.QueuedConnection)
        self.sigMwCwParamsChanged.connect(self._odmr_logic.set_cw_parameters,
                                          QtCore.Qt.QueuedConnection)
        self.sigMwSweepParamsChanged.connect(self._odmr_logic.set_sweep_parameters,
                                             QtCore.Qt.QueuedConnection)
        self.sigRuntimeChanged.connect(self._odmr_logic.set_runtime, QtCore.Qt.QueuedConnection)
        self.sigClockFreqChanged.connect(self._odmr_logic.set_clock_frequency,
                                         QtCore.Qt.QueuedConnection)
        self.sigOptBaySettingsChanged.connect(self._odmr_logic.set_opt_bay_settings,
                                         QtCore.Qt.QueuedConnection)
        self.sigOversamplingChanged.connect(self._odmr_logic.set_oversampling, QtCore.Qt.QueuedConnection)
        self.sigLockInChanged.connect(self._odmr_logic.set_lock_in, QtCore.Qt.QueuedConnection)
        self.sigSaveMeasurement.connect(self._odmr_logic.save_odmr_data, QtCore.Qt.QueuedConnection)
        self.sigAverageLinesChanged.connect(self._odmr_logic.set_average_length,
                                            QtCore.Qt.QueuedConnection)

        # Update signals coming from logic:
        self._odmr_logic.sigParameterUpdated.connect(self.update_parameter,
                                                     QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOutputStateUpdated.connect(self.update_status,
                                                       QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrPlotsUpdated.connect(self.update_plots, QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrFitUpdated.connect(self.update_fit, QtCore.Qt.QueuedConnection)
        self._odmr_logic.sigOdmrElapsedTimeUpdated.connect(self.update_elapsedtime,
                                                           QtCore.Qt.QueuedConnection)

        # connect settings signals
        self._mw.action_Settings.triggered.connect(self._menu_settings)
        self._sd.accepted.connect(self.update_settings)
        self._sd.rejected.connect(self.reject_settings)
        self._sd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(
            self.update_settings)
        self.update_settings()
        self._mw.fit_methods_ComboBox.setCurrentFit('Lorentzian dip')

        self._mw.start_freq_DoubleSpinBox_0.valueChanged.connect(self.change_sweep_params)
        self._mw.step_freq_DoubleSpinBox_0.valueChanged.connect(self.change_sweep_params)
        self._mw.stop_freq_DoubleSpinBox_0.valueChanged.connect(self.change_sweep_params)
        self._mw.cw_power_DoubleSpinBox.valueChanged.connect(self.change_sweep_params)
        
        self.retrieve_status_vars()
        self.change_sweep_params()

        # Show the Main ODMR GUI:
        self.show()

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        # Disconnect signals
        self.store_status_vars()
        self._sd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.disconnect()
        self._sd.accepted.disconnect()
        self._sd.rejected.disconnect()
        self._mw.action_Settings.triggered.disconnect()
        self._odmr_logic.sigParameterUpdated.disconnect()
        self._odmr_logic.sigOutputStateUpdated.disconnect()
        self._odmr_logic.sigOdmrPlotsUpdated.disconnect()
        self._odmr_logic.sigOdmrFitUpdated.disconnect()
        self._odmr_logic.sigOdmrElapsedTimeUpdated.disconnect()
        self.sigCwMwOn.disconnect()
        self.sigMwOff.disconnect()
        self.sigStartOdmrScan.disconnect()
        self.sigStopOdmrScan.disconnect()
        self.sigContinueOdmrScan.disconnect()
        self.sigDoFit.disconnect()
        self.sigMwCwParamsChanged.disconnect()
        self.sigMwSweepParamsChanged.disconnect()
        self.sigRuntimeChanged.disconnect()
        self.sigClockFreqChanged.disconnect()
        self.sigOptBaySettingsChanged.disconnect()
        self.sigOversamplingChanged.disconnect()
        self.sigLockInChanged.disconnect()
        self.sigSaveMeasurement.disconnect()
        self.sigAverageLinesChanged.disconnect()
        self._mw.action_run_stop.triggered.disconnect()
        self._mw.action_resume_odmr.triggered.disconnect()
        self._mw.action_Save.triggered.disconnect()
        self._mw.action_RestoreDefault.triggered.disconnect()
        self._mw.do_fit_PushButton.clicked.disconnect()
        dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
        for identifier_name in dspinbox_dict:
            dspinbox_type_list = dspinbox_dict[identifier_name]
            [dspinbox_type.editingFinished.disconnect() for dspinbox_type in dspinbox_type_list]

        self._mw.cw_power_DoubleSpinBox.editingFinished.disconnect()
        self._mw.runtime_DoubleSpinBox.editingFinished.disconnect()
        self._fsd.sigFitsUpdated.disconnect()
        self._mw.action_FitSettings.triggered.disconnect()
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
        self._sd.exec_()

    def retrieve_status_vars(self):
        self._sd.clock_frequency_DoubleSpinBox.setValue(self.clock_frequency )
        self._sd.esr_contrast_SpinBox.setValue(self.contrast )
        self._sd.esr_offset_SpinBox.setValue(self.offset )
        self._sd.esr_noise_SpinBox.setValue( self.amp_noise )
        self._sd.esr_fwhm_SpinBox.setValue(self.esr_fwhm )
        self._sd.esr_errorMarginCenter_SpinBox.setValue(self.err_margin_x0 )
        self._sd.esr_errorMarginOffset_SpinBox.setValue(self.err_margin_offset )
        self._sd.esr_errorMarginContrast_SpinBox.setValue(self.err_margin_contrast )
        self._sd.esr_nSamples_SpinBox.setValue(self.n_samples )
    
    def store_status_vars(self):
        self.clock_frequency = self._sd.clock_frequency_DoubleSpinBox.value()
        self.contrast = self._sd.esr_contrast_SpinBox.value()
        self.offset = self._sd.esr_offset_SpinBox.value()
        self.amp_noise = self._sd.esr_noise_SpinBox.value() 
        self.esr_fwhm = self._sd.esr_fwhm_SpinBox.value()
        self.err_margin_x0 = self._sd.esr_errorMarginCenter_SpinBox.value()
        self.err_margin_offset = self._sd.esr_errorMarginOffset_SpinBox.value()
        self.err_margin_contrast = self._sd.esr_errorMarginContrast_SpinBox.value()
        self.n_samples = self._sd.esr_nSamples_SpinBox.value()
      
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
            
            dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
            for identifier_name in dspinbox_dict:
                dspinbox_type_list = dspinbox_dict[identifier_name]
                [dspinbox_type.setEnabled(False) for dspinbox_type in dspinbox_type_list]
            
            self._mw.cw_power_DoubleSpinBox.setEnabled(False)
            self._mw.action_resume_odmr.setEnabled(False)

            self._mw.start_freq_DoubleSpinBox_0.setEnabled(False)
            self._mw.step_freq_DoubleSpinBox_0.setEnabled(False)
            self._mw.stop_freq_DoubleSpinBox_0.setEnabled(False)
            self.sigStartOdmrScan.emit()
        else:
            self._mw.action_resume_odmr.setEnabled(True)
            self._mw.cw_power_DoubleSpinBox.setEnabled(True)
            
            self._mw.start_freq_DoubleSpinBox_0.setEnabled(True)
            self._mw.step_freq_DoubleSpinBox_0.setEnabled(True)
            self._mw.stop_freq_DoubleSpinBox_0.setEnabled(True)
            self.sigStopOdmrScan.emit()
        return

    def resume_odmr(self, is_checked):
        if is_checked:
            self._mw.action_run_stop.setEnabled(False)
            self._mw.action_resume_odmr.setEnabled(True)
            dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
            for identifier_name in dspinbox_dict:
                dspinbox_type_list = dspinbox_dict[identifier_name]
                [dspinbox_type.setEnabled(False) for dspinbox_type in dspinbox_type_list]
            self._mw.runtime_DoubleSpinBox.setEnabled(False)
            self._sd.clock_frequency_DoubleSpinBox.setEnabled(False)

            self._mw.cw_power_DoubleSpinBox.setEnabled(False)

            self._mw.start_freq_DoubleSpinBox_0.setEnabled(False)
            self._mw.step_freq_DoubleSpinBox_0.setEnabled(False)
            self._mw.stop_freq_DoubleSpinBox_0.setEnabled(False)
            self.sigContinueOdmrScan.emit()
        else:
            self._mw.cw_power_DoubleSpinBox.setEnabled(True)
            
            self._mw.start_freq_DoubleSpinBox_0.setEnabled(True)
            self._mw.step_freq_DoubleSpinBox_0.setEnabled(True)
            self._mw.stop_freq_DoubleSpinBox_0.setEnabled(True)

            self._mw.action_run_stop.setEnabled(True)
            self._mw.action_resume_odmr.setEnabled(True)
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
        self._mw.action_resume_odmr.blockSignals(True)
        self._mw.action_toggle_cw.blockSignals(True)

        # Update measurement status (activate/deactivate widgets/actions)
        if is_running:
            self._mw.action_resume_odmr.setEnabled(False)
            self._mw.cw_power_DoubleSpinBox.setEnabled(False)
            if mw_mode != 'cw':
                self._mw.action_run_stop.setEnabled(True)
                self._mw.action_toggle_cw.setEnabled(False)
                dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
                for identifier_name in dspinbox_dict:
                    dspinbox_type_list = dspinbox_dict[identifier_name]
                    [dspinbox_type.setEnabled(False) for dspinbox_type in dspinbox_type_list]
                self._mw.runtime_DoubleSpinBox.setEnabled(False)
                self._sd.clock_frequency_DoubleSpinBox.setEnabled(False)
                self._mw.action_run_stop.setChecked(True)
                self._mw.action_resume_odmr.setChecked(True)
            else:
                self._mw.action_run_stop.setEnabled(False)
                dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
                for identifier_name in dspinbox_dict:
                    dspinbox_type_list = dspinbox_dict[identifier_name]
                    [dspinbox_type.setEnabled(True) for dspinbox_type in dspinbox_type_list]
                self._mw.runtime_DoubleSpinBox.setEnabled(True)
                self._sd.clock_frequency_DoubleSpinBox.setEnabled(True)
                self._mw.action_run_stop.setChecked(False)
                self._mw.action_resume_odmr.setChecked(False)
        else:
            self._mw.action_resume_odmr.setEnabled(True)
            self._mw.cw_power_DoubleSpinBox.setEnabled(True)
            self._mw.action_run_stop.setEnabled(True)
            dspinbox_dict = self.get_all_dspinboxes_from_groupbox()
            for identifier_name in dspinbox_dict:
                dspinbox_type_list = dspinbox_dict[identifier_name]
                [dspinbox_type.setEnabled(True) for dspinbox_type in dspinbox_type_list]
            self._mw.runtime_DoubleSpinBox.setEnabled(True)
            self._sd.clock_frequency_DoubleSpinBox.setEnabled(True)
            self._mw.action_run_stop.setChecked(False)
            self._mw.action_resume_odmr.setChecked(False)

        # Unblock signal firing
        self._mw.action_run_stop.blockSignals(False)
        self._mw.action_resume_odmr.blockSignals(False)
        return


    def update_plots(self, odmr_data_x, odmr_data_y):
        """ Refresh the plot widgets with new data. """
        # Update mean signal plot
        self.odmr_image.setData(odmr_data_x, odmr_data_y)

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
        clock_frequency = self._sd.clock_frequency_DoubleSpinBox.value()
        self.sigClockFreqChanged.emit(clock_frequency)

        contrast = self._sd.esr_contrast_SpinBox.value()
        offset = self._sd.esr_offset_SpinBox.value()
        amp_noise = self._sd.esr_noise_SpinBox.value() 
        esr_fwhm = self._sd.esr_fwhm_SpinBox.value()
        err_margin_x0 = self._sd.esr_errorMarginCenter_SpinBox.value()
        err_margin_offset = self._sd.esr_errorMarginOffset_SpinBox.value()
        err_margin_contrast = self._sd.esr_errorMarginContrast_SpinBox.value()
        n_samples = self._sd.esr_nSamples_SpinBox.value()
        param_estimation = {'params': (-(offset*contrast/100),offset,amp_noise,esr_fwhm,err_margin_x0,err_margin_offset,-(offset*err_margin_contrast/100), n_samples)}
        self.sigOptBaySettingsChanged.emit(param_estimation)
        return

    def reject_settings(self):
        """ Keep the old settings and restores the old settings in the gui. """
        self._sd.clock_frequency_DoubleSpinBox.setValue(self._odmr_logic.clock_frequency)
        return

    def do_fit(self):
        fit_function = self._mw.fit_methods_ComboBox.getCurrentFit()[0]
        self.sigDoFit.emit(fit_function, None, None, 0, 0)
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

    def update_parameter(self, param_dict):
        """ Update the parameter display in the GUI.

        @param param_dict:
        @return:

        Any change event from the logic should call this update function.
        The update will block the GUI signals from emitting a change back to the
        logic.
        """
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

        param = param_dict.get('run_time')
        if param is not None:
            self._mw.runtime_DoubleSpinBox.blockSignals(True)
            self._mw.runtime_DoubleSpinBox.setValue(param)
            self._mw.runtime_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('clock_frequency')
        if param is not None:
            self._sd.clock_frequency_DoubleSpinBox.blockSignals(True)
            self._sd.clock_frequency_DoubleSpinBox.setValue(param)
            self._sd.clock_frequency_DoubleSpinBox.blockSignals(False)


        param = param_dict.get('cw_mw_power')
        if param is not None:
            self._mw.cw_power_DoubleSpinBox.blockSignals(True)
            self._mw.cw_power_DoubleSpinBox.setValue(param)
            self._mw.cw_power_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('average_length')
        if param is not None:
            self._mw.average_level_SpinBox.blockSignals(True)
            self._mw.average_level_SpinBox.setValue(param)
            self._mw.average_level_SpinBox.blockSignals(False)
        return

    ############################################################################
    #                           Change Methods                                 #
    ############################################################################

    def change_cw_params(self):
        """ Change CW frequency and power of microwave source """
        frequency = 1e9
        power = self._mw.cw_power_DoubleSpinBox.value()
        self.sigMwCwParamsChanged.emit(frequency, power)
        return

    def change_sweep_params(self):
        """ Change start, stop and step frequency of frequency sweep """
        starts = []
        steps = []
        stops = []

        # construct strings
        start = self._mw.start_freq_DoubleSpinBox_0.value()
        step = self._mw.step_freq_DoubleSpinBox_0.value()
        stop = self._mw.stop_freq_DoubleSpinBox_0.value()

        starts.append(start)
        steps.append(step)
        stops.append(stop)

        power = self._mw.cw_power_DoubleSpinBox.value()
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

    def change_runtime(self):
        """ Change time after which microwave sweep is stopped """
        runtime = self._mw.runtime_DoubleSpinBox.value()
        self.sigRuntimeChanged.emit(runtime)
        return

    def save_data(self):
        """ Save the sum plot, the scan marix plot and the scan data """
        filetag = self._mw.save_tag_LineEdit.text()

        # Percentile range is None, unless the percentile scaling is selected in GUI.
      
        self.sigSaveMeasurement.emit(filetag)
        return
