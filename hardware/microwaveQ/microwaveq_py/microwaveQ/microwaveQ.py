# external modules
import time
import re
from math import floor, ceil
import copy
import os.path
import numpy as np

# sub-components
from . import AxiVersion
from . import ControlUnit
from . import DelayCompensation as DLY
from . import Device as dev
from . import FPGA
from . import Gpio
from . import JesdTx
from . import PulseGen
from . import ResultStreamFilter as RSF
from . import RFController
from . import RFWindow
from . import SpiController
from . import TswAuxiliary


class MicrowaveQ(dev.Device):
	"""MicrowaveQ top level module
	Submodules:
		sys            -- FPGA dna / reset
		ctrl           -- measurement configuration module
		spiTrf         -- TRF3722 SPI contoller
		spiDac         -- DAC38J84 SPI contoller
		spiLmk         -- LMK04828  SPI contoller
		tswAux         -- DAC reset IO
		jesdTx         -- JesdTX FPGA core
		dlyComp        -- Delay compensation module
		rfctrl         -- RF Reconfiguration module
		rfpulse        -- RF pulse shape / generation module
		pixelClkSim    -- Pixel clock simulator
		apdPulseSim    -- APD pulse simulator
		resultFilter   -- Measurement filer
		gpio           -- GPIO module
	"""
	
	dev_id_trf = 0
	dev_id_dac = 1
	dev_id_lmk = 2
	dev_id_gain = 3

	def __init__(self, ip, local_port, streamCb, cu_clk_freq, conf_path=""):
		"""MicrowaveQ top level module
		
		Keyword arguments:
			ip          -- microwaveQ FPGA ip (192.168.2.10)
			local_port  -- microwaveQ local port 55555
			streamCb    -- received measurement data callback
			cu_clk_freq -- Counting clock frequency in Hz
			conf_path   -- configuration files path
		"""
		com		= FPGA.FPGA(ip, local_port, streamCb, cu_clk_freq)
		super().__init__(com, 0x10000000)
		
		self.streamCb = streamCb
		if conf_path == "":
			self._conf_path = os.path.abspath(os.path.dirname(__file__)) + "/files/"
		else:
			self._conf_path = conf_path
		
		self.sys			= AxiVersion.AxiVersion(self.com,		0x00000000)
		self.ctrl 	 		= ControlUnit.ControlUnit(self.com,		0x10000000)
		self.spiLmk			= SpiController.LMK(self.com, 			0x10100000)
		self.spiDac			= SpiController.DAC(self.com, 			0x10200000)
		self.spiTrf			= SpiController.TRF(self.com, 			0x10300000)
		self.tswAux 		= TswAuxiliary.TswAuxiliary(self.com,	0x10400000)

		self.jesdTx			= JesdTx.JesdTx(self.com, 				0x10600000)
		self.dlyComp        = DLY.DelayCompensation(self.com,		0x10700000)
		self.rfctrl			= RFController.RFController(self.com,	0x10800000)
		self.rfpulse		= RFWindow.RFWindow(self.com,			0x10900000)
																	
		self.apdPulseSim	= PulseGen.PulseGen(self.com, 			0x10B00000)
		self.pixelClkSim	= PulseGen.PulseGen(self.com, 			0x10C00000)
		self.resultFilter	= RSF.ResultStreamFilter(self.com,		0x10D00000)
		self.gpio			= Gpio.Gpio(self.com,					0x10E00000)

		self._default_trf_regs = list()
		# internal variables
		self._gain_compensation_table = np.array(None)

		# default TRF configuration
		self.configureTrfReference(8,122.8)
		self.configureTrfDefaultRegs()
		self.configureGainCompensation()


	def initialize(self):
		"""Initializes modules and establishes the connection to the RF board"""
		self.logger.info("Initialization started")
		self.spiLmk.configure()
		self.spiDac.configure()
		self.spiTrf.configure()
		
		self._executeSequence("LMK04828")
		self.jesdTx.configure()
		self.tswAux.resetDAC()
		self._executeSequence("DAC3XJ8X")
		self._seqResetJesdCore(self._conf_path + "resetJesdCore.seq")
		self.jesdTx.reset()
		self._seqTriggerLmk(self._conf_path + "trigger.seq")
		self._executeSequence("TRF3722")
		self.rfpulse.setGain(1.0)
		self.rfpulse.setHigh(1.0)
		self.rfpulse.stopRF()
		self.apdPulseSim.stop()
		self.pixelClkSim.stop()
		self.dlyComp.configure()
		self.resultFilter.set(0.1)
		self.logger.info("Initialization done")

	def disconnect(self):
		""" disconnects from the FPGA board
		follow this command with deletion of the microwaveQ object
		"""
		self.com.conn.disconnect()
		time.sleep(0.1)
		self.com.conn.closeAndJoinThreads()


	def _seqResetJesdCore(self, file_name=""):
		if file_name == "":
			file_name = self._conf_path + "resetJesdCore.seq"
		self._executeSequence("DAC3XJ8X", file_name)

	def _seqTriggerLmk(self, file_name=""):
		if file_name == "":
			file_name = self._conf_path + "trigger.seq"
		self._executeSequence("LMK04828", file_name)

	def _executeSequence(self, device, file_name=""):
		if file_name == "":
			file_name = self._conf_path + "baseline.seq"
		addrData = self._parseLog(file_name,device)
		for addr, data in addrData:
			if device == "TRF3722":
				self.spiTrf.write(addr, data)
			elif device == "DAC3XJ8X":
				self.spiDac.write(addr, data)
			elif device == "LMK04828":
				self.spiLmk.write(addr, data)
			else:
				assert False, "Unknown device"

	# def _simResult(self, data):
	# 	stream=bytearray()
	# 	for d in data:
	# 		for b in range(4):
	# 			stream.append(d & 0xFF)
	# 			d = d >> 8
	# 	self.streamCb(stream)


	def write(self, addr, data):
		"""Low level write

		Keyword arguments:
			addr -- address
			data -- data (list of integers or scalar integer)
		"""
		self.com.write(addr,data)

	def read(self, addr, length=1):
		"""Low level write

		Keyword arguments:
			addr   -- address
			length -- integer (default = 1)
		Returns:
			list of integers (if length > 1), scalar integer otherwise
		"""
		return self.com.read(addr,length)



	def configureCW(self, frequency, countingWindowLength):
		"""Configure CW measurement

		Keyword arguments:
			frequency -- frequency in Hz
			countingWindowLength -- length of a measurement in seconds (rounded up, greater or equal to 2 counting cycles)
		"""
		self.logger.info(f"Configuring CW: frequency {frequency}, counting window length {countingWindowLength}")
		self.ctrl.pulseLength.write([0xffffffff])
		self.ctrl.measurementLength.set(0)
		self.setFrequency(frequency)
		self.ctrl._setCountingWindowLength(countingWindowLength)
		self.ctrl._setCountingDelay(0)
		self.ctrl.countingMode.set('CW')

	def configureCW_PIX(self, frequency):
		"""Configure CW measurement

		Keyword arguments:
			frequency -- frequency in Hz
		"""
		self.logger.info(f"Configuring CW_PIX: frequency {frequency}")

		self.ctrl.pulseLength.write([0xffffffff])
		self.ctrl.measurementLength.set(0)
		self.setFrequency(frequency)
		self.ctrl.countingMode.set('CW_PIX')

	def configureCW_ESR(self, frequencies, countingWindowLength, countingDelay=0):
		"""Configure CW ESR measurement

		Keyword arguments:
			frequencies          -- list of frequencies in Hz
			countingWindowLength -- length of a measurement in seconds (rounded up, greater or equal to 2 counting cycles)
			countingDelay        -- length of delay between enabling the RF andf start of counting in secods (rounded up, must be at least 1 counting cycle)
		"""
		self.logger.info(f"Configuring CW_ESR: frequencies {frequencies}, countingWindowLength {countingWindowLength}, countingDelay {countingDelay}")

		# infinite RF generation
		self.ctrl.pulseLength.write([0xffffffff])
		# number of measurements is counted from 0
		self.ctrl.measurementLength.set(len(frequencies)-1)
		# calculate and download reconfiguration commands
		self._setFrequencies(frequencies)
		# counting length
		self.ctrl._setCountingWindowLength(countingWindowLength)
		# delay between RF and counting
		self.ctrl._setCountingDelay(countingDelay)
		self.ctrl.countingMode.set('CW_ESR')

	def configureRABI(self, frequency, countingWindowLength, laserExcitationLength, rfLaserDelayLength, pulseLengths, laserCooldownLength=0):
		"""Configure RABI measurement
		Keyword arguments:
			frequency             -- frequency in Hz
			countingWindowLength  -- length of counting window in seconds (rounded up to counting cycle, greater or equal to 2 counting cycles)
			laserExcitationLength -- length of laser exitation in seconds (rounded up to counting cycle, greater or equal to 3 counting cycles)
			rfLaserDelayLength    -- length of the delay between the end of the RF pulse and the start of the laser exitation (rounded up to counting cycle, greater or equal to 1)
			pulseLengths          -- list of lengths of the RF pulses in seconds (rounded up DAC cycle)
			laserCooldownLength	  -- length of the delay after laser excitation (default = 0)
		"""
		self.logger.info(f"Configuring RABI: frequency {frequency}, countingWindowLength {countingWindowLength}, laserExcitationLength {laserExcitationLength}, rfLaserDelayLength {rfLaserDelayLength}, pulseLengths {pulseLengths}")

		self.ctrl.measurementLength.set(len(pulseLengths)-1)
		self.setFrequency(frequency)
		self.ctrl._setRfLaserDelayLength(rfLaserDelayLength)
		self.ctrl._setLaserExcitationLength(laserExcitationLength)
		self.ctrl._setCountingWindowLength(countingWindowLength)
		self.ctrl._setPulseLength(pulseLengths)
		self.ctrl._setLaserCooldownLength(laserCooldownLength)
		self.ctrl.countingMode.set('RABI')

	def configurePULSED_ESR(self, frequencies, countingWindowLength, laserExcitationLength, rfLaserDelayLength, pulseLength, laserCooldownLength=0):
		"""Configure RABI measurement
		Keyword arguments:
			frequencies           -- list of frequencies in Hz
			countingWindowLength  -- length of counting window in seconds (rounded up to counting cycle, greater or equal to 2 counting cycles)
			laserExcitationLength -- length of laser exitation in seconds (rounded up to counting cycle, greater or equal to 3 counting cycles)
			rfLaserDelayLength    -- length of the delay between the end of the RF pulse and the start of the laser exitation (rounded up to counting cycle, greater or equal to 1)
			pulseLength           -- length of the RF pulse in seconds (rounded up to DAC cycle, greater or equal to 1)
			laserCooldownLength   -- length of the delay after laser excitation (default = 0)

		"""
		self.logger.info(f"Configuring RABI: frequencies {frequencies}, countingWindowLength {countingWindowLength}, laserExcitationLength {laserExcitationLength}, rfLaserDelayLength {rfLaserDelayLength}, pulseLength {pulseLength}")

		self.ctrl.measurementLength.set(len(frequencies)-1)
		self._setFrequencies(frequencies)
		self.ctrl._setRfLaserDelayLength(rfLaserDelayLength)
		self.ctrl._setLaserExcitationLength(laserExcitationLength)
		self.ctrl._setCountingWindowLength(countingWindowLength)
		self.ctrl._setPulseLength([pulseLength])
		self.ctrl._setLaserCooldownLength(laserCooldownLength)
		self.ctrl.countingMode.set('PULSED_ESR')

	def setFrequency(self, frequency):
		"""Sets the RF frequency
		Keyword arguments:
			freqency -- frequency in Hz
		"""
		self.logger.info(f"Set frequency {frequency}")
		#self._default_trf_regs = [dat << 5 for add, dat in addr_data]
		calculatedReg = self._calcTrfRegVal(self._default_trf_regs, frequency)
		for reg in calculatedReg:
			self.spiTrf.rawWrite(reg & 0xFFFFFFFF)

		val = self._calcGainCompensation(frequency)
		self.rfpulse.setGainCompensation(val)



	def configureTrfDefaultRegs(self, file_name=""):
		"""Sets default values of the TRF3722 registers. These values are a baseline during ESR reconfiguration.

		Keyword arguments:
			file_name -- path of the configuration file containing the default configuration
					 if left empty "defaultConfig.cfg" from configuration path is used
		"""
		if file_name == "":
			file_name = self._conf_path+"defaultConfig.cfg"

		addrData = self._getAddressData(file_name, "TRF3722")
		self._default_trf_regs = [addr | (1 << 3) | data << 5 for addr, data in addrData]

	def configureTrfReference(self,rdiv,f_ref):
		"""Set clock source options for TRF3722 (refer to datasheet)

		Keyword arguments:
			rdiv -- reference clock division ratio
			f_ref --- reference clock in MHz
		"""
		self.RDIV = rdiv
		self.f_ref = f_ref
		self.f_pfd = self.f_ref / self.RDIV


	def configureGainCompensation(self,file=""):
		"""Configure gain compensation coeficients 

		Keyword arguments:
			values -- numpy.array(2,n)  -- column 0: frequency, column 1: linear power (V)
		"""
		self.logger.info("Configuring gain compensation")
		if file == "":
			file=self._conf_path+"gainCompensationTable.tsv"
		
		file_name = file
		data = list()
		with open(file_name, 'r') as in_file:
			for line in in_file:
				data.append([float(x) for x in line.split("\t")])
			self._gain_compensation_table = np.array(data)              
			self._gain_compensation_table[:,1] = (max(self._gain_compensation_table[:,1]) / self._gain_compensation_table[:,1])
			self._gain_compensation_table[:,1] = self._gain_compensation_table[:,1]/max(self._gain_compensation_table[:,1])


	def _setFrequencies(self, frequencies):
		"""Calculates the register values for given frequencies and applies them.
		"""
		#self.logger.info(f"Setting frequencies to RFC {frequencies}")

		if type(frequencies) is not type(list()):
			frequencies = [frequencies]
		
		pointers, values = self._calculateRegs(self._default_trf_regs, frequencies)
		self.rfctrl.writeMemories(pointers, values)

	def startUp(self):
		self.com.write(0x1, 0x1)
		self.com.write(0x2, [0x21,0x22])

	def selectRFHigh(self):
		self.gpio.rfswitch.set(1)

	def selectRFLow(self):
		self.gpio.rfswitch.set(0)

	def _calcGainCompensation(self,f):
		return np.interp(f, self._gain_compensation_table[:,0], self._gain_compensation_table[:,1])

	def _calculateRegs(self, defaultTrfRegs, frequencies):
		tmp = "Calculating registers for frequencies " + ', '.join([str(f) for f in frequencies])
		#self.logger.info(tmp)

		new_regs_table = list()
		offset = 0
		for f in frequencies:
			# calcualte TRF reconfiguration commands
			calculated_register = self._calcTrfRegVal(defaultTrfRegs, f)
			for i in range(len(calculated_register)):
				calculated_register[i] |= (self.dev_id_trf << 32)
			
			# calculate and append gain compensation command
			g = self._calcGainCompensation(f)
			g = (self.dev_id_gain<<32) + int(round(g *(2**15-1)))
			calculated_register.append(g)
			
			new_regs_table.append(calculated_register)
			length = len(calculated_register)

		#self.logger.info("Removing configuration duplicates")

		compressed_regs_table = list()
		compressed_pointer_table = list()
		
		reg_last = [None]*7
		offset = 0
		for calculated_register in new_regs_table:
			compare = [not v1 == v2 for v1,v2 in zip(reg_last, calculated_register)]
			length = sum(compare)
			assert length > 0, 'two sequential configurations are the same'
			compressed_pointer_table.append([offset, length])
			offset += length

			diffRegs = list()
			for i, c in enumerate(compare):
				if c:
					reg_last[i] = calculated_register[i]
					diffRegs.append(calculated_register[i])
			compressed_regs_table.append(diffRegs)
		
		return compressed_pointer_table, compressed_regs_table

	def _calcTrfRegVal(self, default_reg, f):
		params_dict = self._calcTrfParams(f)
		reg = copy.deepcopy(default_reg)
		reg[0] = self._writeBits( reg[0], params_dict['RDIV'], 5, 18)
		reg[1] = self._writeBits( reg[1], params_dict['NINT'], 5, 21)
		reg[1] = self._writeBits( reg[1], params_dict['PLL_DIV_SEL'], 21, 23)
		reg[1] = self._writeBits( reg[1], params_dict['PRSC_SEL'], 23, 24)
		reg[2] = self._writeBits( reg[2], params_dict['NFRAC'], 5, 30)
		reg[5] = self._writeBits( reg[5], params_dict['LO_DIV_SEL'], 23, 25)
		reg[5] = self._writeBits( reg[5], params_dict['TX_DIV_SEL'], 27, 29)
		return reg

	def _calcTrfParams(self, fIn):
		f = fIn / 1e6  # Hz -> MHz

		assert (256.25 <= f) and (f <= 4100)

		RDIV = self.RDIV
		f_ref = self.f_ref

		if (2050 <= f) and (f <= 4100):
			LO_DIV_SEL = 0
			TX_DIV_SEL = 0
		elif (1025 <= f) and (f <= 2050):
			LO_DIV_SEL = 1
			TX_DIV_SEL = 1
		elif (512.5 <= f) and (f <= 1025):
			LO_DIV_SEL = 2
			TX_DIV_SEL = 2
		elif (256.25 <= f) and (f <= 512.5):
			LO_DIV_SEL = 3
			TX_DIV_SEL = 3
		LO_DIV = 2 ** LO_DIV_SEL
		TX_DIV = 2 ** TX_DIV_SEL

		f_VCO = f * TX_DIV

		PLL_DIV = ceil(f_VCO / 3000) 
		for _ in range(len([1, 2, 4])):
			assert PLL_DIV in [1, 2, 4]
			PLL_DIV_SEL = [1, 2, 4].index(PLL_DIV)

			NINT = floor(f_VCO * RDIV / f_ref / PLL_DIV)
			NFRAC = floor((f_VCO * RDIV / f_ref / PLL_DIV - NINT) * 2**25)

			if NINT >= 75:
				PRSC_SEL = 1
				P = 8
			else:
				PRSC_SEL = 0
				P = 4

			f_N = f_VCO / PLL_DIV / P
			if f_N >= 375:
				PLL_DIV *= 2
			else:
				break

		params_dict = {
			"RDIV": RDIV,
			"NINT": NINT,
			"NFRAC": NFRAC,
			"PRSC_SEL": PRSC_SEL,
			"PLL_DIV_SEL": PLL_DIV_SEL,
			"LO_DIV_SEL": LO_DIV_SEL,
			"TX_DIV_SEL": TX_DIV_SEL,
			}
		return params_dict

	@staticmethod
	def _writeBits(register, data, bit_start, bit_stop):
		assert 0 <= bit_start < bit_stop < 32
		assert data.bit_length() <= bit_stop - bit_start
		data <<= bit_start
		mask = sum([1 << i for i in range(bit_start, bit_stop)]) ^ 0xFFFFFFFF
		register &= mask   # clear bits
		register |= data   # write bits
		return register

	@staticmethod
	def _getAddressData(file_name, device):
		"""This method returns list of device parameters with elements [address, data]"""
		with open(file_name, 'r') as in_file:
			# get device
			device_found = False
			while True:
				line = in_file.readline()
				if not line:
					break 
				line = line.strip()
				if device == line:
					device_found = True
					break
			# save address and data for device in list and return it
			if device_found:
				addr_data = list()
				while True:
					line = in_file.readline()
					if not line:
						break # EOF - no more data
					line = line.strip()
					if line[:2] == '0x':
						dat = line.split(' ')
						addr_data.append([int(dat[0],16), int(dat[1],16)])
	
					else:
						break
				return addr_data

	@staticmethod
	def _parseLog(file_name, device = ""):
		addr_data = list()
		with open(file_name, 'r') as in_file:
			for line in in_file:
				device_found = re.search(device, line)
				if device_found:
					write_operation = re.search("Write Register", line)
					if write_operation:
						ad = re.findall(r"\[[^]]*\]", line)         # find all [val]
						ad = [re.sub(r"[^\w]", "", a) for a in ad]  # remove []
						ad = [int(a, 16) for a in ad]               # hex string to int
						addr_data.append(ad)
		return addr_data
