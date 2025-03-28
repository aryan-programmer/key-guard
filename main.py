import logging
import os
import sys
import threading
import time
import traceback
from typing import Tuple

import gpiozero
from RPi import GPIO

import input_timeout
from user_store import UserStore

# from gpiozero.tones import Tone

if True:
    from typeguard import install_import_hook

    install_import_hook("key_store")
    install_import_hook("data_objects")
    install_import_hook("database")
    install_import_hook("mfrc522")
    install_import_hook("mfrc522.chip_select_lock")

from typeguard import typechecked

from key_store import KeyStore
from data_objects import UserData, KeyData
from database import UsersDB
from mfrc522 import SimpleMFRC522
from mfrc522.chip_select_lock import ChipSelectLinesLock

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
INPUT_TIMEOUT_S = 60

solenoid1_controller = gpiozero.DigitalOutputDevice(24)
solenoid2_controller = gpiozero.DigitalOutputDevice(23)
set_pin_mode()
reset_pin = gpiozero.DigitalOutputDevice(22)

reset_pin.off()
time.sleep(1)
reset_pin.on()

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
def on_key_stolen(origin: KeyStore, data: Tuple[KeyData, str | None]):
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


def get_opts_for_key_slot(user: UserData, key_store: KeyStore) -> Tuple[str, bool]:
    if key_store.current_key is None:
        return f"{key_store.slot_name}: Insert key", True
    elif key_store.current_key.id in user.authorized_for:
        return (
            f"{key_store.slot_name}: Remove key {key_store.current_key.name}",
            True,
        )
    else:
        return f"Access to {key_store.slot_name} FORBIDDED", False


def user_found_handle_input_on_seperate_thread(user: UserData):
    global is_waiting_for_user_input
    opts = [get_opts_for_key_slot(user, ks) for ks in key_stores]
    prompt_strs = "\n".join(
        f"{(i+1) if valid else ' '}: {s}" for i, (s, valid) in enumerate(opts)
    )
    prompt_str = f"""Welcome {user.name},
Please select an operation to perform from the ones listed below:
{prompt_strs}
q: Exit
You have {INPUT_TIMEOUT_S/60} minute to decide, after which you will have to authenticate again.
Enter operation> """
    try:
        res = input_timeout.input_timeout(prompt_str, INPUT_TIMEOUT_S)
        if res == "q":
            print("Quitting normally")
            logger.log(logging.INFO, "User {0} exitted prompt with no operation", user)
        else:
            try:
                v = int(res) - 1
                if opts[v][1]:
                    key_stores[v].unlock_key()
                    print(f"Unlocked {key_stores[v].slot_name}")
                    logger.log(
                        logging.INFO,
                        "User {0} entered operation: '{1}'",
                        user,
                        opts[v][0],
                    )
                else:
                    print("Error: You are not authorized for that. Signing out...")
                    logger.log(
                        logging.WARNING,
                        "User {0} entered operation: '{1}' which they are not authorized for",
                        user,
                        opts[v][0],
                    )
            except:
                print("Error: Invalid input entered. Signing out...")
                logger.log(
                    logging.WARNING, "User {0} entered an invalid operation", user
                )
    except input_timeout.InputTimeoutOccurred:
        print("Failed to enter operation in alloted time. Signing out...")
        logger.log(
            logging.WARNING, "User {0} failed to enter operation in alloted time.", user
        )
    finally:
        is_waiting_for_user_input = False


@user_store.user_found.on
@typechecked
def on_user_found(source: UserStore, user: UserData):
    global is_waiting_for_user_input
    if is_waiting_for_user_input:
        return
    is_waiting_for_user_input = True
    logger.log(logging.WARNING, "User found: {0}", user)
    threading.Thread(
        target=user_found_handle_input_on_seperate_thread, args=(user,)
    ).start()


@user_store.unknown_user_found.on
@typechecked
def on_unknown_user_found(source: UserStore, card_id: str):
    logger.log(logging.WARNING, "Unknown user: Card ID: {0}", card_id)


try:
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
