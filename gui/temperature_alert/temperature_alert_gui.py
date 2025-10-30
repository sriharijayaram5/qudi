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

from core.configoption import ConfigOption
from core.util.modules import get_home_dir
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


class TemperatureAlertMainWindow(QtWidgets.QMainWindow):
    """ The main window for the ODMR measurement GUI.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'temperature_alert.ui')

        # Load it
        super(TemperatureAlertMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()

class TemperatureAlertGui(GUIBase):
    """
    This is the GUI Class for ODMR measurements
    """

    # declare connectors
    temperaturealertlogic = Connector(interface='TemperatureAlertLogic')

    sigStart = QtCore.Signal()
    sigStop = QtCore.Signal()
    sigStopSampleSetpointChanged = QtCore.Signal()
    sigStopVTISetpointChanged = QtCore.Signal()
    sigCheckPeriodChanged = QtCore.Signal(float)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Control over temperature alert settings.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        """

        self._temperature_alert_logic = self.temperaturealertlogic()

        # Use the inherited class 'Ui_ODMRGuiUI' to create now the GUI element:
        self._mw = TemperatureAlertMainWindow()
        self.restoreWindowPos(self._mw)

        self._mw.temp_cntrl_diff_DSpinBox.setValue(self._temperature_alert_logic.temp_cntrl_diff)
        self._mw.T_setpoint_waiting_time_DSpinBox.setValue(self._temperature_alert_logic.T_setpoint_waiting_time)
        self._mw.compressor_failure_temp_treshhold_DSpinBox.setValue(self._temperature_alert_logic.compressor_failure_temp_treshhold)
        self._mw.check_period_DSpinBox.setValue(self._temperature_alert_logic.check_period)
        
        self._mw.temp_cntrl_diff_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.T_setpoint_waiting_time_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.compressor_failure_temp_treshhold_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.check_period_DSpinBox.editingFinished.connect(self.check_period_changed)

        self._mw.sample_temp_ctrl_warning_checkBox.clicked.connect(self.sample_temp_cntrl_warning_clicked)
        self._mw.vti_temp_ctrl_warning_checkBox.clicked.connect(self.vti_temp_cntrl_warning_clicked)
        self._mw.compressor_failure_warning_checkBox.clicked.connect(self.compressor_failure_warning_clicked)

        self._mw.chose_log_file_pushButton.clicked.connect(self.chose_log_file_clicked)

        self._temperature_alert_logic.sigSampleTempSensorDisconnected.connect(self.sample_temp_sensor_disconnected)
        self._temperature_alert_logic.sigVTITempSensorDisconnected.connect(self.vti_temp_sensor_disconnected)
        self._temperature_alert_logic.sigReservoirTempSensorDisconnected.connect(self.reservoir_temp_sensor_disconnected)

        self._temperature_alert_logic.sigDeactivateAllWarning.connect(self.deactivate_all_warning)
        self._temperature_alert_logic.sigActivateSampleWarning.connect(self.activte_sample_warning)
        self._temperature_alert_logic.sigActivateVTIWarning.connect(self.activte_vti_warning)
        self._temperature_alert_logic.sigActivateCompressorWarning.connect(self.activte_compressor_warning)

        self.sigStart.connect(self._temperature_alert_logic.startLoop)
        self.sigStop.connect(self._temperature_alert_logic.stopLoop)
        self.sigStopSampleSetpointChanged.connect(self._temperature_alert_logic.stopLoopSampleSetpointChanged)
        self.sigStopVTISetpointChanged.connect(self._temperature_alert_logic.stopLoopVTISetpointChanged)
        self.sigCheckPeriodChanged.connect(self._temperature_alert_logic.check_period_changed)

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        
        self._mw.temp_cntrl_diff_DSpinBox.editingFinished.disconnect()
        self._mw.T_setpoint_waiting_time_DSpinBox.editingFinished.disconnect()
        self._mw.compressor_failure_temp_treshhold_DSpinBox.editingFinished.disconnect()
        self._mw.check_period_DSpinBox.editingFinished.disconnect()

        self._mw.sample_temp_ctrl_warning_checkBox.clicked.disconnect()
        self._mw.vti_temp_ctrl_warning_checkBox.clicked.disconnect()
        self._mw.compressor_failure_warning_checkBox.clicked.disconnect()

        self._mw.chose_log_file_pushButton.clicked.disconnect()

        self._temperature_alert_logic.sigSampleTempSensorDisconnected.disconnect()
        self._temperature_alert_logic.sigVTITempSensorDisconnected.disconnect()
        self._temperature_alert_logic.sigReservoirTempSensorDisconnected.disconnect()

        self._temperature_alert_logic.sigDeactivateAllWarning.disconnect()
        self._temperature_alert_logic.sigActivateSampleWarning.disconnect()
        self._temperature_alert_logic.sigActivateVTIWarning.disconnect()
        self._temperature_alert_logic.sigActivateCompressorWarning.disconnect()

        self.saveWindowGeometry(self._mw)
        self._mw.close()
        return 0
    
    def show(self):
        """Make window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def settings_changed(self):
        self._temperature_alert_logic.temp_cntrl_diff = self._mw.temp_cntrl_diff_DSpinBox.value()
        self._temperature_alert_logic.T_setpoint_waiting_time = self._mw.T_setpoint_waiting_time_DSpinBox.value()
        self._temperature_alert_logic.compressor_failure_temp_treshhold = self._mw.compressor_failure_temp_treshhold_DSpinBox.value()

    def check_period_changed(self):
        check_period = self._mw.check_period_DSpinBox.value()
        self.sigCheckPeriodChanged.emit(check_period)

    def sample_temp_cntrl_warning_clicked(self, state):
        self._temperature_alert_logic.sample_temp_cntrl_warning = state
        if not self._temperature_alert_logic.enabled and self._temperature_alert_logic.sample_temp_cntrl_warning:
            self._temperature_alert_logic.old_sample_temp_setpoint = self._temperature_alert_logic._controller.get_sample_temp_setpoint()
            self.sigStart.emit()
        if self._temperature_alert_logic.enabled and not self._temperature_alert_logic.sample_temp_cntrl_warning and not self._temperature_alert_logic.compressor_failure_warning and not self._temperature_alert_logic.vti_temp_cntrl_warning:
            self.sigStop.emit()
        if not state:
            self.sigStopSampleSetpointChanged.emit()

    def vti_temp_cntrl_warning_clicked(self, state):
        self._temperature_alert_logic.vti_temp_cntrl_warning = state
        if not self._temperature_alert_logic.enabled and self._temperature_alert_logic.vti_temp_cntrl_warning:
            self._temperature_alert_logic.old_vti_temp_setpoint = self._temperature_alert_logic._controller.get_vti_temp_setpoint()
            self.sigStart.emit()
        if self._temperature_alert_logic.enabled and not self._temperature_alert_logic.sample_temp_cntrl_warning and not self._temperature_alert_logic.compressor_failure_warning and not self._temperature_alert_logic.vti_temp_cntrl_warning:
            self.sigStop.emit()
        if not state:
            self.sigStopVTISetpointChanged.emit()

    def compressor_failure_warning_clicked(self, state):
        self._temperature_alert_logic.compressor_failure_warning = state
        if not self._temperature_alert_logic.enabled and self._temperature_alert_logic.compressor_failure_warning:
            self.sigStart.emit()
        if self._temperature_alert_logic.enabled and not self._temperature_alert_logic.sample_temp_cntrl_warning and not self._temperature_alert_logic.compressor_failure_warning and not self._temperature_alert_logic.vti_temp_cntrl_warning:
            self.sigStop.emit()

    def sample_temp_sensor_disconnected(self):
        self._mw.sample_temp_ctrl_warning_checkBox.setChecked(False)
        self.sample_temp_cntrl_warning_clicked(False)

    def vti_temp_sensor_disconnected(self):
        self._mw.vti_temp_ctrl_warning_checkBox.setChecked(False)
        self.vti_temp_cntrl_warning_clicked(False)

    def reservoir_temp_sensor_disconnected(self):
        self._mw.compressor_failure_warning_checkBox.setChecked(False)
        self.compressor_failure_warning_clicked(False)

    def deactivate_all_warning(self):
        self._mw.sample_temp_ctrl_warning_checkBox.setChecked(False)
        self.sample_temp_cntrl_warning_clicked(False)
        self._mw.vti_temp_ctrl_warning_checkBox.setChecked(False)
        self.vti_temp_cntrl_warning_clicked(False)
        self._mw.compressor_failure_warning_checkBox.setChecked(False)
        self.compressor_failure_warning_clicked(False)

    def activte_sample_warning(self):
        self._mw.sample_temp_ctrl_warning_checkBox.setChecked(True)
        self.sample_temp_cntrl_warning_clicked(True)

    def activte_vti_warning(self):
        self._mw.vti_temp_ctrl_warning_checkBox.setChecked(True)
        self.vti_temp_cntrl_warning_clicked(True)

    def activte_compressor_warning(self):
        self._mw.compressor_failure_warning_checkBox.setChecked(True)
        self.compressor_failure_warning_clicked(True)

    def chose_log_file_clicked(self):
        filepath = 'G:\\Data\\Cryostat logs'
        file_name = QtWidgets.QFileDialog.getOpenFileName(
            self._mw,
            'Chose or create temperature log file',
            filepath,
            'DAT Files (*.dat);;All Files (*)')[0]
        if file_name:
            if not file_name.endswith(".dat"):
                file_name += ".dat"
            file_existed = os.path.exists(file_name)
            
            try:
                with open(file_name, "a"):
                    if not file_existed:
                        pass
            except Exception as e:
                self.log.error(f"Failed to open or create file:\n{e}")
                self._temperature_alert_logic.temperature_log_file_name = None
                self._mw.chosen_log_file_label.setText('None')
                return 
            
            self._temperature_alert_logic.temperature_log_file_name = file_name
            self._mw.chosen_log_file_label.setText(file_name)
            return