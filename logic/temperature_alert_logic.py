# -*- coding: utf-8 -*-

"""
A module for controlling temperature alerts for Attodry 2200.

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


class TemperatureAlertLogic(GenericLogic):
    """ Logic module to monitor and control a PID process

    Example config:

    temperaturealertlogic:
        module.Class: 'temperature_alert_logic.TemperatureAlertLogic'
        connect:
            controller: 'temp_controller'
            telebotlogic: 'telebotlogic'

    """

    # declare connectors
    controller = Connector(interface='CryoControllerInterface')
    telebotlogic = Connector(interface='GenericLogic')

    # status vars
    temp_cntrl_diff = StatusVar('temp_cntrl_diff', 1)
    T_setpoint_waiting_time = StatusVar('T_setpoint_waiting_time', 10)
    compressor_failure_temp_treshhold = StatusVar('compressor_failure_temp_treshhold', 10)
    check_period = StatusVar('check_period', 5)

    sigSampleTempSensorDisconnected = QtCore.Signal()  
    sigVTITempSensorDisconnected = QtCore.Signal()  
    sigReservoirTempSensorDisconnected = QtCore.Signal() 

    sigDeactivateAllWarning = QtCore.Signal()
    sigActivateCompressorWarning = QtCore.Signal() 
    sigActivateSampleWarning = QtCore.Signal() 
    sigActivateVTIWarning = QtCore.Signal() 

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._controller = self.controller()
        self._telebotlogic = self.telebotlogic()

        self.enabled = False
        self.sample_temp_cntrl_warning = False
        self.vti_temp_cntrl_warning = False
        self.compressor_failure_warning = False
        self.old_sample_temp_setpoint = self._controller.get_sample_temp_setpoint()
        self.old_vti_temp_setpoint = self._controller.get_vti_temp_setpoint()

        self.temperature_log_file_name = None

        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.check_period * 1000)  # in ms
        self.timer.timeout.connect(self.loop)
        self.sample_temp_setpoint_changed_timer = QtCore.QTimer()
        self.sample_temp_setpoint_changed_timer.setSingleShot(True)
        self.sample_temp_setpoint_changed_timer.setInterval(self.T_setpoint_waiting_time * 1000)  # in ms
        self.sample_temp_setpoint_changed_timer.timeout.connect(self.sample_temp_setpoint_changed_finished)

        self.vti_temp_setpoint_changed_timer = QtCore.QTimer()
        self.vti_temp_setpoint_changed_timer.setSingleShot(True)
        self.vti_temp_setpoint_changed_timer.setInterval(self.T_setpoint_waiting_time * 1000)  # in ms
        self.vti_temp_setpoint_changed_timer.timeout.connect(self.vti_temp_setpoint_changed_finished)

        self._telebotlogic.sigStatusRequest.connect(self.status_request)
        self._telebotlogic.sigDeactivateWarningRequest.connect(self.deactivate_warning_request)
        self._telebotlogic.sigActivateCompressorRequest.connect(self.activate_compressor_warning_request)
        self._telebotlogic.sigActivateSampleRequest.connect(self.activate_sample_warningt_request)
        self._telebotlogic.sigActivateVTIRequest.connect(self.activate_vti_warning_request)

    def on_deactivate(self):
        """ Perform required deactivation. """
        self._telebotlogic.sigStatusRequest.disconnect()

    def check_period_changed(self, check_period):
        self.check_period = check_period
        if self.enabled:
            self.timer.stop()
            self.loop()

    def startLoop(self):
        """ Start the data recording loop.
        """
        self.enabled = True
        self.timer.start(self.check_period * 1000)  # in ms

    def stopLoop(self):
        """ Stop the data recording loop.
        """
        self.enabled = False

    def stopLoopSampleSetpointChanged(self):
        self.sample_temp_setpoint_changed_timer.stop()

    def stopLoopVTISetpointChanged(self):
        self.vti_temp_setpoint_changed_timer.stop()

    def loop(self):
        """ Execute step in the data recording loop: save one of each control and process values
        """
        if self.compressor_failure_warning and (self._controller.get_reservoir_temp_setpoint()<=self.compressor_failure_temp_treshhold) and self._controller.get_reservoir_temp_control_status():
            reservoir_temp = self._controller.get_reservoir_temp()
            if reservoir_temp == -1:
                self.sigReservoirTempSensorDisconnected.emit()
            elif reservoir_temp>self.compressor_failure_temp_treshhold:
                self.send_compressor_failure_warning(reservoir_temp)

        if self.sample_temp_cntrl_warning and self._controller.get_sample_temp_control_status():
            sample_temp = self._controller.get_sample_temp()
            if sample_temp == -1:
                self.sigSampleTempSensorDisconnected.emit()
            else:
                sample_temp_setpoint = self._controller.get_sample_temp_setpoint()
                if self.old_sample_temp_setpoint != sample_temp_setpoint:
                    self.old_sample_temp_setpoint = sample_temp_setpoint
                    self.sample_temp_cntrl_warning = False
                    self.sample_temp_setpoint_changed_timer.start(self.T_setpoint_waiting_time * 1000)
                elif abs(sample_temp_setpoint-sample_temp)>self.temp_cntrl_diff:
                    self.send_sample_temp_warning(sample_temp, sample_temp_setpoint)

        if self.vti_temp_cntrl_warning and self._controller.get_vti_temp_control_status():
            vti_temp = self._controller.get_vti_temp()
            if vti_temp == -1:
                self.sigVTITempSensorDisconnected.emit()
            else:
                vti_temp_setpoint = self._controller.get_vti_temp_setpoint()
                if self.old_vti_temp_setpoint != vti_temp_setpoint:
                    self.old_vti_temp_setpoint = vti_temp_setpoint
                    self.vti_temp_cntrl_warning = False
                    self.vti_temp_setpoint_changed_timer.start(self.T_setpoint_waiting_time * 1000)
                elif abs(vti_temp_setpoint-vti_temp)>self.temp_cntrl_diff:
                    self.send_vti_temp_warning(vti_temp, vti_temp_setpoint)
        
        if self.enabled:
            self.timer.start(self.check_period * 1000)  # in ms

    def send_sample_temp_warning(self, sample_temp, sample_temp_setpoint):
        msg = f'ALERT!\n Sample temperature control failure!\n Sample temperature is {sample_temp}K but Setpoint is {sample_temp_setpoint}K!'
        self.log.error(msg)
        self._telebotlogic.send_message(msg)

    def send_vti_temp_warning(self, vti_temp, vti_temp_setpoint):
        msg = f'ALERT!\n VTI temperature control failure!\n VTI temperature is {vti_temp}K but Setpoint is {vti_temp_setpoint}K!'
        self.log.error(msg)
        self._telebotlogic.send_message(msg)

    def send_compressor_failure_warning(self, reservoir_temp):
        msg = f'ALERT!\n Compressor failure!\n Reservoir temperature is {reservoir_temp}K!'
        self.log.error(msg)
        self._telebotlogic.send_message(msg)

    def sample_temp_setpoint_changed_finished(self):
        self.sample_temp_cntrl_warning = True

    def vti_temp_setpoint_changed_finished(self):
        self.vti_temp_cntrl_warning = True

    def status_request(self, chat_id):
        sample_temp = self._controller.get_sample_temp()
        vti_temp = self._controller.get_vti_temp()
        reservoir_temp = self._controller.get_reservoir_temp()
        magnet_temp = self._controller.get_magnet_temp()
        cryo_in_pressure = self._controller.get_cryo_in_pressure()
        cryo_out_pressure =self._controller.get_cryo_out_pressure()
        dump_pressure = self._controller.get_dump_pressure()
        sample_heater = self._controller.get_sample_heater_power()
        vti_heater = self._controller.get_vti_heater_power()
        reservoir_heater = self._controller.get_reservoir_heater_power()
        if self.compressor_failure_warning and (self._controller.get_reservoir_temp_setpoint()<=self.compressor_failure_temp_treshhold) and self._controller.get_reservoir_temp_control_status():
            compressor_warning_msg = 'ON'
        else:
            compressor_warning_msg = 'OFF'
        if self.sample_temp_cntrl_warning and self._controller.get_sample_temp_control_status():
            sample_warning_msg = 'ON'
        else:
            sample_warning_msg = 'OFF'
        if self.vti_temp_cntrl_warning and self._controller.get_vti_temp_control_status():
            vti_warning_msg = 'ON'
        else:
            vti_warning_msg = 'OFF'
        
        msg = f"Cryostat Status: \
                \nSample temp: {round(sample_temp, 2)}K \
                \nVTI temp: {round(vti_temp, 2)}K \
                \nReservoir temp: {round(reservoir_temp, 2)}K \
                \nMagnet temp: {round(magnet_temp, 2)}K \
                \nCryo in pressure: {round(cryo_in_pressure, 2)}mBar \
                \nCryo out pressure: {round(cryo_out_pressure, 2)}mBar \
                \nDump pressure: {round(dump_pressure, 2)}mBar \
                \nSample heater: {round(sample_heater, 2)}W \
                \nVTI heater: {round(vti_heater, 2)}W \
                \nReservoir heater: {round(reservoir_heater, 2)}W \
                \nCompressor warning: {compressor_warning_msg} \
                \nSample warning: {sample_warning_msg} \
                \nVTI warning: {vti_warning_msg}"
        self._telebotlogic.send_message(msg, [chat_id])

    def deactivate_warning_request(self, chat_id):
        self.sigDeactivateAllWarning.emit()
        msg = f'All warnings deactivated.'
        self._telebotlogic.send_message(msg, [chat_id])

    def activate_compressor_warning_request(self, chat_id):
        self.sigActivateCompressorWarning.emit()
        msg = f'Compressor warning activated.'
        self._telebotlogic.send_message(msg, [chat_id])

    def activate_sample_warningt_request(self, chat_id):
        self.sigActivateSampleWarning.emit()
        msg = f'Sample warning activated.'
        self._telebotlogic.send_message(msg, [chat_id])

    def activate_vti_warning_request(self, chat_id):
        self.sigActivateVTIWarning.emit()
        msg = f'VTI warning activated.'
        self._telebotlogic.send_message(msg, [chat_id])
