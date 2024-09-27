# -*- coding: utf-8 -*-

"""
This file contains a gui for the levelsensor logic.

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
from core.configoption import ConfigOption
from gui.colordefs import QudiPalettePale as palette
from gui.guibase import GUIBase
from qtpy import QtCore
from qtpy import QtWidgets
from qtpy import uic


class LevelsensorMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_levelsensor_control.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class LevelsensorGui(GUIBase):
    """ FIXME: Please document
    """

    # declare connectors
    levelsensorlogic = Connector(interface='LevelsensorLogic')
    control_unit = ConfigOption('control_unit', 'unit', missing='warn')

    sigStart = QtCore.Signal()
    sigStop = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self.log.debug('The following configuration was found.')

        # checking for the right configuration
        for key in config.keys():
            self.log.info('{0}: {1}'.format(key,config[key]))

    def on_activate(self):
        """ Definition and initialisation of the GUI plus staring the measurement.

        """
        self._levelsensor_logic = self.levelsensorlogic()

        #####################
        # Configuring the dock widgets
        # Use the inherited class 'CounterMainWindow' to create the GUI window
        self._mw = LevelsensorMainWindow()

        # Setup dock widgets
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)

        # Plot labels.
        self._pw = self._mw.trace_PlotWidget

        self.plot1 = self._pw.plotItem
        self.plot1.setLabel(
            'left',
            'Level',
             units= self.control_unit)
        self.plot1.setLabel('bottom', 'Time', units='s')

        ## Create an empty plot curve to be filled later, set its pen
        self._curve1 = pg.PlotDataItem(pen=pg.mkPen(palette.c1),#, style=QtCore.Qt.DotLine),
                                       symbol=None
                                       #symbol='o',
                                       #symbolPen=palette.c1,
                                       #symbolBrush=palette.c1,
                                       #symbolSize=3
                                       )

        self._curve3 = pg.PlotDataItem(pen=pg.mkPen(palette.c2),
                                       symbol=None
                                       )

        self._curve2 = pg.PlotDataItem(pen=pg.mkPen(palette.c3),#, style=QtCore.Qt.DotLine),
                                       symbol=None
                                       #symbol='o',
                                       #symbolPen=palette.c3,
                                       #symbolBrush=palette.c3,
                                       #symbolSize=3
                                       )

#        self._curve1 = pg.PlotCurveItem()
#        self._curve1.setPen(palette.c1)

#        self._curve3 = pg.PlotCurveItem()
#        self._curve3.setPen(palette.c2)

#        self._curve2 = pg.PlotCurveItem()
#        self._curve2.setPen(palette.c3)


        self.plot1.addItem(self._curve1)
        self.plot1.addItem(self._curve3)
        self.plot1.addItem(self._curve2)

        # setting the x axis length correctly
        self._pw.setXRange(0, self._levelsensor_logic.getBufferLength() * self._levelsensor_logic.timestep)

        #####################
        # Setting default parameters
        self._mw.highLevelDoubleSpinBox.setValue(self._levelsensor_logic.get_high_level())
        self._mw.lowLevelDoubleSpinBox.setValue(self._levelsensor_logic.get_low_level())
        self._mw.automaticRefillEnabledCheckBox.setChecked(False)
        self._mw.manualRefillEnabledCheckBox.setChecked(False)

        # make correct button state
        self._mw.start_control_Action.setChecked(self._levelsensor_logic.get_enabled())

        #####################
        # Connecting user interactions
        self._mw.start_control_Action.triggered.connect(self.start_clicked)
        self._mw.record_control_Action.triggered.connect(self.save_clicked)

        self._mw.highLevelDoubleSpinBox.editingFinished.connect(self.highLevelChanged)
        self._mw.lowLevelDoubleSpinBox.editingFinished.connect(self.lowLevelChanged)
        self._mw.automaticRefillEnabledCheckBox.toggled.connect(self.automaticRefillEnabledChanged)
        self._mw.manualRefillEnabledCheckBox.toggled.connect(self.manualRefillEnabledChanged)
        self.real_toggle = True
        self.timeout = False

        # Connect the default view action
        self._mw.restore_default_view_Action.triggered.connect(self.restore_default_view)

        #####################
        # starting the physical measurement
        self.sigStart.connect(self._levelsensor_logic.startLoop)
        self.sigStop.connect(self._levelsensor_logic.stopLoop)

        self._levelsensor_logic.sigUpdateDisplay.connect(self.updateData)

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        # FIXME: !
        self._mw.close()

    def updateData(self):
        """ The function that grabs the data and sends it to the plot.
        """

        if self._levelsensor_logic.get_enabled():
            self._mw.current_level_value_Label.setText(
                '<font color={0}>{1:,.3f}</font>'.format(
                palette.c1.name(),
                self._levelsensor_logic.history[0, -1]))
            self._mw.high_level_value_Label.setText(
                '<font color={0}>{1:,.3f}</font>'.format(
                palette.c3.name(),
                self._levelsensor_logic.history[1, -1]))
            self._mw.low_level_value_Label.setText(
                '<font color={0}>{1:,.3f}</font>'.format(
                palette.c2.name(),
                self._levelsensor_logic.history[2, -1]))
            
            if self._levelsensor_logic.history[3, -1] == 0:
                if self.timeout:
                    self._mw.labelfillingstatedisplay.setText('Timeout')
                else:
                    self._mw.labelfillingstatedisplay.setText('OFF')
                    if self._mw.manualRefillEnabledCheckBox.isChecked():
                        self._mw.manualRefillEnabledCheckBox.setChecked(False)
            elif self._levelsensor_logic.history[3, -1] == 1:
                self._mw.labelfillingstatedisplay.setText('ON')
            elif self._levelsensor_logic.history[3, -1] == 2:
                self._mw.labelfillingstatedisplay.setText('Timeout')
                self.timeout = True
                if self._mw.manualRefillEnabledCheckBox.isChecked():
                    self._mw.manualRefillEnabledCheckBox.setChecked(False)
                if self._mw.automaticRefillEnabledCheckBox.isChecked():
                    self._mw.automaticRefillEnabledCheckBox.setChecked(False)

            self._curve1.setData(
                y=self._levelsensor_logic.history[0],
                x=np.arange(0, self._levelsensor_logic.getBufferLength()) * self._levelsensor_logic.timestep
                )
            self._curve2.setData(
                y=self._levelsensor_logic.history[1],
                x=np.arange(0, self._levelsensor_logic.getBufferLength()) * self._levelsensor_logic.timestep
                )
            self._curve3.setData(
                y=self._levelsensor_logic.history[2],
                x=np.arange(0, self._levelsensor_logic.getBufferLength()) * self._levelsensor_logic.timestep
                )

        if self._levelsensor_logic.getSavingState():
            self._mw.record_control_Action.setText('Save')
        else:
            self._mw.record_control_Action.setText('Start Saving Data')

        if self._levelsensor_logic.get_enabled():
            self._mw.start_control_Action.setText('Stop')
        else:
            self._mw.start_control_Action.setText('Start')

    def start_clicked(self):
        """ Handling the Start button to stop and restart the counter.
        """
        if self._levelsensor_logic.get_enabled():
            self._mw.start_control_Action.setText('Start')
            self.sigStop.emit()
        else:
            self._mw.start_control_Action.setText('Stop')
            self.sigStart.emit()

    def save_clicked(self):
        """ Handling the save button to save the data into a file.
        """
        if self._levelsensor_logic.getSavingState():
            self._mw.record_counts_Action.setText('Start Saving Data')
            self._levelsensor_logic.saveData()
        else:
            self._mw.record_counts_Action.setText('Save')
            self._levelsensor_logic.startSaving()

    def restore_default_view(self):
        """ Restore the arrangement of DockWidgets to the default
        """
        # Show any hidden dock widgets
        self._mw.levelsensor_trace_DockWidget.show()
        self._mw.levelsensor_parameters_DockWidget.show()

        # re-dock any floating dock widgets
        self._mw.levelsensor_trace_DockWidget.setFloating(False)
        self._mw.levelsensor_parameters_DockWidget.setFloating(False)

        # Arrange docks widgets
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(1), self._mw.levelsensor_trace_DockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(8), self._mw.levelsensor_parameters_DockWidget)

    def highLevelChanged(self):
        self._levelsensor_logic.set_high_level(self._mw.highLevelDoubleSpinBox.value())

    def lowLevelChanged(self):
        self._levelsensor_logic.set_low_level(self._mw.lowLevelDoubleSpinBox.value())

    def automaticRefillEnabledChanged(self, state):
        if self.real_toggle:
            if self._mw.manualRefillEnabledCheckBox.isChecked():
                self.real_toggle = False
                self._mw.manualRefillEnabledCheckBox.setChecked(False)
                self.real_toggle = True
            if state:
                self.timeout = False
                self._levelsensor_logic._controller.start_automatic_fill()
            else:
                self._levelsensor_logic._controller.stop_fill()


    def manualRefillEnabledChanged(self, state):
        if self.real_toggle:
            if self._mw.automaticRefillEnabledCheckBox.isChecked():
                self.real_toggle = False
                self._mw.automaticRefillEnabledCheckBox.setChecked(False)
                self.real_toggle = True
            if state:
                self.timeout = False
                self._levelsensor_logic._controller.start_manual_fill()
            else:
                self._levelsensor_logic._controller.stop_fill()

