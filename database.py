import functools
from typing import Dict

import pyjson5

from data_objects import *
from singleton import Singleton
import bcrypt


def get_hashed_password(plain_text_password: str) -> str:
    # Hash a password for the first time
    #   (Using bcrypt, the salt is saved into the hash itself)
    return bcrypt.hashpw(plain_text_password.encode(), bcrypt.gensalt()).decode()


def check_password(plain_text_password: str, hashed_password: str) -> bool:
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    return bcrypt.checkpw(plain_text_password.encode(), hashed_password.encode())


@functools.cache
def parse_database() -> tuple[list[KeyData], list[UserData]]:
    with open("./passwords.json") as json_data:
        d = pyjson5.load(json_data)
        passwords: Dict[str, str] = {v["id"]: v["password"] for v in d["passwords"]}
    with open("./database.json") as json_data:
        d = pyjson5.load(json_data)
        keys = [
            KeyData(id=v["id"], rf_id=v["rf_id"], name=v["name"]) for v in d["keys"]
        ]
        users = [
            UserData(
                id=v["id"],
                rf_id=v["rf_id"],
                name=v["name"],
                username=v["username"],
                password=passwords[v["id"]],
                authorized_for=v["authorized_for"],
            )
            for v in d["users"]
        ]
        return keys, users


class KeysDB(Singleton):
    _keys_by_id: Dict[str, KeyData]
    _keys_by_rf_id: Dict[str, KeyData]

    def __init__(self):
        keys, _ = parse_database()
        self._keys_by_id = {v.id: v for v in keys}
        self._keys_by_rf_id = {v.rf_id: v for v in keys}

    def by_id(self, k_id: str) -> KeyData | None:
        return self._keys_by_id.get(k_id)

    def by_rf_id(self, rf_id: str) -> KeyData | None:
        return self._keys_by_rf_id.get(rf_id)


class UsersDB(Singleton):
    _users_by_id: Dict[str, UserData]
    _users_by_rf_id: Dict[str, UserData]
    _users_by_username: Dict[str, UserData]

    def __init__(self):
        _, users = parse_database()
        self._users_by_id = {v.id: v for v in users}
        self._users_by_rf_id = {v.rf_id: v for v in users}
        self._users_by_username = {v.username: v for v in users}

    def by_id(self, k_id: str) -> UserData | None:
        return self._users_by_id.get(k_id)

    def by_rf_id(self, rf_id: str) -> UserData | None:
        return self._users_by_rf_id.get(rf_id)

    def by_username(self, username: str) -> UserData | None:
        return self._users_by_username.get(username)

    def by_username_check_password(
        self, username: str, password: str
    ) -> UserData | None:
        user = self._users_by_username.get(username)
        if user is None:
            return None
        if check_password(password, user.password):
            return user
        return None
