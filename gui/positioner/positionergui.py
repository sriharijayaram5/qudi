# -*- coding: utf-8 -*-

"""
This file contains a gui to show data from a simple data source.

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
import copy
from core.connector import Connector
from gui.guibase import GUIBase
from gui.colordefs import QudiPalettePale as palette
from qtpy import QtWidgets
from qtpy import QtCore
from qtpy import uic


class MainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_positioner_gui.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class PositionerGui(GUIBase):
    """ FIXME: Please document
    """
    # declare connectors
    positionerlogic = Connector(interface='GenericLogic')

    sigStart = QtCore.Signal()
    sigStop = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.log.debug('The following configuration was found.')

        # checking for the right configuration
        for key in config.keys():
            self.log.info('{0}: {1}'.format(key,config[key]))

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """
        self._positioner_logic = self.positionerlogic()

        #####################
        # Configuring the dock widgets
        # Use the inherited class 'CounterMainWindow' to create the GUI window
        self._mw = MainWindow()

        # Setup dock widgets
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)
        self._init_UI()

        # make correct button state
        # self._mw.startAction.setChecked(False)

        #####################
        # Connecting user interactions
        self._connect_buttons()
        # self._mw.startAction.triggered.connect(self.start_clicked)
        # self._mw.recordAction.triggered.connect(self.save_clicked)

        #####################
        self.sigReadPositionTimer = QtCore.QTimer()
        self.sigReadPositionTimer.timeout.connect(self.read_position_loop_body)
        self.sigReadPositionTimer.start(150)

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
        self.sigReadPositionTimer.stop()
        self._mw.close()
    
    def _init_UI(self):
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'pos_widget.ui')

        self._dockwidget_container = {}
        constraints = self._positioner_logic.positioner.get_constraints()
        last_dockwidget = None
        for axis in constraints:
            dockwidget_children = {'DockWidget':None,
                                'Label':None,
                                'PositionSpinBox':None,
                                'StepPos':None,
                                'StepMinus':None,
                                'ContPos':None,
                                'ContMinus':None,
                                'Voltage':None,
                                'Frequency':None,
                                'Stop':None}
            # Load it
            obj_name = constraints[axis]['label']
            widget = uic.loadUi(ui_file)
            dockwidget = widget.dockWidget
            dockwidget.setParent(self._mw.centralWidget())
            dockwidget_children['DockWidget'] = dockwidget

            setattr(self._mw,  f'{obj_name}', dockwidget)
            dockwidget.name = obj_name # store the original name. 

            dockwidget.setWindowTitle(obj_name)
            dockwidget.setObjectName(f'dockWidget_{obj_name}')

            # set size policy for dock widget
            sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                                QtWidgets.QSizePolicy.Preferred)
            sizePolicy.setHorizontalStretch(0)
            sizePolicy.setVerticalStretch(0)
            sizePolicy.setHeightForWidth(dockwidget.sizePolicy().hasHeightForWidth())
            dockwidget.setSizePolicy(sizePolicy)

            self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2), dockwidget)
            if last_dockwidget:
                self._mw.splitDockWidget(last_dockwidget, dockwidget,
                                            QtCore.Qt.Orientation(1))
            last_dockwidget = dockwidget
            # self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(4), dockwidget)
            # self._mw.tabifyDockWidget(ref_last_dockwidget, dockwidget)
            widget = dockwidget.children()[-1]
            _, b1, b2, b3 = widget.children()
            gb1 = b1.children()
            gb2 = b2.children()
            gb3 = b3.children()

            gb1[1].setText(constraints[axis]['label'])
            dockwidget_children['Label'] = gb1[1]
            dockwidget_children['PositionSpinBox'] = gb2[1]
            dockwidget_children['StepMinus'] = gb3[2]
            dockwidget_children['StepPos'] = gb3[3]

            gb3[4].setMinimum(constraints[axis]['volt_min'])
            gb3[4].setMaximum(constraints[axis]['volt_max'])
            dockwidget_children['Voltage'] = gb3[4]
            dockwidget_children['ContMinus'] = gb3[6]
            dockwidget_children['ContPos'] = gb3[7]

            gb3[8].setMinimum(constraints[axis]['vel_min'])
            gb3[8].setMaximum(constraints[axis]['vel_max'])
            dockwidget_children['Frequency'] = gb3[8]
            dockwidget_children['Stop'] = gb3[9]

            self._dockwidget_container[obj_name] = dockwidget_children
        self.pos_list = self._dockwidget_container.keys()
        self._mw.adjustSize()
        return

    def read_position_loop_body(self):
        positions = self._positioner_logic.positioner.get_pos(self.pos_list)
        for pos in positions:
            if pos=='SampleY':
                positions[pos] -= 10e-3 # no idea why the library delivers an offset value by 10mm
            self._dockwidget_container[pos]['PositionSpinBox'].setValue(positions[pos])   
    
    def voltage_changed(self, axis):
        voltage = self._dockwidget_container[axis]['Voltage'].value()
        self._positioner_logic.positioner.positioner_axes[axis].set_voltage(voltage)

    def frequency_changed(self, axis):
        frequency = self._dockwidget_container[axis]['Frequency'].value()
        self._positioner_logic.positioner.positioner_axes[axis].set_velocity(frequency)
    
    def step_clicked(self, up_down, axis):
        self._positioner_logic.positioner.positioner_axes[axis].move_step(up_down)
    
    def cont_clicked(self, up_down, axis):
        direction = '+' if up_down==1 else '-'
        self._positioner_logic.positioner.positioner_axes[axis].continuous(direction)
    
    def stop(self, axis):
        self._positioner_logic.positioner.positioner_axes[axis].stop()

    def _connect_buttons(self):
        status = self._positioner_logic.positioner.get_status()
        for idx, positioner in enumerate(self.pos_list):
            item = self._dockwidget_container[positioner]
            volt = status['voltages'][idx]
            item['Voltage'].setValue(volt)
            item['Voltage'].editingFinished.connect(lambda pos=positioner: self.voltage_changed(pos))

            item['StepMinus'].pressed.connect(lambda pos=positioner: self.step_clicked(-1, pos))
            item['StepPos'].pressed.connect(lambda pos=positioner: self.step_clicked(1, pos))

            item['ContMinus'].pressed.connect(lambda pos=positioner: self.cont_clicked(-1, pos))
            item['ContPos'].pressed.connect(lambda pos=positioner: self.cont_clicked(1, pos))

            item['ContMinus'].released.connect(lambda pos=positioner: self.stop(pos))
            item['ContPos'].released.connect(lambda pos=positioner: self.stop(pos))

            freq = status['frequencies'][idx]
            item['Frequency'].setValue(freq)
            item['Frequency'].editingFinished.connect(lambda pos=positioner: self.frequency_changed(pos))

            item['Stop'].pressed.connect(lambda pos=positioner: self.stop(pos))
        return