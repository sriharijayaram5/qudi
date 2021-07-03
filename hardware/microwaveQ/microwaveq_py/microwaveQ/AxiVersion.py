from . import Device as dev
import struct


class AxiVersion(dev.Device):
    """System registers

        Attributes: 
            rfDelay -- delay rf generation in counting clock cycles
            lsDelay -- delay laser generation in counting clock cycles
            cntDelay0, 
            cntDelay1,
            cntDelay2 -- delay counting window in counting clock cycles 
                        (all cntDelay values must be equal
            rfLatency -- actual latency of the rf generation (default = 71)
    """

    def __init__(self,com,addr):
        super().__init__(com,addr)
        self.fpgaVersion    = dev.Field( self.com, self.addr + 0x00000, 0,32)
        self.fpgaReload     = dev.Field( self.com, self.addr + 0x00104, 0, 1)
        self.userReset      = dev.Field( self.com, self.addr + 0x0010C, 0, 1)
        self.gitHash        = dev.Memory(self.com, self.addr + 0x00600, 32)
        self.deviceDna      = dev.Memory(self.com, self.addr + 0x00700, 32)
        self.buildTag       = dev.Memory(self.com, self.addr + 0x00800, 32)
        self.sysMonTemp     = dev.FieldR(self.com, self.addr + 0x20400, 0,32)

    def reset(self):
        """Resets the FPGA"""
        self.userReset.set(1)

    def getDNA(self):
        """Reads the FPGA DNA

        Returns:
            dna -- 128-bit FPGA dna
        """
        dna_words = self.deviceDna.read(3)
        dna_words.reverse()
        dna = 0x0;
        for word in dna_words:
            dna = (dna << 32) | word;
        return dna

    def getBuildTag(self):
        """Reads the FPGA build tag registers

        Returns:
            build tag string
        """
        myString = ""
        build_words = self.buildTag.read(64)

        for word in build_words:
            bytes_object = struct.unpack('4B', struct.pack('>I', word))
            if bytes_object[3] != 0x00: myString += chr(bytes_object[3])
            if bytes_object[2] != 0x00: myString += chr(bytes_object[2])
            if bytes_object[1] != 0x00: myString += chr(bytes_object[1])
            if bytes_object[0] != 0x00: myString += chr(bytes_object[0])
            
        return myString

    def getGitHash(self):
        """Reads the FPGA git hash registers

        Returns:
            git hash string
        """
        git_words = self.gitHash.read(5)
        git_words.reverse()
        gitHash = 0x0;        
        for word in git_words:
            gitHash = (gitHash << 32) | word;

        return gitHash

    def getTemp(self):
        """Reads the FGPA temperature registers from system monitor - ADC value

        Returns:
            Temperature in degrees - formula from Xilinx ultrascale system monitor data sheet
        """
        adcVal = self.sysMonTemp.get()
        temp = (adcVal * 502.9098/ 2**16) - 273.8195

        return float("{:.3g}".format(temp))