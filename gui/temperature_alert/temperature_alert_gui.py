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
    sigStopSetpointChanged = QtCore.Signal()
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

        self._mw.temp_ctrl_warning_checkBox.clicked.connect(self.temp_cntrl_warning_clicked)
        self._mw.compressor_failure_warning_checkBox.clicked.connect(self.compressor_failure_warning_clicked)

        self._temperature_alert_logic.sigSampleTempSensorDisconnected.connect(self.sample_temp_sensor_disconnected)
        self._temperature_alert_logic.sigReservoirTempSensorDisconnected.connect(self.reservoir_temp_sensor_disconnected)
        self.sigStart.connect(self._temperature_alert_logic.startLoop)
        self.sigStop.connect(self._temperature_alert_logic.stopLoop)
        self.sigStopSetpointChanged.connect(self._temperature_alert_logic.stopLoopSetpointChanged)
        self.sigCheckPeriodChanged.connect(self._temperature_alert_logic.check_period_changed)

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        
        self._mw.temp_cntrl_diff_DSpinBox.editingFinished.disconnect()
        self._mw.T_setpoint_waiting_time_DSpinBox.editingFinished.disconnect()
        self._mw.compressor_failure_temp_treshhold_DSpinBox.editingFinished.disconnect()
        self._mw.check_period_DSpinBox.editingFinished.disconnect()

        self._mw.temp_ctrl_warning_checkBox.clicked.disconnect()
        self._mw.compressor_failure_warning_checkBox.clicked.disconnect()

        self._temperature_alert_logic.sigSampleTempSensorDisconnected.disconnect()
        self._temperature_alert_logic.sigReservoirTempSensorDisconnected.disconnect()

        self.saveWindowGeometry(self._mw)
        self._mw.close()
        return 0

    def settings_changed(self):
        self._temperature_alert_logic.temp_cntrl_diff = self._mw.temp_cntrl_diff_DSpinBox.value()
        self._temperature_alert_logic.T_setpoint_waiting_time = self._mw.T_setpoint_waiting_time_DSpinBox.value()
        self._temperature_alert_logic.compressor_failure_temp_treshhold = self._mw.compressor_failure_temp_treshhold_DSpinBox.value()

    def check_period_changed(self):
        check_period = self._mw.check_period_DSpinBox.value()
        self.sigCheckPeriodChanged.emit(check_period)

    def temp_cntrl_warning_clicked(self, state):
        self._temperature_alert_logic.temp_cntrl_warning = state
        if not self._temperature_alert_logic.enabled and self._temperature_alert_logic.temp_cntrl_warning:
            self.old_sample_temp_setpoint = self._temperature_alert_logic._controller.get_sample_temp_setpoint()
            self.sigStart.emit()
        if self._temperature_alert_logic.enabled and not self._temperature_alert_logic.temp_cntrl_warning and not self._temperature_alert_logic.compressor_failure_warning:
            self.sigStop.emit()
        if not state:
            self.sigStopSetpointChanged.emit()

    def compressor_failure_warning_clicked(self, state):
        self._temperature_alert_logic.compressor_failure_warning = state
        if not self._temperature_alert_logic.enabled and self._temperature_alert_logic.compressor_failure_warning:
            self.sigStart.emit()
        if self._temperature_alert_logic.enabled and not self._temperature_alert_logic.temp_cntrl_warning and not self._temperature_alert_logic.compressor_failure_warning:
            self.sigStop.emit()

    def sample_temp_sensor_disconnected(self):
        self._mw.temp_ctrl_warning_checkBox.setChecked(False)
        self.temp_cntrl_warning_clicked(False)

    def reservoir_temp_sensor_disconnected(self):
        self._mw.compressor_failure_warning_checkBox.setChecked(False)
        self.compressor_failure_warning_clicked(False)