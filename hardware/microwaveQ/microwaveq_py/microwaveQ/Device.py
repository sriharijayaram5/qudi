import logging

class Device:
	"""FPGA compoment template
	"""
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
		super().__init__(com,addr)
		self.bitoffs = bitoffs
		self.bitsize = bitsize
		self.dictionary = dictionary

	def set(self, data):
		""" Sets the value of the field
		
		Keyword arguments:
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

class FieldR(Field):

	def __init__(self,com,addr,bitoffs=0,bitsize=32):
		super().__init__(com,addr,bitoffs,bitsize)

	def set(self,data):
		assert False, "Writing to read-only register"

class FieldW(Field):

	def __init__(self,com,addr,bitoffs=0,bitsize=32):
		super().__init__(com,addr,bitoffs,bitsize)

	def get(self,data):
		assert False, "reading write-only register"

	def set(self,data):
		tmp = data << self.bitoffs
		self.com.write(self.addr, tmp)

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

