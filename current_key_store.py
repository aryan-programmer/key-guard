import datetime
import logging
from threading import RLock
import threading

import gpiozero
from data_objects import KeyData
from database import KeysDB
from event import Event
from logger_instance import logger
from mfrc522 import SimpleMFRC522

KEY_STOLEN_LIMIT = datetime.timedelta(seconds=1)


class CurrentKeyStore:
    relock_key_timeout_event: Event["CurrentKeyStore", None]
    unauthorized_key_swap_attempted: Event["CurrentKeyStore", None]
    key_stolen: Event["CurrentKeyStore", KeyData]
    key_found: Event["CurrentKeyStore", KeyData]
    past_key_card_id: str | None = None
    current_key: KeyData | None = None
    key_reader: SimpleMFRC522
    key_reader_timeout_s: float | int
    key_relock_timeout_s: float | int
    keys_db: KeysDB
    _past_stolen_key_card_id: str | None = None
    _is_key_being_stolen: bool = False
    _key_stolen_decision_time: datetime.datetime | None = None

    _lock: RLock
    _is_key_locked: bool
    _solenoid_controller: gpiozero.DigitalOutputDevice
    _relock_key_timeout_ms: int
    _relock_key_timeout_timer: threading.Timer | None = None

    def __init__(
        self,
        key_reader: SimpleMFRC522,
        init_locked: bool,
        solenoid_controller: gpiozero.DigitalOutputDevice,
        relock_key_timeout_ms: int,
        key_reader_timeout_s: float | int,
        key_relock_timeout_s: float | int,
        keys_db: KeysDB | None = None,
    ):
        self.relock_key_timeout_event = Event(self)
        self.unauthorized_key_swap_attempted = Event(self)
        self.key_stolen = Event(self)
        self.key_found = Event(self)
        self.key_reader = key_reader
        self.key_reader_timeout_s = key_reader_timeout_s
        self.key_relock_timeout_s = key_relock_timeout_s
        self.keys_db = keys_db if keys_db is not None else KeysDB()
        self._lock = RLock()
        self._is_key_locked = init_locked
        self._solenoid_controller = solenoid_controller
        self._relock_key_timeout_ms = relock_key_timeout_ms

    def key_tick(self):
        if (
            self._is_key_being_stolen
            and datetime.datetime.now() >= self._key_stolen_decision_time
        ):
            key = self.keys_db.by_rf_id(self._past_stolen_key_card_id)
            self._is_key_being_stolen = False
            self._past_stolen_key_card_id = None
            self._key_stolen_decision_time = None
            self.key_stolen.trigger(key)

        card_id = self.key_reader.read_id(timeout=self.key_reader_timeout_s)
        # if card_id is not None:
        #     print("Past Key: ", past_key_card_id)
        #     print("Key: ", card_id)
        if self.past_key_card_id == card_id:
            self.past_key_card_id = card_id
            return

        if self._is_key_locked:
            if self.past_key_card_id is None:
                if (
                    self._is_key_being_stolen
                    and datetime.datetime.now() < self._key_stolen_decision_time
                    and self._past_stolen_key_card_id == card_id
                ):
                    logger.log(logging.INFO, "Key re-found")
                    self.past_key_card_id = card_id
                    self._is_key_being_stolen = False
                    self._past_stolen_key_card_id = None
                    self._key_stolen_decision_time = None
                    self._past_stolen_key_card_id = self.past_key_card_id
                else:
                    self.unauthorized_key_swap_attempted.trigger()
            else:
                logger.log(logging.INFO, "Key missing")
                self._is_key_being_stolen = True
                self._past_stolen_key_card_id = self.past_key_card_id
                self.past_key_card_id = None
                self._key_stolen_decision_time = (
                    datetime.datetime.now() + KEY_STOLEN_LIMIT
                )
        elif card_id is not None:
            key = self.keys_db.by_rf_id(card_id)
            if key is not None:
                self.key_found.trigger(key)
                self.past_key_card_id = card_id
                self.lock_key()
            else:
                self.unauthorized_key_swap_attempted.trigger()
        else:
            self.past_key_card_id = None

    def lock_key(self):
        with self._lock:
            logger.log(logging.INFO, "Locking key")
            self._is_key_locked = True
            self._solenoid_controller.off()
            if self._relock_key_timeout_timer != None:
                self._relock_key_timeout_timer.cancel()
                self._relock_key_timeout_timer = None

    def unlock_key(self):
        with self._lock:
            logger.log(logging.INFO, "Unlocking key")
            self._is_key_locked = False
            self._solenoid_controller.on()
            self._relock_key_timeout_timer = threading.Timer(
                self._relock_key_timeout_ms, self._on_relock_key_timeout
            )
            self._relock_key_timeout_timer.start()

    def _on_relock_key_timeout(self):
        self._relock_key_timeout_timer = None
        self.key_tick()
        self.lock_key()
        self.relock_key_timeout_event.trigger()
