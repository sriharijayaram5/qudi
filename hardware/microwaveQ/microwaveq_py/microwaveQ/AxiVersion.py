from . import Device as dev

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
	def __init__(self, com, addr):
		super().__init__(com, addr)
		self.fpgaVersion	= dev.Field( self.com, self.addr + 0x000, 0,32)
		self.fpgaReload		= dev.Field( self.com, self.addr + 0x104, 0, 1)
		self.userReset		= dev.Field( self.com, self.addr + 0x10C, 0, 1)
		self.deviceDna		= dev.Memory(self.com, self.addr + 0x700,32)

	def reset(self):
		""" Resets the FPGA """
		self.userReset.set(1)

	def getDNA(self):
		""" Reads the FGPA DNA

		Returns:
			dna -- 128-bit FPGA dna
		"""
		dna_words = self.deviceDna.read(3)
		dna_words.reverse()
		dna = 0x0;
		for word in dna_words:
			dna = (dna << 32) | word;
		return dna