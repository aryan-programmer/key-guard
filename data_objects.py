
from dataclasses import dataclass
from typing import List


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
    authorized_for: List[str]
