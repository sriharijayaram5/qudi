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
from enum import Enum, EnumMeta
from collections import namedtuple
from datetime import datetime
from core.meta import InterfaceMetaclass


class RecorderMode(EnumMeta):
    # Specific recorder modes are to be defined by user

    # starting methods
    UNCONFIGURED             = 0
    DUMMY                    = 1


class RecorderState(Enum):
    DISCONNECTED = 0 
    LOCKED = 1
    UNLOCKED = 2
    IDLE = 3 
    IDLE_UNACK = 4
    ARMED = 5 
    BUSY = 6 


class RecorderConstraints:
    """ Defines the parameters to configure the recorder device
    """

    def __init__(self):
        # maximum numer of possible detectors for slow counter
        self.max_detectors = 0

        # frequencies in Hz
        self.min_count_frequency = 5e-5
        self.max_count_frequency = 5e5

        # add MicrowaveQMode enums to this list in instances
        self.recorder_modes = []

        # here all the parameters associated to the recorder mode are stored.
        self.recorder_mode_params = {}

        # here default values are specified 
        self.recorder_mode_params_defaults = {}

        # set allowable states, to be populated by allowable states of a mode
        self.recorder_mode_states = {}

        # set method for measurement type
        self.recorder_mode_measurements = {}


class RecorderInterface(metaclass=InterfaceMetaclass):
    """ Define the controls for a recorder device."""

    _modtype = 'RecorderInterface'
    _modclass = 'interface'

    @abc.abstractmethod
    def configure_recorder(self, mode, params):
        """ Configures the recorder mode for current measurement. 

        @param MicrowaveQMode mode: mode of recorder, as available from 
                                  MicrowaveQMode types
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
    def get_available_measurements(self, meas_keys=None):
        """ get measurements, non-blocking, non-state changing
        returns the measurement arrays in integer format

        @param (list): meas_keys: a list of keys in the measurement array; 
                                 if meas_keys = None, the default 'counts' is returned
                                 if meas_keys is not None, but not available, None is returned for the element
        @return int_array: array of measurement as tuple elements
        """
        pass

    @abc.abstractmethod
    def get_measurements(self, meas_keys=None):
        """ get measurements
        returns the measurement arrays in integer format, blocking, state changing

        @param (list): meas_keys: a list of keys in the measurement array; 
                                 if meas_keys = None, the default 'counts' is returned
                                 if meas_keys is not None, but not available, None is returned for the element
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
    def get_parameters_for_modes(self, mode=None):
        """ Returns the required parameters for the modes

        @param MicrowaveQMode mode: specifies the mode for sought parameters
                                  If mode=None, all modes with their parameters 
                                  are returned. Otherwise specific mode 
                                  parameters are returned  

        @return dict: containing as keys the MicrowaveQMode.mode and as values a
                      dictionary with all parameters associated to the mode.

                      Example return with mode=MicrowaveQMode.CW_MW:
                            {MicrowaveQMode.CW_MW: {'countwindow': 10,
                                                  'mw_power': -30}}  
        """
        pass

    @abc.abstractmethod
    def get_current_device_mode(self):
        """ Get the current device mode with its configuration parameters

        @return: (mode, params)
                MicrowaveQMode.mode mode: the current recorder mode 
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
    def get_recorder_constraints(self):
        """ Retrieve the hardware constrains from the recorder device.

        @return RecorderConstraints: object with constraints for the recorder
        """

        pass

    @abc.abstractmethod
    def get_measurement_methods(self):
        """ Retrieve the measurent methods for the recorder.

        @return RecorderMeasurements: object with measurement contraints for the recorder
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