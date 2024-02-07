# written by Thomas Oeckinghaus, 3. Physikalisches Institut, University of Stuttgart
# 2018-01-28 modified by Amit Finkler to be compatible with python 3.5
# 2024-01-30 modified by Sreehari Jayaram and Malik Lenger - functional combined with a qudi hardware file

from hardware.thirdparty.spectrum.pyspcm import *
import numpy as np
import time
import threading
import pylab
import copy
import pickle
from ctypes import *

class AWG:
    """ atm this class assumes only 2 channels per card """

    def __init__(self, _ip: object, _card_ids: object, _hub_id: object) -> object:
        self.ip = _ip
        self.number_of_cards = len(_card_ids)
        self.card_ids = _card_ids
        self.cards = list()
        for i in self.card_ids:
            self.cards.append(Card(self.ip, i))
        self.hub = Hub(_hub_id)
        self.data_list = [None, None, None, None, None, None, None, None, None, None]
        self.set_external_clock_input()
        self.init_all_channels()
        self.sequence = None
        self.save_data = True
        self.uploading = False
        self.temp_sine = ()  # for square cosine debugging purposes

    def set_external_clock_input(self):
        """Function to switch to external reference clock - assumed to be supplied in this case from the PulseStreamer as a 125MHz reference. 
        Ensure PulseStreamer is enabled witht this output before AWG init."""
        # c = self.cards[1]
        # c.set32(SPC_CLOCKMODE, SPC_CM_EXTREFCLOCK)
        # c.set32(SPC_REFERENCECLOCK, 125000000)
        # self.set_samplerate(1250000000)

        # Use this instead for switching to internal clock
        for c in self.cards:
            c.set32(SPC_CLOCKMODE, SPC_CM_INTPLL)

    def init_all_channels(self):
        self.set_selected_channels(0b1111)
        self.set_output(0b1111)
        self.sync_all_cards()
        self.set_loops(0)
        self.set_samplerate(1250000000)
        self.set_mode('single')

    def run_sequence(self, seq, clocking=0, fill_chans=[]):
        self.uploading = True
        ch = self.ch
        seq = eval(seq)
        if clocking:
            seq = self.fill_sequence(seq, clocking, fill_chans)
        return self.run_sequence_from_list(seq)

    def init_ext_trigger(self):
        c1 = self.cards[1]
        c0 = self.cards[0]
        c1.set_trigger_mode(0, 'pos_edge')
        c1.set_trigger_mode(1, 'pos_edge')

        c1.set_trigger_level0(0, 1300)
        c1.set_trigger_level0(1, 1300)
        c0.set_trigger_ormask(0, 0)
        c1.set_trigger_ormask(1, 1)

        c0.set32(SPC_TRIG_TERM, 1) # '0' is 1kOhm termination - '1' is 50Ohm termination for the trigger input
        c1.set32(SPC_TRIG_TERM, 1) # '0' is 1kOhm termination - '1' is 50Ohm termination for the trigger input

    def run_in_sequence_mode(self, seq):
        self.uploading = True
        self.stop()
        self.start_time = time.time()

        ch = self.ch

        self.init_sequence_mode(len(seq))

        for i, s in enumerate(seq):
            tmp_seq = eval(s[0])
            self.upload_wave_from_list(tmp_seq, segment_number=i)
            if i == len(seq) - 1:
                self.write_sequence_step(i, i, s[1], 0, 'always')
            else:
                self.write_sequence_step(i, i, s[1], i + 1, 'always')

        return self.start()

    def write_sequence_step(self, step_index, mem_segment_index, loops, goto, next_condition):
        print(step_index, mem_segment_index, loops, goto, next_condition)
        for card in self.cards:
            card.write_sequence_step(step_index, mem_segment_index, loops, goto, next_condition)

    def fill_sequence(self, seq, fill_to, fill_chans=[]):
        # get length of seq
        seq_length = 0
        for i, s in enumerate(seq):
            seq_length += s[1]
        add_length = (int(seq_length) / int(fill_to) + 1) * fill_to - seq_length
        tmp_seq = (fill_chans, add_length)
        seq.append(tmp_seq)
        return seq

    def init_sequence_mode(self, number_of_segments):
        for card in self.cards:
            card.init_sequence_mode(number_of_segments)

    def get_marker_data(self, channel, duration, sample_rate, start_position):
        length = int(duration * 1e-9 * sample_rate)
        return self.get_marker_samples(length)

    def get_marker_samples(self, samples):
        data = np.ones(samples, dtype=bool)
        return data

    def sync_all_cards(self):
        self.hub.sync_all_cards()

    def start(self):
        return self.hub.start_triggered()

    def start_enable_trigger(self):
        return self.hub.start_enable_trigger()

    def stop(self):
        return self.hub.stop()

    def reset(self):
        return self.hub.reset()

    def write_setup(self):
        return self.hub.write_setup()

    def enable_trigger(self):
        return self.hub.enable_trigger()

    def force_trigger(self):
        return self.hub.force_trigger()

    def disable_trigger(self):
        return self.hub.disable_trigger()

    def wait_trigger(self):
        return self.hub.wait_trigger()

    def wait_ready(self):
        return self.hub.wait_ready()

    def set_samplerate(self, rate):
        for c in self.cards:
            c.set_samplerate(rate)

    def get_samplerate(self):
        return self.cards[1].get_samplerate()

    def set_loops(self, loops):
        for c in self.cards:
            c.set_loops(loops)

    def set_mode(self, mode):
        for card in self.cards:
            card.set_mode(mode)

    def set_segment_size(self, segment_size):
        for card in self.cards:
            card.set_segment_size(segment_size)

    def set_memory_size(self, mem_size, is_sequence_segment=False):
        for card in self.cards:
            card.set_memory_size(mem_size, is_seq_segment=is_sequence_segment)

    def set_selected_channels(self, channels):
        """ set used channels. channels is binary with a flag (bit) for each channel: 0b0101 -> ch 0 & 2 active """
        self.cards[0].set_selected_channels(channels & 0b11)
        # This directly enable both channels on card_0

        c2_channels = 0
        if channels & 0b100:
            c2_channels += 0b01
        if channels & 0b1000:
            c2_channels += 0b10
        # This enable both channels on card_1 for channels 0b1100 or 0b1110 or 0b1101 or 0b1111.
        # Unclear why the both cards are handled differently. Many more straightforwad ways to do this.
        self.cards[1].set_selected_channels(c2_channels)

    def set_output(self, channels):
        """ enables/disables the output of the channels. channels is binary with a flag (bit) for each channel: 0b0101 -> ch 0 & 2 active  """
        self.cards[0].set_channel_output(0, channels & 0b0001)
        self.cards[0].set_channel_output(1, channels & 0b0010)
        self.cards[1].set_channel_output(0, channels & 0b0100)
        self.cards[1].set_channel_output(1, channels & 0b1000)

    def upload(self, data, data_size, mem_offset, is_buffered=True, is_sequence_segment=False):
        self.uploading = True
        # if not data0 == None or not data1 == None:
        self.start_upload_time = time.time()
        t1 = threading.Thread(target=self._run_upload,
                              args=(self.cards[0], [data[0], data[1], data[4], data[5], data[6]]),
                              kwargs={'mem_offset': mem_offset, 'data_size': data_size, 'is_buffered': is_buffered,
                                      'is_sequence_segment': is_sequence_segment})
        t2 = threading.Thread(target=self._run_upload,
                              args=(self.cards[1], [data[2], data[3], data[7], data[8], data[9]]),
                              kwargs={'mem_offset': mem_offset, 'data_size': data_size, 'is_buffered': is_buffered,
                                      'is_sequence_segment': is_sequence_segment})
        del data
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.finish_time = time.time()
        # self.uploading = False

        if not hasattr(self, 'start_time'):
            return

    def wait_upload(self):
        while self.uploading:
            time.sleep(0.1)

    def _run_upload(self, card, data, data_size, mem_offset, is_buffered=True, is_sequence_segment=False):
        # print 'Uploading to card ' + str(card.cardNo) + '...'
        res = card.upload(data_size, data[0], data[1], data[2], data[3], data[4], is_buffered=is_buffered,
                          mem_offset=mem_offset, block=True, is_seq_segment=is_sequence_segment)
        if res == 0:
            pass
            # print 'Upload to card ' + str(card.cardNo) + ' finished.'
        else:
            print('Error on card ' + str(card.cardNo) + ': ' + str(res))

    def close(self):
        for c in self.cards:
            c.close()
        self.hub.close()


