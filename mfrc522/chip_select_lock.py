from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock

import gpiozero


class ChipSelectLinesLock:
    _lock: RLock
    _lines: list[gpiozero.DigitalOutputDevice]
    _lines_locks: list[RLock]
    _current_line: int | None
    _num_lockings: int

    def __init__(self, lines: list[gpiozero.DigitalOutputDevice]) -> None:
        self._lock = RLock()
        self._lines = lines
        self._lines_locks = [RLock() for _ in self._lines]
        self._current_line = None
        self._num_lockings = 0
        for line in self._lines:
            line.on()

    def acquire(self, line, blocking: bool = True, timeout: float = -1) -> bool:
        # print(
        #     "Acquire Before: ",
        #     self._num_lockings,
        #     [self._current_line, line],
        #     [v.value for v in self._lines],
        # )
        # traceback.print_stack(limit=3, file=sys.stdout)
        ret = self._lock.acquire(blocking, timeout)
        if not ret:
            return ret
        ret = self._lines_locks[line].acquire()
        if not ret:
            return ret
        self._num_lockings += 1
        self._current_line = line
        self._lines[self._current_line].off()
        # print(
        #     "Acquire After: ",
        #     self._num_lockings,
        #     [self._current_line, line],
        #     [v.value for v in self._lines],
        # )
        return True

    def release(self) -> None:
        # print(
        #     "Release Before: ",
        #     self._num_lockings,
        #     self._current_line,
        #     [v.value for v in self._lines],
        # )
        # traceback.print_stack(limit=3, file=sys.stdout)
        line = self._current_line
        self._lines[line].on()
        self._lines[line].off()
        self._num_lockings -= 1
        if self._num_lockings == 0:
            self._lines[line].on()
            # print(self._num_lockings, [v.value for v in self._lines])
            self._current_line = None
        self._lines_locks[line].release()
        # self._lock.release()
        # print(
        #     "Release After: ",
        #     self._num_lockings,
        #     [self._current_line, line],
        #     [v.value for v in self._lines],
        # )

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

    @contextmanager
    def acquire_timeout(self, timeout):
        result = self._csl.acquire(blocking=True, timeout=timeout)
        yield result
        if result:
            self._csl.release()
