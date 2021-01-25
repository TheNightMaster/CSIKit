import collections
import os
import struct
import sys
from math import floor

import numpy as np
# import scipy.io

SIZE_STRUCT = struct.Struct(">H").unpack

HEADER_STRUCT_BE = struct.Struct(">QHHBBBBBBBBBBBH").unpack
HEADER_STRUCT_LE = struct.Struct(">QHHBBBBBBBBBBBH").unpack
HEADER_FORMAT = collections.namedtuple("packet_header", ["timestamp", "csi_length", "tx_channel", "err_info", "noise_floor", "rate", "bandwidth", "num_tones", "nr", "nc", "rssi", "rssi_1", "rssi_2", "rssi_3", "payload_length"])

BITS_PER_SYMBOL = 10
BITS_PER_COMPLEX_SYMBOL = 2 * BITS_PER_SYMBOL

class ATHBeamformReader:

    def __init__(self, filename, scaled=False):
        self.filename = filename
        if os.path.exists(filename):
            with open(filename, "rb") as file:
                self.data = file.read()
                self.csi_trace = self.read_bf_file()
        else:
            raise Exception("File not found: {}".format(filename))

    @staticmethod
    def signbit_convert(data, maxbit):
        if (data & (1 << (maxbit - 1))):
            data -= (1 << maxbit)

        return data

    @staticmethod
    def get_next_bits(buf, current_data, idx, bits_left):
        h_data = buf[idx]
        h_data += (buf[idx+1] << 8)

        current_data += h_data << bits_left

        idx += 2
        bits_left += 16

        return current_data, idx, bits_left

    @staticmethod
    def read_bfee(csi_buf, nr, nc, num_tones, scaled=False):

        csi = np.empty((num_tones, nc, nr), dtype=np.complex)

        bitmask = (1 << BITS_PER_SYMBOL) - 1
        idx = 0
        bits_left = 16
        
        h_data = csi_buf[idx]
        idx += 1
        h_data += (csi_buf[idx] << 8)
        idx += 1
        current_data = h_data & ((1 << 16) - 1)
        
        for k in range(num_tones):
            for nc_idx in range(nc):
                for nr_idx in range(nr):
                    if ((bits_left - BITS_PER_SYMBOL) < 0):
                        current_data, idx, bits_left = ATHBeamformReader.get_next_bits(csi_buf, current_data, idx, bits_left)
                    
                    imag = current_data & bitmask
                    imag = ATHBeamformReader.signbit_convert(imag, BITS_PER_SYMBOL)
                    imag += 1

                    bits_left -= BITS_PER_SYMBOL
                    current_data = current_data >> BITS_PER_SYMBOL

                    if ((bits_left - BITS_PER_SYMBOL) < 0):
                        current_data, idx, bits_left = ATHBeamformReader.get_next_bits(csi_buf, current_data, idx, bits_left)

                    real = current_data & bitmask
                    real = ATHBeamformReader.signbit_convert(real, BITS_PER_SYMBOL)
                    real += 1

                    bits_left -= BITS_PER_SYMBOL
                    current_data = current_data >> BITS_PER_SYMBOL

                    csi[k, nc_idx, nr_idx] = np.complex(real, imag)

        # if scaled:
        #     scaled_csi = scale_csi_entry(csi_block)
        #     csi_block["scaled_csi"] = scaled_csi

        return csi

    def read_bf_file(self):
        """
            This function parses .dat files generated by log_to_file.

            Returns:
                total_csi (list): All valid CSI blocks, and their associated headers, contained within the given file.
        """

        data = self.data
        length = len(data)

        total_csi = []
        cursor = 0
        expected_count = 0

        first_byte = data[cursor:cursor+1]

        if first_byte == b'\xff':
            struct_type = HEADER_STRUCT_BE
            cursor += 1
        elif first_byte == b'\x00':
            struct_type = HEADER_STRUCT_LE
            cursor += 1
        else:
            #¯\_(ツ)_/¯
            print("File contains no endianness header. Assuming big.")
            struct_type = HEADER_STRUCT_BE

        while cursor < (length - 4):
            field_length = SIZE_STRUCT(data[cursor:cursor+2])[0]
            
            if (cursor + field_length) > length:
                break

            cursor += 2

            header_block = HEADER_FORMAT._make(struct_type(data[cursor:cursor+25]))
            cursor += 25

            if header_block.csi_length > 0:
                data_block = data[cursor:cursor+header_block.csi_length]

                csi_data = ATHBeamformReader.read_bfee(data_block, header_block.nr, header_block.nc, header_block.num_tones)
                if csi_data is not None:
                    total_csi.append({
                        "header": header_block,
                        "timestamp": header_block.timestamp,
                        "csi": csi_data
                    })

                expected_count += 1
                cursor += header_block.csi_length

            if header_block.payload_length > 0:
                cursor += header_block.payload_length

            if (cursor + 420 > length):
                break

        return total_csi

if __name__ == "__main__":

    if len(sys.argv) > 2:
        path = sys.argv[2]
    else:
        path = "./data/atheros/sample_bigEndian.dat"

    reader = ATHBeamformReader(path)
    print("Have CSI for {} packets.".format(len(reader.csi_trace)))