class Hub():
    _regs_card_index = [SPC_SYNC_READ_CARDIDX0, SPC_SYNC_READ_CARDIDX1, SPC_SYNC_READ_CARDIDX2, SPC_SYNC_READ_CARDIDX3]

    def __init__(self, hub_no):
        self.handle = None
        self.hubNo = hub_no
        self.open()
        if self.handle == None:
            print("Star-Hub not found.".format(hub_no))
            return

        self.card_indices = list()
        self.number_of_cards = self.get_card_count()

        for i in range(self.number_of_cards):
            self.card_indices.append(self.get_card_of_index(i))

    def sync_all_cards(self):
        """The set value should be a mask for which cards are to be synced. 
        In this case, for 2 cards the mask will be 0b11 which enables both cards.
        """
        self.set32(SPC_SYNC_ENABLEMASK, (1 << self.number_of_cards) - 1)

    def open(self):
        address = "sync{0}".format(self.hubNo)
        self.handle = spcm_hOpen(create_string_buffer(bytes(address, 'utf8')))

    def close(self):
        spcm_vClose(self.handle)

    def start_triggered(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER | M2CMD_CARD_FORCETRIGGER)
        return self.chkError()

    def start_enable_trigger(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER)
        return self.chkError()

    def start(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_START)
        return self.chkError()

    def stop(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_STOP)
        return self.chkError()

    def reset(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_RESET)
        return self.chkError()

    def write_setup(self):
        """ writes all settings to the card without starting (start will also write all settings) """
        self.set32(SPC_M2CMD, M2CMD_CARD_WRITESETUP)
        return self.chkError()

    def enable_trigger(self):
        """ triggers will have effect """
        self.set32(SPC_M2CMD, M2CMD_CARD_ENABLETRIGGER)
        return self.chkError()

    def force_trigger(self):
        """ forces a single trigger event """
        self.set32(SPC_M2CMD, M2CMD_CARD_FORCETRIGGER)
        return self.chkError()

    def disable_trigger(self):
        """ all triggers will be ignored """
        self.set32(SPC_M2CMD, M2CMD_CARD_DISABLETRIGGER)
        return self.chkError()

    def wait_trigger(self):
        """ wait until the next trigger event is detected """
        self.set32(SPC_M2CMD, M2CMD_CARD_WAITTRIGGER)
        return self.chkError()

    def wait_ready(self):
        """ wait until the card completed the current run """
        self.set32(SPC_M2CMD, M2CMD_CARD_WAITREADY)
        return self.chkError()

    def get_card_count(self):
        """ returns the number of cards that are connected to the hub """
        res = self.get32(SPC_SYNC_READ_SYNCCOUNT)
        if self.chkError() == -1:
            return -1
        return res

    def get_card_of_index(self, index):
        """ returns the number (Card.cardNo) of the card that is connected to a index on the hub """
        reg = self._regs_card_index[index]
        res = self.get32(reg)
        if self.chkError() == -1:
            return -1
        return res

    def get_serial(self):
        res = self.get32(SPC_PCISERIALNO)
        if self.chkError() == -1:
            return -1
        return res

    def set32(self, register, value):
        spcm_dwSetParam_i32(self.handle, register, int32(value))

    def set64(self, register, value):
        spcm_dwSetParam_i64(self.handle, register, int64(value))

    def get32(self, register):
        res = int32(0)
        spcm_dwGetParam_i32(self.handle, register, byref(res))
        return res.value

    def get64(self, register):
        res = int64(0)
        spcm_dwGetParam_i64(self.handle, register, byref(res))
        return res.value

    def chkError(self):
        error_text = create_string_buffer(ERRORTEXTLEN)
        if (spcm_dwGetErrorInfo_i32(self.handle, None, None, error_text) != ERR_OK):
            print(error_text.value)
            return -1
        return 0


