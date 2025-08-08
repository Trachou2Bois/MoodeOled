#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import threading
import time
import subprocess
import select
import os

try:
    import lgpio  # ✅ Remplace RPi.GPIO
    CHIP = lgpio.gpiochip_open(0)
except ImportError:
    lgpio = None
    CHIP = None

# === Données globales ===
debounce_data = {}
DEBOUNCE_DELAY = 0.2
show_message = None
press_callback = None
remote_mapping = {}
debug_remote = False


# === Chargement du mapping des touches IR depuis config.ini ===
def load_remote_mapping(config):
    mapping = {}
    if config.has_section("remote_mapping"):
        for moodeoled_key, user_key in config.items("remote_mapping"):
            user_key = user_key.strip().upper()
            moodeoled_key = moodeoled_key.strip().upper()
            if user_key:  # Ignorer les lignes vides
                mapping[user_key] = moodeoled_key
    return mapping


# === Gestion des appuis avec debounce et répétition ===
def process_key(key, repeat_code):
    global debounce_data
    try:
        rep = int(repeat_code, 16)
    except Exception as e:
        if show_message:
            show_message("error process_key: ", e)
        print("error process_key: ", e)
        return

    if rep == 0:
        if key not in debounce_data:
            debounce_data[key] = {"max_code": 0, "timer": None}
        else:
            debounce_data[key]["max_code"] = 0

        if debounce_data[key]["timer"] is not None:
            debounce_data[key]["timer"].cancel()

        t = threading.Timer(DEBOUNCE_DELAY, lambda: press_callback(key))
        debounce_data[key]["timer"] = t
        t.start()
        return

    if key not in debounce_data:
        debounce_data[key] = {"max_code": rep, "timer": None}
    else:
        debounce_data[key]["max_code"] = max(debounce_data[key]["max_code"], rep)

    if debounce_data[key]["timer"] is not None:
        debounce_data[key]["timer"].cancel()

    t = threading.Timer(DEBOUNCE_DELAY, lambda: press_callback(key))
    debounce_data[key]["timer"] = t
    t.start()


# === LIRC Listener ===
def lirc_listener(process_key, config):
    global remote_mapping
    try:
        proc = subprocess.Popen(["irw"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
        while True:
            rlist, _, _ = select.select([proc.stdout], [], [], 0.1)
            if rlist:
                line = proc.stdout.readline()
                if not line:
                    break
                parts = line.strip().split()
                if len(parts) >= 3:
                    key = parts[2].strip().upper()
                    repeat_code = parts[1].strip()

                    # 🔄 Remapping des touches IR si défini dans config.ini
                    if key in remote_mapping:
                        mapped = remote_mapping[key]
                        if debug_remote and mapped != key:
                            print(f"[REMOTE MAP] {key} → {mapped}")
                        key = mapped

                    process_key(key, repeat_code)
    except FileNotFoundError:
        if show_message:
            show_message("error: lirc missing")
        print("error: lirc missing")
    except Exception as e:
        if show_message:
            show_message("error lirc listener: ", e)
        print("error lirc listener: ", e)


# === GPIO Listener ===
def gpio_listener(key, pin, process_key):
    pressed_time = None
    while True:
        state = lgpio.gpio_read(CHIP, pin)
        if state == 0:  # LOW = pressed
            if pressed_time is None:
                pressed_time = time.time()
            time.sleep(0.02)
        else:
            if pressed_time:
                duration = time.time() - pressed_time
                repeat_code = "06" if duration >= 1.0 else "00"
                process_key(key, repeat_code)
                pressed_time = None
            time.sleep(0.05)


# === Rotary Encoder Listener ===
def rotary_listener(pin_a, pin_b, process_key):
    last_state = (1, 1)
    while True:
        a = lgpio.gpio_read(CHIP, pin_a)
        b = lgpio.gpio_read(CHIP, pin_b)
        state = (a, b)
        if last_state != state:
            if last_state == (0, 0):
                if state == (0, 1):
                    process_key("KEY_VOLUMEUP", "00")
                elif state == (1, 0):
                    process_key("KEY_VOLUMEDOWN", "00")
            last_state = state
        time.sleep(0.01)


def rotary_button_listener(pin_btn, process_key):
    pressed_time = None
    while True:
        state = lgpio.gpio_read(CHIP, pin_btn)
        if state == 0:  # Pressed
            if pressed_time is None:
                pressed_time = time.time()
            time.sleep(0.02)
        else:
            if pressed_time:
                duration = time.time() - pressed_time
                repeat_code = "06" if duration >= 1.0 else "00"
                process_key("KEY_PLAY", repeat_code)
                pressed_time = None
            time.sleep(0.05)


# === Entrée principale ===
def start_inputs(config, process_press, msg_hook=None):
    global show_message, press_callback, remote_mapping, debug_remote

    show_message = msg_hook
    press_callback = process_press
    debug_remote = config.getboolean("settings", "debug", fallback=False)
    remote_mapping = load_remote_mapping(config)

    # LIRC
    if config.getboolean("manual", "use_lirc", fallback=True):
        threading.Thread(target=lirc_listener, args=(process_key, config), daemon=True).start()

    # GPIO Buttons
    if config.getboolean("manual", "use_gpio", fallback=False):
        if lgpio is None:
            if show_message:
                show_message("error: lgpio missing")
        elif config.has_section("buttons"):
            for key, pin in config.items("buttons"):
                try:
                    pin = int(pin)
                    lgpio.gpio_claim_input(CHIP, pin)  # ✅ Configure en entrée
                    threading.Thread(target=gpio_listener, args=(key.upper(), pin, process_key), daemon=True).start()
                except Exception as e:
                    if show_message:
                        show_message("error gpio pin: ", e)
                    print("error gpio pin: ", e)

    # Rotary Encoder
    if config.getboolean("manual", "use_rotary", fallback=False) and config.has_section("rotary") and lgpio:
        try:
            pin_a = config.getint("rotary", "pin_a")
            pin_b = config.getint("rotary", "pin_b")
            pin_btn = config.getint("rotary", "pin_btn")

            lgpio.gpio_claim_input(CHIP, pin_a)
            lgpio.gpio_claim_input(CHIP, pin_b)
            lgpio.gpio_claim_input(CHIP, pin_btn)

            threading.Thread(target=rotary_listener, args=(pin_a, pin_b, process_key), daemon=True).start()
            threading.Thread(target=rotary_button_listener, args=(pin_btn, process_key), daemon=True).start()

        except Exception as e:
            if show_message:
                show_message("error rotary: ", e)
            print("error rotary: ", e)
