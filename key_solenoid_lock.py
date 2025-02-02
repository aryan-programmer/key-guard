from threading import RLock
from logger_instance import logger
import logging

import gpiozero


class KeySolenoidLock:
    _lock: RLock
    _is_key_locked: bool
    _solenoid_controller: gpiozero.DigitalOutputDevice

    def __init__(self, init_locked: bool, solenoid_controller: gpiozero.DigitalOutputDevice):
        self._lock = RLock()
        self._is_key_locked = init_locked
        self._solenoid_controller = solenoid_controller

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
            else:
                logger.log(logging.INFO, "Unlocking key")
                self._is_key_locked = False
                self._solenoid_controller.on()
