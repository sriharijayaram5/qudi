import logging


class Device:
    """FPGA compoment template."""

    def __init__(self, com, addr):
        """
        Keyword arguments:
            com -- FPGA Communication object
            addr -- device base address  
        """
        self.logger = logging.getLogger(__name__)
        self.com = com
        self.addr = addr
        #print(__name__,hex(addr))


class Field(Device):
    """Bitfield of a register
    
        Attributes: 
            bitoffs -- bit offset
            bitsize -- width of the data
        Methods:
            set,get
    """
    def __init__(self, com, addr, bitoffs=0, bitsize=32, dictionary={}):
        super().__init__(com, addr)
        self.bitoffs = bitoffs
        self.bitsize = bitsize
        self.dictionary = dictionary

    def set(self, data):
        """ Sets the value of the field
        
        Arguments:
            data -- value to be set
        """
        if len(self.dictionary) > 0:
            for key, val in self.dictionary.items():    # for name, age in dictionary.iteritems():  (for Python 2.x)
                if val == data:
                    data = key

        tmp = self.com.read(self.addr)
        tmp &= ~((2**self.bitsize-1) << self.bitoffs)
        tmp |= data << self.bitoffs
        
        self.com.write(self.addr, tmp)

    def get(self):
        """ Gets the value of the field
        
        Returns:
            data -- value of the field
        """
        tmp = self.com.read(self.addr)
        tmp =  (tmp >> self.bitoffs) & (2**self.bitsize-1)
        if len(self.dictionary) > 0:
            return self.dictionary[tmp]
        else:
            return tmp

    def __repr__(self):
        return (f'<{self.__module__}.{self.__class__.__name__} '
               f'object at {str(hex(id(self)))}. Use .get() to obtain '
               f'current value, .set(data) to set current value and .dictionary '
               f'to obtain the possible setter values, if present.>')


class FieldR(Field):

    def __init__(self, com, addr, bitoffs=0, bitsize=32, dictionary={}):
        super().__init__(com, addr, bitoffs, bitsize, dictionary)

    def set(self,data):
        assert False, "Writing to read-only register"

    def __repr__(self):
        return (f'<{self.__module__}.{self.__class__.__name__} '
               f'READ-ONLY object at {str(hex(id(self)))}. Use .get() '
               f'to obtain current value and .dictionary to obtain all '
               f'possible values, if present.>')
               

class FieldW(Field):

    def __init__(self, com, addr, bitoffs=0, bitsize=32, dictionary={}):
        super().__init__(com, addr, bitoffs, bitsize, dictionary)

    def get(self,data):
        assert False, "reading write-only register"

    def set(self,data):
        tmp = data << self.bitoffs
        self.com.write(self.addr, tmp)

    def __repr__(self):
        return (f'<{self.__module__}.{self.__class__.__name__} '
               f'WRITE-ONLY object at {str(hex(id(self)))}. Use '
               f'.set(data) to set current value and .dictionary '
               f'to obtain the possible setter values, if present.>')


class Memory(Device):

    def __init__(self,com,addr,bitsize=32):
        super().__init__(com,addr)
        self.bitsize = bitsize

    def write(self,data):
        a = 0
        for d in data:
            self.com.write(self.addr + a, d)
            a += 4

    def read(self,len):
        return [self.com.read(self.addr + a * 4) for a in range(len)]

    def __repr__(self):
        return (f'<{self.__module__}.{self.__class__.__name__} '
               f'object at {str(hex(id(self)))}. Use .read(data_length) '
               f'to obtain current memory value and .write(data) to set the '
               f'current memory value.>')
