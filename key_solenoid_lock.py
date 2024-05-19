from threading import RLock

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
                print("Locking key")
                self._is_key_locked = True
                self._solenoid_controller.off()
            else:
                print("Unlocking key")
                self._is_key_locked = False
                self._solenoid_controller.on()
