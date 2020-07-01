from . import Device as dev


class DelayCompensation(dev.Device):
    """Delay compensation registers
    
        Attributes: 
            rfDelay -- delay rf generation in counting clock cycles
            lsDelay -- delay laser generation in counting clock cycles
            cntDelay0, 
            cntDelay1 -- delay counting window in counting clock cycles 
                        (all cntDelay values must be equal
            rfLatency -- actual latency of the rf generation (default = 71)
    """
    
    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.rfDelay        = dev.Field( self.com, self.addr + 0x00, 0, 8)
        self.lsDelay        = dev.Field( self.com, self.addr + 0x08, 0, 8)
        self.cntDelay0      = dev.Field( self.com, self.addr + 0x10, 0, 8)
        self.cntDelay1      = dev.Field( self.com, self.addr + 0x18, 0, 8)

        self.rfLatency      = dev.Field( self.com, self.addr + 0x04, 0, 8)

    def configure(self):
        """Configures the delays to default values."""
        
        self.rfDelay.set(0)
        self.lsDelay.set(81)
        self.cntDelay0.set(88)
        self.cntDelay1.set(88)
        self.rfLatency.set(88)

