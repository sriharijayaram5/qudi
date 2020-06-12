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
from gui.colordefs import QudiPalettePale as palette
from gui.guibase import GUIBase
from interface.simple_laser_interface import ControlMode, ShutterState, LaserState
from qtpy import QtCore
from qtpy import QtWidgets
from qtpy import uic

class LaserWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

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
        self._mw = LaserWindow()

        # Plot labels.
        self._pw = self._mw.saturation_Curve_PlotWidget
        self._pw.setLabel('left', 'Fluorescence', units='counts/s')
        self._pw.setLabel('bottom', 'Laser Power', units='W')

        #Setting up the empty curves.
        self.curves = []

        self.curves.append(pg.PlotDataItem(pen=pg.mkPen(palette.c1), symbol=None))
        self._pw.addItem(self.curves[-1])
        self.curves.append(pg.PlotDataItem(pen=pg.mkPen(palette.c2), symbol=None))
        self._pw.addItem(self.curves[-1])

        self._mw.start_saturation_Action.triggered.connect(self.run_stop_saturation)
        self._mw.save_curve_Action.triggered.connect(self.save_saturation_curve_clicked)

        self.sigSaveMeasurement.connect(self._laser_logic.save_saturation_data, QtCore.Qt.QueuedConnection)
        self.sigCurrent.connect(self._laser_logic.set_current)
        self.sigPower.connect(self._laser_logic.set_power)
        self.sigCtrlMode.connect(self._laser_logic.set_control_mode)
        self.sigStartSaturation.connect(self.start_saturation_curve_clicked)
        self.sigStopSaturation.connect(self._laser_logic.stop_saturation_curve_data)
        self._mw.controlModeButtonGroup.buttonClicked.connect(self.changeControlMode)
        self._mw.LaserdoubleSpinBox.editingFinished.connect(self.updatePowerFromSpinBox)
        self._mw.LaserButtonON.clicked.connect(self.LaserStateON)
        self._mw.LaserButtonOFF.clicked.connect(self.LaserStateOFF)
        self._laser_logic.sigRefresh.connect(self.refreshGui)
        self._laser_logic.sigUpdateButton.connect(self.updateButtonsEnabled)
        self._laser_logic.sigAbortedMeasurement.connect(self.aborted_saturation_measurement)

        #Setting up the constraints for the Saturation Curve.
        lpr = self._laser_logic.laser_power_range
        self._mw.startPowerDoubleSpinBox.setRange(lpr[0], lpr[1])
        self._mw.startPowerDoubleSpinBox.setValue(1/1000)
        self._mw.startPowerDoubleSpinBox.setSuffix('W')
        self._mw.stopPowerDoubleSpinBox.setRange(lpr[0], lpr[1])
        self._mw.stopPowerDoubleSpinBox.setValue(22/1000)
        self._mw.stopPowerDoubleSpinBox.setSuffix('W')
        self._mw.numPointsSpinBox.setRange(1,100)
        self._mw.numPointsSpinBox.setValue(15)
        self._mw.timeDoubleSpinBox.setRange(1,1000)
        self._mw.timeDoubleSpinBox.setValue(5)
        self._mw.timeDoubleSpinBox.setSuffix('s')

        self.updateButtonsEnabled()

    def on_deactivate(self):
        """ Deactivate the module properly.
        """

        #self.sigStartSaturation.disconnect()
        #self.sigStopSaturation.disconnect()

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
        self._mw.LaserButtonON.setEnabled(False)
        self._laser_logic.on()
        self._mw.LaserButtonOFF.setEnabled(True)

        #self.sigLaserOn.emit(on)

    def LaserStateOFF(self):
        """ Disable laser power OFF button.
            Button will remain Disabled until laser power ON button is clicked.
        """
        self._mw.LaserButtonOFF.setEnabled(False)
        self._laser_logic.off()
        self._mw.LaserButtonON.setEnabled(True)

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

    @QtCore.Slot()
    def updateButtonsEnabled(self):
        """ Setting up the buttons accordingly. 
        """

        #Checking if the laser is on or off. 
        if self._laser_logic.get_laser_state() == LaserState.ON:
            self._mw.LaserButtonON.setEnabled(False)
            self._mw.LaserButtonOFF.setEnabled(True)
        elif self._laser_logic.get_laser_state() == LaserState.OFF:
            self._mw.LaserButtonOFF.setEnabled(False)
            self._mw.LaserButtonON.setEnabled(True)
        else:
            self._mw.LaserButtonON.setText('Laser: ?')

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
            self._mw.LaserButtonON.setEnabled(False)
            self._mw.LaserButtonOFF.setEnabled(False)
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
                self._mw.LaserButtonON.setEnabled(False)
                self._mw.LaserButtonOFF.setEnabled(True)
            elif self._laser_logic.get_laser_state() == LaserState.OFF:
                self._mw.LaserButtonOFF.setEnabled(False)
                self._mw.LaserButtonON.setEnabled(True)
            else:
                self._mw.LaserButtonON.setText('Laser: ?')


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

        #TODO: Create a display with the error bar and not only the points.
        self._mw.saturation_Curve_Label.setText('{0:6.3f}'.format(self._laser_logic.sat_curve_counts))
        #self._mw.currentLabel.setText('{0:6.3f} mA'.format(self._laser_logic.laser_current_setpoint))
        #self._mw.powerLabel.setText('{0:6.3f} W'.format(self._laser_logic.laser_power_setpoint))
        #self._mw.extraLabel.setText(self._laser_logic.laser_extra)
        #self.updateButtonsEnabled()
        self.curves[0].setData(self._laser_logic.data['Power'], self._laser_logic.data['Fluorescence'])
        #self.curves[1].setData(self._laser_logic.data['Power'],self._laser_logic.data['Stddev'])

    def run_stop_saturation(self, is_checked):
        """ Manages what happens if saturation scan is started/stopped. """
        if is_checked:
            # change the axes appearance according to input values:
            self._mw.LaserButtonON.setEnabled(False)
            self._mw.LaserButtonOFF.setEnabled(False)
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

