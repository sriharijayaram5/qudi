import socket
import threading
import recordtype
import logging
from collections import deque
from enum import Enum
import struct

from . import Segment

from . import DataQueue
from . import ConnManager

logger = logging.getLogger(__name__)

RemoteUdpPort = 8192


class ConnState(Enum):
	Connecting = 1
	Connected = 2
	Disconnected = 3


class CbType(Enum):
	ConnChange = 1
	DataReceived = 2


TaskItem = recordtype.recordtype('TaskItem', 'cbType payload')


# Set to UDP MTU.
BufSize = 2**16


class ControlThread(threading.Thread):
	def __init__(self, conn):
		super().__init__()
		self.conn = conn

	def run(self):
		return self.conn._Connection__controlThreadWorker()

# Utility function for slicing byte buffers.
def subslices(origIter, n):
	for i in range(0, len(origIter), n):
		yield origIter[i:i+n]


class Connection:
	def __init__(self, rssiConfig):
		self.__socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.__ip = None
		self.__port = None

		self.__socketPollPeriodMs = 1
		self.__socket.settimeout(self.__socketPollPeriodMs / 1000)

		self.__controlThread = ControlThread(self)

		self.__connChangeCb = None
		self.__dataCb = None

		self.__connParamsSynHeader = rssiConfig.toSynHeader()
		
		self.__lock = threading.RLock()
		self.__cv = threading.Condition(self.__lock)

		# The following members are all partially or fully protected by self.__lock.
		self.__connState = ConnState.Disconnected

		self.__taskQueue = deque()
		self.__interrupted = False

		self.__dataQueue = DataQueue.DataQueue()
		self.__connMgr = ConnManager.ConnManager()

	def connect(self, ip, localPort, connCb, dataCb):
		assert self.getConnectionState() == ConnState.Disconnected

		self.__ip = ip
		self.__localPort = localPort
		self.__connChangeCb = connCb
		self.__dataCb = dataCb

		self.__connState = ConnState.Connecting

		self.__socket.bind(('', self.__localPort))

		self.__controlThread.start()

	def __controlThreadWorker(self):
		# Initialize the connection manager.
		self.__connMgr.connect(
			0, self.__connParamsSynHeader, self.__send, self.__connFinished)

		while True:
			try:
				(rawData, address) = \
					self.__socket.recvfrom(self.__connParamsSynHeader.maxSegmentSize+8)
				# Firmware RSSI implementation occasionally appends 8 more bytes.
					
				# Raise warning if address not expected.
				if address != (self.__ip, RemoteUdpPort):
					logger.warning('Received unsolicited segment from {}:{}.'.format(*address))
					continue

				self.__processReadSegment(rawData)

			except (socket.timeout, ConnectionResetError):
				# The ConnectionResetError must be handled on Windows in case a previous send
				# has resulted in an ICMP port unreachable error, even though this is not a
				# problem for UDP.
				pass

			# Do periodic tasks.
			if self.__connState == ConnState.Disconnected:
				# If disconnected, quit this thread.
				logger.info('Exiting RSSI control thread.')
				return
			elif self.__connState == ConnState.Connecting:
				self.__connMgr.onControlPeriod()
			elif self.__connState == ConnState.Connected:
				self.__dataQueue.onControlPeriod()
			else:
				assert False

	# Called as a callback from __dataQueue and __connMgr.
	def __send(self, segment):

		with self.__lock:
			# COMMENT OUT SINCE IT OVERFLOWS THE LOGGER
			# logger.debug('Sending RSSI segment: ' + segment.toString())
			self.__socket.sendto(segment.toRaw(), (self.__ip, RemoteUdpPort))
		return True

	# Called as a callback from __connMgr.
	def __connFinished(self, initLocalSeq, initRemoteSeq, remoteSynHeader):
		assert self.__connState == ConnState.Connecting

		if initLocalSeq is None:
			self.__changeConnState(ConnState.Disconnected)
			return

		self.__connParamsSynHeader = remoteSynHeader

		self.__dataQueue.reset(initLocalSeq, initRemoteSeq, remoteSynHeader, self.__lock,
			self.__send, self.__onDataRecvd, self.__disconnect)

		self.__changeConnState(ConnState.Connected)

	def __changeConnState(self, newConnState):
		with self.__cv:
			self.__connState = newConnState
			self.__taskQueue.appendleft(TaskItem(CbType.ConnChange, newConnState))
			self.__cv.notifyAll()

	# __dataQueue callback.
	def __onDataRecvd(self, data):
		with self.__cv:
			self.__taskQueue.appendleft(TaskItem(CbType.DataReceived, data))
			self.__cv.notifyAll()

	# __dataQueue callback.
	def __disconnect(self):
		self.__changeConnState(ConnState.Disconnected)

	# This must only be called after a spurious disconnect or a disconnect request, otherwise
	# the join will hang.
	def closeAndJoinControlThread(self):
		# TODO: Add assertion this will not hang.
		self.__controlThread.join()
		self.__socket.shutdown(1)
		self.__socket.close()

	def __processReadSegment(self, rawData):
		try:
			segment = Segment.Segment.fromRaw(rawData)
		except struct.error:
			logger.warning('Received malformed RSSI segment.')
			return

		if self.__shouldVerifyChecksums() and not segment.verifyChecksum():
			logger.warning('Recvd RSSI segment with invalid checksum: {}' \
				.format(segment.toString()))
			return

		# COMMENT OUT SINCE IT OVERFLOWS THE LOGGER
		#logger.debug('Recvd RSSI segment: {}'.format(segment.toString()))

		# Dispatch segment depending on connection state.
		if self.__connState == ConnState.Disconnected:
			return
		elif self.__connState == ConnState.Connecting:
			self.__connMgr.segmentReceived(segment)
		elif self.__connState == ConnState.Connected:
			self.__dataQueue.segmentReceived(segment)
		else:
			assert False

	def __shouldVerifyChecksums(self):
		return self.__connParamsSynHeader.extraBitField.chk

	def waitForTasksOrInterruption(self):
		while True:
			currentTaskItem = None
			with self.__cv:
				self.__cv.wait_for(self.__tasksReadyOrInterrupted)
				if self.__interrupted:
					return
				if len(self.__taskQueue) > 0:
					currentTaskItem = self.__taskQueue.pop()
			
			# No longer locked at this point.
			if currentTaskItem is None:
				continue
			elif currentTaskItem.cbType == CbType.ConnChange:
				self.__connChangeCb(currentTaskItem.payload)
			elif currentTaskItem.cbType == CbType.DataReceived:
				self.__dataCb(currentTaskItem.payload)
			else:
				assert False

	# Meant to be called locked.
	def __tasksReadyOrInterrupted(self):
		return self.__interrupted or len(self.__taskQueue) > 0

	def getConnectionState(self):
		with self.__lock:
			return self.__connState

	def interrupt(self):
		with self.__cv:
			self.__interrupted = True
			self.__cv.notifyAll()

	def disconnect(self):
		# In a future version, we may support disconnecting while the connection has not yet
		# been established, but this is not supported at present.
		with self.__lock:
			if self.__connState == ConnState.Connected:
				self.__dataQueue.disconnect()
	
	# May only be called after connection has been established.
	def sendData(self, data):
		with self.__lock:
			assert self.__connState == ConnState.Connected
			dataSize = self.__connParamsSynHeader.maxSegmentSize - 8

			for segData in subslices(data, dataSize):
				self.__dataQueue.sendUserData(segData)

	def getMaxSegmentSize(self):
		return self.__connParamsSynHeader.maxSegmentSize
