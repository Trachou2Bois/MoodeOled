import threading
import time
import subprocess
import select

try:
    from RPi import GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
except ImportError:
    GPIO = None

# === Constants ===
DEBOUNCE_DELAY = 0.13
REPEAT_INTERVAL = 0.08  # intervalle en secondes entre repeat_code incrémentés

# === Shared data ===
debounce_data = {}

# === External hooks ===
show_message = None
press_callback = None

# === Repeat threads tracking ===
repeat_threads = {}
repeat_counts = {}

# --- Common repeat sender for GPIO and rotary button ---
def repeat_sender(key, channel):
    while key in repeat_counts:
        time.sleep(REPEAT_INTERVAL)
        if GPIO.input(channel) == GPIO.LOW:
            repeat_counts[key] += 1
            code = f"{repeat_counts[key]:02x}"
            process_key(key, code)
        else:
            break
    # Clean up when released
    repeat_counts.pop(key, None)
    repeat_threads.pop(key, None)

# --- GPIO button event callback ---
def gpio_event(channel, key):
    if GPIO.input(channel) == GPIO.LOW:
        if key not in repeat_threads:
            repeat_counts[key] = 0
            process_key(key, "00")  # premier appui
            t = threading.Thread(target=repeat_sender, args=(key, channel), daemon=True)
            repeat_threads[key] = t
            t.start()
    else:
        # bouton relâché
        repeat_counts.pop(key, None)
        repeat_threads.pop(key, None)

# --- Rotary button event callback ---
def rotary_button_event(channel):
    key = "KEY_PLAY"
    if GPIO.input(channel) == GPIO.LOW:
        if key not in repeat_threads:
            repeat_counts[key] = 0
            process_key(key, "00")
            t = threading.Thread(target=repeat_sender, args=(key, channel), daemon=True)
            repeat_threads[key] = t
            t.start()
    else:
        repeat_counts.pop(key, None)
        repeat_threads.pop(key, None)

# === Traitement touches avec debounce ===
def process_key(key, repeat_code):
    global debounce_data
    try:
        rep = int(repeat_code, 16)
    except Exception as e:
        if show_message:
            show_message(f"error process_key: {e}")
        print("error process_key:", e)
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

# === LIRC listener inchangé ===
def lirc_listener(process_key, config):
    try:
        proc = subprocess.Popen(
            ["irw"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        )
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
                    process_key(key, repeat_code)
    except FileNotFoundError:
        if show_message:
            show_message("error: lirc missing")
        print("error: lirc missing")
    except Exception as e:
        if show_message:
            show_message(f"error lirc listener: {e}")
        print("error lirc listener:", e)

# === Rotary encoder polling ===
def rotary_listener(pin_a, pin_b, process_key):
    last_state = (1, 1)
    while True:
        a = GPIO.input(pin_a)
        b = GPIO.input(pin_b)
        state = (a, b)
        if last_state != state:
            if last_state == (0, 0):
                if state == (0, 1):
                    process_key("KEY_VOLUMEUP", "00")
                elif state == (1, 0):
                    process_key("KEY_VOLUMEDOWN", "00")
            last_state = state
        time.sleep(0.01)

# === Entrée principale ===
def start_inputs(config, process_press, msg_hook=None):
    global show_message, press_callback
    show_message = msg_hook
    press_callback = process_press

    # LIRC
    if config.getboolean("manual", "use_lirc", fallback=True):
        threading.Thread(target=lirc_listener, args=(process_key, config), daemon=True).start()

    # GPIO boutons
    if config.getboolean("manual", "use_gpio", fallback=False):
        if GPIO is None:
            if show_message:
                show_message("error: gpio missing")
        elif config.has_section("buttons"):
            for key, pin in config.items("buttons"):
                try:
                    pin = int(pin)
                    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    GPIO.add_event_detect(
                        pin,
                        GPIO.BOTH,
                        callback=lambda ch, k=key.upper(): gpio_event(ch, k),
                        bouncetime=int(DEBOUNCE_DELAY * 1000),
                    )
                except Exception as e:
                    if show_message:
                        show_message(f"error gpio pin: {e}")
                    print("error gpio pin:", e)

    # Rotary encoder + bouton rotary
    if config.getboolean("manual", "use_rotary", fallback=False) and config.has_section("rotary") and GPIO:
        try:
            pin_a = config.getint("rotary", "pin_a")
            pin_b = config.getint("rotary", "pin_b")
            pin_btn = config.getint("rotary", "pin_btn")

            GPIO.setup(pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(pin_btn, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            threading.Thread(target=rotary_listener, args=(pin_a, pin_b, process_key), daemon=True).start()
            GPIO.add_event_detect(
                pin_btn,
                GPIO.BOTH,
                callback=rotary_button_event,
                bouncetime=int(DEBOUNCE_DELAY * 1000),
            )

        except Exception as e:
            if show_message:
                show_message(f"error rotary: {e}")
            print("error rotary:", e)
