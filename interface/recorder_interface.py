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
from collections import namedtuple
from datetime import datetime
from core.util.interfaces import InterfaceMetaclass
from core.util.mutex import Mutex


class RecorderMode(namedtuple('RecorderMode', 'value name activation'), Enum):
    # starting methods
    UNCONFIGURED             = 0, 'UNCONFIGURED', 'null'
    DUMMY                    = 1, 'DUMMY', 'null'

    # pixel clock counting methods
    PIXELCLOCK               = 2, 'PIXELCLOCK', 'trigger'
    PIXELCLOCK_SINGLE_ISO_B  = 3, 'PIXELCLOCK_SINGLE_ISO_B', 'trigger'
    PIXELCLOCK_N_ISO_B       = 4, 'PIXELCLOCK_N_ISO_B', 'trigger'
    PIXELCLOCK_TRACKED_ISO_B = 5, 'PIXELCLOCK_TRACKED_ISO_B', 'trigger'

    # continous counting methods
    CW_MW                    = 6, 'CW_MW', 'continuous'
    ESR                      = 7, 'ESR', 'continuous'
    COUNTER                  = 8, 'COUNTER', 'continuous'
    CONTINUOUS_COUNTING      = 9, 'CONTINUOUS_COUNTING', 'continuous'

    # advanced measurement mode
    PULSED_ESR               = 10, 'PULSED_ESR', 'advanced'
    PULSED                   = 11, 'PULSED', 'advanced'

    def __str__(self):
        return self.name

    def __int__(self):
        return self.value

class RecorderMeasurementMode(namedtuple('RecorderMeasurementMode', 'value name movement'), Enum):
    DUMMY = 0, 'DUMMY', 'null'
    COUNTER = 1, 'COUNTER', 'null'
    PIXELCLOCK = 2, 'PIXELCLOCK', 'line' 
    PIXELCLOCK_N_ISO_B = 3, 'PIXELCLOCK_N_ISO_B', 'line'
    ESR = 4, 'ESR', 'point'
    PULSED_ESR = 5, 'PULSED_ESR', 'point'

    def __str__(self):
        return self.name

    def __int__(self):
        return self.value

# Note: RecorderMeasurement class was meant 
#       to hold the measurement relevant information, not complete
# 
#class RecorderMeasurement:
#    """ Interface to interact with measurments
#    """
#    def __init__(self):
#        self._lock = Mutex()  # thread lock
#        self._running = False
#        self._mode = RecorderMeasurementMode.DUMMY



class RecorderState(Enum):
    DISCONNECTED = 0 
    LOCKED = 1
    UNLOCKED = 2
    IDLE = 3 
    IDLE_UNACK = 4
    ARMED = 5 
    BUSY = 6 


class RecorderStateMachine:
    """ Interface to mantain the recorder device state
        Enforcement of the state is set here
    """
    def __init__(self, enforce=False):
        self._enforce = enforce          # check state changes, warn if not allowed 
        self._last_update = None         # time when last updated
        self._allowed_transitions = {}   # dictionary of allowed state trasitions
        self._curr_state = None          # current state 
        self._lock = Mutex()             # thread lock
        self._log = None

    def set_allowed_transitions(self,transitions, initial_state=None):
        """ allowed transitions is a dictionary with { 'curr_state1': ['allowed_state1', 'allowed_state2', etc.],
                                                       'curr_state2': ['allowed_state3', etc.]}
        """
        status = -1 
        if isinstance(transitions,dict):
            self._allowed_transitions = transitions
            state = initial_state if initial_state is not None else list(transitions.keys())[0]
            status = self.set_state(state,initial_state=True)

        return status 

    def get_allowed_transitions(self):
        return self._allowed_trasitions

    def is_legal_transition(self, requested_state, curr_state=None):
        """ Checks for a legal transition of state
            @param requested_state:  the next state sought
            @param curr_state:  state to check from (can be hypothetical)

            @return int: error code (1: change OK, 0:could not change, -1:incorrect setting)
        """
        if self._allowed_transitions is None: 
            return -1       # was not configured

        if curr_state is None:
            curr_state = self._curr_state

        if (curr_state in self._allowed_transitions.keys()) and \
           (requested_state in self._allowed_transitions.keys()):

            if requested_state in self._allowed_transitions[curr_state]:
                return 1    # is possible to change
            else: 
                return 0    # is not possible to change
        else:
            return -1       # check your inputs, you asked the wrong question

    def get_state(self):
        return self._curr_state

    def set_state(self,requested_state, initial_state=False):
        """ performs state trasition, if allowed 

            @return int: error code (1: change OK, 0:could not change, -1:incorrect setting)
        """
        if self._allowed_transitions is None: 
            return -1       # was not configured

        if initial_state:
            # required only for initial state, otherwise should be set by transition 
            with self._lock:
                self._curr_state = requested_state
                self._last_update = datetime.now()
            return 1
        else:
            status = self.is_legal_transition(requested_state)
            if status > 0:
                with self._lock:
                    self._prior_state = self._curr_state
                    self._curr_state = requested_state
                    self._last_update = datetime.now()
                    return 1    # state transition was possible
            else:
                if self._enforce:
                    raise Exception(f'RecorderStateMachine: invalid change of state requested: {self._curr_state} --> {requested_state} ')
                return status   # state transition was not possible
        
    def get_last_change(self):
        """ returns the last change of state

            @return tuple: 
            - prior_state: what occured before the current
            - curr_state:  where we are now
            - last_update: when it happened
        """ 
        return self._prior_state, self._curr_state, self._last_update

class RecorderConstraints:
    """ Defines the parameters to configure the recorder device
    """

    def __init__(self):
        # maximum numer of possible detectors for slow counter
        self.max_detectors = 0
        # frequencies in Hz
        self.min_count_frequency = 5e-5
        self.max_count_frequency = 5e5

        # add RecorderMode enums to this list in instances
        self.recorder_modes = []
        # here all the parameters associated to the recorder mode are stored.
        self.recorder_mode_params = {}
        # set allowable states, to be populated by allowable states of a mode
        self.recorder_mode_states = {}
        # set method for measurement type
        self.recorder_mode_measurements = {}

class RecorderMeasurementConstraints:
    """ Defines the measurement data formats for the recorder
    """

    def __init__(self):
        # recorder data mode
        self.meas_modes = [] 
        # recorder data format, returns the structure of expected format
        self.meas_formats = {}
        # recorder measurement processing function 
        self.meas_method = {}

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