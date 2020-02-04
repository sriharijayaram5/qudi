import threading
import copy
import logging
from enum import Enum

from . import AxiStreamPacketizer
from . import SrpConn
from .rssi.Connection import ConnState

logger = logging.getLogger(__name__)


class BlockingReqType(Enum):
    Read = 1
    Write = 2
    WaitConn = 3

class BlockingReqResp(Enum):
    Success = 1
    Disconnected = 2

class MqCallbackThread(threading.Thread):
    def __init__(self, mqConn):
        super().__init__()
        self.mqConn = mqConn

    def run(self):
        return self.mqConn._MqConn__threadWorker()


class MqConn:
    def __initAxiConn(self):
        self.axiConn = AxiStreamPacketizer.AxiStreamPacketConnection(self.rssiConfig)
        self.srpConn = SrpConn.SRPv3Connection(self.axiConn, 0, self.__onSrpPacketRecvd)
        self.axiConn.setChannelCallback(1, self.streamCallback)

    def __init__(self, rssiConfig, streamCallback):
        self.rssiConfig = rssiConfig
        self.streamCallback = streamCallback

        self.__cv = threading.Condition()

        self.__callbackThread = None

    # Called locked.
    def __startBlockingReq(self, blockingReqType):
        assert self.currentBlockingReq is None
        self.currentBlockingReq = blockingReqType
        self.requestResponse = None

    def __signalReqDone(self, resp=BlockingReqResp.Success):
        assert self.currentBlockingReq is not None
        self.requestResponse = resp
        self.__cv.notifyAll()

    def connectAndStartCallbackThread(self, ip, localPort):
        assert self.__callbackThread is None

        self.__ip = ip
        self.__localPort = localPort

        self.__initAxiConn()

        self.currentBlockingReq = None
        self.requestResponse = None
        self.readData = b''

        self.__callbackThread = MqCallbackThread(self)
        self.__callbackThread.start()

    def __threadWorker(self):
        self.axiConn.connect(self.__ip, self.__localPort, self.__connectionCallback)
        while self.axiConn.getConnectionState() != ConnState.Disconnected:
            self.axiConn.waitForTasksOrInterruption()

        with self.__cv:
            if self.currentBlockingReq is not None:
                self.readData = b''
                self.__signalReqDone(BlockingReqResp.Disconnected)

        logger.info('Exiting callback thread.')

    def waitConnected(self):
        if self.isConnected():
            return True

        with self.__cv:
            self.__startBlockingReq(BlockingReqType.WaitConn)
            self.__cv.wait_for(self.__notifyFunc)
            self.currentBlockingReq = None

        return self.isConnected()

    def closeAndJoinThreads(self):
        self.__callbackThread.join()
        self.__callbackThread = None
        self.axiConn.closeAndJoinControlThread()
        # Delete objects pertaining to the RSSI connection.
        del(self.axiConn)
        del(self.srpConn)

    # Utility function, must only be called after a disconnect.
    def reconnect(self):
        self.closeAndJoinThreads()
        self.connectAndStartCallbackThread(self.__ip, self.__localPort)
        return self.waitConnected()

    def isConnected(self):
        return self.axiConn.getConnectionState() == ConnState.Connected

    def disconnect(self):
        return self.axiConn.disconnect()

    def __connectionCallback(self, connState):
        with self.__cv:
            if self.currentBlockingReq == BlockingReqType.WaitConn:
                self.__signalReqDone()

        if connState == ConnState.Disconnected:
            # Wake up the callback thread.
            self.axiConn.interrupt()

    def __onSrpPacketRecvd(self, srpPacket):
        with self.__cv:
            if self.currentBlockingReq == BlockingReqType.Read:
                self.readData = srpPacket.payload
            elif self.currentBlockingReq != BlockingReqType.Write:
                logger.warning('Received unsolicited SRP packet')
                return

            self.__signalReqDone()

    def __notifyFunc(self):
        return self.requestResponse is not None

    def read(self, addr, size):
        if not self.isConnected():
            return (BlockingReqResp.Disconnected, b'')
        
        with self.__cv:
            self.__startBlockingReq(BlockingReqType.Read)
            self.srpConn.sendReadReq(addr, size)
            self.__cv.wait_for(self.__notifyFunc)
            self.currentBlockingReq = None

            return (self.requestResponse, copy.copy(self.readData))

    def write(self, addr, data, posted=False):
        if not self.isConnected():
            return BlockingReqResp.Disconnected
        
        if posted:
            self.srpConn.sendWriteReq(addr, data, posted=True)
            return BlockingReqResp.Success

        with self.__cv:
            self.__startBlockingReq(BlockingReqType.Write)
            self.srpConn.sendWriteReq(addr, data)
            self.__cv.wait_for(self.__notifyFunc)
            self.currentBlockingReq = None
            return self.requestResponse
