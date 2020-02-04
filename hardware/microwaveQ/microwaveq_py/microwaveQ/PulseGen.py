from . import Device as dev


class PulseGen(dev.Device):
	"""Simulation pulse generation module"""
	def __init__(self, com, addr):
		super().__init__(com, addr)
		self.period = dev.Field(self.com, self.addr + 0x00, 0, 31)
		self.en     = dev.Field(self.com, self.addr + 0x00, 31,  1)

	def start(self, period=10000):
		"""Start pulse generation

		Keyword arguments:
			period -- Period of pulse generation (default = 10000)
		"""
		self.period.set(period)
		self.en.set(1)
	
	def stop(self):
		"""Stop pulse generation"""
		self.en.set(0)






