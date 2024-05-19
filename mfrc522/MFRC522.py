#!/usr/bin/env python
# -*- coding: utf8 -*-
#
#    Copyright 2014,2018 Mario Gomez <mario.gomez@teubi.co>
#
#    This file is part of MFRC522-Python
#    MFRC522-Python is a simple Python implementation for
#    the MFRC522 NFC Card Reader for the Raspberry Pi.
#
#    MFRC522-Python is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    MFRC522-Python is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with MFRC522-Python.  If not, see <http://www.gnu.org/licenses/>.
#
import logging
import traceback

import RPi.GPIO as GPIO
import spidev

from mfrc522.chip_select_lock import ChipSelectLineLock


class MFRC522:
    MAX_LEN = 16

    PCD_IDLE = 0x00
    PCD_AUTHENT = 0x0E
    PCD_RECEIVE = 0x08
    PCD_TRANSMIT = 0x04
    PCD_TRANSCEIVE = 0x0C
    PCD_RESETPHASE = 0x0F
    PCD_CALCCRC = 0x03

    PICC_REQIDL = 0x26
    PICC_REQALL = 0x52
    PICC_ANTICOLL = 0x93
    PICC_SElECTTAG = 0x93
    PICC_AUTHENT1A = 0x60
    PICC_AUTHENT1B = 0x61
    PICC_READ = 0x30
    PICC_WRITE = 0xA0
    PICC_DECREMENT = 0xC0
    PICC_INCREMENT = 0xC1
    PICC_RESTORE = 0xC2
    PICC_TRANSFER = 0xB0
    PICC_HALT = 0x50

    MI_OK = 0
    MI_NOTAGERR = 1
    MI_ERR = 2

    Reserved00 = 0x00
    CommandReg = 0x01
    CommIEnReg = 0x02
    DivlEnReg = 0x03
    CommIrqReg = 0x04
    DivIrqReg = 0x05
    ErrorReg = 0x06
    Status1Reg = 0x07
    Status2Reg = 0x08
    FIFODataReg = 0x09
    FIFOLevelReg = 0x0A
    WaterLevelReg = 0x0B
    ControlReg = 0x0C
    BitFramingReg = 0x0D
    CollReg = 0x0E
    Reserved01 = 0x0F

    Reserved10 = 0x10
    ModeReg = 0x11
    TxModeReg = 0x12
    RxModeReg = 0x13
    TxControlReg = 0x14
    TxAutoReg = 0x15
    TxSelReg = 0x16
    RxSelReg = 0x17
    RxThresholdReg = 0x18
    DemodReg = 0x19
    Reserved11 = 0x1A
    Reserved12 = 0x1B
    MifareReg = 0x1C
    Reserved13 = 0x1D
    Reserved14 = 0x1E
    SerialSpeedReg = 0x1F

    Reserved20 = 0x20
    CRCResultRegM = 0x21
    CRCResultRegL = 0x22
    Reserved21 = 0x23
    ModWidthReg = 0x24
    Reserved22 = 0x25
    RFCfgReg = 0x26
    GsNReg = 0x27
    CWGsPReg = 0x28
    ModGsPReg = 0x29
    TModeReg = 0x2A
    TPrescalerReg = 0x2B
    TReloadRegH = 0x2C
    TReloadRegL = 0x2D
    TCounterValueRegH = 0x2E
    TCounterValueRegL = 0x2F

    Reserved30 = 0x30
    TestSel1Reg = 0x31
    TestSel2Reg = 0x32
    TestPinEnReg = 0x33
    TestPinValueReg = 0x34
    TestBusReg = 0x35
    AutoTestReg = 0x36
    VersionReg = 0x37
    AnalogTestReg = 0x38
    TestDAC1Reg = 0x39
    TestDAC2Reg = 0x3A
    TestADCReg = 0x3B
    Reserved31 = 0x3C
    Reserved32 = 0x3D
    Reserved33 = 0x3E
    Reserved34 = 0x3F

    serNum = []

    def __init__(self, bus, device, lock: ChipSelectLineLock, spd=1000000):
        self.spi = spidev.SpiDev(bus, device)
        self.spi.max_speed_hz = spd
        self.spi.open(bus, device)
        self.lock = lock

        self.logger = logging.getLogger('mfrc522Logger')

        self.initialize()
        traceback.print_stack()
        self.logger.log(
            logging.WARN,
            "Successfully initialized RF522 with bus = %d, device = %d",
            bus,
            device,
        )

    def reset(self):
        with self.lock:
            self.write_register(self.CommandReg, self.PCD_RESETPHASE)

    def write_register(self, addr, val):
        with self.lock:
            self.spi.xfer2([(addr << 1) & 0x7E, val])

    def read_register(self, addr):
        with self.lock:
            val = self.spi.xfer2([((addr << 1) & 0x7E) | 0x80, 0])
            return val[1]

    def close(self):
        with self.lock:
            self.spi.close()
            GPIO.cleanup()

    def set_bit_mask(self, reg, mask):
        with self.lock:
            tmp = self.read_register(reg)
            self.write_register(reg, tmp | mask)

    def clear_bit_mask(self, reg, mask):
        with self.lock:
            tmp = self.read_register(reg)
            self.write_register(reg, tmp & (~mask))

    def turn_antenna_on(self):
        with self.lock:
            temp = self.read_register(self.TxControlReg)
            if ~(temp & 0x03):
                self.set_bit_mask(self.TxControlReg, 0x03)

    def turn_antenna_off(self):
        with self.lock:
            self.clear_bit_mask(self.TxControlReg, 0x03)

    def _to_card(self, command, send_data):
        with self.lock:
            back_data = []
            back_len = 0
            status = self.MI_ERR
            irq_en = 0x00
            wait_i_rq = 0x00

            if command == self.PCD_AUTHENT:
                irq_en = 0x12
                wait_i_rq = 0x10
            if command == self.PCD_TRANSCEIVE:
                irq_en = 0x77
                wait_i_rq = 0x30

            self.write_register(self.CommIEnReg, irq_en | 0x80)
            self.clear_bit_mask(self.CommIrqReg, 0x80)
            self.set_bit_mask(self.FIFOLevelReg, 0x80)

            self.write_register(self.CommandReg, self.PCD_IDLE)

            for i in range(len(send_data)):
                self.write_register(self.FIFODataReg, send_data[i])

            self.write_register(self.CommandReg, command)

            if command == self.PCD_TRANSCEIVE:
                self.set_bit_mask(self.BitFramingReg, 0x80)

            i = 2000
            while True:
                n = self.read_register(self.CommIrqReg)
                i -= 1
                if ~((i != 0) and ~(n & 0x01) and ~(n & wait_i_rq)):
                    break

            self.clear_bit_mask(self.BitFramingReg, 0x80)

            if i != 0:
                if (self.read_register(self.ErrorReg) & 0x1B) == 0x00:
                    status = self.MI_OK

                    if n & irq_en & 0x01:
                        status = self.MI_NOTAGERR

                    if command == self.PCD_TRANSCEIVE:
                        n = self.read_register(self.FIFOLevelReg)
                        last_bits = self.read_register(self.ControlReg) & 0x07
                        if last_bits != 0:
                            back_len = (n - 1) * 8 + last_bits
                        else:
                            back_len = n * 8

                        if n == 0:
                            n = 1
                        if n > self.MAX_LEN:
                            n = self.MAX_LEN

                        for i in range(n):
                            back_data.append(self.read_register(self.FIFODataReg))
                else:
                    status = self.MI_ERR

            return status, back_data, back_len

    def send_request(self, req_mode):
        with self.lock:
            tag_type = []

            self.write_register(self.BitFramingReg, 0x07)

            tag_type.append(req_mode)
            (status, back_data, backBits) = self._to_card(self.PCD_TRANSCEIVE, tag_type)

            if (status != self.MI_OK) | (backBits != 0x10):
                status = self.MI_ERR

        return status, backBits

    def anticoll(self):
        with self.lock:
            ser_num_check = 0

            ser_num = []

            self.write_register(self.BitFramingReg, 0x00)

            ser_num.append(self.PICC_ANTICOLL)
            ser_num.append(0x20)

            (status, back_data, backBits) = self._to_card(self.PCD_TRANSCEIVE, ser_num)

            if status == self.MI_OK:
                if len(back_data) == 5:
                    for i in range(4):
                        ser_num_check = ser_num_check ^ back_data[i]
                    if ser_num_check != back_data[4]:
                        status = self.MI_ERR
                else:
                    status = self.MI_ERR

            return status, back_data

    def calculate_crc(self, p_in_data):
        with self.lock:
            self.clear_bit_mask(self.DivIrqReg, 0x04)
            self.set_bit_mask(self.FIFOLevelReg, 0x80)

            for i in range(len(p_in_data)):
                self.write_register(self.FIFODataReg, p_in_data[i])

            self.write_register(self.CommandReg, self.PCD_CALCCRC)
            i = 0xFF
            while True:
                n = self.read_register(self.DivIrqReg)
                i -= 1
                if not ((i != 0) and not (n & 0x04)):
                    break
            p_out_data = [self.read_register(self.CRCResultRegL), self.read_register(self.CRCResultRegM)]
            return p_out_data

    def select_tag(self, ser_num):
        with self.lock:
            buf = [self.PICC_SElECTTAG, 0x70, *ser_num[:5]]

            p_out = self.calculate_crc(buf)
            buf.append(p_out[0])
            buf.append(p_out[1])
            (status, back_data, back_len) = self._to_card(self.PCD_TRANSCEIVE, buf)

            if (status == self.MI_OK) and (back_len == 0x18):
                self.logger.debug("Size: " + str(back_data[0]))
                return back_data[0]
            else:
                return 0

    def auth(self, auth_mode, block_addr, sector_key, ser_num):
        with self.lock:
            buff = [
                # First byte should be the authMode (A or B)
                auth_mode,
                # Second byte is the trailerBlock (usually 7)
                block_addr,
                # Now we need to append the authKey which usually is 6 bytes of 0xFF
                *sector_key,
                # Next we append the first 4 bytes of the UID
                *ser_num[:4]
            ]

            # Now we start the authentication itself
            (status, back_data, back_len) = self._to_card(self.PCD_AUTHENT, buff)

            # Check if an error occurred
            if not (status == self.MI_OK):
                self.logger.error("AUTH ERROR!!")
            if not (self.read_register(self.Status2Reg) & 0x08) != 0:
                self.logger.error("AUTH ERROR(status2reg & 0x08) != 0")

            # Return the status
            return status

    def stop_crypto1(self):
        with self.lock:
            self.clear_bit_mask(self.Status2Reg, 0x08)

    def read_block(self, block_addr):
        with self.lock:
            recv_data = [self.PICC_READ, block_addr]
            p_out = self.calculate_crc(recv_data)
            recv_data.append(p_out[0])
            recv_data.append(p_out[1])
            (status, back_data, back_len) = self._to_card(self.PCD_TRANSCEIVE, recv_data)
            if not (status == self.MI_OK):
                self.logger.error("Error while reading!")

            if len(back_data) == 16:
                self.logger.debug("Sector " + str(block_addr) + " " + str(back_data))
                return back_data
            else:
                return None

    def write_block(self, block_addr, write_data):
        with self.lock:
            buff = [self.PICC_WRITE, block_addr]
            crc = self.calculate_crc(buff)
            buff.append(crc[0])
            buff.append(crc[1])
            (status, back_data, back_len) = self._to_card(self.PCD_TRANSCEIVE, buff)
            if not (status == self.MI_OK) or not (back_len == 4) or not ((back_data[0] & 0x0F) == 0x0A):
                status = self.MI_ERR

            self.logger.debug("%s backdata &0x0F == 0x0A %s" % (back_len, back_data[0] & 0x0F))
            if status == self.MI_OK:
                buf = []
                for i in range(16):
                    buf.append(write_data[i])

                crc = self.calculate_crc(buf)
                buf.append(crc[0])
                buf.append(crc[1])
                (status, back_data, back_len) = self._to_card(self.PCD_TRANSCEIVE, buf)
                if not (status == self.MI_OK) or not (back_len == 4) or not ((back_data[0] & 0x0F) == 0x0A):
                    self.logger.error("Error while writing")
                if status == self.MI_OK:
                    self.logger.debug("Data written")

    def dump_classic_1k(self, key, uid):
        with self.lock:
            for i in range(64):
                status = self.auth(self.PICC_AUTHENT1A, i, key, uid)
                # Check if authenticated
                if status == self.MI_OK:
                    self.read_block(i)
                else:
                    self.logger.error("Authentication error")

    def initialize(self):
        with self.lock:
            self.reset()

            self.write_register(self.TModeReg, 0x8D)
            self.write_register(self.TPrescalerReg, 0x3E)
            self.write_register(self.TReloadRegL, 30)
            self.write_register(self.TReloadRegH, 0)

            self.write_register(self.TxAutoReg, 0x40)
            self.write_register(self.ModeReg, 0x3D)
            self.turn_antenna_on()
