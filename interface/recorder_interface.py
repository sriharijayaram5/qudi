# -*- coding: utf-8 -*-

"""
This file contains the LabQ Interface for Recorder devices.

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

import abc
from enum import Enum
from core.util.interfaces import InterfaceMetaclass


class RecorderMode(Enum):
    """ Operation mode configuration for a microwave/counting devices"""
    # starting methods
    UNCONFIGURED = 0 
    DUMMY = 1 

    # pixel clock counting methods
    PIXELCLOCK = 2 
    PIXELCLOCK_SINGLE_ISO_B = 3 
    PIXELCLOCK_N_ISO_B = 4 
    PIXELCLOCK_TRACKED_ISO_B = 5 

    # continous counting methods
    CW_MW = 6 
    ESR = 7 
    PULSED_ESR = 8 
    COUNTER = 9 

    # advanced measurement mode
    PULSED = 10 


class RecorderState(Enum):
    DISCONNECTED = 0 
    IDLE = 1 
    ARMED = 2 
    BUSY = 3 


class RecorderConstraints:

    def __init__(self):
        # maximum numer of possible detectors for slow counter
        self.max_detectors = 0
        # frequencies in Hz
        self.min_count_frequency = 5e-5
        self.max_count_frequency = 5e5
        # add CountingMode enums to this list in instances
        self.counting_mode = []


class RecorderInterface(metaclass=InterfaceMetaclass):
    """ Define the controls for a recorder device."""

    _modtype = 'RecorderInterface'
    _modclass = 'interface'

    @abc.abstractmethod
    def configure_recorder(mode, params):
        """ Configure recorder
        Configures the recorder mode for current measurment; 
        resetting the mode is also through this interface

        @param RecorderMode: mode:  mode of recorder, as available from RecorderMode types
        @param dict: params:  specific settings as required for the given measurement mode 
        """
        pass

    @abc.abstractmethod
    def start_recorder(arm=True):
        """ Start recorder 
        start recorder with mode as configured 
        If pixel clock based methods, will begin on first trigger
        If not first configured, will cause an error
        
        @param bool: arm: specifies armed state with regard to pixel clock trigger
        """
        pass

    @abc.abstractmethod
    def get_measurment():
        """ get measurement
        returns the measurement array in integer format

        @return int_array: array of measurement as tuple elements
        """
        pass

    @abc.abstractmethod
    def stop_measurement():
        """ stop measurement
        stops all on-going measurements, returns device to idle state
        """
        pass

    @abc.abstractmethod
    def get_parameter_for_modes(mode=None):
        """ get_parameter_for_modes
        returns the required parameters.  
        If mode=None, all paramters are returned.  
        Otherwise specific mode parameters are returned

        @param RecorderMode: mode:  specifies the mode for sought parameters
        @retun dict of dicts: { RecorderMode.mode: { parameter key: value}}
        """
        pass

    @abc.abstractmethod
    def get_current_device_mode():
        """ get_current_device_mode
        returns the current device mode

        @return RecorderMode.mode
        """
        pass

    @abc.abstractmethod
    def get_current_device_state():
        """  get_current_device_state
        returns the current device state

        @return RecorderState.state
        """
        pass

    # -------------------------------------
    # GPIO settings
    # -------------------------------------
    # GPI

    @property
    def gpi0(self):
        """ gpi0 getter
        returns set state of gpi 0 (true/false)        

        @return bool: state
        """
        return False 

    @property
    def gpi1(self):
        """ gpi1 getter
        returns set state of gpi 1 (true/false)        

        @return bool: state
        """
        return False 

    @property
    def gpi2(self):
        """ gpi2 getter
        returns set state of gpi 2 (true/false)        

        @return bool: state
        """
        return False 

    @property
    def gpi3(self):
        """ gpi3 getter
        returns set state of gpi 3 (true/false)        

        @return bool: state
        """
        return False 

    # GPO

    @property
    def gpo0(self):
        """ gpo0 getter
        returns set state of gpo 0 (true/false)        

        @return bool: state
        """
        return False 

    @gpo0.setter
    def gpo0(self, state):
        """ gpo0 setter
        sets the state of gpo 0 (true/false)        

        @return None
        """
        pass

    @property
    def gpo1(self):
        """ gpo1 getter
        returns set state of gpo 1 (true/false)        

        @return bool: state
        """
        return False 

    @gpo1.setter
    def gpo1(self, state):
        """ gpo1 setter
        sets the state of gpo 1 (true/false)        

        @return None
        """
        pass

    @property
    def gpo2(self):
        """ gpo2 getter
        returns set state of gpo 2 (true/false)        

        @return bool: state
        """
        return False 

    @gpo2.setter
    def gpo2(self, state):
        """ gpo2 setter
        sets the state of gpo 2 (true/false)        

        @return None
        """
        pass

    @property
    def gpo3(self):
        """ gpo3 getter
        returns set state of gpo 3 (true/false)        

        @return bool: state
        """
        return False 

    @gpo3.setter
    def gpo3(self, state):
        """ gpo3 setter
        sets the state of gpo 3 (true/false)        

        @return None
        """
        pass