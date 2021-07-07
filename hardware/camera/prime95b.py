# -*- coding: utf-8 -*-
# pylint: disable=no-member
"""
This hardware module is written to integrate the Photometrics Prime 95B camera. It uses a python wrapper PyVcam
to wrap over the PVCAM SDK.
---

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

from core.module import Base
from core.configoption import ConfigOption

from interface.camera_interface import CameraInterface
# from interface.odmr_counter_interface import ODMRCounterInterface
from interface.fast_counter_interface import FastCounterInterface

# Python wrapper for wrapping over the PVCAM SDK. Functions can be found
# in PyVCAM/camera.py
# pylint: disable=no-name-in-module
from pyvcam import pvc
from pyvcam.camera import Camera
from pyvcam import constants as const


class Prime95B(Base, CameraInterface, FastCounterInterface):
    """ Hardware class for Prime95B

    Example config for copy-paste:

    mycamera:
        module.Class: 'camera.prime95b.Prime95B'

    """
    # Camera name to be displayed in GUI
    _camera_name = 'Prime95B'

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self.const = const
        pvc.init_pvcam()
        # Generator function to detect a connected camera
        self.cam = next(Camera.detect_camera())
        self.cam.open()
        self.set_fan_speed(0)
        self.cam.exp_mode = "Internal Trigger"
        self.cam.exp_res = 0
        self.exp_time = self.cam.exp_time = 1
        nx_px, ny_px = self._get_detector()
        self._width, self._height = nx_px, ny_px
        self._live = False
        self.cam.speed_table_index = 1 #16 bit mode
        self.cam.exp_out_mode = 2 #Any row expose out mode
        self.cam.clear_mode = 'Pre-Sequence'
        #For pulsed
        self._number_of_gates = int(0)
        self._bin_width = 1
        self._record_length = int(1)
        self.pulsed_frames = None

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self.stop_acquisition()
        self._shut_down()

    def get_name(self):
        """ Retrieve an identifier of the camera that the GUI can print

        @return string: name for the camera
        """
        return self.cam.name

    def get_size(self):
        """ Retrieve size of the image in pixel

        @return tuple: Size (width, height)
        """
        return self.cam.shape

    def support_live_acquisition(self):
        """ Return whether or not the camera can take care of live acquisition

        @return bool: True if supported, False if not
        """
        return True

    def start_live_acquisition(self):
        """ Start a continuous acquisition

        @return bool: Success ?
        """
        self.cam.start_live()  
        self._live = True

        return True

    def start_single_acquisition(self):
        """ Start a single acquisition

        @return bool: Success ?
        """
        return True

    def stop_acquisition(self):
        """ Stop/abort live or single acquisition

        @return bool: Success ?
        """
        if self._live:
            self._live = False
        return True

    def get_acquired_data(self):
        """ Return an array of last acquired image.

        @return numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        image_array = self.cam.get_frame()

        return image_array

    def set_exposure(self, exposure):
        """ Set the exposure time in mseconds. For this python wrapper for camera hardware it only changes the value
        in the camera instance class and sets the value after image is clicked.
        Hence there maybe a discrepancy between the cam.exp_time value and the value from get_param()

        @param float time: desired new exposure time

        @return bool: Success?
        """
        # self.cam.set_param(const.PARAM_EXPOSURE_TIME, int(exposure))
        self.cam.exp_time = self.exp_time = int(exposure)
        return True

    def get_exposure(self):
        """ Get the exposure time in the current exposure res in mseconds. Different from get_param which returns the true value. This returns
        the value as assigned to the camera class.

        @return float exposure time
        """
        exp_res_dict = {0: 1, 1: 1000}
        return self.cam.exp_time / exp_res_dict[self.get_exp_res()]

    def set_gain(self, gain):
        """ Set the gain

        @param float gain: desired new gain

        @return float: new exposure gain
        """
        self.cam.gain = gain
        return self.cam.gain

    def get_gain(self):
        """ Get the gain

        @return float: exposure gain
        """
        return self.cam.gain

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        @return bool: ready ?
        """
        if self.cam.is_open:
            return True
        else:
            return False

    def _shut_down(self):
        try:
            self.cam.close()
            pvc.uninit_pvcam()
            return True
        except BaseException:
            return False

    def _get_detector(self):
        '''Returns the camera's sensor size

        @return tuple: (width pixrls, heigth pixels)
        '''
        return self.cam.sensor_size

    def get_max_gain(self):
        '''Returns the camera's maximum possible gain value. Determined also by the current speed index.

        @return float: maximum gain
        '''
        return self.cam.get_param(const.PARAM_GAIN_INDEX,
                                  const.ATTR_MAX)

    def get_max_exp(self):
        '''Returns the camera's maximum possible exposure value.

        @return float: maximum exposure
        '''
        return self.cam.get_param(const.PARAM_EXPOSURE_TIME,
                                  const.ATTR_MAX)
    
    def get_exp_res(self):
        '''Returns exposure resolution index: 0~ms, 1~us, 2~s
        '''
        return self.cam.exp_res_index

    
    def set_exp_res(self, index):
        '''Set exposure resolution index: 0~ms, 1~us, 2~s
        '''
        if index < 3:
            self.cam.exp_res = index
            return True
        else:
            return False

    def set_exposure_mode(self, exp_mode):
            '''Sets the exposure to exp_mode passed. Determines trigger behaviour. See constants.py for
            allowed values

            @param exp_mode str: string which is the key to the exposure mode dict in constants.py
            @return bool: always True
            '''
            self.cam.exp_mode = exp_mode
            return True

    def get_exposure_mode(self):
        '''Returns the current exposure mode of the cammera.

        @return str: exp_mode
        '''

        return self.cam.exp_mode

    def avail_exposure_mode(self):
        '''Possibly returns a dict of available exposure modes for the camera.

        @return dict: dict of availabel exposure modes
        '''
        return self.cam.read_enum(const.PARAM_EXPOSURE_MODE)

    def set_speed_index(self, index):
        '''Sets the speed table index. This allows moving between 16bit and 12bit modes corresponding
        also to different max gain values. The default index is 0(?) and is corresponding to 16bit images.

        @param int: index
        '''
        indices = self.cam.get_param(const.PARAM_SPDTAB_INDEX,
                                     const.ATTR_COUNT)
        if index >= indices:
            raise ValueError(
                '{} only supports '
                'speed indices < {}.'.format(
                    self._camera_name, indices))
        self.cam.speed_table_index = index

    def get_sequence(self, num_frames):
        '''Gets a sequence of images that are num_frames in nmumbers.

        @param int: num_frames
        @return ndarray: 3darray of images of shape (num_frames, 1200, 1200) for image size with default roi of
                        (1200, 1200)
        '''
        if self.get_ready_state():
            self.frames = self.cam.get_sequence(num_frames)
            return self.frames
        else:
            return 
    
    def get_constraints(self):
        """ Retrieve the hardware constrains from the Fast counting device.

        @return dict: dict with keys being the constraint names as string and
                      items are the definition for the constaints.

         The keys of the returned dictionary are the str name for the constraints
        (which are set in this method).

                    NO OTHER KEYS SHOULD BE INVENTED!

        If you are not sure about the meaning, look in other hardware files to
        get an impression. If still additional constraints are needed, then they
        have to be added to all files containing this interface.

        The items of the keys are again dictionaries which have the generic
        dictionary form:
            {'min': <value>,
             'max': <value>,
             'step': <value>,
             'unit': '<value>'}

        Only the key 'hardware_binwidth_list' differs, since they
        contain the list of possible binwidths.

        If the constraints cannot be set in the fast counting hardware then
        write just zero to each key of the generic dicts.
        Note that there is a difference between float input (0.0) and
        integer input (0), because some logic modules might rely on that
        distinction.

        ALL THE PRESENT KEYS OF THE CONSTRAINTS DICT MUST BE ASSIGNED!

        # Example for configuration with default values:

        constraints = dict()

        # the unit of those entries are seconds per bin. In order to get the
        # current binwidth in seonds use the get_binwidth method.
        constraints['hardware_binwidth_list'] = []

        """
        constraints = dict()

        # the unit of those entries are seconds per bin. In order to get the
        # current binwidth in seonds use the get_binwidth method.
        constraints['hardware_binwidth_list'] = [1 / 1e6]

        # TODO: think maybe about a software_binwidth_list, which will
        #      postprocess the obtained counts. These bins must be integer
        #      multiples of the current hardware_binwidth

        return constraints

    def ready_pulsed(self, trigger_mode='Trigger Level', mode=3):
        self.stop_acquisition()
        self.set_exposure_mode(trigger_mode)
        # EXPOSE_OUT_FIRST_ROW =  0
        # EXPOSE_OUT_ALL_ROWS = EXPOSE_OUT_FIRST_ROW + 1
        # EXPOSE_OUT_ANY_ROW = EXPOSE_OUT_ALL_ROWS + 1
        # EXPOSE_OUT_ROLLING_SHUTTER = EXPOSE_OUT_ANY_ROW + 1
        # EXPOSE_OUT_LINE_TRIGGER = EXPOSE_OUT_ROLLING_SHUTTER + 1
        # EXPOSE_OUT_GLOBAL_SHUTTER = EXPOSE_OUT_LINE_TRIGGER + 1
        # MAX_EXPOSE_OUT_MODE = EXPOSE_OUT_GLOBAL_SHUTTER + 1
        self.cam.exp_out_mode = mode
        # self.cam.clear_mode = 'Pre-Exposure' #Apparently Prime cameras can only use clear pre sequence. Other modes in constants.py are for other cameras.
        self.cam.clear_mode = 'Pre-Sequence'
        if self.pulsed_frames is None:
            self.pulsed_frames = np.zeros(1, dtype='float32')
    
    def pulsed_done(self):
        self.stop_acquisition()
        self.set_exposure_mode("Internal Trigger")
        mode = 2 #EXPOSE_OUT_ANY_ROWS
        self.cam.exp_out_mode = mode
        # self.cam.clear_mode = 'Post-Sequence' #Apparently Prime cameras can only use clear pre sequence. Other modes in constants.py are for other cameras.
        self.cam.clear_mode = 'Pre-Sequence'
        self.pulsed_frames = None
    
    def configure(self, bin_width_s, record_length_s, number_of_gates=0):
        """ Configuration of the fast counter.

        @param float bin_width_s: Length of a single time bin in the time
                                  trace histogram in seconds.
        @param float record_length_s: Total length of the timetrace/each
                                      single gate in seconds.
        @param int number_of_gates: optional, number of gates in the pulse
                                    sequence. Ignore for not gated counter.

        @return tuple(binwidth_s, record_length_s, number_of_gates):
                    binwidth_s: float the actual set binwidth in seconds
                    gate_length_s: the actual record length in seconds
                    number_of_gates: the number of gated, which are accepted, None if not-gated
        """
        # exp_res_dict = {0: 1000., 1: 1000000.}
        # self.set_exposure(bin_width_s * exp_res_dict[self.get_exp_res()])
        if record_length_s != bin_width_s:
            self.log.info('Bin not equal to record length. Camera cannot implement.')

        self._number_of_gates = number_of_gates
        self._bin_width_s = bin_width_s

        return 1, 1, number_of_gates

    
    def get_status(self):
        """ Receives the current status of the Fast Counter and outputs it as
            return value.

        0 = unconfigured
        1 = idle
        2 = running
        3 = paused
      -1 = error state
        """
        state = self.get_ready_state()
        if state:
            return 1
        else:
            return 2

    
    def start_measure(self, no_of_laser_pulses):
        """ Start the fast counter. """
        self.ready_pulsed(no_of_laser_pulses)
        self.get_sequence(no_of_laser_pulses)
        frame_data = np.mean(self.frames, axis=(1,2))
        self.pulsed_frames += frame_data
        return 0

    
    def stop_measure(self):
        """ Stop the fast counter. """
        self.stop_acquisition()
        self.pulsed_done()
        return 0

    
    def pause_measure(self):
        """ Pauses the current measurement.

        Fast counter must be initially in the run state to make it pause.
        """
        self.stop_acquisition()

    
    def continue_measure(self, no_of_laser_pulses):
        """ Continues the current measurement.

        If fast counter is in pause state, then fast counter will be continued.
        """
        return self.start_measure(no_of_laser_pulses)

    
    def is_gated(self):
        """ Check the gated counting possibility.

        @return bool: Boolean value indicates if the fast counter is a gated
                      counter (TRUE) or not (FALSE).
        """
        return False

    
    def get_binwidth(self):
        """ Returns the width of a single timebin in the timetrace in seconds.

        @return float: current length of a single bin in seconds (seconds/bin)
        """
        exp_res_dict = {0: 1000., 1: 1000000.}
        return self.get_exposure() / exp_res_dict[self.get_exp_res()]

    
    def get_data_trace(self):
        """ Polls the current timetrace data from the fast counter.

        Return value is a numpy array (dtype = int64).
        The binning, specified by calling configure() in forehand, must be
        taken care of in this hardware class. A possible overflow of the
        histogram bins must be caught here and taken care of.
        If the counter is NOT GATED it will return a tuple (1D-numpy-array, info_dict) with
            returnarray[timebin_index]
        If the counter is GATED it will return a tuple (2D-numpy-array, info_dict) with
            returnarray[gate_index, timebin_index]

        info_dict is a dictionary with keys :
            - 'elapsed_sweeps' : the elapsed number of sweeps
            - 'elapsed_time' : the elapsed time in seconds

        If the hardware does not support these features, the values should be None
        """
        info_dict = {'elapsed_sweeps': None,
                     'elapsed_time': None}  # TODO : implement that according to hardware capabilities
        return np.array(self.pulsed_frames, dtype='float32'), info_dict

    def set_fan_speed(self, fan_speed):
        self.cam.set_param(const.PARAM_FAN_SPEED_SETPOINT, fan_speed)
        fs = {0: 'High', 1: 'Medium', 2: 'Low', 3: 'Off'}
        self.log.info(f'Prime95B fan speed: {fs[fan_speed]}')
        if fan_speed==3:
            self.log.warning('Ensure liquid cooling is on!')