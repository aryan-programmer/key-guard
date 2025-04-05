from collections.abc import Callable
import datetime
import json
import random
import threading
import time
from typing import Literal, Union
import jwt
from websockets.sync.server import serve, ServerConnection

from data_objects import UserData
from database import UsersDB
from event import Event
from ws.key_selection_option import KeySelectionOption


class WebsocketServer:
    _main_conn: ServerConnection | None = None
    _last_jwt: str | None = None
    _secret: str
    user_key_selection_timeout_s: float | int
    users_db: UsersDB
    get_key_selection_options: Callable[[UserData], list[KeySelectionOption]]
    should_block_user_login: Callable[[], bool]
    on_key_selected: Callable[[UserData, int], bool]
    user_login: Event["WebsocketServer", UserData]
    user_login_blocked: Event["WebsocketServer", tuple[str, str]]
    user_login_failed: Event["WebsocketServer", tuple[str, str]]
    key_selection_failed: Event[
        "WebsocketServer",
        tuple[Literal["timeout"] | Literal["invalid-jwt"], str | dict, int],
    ]

    def __init__(
        self,
        *,
        secret_file: str,
        user_key_selection_timeout_s: float | int,
        get_key_selection_options: Callable[[UserData], list[KeySelectionOption]],
        should_block_user_login: Callable[[], bool],
        on_key_selected: Callable[[UserData, int], bool],
        users_db: UsersDB | None = None,
    ):
        self.users_db = users_db if users_db is not None else UsersDB()
        self.user_key_selection_timeout_s = user_key_selection_timeout_s
        self.get_key_selection_options = get_key_selection_options
        self.on_key_selected = on_key_selected
        self.should_block_user_login = should_block_user_login
        self.user_login = Event(self)
        self.user_login_blocked = Event(self)
        self.user_login_failed = Event(self)
        self.key_selection_failed = Event(self)
        with open(secret_file, "r") as r:
            self._secret = r.read()

    def _echo(self, websocket: ServerConnection):
        if self._main_conn is not None and self._main_conn is not websocket:
            self._main_conn.close()
        self._main_conn = websocket
        for message in websocket:
            event = json.loads(message)
            match event:
                case {"type": "echo"}:
                    websocket.send(message)
                case {
                    "type": "login",
                    "username": str(username),
                    "password": str(password),
                    "id": str(id),
                }:
                    if self.should_block_user_login():
                        self.user_login_blocked.trigger((username, password))
                        websocket.send(
                            json.dumps({"id": id, "type": "login", "status": "blocked"})
                        )
                    else:
                        user = self.users_db.by_username_check_password(
                            username, password
                        )
                        if user is not None:
                            self.user_login.trigger(user)
                            self._send_login_message(websocket, id, user)
                        else:
                            self.user_login_failed.trigger((username, password))
                            websocket.send(
                                json.dumps(
                                    {"id": id, "type": "login", "status": "failed"}
                                )
                            )
                case {
                    "type": "unlock-key-slot",
                    "jwt": str(enc_jwt),
                    "slotId": int(slot_id),
                    "id": str(id),
                }:
                    self._handle_unlock_key_slot(websocket, id, enc_jwt, slot_id)

    def _send_login_message(
        self, websocket: ServerConnection, req_id: str | None, user: UserData
    ):
        encoded_jwt = jwt.encode(
            {
                "username": str(user.username),
                "expiresAt": (
                    datetime.datetime.now()
                    + datetime.timedelta(seconds=self.user_key_selection_timeout_s)
                ).isoformat(),
            },
            self._secret,
            algorithm="HS256",
        )
        self._last_jwt = encoded_jwt
        v = {} if req_id is not None else {"id": req_id}
        websocket.send(
            json.dumps(
                {
                    "type": "login",
                    **v,
                    "status": "success",
                    "jwt": encoded_jwt,
                    "name": user.name,
                    "keyData": [
                        v.get_json_dict() for v in self.get_key_selection_options(user)
                    ],
                }
            )
        )

    def _handle_unlock_key_slot(
        self, websocket: ServerConnection, id: str, enc_jwt: str, slot_id: int
    ):
        if self._last_jwt != enc_jwt:
            WebsocketServer._send_unlock_key_failed(
                websocket, id, "Authentication Token is outdated"
            )
            return
        try:
            decoded_jwt = jwt.decode(enc_jwt, self._secret, algorithms=["HS256"])
            match decoded_jwt:
                case {
                    "username": str(username),
                    "expiresAt": str(expiresAt),
                }:
                    maxT = datetime.datetime.fromisoformat(expiresAt)
                    if datetime.datetime.now() < maxT:
                        user = self.users_db.by_username(username)
                        if self.on_key_selected(user, slot_id):

                            def fn():
                                websocket.send(
                                    json.dumps(
                                        {
                                            "type": "unlock-key-slot",
                                            "id": id,
                                            "status": "success",
                                        }
                                    )
                                )

                            threading.Timer(2, fn).start()
                            return
                        else:
                            WebsocketServer._send_unlock_key_failed(
                                websocket, id, "Access Denied"
                            )
                            return
                    else:
                        self.key_selection_failed.trigger(
                            ["timeout", decoded_jwt, slot_id]
                        )
                        WebsocketServer._send_unlock_key_failed(
                            websocket, id, "Timed out"
                        )
                        return
                case _:
                    self.key_selection_failed.trigger(
                        ["invalid-jwt", decoded_jwt, slot_id]
                    )
                    WebsocketServer._send_unlock_key_failed(
                        websocket, id, "Invalid JWT Format"
                    )
                    return
            WebsocketServer._send_unlock_key_failed(websocket, id)
        except jwt.InvalidSignatureError:
            self.key_selection_failed.trigger(["invalid-jwt", enc_jwt, slot_id])
            WebsocketServer._send_unlock_key_failed(
                websocket, id, "Invalid signature for JWT token"
            )
            return
        finally:
            self._last_jwt = None

    @staticmethod
    def _send_unlock_key_failed(
        websocket: ServerConnection, id: str, reason: str | None
    ):
        websocket.send(
            json.dumps(
                {
                    "id": id,
                    "type": "unlock-key-slot",
                    "status": "failed",
                    "reason": reason,
                }
            )
        )

    def serve_and_block(self):
        with serve(self._echo, "", 2000) as server:
            server.serve_forever()

    def on_user_found(self, user: UserData):
        if self._main_conn is not None:
            self._send_login_message(self._main_conn, None, user)
