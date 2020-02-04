import time
from . import Device as dev

class JesdTx(dev.Device):
	"""Simulation pulse generation module"""
	def __init__(self,com,addr):
		super().__init__(com,addr)
		self._enable  		=  dev.Field(self.com, self.addr + 0x00, 0, 8)
		self._subclass  	=  dev.Field(self.com, self.addr + 0x10, 0, 1)
		self._replaceEnable =  dev.Field(self.com, self.addr + 0x10, 1, 1)
		self._resetGTs 		=  dev.Field(self.com, self.addr + 0x10, 2, 1)
		self._clearErrors 	=  dev.Field(self.com, self.addr + 0x10, 3, 1)
		self._invertSync 	=  dev.Field(self.com, self.addr + 0x10, 4, 1)
		self._laneStatus	= [dev.Field(self.com, self.addr + 0x40 + 4 * i, 0, 1) for i in range(0,8)]
		self._dataStatus	= [dev.Field(self.com, self.addr + 0x40 + 4 * i, 1, 1) for i in range(0,8)]

	def configure(self):
		"""configures and enabled Jesd 
		"""
		self.logger.info(f"Configuring JESD lanes")
	
		self._enable.set(0xff)
		self._subclass.set(1)
		self._replaceEnable.set(1)
		self._resetGTs.set(0)
		self._clearErrors.set(1)
		self._invertSync.set(0)

	def reset(self):
		""" Resets Jesd lanes 
		"""
		self._resetGTs.set(1)
		time.sleep(1)
		self._resetGTs.set(0)

	def getLaneStatus(self):
		""" Gets lane status
			Returns:
				bitvector of lane statuses (True - OK, False - Error)
		"""
		tmp = 0x00;
		i = 0;
		for status in self._laneStatus:
			tmp |= status.get() << i
			i += 1
		return tmp

	def getDataStatus(self):
		""" Gets data tranmission status
			Returns:
				bitvector of data transmission statuses (True - OK, False - Error)
		"""
		tmp = 0x00;
		i = 0;
		for status in self._dataStatus:
			tmp |= status.get() << i
			i += 1
		return tmp

	





