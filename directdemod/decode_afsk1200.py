'''
AFSK1200
'''
from directdemod import source, sink, chunker, comm, constants, filters, demod_am, demod_fm, peakdetect, \
    framechecksequence
import numpy as np
import logging
import scipy.signal as signal
import matplotlib.pylab as plt

def decode_nrzi(nrzi):
    code_bit = []
    # starting bit. with NRZI it doesn't matter, if 0 or 1 at the beginning
    code_bit.append(1)

    for bit in range(1, len(nrzi)):
        if nrzi[bit - 1] == nrzi[bit]:
            code_bit.append(1)
        elif nrzi[bit - 1] != nrzi[bit]:
            code_bit.append(0)

    return code_bit

def find_bit_stuffing(code_bit):
    stuffed_bit = np.zeros(len(code_bit), dtype=np.int)

    counter = 0
    for bit in range(len(code_bit)):

        if counter == 5 and code_bit[bit] == 1:
            # could be ending, because 6th bit is not 0 and could be intentially left 1, as expected for the frame end
            stuffed_bit[bit] = 2

        if counter == 5 and code_bit[bit] == 0:
            # normal bit stuffing
            stuffed_bit[bit] = 1

        #print(bit, code_bit[bit], stuffed_bit[bit], counter)

        if code_bit[bit] == 1:
            counter += 1
        if code_bit[bit] == 0:
            counter = 0

    return stuffed_bit

def reduce_stuffed_bit(code_bit, stuffed_bit):
    out = []

    for i in range(len(code_bit)):
        if stuffed_bit[i] == 0:
            out.append(code_bit[i])

    return out




'''
Object to decode AFSK1200
'''

