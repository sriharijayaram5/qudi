import time
import logging

from . import Segment

logger = logging.getLogger(__name__)


class ConnManager:
    def __init__(self):
        pass

    def connect(self, initLocalSeq, synHeader, sendFunc, connFinishedFunc):
        self.initLocalSeq = initLocalSeq
        self.localSynHeader = synHeader

        self.resends = -1

        self.sendFunc = sendFunc
        self.connFinishedFunc = connFinishedFunc

        self.__sendConnSegment()

    def __sendConnSegment(self):
        if self.localSynHeader.maxRetransmissions !=0 and \
                self.resends == self.localSynHeader.maxRetransmissions:
            logger.error('Max retransmissions reached.')
            self.connFinishedFunc(None, None, None)

        self.resends += 1
        self.nextResendTime = time.time() + self.localSynHeader.retransmissionTimeout_s

        ctlBits = Segment.CtlBitField.make('SYN')
        commonHeader = Segment.CommonHeader(
            ctlBits, headerLength=24, seqNo=self.initLocalSeq, ackNo=0)
        fullSegment = Segment.Segment(
            Segment.SegmentType.Syn, commonHeader, self.localSynHeader)

        # Send checksums even if not requested locally as we do not know how the remote side is
        # configured.
        fullSegment.setChecksum()

        self.sendFunc(fullSegment)

    def segmentReceived(self, segment):
        ctlBits = segment.commonHeader.ctlBits

        if not (ctlBits.SYN and ctlBits.ACK):
            logger.warning('Received non-SYN-ACK segment.')
            return

        if segment.commonHeader.ackNo != self.initLocalSeq:
            logger.warning('Received SYN-ACK segment with wrong ack number.')
            return

        if ctlBits.BUSY or ctlBits.RST:
            logger.error('Received SYN-ACK segment with BUSY or RST set.')
            self.connFinishedFunc(None, None, None)
            return

        # Check connection parameters, take minimum segmentSize.
        synHeader = segment.specificHeader
        synHeader.maxSegmentSize = \
            min(synHeader.maxSegmentSize, self.localSynHeader.maxSegmentSize)

        logger.info('Received successful SYN-ACK response.')
        self.connFinishedFunc(self.initLocalSeq, segment.commonHeader.seqNo, synHeader)

    def onControlPeriod(self):
        if time.time() >= self.nextResendTime:
            self.__sendConnSegment()
