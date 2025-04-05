class KeySelectionOption:
    slot_id: int
    slot_name: str
    key_name: str | None
    access_denied: bool | None

    def __init__(
        self,
        *,
        slot_id: int,
        slot_name: str,
        key_name: str | None = None,
        access_denied: bool | None = None,
    ):
        self.slot_id = slot_id
        self.slot_name = slot_name
        self.key_name = key_name
        self.access_denied = access_denied

    @staticmethod
    def make_insert_key(slot_id: int, slot_name: str):
        return KeySelectionOption(slot_id=slot_id, slot_name=slot_name)
        # return {"slotId": slot_id, "slotName": slot_name}

    @staticmethod
    def make_remove_key(slot_id: int, slot_name: str, key_name: str):
        return KeySelectionOption(
            slot_id=slot_id, slot_name=slot_name, key_name=key_name
        )
        # return {"slotId": slot_id, "slotName": slot_name, "keyName": key_name}

    @staticmethod
    def make_access_denied(slot_id: int, slot_name: str):
        return KeySelectionOption(
            slot_id=slot_id, slot_name=slot_name, access_denied=True
        )
        # return {"slotId": slot_id, "slotName": slot_name, "accessDenied": True}

    def get_json_dict(self):
        if self.access_denied:
            return {
                "slotId": self.slot_id,
                "slotName": self.slot_name,
                "accessDenied": True,
            }
        elif self.key_name is not None:
            return {
                "slotId": self.slot_id,
                "slotName": self.slot_name,
                "keyName": self.key_name,
            }
        else:
            return {
                "slotId": self.slot_id,
                "slotName": self.slot_name,
            }
