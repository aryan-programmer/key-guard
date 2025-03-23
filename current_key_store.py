import datetime
import logging
from data_objects import KeyData
from database import KeysDB
from event import Event
from key_solenoid_lock import KeySolenoidLock
from logger_instance import logger
from mfrc522 import SimpleMFRC522

KEY_STOLEN_LIMIT = datetime.timedelta(seconds=1)


class CurrentKeyStore:
    unauthorized_key_swap_attempted = Event()
    key_stolen = Event()
    key_found = Event()
    past_key_card_id: str | None = None
    current_key: KeyData | None = None
    key_reader: SimpleMFRC522
    key_locker: KeySolenoidLock
    key_reader_timeout_s: float | int
    key_relock_timeout_s: float | int
    keys_db: KeysDB
    _past_stolen_key_card_id: str | None = None
    _is_key_being_stolen: bool = False
    _key_stolen_decision_time: datetime.datetime | None = None

    def __init__(
        self,
        key_reader: SimpleMFRC522,
        key_locker: KeySolenoidLock,
        key_reader_timeout_s: float | int,
        key_relock_timeout_s: float | int,
        keys_db: KeysDB | None = None,
    ):
        self.key_reader = key_reader
        self.key_locker = key_locker
        self.key_reader_timeout_s = key_reader_timeout_s
        self.key_relock_timeout_s = key_relock_timeout_s
        self.keys_db = keys_db if keys_db is not None else KeysDB()

    def key_tick(self):
        if (
            self._is_key_being_stolen
            and datetime.datetime.now() >= self._key_stolen_decision_time
        ):
            self._is_key_being_stolen = False
            self._past_stolen_key_card_id = None
            self._key_stolen_decision_time = None
            self.key_stolen.trigger()

        card_id = self.key_reader.read_id(timeout=self.key_reader_timeout_s)
        # if card_id is not None:
        #     print("Past Key: ", past_key_card_id)
        #     print("Key: ", card_id)
        if self.past_key_card_id == card_id:
            self.past_key_card_id = card_id
            return

        if self.key_locker.is_key_locked:
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
                self.key_locker.is_key_locked = True
            else:
                self.unauthorized_key_swap_attempted.trigger()
        else:
            self.past_key_card_id = None
            self.key_locker.is_key_locked = True
