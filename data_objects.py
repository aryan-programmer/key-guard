from dataclasses import dataclass


@dataclass
class KeyData:
    id: str
    rf_id: str
    name: str


@dataclass
class UserData:
    id: str
    rf_id: str
    name: str
    authorized_for: [str]
