import logging
import time
from . import Device as dev

class DDR4Control(dev.Device):
    
    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.en                             = dev.Field( self.com, self.addr + 0x00100, 0,  1)
        self.circular                       = dev.Field( self.com, self.addr + 0x00104, 0,  1)
        self.startAddr                      = dev.Field( self.com, self.addr + 0x00108, 0, 64)
        self.size                           = dev.Field( self.com, self.addr + 0x00110, 0, 64)
        self.threshold                      = dev.Field( self.com, self.addr + 0x00118, 0, 32)
                
        self.rResp                          = dev.FieldR( self.com, self.addr + 0x00200, 0, 32)
        self.bResp                          = dev.FieldR( self.com, self.addr + 0x00204, 0, 32)
        self.buffEnd                        = dev.FieldR( self.com, self.addr + 0x00208, 0, 32)
        self.buffOvf                        = dev.FieldR( self.com, self.addr + 0x0020C, 0, 32)
        self.running                        = dev.FieldR( self.com, self.addr + 0x00210, 0, 32)
        self.started                        = dev.FieldR( self.com, self.addr + 0x00214, 0, 32)
        self.stopped                        = dev.FieldR( self.com, self.addr + 0x00218, 0, 32)
        self.addrPointer                    = dev.FieldR( self.com, self.addr + 0x0021C, 0, 32)
        self.transfSize                     = dev.FieldR( self.com, self.addr + 0x00220, 0, 32)
        self.fifoCnt                        = dev.FieldR( self.com, self.addr + 0x00224, 0, 32)

        self.memReady                       = dev.FieldR( self.com, self.addr + 0x01000, 0, 32)
        self.memError                       = dev.FieldR( self.com, self.addr + 0x01004, 0, 32)
        self.addrWidth                      = dev.FieldR( self.com, self.addr + 0x01020, 0, 32)
        self.dataBytes                      = dev.FieldR( self.com, self.addr + 0x01024, 0, 32)
        self.idBits                         = dev.FieldR( self.com, self.addr + 0x01028, 0, 32)
        self.alertL                         = dev.FieldR( self.com, self.addr + 0x01030, 0, 32)
        self.pg                             = dev.FieldR( self.com, self.addr + 0x01034, 0, 32)

        self.ddrRst                         = dev.Field( self.com, self.addr + 0x010FC, 0,  1)

    def loadSeq(self):
        """Arm general pulsed mode measurement run """

        self.threshold.set(128)
        self.en.set(0)
        self.en.set(1)
