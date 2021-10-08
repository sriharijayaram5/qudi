# -*- coding: utf-8 -*-
"""
Synthetic pixel clock implementation for stand alone MicrowaveQ operation 

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
from time import sleep
from qtpy import QtCore

from logic.generic_logic import GenericLogic
from core.module import Connector, ConfigOption
from core.util.mutex import Mutex


class PeriodicTimer(object):
    """ Performs a periodic action on an op function,
        for a given number of iterations. After this period, 
        the time suspends until next command
    """

    def __init__(self):
        # for now, do nothing.  This will be initialized later
        self._timer = None

    def setup(self,
              op_function=None,         # op function to check
              start_delay = 0,          # time in seconds to wait before generating first signal
              connect_start = None,     # a signal which supplies 2 args: n_reps, pulse_length
              connect_stop = [],        # signals to trigger stop
              startup_modifier = None,  # a function with takes the startup args & modifies them to new values (n_reps, pulse_len --> n_reps_new, pulse_len_new)
              start_action = None,      # a function which performs a first action on startup 
              stop_action = None,       # a function to set the end state
              log = None
             ):

        self._lock = Mutex()
        self._timer = QtCore.QTimer()
        self._interval = None   # time to wait for action 
        self._n_reps   = None   # number of times to perform 
        self._i_reps   = None   # current iteration
        self._plane    = None   # current operation plane
        self._start_delay = start_delay
        self._startup_modifier = startup_modifier
        self._start_action = start_action
        self._stop_action = stop_action
        self.log = log

        # attaches to a function which receives i_reps, return value is irrelevant
        # the op_function performs the action.  Arguments can be given in 
        # lambda form during setup
        self._op_function = op_function

        # self signals
        self._timer.timeout.connect(self.perform_action)
        self._timer.setSingleShot(False)

        # start signal to connect to
        if self.start_timer is not None:
            connect_start.connect(self.start_timer)
        
        # update signals to connect to
        for sig in connect_stop:
            sig.connect(self.stop_timer)


    def start_timer(self, n_reps, interval):
        """ Start the timer, if timer is running, it will be restarted. """
        #self.log.debug(f"PixelClockTimer: n_reps={n_reps}, interval={interval}")
        if self._startup_modifier is not None:
            n_reps, interval = self._startup_modifier(n_reps, interval)

        if self._start_action is not None:
            self._start_action()

        with self._lock:
            self._i_reps = 0
            self._n_reps = n_reps
            self._interval = interval
        
        if self._start_delay:
            self._timer.start(self._start_delay * 1000) # in ms
        else:
            self._timer.start(self._interval * 1000) # in ms

    def stop_timer(self):
        """ Stop the timer. """
        if self._timer is not None:
            self._timer.stop()

        if self._stop_action is not None:
            self._stop_action()
        
    def perform_action(self):
        self._op_function(self._i_reps)
        
        with self._lock:
            # reset timer after first call
            if (self._i_reps == 0) and self._start_delay:
                self._timer.setInterval(self._interval * 1000)

            self._i_reps += 1
            if self._i_reps >= self._n_reps:
                self.stop_timer()


class PixelClockSimulator(GenericLogic):
    """ A synthetic hardware device to create pixel clock pulses.
    This is designed to operate with the Qnami MicrowaveQ and 'synth_spm.dll'
    - mq_master:  The MicrowaveQ device which is being tested, which is the main counter device 
                  of the currently operating ProteusQ LabQ instance
    - mq_slave:   The second MicrowaveQ unit, which is being used to produce simulated pixel
                  clock pulses.  Requests to the mq_slave are to produce a number of pixel clock
                  pulses with a given pulse length.  The mq_slave will produce an on/off signal 
                  equivalent to 0.5 the given pulse length (half on, half off)
                 
                  Example for 20 ms pulse, rising edge every 20ms
             5v	   ______      ______      ______
                   |     |     |     |     |     |
             0v	 __|     |_____|     |_____|     |_____
                 ______________________________________
                   0s   .01   .02   .03    .04   .05

     - syn_spm:   The simulated SPM ('synth_spm.dll') which receives a call to the 
                  internal function '.trigger()', which indicates a pulse has occured
                  The start is triggered by the signal 
                        
    Example config for copy-paste:

    pixelclock_sim:
        module.Class: 'pixelclock_sim_logic.PixelClockSimulator'
        start_delay: 0.5
        slave_gpo: 1
        connect:
            syn_spm:   'spm'
            mq_master: 'mq'
            mq_slave:  'mq2'
    """

    __version__ = '0.1.0'

    _modclass = 'PixelClockSimulator'
    _modtype = 'logic'
    _threaded = True 

    PEAK_HOLD_TIME = 0.005

    # declare connectors
    syn_spm = Connector(interface='CustomScanner')          # hardware example
    mq_master = Connector(interface='SlowCounterInterface')
    mq_slave = Connector(interface='SlowCounterInterface')

    _start_delay = ConfigOption('start_delay',default=0.01)
    _slave_gpo   = ConfigOption('slave_gpo', default=1)
    _t_offset    = ConfigOption('t_offset', default=0.0)

    def on_activate(self):
        # attach hardware
        self._syn_spm = self.syn_spm()
        self._mq_master = self.mq_master()
        self._mq_slave  = self.mq_slave()

        self._gpo = { 1: self._mq_slave._dev.gpio.output0.set,
                      2: self._mq_slave._dev.gpio.output1.set,
                      3: self._mq_slave._dev.gpio.output2.set,
                      4: self._mq_slave._dev.gpio.output3.set}.get(self._slave_gpo,None)

        if self._gpo is None:
            self.log.error(f"Could not use the mq_slave GPO as specified: {self._slave_gpo}")

        modifier = lambda n,t: (n, self._t_offset + t)     # n_reps, interval+offset
        #modifier = lambda n,t: (n*2, (self._t_offset + t)/2)     # split pulses in 2 
        #modifier = lambda n,t: (n*2, t/2)     # split pulses in 2 
        #modifier = lambda n,t: (n*2, 0)     # split pulses in 2 
        self.PixelClockTimer = PeriodicTimer()
        self.PixelClockTimer.setup(op_function=self.pulse_action,
                                   connect_start=self._syn_spm.sigPixelClockStarted,
                                   connect_stop=[self._syn_spm.sigPixelClockStopped],
                                   startup_modifier=modifier,
                                   start_delay=self._start_delay,
                                   start_action=self.startup_action,
                                   stop_action=self.pulse_stop,
                                   log=self.log)

        self._syn_spm.sigPixelClockSetup.connect(self.setup_pixelclock)

        self._syn_spm._lib.trigger()   # intial pulse activates external function

        self.log.info("PixelClockSimulator activated")

    def on_deactivate(self):
        #self.PixelClockTimer.stop_timer()
        pass

    def setup_pixelclock(self, plane):
        # recieves information on traversal plane
        self._plane = plane.upper()

    def pulse_action(self,i):
        # on even pulses, 
        #if not i % 2:
        #    self._gpo(1)   # turn on
        #    self._syn_spm._lib.trigger()
        #else:
        #    self._gpo(0)   # turn off 

        self._gpo(1)   # turn on

        if (self._plane == 'XY') or  (self._plane == 'X1Y1'):
            self._syn_spm._lib.trigger()

        sleep(self.PEAK_HOLD_TIME)
        self._gpo(0)   # turn off


    def pulse_stop(self):
        self._gpo(0)

    def startup_action(self):
        self.pulse_action(0)
        #sleep(0.02)
        #self.pulse_action(1)

