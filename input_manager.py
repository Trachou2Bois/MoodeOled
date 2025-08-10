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

# === Données de débounce partagées ===
debounce_data = {}
DEBOUNCE_DELAY = 0.2

# Placeholders for external messaging/logging if available
show_message = None
press_callback = None

# === Traitement des touches avec gestion d'appui long/court ===
def process_key(key, repeat_code):
    global debounce_data
    try:
        rep = int(repeat_code, 16)
    except Exception as e:
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
                    process_key(key, repeat_code)
    except FileNotFoundError:
        show_message("error: lirc missing")
        print("error: lirc missing")
        #config.set("manual", "use_lirc", "false")
    except Exception as e:
        show_message("error lirc listener: ", e)
        print("error lirc listener: ", e)

# === GPIO Listener ===
def gpio_listener(key, pin, process_key):
    pressed_time = None
    while True:
        if GPIO.input(pin) == GPIO.LOW:
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

# === Rotary Encoder ===
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

def rotary_button_listener(pin_btn, process_key):
    pressed_time = None
    while True:
        if GPIO.input(pin_btn) == GPIO.LOW:
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
    global show_message, press_callback
    show_message = msg_hook
    press_callback = process_press

    if config.getboolean("manual", "use_lirc", fallback=True):
        threading.Thread(target=lirc_listener, args=(process_key, config), daemon=True).start()

    if config.getboolean("manual", "use_gpio", fallback=False):
        if GPIO is None:
            if show_message and t:
                show_message("error : gpio missing")
            #config.set("manual", "use_gpio", "false")
        elif config.has_section("buttons"):
            for key, pin in config.items("buttons"):
                try:
                    pin = int(pin)
                    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    threading.Thread(target=gpio_listener, args=(key.upper(), pin, process_key), daemon=True).start()
                except Exception as e:
                    show_message("error gpio pin: ", e)
                    print("error gpio pin: ", e)

    if config.getboolean("manual", "use_rotary", fallback=False) and config.has_section("rotary") and GPIO:
        try:
            pin_a = config.getint("rotary", "pin_a")
            pin_b = config.getint("rotary", "pin_b")
            pin_btn = config.getint("rotary", "pin_btn")

            GPIO.setup(pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(pin_btn, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            threading.Thread(target=rotary_listener, args=(pin_a, pin_b, process_key), daemon=True).start()
            threading.Thread(target=rotary_button_listener, args=(pin_btn, process_key), daemon=True).start()

        except Exception as e:
            show_message("error rotary: ", e)
            print("error rotary: ", e)
