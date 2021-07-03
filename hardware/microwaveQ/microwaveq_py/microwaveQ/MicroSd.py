from . import Device as dev
import struct


class MicroSd(dev.Device):
    """System registers

        Attributes: 
        customIp    -- IP to be used if micro SD card is present
        customMAC1  -- lower 32 bits of MAC address
        customMAC2  -- higer 16 bits of MAC address
    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.customIp       = dev.Field( self.com, self.addr + 0x00000, 0,32)
        self.customMAC1     = dev.Field( self.com, self.addr + 0x00004, 0,32)
        self.customMAC2     = dev.Field( self.com, self.addr + 0x00008, 0,32)

    def getIP(self):
        """Reads the FPGA custom IP

        Returns:
            IP 
        """
        myString = ""
        bytes_object = struct.unpack('4B', struct.pack('>I', self.customIp.get()))
        myString +=     str(bytes_object[3])
        myString += "."+str(bytes_object[2])
        myString += "."+str(bytes_object[1])
        myString += "."+str(bytes_object[0])

        return myString

    def setIP(self,  ip= "192.168.2.10"):
        """ Write Custom IP to FPGA

        parameters:
            ip -- ip string in format "XXX.XXX.XXX.XXX"
        """
        arrOfBytes = ip.split(".")
        reg = int(arrOfBytes[0])| int(arrOfBytes[1]) <<8 | int(arrOfBytes[2]) <<16 | int(arrOfBytes[3]) <<24
        self.customIp.set(reg)

    def getMAC(self):
        """Reads the FPGA custom MAC

        Returns:
            MAC 
        """
        myString = ""
        bytes_object1 = struct.unpack('4B', struct.pack('>I', self.customMAC1.get())) 
        bytes_object2 = struct.unpack('4B', struct.pack('>I', self.customMAC2.get()))
        myString +=     str(format(bytes_object1[3], '02x'))
        myString += ":"+str(format(bytes_object1[2], '02x'))
        myString += ":"+str(format(bytes_object1[1], '02x'))
        myString += ":"+str(format(bytes_object1[0], '02x'))
        myString += ":"+str(format(bytes_object2[3], '02x'))
        myString += ":"+str(format(bytes_object2[2], '02x'))

        return myString

    def setMAC(self,  mac= "00:0a:35:03:05:6b"):
        """ Write Custom MAC to FPGA

        parameters:
            mac -- mac string in format "xx:xx:xx:xx:xx:xx"
        """
        arrOfBytes = mac.split(":")
        reg1 = int(arrOfBytes[0], 16)| int(arrOfBytes[1], 16) << 8 | int(arrOfBytes[2], 16) << 16 | int(arrOfBytes[3], 16) << 24
        reg2 = int(arrOfBytes[4], 16)| int(arrOfBytes[5], 16) << 8 
        self.customMAC1.set(reg1)
        self.customMAC2.set(reg2)

    def write(self, address, data):
        """Write MicroSD data
            
        Keyword arguments:
            addr -- MicroSD device register address
            data -- MicroSD device register value
        """
        combAddr = self.addr + address
        self.com.write(combAddr, data)

    def read(self,address):
        """Read MicroSD data
            
        Keyword arguments:
            addr -- MicroSD device register address

        Return 
            MicroSD device register data
        """
        combAddr = self.addr + address
        return self.com.read(combAddr)
