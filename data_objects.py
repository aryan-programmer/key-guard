from dataclasses import dataclass


@dataclass
class KeyData:
    id: str
    rf_id: str
    name: str

    def __format__(self, format_spec):
        return f"{self.name} ({self.id}, RFID={self.rf_id})"


@dataclass
class UserData:
    id: str
    rf_id: str
    username: str
    password: str
    name: str
    authorized_for: list[str]

    def __format__(self, format_spec):
        return f"{self.name} ({self.username}, ID={self.id}, RFID={self.rf_id})"
