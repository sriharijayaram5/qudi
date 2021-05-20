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
    C0NTINOUSCOUNTER = 10

    # advanced measurement mode
    PULSED = 11 


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

        # add RecorderMode enums to this list in instances
        self.recorder_modes = []
        # here all the parameters associated to the recorder mode are stored.
        self.recorder_modes_params = {}


class RecorderInterface(metaclass=InterfaceMetaclass):
    """ Define the controls for a recorder device."""

    _modtype = 'RecorderInterface'
    _modclass = 'interface'


    @abc.abstractmethod
    def configure_recorder(self, mode, params):
        """ Configures the recorder mode for current measurement. 

        @param RecorderMode mode: mode of recorder, as available from 
                                  RecorderMode types
        @param dict params: specific settings as required for the given 
                            measurement mode 

        @return int: error code (0:OK, -1:error)
        """
        pass

    @abc.abstractmethod
    def start_recorder(self, arm=True):
        """ Start recorder 
        start recorder with mode as configured 
        If pixel clock based methods, will begin on first trigger
        If not first configured, will cause an error
        
        @param bool: arm: specifies armed state with regard to pixel clock trigger
        """
        pass

    @abc.abstractmethod
    def get_measurement(self):
        """ get measurement
        returns the measurement array in integer format

        @return int_array: array of measurement as tuple elements
        """
        pass

    @abc.abstractmethod
    def stop_measurement(self):
        """ stop measurement
        stops all on-going measurements, returns device to idle state
        """
        pass

    #FIXME: this might be a redundant method and can be replaced by get_recorder_limits
    @abc.abstractmethod
    def get_parameter_for_modes(self, mode=None):
        """ Returns the required parameters for the modes

        @param RecorderMode mode: specifies the mode for sought parameters
                                  If mode=None, all modes with their parameters 
                                  are returned. Otherwise specific mode 
                                  parameters are returned  

        @return dict: containing as keys the RecorderMode.mode and as values a
                      dictionary with all parameters associated to the mode.

                      Example return with mode=RecorderMode.CW_MW:
                            {RecorderMode.CW_MW: {'countwindow': 10,
                                                  'mw_power': -30}}  
        """
        pass

    @abc.abstractmethod
    def get_current_device_mode(self):
        """ Get the current device mode with its configuration parameters

        @return: (mode, params)
                RecorderMode.mode mode: the current recorder mode 
                dict params: the current configuration parameter
        """
        pass

    @abc.abstractmethod
    def get_current_device_state(self):
        """  get_current_device_state
        returns the current device state

        @return RecorderState.state
        """
        pass

    @abc.abstractmethod
    def get_recorder_limits(self):
        """ Retrieve the hardware constrains from the recorder device.

        @return RecorderConstraints: object with constraints for the recorder
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