#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import time
import yaml
import threading
import configparser
import sqlite3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from board import SCL, SDA
import busio
import adafruit_ssd1306

i2c = busio.I2C(SCL, SDA)
disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
width = disp.width
height = disp.height

disp.fill(0)
disp.show()

image = Image.new('1', (width, height))
draw = ImageDraw.Draw(image)

thumb_img = Image

HOME_DIR = Path.home()
MOODEOLED_DIR = HOME_DIR / "MoodeOled"
CONFIG_PATH = MOODEOLED_DIR / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

DEBUG = config.getboolean("settings", "debug", fallback=False)
LANGUAGE = config.get("settings", "language", fallback="en")
SCREEN_TIMEOUT = config.getint("settings", "screen_timeout", fallback=0)

font_title_menu = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 8.5)
font_item_menu = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
font_message = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)

message_text = None
message_start_time = 0
message_permanent = False
scroll_offset_message = 0
scroll_speed_message = 1
last_scroll_time = 0
scroll_delay = 0.05

MENU_WIDTH = 127
MENU_LINE_HEIGHT = 11
MENU_MAX_LINES = 4
MENU_MARGIN_TOP = 4
MENU_PADDING_X = 3
MENU_PADDING_Y = 2
SCROLL_SPEED_MENU = 0.1
SCROLL_SPEED_LINEAR = 0.05
SCROLL_TITLE_PADDING_END = 20

scroll_state = {
    "menu_title": {"offset": 0, "last_update": time.time()},
    "menu_item": {"offset": 0, "direction": 1, "last_update": time.time(), "pause": False, "pause_start": 0},
    "nowplaying_artist": {"offset": 0, "last_update": time.time(), "phase": "pause_start", "pause_start_time": time.time(), "pause_duration": 2},
    "nowplaying_title": {"offset": 0, "last_update": time.time(), "phase": "pause_start", "pause_start_time": time.time(), "pause_duration": 2},
    "library_title": {"offset": 0, "last_update": time.time()},
    "library_items": {"offset": 0, "direction": 1, "last_update": time.time(), "pause": False, "pause_start": 0},
    "queue_title": {"offset": 0, "last_update": time.time()},
    "queue_item": {"offset": 0, "direction": 1, "last_update": time.time(), "pause": False, "pause_start": 0},
    "message": {"offset": 0, "direction": 1, "last_update": time.time(), "total_lines": 0, "max_visible_lines": 0}
}

def reset_scroll(*keys):
    now = time.time()
    for key in keys:
        if key in scroll_state:
            scroll_state[key]["offset"] = 0
            scroll_state[key]["direction"] = 1
            scroll_state[key]["pause"] = False
            scroll_state[key]["pause_start"] = now
            scroll_state[key]["phase"] = "pause_start"
            scroll_state[key]["pause_start_time"] = now

global_state = {
    "favorite": False,
    "state": "unknown",
    "volume": "N/A",
    "clock": time.strftime("%Hh%M"),
    "random": "0",
    "repeat": "0",
    "single": "0",
    "consume": "0",
    "title": "",
    "album": "",
    "artist": "",
    "artist_album": "",
    "btsvc": "0",
    "btactive": "0",
    "airplaysvc": "0",
    "aplactive": "0",
    "spotifysvc": "0",
    "spotactive": "0",
    "slsvc": "0",
    "slactive": "0",
    "rbsvc": "0",
    "rbactive": "0",
    "pasvc": "0",
    "paactive": "0",
    "deezersvc": "0",
    "deezactive": "0",
    "upnpsvc": "0",
    "audioout": "Local"
}

def save_config_setting(key, value, section="settings"):
    key = key.strip()
    value = str(value).lower().strip()
    section = section.lower()
    if not CONFIG_PATH.exists():
        # Si fichier absent, crée un fichier minimal
        CONFIG_PATH.write_text(f"[{section}]\n{key} = {value}\n", encoding="utf-8")
        # Recharge la config
        config.read(CONFIG_PATH)
        return
    lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    in_section = False
    key_written = False
    section_found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Détection début section
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].lower()
            # Si on sort d'une section et qu'on n'a pas encore écrit la clé dans cette section
            if in_section and not key_written:
                new_lines.append(f"{key} = {value}")
                key_written = True
            in_section = (current_section == section)
            if in_section:
                section_found = True
            new_lines.append(line)
            continue
        # Si on est dans la section ciblée
        if in_section:
            # Recherche de la clé à modifier
            if (stripped.startswith(f"{key}=") or stripped.startswith(f"{key} =")) and not key_written:
                new_lines.append(f"{key} = {value}")
                key_written = True
                continue
        # Sinon on ajoute la ligne telle quelle
        new_lines.append(line)
    # Si on était dans la dernière section mais clé pas écrite
    if in_section and not key_written:
        new_lines.append(f"{key} = {value}")
        key_written = True
    # Si section absente du fichier, on l'ajoute à la fin avec la clé
    if not section_found:
        new_lines.append(f"\n[{section}]")
        new_lines.append(f"{key} = {value}")
    # Écriture finale avec saut de ligne final
    CONFIG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # Recharge la config en mémoire pour que les accès suivants soient à jour
    config.read(CONFIG_PATH)


