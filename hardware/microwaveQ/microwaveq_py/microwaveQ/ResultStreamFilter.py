from . import Device as dev


class ResultStreamFilter(dev.Device):
    """RF pulse generation module
        Attributes: 
            period -- Minimum pause between measurement result transmissions in counting unit cycles. 
    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.period         = dev.Field( self.com, self.addr + 0x0000, 0, 32)

    def set(self, period):
        """Configure period in seconds
            Arguments:
                period -- Minimum pause between measurement result transmissions in seconds
        """
        self.period.set(self.com.convSecToAxiCyc(period))

