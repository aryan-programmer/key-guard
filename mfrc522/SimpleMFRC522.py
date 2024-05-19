import math
import time

from . import MFRC522
from .chip_select_lock import ChipSelectLineLock


def uid_to_num(uid):
    return "".join((hex(v)[2:] for v in uid))


class SimpleMFRC522:
    _reader = None

    KEY = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    BLOCK_ADDRS = [8, 9, 10]

    def __init__(self, bus, device, lock: ChipSelectLineLock, spd=1000000):
        self._reader = MFRC522(bus, device, lock, spd)
        self._reader.turn_antenna_off()

    def read(self):
        with self._reader.lock:
            self._reader.turn_antenna_on()
            card_id, text = self._read_no_block()
            while not card_id:
                card_id, text = self._read_no_block()
            self._reader.turn_antenna_off()
            return card_id, text

    # @timing_decorator
    def read_id(self, timeout: float = -1):
        if timeout == -1:
            timeout = math.inf
        t1 = time.perf_counter()
        t_end = t1 + timeout
        with self._reader.lock:
            self._reader.turn_antenna_on()
            card_id = self._read_id_no_block()
            if not card_id:
                tn = time.perf_counter()
                while not card_id and tn < t_end:
                    card_id = self._read_id_no_block()
                    tn = time.perf_counter()
            self._reader.turn_antenna_off()
            return card_id

    # @timing
    def _read_id_no_block(self):
        (status, TagType) = self._reader.send_request(self._reader.PICC_REQIDL)
        if status != self._reader.MI_OK:
            return None
        (status, uid) = self._reader.anticoll()
        if status != self._reader.MI_OK:
            return None
        return uid_to_num(uid)

    def _auth_and_get_id(self):
        (status, TagType) = self._reader.send_request(self._reader.PICC_REQIDL)
        if status != self._reader.MI_OK:
            return status, None
        (status, uid) = self._reader.anticoll()
        if status != self._reader.MI_OK:
            return status, None
        card_id = uid_to_num(uid)
        self._reader.select_tag(uid)
        status = self._reader.auth(self._reader.PICC_AUTHENT1A, 11, self.KEY, uid)
        return status, card_id

    def _read_no_block(self):
        status, card_id = self._auth_and_get_id()
        if status != self._reader.MI_OK:
            return None, None
        data = []
        text_read = ''
        if status == self._reader.MI_OK:
            for block_num in self.BLOCK_ADDRS:
                block = self._reader.read_block(block_num)
                if block:
                    data += block
            if data:
                text_read = ''.join(chr(i) for i in data)
        self._reader.stop_crypto1()
        return card_id, text_read

    def write(self, text):
        with self._reader.lock:
            self._reader.turn_antenna_on()
            card_id, text_in = self._write_no_block(text)
            while not card_id:
                card_id, text_in = self._write_no_block(text)
            self._reader.turn_antenna_off()
            return card_id, text_in

    def _write_no_block(self, text):
        status, card_id = self._auth_and_get_id()
        if status != self._reader.MI_OK:
            return None, None
        self._reader.read_block(11)
        if status == self._reader.MI_OK:
            data = bytearray()
            data.extend(bytearray(text.ljust(len(self.BLOCK_ADDRS) * 16).encode('ascii')))
            i = 0
            for block_num in self.BLOCK_ADDRS:
                self._reader.write_block(block_num, data[(i * 16):(i + 1) * 16])
                i += 1
        self._reader.stop_crypto1()
        return card_id, text[0:(len(self.BLOCK_ADDRS) * 16)]

    def cleanup(self):
        self._reader.turn_antenna_off()
        self._reader.close()
