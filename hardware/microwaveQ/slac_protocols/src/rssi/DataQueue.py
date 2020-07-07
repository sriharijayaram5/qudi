# external standard python modules
import time
import recordtype
import logging
from collections import deque

# subcomponents related to this package
from .Segment import Segment, SegmentType, CtlBitField, CommonHeader, NonSynHeader

# Terminology:
# - Local/remote Seq: the sequence numbers with which local/remote data is labelled,
#   respectively

# Thoughts on disconnection behaviour:
# Well, the specification is not clear, so on receiving an RST directly respond with RST-ACK,
# check queues and log if data was possibly not delivered.
# On receiving a user disconnect request, stop receiving user data, schedule the RST request as
# usual, stop scheduling new NUL packets, set the retransmit timeout to the minimum of current
# retransmit timeout and null timeout / 3, and quit either on data queue empty or RST-ACK
# (warn that queues not empty).

logger = logging.getLogger(__name__)

UnackedDataItem = recordtype.recordtype('UnackedDataItem',
    ['data', 'ctlBits', 'seqNo', 'retransmissionTime', 'resends'])

UnsentDataItem = recordtype.recordtype('UnsentDataItem', ['data', 'ctlBits'])

def incrementSeqNo(seqNo):
    return (seqNo + 1) % 2**8

def seqNoDifference(seqNo1, seqNo2):
    return (seqNo1 - seqNo2) % 2**8

def seqNoInRangeInclusive(rangeBegin, rangeEnd, seqNo):
    if rangeBegin < rangeEnd:
        return seqNo >= rangeBegin and seqNo <= rangeEnd
    else:
        return seqNo >= rangeBegin or seqNo <= rangeEnd

# Keeping track of data.
class DataQueue:
    def __init__(self):
        pass

    def reset(self, initLocalSeq, initRemoteSeq, synHeader, lock,
            sendFunc, dataRecvFunc, disconnFunc):
        self.lastLocalSeq = initLocalSeq
        self.lastAckedLocalSeq = initLocalSeq

        self.lastAckedRemoteSeq = initRemoteSeq
        self.lastRemoteSeq = initRemoteSeq

        self.unackedData = deque()
        self.unsentData = deque()

        self.maxCumAcks = synHeader.maxCumAcks
        self.maxOutstandingSegments = synHeader.maxOutstandingSegments
        self.maxRetransmissions = synHeader.maxRetransmissions

        self.disconnectRequested = False

        self.sendFunc = sendFunc
        self.dataRecvFunc = dataRecvFunc
        self.disconnFunc = disconnFunc

        self.lock = lock

        self.nullTimeout = synHeader.nullTimeout_s
        self.cumAckTimeout = synHeader.cumAckTimeout_s
        self.retrTimeout = synHeader.retransmissionTimeout_s
        self.calcChecksums = synHeader.extraBitField.chk

        self.remoteNeedsAck = False

        currTime = time.time()

        # Time after which unacked data will be acked if no other segments have been sent
        # before.
        self.cumAckTime = currTime + self.cumAckTimeout

        # Time after which a nul segment will be sent if no segments have been sent before.
        self.nullTime = currTime

    def segmentReceived(self, segment):
