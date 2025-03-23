
from threading import RLock
import threading
from event import Event
from logger_instance import logger
import logging

import gpiozero


class KeySolenoidLock:
    _lock: RLock
    _is_key_locked: bool
    _solenoid_controller: gpiozero.DigitalOutputDevice
    _relock_key_timeout_ms = Event()
    _relock_key_timeout_timer: threading.Timer | None
    relock_key_timeout_event = Event()

    def __init__(self, init_locked: bool, solenoid_controller: gpiozero.DigitalOutputDevice, relock_key_timeout_ms: int):
        self._lock = RLock()
        self._is_key_locked = init_locked
        self._solenoid_controller = solenoid_controller
        self._relock_key_timeout_ms = relock_key_timeout_ms

    @property
    def is_key_locked(self) -> bool:
        return self._is_key_locked

    @is_key_locked.setter
    def is_key_locked(self, value: bool):
        with self._lock:
            if value:
                logger.log(logging.INFO, "Locking key")
                self._is_key_locked = True
                self._solenoid_controller.off()
                if self._relock_key_timeout_timer != None:
                    self._relock_key_timeout_timer.cancel()
                    self._relock_key_timeout_timer = None
            else:
                logger.log(logging.INFO, "Unlocking key")
                self._is_key_locked = False
                self._solenoid_controller.on()
                self._relock_key_timeout_timer = threading.Timer(self._relock_key_timeout_ms, self._on_relock_key_timeout)
                self._relock_key_timeout_timer.start()

    def _on_relock_key_timeout(self):
        logger.log(logging.INFO, "Re-locking key")
        self._relock_key_timeout_timer = None
        self.relock_key_timeout_event.trigger()
