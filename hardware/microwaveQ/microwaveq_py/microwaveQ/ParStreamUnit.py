import logging
import time
from . import Device as dev

class ParStreamUnit(dev.Device):
    """
        Attributes: 
            en              -- enable parallel streaming channel
            headIncl        -- include header number to packets
            period          -- time between two different packets
            divPulseCount   -- divider for APD pulse counter

    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.en                  = dev.Field( self.com, self.addr + 0x00000, 0,  1)
        self.headIncl            = dev.Field( self.com, self.addr + 0x00004, 0,  1)
        self.period              = dev.Field( self.com, self.addr + 0x0000c, 0, 32)
        self.divPulseCount       = dev.Field( self.com, self.addr + 0x00010, 0, 32)


    def _setStreamPeriod(self, arg):
        cycles = self.com.convSecToCuCyc(arg)
        self.period.set(cycles)

    def _getStreamPeriod(self):
        sec = self.com.convCuCycToSec(self.period.get())
        return sec

    def start(self):
        """Start parallel streaming channel run """
        self.en.set(1)

    def stop(self):
        """Stop parallel streaming channel run
        """
        self.en.set(0)