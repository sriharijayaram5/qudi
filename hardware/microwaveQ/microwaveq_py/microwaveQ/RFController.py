from . import Device as dev

class RFController(dev.Device):
	"""Delay compensation registers
		Attributes: 
			pointer -- memory containing offsets and lengths of reconfiguration segments
			device  -- memory containing id of the device used in reconfiguration command
			data	-- memory containing reconfiguration command

			delay	-- amount of delay after last reconfiguration word is applies in counting clock cycles
	"""
	def __init__(self,com,addr):
		super().__init__(com,addr)
		self.pointer		= dev.Memory( self.com, self.addr + 0x00040000, 32)
		self.devices		= dev.Memory( self.com, self.addr + 0x00080000,  2)
		self.data			= dev.Memory( self.com, self.addr + 0x000c0000, 32)

		self.delay			= dev.Field(  self.com, self.addr + 0x00000000, 0, 32)



	def writeMemories(self,pointers,values):
		"""Downloads reconfiguration segments to FPGA memory
		Keyword arguments:
			pointers -- bits  7: 0 - Number of operations required for submeasurement reconfiguration
						bits 23: 8 - Offset in the Device selection and Device data memories at which reconfiguration segment is stored
			values   -- bits 33:32 - device id
						bits 31: 0 - reconfiguration command
		"""

		self.logger.info("Applying calculated registers")

		tmp = list()
		for val in pointers:
			offset = val[0]
			length = val[1]
			tmp.append((offset << 8) | length-1)
		self.pointer.write(tmp)

		data = [val & 0xffffffff for sublist in values for val in sublist]
		self.data.write(data)
		devices = [val >> 32 for sublist in values for val in sublist]
		self.devices.write(devices)

	def setDelay(self, delay):
		"""Configure delay between last reconfiguration operation in ESR and resumption of measurement
		Used to wait for PLL locking (typically 70 us)
		Keyword arguments:
			delay -- value in seconds
		"""
		self.delay.set(self.com.convSecToAxiCyc(delay))


