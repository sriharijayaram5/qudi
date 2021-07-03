import logging
import time
from . import Device as dev

class TrackUnit(dev.Device):
    
    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.en                             = dev.Field( self.com, self.addr + 0x00000, 0,  1)
        self.rst                            = dev.Field( self.com, self.addr + 0x00004, 0,  1)
        self.deltaFreq                      = dev.Field( self.com, self.addr + 0x00008, 0, 32)
        self.NdeltaFreq                     = dev.Field( self.com, self.addr + 0x0000c, 0, 32)
        self.startFreq                      = dev.Field( self.com, self.addr + 0x00010, 0, 32)
        self.cutOffFreq                     = dev.Field( self.com, self.addr + 0x00014, 0, 32)
        self.trackSendEn                    = dev.Field( self.com, self.addr + 0x00018, 0, 32)
        self.mode                           = dev.Field( self.com, self.addr + 0x0001C, 0, 32)
                
        self.offsetStatus                   = dev.Field( self.com, self.addr + 0x00100, 0, 32)
        self.trackReg0Status                = dev.Field( self.com, self.addr + 0x00104, 0, 32)
        self.trackReg1Status                = dev.Field( self.com, self.addr + 0x00108, 0, 32)
        self.trackReg2Status                = dev.Field( self.com, self.addr + 0x0010C, 0, 32)
        self.trackReg3Status                = dev.Field( self.com, self.addr + 0x00110, 0, 32)
        self.trackReg4Status                = dev.Field( self.com, self.addr + 0x00114, 0, 32)
        self.trackReg5Status                = dev.Field( self.com, self.addr + 0x00118, 0, 32)

    def _setDeltaFreq(self, freq):
        val = round(freq/153.6e6 * 2**28) + (2**30-1)
        self.logger.info(f"Setting the nco delta frequency {val}")
        self.deltaFreq.set(val)

    def _setStartFreq(self, freq):
        val = round(freq/153.6e6 * 2**28) + (2**30-1)
        self.logger.info(f"Setting the nco starting frequency {val}")
        self.startFreq.set(val)

    def _setCutOffFreq(self, freq):
        val = round(freq/153.6e6 * 2**28) + (2**30-1)
        self.logger.info(f"Setting the nco cuttoff frequency {val}")
        self.cutOffFreq.set(val)

    def _getOffsetFreq(self):
        freq = (self.twos_comp(self.offsetStatus.get(),30))*153.6e6 / (2**28)
        self.logger.info(f"Getting the nco offset frequency {freq}")
        return freq

    def _getDeltaFreq(self):
        freq = (self.twos_comp(self.deltaFreq.get(),30))*153.6e6 / (2**28)
        self.logger.info(f"Getting the nco delta frequency {freq}")
        return freq

    def _getStartFreq(self):
        freq = (self.twos_comp(self.startFreq.get(),30))*153.6e6 / (2**28)
        self.logger.info(f"Getting the nco starting frequency {freq}")
        return freq

    def _getCutOffFreq(self):
        freq = (self.twos_comp(self.cutOffFreq.get(),30))*153.6e6 / (2**28)
        self.logger.info(f"Getting the nco cutoff frequency {freq}")
        return freq

    def twos_comp(self, val, bits):
        """compute the 2's complement of int value val"""
        if (val & (1 << (bits - 1))) != 0: # if sign bit is set e.g., 8bit: 128-255
            val = val - (1 << bits)        # compute negative value
        return val 