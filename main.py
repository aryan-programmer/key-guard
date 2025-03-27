import logging
import threading
import time
from typing import Tuple

import gpiozero
from RPi import GPIO

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

led = gpiozero.LED(27)
# buzzer = gpiozero.TonalBuzzer(12, mid_tone=Tone("A5"))
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
    init_locked=False,
    solenoid_controller=solenoid1_controller,
    relock_key_timeout_ms=RELOCK_KEY_TIMEOUT_S,
    reader=key1_reader,
    reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
    solenoid_lock_wait_time_s=SOLENOID_LOCK_WAIT_TIME_S
)
key2_store = KeyStore(
    init_locked=False,
    solenoid_controller=solenoid2_controller,
    relock_key_timeout_ms=RELOCK_KEY_TIMEOUT_S,
    reader=key2_reader,
    reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
    solenoid_lock_wait_time_s=SOLENOID_LOCK_WAIT_TIME_S
)
user_store = UserStore(
    user_reader=user_reader,
    user_reader_timeout_s=READER_TIMEOUT_S,
)

# logger.log(logging.INFO,
#     f"Buzzer data: min: {buzzer.min_tone.frequency}, mid: {buzzer.mid_tone.frequency}, max: {buzzer.max_tone.frequency}"
# )


# def turn_off_buzzer():
#     buzzer.stop()


@key1_store.unauthorized_key_place_attempted.on
@typechecked
def on_unauthorized_key_swap_attempted(origin: KeyStore, data: str | None):
    logger.log(logging.WARNING, "Unauthorized key swap attempted: %s", data)
    led.blink(0.125, 0.125, 16)
    # buzzer.play(Tone.from_frequency(1300))
    # threading.Timer(3, turn_off_buzzer).start()


@key1_store.key_stolen.on
@typechecked
def on_key_stolen(origin: KeyStore, data: Tuple[KeyData, str | None]):
    key, replacement = data
    if replacement is not None:
        logger.log(
            logging.WARNING,
            "Key stolen: %s, with tricking replacement: %s",
            key,
            replacement,
        )
    else:
        logger.log(logging.WARNING, "Key stolen: %s", key)
    led.blink(0.125, 0.125, 8)
    # buzzer.play(Tone.from_frequency(1700))
    # threading.Timer(7, turn_off_buzzer).start()


@key1_store.key_found.on
@typechecked
def on_key_found(origin: KeyStore, key: KeyData):
    logger.log(logging.INFO, "Key found: %s", key)
    led.blink(0.25, 0.25, 4)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(1, turn_off_buzzer).start()


@user_store.user_found.on
@typechecked
def on_user_found(source: UserStore, user: UserData):
    logger.log(logging.WARNING, "User found: %s", user.name)
    led.blink(0.5, 0.5, 2)
    key1_store.unlock_key()
    # buzzer.play(Tone.from_frequency(880))
    # threading.Timer(RELOCK_KEY_TIMEOUT_S, turn_off_buzzer).start()


@user_store.unknown_user_found.on
@typechecked
def on_unknown_user_found(source: UserStore, card_id: str):
    logger.log(logging.WARNING, "Unknown user: Card ID: %s", card_id)
    led.blink(1, 1, 1)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(3, turn_off_buzzer).start()


@key1_store.relocked.on
@typechecked
def relock_key_timeout_handler(origin: KeyStore):
    logger.log(logging.INFO, "Re-locking key")
    # turn_off_buzzer()


try:
    while True:
        user_store.tick()
        key1_store.tick()
        # key2_store.key_tick()
        time.sleep(MAIN_LOOP_DELAY_S)
except Exception as ex:
    ex.with_traceback()
finally:
    key1_reader.cleanup()
    user_reader.cleanup()
    GPIO.cleanup()
    logging.shutdown()
