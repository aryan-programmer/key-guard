from typing import Literal
from data_objects import UserData
from database import UsersDB
from event import Event
from mfrc522 import SimpleMFRC522


class UserStore:
    _past_user_card_id: str | None = None
    reader_timeout_s: float | int
    reader: SimpleMFRC522
    users_db: UsersDB
    unknown_user_found: Event["UserStore", str]
    user_card_found_but_blocked: Event["UserStore", UserData]
    user_found: Event["UserStore", tuple[UserData, Literal["login"] | Literal["card"]]]
    current_user: UserData | None = None

    def __init__(
        self,
        *,
        user_reader: SimpleMFRC522,
        user_reader_timeout_s: float | int,
        users_db: UsersDB | None = None,
    ):
        self.reader = user_reader
        self.reader_timeout_s = user_reader_timeout_s
        self.users_db = users_db if users_db is not None else UsersDB()
        self.unknown_user_found = Event(self)
        self.user_found = Event(self)
        self.user_card_found_but_blocked = Event(self)

    def tick(self):
        card_id = self.reader.read_id(timeout=self.reader_timeout_s)
        # if card_id is not None:
        #     logger.log(logging.INFO, "Past User: %s", past_user_card_id)
        #     logger.log(logging.INFO, "User: %s", card_id)
        if self._past_user_card_id == card_id:
            self._past_user_card_id = card_id
            return
        self._past_user_card_id = card_id
        if card_id is None:
            return
        user = self.users_db.by_rf_id(card_id)
        if user is not None:
            if self.current_user is not None:
                if self.current_user != user:
                    self.user_card_found_but_blocked.trigger(user)
            else:
                self.current_user = user
                self.user_found.trigger((user, "card"))
        elif card_id is not None:
            self.unknown_user_found.trigger(card_id)

    def on_user_login(self, user: UserData):
        self.current_user = user
        self.user_found.trigger((user, "login"))

    def logout_user(self):
        self.current_user = None