# - check remote seq is the next one expected
# -- if not, drop segment
# -- if yes, update lastRemoteDataSeq
# - if not dropped, check if new data acked, pop from unackedData, move from unsentData if
#   necessary and send.
# - if not sent, check difference between lastRemoteDataSeq and lastAckedRemoteSeq, send ack
# segment if appropriate. I suppose an empty one.
        if not self.__checkRecvSegmentValid(segment):
            return

        ctlBits = segment.commonHeader.ctlBits

        # Update local data queues.
        if ctlBits.ACK:
            segmentsSent = self.__updateAckQueues(segment.commonHeader.ackNo)
        else:
            segmentsSent = False

        # Check disconnection tasks.
        disconnected = self.__checkDisconnectionState(ctlBits)

        if len(segment.payload) > 0 and not ctlBits.RST:
            # Only increment remote seq number for DATA segments and not empty ACKs.
            with self.lock:
                self.lastRemoteSeq = segment.commonHeader.seqNo
                if not self.remoteNeedsAck:
                    self.cumAckTime = time.time() + self.cumAckTimeout
                self.remoteNeedsAck = True

            self.dataRecvFunc(segment.payload)

        if segmentsSent or disconnected:
            return

        if seqNoDifference(self.lastRemoteSeq, self.lastAckedRemoteSeq) > self.maxCumAcks:
            ctlBits = CtlBitField.make('ACK')
            segmentsSent = self.__sendNextSegment(b'', ctlBits)
        
        if not segmentsSent and incrementSeqNo(self.lastRemoteSeq) == self.lastAckedRemoteSeq:
            ctlBits = CtlBitField.make('ACK')
            if not self.__sendNextSegment(b'', ctlBits):
                logger.warning('Remote sequence number overflow may occur with next ' +
                    'received segment. Data corruption is possible.')

        return

    # Returns True if the segment is valid.
    def __checkRecvSegmentValid(self, segment):
        expectedRemoteSeqNo = incrementSeqNo(self.lastRemoteSeq)

        if segment.commonHeader.seqNo != expectedRemoteSeqNo:
            logger.warning('Expected remote sequence number {}, got {}.'
                .format(expectedRemoteSeqNo, segment.commonHeader.seqNo))
            return False

        # Check control bits valid.
        ctlBits = segment.commonHeader.ctlBits

        if ctlBits.NUL or ctlBits.SYN or (not ctlBits.ACK and not ctlBits.RST):
            logger.warning('Received segment with invalid control bit combination: {}' \
                    .format(ctlBits.toString()))
            return False

        return True

    # Returns whether segments have been sent.
    def __updateAckQueues(self, ackedLocalSeq):
        with self.lock:
            if not seqNoInRangeInclusive(
                    self.lastAckedLocalSeq, self.lastLocalSeq, ackedLocalSeq):
                logger.warning(('Received acknowledgment for sequence number {} with ' +
                    'unacknowledged sequence numbers ({}, {}].')
                    .format(ackedLocalSeq, self.lastAckedLocalSeq, self.lastLocalSeq))
                return False

            ackedSegs = seqNoDifference(ackedLocalSeq, self.lastAckedLocalSeq)
            self.lastAckedLocalSeq = ackedLocalSeq

            for i in range(ackedSegs):
                self.unackedData.popleft()

            if ackedSegs == 0 or len(self.unsentData) == 0:
                return False

            remainingSends = ackedSegs
            while len(self.unsentData) > 0 and remainingSends > 0:
                nextItemToSend = self.unsentData.popleft()
                self.__sendNextSegment(nextItemToSend.data, nextItemToSend.ctlBits)
                remainingSends -= 1

            return True

    # Returns whether we have disconnected.
    def __checkDisconnectionState(self, ctlBits):
        with self.lock:
            if self.disconnectRequested and self.__dataFlushed():
                logger.info('All submitted data has been acknowledged ' +
                    'after disconnect request, quitting.')
                self.disconnFunc()
                return True

            if not ctlBits.RST:
                return False

            if not self.__dataFlushed():
                logger.warning('Received RST segment with unacknowledged or unsent data, ' +
                    'quitting anyway.')
                self.disconnFunc()
                return True

    def __dataFlushed(self):
        return len(self.unackedData) == 0 and len(self.unsentData) == 0

    def disconnect(self):
        with self.lock:
            if self.disconnectRequested:
                logger.info('User disconnection request received while already disconnecting.')
                return

            # This will prevent accepting new user data and sending new NUL segments.
            self.disconnectRequested = True

            # Stop sending NUL segments to simplify detecting successful disconnection
            # conditions, but reduce retransmissionTimeout to retain keepalive behaviour. We
            # will have at least one segment in the queue, the RST segment.
            self.retrTimeout = min(self.retrTimeout, self.nullTimeout / 3)
            if len(self.unackedData) > 0:
                firstUnacked = self.unackedData[0]
                firstUnacked.retransmissionTime = \
                    min(firstUnacked.retransmissionTime, self.nullTime)

            # Schedule the RST segment.
            ctlBits = CtlBitField.make('ACK', 'RST')
            self.__sendNextSegment(b'', ctlBits)

    def __unackedDataFull(self):
        return (len(self.unackedData) == self.maxOutstandingSegments)

    def sendUserData(self, data):
        with self.lock:
            if self.disconnectRequested:
                logger.warning('Not sending user data as a disconnect has been requested.')
                return

        ctlBits = CtlBitField.make('ACK')
        self.__sendNextSegment(data, ctlBits)

    # Returns whether any segments were sent.
    def __sendNextSegment(self, data, ctlBits):
