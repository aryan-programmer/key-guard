import logging
import os
import sys
import threading
import time
import traceback
from typing import Literal

import gpiozero
from RPi import GPIO

import input_timeout

# from gpiozero.tones import Tone

if True:
    from typeguard import install_import_hook

    install_import_hook("user_store")
    install_import_hook("key_store")
    install_import_hook("data_objects")
    install_import_hook("database")
    install_import_hook("mfrc522")
    install_import_hook("mfrc522.chip_select_lock")
    install_import_hook("ws")
    install_import_hook("ws.server")
    install_import_hook("ws.key_selection_option")

from typeguard import typechecked

from user_store import UserStore
from ws.server import WebsocketServer
from key_store import KeyStore
from data_objects import UserData, KeyData
import database
from mfrc522 import SimpleMFRC522
from mfrc522.chip_select_lock import ChipSelectLinesLock
from ws.key_selection_option import KeySelectionOption

from logger_instance import logger


def set_pin_mode():
    pin_mode = GPIO.BCM
    gpio_mode = GPIO.getmode()
    if gpio_mode is None:
        GPIO.setmode(pin_mode)
    else:
        pin_mode = gpio_mode
    return pin_mode


# source ../.virtualenvs/key-guard/bin/activate

SOLENOID_LOCK_WAIT_TIME_S = 2
RELOCK_KEY_TIMEOUT_S = 5
READER_TIMEOUT_S = 0.1
MAIN_LOOP_DELAY_S = 1 / 10000
KEY_SELECTION_INPUT_TIMEOUT_S = 60

solenoid1_controller = gpiozero.DigitalOutputDevice(24)
solenoid2_controller = gpiozero.DigitalOutputDevice(23)
set_pin_mode()
reset_pin = gpiozero.DigitalOutputDevice(22)

reset_pin.off()
time.sleep(1)
reset_pin.on()

_: database.UsersDB
user_reader_select = gpiozero.DigitalOutputDevice(25)
key1_reader_select = gpiozero.DigitalOutputDevice(5)
key2_reader_select = gpiozero.DigitalOutputDevice(6)
lines_locks = ChipSelectLinesLock(
    [user_reader_select, key1_reader_select, key2_reader_select]
)
user_reader = SimpleMFRC522(bus=0, device=0, lock=lines_locks.individual_line_lock(0))
key1_reader = SimpleMFRC522(bus=0, device=0, lock=lines_locks.individual_line_lock(1))
key2_reader = SimpleMFRC522(bus=0, device=0, lock=lines_locks.individual_line_lock(2))
past_user_card_id: str | None = None
key1_store = KeyStore(
    slot_name="Key Slot 1",
    init_locked=False,
    solenoid_controller=solenoid1_controller,
    relock_key_timeout_ms=RELOCK_KEY_TIMEOUT_S,
    reader=key1_reader,
    reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
    solenoid_lock_wait_time_s=SOLENOID_LOCK_WAIT_TIME_S,
)
key2_store = KeyStore(
    slot_name="Key Slot 2",
    init_locked=False,
    solenoid_controller=solenoid2_controller,
    relock_key_timeout_ms=RELOCK_KEY_TIMEOUT_S,
    reader=key2_reader,
    reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
    solenoid_lock_wait_time_s=SOLENOID_LOCK_WAIT_TIME_S,
)
key_stores = [key1_store, key2_store]
user_store = UserStore(
    user_reader=user_reader,
    user_reader_timeout_s=READER_TIMEOUT_S,
)
is_waiting_for_user_input = False


@typechecked
def get_opts_for_key_slot(
    user: UserData, slot_id: int, key_store: KeyStore
) -> KeySelectionOption:
    if key_store.current_key is None:
        return KeySelectionOption.make_insert_key(slot_id, key_store.slot_name)
    elif key_store.current_key.id in user.authorized_for:
        return KeySelectionOption.make_remove_key(
            slot_id, key_store.slot_name, key_store.current_key.name
        )
    else:
        return KeySelectionOption.make_access_denied(slot_id, key_store.slot_name)


@typechecked
def get_key_selection_options(user: UserData) -> list[KeySelectionOption]:
    return [get_opts_for_key_slot(user, i + 1, ks) for i, ks in enumerate(key_stores)]


@typechecked
def on_key_selected(user: UserData, iv: int) -> bool:
    global is_waiting_for_user_input
    is_waiting_for_user_input = False
    i = iv - 1
    if not (0 <= i < len(key_stores)):
        return False
    if (
        key_stores[i].current_key is None
        or key_stores[i].current_key.id in user.authorized_for
    ):
        key_stores[i].unlock_key()
        logger.log(
            logging.INFO,
            "User {0}: Unlocked key slot '{1}' (current_key={2})",
            user,
            key_stores[i].slot_name,
            key_stores[i].current_key,
        )
        return True
    else:
        logger.log(
            logging.WARNING,
            "User {0}: Attempted to unlock '{1}' (current_key={2}) which they are not authorized for",
            user,
            key_stores[i].slot_name,
            key_stores[i].current_key,
        )
        return False


