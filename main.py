import logging
import threading
import time

import gpiozero
from RPi import GPIO
from gpiozero.tones import Tone

from data_objects import UserData, KeyData
from database import KeysDB, UsersDB
from key_solenoid_lock import KeySolenoidLock
from mfrc522 import SimpleMFRC522
from mfrc522.chip_select_lock import ChipSelectLinesLock


def set_pin_mode():
    pin_mode = GPIO.BCM
    gpio_mode = GPIO.getmode()
    if gpio_mode is None:
        GPIO.setmode(pin_mode)
    else:
        pin_mode = gpio_mode
    return pin_mode


logger = logging.getLogger('mfrc522Logger')
logger.addHandler(logging.StreamHandler())
level = logging.getLevelName(logging.WARN)
logger.setLevel(level)

RELOCK_KEY_TIMEOUT_S = 5
READER_TIMEOUT_S = 0.5
MAIN_LOOP_DELAY_S = 1 / 1000

led = gpiozero.LED(27)
buzzer = gpiozero.TonalBuzzer(19, mid_tone=Tone("A5"))
solenoid_controller = gpiozero.DigitalOutputDevice(22)
set_pin_mode()
reset_pin = gpiozero.DigitalOutputDevice(26)

reset_pin.off()
time.sleep(1)
reset_pin.on()

user_reader_select = gpiozero.DigitalOutputDevice(5)
key_reader_select = gpiozero.DigitalOutputDevice(6)
lines_locks = ChipSelectLinesLock([user_reader_select, key_reader_select])
user_reader = SimpleMFRC522(bus=0, device=0, lock=lines_locks.individual_line_lock(0))
key_reader = SimpleMFRC522(bus=0, device=0, lock=lines_locks.individual_line_lock(1))
key_locker = KeySolenoidLock(init_locked=False, solenoid_controller=solenoid_controller)
past_key_card_id = None
past_user_card_id = None

print(f"Buzzer data: min: {buzzer.min_tone.frequency}, mid: {buzzer.mid_tone.frequency}, max: {buzzer.max_tone.frequency}")


def turn_off_buzzer():
    buzzer.stop()


def on_unauthorized_key_swap_attempted():
    print("Unauthorized key swap attempted.")
    led.blink(0.125, 0.125, 16)
    # buzzer.play(Tone.from_frequency(1300))
    # threading.Timer(3, turn_off_buzzer).start()


def on_key_stolen():
    print("Key stolen.")
    led.blink(0.125, 0.125, 8)
    buzzer.play(Tone.from_frequency(1700))
    threading.Timer(7, turn_off_buzzer).start()


def on_key_found(key: KeyData):
    print("Key found: ", key)
    led.blink(0.25, 0.25, 4)
    buzzer.play(Tone.from_frequency(440))
    threading.Timer(1, turn_off_buzzer).start()


def on_user_found(user: UserData):
    print("User found: ", user)
    led.blink(0.5, 0.5, 2)
    buzzer.play(Tone.from_frequency(880))
    threading.Timer(RELOCK_KEY_TIMEOUT_S, turn_off_buzzer).start()


def on_unknown_user_found(card_id):
    print("Unknown user: Card ID: ", card_id)
    led.blink(1, 1, 1)
    # buzzer.play(Tone.from_frequency(440))
    # threading.Timer(3, turn_off_buzzer).start()


def relock_key_timeout_handler():
    print("Re-locking key")
    key_locker.is_key_locked = True
    turn_off_buzzer()
    key_tick()


def user_tick():
    global past_user_card_id
    card_id = user_reader.read_id(timeout=READER_TIMEOUT_S)
    # if card_id is not None:
    #     print("Past User: ", past_user_card_id)
    #     print("User: ", card_id)
    if past_user_card_id == card_id:
        past_user_card_id = card_id
        return

    user = UsersDB().by_rf_id(card_id)
    if user is not None:
        on_user_found(user)
        key_locker.is_key_locked = False
        threading.Timer(RELOCK_KEY_TIMEOUT_S, relock_key_timeout_handler).start()
    elif card_id is not None:
        on_unknown_user_found(card_id)

    past_user_card_id = card_id


def key_tick():
    global past_key_card_id

    card_id = key_reader.read_id(timeout=READER_TIMEOUT_S)
    # if card_id is not None:
    #     print("Past Key: ", past_key_card_id)
    #     print("Key: ", card_id)
    if past_key_card_id == card_id:
        past_key_card_id = card_id
        return

    if key_locker.is_key_locked:
        if past_key_card_id is None:
            on_unauthorized_key_swap_attempted()
            pass
        else:
            on_key_stolen()
    elif card_id is not None:
        key = KeysDB().by_rf_id(card_id)
        if key is not None:
            on_key_found(key)
            key_locker.is_key_locked = True
        else:
            on_unauthorized_key_swap_attempted()
            pass

    past_key_card_id = card_id


def on_rfid_card_found(card_id):
    led.blink(0.75, 0.25, 3)
    print("Unknown card given: ", card_id)


try:
    while True:
        user_tick()
        key_tick()
        time.sleep(MAIN_LOOP_DELAY_S)
finally:
    key_reader.cleanup()
    user_reader.cleanup()
    GPIO.cleanup()
