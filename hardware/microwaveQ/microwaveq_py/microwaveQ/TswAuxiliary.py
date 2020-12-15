import time

from . import Device as dev


class TswAuxiliary(dev.Device):
    """Simulation pulse generation module"""

    def __init__(self, com, addr):
        super().__init__(com, addr)
        self.reset  = dev.Field(self.com, self.addr + 0x00, 0, 1)

    def resetDAC(self, wait=2):
        """Reset DAC

        Keyword arguments:
            wait -- time for dac reset (default = 2)
        """
        self.logger.info(f"Resetting DAC")
    
        self.reset.set(1)
        self.reset.set(0)
        time.sleep(wait)
        self.reset.set(1)
