# -*- coding: utf-8 -*-

"""
A module for controlling processes with LN2 level sensor.

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
from collections import OrderedDict
import datetime
from decimal import Decimal

from core.connector import Connector
from core.statusvariable import StatusVar
from core.configoption import ConfigOption
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore


class LevelsensorLogic(GenericLogic):
    """ Logic module to monitor and control a PID process

    Example config:

    pidlogic:
        module.Class: 'levelsensor_logic.PIDLogic'
        timestep: 0.1
        connect:
            controller: 'levelsensor'
            savelogic: 'savelogic'

    """

    # declare connectors
    controller = Connector(interface='SimpleDataInterface')
    savelogic = Connector(interface='SaveLogic')

    # status vars
    bufferLength = StatusVar('bufferlength', 1000)
    timestep = ConfigOption('timestep', 100e-3)  # timestep in seconds

    # signals
    sigUpdateDisplay = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.log.debug('The following configuration was found.')

        #number of lines in the matrix plot
        self.NumberOfSecondsLog = 100
        self.threadlock = Mutex()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._controller = self.controller()
        self._save_logic = self.savelogic()

        self.history = np.zeros([4, self.bufferLength])
        self.savingState = False
        self.enabled = False
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.timestep * 1000)  # in ms
        self.timer.timeout.connect(self.loop)

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def getBufferLength(self):
        """ Get the current data buffer length.
        """
        return self.bufferLength

    def startLoop(self):
        """ Start the data recording loop.
        """
        self.enabled = True
        self.timer.start(self.timestep * 1000)  # in ms

    def stopLoop(self):
        """ Stop the data recording loop.
        """
        self.enabled = False

    def loop(self):
        """ Execute step in the data recording loop: save one of each control and process values
        """
        self.history = np.roll(self.history, -1, axis=1)
        self.history[0, -1] = self._controller.getLevel()
        self.history[1, -1] = self._controller.get_high_level()
        self.history[2, -1] = self._controller.get_low_level()
        fillstatus = self._controller.get_fill_status()
        if fillstatus == 'off':
            self.history[3, -1] = 0
        elif fillstatus == 0.0:
            self.history[3, -1] = 1
        elif fillstatus == 'timeout':
            self.history[3, -1] = 2
        else:
            self.history[3, -1] = 3
        self.sigUpdateDisplay.emit()

        if self.savingState:
            timestamp = datetime.datetime.now()
            time_delta = timestamp - self.start_timestamp
            time = '%.2E' % Decimal(f'{time_delta.total_seconds()}')
            current_level = '%.2E' % Decimal(f'{self.history[0, -1]}')
            high_level = '%.2E' % Decimal(f'{self.history[1, -1]}')
            low_level = '%.2E' % Decimal(f'{self.history[2, -1]}')
            add_row = f'{time}' + '\t' + f'{current_level}' + '\t' + f'{low_level}' + '\t' + f'{high_level}' +  '\n'
            with open(self.file, 'a') as file:
                file.write(add_row)

        if self.enabled:
            self.timer.start(self.timestep * 1000)  # in ms

    def getSavingState(self):
        """ Return whether we are saving data

            @return bool: whether we are saving data right now
        """
        return self.savingState

    def startSaving(self):
        """ Start logging data.

        """
        self.start_timestamp = datetime.datetime.now()
        filepath = self._save_logic.get_path_for_module(module_name='LN2_level_log')
        filelabel = 'LN2_level_log'
        filename = self.start_timestamp.strftime('%Y%m%d-%H%M-%S' + '_' + filelabel + '.dat')
        self.file = filepath +'\\' +  filename
        data = OrderedDict()
        data['time (s)'] = []
        data['current level (%)'] = []
        data['low level (%)'] = []
        data['high level (%)'] = []

        self._save_logic.save_data(data,
                        filepath=filepath,
                        filename=filename,
                        fmt='%.2e',
                        delimiter='\t')
        
        self.savingState = True

    def saveData(self):
        """ Stop logging data.
        """

        self.savingState = False

    def setBufferLength(self, newBufferLength):
        """ Change buffer length to new value.

            @param int newBufferLength: new buffer length
        """
        self.bufferLength = newBufferLength
        self.history = np.zeros([3, self.bufferLength])

    def get_high_level(self):
        """ Return the proportional constant.

            @return float: proportional constant of PID controller
        """
        return self._controller.get_high_level()

    def set_high_level(self, high_level):
        """ Set the proportional constant of the PID controller.

            @prarm float kp: proportional constant of PID controller
        """
        return self._controller.set_high_level(high_level)

    def get_low_level(self):
        """ Get the current setpoint of the PID controller.

            @return float: current set point of the PID controller
        """
        return self._controller.get_low_level()

    def set_low_level(self, setpoint):
        """ Set the current setpoint of the PID controller.

            @param float setpoint: new set point of the PID controller
        """
        self._controller.set_low_level(setpoint)

    def get_enabled(self):
        """ See if the PID controller is controlling a process.

            @return bool: whether the PID controller is preparing to or conreolling a process
        """
        return self.enabled

    def set_enabled(self, enabled):
        """ Set the state of the PID controller.

            @param bool enabled: desired state of PID controller
        """
        if enabled and not self.enabled:
            self.startLoop()
        if not enabled and self.enabled:
            self.stopLoop()
