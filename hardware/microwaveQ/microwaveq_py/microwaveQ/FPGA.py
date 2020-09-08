# external standard python modules
import math
import logging
import os

# external subcomponents from different (and 3rd party) packages
from src.MqConn import MqConn, BlockingReqResp
from src.rssi import Config as RssiConfig


class CommError(Exception):
    def __init__(self, desc):
        self.desc = desc


class FPGA:

    RETRY_COUNT = 10

    def __init__(self, ip, local_port, streamCb, cu_clk_freq):
        self.__ip = ip
        self.__axi_clk_freq = 125e6
        self.__cu_clk_freq = cu_clk_freq
        self.__cu_dac_mult = 4
        self.__dac_clk_freq = self.__cu_clk_freq * self.__cu_dac_mult
        self.logger = logging.getLogger(__name__)
        
        confPath = os.path.realpath(os.path.join(
            os.path.dirname(__file__), '..', 'config', 'protocol-config.yaml'))

        try:
            rssiConfig = RssiConfig.Config(confPath)
        except RssiConfig.VerificationError as e:
            logging.error('Error parsing config: {}'.format(e.desc))
            return
        self.conn = MqConn(rssiConfig,streamCb)
        self.conn.connectAndStartCallbackThread(ip, local_port)
        self.conn.waitConnected()

    def write(self, addr, data):
        if not isinstance(data,list):
            data = [data]
        self.__op_done = False
        data = self.intListToData(data)
        for i in range(self.RETRY_COUNT):
            status = self.conn.write(addr=addr, data=data, posted=False)
            if status == BlockingReqResp.Disconnected:
                logging.error('Disconnected, reconnecting (try {} of {}).'
                    .format(i+1, self.RETRY_COUNT))
                self.conn.reconnect()
            else:
                break
        else:
            logging.error('Maximum reconnect count exceeded, aborting.')
            # TODO: wait for retry. Call waitConnected or gtfo.

    def read(self, addr, length=1):
        self.__op_done = False
        for i in range(self.RETRY_COUNT):
            status, data = self.conn.read(addr=addr, size=length * 4)
            if status == BlockingReqResp.Disconnected:
                logging.error('Disconnected, reconnecting (try {} of {}).'
                    .format(i+1, self.RETRY_COUNT))
                self.conn.reconnect()
            else:
                break
        else:
            logging.error('Maximum reconnect count exceeded, aborting.')
            return []
            # TODO: wait for retry. Call waitConnected or gtfo.
            
        data = self.bytesToLEIntList(data)
        if length == 1:
            data = data[0]
        return data
    
    def convSecToAxiCyc(self, arg, convMeth = math.ceil):
        return convMeth(arg * self.__axi_clk_freq)  

    def convSecToCuCyc(self, arg, convMeth = math.ceil):
        return convMeth(arg * self.__cu_clk_freq)   

    def convSecToDacCyc(self, arg, convMeth = math.ceil):
        return convMeth(arg * self.__cu_clk_freq * self.__cu_dac_mult)  
    
    @staticmethod
    def bytesToLEIntList(data):
        return [int.from_bytes(data[i:i+4], byteorder='little') for i in range(0, len(data), 4)]

    @staticmethod
    def intListToData(intList):
        return b''.join([elem.to_bytes(4, byteorder='little') for elem in intList])