class Card():
    # lists that hold the registers of the same type but for different channels (0-3) or trigger channels (0-1)
    # register for Amplitde in mV
    _regs_amplitude = [SPC_AMP0, SPC_AMP1, SPC_AMP2, SPC_AMP3]
    _regs_output = [SPC_ENABLEOUT0, SPC_ENABLEOUT1, SPC_ENABLEOUT2, SPC_ENABLEOUT3]
    # Filter cut off for antialiasing (pg. 73 manual)
    _regs_filter = [SPC_FILTER0, SPC_FILTER1, SPC_FILTER2, SPC_FILTER3]
    _regs_stoplevel = [SPC_CH0_STOPLEVEL, SPC_CH1_STOPLEVEL, SPC_CH2_STOPLEVEL, SPC_CH3_STOPLEVEL]
    _regs_trigger_level0 = [SPC_TRIG_EXT0_LEVEL0, SPC_TRIG_EXT1_LEVEL0]
    _regs_trigger_mode = [SPC_TRIG_EXT0_MODE, SPC_TRIG_EXT1_MODE]
    _regs_offset = [SPC_OFFS0, SPC_OFFS1, SPC_OFFS2, SPC_OFFS3]

    # values for stoplevel. defines the output after a waveform is finished
    _vals_stoplevel = {
        'zero': SPCM_STOPLVL_ZERO,  # output 0 voltage
        'low': SPCM_STOPLVL_LOW,  # output low voltage
        'high': SPCM_STOPLVL_HIGH,  # output high voltage
        'hold': SPCM_STOPLVL_HOLDLAST  # hold the last voltage of the last sample
    }

    # output mode
    _vals_mode = {
        'single': SPC_REP_STD_SINGLE,
        'multi': SPC_REP_STD_MULTI,
        'gate': SPC_REP_STD_GATE,
        'singlerestart': SPC_REP_STD_SINGLERESTART,
        'sequence': SPC_REP_STD_SEQUENCE,
        'continuous': SPC_REP_STD_CONTINUOUS,
        'fifo_single': SPC_REP_FIFO_SINGLE,
        'fifo_multi': SPC_REP_FIFO_MULTI,
        'fifo_gate': SPC_REP_FIFO_GATE
    }

    # trigger modes
    _vals_trig_mode = {
        'pos_edge': SPC_TM_POS,
        'neg_edge': SPC_TM_NEG
    }

    _vals_sequence_step = {
        'on_trig': SPCSEQ_ENDLOOPONTRIG,
        'always': SPCSEQ_ENDLOOPALWAYS,
        'stop': SPCSEQ_END
    }

    def __init__(self, _ip, CardNo):
        self.ip = _ip
        self.handle = None
        self.cardNo = CardNo
        self.open()
        # print("Handle is " + str(self.handle))
        if self.handle == None:
            print("Spectrum Card No.{0} not found.".format(CardNo))
            return
        self.serial = self.get_serial()
        self.digital_markers_enabled = False
        self.init_markers(disable=False)
        self.temp_data = ()  # added this for debugging purposes and future plotting of data

    def init_markers(self, disable=False):
        """ set markers:
                mrkr0 -> bit 14 of a_ch0
                mrkr1 -> bit 15 of a_ch1
                mrkr2 -> bit 14 of a_ch1
                see pg126. https://spectrum-instrumentation.com/dl/dn_66x_manual_english.pdf
        """
        if disable:
            self.set32(SPCM_X0_MODE, SPCM_XMODE_DISABLE)
            self.set32(SPCM_X1_MODE, SPCM_XMODE_DISABLE)
            self.set32(SPCM_X2_MODE, SPCM_XMODE_DISABLE)
            self.digital_markers_enabled = False
        else:    
            mrkr_mode = (SPCM_XMODE_DIGOUT | SPCM_XMODE_DIGOUTSRC_CH0 | SPCM_XMODE_DIGOUTSRC_BIT14)
            self.set32(SPCM_X0_MODE, mrkr_mode)

            mrkr_mode = (SPCM_XMODE_DIGOUT | SPCM_XMODE_DIGOUTSRC_CH1 | SPCM_XMODE_DIGOUTSRC_BIT15)
            self.set32(SPCM_X1_MODE, mrkr_mode)

            mrkr_mode = (SPCM_XMODE_DIGOUT | SPCM_XMODE_DIGOUTSRC_CH1 | SPCM_XMODE_DIGOUTSRC_BIT14)
            self.set32(SPCM_X2_MODE, mrkr_mode)

            self.digital_markers_enabled = True

    def open(self):
        # print(str(self.ip))
        # print(str(self.cardNo))
        if 1:
            address = "TCPIP::{0}::INST{1}::INSTR".format(self.ip, self.cardNo)
        else:
            address = "{0}{1}".format(self.ip, self.cardNo)
        self.handle = spcm_hOpen(create_string_buffer(bytes(address, 'utf8')))
        # (str(self.handle))

    def close(self):
        spcm_vClose(self.handle)

    def start(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_START)
        return self.chkError()

    def stop(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_STOP)
        return self.chkError()

    def reset(self):
        self.set32(SPC_M2CMD, M2CMD_CARD_RESET)
        return self.chkError()

    def write_setup(self):
        """ writes all settings to the card without starting (start will also write all settings) """
        self.set32(SPC_M2CMD, M2CMD_CARD_WRITESETUP)
        return self.chkError()

    def enable_trigger(self):
        """ triggers will have effect """
        self.set32(SPC_M2CMD, M2CMD_CARD_ENABLETRIGGER)
        return self.chkError()

    def force_trigger(self):
        """ forces a single trigger event """
        self.set32(SPC_M2CMD, M2CMD_CARD_FORCETRIGGER)
        return self.chkError()

    def disable_trigger(self):
        """ all triggers will be ignored """
        self.set32(SPC_M2CMD, M2CMD_CARD_DISABLETRIGGER)
        return self.chkError()

    def wait_trigger(self):
        """ wait until the next trigger event is detected """
        self.set32(SPC_M2CMD, M2CMD_CARD_WAITTRIGGER)
        return self.chkError()

    def wait_ready(self):
        """ wait until the card completed the current run """
        self.set32(SPC_M2CMD, M2CMD_CARD_WAITREADY)
        return self.chkError()

    def get_serial(self):
        res = self.get32(SPC_PCISERIALNO)
        if self.chkError() == -1:
            return -1
        return res

    def set_wait_timeout(self, timeout):
        """ sets the timeout for all wait commands in ms. set to 0 to disable timeout """
        self.set32(SPC_TIMEOUT, timeout)
        return self.chkError()

    def get_wait_timeout(self):
        """ get the timeout of wait commands in ms """
        res = self.get32(SPC_TIMEOUT)
        if self.chkError() == -1:
            return -1
        return res

    def set_loops(self, loops):
        """ number of times the memory is replayed in a single event. set to 0 to have continuouly generation. """
        self.set32(SPC_LOOPS, loops)
        return self.chkError()

    def get_loops(self):
        res = self.get32(SPC_LOOPS)
        if self.chkError() == -1:
            return -1
        return res

    def set_trigger_level0(self, trig_channel, level):
        """ sets the lower trigger level of a trig channel in mV """
        reg = self._regs_trigger_level0[trig_channel]
        self.set32(reg, level)
        return self.chkError()

    def get_trigger_level0(self, trig_channel):
        reg = self._regs_trigger_level0[trig_channel]
        res = self.get32(reg)
        if self.chkError() == -1:
            return -1
        return res

    def set_trigger_mode(self, trig_channel, mode):
        reg = self._regs_trigger_mode[trig_channel]

        self.set32(reg, self._vals_trig_mode[mode])
        return self.chkError()

    def get_trigger_mode(self, trig_channel):
        reg = self._regs_trigger_mode[trig_channel]
        res = self.get32(reg)

        # get the name of the result from the trigger mode dictionary
        for key in self._vals_trig_mode.keys():
            if self._vals_trig_mode[key] == res:
                res = key

        if self.chkError() == -1:
            return -1
        return res

    def set_trigger_ormask(self, trig0_active, trig1_active):
        """ adds/removes the given trigger channel to/from the TRIG_ORMASK of the card (see manual for details) """
        reg = SPC_TRIG_ORMASK

        com = 0
        if trig0_active:
            com += SPC_TMASK_EXT0
        if trig1_active:
            com += SPC_TMASK_EXT1

        self.set32(reg, com)
        return self.chkError()

    def get_trigger_in_ormask(self, trig_channel):
        reg = SPC_TRIG_ORMASK

        res = self.get32(reg)
        if self.chkError() == -1:
            return -1

        if trig_channel == 0:
            com = SPC_TMASK_EXT0
        elif trig_channel == 1:
            com = SPC_TMASK_EXT1
        else:
            print('Unknown channel {0} in get_trigger_in_ormask.'.format(trig_channel))
            return -1

        return (res & com > 0)

    def set_triggered_channels_ormask(self, channels):
        """ sets channels that react to the trigger ormask.
            Give channels as binary with flags for single channel:
            0b111 -> channel 0,1,2 active
            0b100 -> channel 2 active
        """
        self.set32(SPC_TRIG_CH_ORMASK0, channels)
        return self.chkError()

    def get_state(self):
        res = self.get32(SPC_M2STATUS)
        if self.chkError() == -1:
            return -1
        if res & M2STAT_CARD_READY:
            return 'Ready'
        elif res & M2STAT_CARD_TRIGGER:
            return 'First trigger has been detected.'
        else:
            return 'Unknown state'

    def get_datatransfer_state(self):
        res = self.get32(SPC_M2STATUS)
        if self.chkError() == -1:
            return -1
        if res & M2STAT_DATA_END:
            return 'Data transfer finished.'
        elif res & M2STAT_DATA_ERROR:
            return 'Error during data transfer.'
        elif res & M2STAT_DATA_OVERRUN:
            return 'Overrun occured during data transfer.'
        else:
            return 'Unknown state'

    def set_memory_size(self, mem_size, is_seq_segment=False):
        """ set the amount of memory that is used for operation. Has to be set before data transfer to card. """
        if is_seq_segment:
            self.set32(SPC_SEQMODE_SEGMENTSIZE, mem_size)
        else:
            self.set32(SPC_MEMSIZE, mem_size)
        return self.chkError()

    def get_memory_size(self):
        res = self.get32(SPC_MEMSIZE)
        if self.chkError() == -1:
            return -1
        return res

    def upload(self, number_of_samples, data=None, data1=None, marker0_data=None, marker1_data=None, marker2_data=None,
               is_buffered=False, mem_offset=0, block=False, is_seq_segment=False):
        """ uploads data to the card.
        Values in 'data' range in int16.
        Values in marker data can only be 0 or 1

        Make sure, that the initialization of the digital markers in init_marker and the bit depth and marker_data fit together.
        """

        new_samples = number_of_samples
        if self.digital_markers_enabled:
            data //= 4 #to reduce the analog data bit depth such that the digital samples can be the MSBs. see pg 126 of https://spectrum-instrumentation.com/dl/dn_66x_manual_english.pdf
            data1 //= 4 #to reduce the analog data bit depth such that the digital samples can be the MSBs. see pg 126 of https://spectrum-instrumentation.com/dl/dn_66x_manual_english.pdf
        # a_ch0 is reduced in bit depth similar to a_ch1 althought not necessary but just to have a an identical bit depth. 15th bit of a_ch0 is completely unused.
        # set the commands that are used for the data transfer
        if block:
            com = M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA
        else:
            com = M2CMD_DATA_STARTDMA

        used_channels = self.get_selected_channels_count()
        bytes_per_sample = self.get_bytes_per_sample()

        # set the amount of memory that will be used
        if not is_buffered:
            while (not (new_samples % 32 == 0)) or (is_seq_segment is True and new_samples < 192):
                new_samples += 1

            self.set_memory_size(new_samples, is_seq_segment=is_seq_segment)

        # set the buffer
        BufferSize = uint64(new_samples * bytes_per_sample * used_channels)
        pvBuffer = create_string_buffer(BufferSize.value)
        pnBuffer = np.zeros(new_samples * used_channels, dtype=np.int16)

        pnBuffer[0:number_of_samples * used_channels:used_channels] = data[0:number_of_samples]
        if self.digital_markers_enabled:
            pnBuffer[0:number_of_samples * used_channels:used_channels] += marker0_data[0:number_of_samples] * 2 ** 14
        del data
        del marker0_data    
        pnBuffer[1:number_of_samples * used_channels:used_channels] = data1[0:number_of_samples]
        if self.digital_markers_enabled:
            pnBuffer[1:number_of_samples * used_channels:used_channels] += marker1_data[0:number_of_samples] * 2 ** 15 * -1 # since this is the MSB being equal to -32768. Positive 32768 is already overflow
            pnBuffer[1:number_of_samples * used_channels:used_channels] += marker2_data[0:number_of_samples] * 2 ** 14
        del data1    
        del marker1_data
        del marker2_data
   
        pvBuffer.raw = pnBuffer.tostring()

        # define the data transfer
        spcm_dwDefTransfer_i64(self.handle, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, uint32(0), pvBuffer,
                               uint64(mem_offset * used_channels * bytes_per_sample), BufferSize)

        # execute the transfer
        self.set32(SPC_M2CMD, com)
        if block:
            del pnBuffer, pvBuffer
        err = self.chkError()
        # print err
        return err  # self.chkError()

    # @profile
    def upload_old(self, number_of_samples, data=None, data1=None, marker0_data=None, marker1_data=None, marker2_data=None,
               is_buffered=False, mem_offset=0, block=False, is_seq_segment=False):
        """ uploads data to the card.
        Values in 'data' can not exceed -1.0 to 1.0.
        Values in marker data can only be 0 or 1

        If marker_data parameters are all None the marker outputs will be disabled.

        PS: the current version uses a fixed setting for the markers. Therefore all marker and channels are used
            all the time, whether they output data or not. This makes the code simpler but also leads to
            unneccesary upload of zeros...
        """

        new_samples = number_of_samples
        # print(data)
        data //= 2
        data1 //= 4

        # set the commands that are used for the data transfer
        if block:
            com = M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA
        else:
            com = M2CMD_DATA_STARTDMA

        used_channels = self.get_selected_channels_count()
        bytes_per_sample = self.get_bytes_per_sample()

        # set the amount of memory that will be used
        if not is_buffered:
            while (not (new_samples % 32 == 0)) or (is_seq_segment is True and new_samples < 192):
                new_samples += 1

            self.set_memory_size(new_samples, is_seq_segment=is_seq_segment)

        # set the buffer
        BufferSize = uint64(new_samples * bytes_per_sample * used_channels)
        pvBuffer = create_string_buffer(BufferSize.value)
        pnBuffer = np.zeros(new_samples * used_channels, dtype=np.int16)

        pnBuffer[0:number_of_samples * 2:2] = data[0:number_of_samples]
        pnBuffer[0:number_of_samples * 2:2] += np.ma.masked_where(data[0:number_of_samples] < 0,
                                                                  data[0:number_of_samples], copy=False).mask * 2 ** 15
        del data
        del marker0_data

        pnBuffer[1:number_of_samples * 2:2] = data1[0:number_of_samples]
        pnBuffer[1:number_of_samples * 2:2] += np.ma.masked_where(data1[0:number_of_samples] < 0,
                                                                  data1[0:number_of_samples], copy=False).mask * 2 ** 14
        del data1
        del marker1_data
        del marker2_data

        pvBuffer.raw = pnBuffer.tostring()


        # define the data transfer
        spcm_dwDefTransfer_i64(self.handle, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, uint32(0), pvBuffer,
                               uint64(mem_offset * used_channels * bytes_per_sample), BufferSize)
        # execute the transfer
        self.set32(SPC_M2CMD, com)
        if block:
            del pnBuffer, pvBuffer
        err = self.chkError()
        return err  # self.chkError()

    def init_sequence_mode(self, step_count):
        """ Sets the mode to sequence and set the maximum number of segments in the memory (max number of steps). """
        # get the maximum segments value (only power of two is allowed)
        max_segments = 0
        for i in range(16):
            if step_count <= 1 << i:
                max_segments = 1 << i
                break

        self.set_mode('sequence')
        self.set32(SPC_SEQMODE_MAXSEGMENTS, max_segments)
        self.set32(SPC_SEQMODE_STARTSTEP, 0)

    def set_segment_size(self, size):
        self.set32(SPC_SEGMENTSIZE, size)
        return self.chkError()

    def set_current_segment(self, index):
        self.set32(SPC_SEQMODE_WRITESEGMENT, index)

    def write_sequence_segment(self, mem_segment_index, data0=None, data1=None, mrkr0=None, mrkr1=None, mrkr2=None):
        """ Creates a memory segment that can be used for a sequence step """

        # select memory segment
        self.set32(SPC_SEQMODE_WRITESEGMENT, mem_segment_index)

        self.upload(data0, data1, mrkr0, mrkr1, mrkr2, is_segment=True)

        return self.chkError()

    # def write_sequence_segment(self, step_index, mem_segment_index, loops, goto, next_condition, data0=None, data1=None, mrkr0=None, mrkr1=None, mrkr2=None):
    #     """ Creates a memory segment that can be used for a sequence step """
    #
    #     #select memory segment
    #     self.set32(SPC_SEQMODE_WRITESEGMENT, mem_segment_index)
    #
    #     self.upload(data0, data1, mrkr0, mrkr1, mrkr2, is_segment=True)
    #
    #     # self.define_sequence_step(step_index, mem_segment_index, loops, goto, next_condition)
    #
    #     return self.chkError()

    def write_sequence_step(self, step_index, mem_segment_index, loops, goto, next_condition):
        """ Writes an entry into the the sequence memory of the card (does not upload data to the card). """
        val = int(mem_segment_index) | int(goto) << 16 | int(loops) << 32 | self._vals_sequence_step[
            next_condition] << 32
        self.set64(SPC_SEQMODE_STEPMEM0 + step_index, val)

        return self.chkError()

    def get_bytes_per_sample(self):
        """ return the number of bytes that are used for a single sample """
        res = self.get32(SPC_MIINST_BYTESPERSAMPLE)
        if self.chkError() == -1:
            return -1
        return res

    def set_samplerate(self, rate):
        """ set sample rate in Hz """
        self.set32(SPC_SAMPLERATE, rate)
        return self.chkError()

    def get_samplerate(self):
        """ get sample rate in Hz """
        res = self.get32(SPC_SAMPLERATE)
        if self.chkError() == -1:
            return -1
        return res

    def set_selected_channels(self, chans):
        """
        set selected channels (channels that can be used for output)

        chans consists of binary flags for each channel:
        chans = 0b00 => not ch1, not ch2
        chans = 0b01 => ch1, not ch2
        pg 71 manual
        ...
        """
        self.set32(SPC_CHENABLE, chans)
        return self.chkError()

    def get_selected_channels(self):
        """ get selected channels
        Sets the channel enable information for the next card run.
        pg. 73 manual
        """
        res = self.get32(SPC_CHENABLE)
        if self.chkError() == -1:
            return -1
        return res

    def get_selected_channels_count(self):
        """ get count of selected channels
        Reads back the number of currently activated channels.
        pg 73 manual
        """
        res = self.get32(SPC_CHCOUNT)
        if self.chkError() == -1:
            return -1
        return res

    def set_channel_output(self, ch, enabled):
        """ set output of channel enabled/disabled """
        ch_reg = self._regs_output[ch]  # get the enable output register of the specific channel
        self.set32(ch_reg, enabled)
        return self.chkError()

    def get_channel_output(self, ch):
        """ get whether the output of the channel is enabled """
        ch_reg = self._regs_output[ch]  # get the enable output register of the specific channel
        res = self.get32(ch_reg)
        if self.chkError() == -1:
            return -1
        return res

    def set_amplitude(self, ch, amp):
        """ set the amplitude of a channel in mV (into 50 Ohms) """
        reg = self._regs_amplitude[ch]  # get the amplitude register of the specific channel
        self.set32(reg, amp)
        return self.chkError()

    def get_amplitude(self, ch):
        """ get the amplitude of a channel in mV (into 50 Ohms) """
        reg = self._regs_amplitude[ch]  # get the amplitude register of the specific channel
        res = self.get32(reg)
        if self.chkError() == -1:
            return -1
        return res

    def set_filter(self, ch, amp):
        """ set the filter cut off frequency (ls) """
        reg = self._regs_filter[ch]  # get the filter register of the specific channel
        self.set32(reg, amp)
        return self.chkError()

    def get_filter(self, ch):
        """ get the filter cut off frequency (ls) """
        reg = self._regs_filter[ch]  # get the filter register of the specific channel
        res = self.get32(reg)
        if self.chkError() == -1:
            return -1
        return res

    def set_offset(self, ch, amp):
        """ set the ofset of a channel +/-100% in steps of 1%, pg. 74  """
        reg = self._regs_offset[ch]  # get the offset register of the specific channel
        self.set32(reg, amp)
        return self.chkError()

    def get_offset(self, ch):
        """ get the amplitude of a channel +/-100% in steps of 1%, pg. 74   """
        reg = self._regs_offset[ch]  # get the offest register of the specific channel
        res = self.get32(reg)
        if self.chkError() == -1:
            return -1
        return res

    def set_stoplevel(self, ch, stoplevel):
        """ define what is put out after a waveform is finished

            zero: output 0V
            high: output high voltage
            low: output low voltage
            hold: hold voltage of last sample
        """
        reg = self._regs_stoplevel[ch]  # get register for stoplevel

        if not self._vals_stoplevel.has_key(stoplevel):
            print('Unknown parameter value {0} in set_stoplevel.'.format(stoplevel))

        val = self._vals_stoplevel[stoplevel]  # values are stored in a dictionary
        self.set32(reg, val)
        return self.chkError()

    def get_stoplevel(self, ch):
        """ get what is put out after a waveform is finished

            zero: output 0V
            high: output high voltage
            low: output low voltage
            hold: hold voltage of last sample
        """
        reg = self._regs_stoplevel[ch]  # get register for stoplevel
        res = self.get32(reg)

        # get the name of the result from the stoplevel dictionary
        for key in self._vals_stoplevel.keys():
            if self._vals_stoplevel[key] == res:
                res = key

        if self.chkError() == -1:
            return -1
        return res

    def set_mode(self, mode):
        mode = self._vals_mode[mode]
        self.set32(SPC_CARDMODE, mode)
        return self.chkError()

    def get_mode(self):
        res = self.get32(SPC_CARDMODE)

        # get the name of the result from the mode dictionary
        for key in self._vals_mode.keys():
            if self._vals_mode[key] == res:
                res = key

        if self.chkError() == -1:
            return -1
        return res

    def set32(self, register, value):
        spcm_dwSetParam_i32(self.handle, register, int32(value))

    def set64(self, register, value):
        spcm_dwSetParam_i64(self.handle, register, int64(value))

    def get32(self, register):
        res = int32(0)
        spcm_dwGetParam_i32(self.handle, register, byref(res))
        return res.value

    def get64(self, register):
        res = int64(0)
        spcm_dwGetParam_i64(self.handle, register, byref(res))
        return res.value

    def chkError(self):
        error_text = create_string_buffer(ERRORTEXTLEN)
        if (spcm_dwGetErrorInfo_i32(self.handle, None, None, error_text) != ERR_OK):
            print(error_text.value)
            return -1
        return 0

    def _zeros_to_32(self, data):
        """ Fills the list with zeros until the length is a multiple of 32 (converts lists to arrays). """
        if not type(data) == type([]):
            data = data.tolist()

        while not len(data) % 32 == 0:
            data.append(0)

        return np.asarray(data)

    def _hold_to_32(self, data):
        """ Fills the list with last value until the length is a multiple of 32 (converts lists to arrays). """
        val = data[-1]
        if not type(data) == type([]):
            data = data.tolist()

        while not len(data) % 32 == 0:
            data.append(val)

        return np.asarray(data)