translations = {}
def load_translations(script_name="script"):
    global translations
    translations.clear()

    lang_dir = MOODEOLED_DIR / "language"
    selected_file = lang_dir / f"{script_name}_{LANGUAGE}.yaml"
    fallback_file = lang_dir / f"{script_name}_en.yaml"

    if selected_file.exists():
        with open(selected_file, "r", encoding="utf-8") as f:
            translations.update(yaml.safe_load(f) or {})
    elif fallback_file.exists():
        print(f"Translation file not found: {selected_file.name}, using fallback: {fallback_file.name}")
        with open(fallback_file, "r", encoding="utf-8") as f:
            translations.update(yaml.safe_load(f) or {})
    else:
        print(f"No translation file found for script: {script_name}")

def t(key, **kwargs):
    template = translations.get(key, key)
    try:
        return template.format(**kwargs)
    except KeyError as e:
        if DEBUG:
            print(f"Missing placeholder {e} in key '{key}'")
        return template

def debug_error(context_key, e, silent=False):
    if DEBUG:
        msg = t(context_key, error=str(e))
        print(msg)
        if not silent:
            show_message(msg)

def is_renderer_active():
    return (
        global_state.get("btsvc") == "1"
        and global_state.get("audioout") == "Local"
        and global_state.get("btactive") == "1"
    ) or any(
        global_state.get(flag) == "1"
        for flag in (
            "aplactive", "spotactive", "slactive", "rbactive",
            "paactive", "deezactive"
        )
    )

RENDERER_PARAMS = [
    "btsvc", "btactive", "airplaysvc", "aplactive", "spotifysvc", "spotactive",
    "slsvc", "slactive", "rbsvc", "rbactive", "pasvc", "paactive","deezersvc", "deezactive",
    "inpactive", "rxactive", "upnpsvc", "audioout"
]

def load_renderer_states_from_db():
    try:
        db_path = "/var/local/www/db/moode-sqlite3.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(RENDERER_PARAMS))
        cursor.execute(f"SELECT param, value FROM cfg_system WHERE param IN ({placeholders})", RENDERER_PARAMS)
        rows = cursor.fetchall()
        conn.close()
        for param, value in rows:
            global_state[param] = value
    except Exception as e:
        debug_error("error_db", e)

