import struct
from enum import Enum

# NOTE: In SLAC documentation, SYN and non-SYN headers are considered different but both begin
# at the beginning of the segment. Since there is a common initial part, this code considers
# SYN and non-SYN headers to be only the differing parts following the common header.

CtlBitNames = ['BUSY', 'UNUSED1', 'UNUSED2', 'NUL', 'RST', 'EAC', 'ACK', 'SYN']

class CtlBitField:
    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            self.__setattr__(key, val)

    @classmethod
    def fromByte(cls, byte):
        bitDict = {CtlBitNames[i] : ((byte & (0x1 << i)) != 0) for i in range(8)}
        return CtlBitField(**bitDict)

    @classmethod
    def make(cls, *kargs):
        bitDict = {bitName : False for bitName in CtlBitNames}
        for bitName in kargs:
            bitDict[bitName] = True
        return CtlBitField(**bitDict)

    def toByte(self):
        byte = 0
        for i in range(8):
            byte |= (self.__getattribute__(CtlBitNames[i]) << i)

        return byte

    def toString(self):
        presentNames = [name for name in CtlBitNames if self.__getattribute__(name)]
        return "Ctl: '" + ' '.join(presentNames) + "'"


class ExtraSynBitField:
    def __init__(self, version=1, oneBit=1, chk=False, zeroBits=0):
        self.version = version
        self.oneBit = oneBit
        self.chk = chk
        self.zeroBits = zeroBits

    @classmethod
    def fromByte(cls, byte):
        return ExtraSynBitField(
            (byte & 0xf0) >> 4, (byte & 0x8) >> 3, (byte & 0x4) != 0, (byte & 0x3))

    def toByte(self):
        return (self.version << 4) | (self.oneBit << 3) | (int(self.chk) << 2) | self.zeroBits


class CommonHeader:
    def __init__(self, ctlBits=CtlBitField.make(), headerLength=0, seqNo=0, ackNo=0):
        self.ctlBits = ctlBits
        self.headerLength = headerLength
        self.seqNo = seqNo
        self.ackNo = ackNo

    @classmethod
    def fromRaw(cls, rawData):
        return CommonHeader(ctlBits = CtlBitField.fromByte(rawData[0]),
            headerLength = rawData[1], seqNo = rawData[2], ackNo = rawData[3])

    def toRaw(self):
        return bytes([self.ctlBits.toByte(), self.headerLength, self.seqNo, self.ackNo])

    def toString(self):
        return '; '.join(
            [self.ctlBits.toString(), 'seq: {}; ack: {}'.format(self.seqNo, self.ackNo)])


class NonSynHeader:
    def __init__(self, spare=0, checksum=0):
        self.spare = spare
        self.checksum = checksum

    @classmethod
    def fromRaw(cls, rawData):
        (spare, checksum) = struct.unpack_from('>HH', rawData)
        return NonSynHeader(spare, checksum)

    def toRaw(self):
        return struct.pack('>HH', self.spare, self.checksum)

    def toString(self):
        return ''


def calculateChecksum(data):
        checksum = 0
        data_len = len(data)
        if (data_len % 2) == 1:
            data_len += 1
            data += struct.pack('!B', 0)
        
        for i in range(0, len(data), 2):
            w = (data[i] << 8) + (data[i + 1])
            checksum += w

        checksum = (checksum >> 16) + (checksum & 0xffff)
        checksum = ~checksum & 0xffff
        return checksum


