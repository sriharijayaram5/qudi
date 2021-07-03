from . import Device as dev


class Gpio(dev.Device):
    """GPIO registers

    Attribures
    output0 -- pin PMOD1_0
    output1 -- pin PMOD1_1 
    output2 -- pin PMOD1_2 
    output3 -- pin PMOD1_3 
    input0  -- pin PMOD1_4
    input1  -- pin PMOD1_5
    input2  -- pin PMOD1_6
    input3  -- pin PMOD1_7
    
    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.output0  = dev.Field( self.com, self.addr + 0x00, 0, 1)
        self.output1  = dev.Field( self.com, self.addr + 0x00, 1, 1)
        self.output2  = dev.Field( self.com, self.addr + 0x00, 2, 1)
        self.output3  = dev.Field( self.com, self.addr + 0x00, 3, 1)
        self.input0   = dev.FieldR(self.com, self.addr + 0x04, 0, 1)
        self.input1   = dev.FieldR(self.com, self.addr + 0x04, 1, 1)
        self.input2   = dev.FieldR(self.com, self.addr + 0x04, 2, 1)
        self.input3   = dev.FieldR(self.com, self.addr + 0x04, 3, 1)
        self.rfswitch = dev.Field( self.com, self.addr + 0x08, 0, 1)

        self.outputAll= dev.Field( self.com, self.addr + 0x00, 0, 4)
        self.inputAll = dev.Field( self.com, self.addr + 0x04, 0, 4)

    
