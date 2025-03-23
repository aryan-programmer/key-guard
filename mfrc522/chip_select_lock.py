from dataclasses import dataclass
from threading import RLock
from typing import List

import gpiozero


class ChipSelectLinesLock:
    _lock: RLock
    _lines: List[gpiozero.DigitalOutputDevice]
    _lines_locks: List[RLock]
    _current_line: int | None
    _num_lockings: int

    def __init__(self, lines: List[gpiozero.DigitalOutputDevice]) -> None:
        self._lock = RLock()
        self._lines = lines
        self._lines_locks = [RLock() for _ in self._lines]
        self._current_line = None
        self._num_lockings = 0
        for line in self._lines:
            line.on()

    def acquire(self, line, blocking: bool = True, timeout: float = -1) -> bool:
        ret = self._lock.acquire(blocking, timeout)
        if not ret:
            return ret
        ret = self._lines_locks[line].acquire()
        if not ret:
            return ret
        self._num_lockings += 1
        self._current_line = line
        self._lines[self._current_line].off()
        return True

    def release(self) -> None:
        line = self._current_line
        self._lines[line].on()
        self._num_lockings -= 1
        if self._num_lockings == 0:
            self._current_line = None
        self._lines_locks[line].release()
        self._lock.release()

    def individual_line_lock(self, line: int):
        return ChipSelectLineLock(self, line)


@dataclass
class ChipSelectLineLock:
    _csl: ChipSelectLinesLock
    _line: int

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        # logger.log(logging.INFO, "Acquiring: %s", self)
        return self._csl.acquire(self._line, blocking, timeout)

    def release(self) -> None:
        # logger.log(logging.INFO, "Releasing: %s", self)
        self._csl.release()

    def __enter__(self):
        # logger.log(logging.INFO, "Entering: %s", self)
        # traceback.print_stack()
        self._csl.acquire(self._line, blocking=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # logger.log(logging.INFO, "Exiting: %s", self)
        # traceback.print_stack()
        self._csl.release()
