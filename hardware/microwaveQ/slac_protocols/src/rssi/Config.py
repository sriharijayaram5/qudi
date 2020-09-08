import yaml
import numbers
import random

from .Segment import ExtraSynBitField, SynHeader

def toMachineUnits(naturalVal, minusLog10unit):
    return int(naturalVal / 10.**(-minusLog10unit))

class VerificationError(Exception):
    def __init__(self, desc):
        self.desc = desc

def checkIntRange(val, desc, min, max):
    if val < min or val > max:
        raise VerificationError('{} has value {}, not in valid range [{}, {}].' \
            .format(desc, val, min, max))

class Config:
    def __init__(self, confFilePath):
        with open(confFilePath, 'r') as f:
            conf = yaml.load(f, Loader=yaml.Loader)

        try:
            self.conf = conf['rssi']
        except KeyError:
            raise VerificationError('Config does not have a root \'rssi\' node.')

        # Generate random ID and cyclically increment it every time this Config object is used
        # for initiating a new connection, i.e., when toSynHeader is called.
        self.connectionId = random.randrange(2**32)

        self.verify()

    def getField(self, key):
        try:
            return self.conf[key]
        except KeyError:
            raise VerificationError('Config does not have item with key \'{}\'.'.format(key))

    def checkType(self, val, key, classinfo):
        if not isinstance(val, classinfo):
            raise VerificationError('Config item \'{}\' is not of type {}.' \
                .format(key, classinfo))

    def checkIntField(self, key, min, max):
        val = self.getField(key)
        self.checkType(val, key, int)
        desc = 'Config item \'{}\''.format(key)
        checkIntRange(val, desc, min, max)
        return val

    def checkTimeoutField(self, key, minusLog10unit):
        val = self.getField(key)
        self.checkType(val, key, numbers.Number)
        intVal = toMachineUnits(val, minusLog10unit)
        desc = 'Config item \'{}\' converted to machine units'.format(key)
        checkIntRange(intVal, key, 1, 0xffff)

    def verify(self):
        key = 'useChecksum'
        self.checkType(self.getField(key), key, bool)

        self.checkIntField('maxOutstandingSegments', 1, 0xff)
        self.checkIntField('maxSegmentSize', 1, 0xffff)
        self.checkIntField('maxRetransmissions', 0, 0xff)
        self.checkIntField('maxCumAcks', 1, 0xff)
        
        minusLog10unit = self.checkIntField('minusLog10timeoutUnit', 0, 0xf)

        self.checkTimeoutField('retransmissionTimeout_s', minusLog10unit)
        self.checkTimeoutField('cumAckTimeout_s', minusLog10unit)
        self.checkTimeoutField('nullTimeout_s', minusLog10unit)

    def toSynHeader(self):
        self.connectionId = (self.connectionId + 1) % (2**32)
        conf = self.conf
        extraBitField = ExtraSynBitField(version=0x1, chk=conf['useChecksum'])
        return SynHeader(extraBitField,
            maxOutstandingSegments  = conf['maxOutstandingSegments'],
            maxSegmentSize          = conf['maxSegmentSize'],
            retransmissionTimeout_s = conf['retransmissionTimeout_s'],
            cumAckTimeout_s         = conf['cumAckTimeout_s'],
            nullTimeout_s           = conf['nullTimeout_s'],
            maxRetransmissions      = conf['maxRetransmissions'],
            maxCumAcks              = conf['maxCumAcks'],
            minusLog10timeoutUnit   = conf['minusLog10timeoutUnit'],
            connectionId = self.connectionId)
