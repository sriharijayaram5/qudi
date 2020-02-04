import time
from . import Device as dev
import ctypes

class RFWindow(dev.Device):
	"""RF pulse generation module
		Attributes: 
			high -- high value of the RF window 
			gain -- global gain 
			gainCompensation -- gain compensation setting
			rise -- rise transition of the RF window
			fall -- fall transition of the RF window
	"""

	def __init__(self, com, addr):
		super().__init__(com, addr)
		self.high				= dev.Field( self.com, self.addr + 0x0000, 0, 16)
		self.gain				= dev.Field( self.com, self.addr + 0x0004, 0, 16)
		self._testEn			= dev.Field( self.com, self.addr + 0x0008,31,  1)
		self._testGenerate		= dev.Field( self.com, self.addr + 0x0008,30,  1)
		self._testLen			= dev.Field( self.com, self.addr + 0x0008, 0, 30)
		self.gainCompensation	= dev.Field( self.com, self.addr + 0x000C, 0, 16)
		self.rise				= Transition(self.com, self.addr + 0x1000)
		self.fall				= Transition(self.com, self.addr + 0x1000)

	def configure(self,rise = [],high = 1.0,fall = []):
		"""configures RF window shape
		Keyword arguments:
			rise -- rise waveform list range [0:1] (default = empty list) 
			high -- hifg value of the window [0:1] (default = 1.0) 
			fall -- rise waveform list range [0:1] (default = empty list) 
		"""
		self.setHigh(high)
		self.rise.set(rise)
		self.fall.set(fall)

	def setHigh(self, arg=1.0):
		"""Set gain
		Keyword arguments:
			arg -- high value (default = 1)
		"""
		assert 0 <= arg <= 1
		self.logger.info(f"Setting waveform height to {arg}")

		self.high.set(round((2**15-1)*arg))

	def getHigh(self):
		"""Read high value of RF window 
		Returns:
			window high value inrange [0:1]
		"""
		return 1.0/(2**15-1) * self.high.get()

	def setGain(self, arg):
		"""Set gain
		Keyword arguments:
			arg -- gain (range [0:1])
		"""
		assert 0 <= arg <= 1
		self.logger.info(f"Setting gain to {arg}")

		self.gain.set(int(round((2**15-1)*arg)))

	def getGain(self):
		"""Read gain and convert to range [0:1]
		Returns:
			global gain (double)
		"""
		return 1.0/(2**15-1) * self.gain.get()

	def setGainCompensation(self, arg):
		"""Set gain compensation
		Keyword arguments:
			arg -- gain (range [0:1])
		"""
		assert 0 <= arg <= 1
		self.logger.info(f"Setting gain compensation {arg}")        

		self.gainCompensation.set(int(round((2**15-1)*arg)))

	def getGainCompensation(self):
		"""Read gain compensation and convert to range [0:1]
		Returns:
			global gain (double)
		"""
		return 1.0/(2**15-1) * self.gainCompensation.get()

	def genTestPulse(self, arg):
		"""Generate service mode RF pulse 
		Keyword arguments:
			arg -- pulse length in DAC clock cycles
		"""
		self.logger.info(f"Generate test pulse {arg}")

		self._testLen.set(arg)
		self._testGenerate.set(True)
		self._testEn.set(False)
		self._testEn.set(True)
		time.sleep(1)
		self._testEn.set(False)

	def startRF(self):
		"""Start service mode RF generation
		"""
		self.logger.info(f"Start RF")

		self._testLen.set(0x3fffffff)
		self._testGenerate.set(True)
		self._testEn.set(False)
		self._testEn.set(True)

	def stopRF(self):
		"""Stop service mode RF generation
		"""
		self.logger.info(f"Stop RF")

		self._testLen.set(0x3fffffff)
		self._testEn.set(False)
		self._testGenerate.set(False)

class Transition(dev.Device):
	def __init__(self,com,addr):
		super().__init__(com,addr)

		self.val		= dev.Memory( self.com, self.addr + 0x0400, 16)
		self.len		= dev.Field(  self.com, self.addr + 0x0000, 0, 32)

	def set(self, transition):
		"""Configure the RF window transition waveform

		Keyword arguments:
			transition -- a list of double samples consituting a transition
		"""
		l = len(transition)
		idx = list()
		for i in range(64):
			idx += [i, 64+i, 2*64+i, 3*64+i]

		tmp = [0 for _ in range(256)]
		for i, a in zip(idx, transition):
			tmp[i] = round((2**15-1)*a)

		self.val.write(tmp)
		self.len.set(l)

	def get(self):
		"""Readback the RF window transition waveform

		Returns:
			a list of double samples consituting a transition
		"""
		l = self.len.get() + 1
		idx = list()
		for i in range(64):
			idx += [i, 64+i, 2*64+i, 3*64+i]

		readBack = self.val.rawBurstRead(256)
		readBack16 = [ctypes.c_int16(r).value for r in readBack]

		getList = list()
		for i, _ in zip(idx, range(l)):
			getList.append(1.0/(2**15-1) * readBack16[i])
		return getList
