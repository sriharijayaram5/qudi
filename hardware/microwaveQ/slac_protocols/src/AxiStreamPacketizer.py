import struct
import copy
import zlib
import logging

from .rssi import Connection

# NOTE: The channel is encoded in the TDEST field of the header - here we use 'channel' and
# 'tdest' interchangeably.

logger = logging.getLogger(__name__)

class AxiStreamPacketHeader:
    def __init__(self, version=0x2, crcType=0, tuser=2, channel=0, tid=0, seq=0, sof=False):
        self.version = version
        self.crcType = crcType
        self.tuser = tuser
        self.channel = channel
        self.tid = tid
        self.seq = seq
        self.sof = sof

    @classmethod
    def fromRaw(cls, rawData):
        (versionAndCrc, tuser, channel, tid, seq, unused, sofByte) = \
            struct.unpack_from('<BBBBHBB', rawData)
        version = (versionAndCrc & 0xf)
        crcType = (versionAndCrc & 0xf0) >> 4
        sof = ((sofByte & 0x80) != 0)
        return AxiStreamPacketHeader(version, crcType, tuser, channel, tid, seq, sof)

    def toRaw(self):
        sofByte = 0x80 if self.sof else 0
        versionAndCrc = (self.crcType << 4) | self.version
        return struct.pack('<BBBBHBB', versionAndCrc, self.tuser, self.channel, self.tid,
            self.seq, 0, sofByte)

    def toString(self):
        return 'Version: {}, crcType: {}, TUSER: {}, Channel: {}, TID: {}, SEQ: {}, SOF: {}' \
            .format(self.version, self.crcType, self.tuser,
                self.channel, self.tid, self.seq, self.sof)

class AxiStreamPacketTail:
    def __init__(self, tuserLast=0, eof=False, lastByteCnt=8, crc=0):
        self.tuserLast = tuserLast
        self.eof = eof
        self.lastByteCnt = lastByteCnt
        self.crc = crc

    @classmethod
    def fromRaw(cls, rawData):
        (tuserLast, eofByte, lastByteCntShort, crc) = struct.unpack_from('<BBHI', rawData)
        lastByteCnt = (lastByteCntShort & 0xf)
        eof = ((eofByte & 0x1) != 0)
        return AxiStreamPacketTail(tuserLast, eof, lastByteCnt, crc)

    def toRaw(self):
        eofByte = 1 if self.eof else 0
        return struct.pack('<BBHI', self.tuserLast, eofByte, self.lastByteCnt, self.crc)

    def toString(self):
        return 'TUSER_LAST: {}, EOF: {}, LAST_BYTE_CNT: {}, CRC: 0x{:04x}' \
            .format(self.tuserLast, self.eof, self.lastByteCnt, self.crc)

class AxiStreamPacket:
    # This class stores the entire payload, which must have a length which is a multiple of 8
    # bytes. If a payload for which this is not the case is passed to the constructor, zero
    # padding bytes are added to the end. The number of valid bytes in the last 8-byte chunk
    # are always calculated and stored in self.tail.lastByteCnt. The valid portion of the
    # payload is available through getValidPayload().
    def __init__(self, header, fullPayload, tail):
        self.header = header
        self.fullPayload = fullPayload
        self.tail = tail

    def padPayload(self):
        # Pad data with zeroes to make its length a multiple of 8.
        if len(self.fullPayload) == 0:
            self.tail.lastByteCnt = 0
            paddingBytes = 0
        else:
            self.tail.lastByteCnt = (len(self.fullPayload) % 8)
            if self.tail.lastByteCnt == 0:
                self.tail.lastByteCnt = 8
            paddingBytes = 8 - self.tail.lastByteCnt

        self.fullPayload = self.fullPayload + bytes(paddingBytes)

    def calcCrc(self):
        crcType = self.header.crcType
        if crcType == 0:
            self.tail.crc = 0
            return
        elif crcType == 1:
            crcData = self.fullPayload
        elif crcType == 2:
            crcData = self.header.toRaw() + self.fullPayload + self.tail.toRaw()[:-4]

        self.tail.crc = struct.unpack('>I', struct.pack('<I', zlib.crc32(crcData)))[0]

    # This method returns the payload without any invalid final bytes.
    def getValidPayload(self):
        if len(self.fullPayload) == 0:
            return b''

        paddingBytes = 8 - self.tail.lastByteCnt
        return self.fullPayload[:len(self.fullPayload)-paddingBytes]

    @classmethod
    def fromRaw(cls, rawData):
        header = AxiStreamPacketHeader.fromRaw(rawData)
        tail = AxiStreamPacketTail.fromRaw(rawData[-8:])
        fullPayload = rawData[8:-8]
        return AxiStreamPacket(header, fullPayload, tail)

    def toRaw(self):
        return self.header.toRaw() + self.fullPayload + self.tail.toRaw()

    def toString(self, payload=False):
        retStr = '{}; {}'.format(self.header.toString(), self.tail.toString())
        if payload:
            retStr += '; Payload: {}'.format(self.fullPayload)
        return retStr

# Wraps the rssi connection, forwards connection callback, handles data received callback,
# buffers data until EOF, and forwards the channel thing. Actually should have a map between
# channels and callbacks.
class AxiStreamPacketConnection:
    def __init__(self, rssiConfig):
        self.rssi = Connection.Connection(rssiConfig)
        self.dataCbDict = {}
        self.partialPacket = {}

    def setChannelCallback(self, channelNum, cb):
        self.dataCbDict[channelNum] = cb
        self.partialPacket[channelNum] = b''

    def getConnectionState(self):
        return self.rssi.getConnectionState()

    def connect(self, ip, localPort, connCb):
        self.rssi.connect(ip, localPort, connCb, self.__dataCallback)

    def disconnect(self):
        self.rssi.disconnect()

    def __dataCallback(self, data):
        axiPacket = AxiStreamPacket.fromRaw(data)

        # COMMENT OUT SINCE IT OVERFLOWS THE LOGGER
        #logger.debug('Recvd ASP packet: ' + axiPacket.toString())

        channel = axiPacket.header.channel

        if not channel in self.dataCbDict:
            return

        if axiPacket.header.sof:
            self.partialPacket[channel] = axiPacket.getValidPayload()
        else:
            self.partialPacket[channel] += axiPacket.getValidPayload()

        if not axiPacket.tail.eof:
            return

        self.dataCbDict[channel](self.partialPacket[channel])

    def sendData(self, channel, data):
        # Deduce the maxPayloadSize from RSSI maxSegmentSize, reduced by the size of RSSI and
        # ASP headers and footers.
        maxPayloadSize = self.rssi.getMaxSegmentSize() - 24

        # Payload size also has to be a multiple of eight.
        maxPayloadSize &= ~0x7

        header = AxiStreamPacketHeader(channel=channel, crcType=2)
        tail = AxiStreamPacketTail()

        packets = [AxiStreamPacket(
            copy.deepcopy(header), data[i:i+maxPayloadSize], copy.deepcopy(tail))
                for i in range(0, len(data), maxPayloadSize)]

        packets[0].header.sof = True
        packets[-1].tail.eof = True

        for packet in packets:
            packet.padPayload()
            packet.calcCrc()

            # COMMENT OUT SINCE IT OVERFLOWS THE LOGGER
            #logger.debug('Sending ASP packet: ' + packet.toString())

            self.rssi.sendData(packet.toRaw())

    def closeAndJoinControlThread(self):
        return self.rssi.closeAndJoinControlThread()

    def waitForTasksOrInterruption(self):
        return self.rssi.waitForTasksOrInterruption()

    def interrupt(self):
        return self.rssi.interrupt()
