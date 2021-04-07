# -*- coding: utf-8 -*-
"""
Dummy implementation for spm devices.

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

import os
import ctypes
import numpy as np
import time
import threading
import copy

from qtpy import QtCore

from core.module import Base, ConfigOption
from core.util.mutex import Mutex
from enum import IntEnum


# Interfaces to implement:
# SPMInterface

class SPMDummy(Base):
    """ Smart SPM wrapper for the communication with the module.

    Example config for copy-paste:

    simple_data_dummy:
        module.Class: 'smart_spm.SmartSPM'
        libpath: 'path/to/lib/folder'

    """

    _modclass = 'SPMDummy'
    _modtype = 'hardware'

    def __init__(self, config, **kwargs):
        """ Create CounterLogic object with connectors.

        @param dict config: module configuration
        @param dict kwargs: optional parameters
        """
        super().__init__(config=config, **kwargs)

        # locking mechanism for thread safety. 
        self.threadlock = Mutex()

        # use it like this:
        #   self.threadlock.lock() # to lock the current thread
        #   self.threadlock.unlock() # to unlock the current thread
        #   self.threadlock.acquire() # to acquire a lock
        #   self.threadlock.trylock()   # to try to lock it.

        # checking for the right configuration
        for key in config.keys():
            self.log.debug('{0}: {1}'.format(key, config[key]))

    def on_activate(self):
        """ Prepare and activate the spm module. """

        pass

    def on_deactivate(self):
        """ Clean up and deactivate the spm module. """
        pass


    # current methods:

    """
    create_scan_leftright       => logic methods!!
    create_scan_leftright2      => logic methods!!
    create_scan_snake           => logic methods!!
    check_spm_scan_params_by_plane => put this check into logic and get all the limits from hardware

    get_meas_params             => get this from settings/limits
    setup_spm                   => configure_scan_device
    set_ext_trigger             => include in configure_scan_device
    setup_scan_line             => configure_scan_line
    scan_line                   => scan_line
    get_scanned_line            => get_scanned_line
    finish_scan                 => stop_scan
    scan_point                  => scan_point
    get_objective_scanner_pos
    set_objective_scanner_pos
    get_probe_scanner_pos
    set_probe_scanner_pos

    """ 

    # Interface methods
    """
    
    Device specific functions
    =========================
    reset_device()      => ???

    get_current_device_state()
    get_current_device_config()     => internally: _set_current_device_config()
    get_available_scan_modes()
    get_parameter_for_modes()
    get_available_scan_style()


    Objective scanner Movement functions
    ==============================
    get_objective_pos
    get_objective_target_pos
    set_objective_pos_abs (vel=None, time=None)  if velocity is given, time will be ignored
    set_objective_pos_rel (vel=None, time=None)  if velocity is given, time will be ignored


    Probe scanner Movement functions
    ==============================
    get_probe_pos
    get_probe_target_pos
    set_probe_pos_abs (vel=None, time=None)  if velocity is given, time will be ignored
    set_probe_pos_rel (vel=None, time=None)  if velocity is given, time will be ignored

    Scan Functions
    ==============

    configure_scan_device (mode, params, scan_style) 
        [scan_style can be included in the params dict]
        if configuration is not possible or failed, abort further scan in the logic
        return (True, False=Not successful, -1= invalid/missing parameter)

        mode:
            OBJECTIVE_XY 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode:
            OBJECTIVE_XZ 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode:
            OBJECTIVE_YZ 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN
                
        mode:
            PROBE_CONTACT 
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode: 
            PROBE_CONSTANT_HEIGHT
        params:
            line_points
            meas_params
            lift_height
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode: 
            PROBE_DUAL_PASS
        params:
            line_points
            meas_params_pass1
            meas_params_pass2
            lift_height
        scan_style:
            LINE_SCAN or POINT_SCAN

        mode: 
            PROBE_Z_SWEEP
        params:
            line_points
            meas_params
        scan_style:
            LINE_SCAN or POINT_SCAN

    get_current_configuration()

    configure_scan_line(corr0_start, corr0_stop, corr1_start, corr1_stop, # not used in case of z sweep
                        time_forward, time_back)
        will configure a line depending on the selected mode


        (required configure_scan_device be done before the scan)
        allocate the array where data will be saved to
        
    scan_line (required configure_scan_line to be called prior)
        will execute a scan line depending on the selected mode

    get_measurement (required configure_scan_line to be called prior)
        => blocking method, either with timeout or stoppable via stop measurement

    scan_point (blocking method, required configure_scan_line to be called prior)
    
    stop_measurement()     => hardcore stop mechanism
        => if PROBE_CONSTANT_HEIGHT: land_probe
        => if PROBE_DUAL_PASS: land_probe
        => if PROBE_Z_SWEEP: BreakProbeSweepZ

        - land probe after each scan! land_probe(fast=False)
        => configuration will be set to UNCONFIGURED

    calibrate_constant_height( array with (x,y) points, safety_lift, ) 
        => return calibration points array of (x,y,z)

    get_constant_height_calibration()
        => return calibration points array of (x,y,z)


    Probe lifting functions
    ========================

    lift_probe(rel_value)
    get_lifted_value()  
        return absolute lifted value
    is_probe_landed() 
        return True/False
    land_probe(fast=False)

    """

    # SPM CONSTANTS/LIMITS      => get_spm_
    """
    DATA_CHANNEL_NAMES_LIST      => all available 
    DATA_CHANNEL_UNITS_LIST

    # ranges for objective scanner
    OBJECTIVE_SCANNER_X_MIN
    OBJECTIVE_SCANNER_X_MAX
    OBJECTIVE_SCANNER_Y_MIN
    OBJECTIVE_SCANNER_Y_MAX
    OBJECTIVE_SCANNER_Z_MIN
    OBJECTIVE_SCANNER_Z_MAX

    # ranges for probe scanner
    PROBE_SCANNER_X_MIN
    PROBE_SCANNER_X_MAX
    PROBE_SCANNER_Y_MIN
    PROBE_SCANNER_Y_MAX
    PROBE_SCANNER_Z_MIN
    PROBE_SCANNER_Z_MAX
    """

    #2D_SCAN_MODE          => get_available_scan_modes()
    """
    OBJECTIVE_XY
    OBJECTIVE_XZ
    OBJECTIVE_YZ
    PROBE_CONTACT
    PROBE_CONSTANT_HEIGHT
    PROBE_DUAL_PASS
    PROBE_Z_SWEEP
    """

    #SCAN_STYLE         => get_available_scan_style()
    """
    LINE_SCAN
    POINT_SCAN
    """


    #SPM_DEVICE_STATE   => get_current_device_state() will return one of those
    """
    DISCONNECTED
    IDLE                
    OBJECTIVE_MOVING
    OBJECTIVE_SCANNING
    PROBE_MOVING
    PROBE_SCANNING
    PROBE_LIFTED
    PROBE_SCANNING_LIFTED
    """



    #SPM SETTINGS       => all these settings are attributed to a function and 
    #                      not set individually!!
    """
    library version
    spm version
    idle_move_speed_during_scan_objective   => logic attribute, 
    scan_speed_objective                    => logic attribute

    idle_move_speed_during_scan_probe       => logic attribute
    scan_speed_probe                        => logic attribute

    idle_move_speed_position                => logic attribute

    lift_speed                              => logic attribute
    """