websocket_server = WebsocketServer(
    secret_file="./ws_hmac",
    user_key_selection_timeout_s=KEY_SELECTION_INPUT_TIMEOUT_S,
    get_key_selection_options=get_key_selection_options,
    should_block_user_login=lambda: is_waiting_for_user_input,
    on_key_selected=on_key_selected,
)


@key1_store.unauthorized_key_place_attempted.on
@key2_store.unauthorized_key_place_attempted.on
@typechecked
def on_unauthorized_key_swap_attempted(origin: KeyStore, data: str | None):
    logger.log(
        logging.WARNING,
        "({0}) Unauthorized key swap attempted: {1}",
        origin.slot_name,
        data,
    )


@key1_store.key_stolen.on
@key2_store.key_stolen.on
@typechecked
def on_key_stolen(origin: KeyStore, data: tuple[KeyData, str | None]):
    key, replacement = data
    if replacement is not None:
        logger.log(
            logging.WARNING,
            "({0}) Key stolen: {1}, with tricking replacement: {2}",
            origin.slot_name,
            key,
            replacement,
        )
    else:
        logger.log(logging.WARNING, "({0}) Key stolen: {1}", origin.slot_name, key)


@key1_store.key_found.on
@key2_store.key_found.on
@typechecked
def on_key_found(origin: KeyStore, key: KeyData):
    logger.log(logging.INFO, "({0}) Key found: {1}", origin.slot_name, key)


@key1_store.relocked.on
@key2_store.relocked.on
@typechecked
def relock_key_timeout_handler(origin: KeyStore):
    logger.log(logging.INFO, "({0}) Re-locking key", origin.slot_name)


def stop_waiting_for_user_input(user: UserData):
    global is_waiting_for_user_input
    if is_waiting_for_user_input:
        logger.log(
            logging.WARNING, "User {0} failed to enter operation in alloted time.", user
        )
        is_waiting_for_user_input = False


@user_store.user_found.on
@typechecked
def on_user_found(source: UserStore, user: UserData):
    global is_waiting_for_user_input
    if is_waiting_for_user_input:
        return
    is_waiting_for_user_input = True
    logger.log(logging.INFO, "User found: {0}", user)
    websocket_server.on_user_found(user)
    threading.Timer(
        function=stop_waiting_for_user_input,
        interval=KEY_SELECTION_INPUT_TIMEOUT_S,
        args=(user,),
    ).start()


@websocket_server.user_login.on
@typechecked
def on_user_login(source: WebsocketServer, user: UserData):
    global is_waiting_for_user_input
    if is_waiting_for_user_input:
        return
    is_waiting_for_user_input = True
    logger.log(logging.INFO, "User login with password: {0}", user)
    threading.Timer(
        function=stop_waiting_for_user_input,
        interval=KEY_SELECTION_INPUT_TIMEOUT_S,
        args=(user,),
    ).start()


@websocket_server.user_login_blocked.on
@typechecked
def on_user_login_blocked(source: WebsocketServer, v: tuple[str, str]):
    (username, password) = v
    logger.log(logging.INFO, "User login blocked: {0}", username)


@websocket_server.user_login_failed.on
@typechecked
def on_user_login_failed(source: WebsocketServer, v: tuple[str, str]):
    (username, password) = v
    logger.log(logging.WARNING, "User login failed: {0}", username)


@websocket_server.key_selection_failed.on
@typechecked
def on_key_selection_failed(
    source: WebsocketServer,
    v: tuple[Literal["timeout"] | Literal["invalid-jwt"], str | dict, int],
):
    global is_waiting_for_user_input
    is_waiting_for_user_input = False
    (reason, jwt, slot_id) = v
    slot_id -= 1
    if reason == "timeout":
        logger.log(
            logging.INFO,
            "Key slot {0} selection occured after time out: {1} ",
            slot_id,
            jwt,
        )
    else:
        logger.log(
            logging.WARNING,
            "Key slot {0} selection failed due to invalid authentication JWT: {1} ",
            slot_id,
            jwt,
        )


@user_store.unknown_user_found.on
@typechecked
def on_unknown_user_found(source: UserStore, card_id: str):
    logger.log(logging.WARNING, "Unknown user: Card ID: {0}", card_id)


try:
    ws_thread = threading.Thread(target=websocket_server.serve_and_block, daemon=True)
    ws_thread.start()
    while True:
        user_store.tick()
        key1_store.tick()
        key2_store.tick()
        time.sleep(MAIN_LOOP_DELAY_S)
except Exception as ex:
    traceback.print_exc()
finally:
    key1_reader.cleanup()
    key2_reader.cleanup()
    user_reader.cleanup()
    GPIO.cleanup()
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
