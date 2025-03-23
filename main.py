import logging
import threading
import time

import gpiozero
from RPi import GPIO

# from gpiozero.tones import Tone

if True:
    from typeguard import install_import_hook

    install_import_hook("current_key_store")
    install_import_hook("data_objects")
    install_import_hook("database")
    install_import_hook("mfrc522")
    install_import_hook("mfrc522.chip_select_lock")

from typeguard import typechecked

from current_key_store import CurrentKeyStore
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

RELOCK_KEY_TIMEOUT_S = 5
READER_TIMEOUT_S = 0.5
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
key1_store = CurrentKeyStore(
    init_locked=False,
    solenoid_controller=solenoid1_controller,
    relock_key_timeout_ms=RELOCK_KEY_TIMEOUT_S,
    key_reader=key1_reader,
    key_reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
)
key2_store = CurrentKeyStore(
    init_locked=False,
    solenoid_controller=solenoid2_controller,
    relock_key_timeout_ms=RELOCK_KEY_TIMEOUT_S,
    key_reader=key2_reader,
    key_reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
)

# logger.log(logging.INFO,
#     f"Buzzer data: min: {buzzer.min_tone.frequency}, mid: {buzzer.mid_tone.frequency}, max: {buzzer.max_tone.frequency}"
# )


# def turn_off_buzzer():
#     buzzer.stop()


@key1_store.unauthorized_key_swap_attempted.on
@typechecked
def on_unauthorized_key_swap_attempted(origin: CurrentKeyStore):
    logger.log(logging.WARNING, "Unauthorized key swap attempted.")
    led.blink(0.125, 0.125, 16)
    # buzzer.play(Tone.from_frequency(1300))
    # threading.Timer(3, turn_off_buzzer).start()


@key1_store.key_stolen.on
@typechecked
def on_key_stolen(origin: CurrentKeyStore, key: KeyData):
    logger.log(logging.WARNING, "Key stolen: %s", key)
    led.blink(0.125, 0.125, 8)
    # buzzer.play(Tone.from_frequency(1700))
    # threading.Timer(7, turn_off_buzzer).start()


@key1_store.key_found.on
@typechecked
def on_key_found(origin: CurrentKeyStore, key: KeyData):
    logger.log(logging.INFO, "Key found: %s", key)
    led.blink(0.25, 0.25, 4)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(1, turn_off_buzzer).start()


@typechecked
def on_user_found(user: UserData):
    logger.log(logging.WARNING, "User found: %s", user.name)
    led.blink(0.5, 0.5, 2)
    # buzzer.play(Tone.from_frequency(880))
    # threading.Timer(RELOCK_KEY_TIMEOUT_S, turn_off_buzzer).start()


@typechecked
def on_unknown_user_found(card_id):
    logger.log(logging.WARNING, "Unknown user: Card ID: %s", card_id)
    led.blink(1, 1, 1)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(3, turn_off_buzzer).start()


@key1_store.relock_key_timeout_event.on
@typechecked
def relock_key_timeout_handler(origin: CurrentKeyStore):
    logger.log(logging.INFO, "Re-locking key")
    # turn_off_buzzer()


def user_tick():
    global past_user_card_id
    card_id = user_reader.read_id(timeout=READER_TIMEOUT_S)
    # if card_id is not None:
    #     logger.log(logging.INFO, "Past User: %s", past_user_card_id)
    #     logger.log(logging.INFO, "User: %s", card_id)
    if past_user_card_id == card_id:
        past_user_card_id = card_id
        return

    user = UsersDB().by_rf_id(card_id)
    if user is not None:
        on_user_found(user)
        key1_store.unlock_key()
    elif card_id is not None:
        on_unknown_user_found(card_id)

    past_user_card_id = card_id


try:
    while True:
        user_tick()
        key1_store.key_tick()
        # key2_store.key_tick()
        time.sleep(MAIN_LOOP_DELAY_S)
except Exception as ex:
    ex.with_traceback()
finally:
    key1_reader.cleanup()
    user_reader.cleanup()
    GPIO.cleanup()
    logging.shutdown()