class SynHeader:
    def __init__(self, extraBitField=ExtraSynBitField(),
            maxOutstandingSegments=0, maxSegmentSize=0, retransmissionTimeout_s=0,
            cumAckTimeout_s=0, nullTimeout_s=0, maxRetransmissions=0, maxCumAcks=0,
            maxOutOfSeqAck=0, minusLog10timeoutUnit=0, connectionId=0, checksum=0):
        self.extraBitField = extraBitField
        self.maxOutstandingSegments = maxOutstandingSegments
        self.maxSegmentSize = maxSegmentSize
        self.retransmissionTimeout_s = retransmissionTimeout_s
        self.cumAckTimeout_s = cumAckTimeout_s
        self.nullTimeout_s = nullTimeout_s
        self.maxRetransmissions = maxRetransmissions
        self.maxCumAcks = maxCumAcks
        self.maxOutOfSeqAck = maxOutOfSeqAck
        self.minusLog10timeoutUnit = minusLog10timeoutUnit
        self.connectionId = connectionId
        self.checksum = checksum

    def toMachineTime(self, val_s):
        return int(val_s / 10.**(-self.minusLog10timeoutUnit))

    @classmethod
    def fromRaw(cls, rawData):
        extraBitField = ExtraSynBitField.fromByte(rawData[0])
        (maxOutstandingSegments, maxSegmentSize, retransmissionTimeout, cumAckTimeout,
            nullTimeout, maxRetransmissions, maxCumAcks, maxOutOfSeqAck, minusLog10timeoutUnit,
            connectionId, checksum) = struct.unpack_from('>BHHHHBBBBIH', rawData, offset=1)

        timeoutUnit_s = 10.**(-minusLog10timeoutUnit)

        return SynHeader(extraBitField, maxOutstandingSegments, maxSegmentSize,
            retransmissionTimeout * timeoutUnit_s, cumAckTimeout * timeoutUnit_s,
            nullTimeout * timeoutUnit_s, maxRetransmissions, maxCumAcks, maxOutOfSeqAck,
            minusLog10timeoutUnit, connectionId, checksum)

    def toRaw(self):
        return bytes([self.extraBitField.toByte()]) + \
            struct.pack('>BHHHHBBBBIH', self.maxOutstandingSegments, self.maxSegmentSize,
                self.toMachineTime(self.retransmissionTimeout_s),
                self.toMachineTime(self.cumAckTimeout_s),
                self.toMachineTime(self.nullTimeout_s), self.maxRetransmissions,
                self.maxCumAcks, self.maxOutOfSeqAck, self.minusLog10timeoutUnit,
                self.connectionId, self.checksum)

    def toString(self):
        return ('Version: {}, Chk: {}, maxOutstandingSegments: {}, maxSegmentSize: {}, ' + \
            'retransmissionTimeout_s: {}, cumAckTimeout_s: {}, nullTimeout_s: {}, ' + \
            'maxRetransmissions: {}, maxCumAcks: {}, maxOutOfSeqAck: {}, ' + \
            'minusLog10timeoutUnit: {}, connectionId: {}').format(self.extraBitField.version,
                self.extraBitField.chk, self.maxOutstandingSegments, self.maxSegmentSize,
                self.retransmissionTimeout_s, self.cumAckTimeout_s, self.nullTimeout_s,
                self.maxRetransmissions, self.maxCumAcks, self.maxOutOfSeqAck,
                self.minusLog10timeoutUnit, self.connectionId)


class SegmentType(Enum):
    Syn = 1
    NonSyn = 2


class Segment:
    def __init__(self,
            segmentType, commonHeader=CommonHeader(), specificHeader=None, payload=b''):
        self.segmentType = segmentType
        self.commonHeader = commonHeader

        if specificHeader is None:
            if segmentType == SegmentType.Syn:
                self.specificHeader = SynHeader()
            elif segmentType == SegmentType.NonSyn:
                self.specificHeader = NonSynHeader()
            else:
                assert False
        else:
            self.specificHeader = specificHeader

        self.payload = payload

    def calcChecksum(self):
        checkSumData = self.commonHeader.toRaw() + self.specificHeader.toRaw()[:-2]
        return calculateChecksum(checkSumData)

    def setChecksum(self):
        self.specificHeader.checksum = self.calcChecksum()

    def verifyChecksum(self):
        return self.specificHeader.checksum == self.calcChecksum()

    @classmethod
    def fromRaw(cls, rawData):
        commonHeader = CommonHeader.fromRaw(rawData)

        if commonHeader.ctlBits.SYN:
            segmentType = SegmentType.Syn
            payloadOffset = 24
            specificHeader = SynHeader.fromRaw(rawData[4:])
        else:
            segmentType = SegmentType.NonSyn
            payloadOffset = 8
            specificHeader = NonSynHeader.fromRaw(rawData[4:])

        return Segment(
            segmentType, commonHeader, specificHeader, payload=rawData[payloadOffset:])

    def toRaw(self):
        return self.commonHeader.toRaw() + self.specificHeader.toRaw() + self.payload

    def toString(self, payload=False):
        retStr = '{}; {}'.format(self.commonHeader.toString(), self.specificHeader.toString())
        if payload:
            retStr += '; Payload: {}'.format(self.payload)
        return retStr
