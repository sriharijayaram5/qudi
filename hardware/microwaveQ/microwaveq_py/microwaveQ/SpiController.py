import logging
import time

from . import Device as dev


class SpiController(dev.Device):
    """RF pulse generation module
    
        Attributes: 
            txdata -- data to be tranmitted
            rxdata -- receiced data
            irq -- interrupt (transfer completed sticky)
            busy -- transfer underway
            en -- start transaction (0->1)
            wr -- Drive pins as output (exe-cute write operation)
            div -- Ratio of SPI clock to AXI clock (125MHz). Recommended 8 (15 MHz)
            ldiv -- (Applies only to TRF) Ratio of SPI clock to AXI clock (125MHz) for TRF LE signal generation. Recommended 8 (15 MHz)
    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
    
        self.txdata = dev.FieldW(self.com, self.addr + 0x00, 0, 32)
        self.rxdata = dev.FieldR(self.com, self.addr + 0x04, 0, 32)
        self.irq    = dev.Field( self.com, self.addr + 0x08, 0,  1)
        self.busy   = dev.Field( self.com, self.addr + 0x08, 1,  1)
        self.en     = dev.Field( self.com, self.addr + 0x0c, 0,  1)
        self.wr     = dev.Field( self.com, self.addr + 0x0c, 1,  1)
        self.div    = dev.Field( self.com, self.addr + 0x10, 0,  8)

    def waitBusy(self, timeout=0.01, step=0.001):
        """Wait for the transaction to complete
        
        Arguments:
            timeout -- transaction timeout (default = 1)
            step -- read busy flag period
        """
        success = False
        for i in range(int(timeout/step)):
            if (not self.busy.get()):
                success = True
                break
            time.sleep(step)
        assert success,"SPI operation timed out"

    def configure(self, div=8):
        """Configure SPI clock division
        
        Arguments:
            div -- Ratio of SPI clock to AXI clock (125MHz). Recommended 8 (15 MHz)
        """
        self.div.set(div)
    
    def write(self, addr, data):
        """Write SPI data
            
        Keyword arguments:
            addr/regId -- SPI device register address or ID
            data -- SPI device register value
        """
        # child implementation override (here only for docstring)
        pass 

    def read(self,addr):
        """Write SPI data
            
        Keyword arguments:
            addr/regId -- SPI device register address or ID

        Return 
            SPI device register data
        """
        # child implementation override (here only for docstring)
        pass


class TRF(SpiController):

    def __init__(self, com, addr):
        super(TRF, self).__init__(com,addr)
        self.ldiv   = dev.Field(self.com, self.addr + 0x10, 8,  8)

    def configure(self, div=4, ldiv=4):
        """Configure SPI clock division
            
        Keyword arguments:
            div -- Ratio of SPI clock to AXI clock (125MHz). Recommended 8 (15 MHz)
            ldiv -- Ratio of SPI clock to AXI clock (125MHz) for TRF LE signal generation. Recommended 8 (15 MHz)
        """
        super().configure(div)
        self.ldiv.set(ldiv)

    def rawWrite(self,reg):

        self.en.set(0)
        self.wr.set(1)
        self.txdata.set(reg)
        self.en.set(1)
        self.waitBusy()
        self.en.set(0)

    def write(self,regId,data):
        self.logger.debug(f"TRF3722 - Writing [{data:#0x}] to [{regId:#0x}]")
        self.rawWrite(regId | (1 << 3) | (data << 5))

    def read(self,regId):
        self.logger.debug(f"TRF3722 - Reading from [{regId:#0x}]")

        self.en.set(0)
        self.wr.set(0)
        self.txdata.set((1 << 3) | (regId <<28 ) | (1 << 31))
        self.en.set(1)
        self.waitBusy()
        self.en.set(0)
        return self.rxdata.get()


class DAC(SpiController):

    def __init__(self, com, addr):
        super(DAC, self).__init__(com,addr)

    # bit 23: R/W - 0=write, 1=read
    # bit 16-22: A0-A6
    # bit 0-15: D0-D15
    def write(self, address, data):
        self.logger.debug(f"DAC3XJ8X - Writing [{data:#0x}] to [{address:#0x}]")
        
        self.en.set(0)
        self.wr.set(1)
        self.txdata.set((address << 16) | data)
        self.en.set(1)
        self.waitBusy()
        self.en.set(0)

    def read(self, address):
        self.logger.debug(f"DAC3XJ8X - Reading from [{address:#0x}]")
        
        self.en.set(0)
        self.wr.set(0)
        self.txdata.set((1 << 23) | (address << 16))
        self.en.set(1)
        self.waitBusy()
        self.en.set(0)
        return self.rxdata.get()


class LMK(SpiController):

    def __init__(self,com,addr):
        super().__init__(com,addr)

    # bit 23: R/W - 0=write, 1=read
    # bit 21-22: W0, W1 = 0, 0
    # bit 8-20: A0-A12
    # bit 0-7: D0-D7
    
    def write(self, address, data):
        self.logger.debug(f"LMK04828 - Writing [{data:#0x}] to [{address:#0x}]")
        
        self.en.set(0)
        self.wr.set(1)
        self.txdata.set((address << 8) | data)
        self.en.set(1)
        self.waitBusy()
        self.en.set(0)

    def read(self, address):
        self.logger.debug(f"LMK04828 - Reading from [{address:#0x}]")
        
        self.en.set(0)
        self.wr.set(0)
        self.txdata.set((1 << 23) | (address << 8))
        self.en.set(1)
        self.waitBusy()
        self.en.set(0)
        return self.rxdata.get()