class decode_afsk1200:

    '''
    Object to decode AFSK1200
    '''

    def __init__(self, sigsrc, offset, bw):

        '''Initialize the object

        Args:
            sigsrc (:obj:`commSignal`): IQ data source
            offset (:obj:`float`): Frequency offset of source in Hz
            bw (:obj:`int`, optional): Bandwidth
        '''

        self.BAUDRATE = 1200
        self.mark_frequency = 1200
        self.space_frequency = 2200

        self.__bw = bw
        if self.__bw is None:
            self.__bw = 22050
        self.__sigsrc = sigsrc
        self.__offset = offset
        self.__msg = None
        self.__graphs = 0

    @property
    def getMsg(self):
        '''Get the message from data

        Returns:
            :string: A string of message data
        '''

        if self.__msg is None:
            ## Next create a signal object, reading data from the source
            # Read all values from the source into an array
            sigArray = self.__sigsrc.read(0, self.__sigsrc.length)

            # a commSignal object basically stores the signal array and its samplingrate
            # if you want the array do sig.signal
            # if you want the samping rate do sig.sampRate
            sig = comm.commSignal(self.__sigsrc.sampFreq, sigArray)

            ## Offset the frequency if required, not needed here
            # sig.offsetFreq(0)

            ## Apply a blackman harris filter to get rid of noise
            bhFilter = filters.blackmanHarris(151)
            sig.filter(bhFilter)

            ## Limit bandwidth, say 30000
            rate_out = self.__bw
            sig.bwLim(rate_out)

            ## FM demodulate
            fmDemodulator = demod_fm.demod_fm()
            sig.funcApply(fmDemodulator.demod)

            ## APRS has two freqs 1200 and 2200, hence create a butter band pass filter from 1200-500 to 2200+500
            bFilter = filters.butter(sig.sampRate, 1200 - 500, 2200 + 500, typeFlt=constants.FLT_BP)
            sig.filter(bFilter)

            ## plot the signal
            if self.__graphs == 1:
                plt.plot(sig.signal)
                plt.show()

            BAUDRATE = self.BAUDRATE
            mark_frequency = self.mark_frequency
            space_frequency = self.space_frequency

            buffer_size = int(np.round(rate_out / BAUDRATE))
            SAMPLE_PER_BAUD = rate_out // BAUDRATE


            # creating the “correlation list" for the comparison frequencies of the digital frequency filers
            corr_mark_i = np.zeros(buffer_size)
            corr_mark_q = np.zeros(buffer_size)
            corr_space_i = np.zeros(buffer_size)
            corr_space_q = np.zeros(buffer_size)

            # filling the "correlation list" with sampled waveform for the two frequencies.
            for i in range(buffer_size):
                mark_angle = (i * 1.0 / rate_out) / (1 / mark_frequency) * 2 * np.pi
                corr_mark_i[i] = np.cos(mark_angle)
                corr_mark_q[i] = np.sin(mark_angle)

                space_angle = (i * 1.0 / rate_out) / (1 / space_frequency) * 2 * np.pi
                corr_space_i[i] = np.cos(space_angle)
                corr_space_q[i] = np.sin(space_angle)


            # now we check the full signal for the binary states, whether it is closer to 1200 hz or closer to 2200 Hz
            binary_filter = np.zeros(len(sig.signal))

            for sample in range(len(sig.signal) - buffer_size):
                corr_mi = 0
                corr_mq = 0
                corr_si = 0
                corr_sq = 0

                for sub in range(buffer_size):
                    corr_mi = corr_mi + sig.signal[sample + sub] * corr_mark_i[sub]
                    corr_mq = corr_mq + sig.signal[sample + sub] * corr_mark_q[sub]

                    corr_si = corr_si + sig.signal[sample + sub] * corr_space_i[sub]
                    corr_sq = corr_sq + sig.signal[sample + sub] * corr_space_q[sub]

                binary_filter[sample] = (corr_mi ** 2 + corr_mq ** 2 - corr_si ** 2 - corr_sq ** 2)

            if self.__graphs == 1:
                plt.plot(sig.signal / np.max(sig.signal))
                plt.plot(np.sign(binary_filter))
                plt.show()

            # now trying to find the raising or falling edges of the bits
            # generating the edge detection kernel
            kernel = np.zeros(SAMPLE_PER_BAUD)
            for i in range(len(kernel)):
                if i < SAMPLE_PER_BAUD // 2:
                    kernel[i] = -1
                else:
                    kernel[i] = 1

            changes = np.correlate(np.sign(binary_filter), kernel, mode="same") / SAMPLE_PER_BAUD

            if self.__graphs == 1:
                plt.plot(np.sign(binary_filter))
                plt.plot(changes)
                plt.title("bit starts")
                plt.show()


            # by using the edges of the bits for synching the sampling to the transmitted bits, the algo is
            # self synchronizing.
            # but sometimes the crossing areas between the bits can be uncertain. for that, a peak detection defines
            # only one solution in close vicinity and defining the edges further.
            peaks = peakdetect.peakdetect(np.abs(changes), lookahead=int(SAMPLE_PER_BAUD * 0.65))

            peaks1_x = []
            peaks1_y = []

            # positive peaks
            for i in range(len(peaks[0])):
                peaks1_x.append(peaks[0][i][0])
                peaks1_y.append(peaks[0][i][1])

            if self.__graphs == 1:
                plt.plot(peaks1_x, peaks1_y, "o")
                plt.plot(np.abs(changes))
                plt.plot(np.sign(binary_filter))
                plt.plot(sig.signal / np.max(sig.signal))
                plt.show()

            bit_repeated = np.round(np.diff(peaks1_x) / (rate_out / BAUDRATE))

            if self.__graphs == 1:
                plt.plot(np.sign(binary_filter))
                plt.plot(peaks1_x[:-1], bit_repeated, "*")
                plt.grid()
                plt.title("where frequency shifts")
                plt.show()

            # making the bits for nrzi
            bitstream_nrzi = []

            c = 0
            for i in range(len(bit_repeated)):
                # print(c, i, x1[i], "p", int(bit_repeated[i]))
                for repeats in range(int(bit_repeated[i])):
                    bitstream_nrzi.append((np.mean(binary_filter[
                                                   peaks1_x[i] + repeats * SAMPLE_PER_BAUD: peaks1_x[i] + (
                                                                                                          repeats + 1) * SAMPLE_PER_BAUD])))
                    # print(c, bitstream_nrzi[-1])
                    c += 1

            # here we convert the nrzi bits to normal bits
            bitstream = decode_nrzi(np.sign(bitstream_nrzi))

            if self.__graphs == 1:
                plt.plot(np.sign(bitstream_nrzi))
                plt.plot(bitstream_nrzi, "o-")
                plt.plot(bitstream, "*")
                plt.show()

            bit_startflag = []
            bit_startflag_marker = []

            for bit in range(len(bitstream) - 8):
                out = ""
                for i in range(8):
                    out += str(bitstream[bit + i])

                if out == "01111110":
                    # print(bit)
                    bit_startflag.append(bit)
                    bit_startflag_marker.append(1)

            length = np.diff(bit_startflag)

            # there are still the stuffed bits inside the bit stream, so we need to find them...
            bitstream_stuffed = find_bit_stuffing(bitstream)

            if self.__graphs == 1:
                plt.plot(bitstream_nrzi)
                plt.plot(bitstream, "o-")
                plt.plot(bit_startflag[:-1], length, "o")
                plt.plot(bit_startflag, bit_startflag_marker, "o")
                plt.plot(bitstream_stuffed, "*")
                plt.title("test1")
                plt.show()


            # checking at each possible start flag, if the bit stream was received correctly.
            # this is done by checking the crc16 at the end of the msg with the msg body.
            for flag in range(len(bit_startflag) - 1):

                # and firstly, we need to get rid of the stuffed bits, that are still inside the bit stream
                bits = reduce_stuffed_bit(bitstream[bit_startflag[flag] + 8: bit_startflag[flag + 1]],
                                          bitstream_stuffed[bit_startflag[flag] + 8: bit_startflag[flag + 1]])

                msg = bits[:-16]

                if len(bits) % 8 == 0 and len(msg) > 16 * 8:

                    out = ""
                    for i in range(len(msg)):
                        out += str(msg[i])
                    crc = framechecksequence.fcs_crc16(out)

                    crc_received = ""
                    msg_rest = bits[-16:]
                    for i in range(len(msg_rest)):
                        crc_received += str(msg_rest[i])

                    if crc_received == crc:
                        print("one aprs msg with correct crc is found. #", flag, "starts at", bit_startflag[flag], "length is", len(bits) / 8)

                        if self.__graphs == 1:
                            plt.plot(bitstream[bit_startflag[flag] + 8: bit_startflag[flag + 1] + 8], "o-")
                            plt.plot(bits, "*-")
                            plt.show()

                        # there can be several messages per stream, so for now only the last is stored.
                        # to-do
                        self.__msg = "template: space rocks!"

            logging.info('Message extraction complete')

        return self.__msg


if __name__== "__main__":
    # input file name
    fileName = "../samples/SDRSharp_20170830_073907Z_145825000Hz_IQ_autogain.wav"


    # create this as a signal source
    sigsrc = source.IQwav(fileName)

    freqOffset = 0
    bandwidth = 22050

    afskObj = decode_afsk1200(sigsrc, freqOffset, bandwidth)

    print(afskObj.getMsg)