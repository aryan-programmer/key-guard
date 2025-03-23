import functools
from typing import Dict

import pyjson5

from data_objects import *
from singleton import Singleton


@functools.cache
def parse_database():
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

    def by_id(self, k_id):
        return self._keys_by_id.get(k_id)

    def by_rf_id(self, rf_id):
        return self._keys_by_rf_id.get(rf_id)


class UsersDB(Singleton):
    _users_by_id: Dict[str, UserData]
    _users_by_rf_id: Dict[str, UserData]

    def __init__(self):
        _, users = parse_database()
        self._users_by_id = {v.id: v for v in users}
        self._users_by_rf_id = {v.rf_id: v for v in users}

    def by_id(self, k_id):
        return self._users_by_id.get(k_id)

    def by_rf_id(self, rf_id):
        return self._users_by_rf_id.get(rf_id)
