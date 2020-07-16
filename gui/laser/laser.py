# -*- coding: utf-8 -*-

"""
This file contains a gui for the laser controller logic.

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
import time

from core.module import Connector
from core.util import units
from gui.colordefs import QudiPalettePale as palette
from gui.guiutils import ColorBar
from gui.colordefs import ColorScaleViridis
from gui.guibase import GUIBase
from interface.simple_laser_interface import ControlMode, ShutterState, LaserState
from qtpy import QtCore
from qtpy import QtWidgets
from qtpy import uic

class LaserWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. 
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_laser.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class LaserGUI(GUIBase):
    """ FIXME: Please document
    """
    _modclass = 'lasergui'
    _modtype = 'gui'

    ## declare connectors
    laserlogic = Connector(interface='LaserLogic')
    counter_logic = Connector(interface='CounterLogic')

    sigPower = QtCore.Signal(float)
    sigCurrent = QtCore.Signal(float)
    sigCtrlMode = QtCore.Signal(ControlMode)
    sigStartSaturation = QtCore.Signal()
    sigStopSaturation = QtCore.Signal()
    sigSaveMeasurement = QtCore.Signal(str)
    sigStartOOPMeasurement = QtCore.Signal()
    sigStopOOPMeasurement = QtCore.Signal()
    sigOOPLaserParamsChanged = QtCore.Signal(float, float, int)
    sigOOPMwParamsChanged = QtCore.Signal(float, float, int)
    sigOOPFreqParamsChanged = QtCore.Signal(float, float, int)
    sigOOPRuntimeParamsChanged = QtCore.Signal(float, float)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition and initialisation of the GUI plus staring the measurement.
        """
        self._laser_logic = self.laserlogic()
        self._counterlogic = self.counter_logic()

        #####################
        # Configuring the dock widgets
        # Use the inherited class 'LaserWindow' to create the GUI window
        # Hiding the central widget for comfort. 
        self._mw = LaserWindow()
        self._mw.centralwidget.hide()
        self._mw.tabifyDockWidget(self._mw.saturation_fit_DockWidget, self._mw.OOP_DockWidget)

        # Create a QSettings object for the mainwindow and store the actual GUI layout
        self.mwsettings = QtCore.QSettings("QUDI", "Saturation")
        self.mwsettings.setValue("geometry", self._mw.saveGeometry())
        self.mwsettings.setValue("windowState", self._mw.saveState())

        # Plot labels.
        self._pw = self._mw.saturation_Curve_PlotWidget
        self._pw.setLabel('left', 'Fluorescence', units='counts/s')
        self._pw.setLabel('bottom', 'Laser Power', units='W')

        self._matrix_pw = self._mw.matrix_PlotWidget
        self._matrix_pw.setLabel(axis='left', text='Laser power', units='W')
        self._matrix_pw.setLabel(axis='bottom', text='MW power', units='dBm')

        #Setting up the curves.
        self.saturation_curve = pg.PlotDataItem(pen=pg.mkPen(palette.c1, style=QtCore.Qt.DotLine), 
                                                  symbol='o', symbolPen=palette.c1,
                                                  symbolBrush=palette.c1,
                                                  symbolSize=7 )
        self.errorbar = pg.ErrorBarItem(x=np.array([0]), y =np.array([0]), pen=pg.mkPen(palette.c6, style=QtCore.Qt.SolidLine), beam=1)
        self.saturation_fit_image = pg.PlotDataItem(pen=pg.mkPen(palette.c2), symbol=None)  
        self.matrix_image = pg.ImageItem()
        # self.matrix_image = pg.ImageItem(self._laser_logic._odmr_data['fit_contrast'], 
        #                                  axisOrder='row-major')
        # self.matrix_image.setRect(QtCore.QRectF())                     
        
        self._pw.addItem(self.saturation_curve)
        self._pw.addItem(self.errorbar)
        self._matrix_pw.addItem(self.matrix_image)

        # Get the colorscales at set LUT
        my_colors = ColorScaleViridis()
        self.matrix_image.setLookupTable(my_colors.lut)

        ########################################################################
        #                  Configuration of the Colorbar                       #
        ########################################################################
        self.oop_cb = ColorBar(my_colors.cmap_normed, 100, 0, 100)

        # adding colorbar to ViewWidget
        self._mw.oop_cb_PlotWidget.addItem(self.oop_cb)
        self._mw.oop_cb_PlotWidget.hideAxis('bottom')
        self._mw.oop_cb_PlotWidget.hideAxis('left')
        self._mw.oop_cb_PlotWidget.setLabel('right')
        #Setting up the constraints for the Saturation Curve.
        lpr = self._laser_logic.laser_power_range
        self._mw.startPowerDoubleSpinBox.setRange(lpr[0], lpr[1])
        self._mw.startPowerDoubleSpinBox.setValue(self._laser_logic.power_start)
        self._mw.stopPowerDoubleSpinBox.setRange(lpr[0], lpr[1])
        self._mw.stopPowerDoubleSpinBox.setValue(self._laser_logic.power_stop)
        self._mw.numPointsSpinBox.setRange(1,100)
        self._mw.numPointsSpinBox.setValue(self._laser_logic.number_of_points)
        self._mw.timeDoubleSpinBox.setRange(1,1000)
        self._mw.timeDoubleSpinBox.setValue(self._laser_logic.time_per_point)

        odmr_constraints = self._laser_logic.get_odmr_constraints()
        self._mw.laser_power_start_DoubleSpinBox.setRange(lpr[0], lpr[1])
        self._mw.laser_power_start_DoubleSpinBox.setValue(self._laser_logic.laser_power_start)
        self._mw.laser_power_stop_DoubleSpinBox.setRange(lpr[0], lpr[1])
        self._mw.laser_power_stop_DoubleSpinBox.setValue(self._laser_logic.laser_power_stop)
        self._mw.laser_power_num_SpinBox.setValue(self._laser_logic.laser_power_num)
        self._mw.mw_power_start_DoubleSpinBox.setRange(odmr_constraints.min_power, odmr_constraints.max_power)
        self._mw.mw_power_start_DoubleSpinBox.setValue(self._laser_logic.mw_power_start)
        self._mw.mw_power_stop_DoubleSpinBox.setRange(odmr_constraints.min_power, odmr_constraints.max_power)
        self._mw.mw_power_stop_DoubleSpinBox.setValue(self._laser_logic.mw_power_stop)
        self._mw.mw_power_num_SpinBox.setValue(self._laser_logic.mw_power_num)
        self._mw.freq_start_DoubleSpinBox.setRange(odmr_constraints.min_frequency, odmr_constraints.max_frequency)
        self._mw.freq_start_DoubleSpinBox.setValue(self._laser_logic.freq_start)
        self._mw.freq_stop_DoubleSpinBox.setRange(odmr_constraints.min_frequency, odmr_constraints.max_frequency)
        self._mw.freq_stop_DoubleSpinBox.setValue(self._laser_logic.freq_stop)
        self._mw.freq_num_SpinBox.setRange(1, 1000)
        self._mw.freq_num_SpinBox.setValue(self._laser_logic.freq_num)
        self._mw.counter_runtime_DoubleSpinBox.setRange(1, 1000)
        self._mw.counter_runtime_DoubleSpinBox.setValue(self._laser_logic.counter_runtime)
        self._mw.odmr_runtime_DoubleSpinBox.setRange(1, 1000)
        self._mw.odmr_runtime_DoubleSpinBox.setValue(self._laser_logic.odmr_runtime)
        self._mw.channel_SpinBox.setValue(self._laser_logic.channel)
        self._mw.optimize_CheckBox.setChecked(self._laser_logic.optimize)
        for fit in self._laser_logic.get_odmr_fits():
            self._mw.fit_ComboBox.addItem(fit)
        self._mw.fit_ComboBox.setCurrentText(self._laser_logic.odmr_fit_function)
        self._mw.nametag_LineEdit.setText(self._laser_logic.OOP_nametag)

        self.updateButtonsEnabled()
        
        ########################################################################
        #                       Connect signals                                #
        ########################################################################

        # Internal user input changed signals
        self._mw.laser_power_start_DoubleSpinBox.editingFinished.connect(self.change_laser_params)
        self._mw.laser_power_stop_DoubleSpinBox.editingFinished.connect(self.change_laser_params)
        self._mw.laser_power_num_SpinBox.editingFinished.connect(self.change_laser_params)
        self._mw.mw_power_start_DoubleSpinBox.editingFinished.connect(self.change_mw_params)
        self._mw.mw_power_stop_DoubleSpinBox.editingFinished.connect(self.change_mw_params)
        self._mw.mw_power_num_SpinBox.editingFinished.connect(self.change_mw_params)
        self._mw.freq_start_DoubleSpinBox.editingFinished.connect(self.change_freq_params) 
        self._mw.freq_stop_DoubleSpinBox.editingFinished.connect(self.change_freq_params)
        self._mw.freq_num_SpinBox.editingFinished.connect(self.change_freq_params)
        self._mw.counter_runtime_DoubleSpinBox.editingFinished.connect(self.change_runtime_params)
        self._mw.odmr_runtime_DoubleSpinBox.editingFinished.connect(self.change_runtime_params)
        self._mw.channel_SpinBox.valueChanged.connect(self._laser_logic.set_OOP_channel)
        self._mw.optimize_CheckBox.stateChanged.connect(self._laser_logic.set_OOP_optimize)
        self._mw.fit_ComboBox.currentTextChanged.connect(self._laser_logic.set_odmr_fit)
        self._mw.data_ComboBox.currentTextChanged.connect(self.OOP_update_data)
        self._mw.nametag_LineEdit.textChanged.connect(self._laser_logic.set_OOP_nametag)
        
        # Internal trigger signals
        self._mw.start_saturation_Action.triggered.connect(self.run_stop_saturation)
        self._mw.start_saturation_Action.triggered.connect(self.update_settings)
        self._mw.save_curve_Action.triggered.connect(self.save_saturation_curve_clicked)
        self._mw.action_Save.triggered.connect(self.save_saturation_curve_clicked)
        self._mw.action_RestoreDefault.triggered.connect(self.restore_defaultview)
        self._mw.laser_ON_Action.triggered.connect(self.LaserStateON)
        self._mw.laser_OFF_Action.triggered.connect(self.LaserStateOFF)
        self._mw.controlModeButtonGroup.buttonClicked.connect(self.changeControlMode)
        #self._mw.LaserButtonON.clicked.connect(self.LaserStateON)
        #self._mw.LaserButtonOFF.clicked.connect(self.LaserStateOFF)
        self._mw.dofit_Button.clicked.connect(self.dofit_button_clicked)
        self._mw.run_stop_measurement_Action.triggered.connect(self.run_stop_OOP_measurement)

        # Control/values-changed signals to logic
        self.sigSaveMeasurement.connect(self._laser_logic.save_saturation_data, QtCore.Qt.QueuedConnection)
        self.sigCurrent.connect(self._laser_logic.set_current)
        self.sigPower.connect(self._laser_logic.set_power)
        self.sigCtrlMode.connect(self._laser_logic.set_control_mode)
        self.sigStartSaturation.connect(self.start_saturation_curve_clicked)
        self.sigStopSaturation.connect(self._laser_logic.stop_saturation_curve_data)
        self.sigStartOOPMeasurement.connect(self._laser_logic.start_OOP_measurement, QtCore.Qt.QueuedConnection)
        self.sigStopOOPMeasurement.connect(self._laser_logic.stop_OOP_measurement, QtCore.Qt.QueuedConnection)
        self.sigOOPLaserParamsChanged.connect(self._laser_logic.set_OOP_laser_params)
        self.sigOOPMwParamsChanged.connect(self._laser_logic.set_OOP_mw_params)
        self.sigOOPFreqParamsChanged.connect(self._laser_logic.set_OOP_freq_params)
        self.sigOOPRuntimeParamsChanged.connect(self._laser_logic.set_OOP_runtime_params)
        # Update signals coming from logic:
        self._laser_logic.sigSaturationFitUpdated.connect(self.update_fit, QtCore.Qt.QueuedConnection)
        self._laser_logic.sigRefresh.connect(self.refreshGui)
        self._laser_logic.sigUpdateButton.connect(self.updateButtonsEnabled)
        self._laser_logic.sigAbortedMeasurement.connect(self.aborted_saturation_measurement)
        self._laser_logic.sigOOPStarted.connect(self.OOP_started)
        self._laser_logic.sigOOPStopped.connect(self.OOP_stopped)
        self._laser_logic.sigOOPUpdateData.connect(self.OOP_update_data)
        self._laser_logic.sigParameterUpdated.connect(self.update_parameters)
        self._laser_logic.sigDataAvailableUpdated.connect(self.fill_combobox)

        # Internal user input changed signals
        self._mw.LaserdoubleSpinBox.editingFinished.connect(self.updatePowerFromSpinBox)

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        # Disconnect signals
        #self.sigStartSaturation.disconnect()
        #self.sigStopSaturation.disconnect()
        self._laser_logic.sigSaturationFitUpdated.disconnect()
        self._mw.action_Save.triggered.disconnect()
        self._mw.action_RestoreDefault.triggered.disconnect()
        self._mw.close()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def LaserStateON(self):
        """ Disable laser power ON button.
            Button will remain Disabled until laser power OFF button is clicked.
        """
        
        self._mw.laser_ON_Action.setEnabled(False)
        self._mw.laser_ON_Action.setChecked(False)
        #self._mw.LaserButtonON.setEnabled(False)
        self._laser_logic.on()
        self._mw.laser_OFF_Action.setEnabled(True)
        #self._mw.LaserButtonOFF.setEnabled(True)

        #self.sigLaserOn.emit(on)

    def LaserStateOFF(self):
        """ Disable laser power OFF button.
            Button will remain Disabled until laser power ON button is clicked.
        """
        self._mw.laser_OFF_Action.setEnabled(False)
        self._mw.laser_OFF_Action.setChecked(False)
        #self._mw.LaserButtonOFF.setEnabled(False)
        self._laser_logic.off()
        self._mw.laser_ON_Action.setEnabled(True)
        #self._mw.LaserButtonON.setEnabled(True)

        #self.sigLaserOn.emit(on)

    @QtCore.Slot(QtWidgets.QAbstractButton)
    def changeControlMode(self, buttonId):
        """ Process signal from laser control mode radio button group. 
        """
        cur = self._mw.currentRadioButton.isChecked() and self._mw.currentRadioButton.isEnabled()
        pwr = self._mw.powerRadioButton.isChecked() and self._mw.powerRadioButton.isEnabled()
        dig_mod = self._mw.digModulationRadioButton.isChecked() and self._mw.digModulationRadioButton.isEnabled()
        analog_mod = self._mw.analogModulationRadioButton.isChecked() and self._mw.analogModulationRadioButton.isEnabled()

        if pwr:
            lpr = self._laser_logic.laser_power_range
            self._mw.LaserdoubleSpinBox.setRange(lpr[0], lpr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_power_setpoint)
            self._mw.LaserdoubleSpinBox.setSuffix('W')
            #self._mw.setValueVerticalSlider.setValue(
            #    self._laser_logic.laser_power_setpoint / (lpr[1] - lpr[0]) * 100 - lpr[0])
            self.sigCtrlMode.emit(ControlMode.POWER)
        elif cur:
            lcr = self._laser_logic.laser_current_range
            self._mw.LaserdoubleSpinBox.setRange(lcr[0], lcr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_current_setpoint)
            self._mw.LaserdoubleSpinBox.setSuffix('mA')
            #self._mw.setValueVerticalSlider.setValue(
            #    self._laser_logic.laser_current_setpoint / (lcr[1] - lcr[0]) * 100 - lcr[0])
            self.sigCtrlMode.emit(ControlMode.CURRENT)
        elif dig_mod:
            lpr = self._laser_logic.laser_power_range
            self._mw.LaserdoubleSpinBox.setRange(lpr[0], lpr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_power_setpoint)
            self._mw.LaserdoubleSpinBox.setSuffix('W')
            self.sigCtrlMode.emit(ControlMode.MODULATION_DIGITAL)
        elif analog_mod:
            lpr = self._laser_logic.laser_power_range
            self._mw.LaserdoubleSpinBox.setRange(lpr[0], lpr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_power_setpoint)
            self._mw.LaserdoubleSpinBox.setSuffix('W')
            self.sigCtrlMode.emit(ControlMode.MODULATION_ANALOG)
        else:
            self.log.error('How did you mess up the radio button group?')

    ###########################################################################
    #                      Saturation curve methods                           #
    ###########################################################################

    @QtCore.Slot()
    def updateButtonsEnabled(self):
        """ Setting up the buttons accordingly. 
        """

        #Checking if the laser is on or off. 
        if self._laser_logic.get_laser_state() == LaserState.ON:
            self._mw.laser_ON_Action.setEnabled(False)
            #self._mw.LaserButtonON.setEnabled(False)
            self._mw.laser_OFF_Action.setEnabled(True)
            #self._mw.LaserButtonOFF.setEnabled(True)
        elif self._laser_logic.get_laser_state() == LaserState.OFF:
            self._mw.laser_OFF_Action.setEnabled(False)
            #self._mw.LaserButtonOFF.setEnabled(False)
            self._mw.laser_ON_Action.setEnabled(True)
            #self._mw.LaserButtonON.setEnabled(True)
        else:
            self._mw.laser_ON_Action.setText('Laser: ?')
            #self._mw.LaserButtonON.setText('Laser: ?')

        #Checking which control modes are available.
        if self._laser_logic.laser_can_power == True:
            self._mw.powerRadioButton.setEnabled(True)
            lpr = self._laser_logic.laser_power_range
            self._mw.LaserdoubleSpinBox.setRange(lpr[0], lpr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_power_setpoint)
        else:
            self._mw.powerRadioButton.setEnabled(False)

        if self._laser_logic.laser_can_current == True:
            self._mw.currentRadioButton.setEnabled(True)
            lcr = self._laser_logic.laser_current_range
            self._mw.LaserdoubleSpinBox.setRange(lcr[0], lcr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_current_setpoint)
        else:
            self._mw.currentRadioButton.setEnabled(False)

        if self._laser_logic.laser_can_digital_mod == True:
            self._mw.digModulationRadioButton.setEnabled(True)
            lpr = self._laser_logic.laser_power_range
            self._mw.LaserdoubleSpinBox.setRange(lpr[0], lpr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_power_setpoint)
        else:
            self._mw.digModulationRadioButton.setEnabled(False)

        if self._laser_logic.laser_can_analog_mod == True:
            self._mw.analogModulationRadioButton.setEnabled(True)
            lpr = self._laser_logic.laser_power_range
            self._mw.LaserdoubleSpinBox.setRange(lpr[0], lpr[1])
            self._mw.LaserdoubleSpinBox.setValue(self._laser_logic.laser_power_setpoint)
        else:
            self._mw.analogModulationRadioButton.setEnabled(False)

        #Checking which control mode is currently used.
        if self._laser_logic.laser_control_mode == ControlMode.POWER:
            self._mw.powerRadioButton.setChecked(True)
            self._mw.currentRadioButton.setChecked(False)
            self._mw.digModulationRadioButton.setChecked(False)
            self._mw.analogModulationRadioButton.setChecked(False)
            self._mw.LaserdoubleSpinBox.setSuffix('W')
        elif self._laser_logic.laser_control_mode == ControlMode.CURRENT:
            self._mw.currentRadioButton.setChecked(True)
            self._mw.powerRadioButton.setChecked(False)
            self._mw.digModulationRadioButton.setChecked(False)
            self._mw.analogModulationRadioButton.setChecked(False)
            self._mw.LaserdoubleSpinBox.setSuffix('mA')
        elif self._laser_logic.laser_control_mode == ControlMode.MODULATION_DIGITAL:
            self._mw.digModulationRadioButton.setChecked(True)
            self._mw.powerRadioButton.setChecked(False)
            self._mw.currentRadioButton.setChecked(False)
            self._mw.analogModulationRadioButton.setChecked(False)
        elif self._laser_logic.laser_control_mode == ControlMode.MODULATION_ANALOG:
            self._mw.analogModulationRadioButton.setChecked(True)
            self._mw.powerRadioButton.setChecked(False)
            self._mw.currentRadioButton.setChecked(False)
            self._mw.digModulationRadioButton.setChecked(False)

        #Checking if you can do another saturation measurement again.
        #Note, it could be that it is better to use the counterlogic!
        if self._counterlogic.module_state() == 'locked':
            self._mw.start_saturation_Action.setEnabled(True)
            self._mw.start_saturation_Action.setChecked(True)
            self._mw.laser_ON_Action.setEnabled(False)
            #self._mw.LaserButtonON.setEnabled(False)
            self._mw.laser_OFF_Action.setEnabled(False)
            #self._mw.LaserButtonOFF.setEnabled(False)
            self._mw.LaserdoubleSpinBox.setEnabled(False)
            self._mw.analogModulationRadioButton.setEnabled(False)
            self._mw.currentRadioButton.setEnabled(False)
            self._mw.digModulationRadioButton.setEnabled(False)
            self._mw.powerRadioButton.setEnabled(False)
            self._mw.numPointsSpinBox.setEnabled(False)
            self._mw.startPowerDoubleSpinBox.setEnabled(False)
            self._mw.stopPowerDoubleSpinBox.setEnabled(False)
            self._mw.timeDoubleSpinBox.setEnabled(False)
        else:
            self._mw.start_saturation_Action.setEnabled(True)
            self._mw.start_saturation_Action.setChecked(False)
            self._mw.LaserdoubleSpinBox.setEnabled(True)
            self._mw.analogModulationRadioButton.setEnabled(True)
            self._mw.currentRadioButton.setEnabled(True)
            self._mw.digModulationRadioButton.setEnabled(True)
            self._mw.powerRadioButton.setEnabled(True)
            self._mw.numPointsSpinBox.setEnabled(True)
            self._mw.startPowerDoubleSpinBox.setEnabled(True)
            self._mw.stopPowerDoubleSpinBox.setEnabled(True)
            self._mw.timeDoubleSpinBox.setEnabled(True)
            #Checking if the laser is on or off. 
            if self._laser_logic.get_laser_state() == LaserState.ON:
                self._mw.laser_ON_Action.setEnabled(False)
                #self._mw.LaserButtonON.setEnabled(False)
                self._mw.laser_OFF_Action.setEnabled(True)
                #self._mw.LaserButtonOFF.setEnabled(True)
            elif self._laser_logic.get_laser_state() == LaserState.OFF:
                self._mw.laser_OFF_Action.setEnabled(False)
                #self._mw.LaserButtonOFF.setEnabled(False)
                self._mw.laser_ON_Action.setEnabled(True)
                #self._mw.LaserButtonON.setEnabled(True)
            else:
                self._mw.laser_ON_Action.setText('Laser: ?')
                #self._mw.LaserButtonON.setText('Laser: ?')


    @QtCore.Slot()
    def updatePowerFromSpinBox(self):
        """ The user has changed the spinbox, update all other values from that. 
        """
        #self._mw.setValueVerticalSlider.setValue(self._mw.setValueDoubleSpinBox.value())
        cur = self._mw.currentRadioButton.isChecked() and self._mw.currentRadioButton.isEnabled()
        pwr = self._mw.powerRadioButton.isChecked() and  self._mw.powerRadioButton.isEnabled()
        dig_mod = self._mw.digModulationRadioButton.isChecked() and self._mw.digModulationRadioButton.isEnabled()
        analog_mod = self._mw.analogModulationRadioButton.isChecked() and self._mw.analogModulationRadioButton.isEnabled()

        if pwr:
            self.sigPower.emit(self._mw.LaserdoubleSpinBox.value())
        elif cur:
            self.sigCurrent.emit(self._mw.LaserdoubleSpinBox.value())
        elif dig_mod:
            self.sigPower.emit(self._mw.LaserdoubleSpinBox.value())
        elif analog_mod:
            self.sigPower.emit(self._mw.LaserdoubleSpinBox.value())

    @QtCore.Slot()
    def refreshGui(self):
        """ Update labels, the plot and button states with new data. 
        """

        sat_data = self._laser_logic.get_saturation_data()
        #TODO: Create a display with the error bar and not only the points.
        counts_value = sat_data['Fluorescence'][-1]
        scale_fact = units.ScaledFloat(counts_value).scale_val
        unit_prefix = units.ScaledFloat(counts_value).scale
        self._mw.saturation_Curve_Label.setText('{0:6.3f} {1}{2}'.format(counts_value / scale_fact,  unit_prefix, 'counts/s'))
        #self._mw.currentLabel.setText('{0:6.3f} mA'.format(self._laser_logic.laser_current_setpoint))
        #self._mw.powerLabel.setText('{0:6.3f} W'.format(self._laser_logic.laser_power_setpoint))
        #self._mw.extraLabel.setText(self._laser_logic.laser_extra)
        #self.updateButtonsEnabled()
        self.saturation_curve.setData(sat_data['Power'], sat_data['Fluorescence'])    
        self.errorbar.setData(x=sat_data['Power'], y=sat_data['Fluorescence'], height=sat_data['Stddev'])
                              
        if len(sat_data['Power']) > 1:
            self.errorbar.setData(beam=(sat_data['Power'][1] - sat_data['Power'][0])/4) 

    @QtCore.Slot()       
    def restore_defaultview(self):
        self._mw.restoreGeometry(self.mwsettings.value("geometry", ""))
        self._mw.restoreState(self.mwsettings.value("windowState", ""))

    def update_settings(self):
        """ Write the new settings from the gui to the file. """
        self._laser_logic.power_start = self._mw.startPowerDoubleSpinBox.value()
        self._laser_logic.power_stop = self._mw.stopPowerDoubleSpinBox.value()
        self._laser_logic.number_of_points = self._mw.numPointsSpinBox.value()
        self._laser_logic.time_per_point = self._mw.timeDoubleSpinBox.value()
        return

    @QtCore.Slot(np.ndarray, np.ndarray, dict)
    def update_fit(self, x_data, y_data, result_str_dict):
        """ Update the plot of the fit and the fit results displayed.

        @params np.array x_data: 1D arrays containing the x values of the fitting function
        @params np.array y_data: 1D arrays containing the y values of the fitting function
        @params dict result_str_dict: a dictionary with the relevant fit parameters. Each entry has
                                            to be a dict with two needed keywords 'value' and 'unit'
                                            and one optional keyword 'error'.
        """
        self._mw.saturation_fit_results_DisplayWidget.clear()
        try:
            formated_results = units.create_formatted_output(result_str_dict)
        except:
            formated_results = 'this fit does not return formatted results'
        self._mw.saturation_fit_results_DisplayWidget.setPlainText(formated_results)
        self.saturation_fit_image.setData(x=x_data, y=y_data)
        if self.saturation_fit_image not in self._pw.listDataItems():
            self._pw.addItem(self.saturation_fit_image)
        self._mw.dofit_Button.setChecked(True)

    @QtCore.Slot(bool)
    def run_stop_saturation(self, is_checked):
        """ Manages what happens if saturation scan is started/stopped. """
        if is_checked:
            # change the axes appearance according to input values:
            self._mw.laser_ON_Action.setEnabled(False)
            #self._mw.LaserButtonON.setEnabled(False)
            self._mw.laser_OFF_Action.setEnabled(False)
            #self._mw.LaserButtonOFF.setEnabled(False)
            self._mw.LaserdoubleSpinBox.setEnabled(False)
            self._mw.analogModulationRadioButton.setEnabled(False)
            self._mw.currentRadioButton.setEnabled(False)
            self._mw.digModulationRadioButton.setEnabled(False)
            self._mw.powerRadioButton.setEnabled(False)
            self._mw.numPointsSpinBox.setEnabled(False)
            self._mw.startPowerDoubleSpinBox.setEnabled(False)
            self._mw.stopPowerDoubleSpinBox.setEnabled(False)
            self._mw.timeDoubleSpinBox.setEnabled(False)
            self.sigStartSaturation.emit()
            self._mw.start_saturation_Action.setEnabled(False)
            self._pw.removeItem(self.saturation_fit_image)
            self._mw.saturation_fit_results_DisplayWidget.clear()
            self._mw.dofit_Button.setChecked(False)
           
        else:
            self._mw.LaserdoubleSpinBox.setEnabled(True)
            self._mw.analogModulationRadioButton.setEnabled(True)
            self._mw.currentRadioButton.setEnabled(True)
            self._mw.digModulationRadioButton.setEnabled(True)
            self._mw.powerRadioButton.setEnabled(True)
            self._mw.numPointsSpinBox.setEnabled(True)
            self._mw.startPowerDoubleSpinBox.setEnabled(True)
            self._mw.stopPowerDoubleSpinBox.setEnabled(True)
            self._mw.timeDoubleSpinBox.setEnabled(True)
            self.sigStopSaturation.emit()
            self._mw.start_saturation_Action.setChecked(False)
            self._mw.start_saturation_Action.setEnabled(True)
        return

    @QtCore.Slot()
    def start_saturation_curve_clicked(self):
        """ Deals with what needs to happen when a Saturation curve is started. 
        """
        pwr = self._mw.powerRadioButton.isChecked()

        time_per_point = self._mw.timeDoubleSpinBox.value()
        start_power = self._mw.startPowerDoubleSpinBox.value()
        stop_power = self._mw.stopPowerDoubleSpinBox.value()
        num_of_points = self._mw.numPointsSpinBox.value()

        if start_power > stop_power:
            start_power = stop_power
            num_of_points = start_power/stop_power

        if pwr:
            final_power = self._mw.LaserdoubleSpinBox.value()
        else:
            final_power = start_power

        if self._counterlogic.module_state() == 'locked':
            self._mw.start_saturation_Action.setText('Start saturation')
            self._laser_logic.stop_saturation_curve_data()
        else:
            self._mw.start_saturation_Action.setText('Stop saturation')
            self._laser_logic.start_saturation_curve_data(time_per_point,
                                                                start_power,
                                                                stop_power,
                                                                num_of_points,
                                                                final_power)

        return self._laser_logic.module_state()

    def save_saturation_curve_clicked(self):
        """ Save the saturation curve data and the figure
        """

        filetag = self._mw.save_tag_LineEdit.text()

        self.sigSaveMeasurement.emit(filetag)
        self._mw.save_curve_Action.setChecked(False)
        return

    def aborted_saturation_measurement(self):
        """ Makes sure everything goes back to normal if a measurement is aborted.
        """
        self._mw.start_saturation_Action.setChecked(False)
        self._mw.start_saturation_Action.setEnabled(True)
        self._mw.start_saturation_Action.setText('Start saturation')
        self._mw.LaserdoubleSpinBox.setEnabled(True)
        self._mw.analogModulationRadioButton.setEnabled(True)
        self._mw.currentRadioButton.setEnabled(True)
        self._mw.digModulationRadioButton.setEnabled(True)
        self._mw.powerRadioButton.setEnabled(True)
        self._mw.numPointsSpinBox.setEnabled(True)
        self._mw.startPowerDoubleSpinBox.setEnabled(True)
        self._mw.stopPowerDoubleSpinBox.setEnabled(True)
        self._mw.timeDoubleSpinBox.setEnabled(True)

        return

    def dofit_button_clicked(self, checked):
        if checked:
            self._mw.dofit_Button.setChecked(False)
            self._laser_logic.do_fit()
        else: 
            self._pw.removeItem(self.saturation_fit_image)
            self._mw.saturation_fit_results_DisplayWidget.clear()


    ###########################################################################
    #              Optimal operation point measurement methods                #
    ###########################################################################

    @QtCore.Slot(bool)
    def run_stop_OOP_measurement(self, is_checked):
        """ Manages what happens if operation point measurement is started/stopped. """
        if is_checked:
            self.sigStartOOPMeasurement.emit()
        else:
            self.sigStopOOPMeasurement.emit()
        return


    @QtCore.Slot()
    def OOP_started(self):
        self._mw.run_stop_measurement_Action.setChecked(True)
        self._mw.laser_power_start_DoubleSpinBox.setEnabled(False)
        self._mw.laser_power_stop_DoubleSpinBox.setEnabled(False)
        self._mw.laser_power_num_SpinBox.setEnabled(False)
        self._mw.mw_power_start_DoubleSpinBox.setEnabled(False)
        self._mw.mw_power_stop_DoubleSpinBox.setEnabled(False)
        self._mw.mw_power_num_SpinBox.setEnabled(False)
        self._mw.freq_start_DoubleSpinBox.setEnabled(False)
        self._mw.freq_stop_DoubleSpinBox.setEnabled(False)
        self._mw.freq_num_SpinBox.setEnabled(False)
        self._mw.counter_runtime_DoubleSpinBox.setEnabled(False)
        self._mw.odmr_runtime_DoubleSpinBox.setEnabled(False)
        self._mw.channel_SpinBox.setEnabled(False)
        self._mw.optimize_CheckBox.setEnabled(False)
        self._mw.fit_ComboBox.setEnabled(False)
        self._mw.nametag_LineEdit.setEnabled(False)
        self._mw.start_saturation_Action.setEnabled(False)
        self._mw.laser_ON_Action.setEnabled(False)
        self._mw.laser_OFF_Action.setEnabled(False)
        self._mw.LaserdoubleSpinBox.setEnabled(False)
        self._mw.analogModulationRadioButton.setEnabled(False)
        self._mw.currentRadioButton.setEnabled(False)
        self._mw.digModulationRadioButton.setEnabled(False)
        self._mw.powerRadioButton.setEnabled(False)

    @QtCore.Slot()
    def OOP_stopped(self):
        self._mw.run_stop_measurement_Action.setChecked(False)
        self._mw.laser_power_start_DoubleSpinBox.setEnabled(True)
        self._mw.laser_power_stop_DoubleSpinBox.setEnabled(True)
        self._mw.laser_power_num_SpinBox.setEnabled(True)
        self._mw.mw_power_start_DoubleSpinBox.setEnabled(True)
        self._mw.mw_power_stop_DoubleSpinBox.setEnabled(True)
        self._mw.mw_power_num_SpinBox.setEnabled(True)
        self._mw.freq_start_DoubleSpinBox.setEnabled(True)
        self._mw.freq_stop_DoubleSpinBox.setEnabled(True)
        self._mw.freq_num_SpinBox.setEnabled(True)
        self._mw.counter_runtime_DoubleSpinBox.setEnabled(True)
        self._mw.odmr_runtime_DoubleSpinBox.setEnabled(True)
        self._mw.channel_SpinBox.setEnabled(True)
        self._mw.optimize_CheckBox.setEnabled(True)
        self._mw.fit_ComboBox.setEnabled(True)
        self._mw.nametag_LineEdit.setEnabled(True)
        self._mw.start_saturation_Action.setEnabled(True)
        self._mw.laser_ON_Action.setEnabled(True)
        self._mw.laser_OFF_Action.setEnabled(True)
        self._mw.LaserdoubleSpinBox.setEnabled(True)
        self._mw.analogModulationRadioButton.setEnabled(True)
        self._mw.currentRadioButton.setEnabled(True)
        self._mw.digModulationRadioButton.setEnabled(True)
        self._mw.powerRadioButton.setEnabled(True)

    @QtCore.Slot()
    def OOP_update_data(self):
        # self.matrix_image.setRect(QtCore.QRectF())
        data_name = self._mw.data_ComboBox.currentText()
        if data_name != '':

            matrix = self._laser_logic.get_data(data_name) 
            scale_fact = units.ScaledFloat(matrix[0][0]).scale_val
            unit_prefix = units.ScaledFloat(matrix[0][0]).scale
            matrix_scaled = matrix / scale_fact
            cb_range = self.get_matrix_cb_range(matrix_scaled)
            unit_scaled = unit_prefix + self._laser_logic.get_data_unit(data_name)
            self.update_colorbar(cb_range, unit_scaled)

            self.matrix_image.setImage(image=matrix_scaled,
                                       axisOrder='row-major',
                                       levels=(cb_range[0], cb_range[1]))
            self.matrix_image.setRect(
                QtCore.QRectF(
                    self._laser_logic._odmr_data['coord1_arr'][0],
                    self._laser_logic._odmr_data['coord0_arr'][0],
                    self._laser_logic._odmr_data['coord1_arr'][-1] - self._laser_logic._odmr_data['coord1_arr'][0],
                    self._laser_logic._odmr_data['coord0_arr'][-1] - self._laser_logic._odmr_data['coord0_arr'][0])
                )

    def get_matrix_cb_range(self, matrix):
        matrix_nonzero = matrix[np.nonzero(matrix)]
        cb_min = np.min(matrix_nonzero)
        cb_max = np.max(matrix_nonzero)
        cb_range = [cb_min, cb_max]
        return cb_range

    #FIXME: Colorbar not properly displayed for big numbers (>1e9) or small numbers (<1e-3)
    def update_colorbar(self, cb_range, unit):
        self.oop_cb.refresh_colorbar(cb_range[0], cb_range[1])
        self._mw.oop_cb_PlotWidget.setLabel('right', units=unit)
        return

    def change_laser_params(self):
        laser_power_start = self._mw.laser_power_start_DoubleSpinBox.value()
        laser_power_stop = self._mw.laser_power_stop_DoubleSpinBox.value()
        laser_power_num = self._mw.laser_power_num_SpinBox.value()
        self.sigOOPLaserParamsChanged.emit(laser_power_start, laser_power_stop, laser_power_num)
        return
    
    def change_mw_params(self):
        mw_power_start = self._mw.mw_power_start_DoubleSpinBox.value()
        mw_power_stop = self._mw.mw_power_stop_DoubleSpinBox.value()
        mw_power_num = self._mw.mw_power_num_SpinBox.value()
        self.sigOOPMwParamsChanged.emit(mw_power_start, mw_power_stop, mw_power_num)
        return

    def change_freq_params(self):
        freq_start = self._mw.freq_start_DoubleSpinBox.value()
        freq_stop = self._mw.freq_stop_DoubleSpinBox.value()
        freq_num = self._mw.freq_num_SpinBox.value()
        self.sigOOPFreqParamsChanged.emit(freq_start, freq_stop, freq_num)
        return

    def change_runtime_params(self):
        counter_runtime = self._mw.counter_runtime_DoubleSpinBox.value()
        odmr_runtime = self._mw.odmr_runtime_DoubleSpinBox.value()
        self.sigOOPRuntimeParamsChanged.emit(counter_runtime, odmr_runtime)
        return

    def update_parameters(self):
        param_dict = self._laser_logic.get_OOP_parameters()

        param = param_dict.get('laser_power_start')
        self._mw.laser_power_start_DoubleSpinBox.blockSignals(True)
        self._mw.laser_power_start_DoubleSpinBox.setValue(param)
        self._mw.laser_power_start_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('laser_power_stop')
        self._mw.laser_power_stop_DoubleSpinBox.blockSignals(True)
        self._mw.laser_power_stop_DoubleSpinBox.setValue(param)
        self._mw.laser_power_stop_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('laser_power_num')
        self._mw.laser_power_num_SpinBox.blockSignals(True)
        self._mw.laser_power_num_SpinBox.setValue(param)
        self._mw.laser_power_num_SpinBox.blockSignals(False)

        param = param_dict.get('mw_power_start')
        self._mw.mw_power_start_DoubleSpinBox.blockSignals(True)
        self._mw.mw_power_start_DoubleSpinBox.setValue(param)
        self._mw.mw_power_start_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('mw_power_stop')
        self._mw.mw_power_stop_DoubleSpinBox.blockSignals(True)
        self._mw.mw_power_stop_DoubleSpinBox.setValue(param)
        self._mw.mw_power_stop_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('mw_power_num')
        self._mw.mw_power_num_SpinBox.blockSignals(True)
        self._mw.mw_power_num_SpinBox.setValue(param)
        self._mw.mw_power_num_SpinBox.blockSignals(False)

        param = param_dict.get('freq_start')
        self._mw.freq_start_DoubleSpinBox.blockSignals(True)
        self._mw.freq_start_DoubleSpinBox.setValue(param)
        self._mw.freq_start_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('freq_stop')
        self._mw.freq_stop_DoubleSpinBox.blockSignals(True)
        self._mw.freq_stop_DoubleSpinBox.setValue(param)
        self._mw.freq_stop_DoubleSpinBox.blockSignals(False)
        
        param = param_dict.get('freq_num')
        self._mw.freq_num_SpinBox.blockSignals(True)
        self._mw.freq_num_SpinBox.setValue(param)
        self._mw.freq_num_SpinBox.blockSignals(False)
        
        param = param_dict.get('counter_runtime')
        self._mw.counter_runtime_DoubleSpinBox.blockSignals(True)
        self._mw.counter_runtime_DoubleSpinBox.setValue(param)
        self._mw.counter_runtime_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('odmr_runtime')
        self._mw.odmr_runtime_DoubleSpinBox.blockSignals(True)
        self._mw.odmr_runtime_DoubleSpinBox.setValue(param)
        self._mw.odmr_runtime_DoubleSpinBox.blockSignals(False)

        param = param_dict.get('channel')
        self._mw.channel_SpinBox.blockSignals(True)
        self._mw.channel_SpinBox.setValue(param)
        self._mw.channel_SpinBox.blockSignals(False)

        param = param_dict.get('optimize')
        self._mw.optimize_CheckBox.blockSignals(True)
        self._mw.optimize_CheckBox.setChecked(param)
        self._mw.optimize_CheckBox.blockSignals(False)

        param = param_dict.get('odmr_fit_function')
        self._mw.fit_ComboBox.blockSignals(True)
        self._mw.fit_ComboBox.setCurrentText(param)
        self._mw.fit_ComboBox.blockSignals(False)

        param = param_dict.get('OOP_nametag')
        self._mw.nametag_LineEdit.blockSignals(True)
        self._mw.nametag_LineEdit.setText(param)
        self._mw.nametag_LineEdit.blockSignals(False)

        return
    
    def fill_combobox(self, data_list):
        self._mw.data_ComboBox.clear()
        for data_name in data_list:
            self._mw.data_ComboBox.addItem(data_name)