# on every data send:
# - if unackedData full, put into unsentData and return

        # Simplest to just lock this whole function
        with self.lock:
            isData = len(data) > 0

            emptyAck = not (isData or ctlBits.NUL)

            if self.__unackedDataFull() and (isData or ctlBits.RST):
                self.unsentData.append(UnsentDataItem(data, ctlBits))
                return False

            seqNo = incrementSeqNo(self.lastLocalSeq)

            # For DATA and NULL segments, increment localSequence number.
            if not emptyAck:
                self.lastLocalSeq = seqNo

            segment = self.__makeSegment(ctlBits, seqNo, data)

            # Do not wait for acknowledgment of empty ACKs and NULs.
            if not emptyAck:
                retransmissionTime = time.time() + self.retrTimeout
                self.unackedData.append(UnackedDataItem(
                    data, ctlBits, seqNo, retransmissionTime, resends=0))

            return self.__sendSegment(segment)

    def __sendSegment(self, segment):
# on every send:
# - reset nul timer
# - reset cumulative acknowledgment timeout

        with self.lock:
            currTime = time.time()

            self.remoteNeedsAck = False
            self.nullTime = currTime + self.nullTimeout / 3

            return self.sendFunc(segment)

    def __makeSegment(self, ctlBits, seqNo, data):
        with self.lock:
            commonHeader = CommonHeader(ctlBits, 8, seqNo, self.lastRemoteSeq)
            self.lastAckedRemoteSeq = self.lastRemoteSeq

        nonSynHeader = NonSynHeader(0, 0)

        fullSegment = Segment(SegmentType.NonSyn, 
                              commonHeader, 
                              nonSynHeader, 
                              data)

        if self.calcChecksums:
            fullSegment.setChecksum()

        return fullSegment

    def onControlPeriod(self):
# - check retransmission times, resend if necessary, if retransmission count reached close
#   connection
# - if no sends, check cumulative acknowledgment timer, send empty ack if necessary
# - if no sends, check nul timer, send nul frame if necessary

        with self.lock:
            currTime = time.time()

            # If the first segment is ready for retransmission, resend all of them.
            segmentsSent = False
            if len(self.unackedData) > 0 and self.unackedData[0].retransmissionTime <= currTime:
                if self.unackedData[0].resends == self.maxRetransmissions and \
                        self.maxRetransmissions != 0:
                    return self.disconnFunc()

                for unackedItem in self.unackedData:
                    segment = self.__makeSegment(
                        unackedItem.ctlBits, unackedItem.seqNo, unackedItem.data)
                    unackedItem.retransmissionTime = currTime + self.retrTimeout
                    unackedItem.resends += 1
                    segmentsSent = self.__sendSegment(segment)

            if self.remoteNeedsAck and self.cumAckTime <= currTime:
                ctlBits = CtlBitField.make('ACK')
                segmentsSent = self.__sendNextSegment(b'', ctlBits)

            if not segmentsSent and not self.disconnectRequested and self.nullTime <= currTime:
                ctlBits = CtlBitField.make('ACK', 'NUL')
                self.__sendNextSegment(b'', ctlBits)
