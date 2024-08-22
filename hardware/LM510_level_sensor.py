# -*- coding: utf-8 -*-
"""
Author: Malik Lenger
Code for Cryomagnetics LM510 level sensor controller.

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

from pylablib.devices import Cryomagnetics
from core.module import Base
from core.configoption import ConfigOption
from interface.simple_data_interface import SimpleDataInterface

class LM510levelsensor(Base, SimpleDataInterface):
    """ Read human readable numbers from serial port.

    Example config for copy-paste:

    level_sensor:
        module.Class: 'LM510_level_sensor.LM510levelsensor'
        serial_port: 'COM1'

    """
    serial_port = ConfigOption('serial_port', 'COM1', missing='warn')

    def on_activate(self):
        """ Activate module.
        """
        try:
            self.level_sensor = Cryomagnetics.LM510(self.serial_port)
        except:
            self.log.error('Connection to the LM510 level sensor failed.')

    def on_deactivate(self):
        """ Deactivate module.
        """
        self.level_sensor.reconnect()
        self.level_sensor.close()

    def getData(self):
        """ Read current value of current channel from the level sensor.

            @return float: value from current channel of level sensor
        """
        data = 0
        try:
            data = self.level_sensor.measure_level()
        except:
            try:
                self.level_sensor.reconnect()
                data = self.level_sensor.measure_level()
            except:
                self.log.error('Something went wrong while reading the level.')
                data = 0
        return data

    def getChannels(self):
        """ Number of channels.

            @return int: number of channels
        """
        try:
            channel = self.level_sensor.get_channel()
        except:
            try:
                self.level_sensor.reconnect()
                channel = self.level_sensor.get_channel()
            except:
                self.log.error('Something went wrong while reading the channel.')
                channel = 0
        return channel
    
    def selectChannel(self, channel = 1):
        """ Sets the current channel to work with.

            @param int channel: Selected channel for operation
        """
        if channel != 1 and channel != 2:
            self.log.warning('Selected channel is not excisting. Chose channel == 1 or channel == 2.')
            return -1
        try:
            self.level_sensor.select_channel(channel)
            return 0
        except:
            try:
                self.level_sensor.reconnect()
                self.level_sensor.select_channel(channel)
                return 0
            except:
                self.log.error('Something went wrong while selecting the channel.')
                return -1
    
    def getLevel(self, channel = 1):
        """ Read current value measured by the level sensor on channel {channel}.

            @param int channel: Selected channel for operation
            @return float: value form level sensor
        """
        self.selectChannel(channel)
        return self.getData()
    
    def get_full_status(self):
        """ Read all the important status information of the hole sensor.

            @return dictonary: status information for the hole sensor
        """
        try:
            status = self.level_sensor.get_full_status()
        except:
            try:
                self.level_sensor.reconnect()
                status = self.level_sensor.get_full_status()
            except:
                self.log.error('Something went wrong while reading the full status.')
                status = -1
        return status
    
    def get_fill_status(self, channel=1):
        """ Read the filling status for automatic refilling at given channel.

            @param int channel: Selected channel for operation
            @return string or float: "off", "timeout", float (time spent with refilling)
        """
        try:
            status = self.level_sensor.get_fill_status(channel)
        except:
            try:
                self.level_sensor.reconnect()
                status = self.level_sensor.get_fill_status(channel)
            except:
                self.log.error('Something went wrong while reading the fill status.')
                status = -1
        return status
    
    def get_high_level(self, channel = 1):
        """ Read the high level for automatic refilling at given channel.

            @param int channel: Selected channel for operation
            @return float: high level
        """
        try:
            high_level = self.level_sensor.get_high_level(channel)
        except:
            try:
                self.level_sensor.reconnect()
                high_level = self.level_sensor.get_high_level(channel)
            except:
                self.log.error('Something went wrong while reading the high level.')
                high_level = -1
        return high_level
    
    def get_low_level(self, channel = 1):
        """ Read the low level for automatic refilling at given channel.

            @param int channel: Selected channel for operation
            @return float: low level
        """
        try:
            low_level = self.level_sensor.get_low_level(channel)
        except:
            try:
                self.level_sensor.reconnect()
                low_level = self.level_sensor.get_low_level(channel)
            except:
                self.log.error('Something went wrong while reading the low level.')
                low_level = -1
        return low_level
    
    def get_type(self, channel = 1):
        """ Read the type of sensor used.

            @param int channel: Selected channel for operation
            @return string: "lhe" for liquid helium or "ln" for iquid nitrogen
        """
        try:
            type = self.level_sensor.get_type(channel)
        except:
            try:
                self.level_sensor.reconnect()
                type = self.level_sensor.get_type(channel)
            except:
                self.log.error('Something went wrong while reading the type.')
                type = -1
        return type
    
    def set_high_level(self, level, channel = 1):
        """ Set the high level for automatic refilling at given channel.

            @param int channel: Selected channel for operation
        """
        try:
            self.level_sensor.set_high_level(level, channel)
        except:
            try:
                self.level_sensor.reconnect()
                self.level_sensor.set_high_level(level, channel)
            except:
                self.log.error('Something went wrong while setting the high level.')
    
    def set_low_level(self, level, channel = 1):
        """ Set the low level for automatic refilling at given channel.

            @param int channel: Selected channel for operation
        """
        try:
            self.level_sensor.set_low_level(level, channel)
        except:
            try:
                self.level_sensor.reconnect()
                self.level_sensor.set_low_level(level, channel)
            except:
                self.log.error('Something went wrong while setting the low level.')

    def set_control_mode(self, mode = 'off', channel = 1):
        """ Turns automated refilling on and off.

            @param int channel: Selected channel for operation
        """
        if mode != 'off' and mode != 'auto':
            self.log.warning('Wrong mode used. Allowed modes for automated refilling are off and auto.')
        else:
            try:
                self.level_sensor.set_control_mode(channel, mode)
            except:
                try:
                    self.level_sensor.reconnect()
                    self.level_sensor.set_control_mode(channel, mode)
                except:
                    self.log.error('Something went wrong while setting the control mode.')
    
    def start_fill(self, channel = 1):
        """ Starts a manual filling.

            @param int channel: Selected channel for operation
        """
        try:
            self.level_sensor.start_fill(channel)
        except:
            try:
                self.level_sensor.reconnect()
                self.level_sensor.start_fill(channel)
            except:
                self.log.error('Something went wrong while starting the manual filling.')

    def reset(self):
        """ Resets the device. Most of the device parameters are unchanged.
            This can be used to stop any filling and resetting the timeout state

        """
        try:
            self.level_sensor.reset()
        except:
            try:
                self.level_sensor.reconnect()
                self.level_sensor.reset()
            except:
                self.log.error('Something went wrong while resetting the device.')
