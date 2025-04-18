import datetime
import logging
from threading import RLock
import threading
import time

import gpiozero
from data_objects import KeyData
from database import KeysDB
from event import Event
from logger_instance import logger
from mfrc522 import SimpleMFRC522

KEY_STOLEN_LIMIT = datetime.timedelta(seconds=1)


class KeyStore:
    relocked: Event["KeyStore", None]
    unauthorized_key_place_attempted: Event["KeyStore", str | KeyData]
    unknown_key_placed: Event["KeyStore", str]
    key_stolen: Event["KeyStore", tuple[KeyData, str | None]]
    key_uninserted: Event["KeyStore", KeyData]
    key_found: Event["KeyStore", KeyData]
    solenoid_locked: Event["KeyStore", None]
    past_key_card_id: str | None = None
    current_key: KeyData | None = None
    reader: SimpleMFRC522
    reader_timeout_s: float | int
    relock_timeout_s: float | int
    solenoid_lock_wait_time_s: float | int
    keys_db: KeysDB
    slot_name: str
    _past_stolen_key_card_id: str | None = None
    _is_key_being_stolen: bool = False
    _key_stolen_decision_time: datetime.datetime | None = None

    _lock: RLock
    _is_key_locked: bool
    _solenoid_controller: gpiozero.DigitalOutputDevice
    _relock_key_timeout_ms: int
    _relock_key_timeout_timer: threading.Timer | None = None

    _initialization_state: bool

    def __init__(
        self,
        *,
        slot_name: str,
        reader: SimpleMFRC522,
        init_locked: bool,
        solenoid_controller: gpiozero.DigitalOutputDevice,
        relock_key_timeout_ms: int,
        reader_timeout_s: float | int,
        key_relock_timeout_s: float | int,
        solenoid_lock_wait_time_s: float | int,
        keys_db: KeysDB | None = None,
    ):
        self.relocked = Event(self)
        self.unauthorized_key_place_attempted = Event(self)
        self.key_stolen = Event(self)
        self.key_found = Event(self)
        self.unknown_key_placed = Event(self)
        self.solenoid_locked = Event(self)
        self.key_uninserted = Event(self)
        self.slot_name = slot_name
        self.reader = reader
        self.reader_timeout_s = reader_timeout_s
        self.relock_timeout_s = key_relock_timeout_s
        self.solenoid_lock_wait_time_s = solenoid_lock_wait_time_s
        self.keys_db = keys_db if keys_db is not None else KeysDB()
        self._lock = RLock()
        self._is_key_locked = init_locked
        self._initialization_state = not init_locked
        self._solenoid_controller = solenoid_controller
        self._relock_key_timeout_ms = relock_key_timeout_ms

    def tick(self):
        # (a) If the key was being stolen and we are past the _key_stolen_decision_time threshold
        if (
            self._is_key_being_stolen
            and datetime.datetime.now() >= self._key_stolen_decision_time
        ):
            # Then someone stole the key
            key = self.keys_db.by_rf_id(self._past_stolen_key_card_id)
            self._is_key_being_stolen = False
            self._past_stolen_key_card_id = None
            self._key_stolen_decision_time = None
            self.key_stolen.trigger((key, None))
            self.current_key = None

        card_id = self.reader.read_id(timeout=self.reader_timeout_s)
        try:
            if self.past_key_card_id == card_id:
                self.past_key_card_id = card_id
                return
            # If the reader is currently locked...
            if self._is_key_locked:
                # Only one of past_key_card_id and card_id can be null simulatenously
                assert (
                    (self.past_key_card_id is None and card_id is not None)
                    or (self.past_key_card_id is not None and card_id is None)
                    or (self.past_key_card_id is not None and card_id is not None)
                )
                # If the reader is currently locked
                # And there previously was no key in the slot, (and thus currently we found a new one)
                if self.past_key_card_id is None and (
                    # (b) Check if there was a brief glitch in the reader
                    # If the last key in place has been missing for some time...
                    self._is_key_being_stolen
                    # ...for some time less than the threshold _key_stolen_decision_time
                    and datetime.datetime.now() < self._key_stolen_decision_time
                    # and the missing key is the same as the currently found one
                    and self._past_stolen_key_card_id == card_id
                ):
                    # Then there is nothing to worry about
                    logger.log(logging.INFO, "({0}) Key re-found", self.slot_name)
                    self.past_key_card_id = card_id
                    self._is_key_being_stolen = False
                    self._past_stolen_key_card_id = None
                    self._key_stolen_decision_time = None
                    self._past_stolen_key_card_id = card_id
                    return

                # If there is no key currently
                elif card_id is None:
                    # And we have a valid key inserted
                    if self.current_key is not None:
                        # Then it may just be a glitch, wait and check first, see (a) & (b) above
                        logger.log(logging.INFO, "({0}) Key missing", self.slot_name)
                        self._is_key_being_stolen = True
                        self._past_stolen_key_card_id = self.past_key_card_id
                        self._key_stolen_decision_time = (
                            datetime.datetime.now() + KEY_STOLEN_LIMIT
                        )
                    return

                else:
                    # Otherwise someone tried to pull a fast one by quickly replacing a stolen key with a new key, or just placing a new key, check which
                    if self._is_key_being_stolen:
                        # Then someone stole the key
                        key = self.keys_db.by_rf_id(self._past_stolen_key_card_id)
                        self._is_key_being_stolen = False
                        self._past_stolen_key_card_id = None
                        self._key_stolen_decision_time = None
                        self.key_stolen.trigger((key, card_id))
                        self.current_key = None
                    else:
                        key = self.keys_db.by_rf_id(card_id)
                        self.unauthorized_key_place_attempted.trigger(
                            key if key is not None else card_id
                        )

            # If we are unlocked:
            # And there is a key card
            elif card_id is not None:
                key = self.keys_db.by_rf_id(card_id)
                if key is not None:  # And the key exists:
                    # Then, we have a valid key insertion:
                    self.current_key = key
                    self.key_found.trigger(key)
                    self.lock_key()
                else:
                    # Otherwise, the key placement is invalid
                    self.unknown_key_placed.trigger(card_id)
            elif self.current_key is not None:
                # Otherwise, the validated user took away a valid key
                past_key = self.current_key
                self.current_key = None
                self.key_uninserted.trigger(past_key)
                self.lock_key()
        finally:
            self.past_key_card_id = card_id
            if self._initialization_state:
                self.lock_key(quick_lock=True)

    def lock_key(self, quick_lock: bool = False):
        with self._lock:
            logger.log(logging.INFO, "({0}) Locking key", self.slot_name)
            self._is_key_locked = True
            if self._relock_key_timeout_timer != None:
                self._relock_key_timeout_timer.cancel()
                self._relock_key_timeout_timer = None
            if self._initialization_state:
                self._initialization_state = False
            elif not quick_lock:
                time.sleep(self.solenoid_lock_wait_time_s)
            self._solenoid_controller.off()
            self.solenoid_locked.trigger()

    def unlock_key(self):
        with self._lock:
            logger.log(logging.INFO, "({0}) Unlocking key", self.slot_name)
            self._is_key_locked = False
            self._solenoid_controller.on()
            self._relock_key_timeout_timer = threading.Timer(
                self._relock_key_timeout_ms, self._on_relock_key_timeout
            )
            self._relock_key_timeout_timer.start()

    def _on_relock_key_timeout(self):
        self._relock_key_timeout_timer = None
        self.relocked.trigger()
        self.lock_key(quick_lock=True)
