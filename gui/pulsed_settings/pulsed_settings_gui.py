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


class PulsedSettingsMainWindow(QtWidgets.QMainWindow):
    """ The main window for the ODMR measurement GUI.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'pulsed_settings.ui')

        # Load it
        super(PulsedSettingsMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()

class PulsedSettingsGui(GUIBase):
    """
    This is the GUI Class for ODMR measurements
    """

    # declare connectors
    pulsedsettingslogic = Connector(interface='PulsedSettingsLogic')

    waveform_folder = ConfigOption(name="waveform_folder",
                                   default=os.path.join(get_home_dir(), 'saved_pulsed_assets', 'waveform'),
                                   missing="warn")
    sequence_folder = ConfigOption(name="sequence_folder",
                                   default=os.path.join(get_home_dir(), 'saved_pulsed_assets', 'sequence'),
                                   missing="warn")

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition, configuration and initialisation of the ODMR GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        """

        self._pulsed_settings_logic = self.pulsedsettingslogic()

        # Use the inherited class 'Ui_ODMRGuiUI' to create now the GUI element:
        self._mw = PulsedSettingsMainWindow()
        self.restoreWindowPos(self._mw)

        self._mw.AWG_sync_time_DSpinBox.setValue(self._pulsed_settings_logic.awg_sync_time)
        self._mw.laser_waiting_time_DSpinBox.setValue(self._pulsed_settings_logic.laser_waiting_time)
        self._mw.MW_waiting_time_DSpinBox.setValue(self._pulsed_settings_logic.mw_waiting_time)
        self._mw.read_out_time_DSpinBox.setValue(self._pulsed_settings_logic.read_out_time)
        self._mw.add_tt_read_out_DSpinBox.setValue(self._pulsed_settings_logic.add_tt_read_out)
        self._mw.bin_width_DSpinBox.setValue(self._pulsed_settings_logic.bin_width)

        self._mw.AWG_sync_time_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.laser_waiting_time_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.MW_waiting_time_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.read_out_time_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.add_tt_read_out_DSpinBox.editingFinished.connect(self.settings_changed)
        self._mw.bin_width_DSpinBox.editingFinished.connect(self.settings_changed)

        self._mw.action_restore_default_values.triggered.connect(self.restore_default)
        self._mw.action_delete_all_pulsed_assets.triggered.connect(self.delete_pulsed_assets)

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        
        self._mw.AWG_sync_time_DSpinBox.editingFinished.disconnect()
        self._mw.laser_waiting_time_DSpinBox.editingFinished.disconnect()
        self._mw.MW_waiting_time_DSpinBox.editingFinished.disconnect()
        self._mw.read_out_time_DSpinBox.editingFinished.disconnect()
        self._mw.add_tt_read_out_DSpinBox.editingFinished.disconnect()
        self._mw.bin_width_DSpinBox.editingFinished.disconnect()

        self._mw.action_restore_default_values.triggered.disconnect()
        self._mw.action_delete_all_pulsed_assets.triggered.disconnect()

        self.saveWindowGeometry(self._mw)
        self._mw.close()
        return 0

    def settings_changed(self):
        self._pulsed_settings_logic.awg_sync_time = self._mw.AWG_sync_time_DSpinBox.value()
        self._pulsed_settings_logic.laser_waiting_time = self._mw.laser_waiting_time_DSpinBox.value()
        self._pulsed_settings_logic.mw_waiting_time = self._mw.MW_waiting_time_DSpinBox.value()
        self._pulsed_settings_logic.read_out_time = self._mw.read_out_time_DSpinBox.value()
        self._pulsed_settings_logic.add_tt_read_out = self._mw.add_tt_read_out_DSpinBox.value()
        self._pulsed_settings_logic.bin_width = self._mw.bin_width_DSpinBox.value()

    def restore_default(self):
        self._mw.AWG_sync_time_DSpinBox.setValue(self._pulsed_settings_logic.awg_sync_time_default)
        self._mw.laser_waiting_time_DSpinBox.setValue(self._pulsed_settings_logic.laser_waiting_time_default)
        self._mw.MW_waiting_time_DSpinBox.setValue(self._pulsed_settings_logic.mw_waiting_time_default)
        self._mw.read_out_time_DSpinBox.setValue(self._pulsed_settings_logic.read_out_time_default)
        self._mw.add_tt_read_out_DSpinBox.setValue(self._pulsed_settings_logic.add_tt_read_out_default)
        self._mw.bin_width_DSpinBox.setValue(self._pulsed_settings_logic.bin_width_default)

    def delete_pulsed_assets(self):
        for f in os.listdir(self.waveform_folder):
            if f.endswith(".pkl"):
                os.remove(os.path.join(self.waveform_folder, f))

        for f in os.listdir(self.sequence_folder):
            if f.endswith(".block") or f.endswith(".ensemble"):
                os.remove(os.path.join(self.sequence_folder, f))

        self._pulsed_settings_logic.pulsed_assets_deleted = True