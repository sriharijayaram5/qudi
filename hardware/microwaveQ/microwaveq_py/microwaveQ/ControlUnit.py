import time

from . import Device as dev

class ControlUnit(dev.Device):
    """RF pulse generation module

        Attributes: 
            en                      -- Arm Measurement Run
            countingMode            -- Counting Mode
            measurementRunTrigger   -- Measurement Run Trigger
            accumulationMode        -- Accumulation Mode
            countingWindowLength    -- Time in control unit clock cycles. Value must be at least 2 Counting clock periods
            rfLaserDelayLength      -- Time in control unit clock cycles. Value must be at least 1 Counting clock peri-ods
            laserExcitationLength   -- Time in control unit clock cycles. Value must be at least 1 Counting clock peri-ods
            measurementLength       -- Number of sub-measurements in a meas-urement (counted from 0). 
            measurementRunLength    -- Number of measurements in a measurement run (counted from 0). 
            countingDelay           -- Delay after enabling the RF until enabling of the count-ing in continuous modes. Time in control unit clock cycles. Value must be at least 1 Counting clock peri-ods
            countingState           -- Measurement state
            reconfState             -- RF reconfiguration state
            currentTime             -- current time (debug)
            currentSubmeasurement   -- currently executing sub-measurement
            currentMeasurement      -- currently executing measurement
            pulseLength             -- table of pulse lengths in DAC cycles 
            apd2GpoAll              -- apd to all gpos enable           
            apd2Gpo0                -- apd to gpo 0 enable         
            apd2Gpo1                -- apd to gpo 1 enable         
            apd2Gpo2                -- apd to gpo 2 enable         
            apd2Gpo3                -- apd to gpo 3 enable   
            generalPulseModeEn      -- general pulsed mode enable
            ncoWord                 -- nco words array     
            ncoGain                 -- nco gains array
    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
    
        self.en                             = dev.Field( self.com, self.addr + 0x00000, 0,  1)

        self.countingMode                   = dev.Field( self.com, self.addr + 0x00004, 0,  3, {0:'None', 1:'CW', 2:'CW_ESR', 3:'RABI', 4:'PULSED_ESR', 5:'CW_PIX', 6:'ISO'})
        self.measurementRunTrigger          = dev.Field( self.com, self.addr + 0x00004, 3,  1, {0:'Manual', 1:'Triggered'})
        self.accumulationMode               = dev.Field( self.com, self.addr + 0x00004, 4,  1, {0:'Disabled', 1:'Enabled'})

        self.countingWindowLength           = dev.Field( self.com, self.addr + 0x00008, 0, 28)
        self.rfLaserDelayLength             = dev.Field( self.com, self.addr + 0x0000c, 0, 28)
        self.laserExcitationLength          = dev.Field( self.com, self.addr + 0x00010, 0, 28)
        self.measurementLength              = dev.Field( self.com, self.addr + 0x00014, 0, 32)
        self.measurementRunLength           = dev.Field( self.com, self.addr + 0x00018, 0, 32)
        self.countingDelay                  = dev.Field( self.com, self.addr + 0x0001c, 0, 28)
        self._key                           = dev.Memory(self.com, self.addr + 0x00020, 32)
        self._decode                        = dev.Field( self.com, self.addr + 0x00030, 0,  1)
        self._features                      = dev.FieldR(self.com, self.addr + 0x00034, 0, 32)
        self._unlockingDone                 = dev.FieldR(self.com, self.addr + 0x00038, 0,  1)
        self.countingState                  = dev.FieldR(self.com, self.addr + 0x00040, 0,  4)
        self.reconfState                    = dev.FieldR(self.com, self.addr + 0x00044, 0,  4, {0:'Unconfigured', 1:'RF_IDLE_S', 2:'RF_CMD_S', 3:'RF_WAIT_RSP_S', 4:'RF_CONFIGURED_S', 5:'RF_WAIT_PULSE_S', 6:'RF_ERROR_S'})
        self.currentTime                    = dev.FieldR(self.com, self.addr + 0x00048, 0, 32)
        self.currentSubmeasurement          = dev.FieldR(self.com, self.addr + 0x0004c, 0, 32)
        self.currentMeasurement             = dev.FieldR(self.com, self.addr + 0x00050, 0, 32)
        self.laserCooldownLength            = dev.Field( self.com, self.addr + 0x00060, 0, 28)

        self.apd2GpoAll                     = dev.Field( self.com, self.addr + 0x00070, 0, 4)
        self.apd2Gpo0                       = dev.Field( self.com, self.addr + 0x00070, 0, 1)
        self.apd2Gpo1                       = dev.Field( self.com, self.addr + 0x00070, 1, 1)
        self.apd2Gpo2                       = dev.Field( self.com, self.addr + 0x00070, 2, 1)
        self.apd2Gpo3                       = dev.Field( self.com, self.addr + 0x00070, 3, 1)

        self.sdInitDone                     = dev.FieldR( self.com, self.addr + 0x00080, 0, 1)
        self.sdCardDet                      = dev.FieldR( self.com, self.addr + 0x00084, 0, 1)

        self.generalPulseModeEn             = dev.Field( self.com, self.addr + 0x00100, 0, 1)
        self.generalPulseState              = dev.FieldR(self.com, self.addr + 0x00140, 0, 4)

        self.pulseLength                    = dev.Memory(self.com, self.addr + 0x10000, 32)
        self.ncoWord                        = dev.Memory(self.com, self.addr + 0x20000, 32)
        self.ncoGain                        = dev.Memory(self.com, self.addr + 0x30000, 32)

    def start(self,len=0x0):
        """Arm/Start measurement run

        Keyword arguments:
            len - number of measurments (default (0) = Infinite)
        """
        if len == 0:
            len = 0xffffffff
        else:
            len = len - 1;
        self.measurementRunLength.set(len)
        self.en.set(0)
        self.en.set(1)

    def startGenPulseMode(self):
        """Arm/Start measurement run """
        self.generalPulseModeEn.set(0)
        self.generalPulseModeEn.set(1)

    def stop(self):
        """Stop measurement run (after competition of the current measurement)
        """
        self.en.set(0)
        self.generalPulseModeEn.set(0)

    def unlock(self,key):
        """Unlocks measurement modes.
        
        Arguments:
            key - Unlocking key
        Returns:
            vector of enabled features
        """
        self.logger.info(f"Loading key {key}")
        k = list()
        for i in range(4):
            k.append((key >> i*32) & 0xFFFFFFFF)
        
        self._key.write(k)
        self._decode.set(1)
        time.sleep(1)
        return self._features.get()

    def isBusy(self):
        """Returns the state of the measurement run

        Returns:
            True - if measurement running
            False - otherwise
        """
        if self.countingState.get() == 1:
            return False
        else:
            return True

    def isSdCardDet(self):
        """Returns the state of the sd card detection

        Returns:
            True - not detected
            False - detected
        """
        if self.sdCardDet.get() == 1:
            return False
        else:
            return True

    def isSdInitDone(self):
        """Returns the state of the sd card initiaization status

        Returns:
            True - micro SD init done successfully
            False - micro SD not initialized
        """
        if self.sdInitDone.get() == 1:
            return True
        else:
            return False

    def isGenPulsedSeqBusy(self):
        """Returns the state of the measurement run

        Returns:
            True - if measurement running
            False - otherwise
        """
        if self.generalPulseState.get() == 1:
            return False
        else:
            return True

    def _setCountingWindowLength(self, arg):
        cycles = self.com.convSecToCuCyc(arg)
        assert cycles >= 2, "Counting window must be at least 2 cycles"
        self.countingWindowLength.set(cycles)

    def _setCountingDelay(self, arg):
        cycles = self.com.convSecToCuCyc(arg)
        self.countingDelay.set(cycles)

    def _setRfLaserDelayLength(self, arg):
        cycles = self.com.convSecToCuCyc(arg)
        self.rfLaserDelayLength.set(cycles)

    def _setLaserExcitationLength(self, arg):
        cycles = self.com.convSecToCuCyc(arg)
        self.laserExcitationLength.set(cycles)

    def _setLaserCooldownLength(self, arg):
        cycles = self.com.convSecToCuCyc(arg)
        self.laserCooldownLength.set(cycles)

    def _setPulseLength(self, times):
        iList = [self.com.convSecToDacCyc(t) for t in times]
        self.logger.info(f"Setting the pulse lengths {iList}")
        self.pulseLength.write(iList)

    def _setNcoWord(self, words):
        iList = [(round(-freq/153.6e6 * 2**28) + 2**30) for freq in words]
        self.logger.info(f"Setting the NCO words {iList}")
        self.ncoWord.write(iList)

    def _setNcoGain(self, gains):
        iList = [round((2**15-1)*gain) for gain in gains]
        self.logger.info(f"Setting the NCO gains {iList}")
        self.ncoGain.write(iList)

