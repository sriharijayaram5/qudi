import struct
import logging

# All SRP packets have an identically structured header. Write requests and non-posted
# responses have a payload. Responses have a footer.

logger = logging.getLogger(__name__)


class SrpSupportField:
    def __init__(self, unalignedAccess=False, byteAccess=False, write=False, read=False):
        self.unalignedAccess = unalignedAccess
        self.byteAccess = byteAccess
        self.write = write
        self.read = read

    @classmethod
    def fromByte(cls, byte):
        suppFlags = [(byte & (0x1 << shift)) != 0 for shift in range(2, 6)]
        return SrpSupportField(*suppFlags)

    def toByte(self):
        return (int(self.unalignedAccess) << 2) | (int(self.byteAccess) << 3) | \
            (int(self.write) << 4) | (int(self.read) << 5)

    def toString(self):
        featureNames = ['unalignedAccess', 'byteAccess', 'write', 'read']
        presentNames = []
        for name in featureNames:
            if self.__getattribute__(name):
                presentNames.append(name)

        return ' '.join(presentNames) if len(presentNames) > 0 else 'none'


class SrpHeader:
    def __init__(self, version=0x3, opcode=0x3, supportField=SrpSupportField(),
            ignoreMemResp=False, prot=0, timeoutCnt=0, tid=0, addr=0, size=0):
        self.version = version
        self.opcode = opcode
        self.supportField = supportField
        self.ignoreMemResp = ignoreMemResp
        self.prot = prot
        self.timeoutCnt = timeoutCnt
        self.tid = tid
        self.addr = addr
        self.size = size

    @classmethod
    def fromRaw(cls, rawData):
        (version, opAccIgnByte, protByte, timeoutCnt, tid, addr, size) \
            = struct.unpack_from('<BBBBIQI', rawData)
        opcode = (opAccIgnByte & 0x3)
        supportField = SrpSupportField.fromByte(opAccIgnByte)
        ignoreMemResp = ((opAccIgnByte & 0x40) != 0)
        prot = ((protByte & 0xc0) >> 6)
        return SrpHeader(version, opcode, supportField, ignoreMemResp,
                prot, timeoutCnt, tid, addr, size)

    def toRaw(self):
        protByte = self.prot << 6
        opAccIgnByte = (int(self.ignoreMemResp) << 6) | self.supportField.toByte() | \
            self.opcode
        return struct.pack('<BBBBIQI', self.version, opAccIgnByte, protByte, self.timeoutCnt,
            self.tid, self.addr, self.size)

    def toString(self):
        return ('Version: {}, Opcode: {}, SupportField: {}, IgnoreMemResp: {}, Prot: {}, ' + \
                'TimeoutCnt: {}, Tid: {}, Addr: 0x{:08x}, Size: {}').format(self.version,
                self.opcode, self.supportField.toString(), self.ignoreMemResp, self.prot,
                self.timeoutCnt, self.tid, self.addr, self.size)


class SrpFooter:
    def __init__(self, memBusResp=0, timeout=False, eofe=False, frameError=False,
            verMismatch=False, reqError=False):
        self.memBusResp = memBusResp
        self.timeout = timeout
        self.eofe = eofe
        self.frameError = frameError
        self.verMismatch = verMismatch
        self.reqError = reqError

    @classmethod
    def fromRaw(cls, rawData):
        (memBusResp, flagByte) = struct.unpack_from('<BB', rawData)
        
        timeout =     ((flagByte & 0x01) != 0)
        eofe =        ((flagByte & 0x02) != 0)
        frameError =  ((flagByte & 0x04) != 0)
        verMismatch = ((flagByte & 0x08) != 0)
        reqError =    ((flagByte & 0x10) != 0)

        return SrpFooter(memBusResp, timeout, eofe, frameError, verMismatch, reqError)

    def toRaw(self):
        flagByte = (int(self.timeout) << 0) | (int(self.eofe) << 1) | \
            (int(self.frameError) << 2) | (int(self.verMismatch) << 3) | \
            (int(self.reqError) << 4)

        return struct.pack('<BBH', self.memBusResp, flagByte, 0)

    def toString(self):
        errNames = ['timeout', 'eofe', 'frameError', 'verMismatch', 'reqError']
        presentErrNames = []
        for errName in errNames:
            if self.__getattribute__(errName):
                presentErrNames.append(errName)

        errStr = ' '.join(presentErrNames)

        retStr = 'MemBusResp: {}'.format(self.memBusResp)
        if len(errStr) > 0:
            retStr += '; ERRORS: ' + errStr

        return retStr


class SrpPacket:
    def __init__(self, header=SrpHeader(), payload=b'', footer=None):
        self.header = header
        self.payload = payload
        self.footer = footer

    @classmethod
    def reqFromRaw(cls, rawData):
        header = SrpHeader.fromRaw(rawData)
        payload = rawData[20:]
        footer = None

        return SrpPacket(header, payload, footer)

    @classmethod
    def respFromRaw(cls, rawData):
        header = SrpHeader.fromRaw(rawData)
        payload = rawData[20:-4]
        footer = SrpFooter.fromRaw(rawData[-4:])

        return SrpPacket(header, payload, footer)

    def toRaw(self):
        serBytes = self.header.toRaw() + self.payload
        if self.footer is not None:
            serBytes += self.footer.toRaw()

        return serBytes

    def toString(self, payload=False):
        retStr = self.header.toString()
        if self.footer is not None:
            retStr += '; ' + self.footer.toString()
        if payload:
            retStr += '; Payload: {}'.format(self.payload)
        return retStr


# This just references an AxiStreamPacketConnection and a channel number, 
class SRPv3Connection:
    def __init__(self, axiPacketConnection, channelNum, packetCallback):
        self.channelNum = channelNum
        self.axiPacketConnection = axiPacketConnection
        self.axiPacketConnection.setChannelCallback(channelNum, self.__dataCallback)
        self.packetCb = packetCallback
        #self.__tid = random.randrange(2**32)
        self.__tid = 0x5a0d

    def __dataCallback(self, data):
        srpPacket = SrpPacket.respFromRaw(data)
        # COMMENT OUT SINCE IT OVERFLOWS THE LOGGER
        #logger.debug('Recvd SRP packet: ' + srpPacket.toString())
        self.packetCb(srpPacket)

    def sendReadReq(self, addr, size):
        header = SrpHeader(opcode=0x0, tid=self.__tid, addr=addr, size=(size-1))
        packet = SrpPacket(header)
        self.__sendPacket(packet)
        return

    def sendWriteReq(self, addr, data, posted=False):
        opcode = 0x2 if posted else 0x1
        header = SrpHeader(opcode=opcode, tid=self.__tid, addr=addr, size=(len(data)-1))
        packet = SrpPacket(header, data)
        self.__sendPacket(packet)
        return

    def __sendPacket(self, packet):
        # COMMENT OUT SINCE IT OVERFLOWS THE LOGGER
        #logger.debug('Sending SRP packet: ' + packet.toString(payload=True))
        self.__tid = (self.__tid + 1) % 2**32
        self.axiPacketConnection.sendData(self.channelNum, packet.toRaw())
