
import logging
import threading
import time

import gpiozero
from RPi import GPIO
# from gpiozero.tones import Tone

from current_key_store import CurrentKeyStore
from data_objects import UserData, KeyData
from database import KeysDB, UsersDB
from key_solenoid_lock import KeySolenoidLock
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
MAIN_LOOP_DELAY_S = 1 / 1000

led = gpiozero.LED(27)
# buzzer = gpiozero.TonalBuzzer(12, mid_tone=Tone("A5"))
solenoid_controller = gpiozero.DigitalOutputDevice(23)
set_pin_mode()
reset_pin = gpiozero.DigitalOutputDevice(22)

reset_pin.off()
time.sleep(1)
reset_pin.on()

user_reader_select = gpiozero.DigitalOutputDevice(5)
key_reader_select = gpiozero.DigitalOutputDevice(6)
lines_locks = ChipSelectLinesLock([user_reader_select, key_reader_select])
user_reader = SimpleMFRC522(
    bus=0, device=0, lock=lines_locks.individual_line_lock(0))
key_reader = SimpleMFRC522(
    bus=0, device=0, lock=lines_locks.individual_line_lock(1))
key_locker = KeySolenoidLock(
    init_locked=False, solenoid_controller=solenoid_controller)
past_user_card_id: str | None = None
current_key_store = CurrentKeyStore(
    key_locker=key_locker,
    key_reader=key_reader,
    key_reader_timeout_s=READER_TIMEOUT_S,
    key_relock_timeout_s=RELOCK_KEY_TIMEOUT_S,
)

# logger.log(logging.INFO,
#     f"Buzzer data: min: {buzzer.min_tone.frequency}, mid: {buzzer.mid_tone.frequency}, max: {buzzer.max_tone.frequency}"
# )


# def turn_off_buzzer():
#     buzzer.stop()


@current_key_store.unauthorized_key_swap_attempted.on
def on_unauthorized_key_swap_attempted():
    logger.log(logging.WARNING, "Unauthorized key swap attempted.")
    led.blink(0.125, 0.125, 16)
    # buzzer.play(Tone.from_frequency(1300))
    # threading.Timer(3, turn_off_buzzer).start()


@current_key_store.key_stolen.on
def on_key_stolen():
    logger.log(logging.WARNING, "Key stolen.")
    led.blink(0.125, 0.125, 8)
    # buzzer.play(Tone.from_frequency(1700))
    # threading.Timer(7, turn_off_buzzer).start()


@current_key_store.key_found.on
def on_key_found(key: KeyData):
    logger.log(logging.INFO, "Key found: %s", key)
    led.blink(0.25, 0.25, 4)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(1, turn_off_buzzer).start()


def on_user_found(user: UserData):
    logger.log(logging.WARNING, "User found: %s", user.name)
    led.blink(0.5, 0.5, 2)
    # buzzer.play(Tone.from_frequency(880))
    # threading.Timer(RELOCK_KEY_TIMEOUT_S, turn_off_buzzer).start()


def on_unknown_user_found(card_id):
    logger.log(logging.WARNING, "Unknown user: Card ID: %s", card_id)
    led.blink(1, 1, 1)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(3, turn_off_buzzer).start()


def relock_key_timeout_handler():
    logger.log(logging.INFO, "Re-locking key")
    current_key_store.key_tick()
    key_locker.is_key_locked = True
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
        key_locker.is_key_locked = False
        threading.Timer(RELOCK_KEY_TIMEOUT_S,
                        relock_key_timeout_handler).start()
    elif card_id is not None:
        on_unknown_user_found(card_id)

    past_user_card_id = card_id


def on_rfid_card_found(card_id):
    led.blink(0.75, 0.25, 3)
    logger.log(logging.WARNING, "Unknown card given: %s", card_id)


try:
    while True:
        user_tick()
        current_key_store.key_tick()
        time.sleep(MAIN_LOOP_DELAY_S)
except Exception as ex:
    ex.with_traceback()
finally:
    key_reader.cleanup()
    user_reader.cleanup()
    GPIO.cleanup()
    logging.shutdown()