def draw_custom_menu(options, selection, title="Menu", multi=None, checkmark="✓ "):
    global scroll_state
    now = time.time()

    # --- SCROLL TITLE ---
    state_t = scroll_state["menu_title"]
    if now - state_t["last_update"] > SCROLL_SPEED_LINEAR:
        title_w  = draw.textlength(title, font=font_title_menu)
        scroll_w = title_w + SCROLL_TITLE_PADDING_END
        state_t["offset"] = (state_t["offset"] + 1) % scroll_w
        state_t["last_update"] = now

    visible_lines = min(len(options), MENU_MAX_LINES)
    menu_height   = visible_lines * MENU_LINE_HEIGHT + MENU_MARGIN_TOP + 12
    x0 = (disp.width  - MENU_WIDTH)  // 2
    y0 = (disp.height - menu_height) // 2

    draw.rectangle((0, 0, disp.width, disp.height), fill=0)
    draw.rectangle((x0, y0, x0 + MENU_WIDTH, y0 + menu_height),
                   outline=255, fill=0)

    # --- DRAW TITLE ---
    bbox_title   = draw.textbbox((0, 0), title, font=font_title_menu)
    title_width  = bbox_title[2] - bbox_title[0]
    max_title_w  = MENU_WIDTH - 2 * MENU_PADDING_X
    y_title      = y0 + MENU_MARGIN_TOP

    if title_width <= max_title_w:
        x_center = x0 + (MENU_WIDTH - title_width) // 2
        draw.text((x_center, y_title), title, font=font_title_menu, fill=255)
    else:
        off    = scroll_state["menu_title"]["offset"]
        total  = title_width + SCROLL_TITLE_PADDING_END
        x_sc   = x0 + MENU_PADDING_X - off
        draw.text((x_sc, y_title),           title, font=font_title_menu, fill=255)
        draw.text((x_sc + total, y_title),   title, font=font_title_menu, fill=255)

    # --- DRAW OPTIONS ---
    start_y   = y0 + MENU_MARGIN_TOP + 10
    start_idx = max(0, selection - MENU_MAX_LINES // 2)

    for i in range(visible_lines):
        idx = start_idx + i
        if idx >= len(options):
            break

        entry    = options[idx]
        label    = entry[0] if isinstance(entry, tuple) else entry
        prefix   = checkmark if multi and label in multi else ""
        full_txt = prefix + label
        y        = start_y + i * MENU_LINE_HEIGHT

        if idx == selection:
            draw.rectangle(
                (x0 + MENU_PADDING_X - 2, y,
                 x0 + MENU_WIDTH - MENU_PADDING_X + 2, y + MENU_LINE_HEIGHT + 1),
                outline=255, fill=0
            )

            state_i = scroll_state["menu_item"]
            text_w  = draw.textlength(full_txt, font=font_item_menu)
            avail   = MENU_WIDTH - 2 * MENU_PADDING_X

            if text_w > avail and now - state_i["last_update"] > SCROLL_SPEED_MENU:
                max_off = text_w - avail
                if not state_i["pause"]:
                    state_i["offset"] += state_i["direction"]
                    if state_i["offset"] >= max_off or state_i["offset"] <= 0:
                        state_i["pause"] = True
                        state_i["pause_start"] = now
                else:
                    if now - state_i["pause_start"] > 0.5:
                        state_i["direction"] *= -1
                        state_i["offset"] = max(0, min(max_off, state_i["offset"] + state_i["direction"]))
                        state_i["pause"] = False
                state_i["last_update"] = now

            off = state_i["offset"]
            x_text = x0 + MENU_PADDING_X - off if text_w > avail else x0 + MENU_PADDING_X
            draw.text((x_text, y), full_txt, font=font_item_menu, fill=255)

        else:
            x_text = x0 + MENU_PADDING_X
            draw.text((x_text, y), full_txt, font=font_item_menu, fill=255)

def show_message(text, permanent=False):
    global message_text, message_start_time, message_permanent
    message_permanent = permanent
    message_text = text

    if permanent:
        message_start_time = float('inf')
        return

    words = text.strip().split()
    lines = []
    line = ""
    mess_width = 127
    padding = 2
    for word in words:
        test_line = (line + " " + word) if line else word
        w = font_message.getbbox(test_line)[2] - font_message.getbbox(test_line)[0]
        if w <= mess_width - 2 * padding:
            line = test_line
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)

    # 2s line, min 2s, max 30s
    per_line = 2.0
    duration = min(max(len(lines) * per_line, 2.0), 30.0)
    message_start_time = time.time() + duration

def draw_message():
    global message_text, scroll_offset_message, last_scroll_time
    if not message_text:
        return
    text = message_text
    if text is None:
        return
    mess_width = 127
    padding = 2
    line_height = font_message.getbbox("Ay")[3] + 2

    words = text.strip().split()
    lines = []
    line = ""

    for word in words:
        test_line = (line + " " + word) if line else word
        test_width = font_message.getbbox(test_line)[2] - font_message.getbbox(test_line)[0]
        if test_width <= mess_width - 2 * padding:
            line = test_line
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)

    total_text_height = len(lines) * line_height
    menu_height = height - 4
    x0 = (width - mess_width) // 2
    y0 = 2

    if total_text_height > menu_height - 2 * padding:
        now = time.time()
        if now - last_scroll_time >= scroll_delay:
            scroll_offset_message = (scroll_offset_message + scroll_speed_message) % (total_text_height + padding)
            last_scroll_time = now
        y_start = y0 + padding - scroll_offset_message
    else:
        scroll_offset_message = 0
        y_start = y0 + (menu_height - total_text_height) // 2

    draw.rectangle((x0, y0, x0 + mess_width, y0 + menu_height), outline=255, fill=0)

    for i, line in enumerate(lines):
        y = y_start + i * line_height
        if y >= y0 + padding and y + line_height <= y0 + menu_height - padding:
            text_width = font_message.getbbox(line)[2] - font_message.getbbox(line)[0]
            x = x0 + max(0, (mess_width - text_width) // 2)
            draw.text((x, y), line, font=font_message, fill=255)

def message_updater():
    global message_text, message_start_time, scroll_offset_message, message_permanent
    while True:
        if message_text and not message_permanent and time.time() >= message_start_time:
            message_text = None
            scroll_offset_message = 0
        time.sleep(1)

def start_message_updater():
    threading.Thread(target=message_updater, daemon=True).start()
