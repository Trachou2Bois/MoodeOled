#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import os
import sys
import subprocess
import socket
import re
import time
import datetime
import threading
import requests
import html
import http.server
import sqlite3
import json
import queue
from pathlib import Path
from mpd import MPDClient

import core_common as core
from input_manager import start_inputs, debounce_data, process_key
from media_key_actions import handle_audio_keys, handle_custom_key, USED_MEDIA_KEYS, set_hooks as set_custom_hooks

SAVED_STREAM_PROFILE = core.config.get("settings", "stream_profile", fallback="standard")
yt_cache_path = core.MOODEOLED_DIR / "yt_cache.json"

PLS_PATH = "/var/lib/mpd/music/RADIO/Local Stream.pls"
LOGO_PATH = "/var/local/www/imagesw/radio-logos/Local Stream.jpg"
THUMB_PATH = "/var/local/www/imagesw/radio-logos/thumbs/Local Stream.jpg"
THUMB_SM_PATH = "/var/local/www/imagesw/radio-logos/thumbs/Local Stream_sm.jpg"
DB_PATH = "/var/local/www/db/moode-sqlite3.db"
STREAM_URL = "http://localhost:8080/stream.mp3"

core.load_translations(Path(__file__).stem)

now_playing_mode = False

idle_timer = time.time()
last_wake_time = 0
screen_on = True
is_sleeping = False
blocking_render = False
previous_blocking_render = False

SCROLL_SPEED_NOWPLAYING = 0.05

font_artist = core.ImageFont.truetype(core.MOODEOLED_DIR / 'Verdana.ttf', 15)
font_title = core.ImageFont.truetype(core.MOODEOLED_DIR / 'Verdana.ttf', 16)
font_vol = core.ImageFont.truetype(core.MOODEOLED_DIR / 'Verdana.ttf', 14)
font_clock = core.ImageFont.truetype(core.MOODEOLED_DIR / 'Verdana.ttf', 24)
font_temp = core.ImageFont.truetype(core.MOODEOLED_DIR / 'Verdana.ttf', 14)

menu_active = False
menu_options = [
    {"id": "remove_queue", "label": core.t("menu_remove_queue")},
    {"id": "playback_modes", "label": core.t("menu_playback_modes")},
    {"id": "power", "label": core.t("menu_power")}
]
menu_add_fav_option = [{"id": "add_fav", "label": core.t("menu_add_fav")}]
menu_remove_fav_option = [{"id": "remove_fav", "label": core.t("menu_remove_fav")}]
menu_add_songlog_option = [{"id": "add_songlog", "label": core.t("menu_add_songlog")}]
menu_search_artist_option = [{"id": "search_artist", "label": core.t("menu_search_artist")}]
menu_show_stream_queue_option = [{"id": "show_stream_queue", "label": core.t("menu_show_stream_queue")}]
menu_options_contextuel = []
menu_selection = 0
menu_context_flag = ""

playback_modes_menu_active = False
playback_modes_selection = 0
playback_modes_options = [
    {"id": "random", "label": core.t("menu_random")},
    {"id": "repeat", "label": core.t("menu_repeat")},
    {"id": "single", "label": core.t("menu_single")},
    {"id": "consume", "label": core.t("menu_consume")}
]
power_menu_active = False
power_menu_selection = 0
power_menu_options = [
    {"id": "poweroff", "label": core.t("menu_poweroff")},
    {"id": "reboot", "label": core.t("menu_reboot")},
    {"id": "reload_screen", "label": core.t("menu_reload_screen")},
    {"id": "restart_mpd", "label": core.t("menu_restart_mpd")}
]
confirm_box_active = False
confirm_box_selection = 0
confirm_box_title = core.t("title_confirm")
confirm_box_callback = None
confirm_box_options = [
    {"id": "confirm_yes", "label": core.t("menu_yes")},
    {"id": "confirm_no", "label": core.t("menu_no")}
]
tool_menu_active = False
tool_menu_selection = 0
tool_menu_options = [
    {"id": "renderers", "label": core.t("menu_renderers")},
    {"id": "show_songlog", "label": core.t("menu_show_songlog")},
    {"id": "hardware_info", "label": core.t("menu_hardware_info")},
    {"id": "configuration", "label": core.t("menu_configuration")}
]
songlog_active = False
songlog_lines = []
songlog_meta = []
songlog_selection = 0

songlog_action_active = False
songlog_action_selection = 0
songlog_action_options = [
    {"id": "play_yt_songlog", "label": core.t("menu_play_yt_songlog")},
    {"id": "queue_yt_songlog", "label": core.t("menu_queue_yt_songlog")},
    {"id": "show_info_songlog", "label": core.t("menu_show_info_songlog")},
    {"id": "delete_entry_songlog", "label": core.t("menu_delete_entry_songlog")},
    {"id": "delete_all_songlog", "label": core.t("menu_delete_all_songlog")}
]

stream_queue_active = False
stream_queue_lines = []
stream_queue_selection = 0

stream_queue = []
stream_queue_pos = 0
preload_queue = queue.Queue()
preload_queue_worker_started = False
yt_cache_lock = threading.Lock()

stream_queue_action_active = False
stream_queue_action_selection = 0
stream_queue_action_options = [
    {"id": "play_stream_queue_pos", "label": core.t("menu_play_stream_queue_pos")}
]

stream_manual_stop = False
stream_manual_skip = False
stream_transition_in_progress = False
current_ffmpeg = None
current_server = None

config_menu_active = False
config_menu_selection = 0
config_menu_options = [
    {"id": "sleep", "label": None},
    {"id": "stream_quality", "label": core.t("menu_stream_quality")},
    {"id": "language", "label": core.t("menu_language")},
    {"id": "debug", "label": core.t("menu_debug")}
]
sleep_timeout_options = [0, 15, 30, 60, 300, 600]  # en secondes
sleep_timeout_labels = {0: "Off", 15: "15s", 30: "30s", 60: "1m", 300: "5m", 600: "10m"}

stream_profile_menu_active = False
stream_profile_menu_selection = 0
stream_profile_menu_options = [
    {"id": "low", "label": core.t("stream_low"), "yt_format": core.config.get("manual", "yt_format_low", fallback="bestaudio[abr<=96][protocol!=m3u8]"), "ffmpeg_bitrate": "96k"},
    {"id": "standard", "label": core.t("stream_standard"), "yt_format": core.config.get("manual", "yt_format_standard", fallback="bestaudio[ext=m4a][protocol!=m3u8]/bestaudio[protocol!=m3u8]"), "ffmpeg_bitrate": "128k"},
    {"id": "hifi", "label": core.t("stream_hifi"), "yt_format": core.config.get("manual", "yt_format_hifi", fallback="bestaudio[ext=webm][protocol!=m3u8]/bestaudio[protocol!=m3u8]"), "ffmpeg_bitrate": "160k"}
]
hardware_info_active = False
hardware_info_selection = 0
hardware_info_lines = []

language_menu_active = False
language_menu_selection = 0
language_menu_options = [
    {"id": "en", "label": core.t("English")},
    {"id": "fr", "label": core.t("French")}
]
renderers_menu_active = False
renderers_menu_selection = 0
renderers_menu_options = [
    {"id": "bluetooth", "label": core.t("menu_renderer_bluetooth")},
    {"id": "airplay", "label": core.t("menu_renderer_airplay")},
    {"id": "upnp", "label": core.t("menu_renderer_upnp")}
]
bluetooth_menu_active = False
bluetooth_menu_selection = 0
bluetooth_menu_options = [
    {"id": "bt_toggle", "label": core.t("menu_bt_toggle")},
    {"id": "bt_scan", "label": core.t("menu_bt_scan")},
    {"id": "bt_paired", "label": core.t("menu_bt_paired")},
    {"id": "bt_audio_output", "label": core.t("menu_bt_audio_output")},
    {"id": "bt_disconnect_all", "label": core.t("menu_bt_disconnect_all")}
]
bluetooth_scan_menu_active = False
bluetooth_scan_menu_selection = 0
bluetooth_scan_menu_options = [] #doit lister ligne par ligne les périph decouvert ou "trusted"

bluetooth_paired_menu_active = False
bluetooth_paired_menu_selection = 0
bluetooth_paired_menu_options = [] #doit lister ligne par ligne les périph "paired"

bluetooth_audioout_menu_active = False
bluetooth_audioout_menu_selection = 0
bluetooth_audioout_menu_options = [
    {"id": "audioout_local", "label": core.t("menu_audioout_local")},
    {"id": "audioout_bt", "label": core.t("menu_audioout_bt")}
]
bluetooth_device_actions_menu_active = False
bluetooth_device_actions_menu_selection = 0
bluetooth_device_actions_menu_options = []

selected_bt_mac = None
wifi_extra_info = ""
eth_extra_info = ""

help_active = False
help_lines = []
help_selection = 0

icons = {
    "play": core.Image.open(core.MOODEOLED_DIR / "icons/play.png"),
    "pause": core.Image.open(core.MOODEOLED_DIR / "icons/pause.png"),
    "stop": core.Image.open(core.MOODEOLED_DIR / "icons/stop.png"),
    "random_on": core.Image.open(core.MOODEOLED_DIR / "icons/random.png"),
    "repeat_on": core.Image.open(core.MOODEOLED_DIR / "icons/repeat.png"),
    "repeat1_on": core.Image.open(core.MOODEOLED_DIR / "icons/repeat1.png"),
    "single_on": core.Image.open(core.MOODEOLED_DIR / "icons/single.png"),
    "consume_on": core.Image.open(core.MOODEOLED_DIR / "icons/consume.png"),
    "favorite": core.Image.open(core.MOODEOLED_DIR / "icons/favorite.png"),
    "bluetooth": core.Image.open(core.MOODEOLED_DIR / "icons/bluetooth.png"),
    "empty": core.Image.open(core.MOODEOLED_DIR / "icons/empty.png"),
}
icon_width = 16

last_title_seen = ""
last_artist_seen = ""

query = ""
stream_url = ""
title_yt = ""
artist_yt = ""
album_yt = ""
final_title_yt = ""

favorites_cache = []
favorites_last_mtime = 0
favorites_last_check = 0

def run_active_loop():
    if not blocking_render and not is_sleeping:
        render_screen()

def run_sleep_loop():
    global is_sleeping, screen_on
    if is_sleeping:
        return

    core.disp.fill(0)
    core.disp.show()
    core.disp.poweroff()
    screen_on = False
    is_sleeping = True

def has_internet_connection(timeout=2):
    try:
        # On tente d'ouvrir une connexion TCP vers un serveur bien connu (Google DNS)
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        return False

def update_status_info():
    global last_title_seen, last_artist_seen, menu_context_flag

    last_song_time = 0
    last_volume_time = 0
    last_fav_time = 0
    last_clock_time = 0
    last_status_time = 0
    last_renderer_check = 0

    while True:
        if is_sleeping:
            time.sleep(1)
            continue

        now = time.time()

        if now - last_renderer_check > 1:
            last_renderer_check = now
            core.load_renderer_states_from_db()

        if now - last_status_time > 0.3:
            last_status_time = now
            try:
                r = requests.get("http://localhost/command/?cmd=status", timeout=2)
                status_data = r.json()
                core.global_state["state"] = status_data.get("9", "state: unknown").split(": ")[-1].strip()
                core.global_state["repeat"] = status_data.get("1", "repeat: 0").split(": ")[-1].strip()
                core.global_state["random"] = status_data.get("2", "random: 0").split(": ")[-1].strip()
                core.global_state["single"] = status_data.get("3", "single: 0").split(": ")[-1].strip()
                core.global_state["consume"] = status_data.get("4", "consume: 0").split(": ")[-1].strip()

            except Exception as e:
                core.debug_error("error_status", e, silent=True)

        if now - last_song_time > 1:
            last_song_time = now
            try:
                r = requests.get("http://localhost/command/?cmd=get_currentsong", timeout=2)
                song_data = r.json()
                artist = html.unescape(song_data.get("artist", ""))
                album = html.unescape(song_data.get("album", ""))
                title = html.unescape(song_data.get("title", ""))
                path = song_data.get("file", "")

                if artist == 'Radio station' or path.startswith("http"):
                    menu_context_flag = "radio"
                    if path == "http://localhost:8080/stream.mp3":
                        menu_context_flag = "local_stream"
                        if stream_queue:
                            position = stream_queue_pos + 1 if 0 <= stream_queue_pos < len(stream_queue) else "?"
                            artist_album = f"{album} | {core.t('show_stream_queue_number', count=len(stream_queue), position=position)}"
                            title = final_title_yt
                        else:
                            artist_album = f"{album} | [Album: {album_yt}]" if album_yt else album
                            title = final_title_yt
                    else:
                        artist_album = album
                else:
                    menu_context_flag = "library"
                    artist_album = f"{artist} - {album}"

                if title != last_title_seen:
                    core.reset_scroll("nowplaying_title")
                    last_title_seen = title
                if artist_album != last_artist_seen:
                    core.reset_scroll("nowplaying_artist")
                    last_artist_seen = artist_album

                core.global_state["title"] = title
                core.global_state["album"] = album
                core.global_state["artist"] = artist
                core.global_state["artist_album"] = artist_album

            except Exception as e:
                core.debug_error("error_song", e, silent=True)

        if now - last_fav_time > 1:
            last_fav_time = now
            core.global_state["favorite"] = is_current_song_favorite(path)

        if now - last_volume_time > 0.5:
            last_volume_time = now
            try:
                r = requests.get("http://localhost/command/?cmd=get_volume", timeout=2)
                volume_data = r.json()
                if volume_data.get("muted") == "yes":
                    core.global_state["volume"] = "Mute"
                else:
                    core.global_state["volume"] = volume_data.get("volume", "N/A")
            except Exception as e:
                core.debug_error("error_volume", e, silent=True)

        if now - last_clock_time > 10:
            last_clock_time = now
            core.global_state["clock"] = time.strftime("%Hh%M")

        time.sleep(0.1)

def update_hardware_info():
    global hardware_info_lines

    last_temp_time = 0
    last_cpu_time = 0
    last_mem_time = 0
    last_wifi_time = 0
    last_disk_time = 0
    last_eth_time = 0

    def get_cpu_percent_avg():
        def read_stat():
            with open("/proc/stat") as f:
                for line in f:
                    if line.startswith("cpu "):
                        return list(map(int, line.strip().split()[1:]))
        s1 = read_stat()
        time.sleep(1.0)
        s2 = read_stat()
        idle1 = s1[3] + s1[4]
        idle2 = s2[3] + s2[4]
        total1 = sum(s1)
        total2 = sum(s2)
        total_diff = total2 - total1
        idle_diff = idle2 - idle1
        if total_diff == 0:
            return "Cpu: N/A"
        usage = 100.0 * (total_diff - idle_diff) / total_diff
        return f"Cpu: {usage:.0f}%"

    while hardware_info_active:
        now = time.time()

        if now - last_temp_time > 5:
            last_temp_time = now
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    temp_val = int(f.read()) / 1000
                temp = f"Temp: {temp_val:.1f}°C"
            except Exception as e:
                if core.DEBUG: print(f"error temp: {e}")
                temp = "Temp: N/A"

        if now - last_cpu_time > 1:
            last_cpu_time = now
            try:
                cpu = get_cpu_percent_avg()
            except Exception as e:
                if core.DEBUG: print(f"error Cpu: {e}")
                cpu = "Cpu: N/A"

        if now - last_mem_time > 3:
            last_mem_time = now
            zram_line = "Zram: N/A"
            swap_line = "Swap: None"
            try:
                with os.popen("free -m") as f:
                    lines = f.readlines()
                if len(lines) > 1:
                    ram_line = lines[1].split()
                    total = int(ram_line[1])
                    used = int(ram_line[2])
                    mem = f"Mem: {used}/{total} MB"
                else:
                    mem = "Mem: N/A"
            except Exception as e:
                if core.DEBUG: print(f"error Mem: {e}")
                mem = "Mem: N/A"

            try:
                with os.popen("zramctl") as f:
                    lines = f.readlines()
                for line in lines:
                    if line.startswith("/dev/zram"):
                        parts = line.split()
                        if len(parts) >= 5:
                            disksize = parts[2]
                            data = parts[3]
                            comp = parts[4]
                            zram_line = f"Zram: {data} / {disksize} (cmp: {comp})"
                        break
            except Exception as e:
                if core.DEBUG: print(f"error Zram: {e}")
                zram_line = "Zram: N/A"

            try:
                with open("/proc/swaps", "r") as f:
                    lines = f.readlines()
                if len(lines) > 1:
                    for line in lines[1:]:
                        if "zram" not in line:
                            parts = line.split()
                            if len(parts) >= 4:
                                total = int(parts[2]) // 1024
                                used = int(parts[3]) // 1024
                                swap_line = f"Swap: {used}/{total} MB"
                            break
            except Exception as e:
                if core.DEBUG: print(f"error Swap: {e}")
                swap_line = "Swap: N/A"

        if now - last_wifi_time > 2:
            global wifi_extra_info
            last_wifi_time = now
            wifi = "WiFi: N/A"
            wifi_extra_info = ""
            ap_mode = False
            ssid = None
            ip_addr = None

            try:
                iw_info = os.popen("iw dev wlan0 info 2>/dev/null").read()
                if "type AP" in iw_info:
                    ap_mode = True
                    for line in iw_info.splitlines():
                        if "ssid" in line.lower():
                            ssid = line.strip().split()[-1]
                            break
                    wifi = "Access Point"

                else:
                    with os.popen("iwconfig wlan0 2>/dev/null") as f:
                        for line in f:
                            if "Link Quality" in line:
                                parts = line.strip().split("Link Quality=")
                                if len(parts) > 1:
                                    quality = parts[1].split()[0]
                                    if "/" in quality:
                                        val, max_ = map(int, quality.split("/"))
                                        if max_ != 0:
                                            wifi = f"WiFi: {round(100 * val / max_)}%"

                    with os.popen("iwgetid -r") as f:
                        ssid = f.read().strip()

                with os.popen("ip addr show dev wlan0") as f:
                    for line in f:
                        if "inet " in line:
                            ip_addr = line.strip().split()[1].split("/")[0]
                            break

                if ap_mode:
                    wifi_extra_info = core.t("info_wifi_ap", ssid=ssid or "AP", ip=ip_addr or "N/A")
                    if has_internet_connection():
                        wifi_extra_info += f" | {core.t('info_internet_ok')}"
                    else:
                        wifi_extra_info += f" | {core.t('info_no_internet')}"
                elif ssid:
                    wifi_extra_info = core.t("info_wifi_connected", ssid=ssid, ip=ip_addr or "N/A")
                    if has_internet_connection():
                        wifi_extra_info += f" | {core.t('info_internet_ok')}"
                    else:
                        wifi_extra_info += f" | {core.t('info_no_internet')}"
                else:
                    wifi_extra_info = core.t("info_wifi_disconnected")

            except Exception as e:
                wifi = "Wifi: N/A"
                wifi_extra_info = ""
                core.debug_error("error_wifi_status", e)

        if now - last_eth_time > 2:
            global eth_extra_info
            last_eth_time = now
            eth = None
            eth_extra_info = ""
            try:
                if os.path.exists("/sys/class/net/eth0"):
                    with os.popen("ip addr show eth0") as f:
                        output = f.read()
                    if "inet " in output:
                        ip_line = [line for line in output.splitlines() if "inet " in line][0]
                        ip = ip_line.strip().split()[1].split("/")[0]
                        eth = f"Eth: {ip}"
                        if has_internet_connection():
                            eth_extra_info = core.t("info_internet_ok")
                        else:
                            eth_extra_info = core.t("info_no_internet")
                    else:
                        eth = core.t("menu_eth_disconnected")
            except Exception as e:
                eth = None  # Ne pas afficher si erreur
                core.debug_error("error_eth_status", e)

        if now - last_disk_time > 30:
            last_disk_time = now
            try:
                with os.popen("df -h /") as f:
                    lines = f.readlines()
                if len(lines) > 1:
                    parts = lines[1].split()
                    used, total, avail = parts[2], parts[1], parts[3]
                    disk = f"Root: {used}/{total} (free: {avail})"
                else:
                    disk = "Root: N/A"
            except Exception as e:
                if core.DEBUG: print(f"error Disk: {e}")
                disk = "Root: N/A"

            try:
                mpd_mounts = []
                with os.popen("df -h -x tmpfs -x devtmpfs") as f:
                    lines = f.readlines()[1:]
                for line in lines:
                    parts = line.split()
                    if len(parts) < 6:
                        continue
                    mount_point = parts[5]
                    if not (mount_point.startswith("/media/") or mount_point.startswith("/mnt/")):
                        continue
                    used, total, avail = parts[2], parts[1], parts[3]
                    name = os.path.basename(mount_point)
                    mpd_mounts.append(f"{name}: {used}/{total} (free: {avail})")

                def is_usb_mount(name, mount_point):
                    lower = name.lower()
                    return (
                        mount_point.startswith("/media/") or
                        "usb" in lower or
                        "sda" in lower or
                        "flash" in lower or
                        "stick" in lower
                    )

                mpd_mounts.sort(key=lambda line: (
                    is_usb_mount(line.split(":")[0], line),
                    line.lower()
                ))
            except Exception as e:
                if core.DEBUG: print(f"error Disk: {e}")
                mpd_mounts = ["Storage: N/A"]

        hardware_info_lines = [temp, cpu, wifi, mem, zram_line, swap_line, disk]
        if eth:
            hardware_info_lines.insert(3, eth)  # Facultatif, pour garder l’ordre logique
        hardware_info_lines += mpd_mounts

def set_mpd_state(option, value):
    try:
        client = MPDClient()
        client.timeout = 2
        client.connect("localhost", 6600)
        if option == "random":
            client.random(value)
        elif option == "repeat":
            client.repeat(value)
        elif option == "single":
            client.single(value)
        elif option == "consume":
            client.consume(value)
        client.close()
        client.disconnect()
    except Exception as e:
        core.debug_error("error_mpd", e)

def get_favorites_playlist_name():
    try:
        conn = sqlite3.connect("/var/local/www/db/moode-sqlite3.db")
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cfg_system WHERE param = 'favorites_name'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "Favorites"
    except Exception as e:
        core.debug_error("error_db", e)
        return "Favorites"

core.global_state["favorites_playlist"] = get_favorites_playlist_name()

def is_current_song_favorite(path):
    global favorites_cache, favorites_last_mtime, favorites_last_check
    now = time.time()
    fav_name = core.global_state.get("favorites_playlist", "Favorites")
    fav_path = f"/var/lib/mpd/playlists/{fav_name}.m3u"

    if now - favorites_last_check < 3:
        return path in favorites_cache

    favorites_last_check = now
    try:
        mtime = os.path.getmtime(fav_path)
        if mtime != favorites_last_mtime:
            with open(fav_path, "r") as f:
                favorites_cache = set(f.read().splitlines())
            favorites_last_mtime = mtime
        return path in favorites_cache
    except Exception as e:
        core.debug_error("error_favorite", e)
        return False

def toggle_favorite():
    global favorites_last_check
    fav_name = core.global_state.get("favorites_playlist", "Favorites")

    try:
        client = MPDClient()
        client.timeout = 2
        client.idletimeout = None
        client.connect("localhost", 6600)

        song = client.currentsong()
        file_path = song.get("file")

        if not file_path:
            core.show_message(core.t("info_no_track"))
            client.close()
            client.disconnect()
            return

        try:
            client.listplaylist(fav_name)
        except:
            client.save(fav_name)

        playlist = client.listplaylist(fav_name)

        if file_path in playlist:
            client.command_list_ok_begin()
            client.playlistdelete(fav_name, playlist.index(file_path))
            client.command_list_end()
            if core.DEBUG: print("✓ Removed from Favorites")
        else:
            client.playlistadd(fav_name, file_path)
            if core.DEBUG: print("✓ Added to Favorites")

        client.close()
        client.disconnect()
        favorites_last_check = 0

    except Exception as e:
        core.debug_error("error_mpd", e)

def remove_from_queue():
    try:
        client = MPDClient()
        client.connect("localhost", 6600)

        song = client.currentsong()
        pos = song.get("pos")

        if pos is not None:
            client.delete(int(pos))
            core.show_message(core.t("info_removed_queue"))

        client.close()
        client.disconnect()

    except Exception as e:
        core.debug_error("error_mpd", e)

def search_artist_from_now():
    artist = core.global_state.get("artist", "").strip()
    if not artist:
        core.show_message(core.t("error_search_artist_generic"))
        return

    artist_words = artist.split()
    if len(artist_words) > 2:
        artist = " ".join(artist_words[:2])
    artist = artist.lower()

    try:
        override_path = core.MOODEOLED_DIR / ".search_artist"
        with open(override_path, "w", encoding="utf-8") as f:
            f.write(artist)
        os.chmod(override_path, 0o664)
        os.chown(override_path, os.getuid(), os.getgid())

        core.show_message(core.t("info_search_artist", artist=artist))
        time.sleep(2)
        subprocess.call(["sudo", "systemctl", "start", "navoled.service"])
        subprocess.call(["sudo", "systemctl", "stop", "nowoled.service"])
    except Exception as e:
        core.debug_error("error_search_artist", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def ensure_songlog_file():
    try:
        path = core.MOODEOLED_DIR / "songlog.txt"
        if not path.exists():
            path.touch(mode=0o664, exist_ok=True)
            os.chown(path, os.getuid(), os.getgid())
    except Exception as e:
        core.debug_error("error_create_songlog", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def log_song():
    artist = core.global_state.get('artist', 'Unknown')
    title = core.global_state.get('title', 'Unknown')
    album = core.global_state.get('album', 'Unknown')
    now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    # Format : Artist - Title [radio name | Date]
    if artist == 'Radio station':
        main = f"{title}"
    else:
        main = f"{artist} - {title}"
    suffix = f"[{album} | {now}]"
    songlog_line = f"{main} {suffix}\n"
    ensure_songlog_file()
    with open(core.MOODEOLED_DIR / 'songlog.txt', 'a') as f:
        f.write(songlog_line)
    core.show_message(core.t("info_logged_title"))
    if core.DEBUG:
        print("Saved:", songlog_line.strip())

def show_songlog():
    global songlog_lines, songlog_meta
    try:
        ensure_songlog_file()
        path = core.MOODEOLED_DIR / "songlog.txt"
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines = [html.unescape(line.strip()) for line in lines if line.strip()]
        if not lines:
            core.show_message(core.t("info_empty_songlog"))
            songlog_lines = []
            songlog_meta = []
            return
        entries = lines[-50:][::-1]
        songlog_lines = []
        songlog_meta = []
        for line in entries:
            if "[" in line and "]" in line:
                text, meta = line.rsplit("[", 1)
                songlog_lines.append(text.strip())
                songlog_meta.append(meta.rstrip("] "))
            else:
                songlog_lines.append(line)
                songlog_meta.append("")
        prune_yt_cache_to_songlog()
    except Exception as e:
        core.debug_error("error_rd_songlog", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def confirm_delete_all_songlog(cancel=False):
    if cancel:
        global songlog_active
        core.show_message(core.t("info_cancelled"))
        show_songlog()
        if not songlog_lines:
            tool_menu_active = True
        else:
            songlog_active = True
        core.reset_scroll("menu_item")
    else:
        delete_all_songlog()

def delete_all_songlog():
    global songlog_lines, songlog_selection, songlog_active
    try:
        ensure_songlog_file()
        path = core.MOODEOLED_DIR / "songlog.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("")  # Vide le fichier
        songlog_lines = []
        songlog_meta = []
        songlog_selection = 0
        core.show_message(core.t("info_all_deleted"))
        time.sleep(2)
        show_songlog()
    except Exception as e:
        core.debug_error("error_rm_all_songlog", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def delete_songlog_entry(index_from_display):
    global songlog_lines, songlog_selection
    global stream_queue, stream_queue_pos
    try:
        path = core.MOODEOLED_DIR / "songlog.txt"

        # Assure que le fichier est accessible et songlog_lines aussi
        with open(path, "r", encoding="utf-8") as f:
            all_lines = [ln.rstrip("\n") for ln in f if ln.strip()]

        if not all_lines or not songlog_lines:
            core.show_message(core.t("info_nothing_delete"))
            return

        # Récupérer la ligne à supprimer dans songlog_lines
        target_line = songlog_lines[index_from_display]
        idx_abs = index_from_display  # index dans songlog_lines et stream_queue

        # Vérifier si c'est la piste en cours de lecture
        if stream_queue and 0 <= stream_queue_pos < len(stream_queue):
            playing_index = stream_queue[stream_queue_pos]
            if 0 <= playing_index < len(songlog_lines):
                delete_current = {songlog_lines[playing_index]}

        # Si on supprime la piste en cours, passer à la suivante
        if delete_current and stream_queue:
            if core.DEBUG:
                print("♻️  Track in play was deleted – skipping to next")
            next_stream(manual_skip=True)

        new_all_lines = []
        for ln in all_lines:
            if ln.startswith(target_line):
                # C'est la ligne à supprimer, on l'ignore
                continue
            new_all_lines.append(ln)

        with open(path, "w", encoding="utf-8") as f:
            for ln in new_all_lines:
                f.write(ln + "\n")

        # Mise à jour de songlog_lines : suppression par indice
        songlog_lines.pop(idx_abs)

        # Mise à jour de stream_queue : suppression des indices égaux et ajustement des autres
        new_queue = []
        for i in stream_queue:
            if i == idx_abs:
                continue
            new_queue.append(i - 1 if i > idx_abs else i)

        # Ajuster la position dans la queue
        removed_before_pos = len(stream_queue) - len(new_queue)
        if stream_queue_pos >= len(new_queue):
            stream_queue_pos = max(0, len(new_queue) - 1)
        elif removed_before_pos and stream_queue_pos > 0:
            stream_queue_pos = max(0, stream_queue_pos - removed_before_pos)
        stream_queue = new_queue

        core.show_message(core.t("info_entry_deleted"))
        time.sleep(1)
        show_songlog()

        if songlog_selection >= len(songlog_lines):
            songlog_selection = max(0, len(songlog_lines) - 1)

    except Exception as e:
        core.debug_error("error_rm_songlog", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def prune_yt_cache_to_songlog():
    cache_path = core.MOODEOLED_DIR / "yt_cache.json"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            yt_cache = json.load(f)
    except:
        return
    # On garde uniquement les clés encore présentes dans songlog_lines
    valid_keys = set(line.strip() for line in songlog_lines)
    removed = 0
    for key in list(yt_cache.keys()):
        if key not in valid_keys:
            del yt_cache[key]
            removed += 1
    if removed:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(yt_cache, f, indent=2)
        if core.DEBUG:
            print(f"Pruned {removed} entries from yt_cache (not in songlog)")

def ensure_local_stream():
    # Copy logo if present (optional)
    if os.path.exists(core.MOODEOLED_DIR / "local-stream.jpg") and not os.path.exists(LOGO_PATH):
        if core.DEBUG:
            print("Copying Local Stream logo...")
        subprocess.run(["sudo", "cp", core.MOODEOLED_DIR / "local-stream.jpg", LOGO_PATH])
        subprocess.run(["sudo", "chmod", "777", LOGO_PATH])
        subprocess.run(["sudo", "chown", "root:root", LOGO_PATH])

        # Create large thumbnail (same as original logo)
        if core.DEBUG:
            print("Creating thumbnails...")
        subprocess.run(["sudo", "cp", core.MOODEOLED_DIR / "local-stream.jpg", THUMB_PATH])
        subprocess.run(["sudo", "chmod", "777", THUMB_PATH])
        subprocess.run(["sudo", "chown", "root:root", THUMB_PATH])

        # Create small thumbnail (80x80)
        img = core.thumb_img.open(core.MOODEOLED_DIR / "local-stream.jpg")
        img.thumbnail((80, 80))
        img = img.convert("RGB")  # Ensure JPEG format
        temp_thumb_sm = "/tmp/local-stream-thumb-sm.jpg"
        img.save(temp_thumb_sm, "JPEG")
        subprocess.run(["sudo", "cp", temp_thumb_sm, THUMB_SM_PATH])
        subprocess.run(["sudo", "chmod", "777", THUMB_SM_PATH])
        subprocess.run(["sudo", "chown", "root:root", THUMB_SM_PATH])

    # Check database entry
    result = subprocess.run(
        ["sqlite3", DB_PATH, f"SELECT COUNT(*) FROM cfg_radio WHERE station='{STREAM_URL}';"],
        capture_output=True,
        text=True
    )
    if result.stdout.strip() == "0":
        if core.DEBUG:
            print("Inserting Local Stream into database...")
        sql_insert = f"""
        INSERT INTO cfg_radio (
            station, name, type, logo, genre, broadcaster, language,
            country, region, bitrate, format, geo_fenced, home_page, monitor
        ) VALUES (
            '{STREAM_URL}',
            'Local Stream',
            'r',
            'local',
            '',
            '',
            '',
            '',
            '',
            '128',
            'MP3',
            'No',
            '',
            'No'
        );
        """
        subprocess.run(f"echo \"{sql_insert}\" | sudo sqlite3 {DB_PATH}", shell=True, check=True)

    # Create .pls file if missing
    if not os.path.exists(PLS_PATH):
        if core.DEBUG:
            print("Creating Local Stream .pls file...")
        pls_content = """[playlist]
File1=http://localhost:8080/stream.mp3
Title1=Local Stream
Length1=-1
NumberOfEntries=1
Version=2
"""
        subprocess.run(f"echo '{pls_content}' | sudo tee '{PLS_PATH}' > /dev/null", shell=True, check=True)
        subprocess.run(["sudo", "chmod", "777", PLS_PATH])
        subprocess.run(["sudo", "chown", "root:root", PLS_PATH])
        subprocess.run(f"sudo touch '{PLS_PATH}'", shell=True, check=True)
        subprocess.run(["sudo", "php", core.MOODEOLED_DIR / "update_local_stream.php", STREAM_URL, "Local Stream", "r", "128", "MP3"])

    else:
        if core.DEBUG:
            print("Local Stream already exists in database.")

def check_stream_format(profile_id, yt_format, preload=False):
    suspicious = (
        not yt_format
        or yt_format.strip() in {"140", "251", "bestaudio"}
        or ("[protocol" not in yt_format and "/" not in yt_format)
    )
    if suspicious:
        if not preload:
            core.show_message(core.t("warning_stream_format", profile=profile_id, fmt=yt_format))
        if core.DEBUG:
            print(f"⚠ [Warning] Suspicious yt_format for '{profile_id}': {yt_format}")

def preload_worker():
    while True:
        index = preload_queue.get()
        if core.DEBUG:
            print("-  -  -  -  -  -  -  -  -")
            print(f"⚪ Preloading track index {index}")
        try:
            yt_search_track(index, preload=True)
        except Exception as e:
            core.debug_error("preload_yt", e)
        time.sleep(0.5)
        preload_queue.task_done()

def play_all_songlog_from_queue():
    global stream_queue, stream_queue_pos, preload_queue_worker_started
    if not songlog_lines:
        core.show_message(core.t("info_empty_songlog"))
        return
    for i in range(len(songlog_lines)):
        stream_queue.append(i)
    core.show_message(core.t("info_stream_queue_full", count=len(stream_queue)))
    time.sleep(1.5)
    stream_queue_pos = 0
    yt_search_track(stream_queue[0])
    # Lancer le preload worker une seule fois
    if not preload_queue_worker_started:
        threading.Thread(target=preload_worker, daemon=True).start()
        preload_queue_worker_started = True
    for i in stream_queue[1:]:
        preload_queue.put(i)

def next_stream(manual_skip=False):
    global stream_queue_pos, stream_manual_skip, stream_transition_in_progress
    if stream_transition_in_progress:
        if core.DEBUG:
            print("⚠️ next_stream ignored (stream already launching)")
        return
    stream_queue_pos += 1
    if stream_queue_pos < len(stream_queue):
        stream_transition_in_progress = True
        stream_manual_skip = manual_skip
        next_index = stream_queue[stream_queue_pos]
        core.show_message(core.t("info_next_stream", pos=stream_queue_pos + 1, total=len(stream_queue)))
        if core.DEBUG:
            print("-------------------------Next Stream----------------------------------")
            print(f"⏭️ Next stream from queue: {next_index}")
            print(f"[next_stream] manual_skip = {manual_skip}")
        yt_search_track(next_index, preload=False)
    else:
        core.show_message(core.t("info_end_queue"))
        if core.DEBUG:
            print("✅ End of stream queue")

def previous_stream(manual_skip=True):
    global stream_queue_pos, stream_manual_skip, stream_transition_in_progress
    if stream_transition_in_progress:
        if core.DEBUG:
            print("⚠️ previous_stream ignored (stream already launching)")
        return
    previous_index = stream_queue_pos - 1
    if previous_index >= 0:
        stream_transition_in_progress = True
        stream_manual_skip = manual_skip
        stream_queue_pos = previous_index
        core.show_message(core.t("info_prev_stream", pos=stream_queue_pos + 1, total=len(stream_queue)))
        if core.DEBUG:
            print("-------------------------Previous Stream----------------------------------")
            print(f"⏮️ Previous stream from queue: {previous_index}")
            print(f"[prev_stream] manual_skip = {manual_skip}")
        yt_search_track(previous_index, preload=False)
    else:
        core.show_message(core.t("info_top_queue"))
        if core.DEBUG:
            print("✅ Top of stream queue")

def set_stream_manual_stop(manual_stop=True):
    global stream_manual_stop
    stream_manual_stop = manual_stop

def yt_search_track(index, preload=False, _fallback_attempt=False, local_query=None):
    global stream_url, final_title_yt, album_yt, artist_yt, query, blocking_render, stream_transition_in_progress

    core.load_renderer_states_from_db()
    if core.is_renderer_active() and not preload:
        if core.DEBUG:
            print("Renderer active – aborting yt_search_track()")
        return

    if not preload:
        stop_current_stream()

    # Lecture du profil
    stream_profile_selected = next(
        (item for item in stream_profile_menu_options if item["id"] == SAVED_STREAM_PROFILE),
        stream_profile_menu_options[1]
    )
    check_stream_format(stream_profile_selected["id"], stream_profile_selected["yt_format"], preload)

    if local_query is None:
        if index >= len(songlog_lines):
            if not preload:
                core.show_message(core.t("info_invalid_index"))
            return
        local_query = songlog_lines[index].strip()

    if core.DEBUG:
        print(f"→ Search for: {local_query}")

    yt_cache = {}

    # Chargement thread-safe du cache
    with yt_cache_lock:
        try:
            with open(yt_cache_path, "r", encoding="utf-8") as f:
                yt_cache = json.load(f)
        except:
            yt_cache = {}

    cache_entry = yt_cache.get(local_query)
    url_expired = False

    if cache_entry and cache_entry.get("resolved") and cache_entry.get("url"):
        expire_ts = cache_entry.get("expire_ts")
        expire_str = cache_entry.get("expires", "?")
        now_ts = int(time.time())

        if expire_ts is None:
            url_expired = True
            if core.DEBUG:
                print("❓ No expire_ts in cache – assuming expired")
        elif now_ts >= expire_ts:
            url_expired = True
            if core.DEBUG:
                print(f"🟢 Cached URL expired\n   Expired at: {expire_str}\n   Now       : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            if core.DEBUG:
                print(f"✓ Cached URL still valid until {expire_str}")

        if not url_expired:
            if core.DEBUG:
                print(f"Using cached result for: {local_query}")
            if not preload:
                stream_url = cache_entry["url"]
                final_title_yt = cache_entry["title"]
                artist_yt = cache_entry["artist"]
                album_yt = cache_entry.get("album", "")
                core.load_renderer_states_from_db()
                if core.is_renderer_active():
                    if core.DEBUG:
                        print("Renderer active – aborting launch of stream_songlog_entry()")
                    return
                try:
                    stream_songlog_entry()
                finally:
                    stream_transition_in_progress = False
                    stream_manual_skip = False
            return
    else:
        if core.DEBUG:
            print("❓ No entry in cache")

    # Si pas dans le cache ou expiré : yt-dlp
    if not preload:
        core.message_text = core.t("info_search_yt", query=local_query)
        core.message_permanent = True
        blocking_render = True
        time.sleep(0.05)
        render_screen()

    from yt_dlp import YoutubeDL
    try:
        ydl_opts = {
            'quiet': True,
            'default_search': 'ytsearch',
            'noplaylist': True,
            'format': stream_profile_selected["yt_format"],
            'no_warnings': True
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(local_query, download=False)
            video = info['entries'][0] if '_type' in info else info

            resolved_url = video['url']
            title_raw = video.get("track") or video.get("title") or "Unknown"
            album = video.get("album")
            duration = video.get("duration")
            webpage_url = video.get("webpage_url")

            artist_candidates = {
                "artist": video.get("artist"),
                "album_artist": video.get("album_artist"),
                "composer": video.get("composer"),
                "creator": video.get("creator"),
                "uploader": video.get("uploader"),
            }

            if " - " in local_query:
                artist_query, title_query = map(str.strip, local_query.split(" - ", 1))
            else:
                artist_query = local_query.strip()
                title_query = ""

            artist_match = next((v for v in artist_candidates.values() if v and artist_query.lower() in v.lower()), None)

            if artist_query.lower() in title_raw.lower():
                title_final = title_raw
                artist_final = artist_query
            elif artist_match:
                title_final = f"{artist_query} - {title_raw}"
                artist_final = artist_query
            else:
                title_final = f"{title_raw} - ({artist_query} ?)"
                artist_final = f"Unknown / maybe {artist_query}"

            expire_ts = None
            expire_str = None
            match = re.search(r"[?&]expire=(\d+)", resolved_url)
            if match:
                expire_ts = int(match.group(1))
                expire_str = datetime.datetime.fromtimestamp(expire_ts).strftime("%Y-%m-%d %H:%M:%S")

            if core.DEBUG:
                print(f"[yt-dlp] title: {title_raw}")
                print(f"[yt-dlp] album: {album}")
                print(f"[yt-dlp] final-title: {title_final}")
                print(f"[yt-dlp] duration: {duration}")
                print(f"[yt-dlp] expire at: {expire_str}")
                #print(f"[yt-dlp] url: {resolved_url}")

            # Sauvegarde dans le cache (sous verrou)
            with yt_cache_lock:
                yt_cache[local_query] = {
                    "title": title_final,
                    "artist": artist_final,
                    "album": album,
                    "duration": duration,
                    "acodec": video.get('acodec'),
                    "abr": video.get('abr'),
                    "ext": video.get('ext'),
                    "format": video.get('format'),
                    "webpage_url": webpage_url,
                    "url": resolved_url,
                    "resolved": True,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "expires": expire_str,
                    "expire_ts": expire_ts
                }

                with open(yt_cache_path, "w", encoding="utf-8") as f:
                    json.dump(yt_cache, f, indent=2)

            if not preload:
                stream_url = resolved_url
                final_title_yt = title_final
                artist_yt = artist_final
                album_yt = album
                core.load_renderer_states_from_db()
                if core.is_renderer_active():
                    if core.DEBUG:
                        print("Renderer active – aborting launch of stream_songlog_entry()")
                    core.message_permanent = False
                    core.message_text = None
                    blocking_render = False
                    return
                try:
                    stream_songlog_entry()
                finally:
                    stream_transition_in_progress = False
                    stream_manual_skip = False

    except Exception as e:
        if not preload:
            core.message_permanent = False
            core.message_text = None
            stream_manual_skip = False
            stream_transition_in_progress = False
            blocking_render = False

        # Gestion du fallback si pas déjà tenté
        if not _fallback_attempt:
            # Essayer fallback en simplifiant la query
            parts = local_query.split(" - ")
            if len(parts) == 2:
                fallback_query = parts[1].strip()  # garder que le titre
            else:
                fallback_query = local_query  # pas de fallback possible

            if core.DEBUG:
                print(f"No results for query: {local_query}")
                print(f"Retrying with fallback query: {fallback_query}")

            return yt_search_track(index, preload=preload, _fallback_attempt=True, local_query=fallback_query)

        core.debug_error("error_yt", e)
        if not preload and not core.DEBUG:
            core.show_message(core.t("error_yt_simple"))
        return

    if not preload:
        core.message_permanent = False
        core.message_text = None
        blocking_render = False

def stop_current_stream():
    global current_ffmpeg, current_server

    if current_ffmpeg and current_ffmpeg.poll() is None:
        try:
            current_ffmpeg.terminate()
            current_ffmpeg.wait(timeout=4)
            if core.DEBUG:
                print("✓ ffmpeg terminated")
        except subprocess.TimeoutExpired:
            if core.DEBUG:
                print("⚠️ ffmpeg did not terminate in time, killing...")
            try:
                current_ffmpeg.kill()
                current_ffmpeg.wait(timeout=2)
                if core.DEBUG:
                    print("✓ ffmpeg killed")
            except Exception as e:
                core.debug_error("error_kill_ffmpeg", e)
        except Exception as e:
            core.debug_error("error_stop_ffmpeg", e)
    current_ffmpeg = None

    if current_server:
        try:
            current_server.shutdown()
            current_server.server_close()
            if core.DEBUG:
                print("✓ HTTP server stopped")
        except Exception as e:
            core.debug_error("error_http_server", e)
    current_server = None

    # Attendre max 4s la libération du port 8080
    for i in range(20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", 8080)) != 0:
                    if core.DEBUG:
                        print("✓ Port 8080 libre")
                    break
        except Exception as e:
            core.debug_error("error_socket_check", e)
            break
        time.sleep(0.2)
    else:
        if core.DEBUG:
            print("⚠️ Port 8080 encore occupé après timeout")

def stream_songlog_entry():
    global current_ffmpeg, current_server, blocking_render, stream_manual_skip, stream_transition_in_progress
    stream_manual_skip = False

    core.load_renderer_states_from_db()
    if core.is_renderer_active():
        if core.DEBUG:
            print("Renderer active – aborting stream_songlog_entry()")
        return

    stream_profile_selected = next(
        (item for item in stream_profile_menu_options if item["id"] == SAVED_STREAM_PROFILE),
        stream_profile_menu_options[1]  # fallback sur "standard"
    )

    if core.DEBUG:
        print(f"⇨ Start Local Stream")

    core.message_text = core.t("info_start_stream")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    class StreamHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            global current_ffmpeg, blocking_render, current_server, stream_manual_stop, stream_manual_skip
            if self.path != "/stream.mp3":
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.end_headers()

            if core.DEBUG:
                print(f"→ Launching ffmpeg for: {final_title_yt}")

            cmd = [
                "ffmpeg", "-re",
                "-fflags", "+discardcorrupt",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "2",
                "-i", stream_url,
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", stream_profile_selected["ffmpeg_bitrate"],
                "-metadata", f"title={final_title_yt}",
                "-f", "mp3", "-"
            ]
            if core.DEBUG:
                print("[ffmpeg] Launching with parameters:")
                print(f"    Codec:     libmp3lame")
                print(f"    Bitrate:   {stream_profile_selected['ffmpeg_bitrate']}")

            try:
                current_ffmpeg = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

                if not current_ffmpeg or not current_ffmpeg.stdout:
                    if core.DEBUG:
                        print("⚠️ ffmpeg not ready, aborting stream")
                    return

                empty_reads = 0
                while True:
                    chunk = current_ffmpeg.stdout.read(4096)
                    if not chunk:
                        empty_reads += 1
                        if empty_reads >= 20:
                            if core.DEBUG:
                                print("2s of empty chunk – aborting stream loop")
                            break
                        time.sleep(0.1)
                        continue

                    empty_reads = 0
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError) as e:
                        if core.DEBUG:
                            print(f"⚠️ Client disconnected: {e}")
                        break

            except Exception as e:
                if "NoneType" in str(e) and "stdout" in str(e):
                    # erreur attendue lors de l'arrêt de ffmpeg, on ignore en mode normal
                    if core.DEBUG:
                        print(f"Ignored stream error on ffmpeg stop: {e}")
                else:
                    core.debug_error("error_stream", e)

            finally:
                try:
                    client = MPDClient()
                    client.connect("localhost", 6600)
                    client.stop()
                    client.close()
                    client.disconnect()
                except Exception as e:
                    core.debug_error("error_mpd", e, silent=True)
                    if not core.DEBUG:
                        core.show_message(core.t("error_generic"))

                if current_ffmpeg and current_ffmpeg.poll() is None:
                    try:
                        current_ffmpeg.terminate()
                        current_ffmpeg.wait(timeout=4)
                        if core.DEBUG:
                            print("✓ ffmpeg terminated cleanly")
                    except subprocess.TimeoutExpired:
                        if core.DEBUG:
                            print("⚠️ ffmpeg timeout, forcing kill")
                        try:
                            current_ffmpeg.kill()
                            current_ffmpeg.wait(timeout=2)
                            if core.DEBUG:
                                print("✓ ffmpeg killed")
                        except Exception as e:
                            core.debug_error("error_ffmpeg", e)
                current_ffmpeg = None
                if core.DEBUG:
                    print("----------------End of Stream---------------------")
                    print(f"[StreamHandler] stream_manual_skip = {stream_manual_skip}")
                    print(f"[StreamHandler] stream_manual_stop = {stream_manual_stop}")
                core.load_renderer_states_from_db()
                if not stream_manual_skip and not stream_manual_stop and not core.is_renderer_active():
                    threading.Thread(target=next_stream, daemon=True).start()
                stream_manual_stop = False
                stream_manual_skip = False

    def run_server():
        global current_server
        current_server = http.server.HTTPServer(("0.0.0.0", 8080), StreamHandler)
        current_server.serve_forever()

    threading.Thread(target=run_server, daemon=True).start()

    try:
        client = MPDClient()
        client.connect("localhost", 6600)
        client.clear()
        client.load("RADIO/Local Stream.pls")

        for _ in range(5):
            try:
                with socket.create_connection(("localhost", 8080), timeout=1):
                    break
            except:
                time.sleep(0.2)

        client.play()
        client.close()
        client.disconnect()
        time.sleep(1)
        core.message_permanent = False
        core.message_text = None
        core.show_message(core.t("info_streaming", title=final_title_yt))
        if core.DEBUG:
            print(f"✅ Streaming ready: {final_title_yt}")
            print(f"  Using profile: {SAVED_STREAM_PROFILE}")
    except Exception as e:
        core.message_permanent = False
        core.message_text = None
        stream_transition_in_progress = False
        blocking_render = False
        core.debug_error("error_mpd", e, silent=True)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

    stream_transition_in_progress = False
    blocking_render = False

def run_bluetooth_action(*args):
    output = []

    def act_blucontrol():
        try:
            result = subprocess.run(["sudo", "/var/www/util/blu-control.sh"] + list(args), capture_output=True, text=True, timeout=30)
            output.append(result.stdout.strip())
        except Exception as e:
            core.debug_error("error_bluetooth_action", e)
            output.append("")

    thread = threading.Thread(target=act_blucontrol)
    thread.start()
    thread.join()  # ← tu peux mettre un timeout si nécessaire
    return output[0] if output else ""

def perform_bluetooth_scan():
    global blocking_render, bluetooth_scan_menu_active
    core.message_text = core.t("inf_bt_scanning")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    run_bluetooth_action("-S")
    update_trusted_devices_menu()

    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None
    core.show_message(core.t("info_bt_scan_ok"))
    blocking_render = False
    bluetooth_scan_menu_active = True

def update_trusted_devices_menu():
    global bluetooth_scan_menu_options
    output = run_bluetooth_action("-l")
    paired = run_bluetooth_action("-p").splitlines()
    paired_set = set(
        line[3:].strip().split(" ", 1)[0]
        for i, line in enumerate(paired)
        if i >= 2 and line.startswith("** ")
    )
    connected = run_bluetooth_action("-c").splitlines()
    connected_set = set(
        line[3:].strip().split(" ", 1)[0]
        for i, line in enumerate(connected)
        if i >= 2 and line.startswith("** ")
    )
    bluetooth_scan_menu_options = []
    for i, line in enumerate(output.splitlines()):
        if i < 2:
            continue
        if not line.startswith("** "):
            continue
        line = line[3:].strip()
        parts = line.split(" ", 1)
        if len(parts) == 2:
            mac, name = parts
            is_paired = mac in paired_set
            is_connected = mac in connected_set
            if is_connected:
                icon = "✓⚪ "
            elif is_paired and not is_connected:
                icon = "⚪ "
            else:
                icon = ""
            bluetooth_scan_menu_options.append({"id": f"bt_trusted_{mac}", "label": f"{icon}{name}", "mac": mac, "paired": is_paired, "connected": is_connected})

def update_paired_devices_menu():
    global bluetooth_paired_menu_options
    paired = run_bluetooth_action("-p").splitlines()
    connected = run_bluetooth_action("-c").splitlines()
    connected_set = set(
        line[3:].strip().split(" ", 1)[0]
        for i, line in enumerate(connected)
        if i >= 2 and line.startswith("** ")
    )

    bluetooth_paired_menu_options = []
    for i, line in enumerate(paired):
        if i < 2:
            continue
        if not line.startswith("** "):
            continue
        line = line[3:].strip()
        parts = line.split(" ", 1)
        if len(parts) == 2:
            mac, name = parts
            is_connected = mac in connected_set
            icon = "✓ " if is_connected else ""
            bluetooth_paired_menu_options.append({"id": f"bt_dev_{mac}", "label": f"{icon} {name}", "mac": mac, "connected": is_connected})

def open_device_actions_menu(mac, paired=False, connected=False):
    name = next((d['label'] for d in bluetooth_scan_menu_options + bluetooth_paired_menu_options if d['mac'] == mac), mac)
    global bluetooth_device_actions_menu_options, selected_bt_mac
    selected_bt_mac = mac
    options = []
    if not paired:
        options.append({"id": f"bt_pair_{mac}", "label": core.t("menu_bt_pair")})
        options.append({"id": f"bt_mac_{mac}", "label": mac})
    if paired and not connected:
        options.append({"id": f"bt_connect_{mac}", "label": core.t("menu_bt_connect")})
    if connected:
        options.append({"id": f"bt_disconnect_{mac}", "label": core.t("menu_bt_disconnect")})
    if paired:
        options.append({"id": f"bt_remove_{mac}", "label": core.t("menu_bt_remove")})
        options.append({"id": f"bt_mac_{mac}", "label": mac})
    bluetooth_device_actions_menu_options = options

def run_bt_action_and_msg(flag, mac, msg_key):
    global blocking_render, bluetooth_menu_active

    core.message_text = core.t("info_working")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    run_bluetooth_action(flag, mac)

    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None
    core.show_message(core.t(msg_key, name=mac))
    blocking_render = False
    bluetooth_menu_active = True

def toggle_audio_output(mode):
    global blocking_render, bluetooth_menu_active

    core.message_text = core.t("info_working")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    output = []

    def act_bluaudiout():
        try:
            result = subprocess.run(
                ["sudo", "php", str(core.MOODEOLED_DIR / "audioout-toggle.php"), mode],
                capture_output=True, text=True, check=False
            )
            output.append(result.stdout.strip())
        except Exception as e:
            core.debug_error("error_audioout", e)
            output.append("[ERROR]")

    thread = threading.Thread(target=act_bluaudiout)
    thread.start()
    thread.join()

    core.load_renderer_states_from_db()
    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None

    result_line = output[0] if output else "[ERROR]"

    if result_line.startswith("[AUDIOOUT_CHANGED]"):
        core.show_message(core.t("info_audioout_changed", mode=mode))
    elif result_line.startswith("[AUDIOOUT_ALREADY_SET]"):
        core.show_message(core.t("info_audioout_already", mode=mode))
    elif result_line.startswith("[AUDIOOUT_NO_BT]"):
        core.show_message(core.t("error_audioout_bt_missing"))
    elif result_line.startswith("[AUDIOOUT_INVALID]"):
        core.show_message(core.t("error_audioout_invalid"))
    elif result_line.startswith("[AUDIOOUT_USAGE]"):
        core.show_message(core.t("error_audioout_usage"))
    else:
        core.show_message(result_line)
    blocking_render = False
    bluetooth_menu_active = True

def render_screen():
    global now_playing_mode

    core.image = core.Image.new("1", (core.width, core.height))     # ← recrée un buffer vierge
    core.draw = core.ImageDraw.Draw(core.image)
    now_playing_mode = False

    if core.message_text:
        core.draw_message()
        idle_timer = time.time()
    elif help_active:
        draw_help_screen()
    elif confirm_box_active:
        draw_confirm_box()
    elif hardware_info_active:
        draw_hardware_info()
    elif language_menu_active:
        draw_language_menu()
    elif stream_profile_menu_active:
        draw_stream_profile_menu()
    elif config_menu_active:
        draw_config_menu()
    elif renderers_menu_active:
        draw_renderers_menu()
    elif bluetooth_device_actions_menu_active:
        draw_bluetooth_device_actions_menu()
    elif bluetooth_audioout_menu_active:
        draw_bluetooth_audioout_menu()
    elif bluetooth_scan_menu_active:
        draw_bluetooth_scan_menu()
    elif bluetooth_paired_menu_active:
        draw_bluetooth_paired_menu()
    elif bluetooth_menu_active:
        draw_bluetooth_menu()
    elif tool_menu_active:
        draw_tool_menu()
    elif songlog_action_active:
        draw_songlog_action_menu()
    elif songlog_active:
        draw_songlog_menu()
    elif power_menu_active:
        draw_power_menu()
    elif playback_modes_menu_active:
        draw_playback_modes_menu()
    elif stream_queue_action_active:
        draw_stream_queue_action_menu()
    elif stream_queue_active:
        draw_stream_queue_menu()
    elif menu_active:
        draw_menu()
    else:
        now_playing_mode = True
        draw_nowplaying()

    core.disp.image(core.image)
    core.disp.show()

def draw_menu():
    global menu_options_contextuel

    if core.global_state.get("state", "unknown") == "stop":
        menu_options_contextuel = menu_options.copy()
    elif menu_context_flag == "library":
        menu_options_contextuel = (
            (menu_remove_fav_option.copy() if core.global_state.get("favorite") else menu_add_fav_option.copy())
            + menu_search_artist_option.copy()
            + menu_options.copy()
        )
    elif menu_context_flag == "radio":
        if core.global_state.get("state", "unknown") == "pause":
            menu_options_contextuel = menu_options.copy()
        else:
            menu_options_contextuel = menu_add_songlog_option.copy() + menu_options.copy()
    elif menu_context_flag == "local_stream":
        filtered_options = [opt for opt in menu_options if opt.get("id") not in {"remove_queue", "playback_modes"}]
        if stream_queue:
            menu_options_contextuel = menu_show_stream_queue_option.copy() + filtered_options
        else:
            menu_options_contextuel = filtered_options
    else:
        menu_options_contextuel = menu_options.copy()

    core.draw_custom_menu([item["label"] for item in menu_options_contextuel], menu_selection, title=core.t("title_menu"))

def draw_playback_modes_menu():
    active = []
    for item in playback_modes_options:
        key = item["id"]
        if core.global_state.get(key) == "1":
            active.append(item["label"])
    core.draw_custom_menu([item["label"] for item in playback_modes_options], playback_modes_selection, title=core.t("title_playback"), multi=active)

def draw_power_menu():
    core.draw_custom_menu([item["label"] for item in power_menu_options], power_menu_selection, title=core.t("title_power"))

def draw_songlog_menu():
    selected = set()
    if stream_queue and 0 <= stream_queue_pos < len(stream_queue):
        playing_index = stream_queue[stream_queue_pos]
        if 0 <= playing_index < len(songlog_lines):
            selected = {songlog_lines[playing_index]}
    core.draw_custom_menu(songlog_lines, songlog_selection, title=core.t("title_songlog"), multi=selected, checkmark="▶ ")

def draw_stream_queue_menu():
    global stream_queue_lines
    stream_queue_lines = [songlog_lines[i] for i in stream_queue if 0 <= i < len(songlog_lines)]
    selected = {stream_queue_lines[stream_queue_pos]}
    core.draw_custom_menu(stream_queue_lines, stream_queue_selection, title=core.t("title_stream_queue"), multi=selected, checkmark="▶ ")

def draw_stream_queue_action_menu():
    core.draw_custom_menu([item["label"] for item in stream_queue_action_options], stream_queue_action_selection, title=core.t("title_action_stream_queue"))

def draw_songlog_action_menu():
    core.draw_custom_menu([item["label"] for item in songlog_action_options], songlog_action_selection, title=core.t("title_action_songlog"))

def draw_tool_menu():
    core.draw_custom_menu([item["label"] for item in tool_menu_options], tool_menu_selection, title=core.t("title_tools"))

def draw_language_menu():
    selected = {item["label"] for item in language_menu_options if item["id"] == core.LANGUAGE}
    core.draw_custom_menu([item["label"] for item in language_menu_options], language_menu_selection, title=core.t("title_language"), multi=selected)

def draw_stream_profile_menu():
    selected = {item["label"] for item in stream_profile_menu_options if item["id"] == SAVED_STREAM_PROFILE}
    core.draw_custom_menu([item["label"] for item in stream_profile_menu_options], stream_profile_menu_selection, title=core.t("title_stream_profile"), multi=selected)

def draw_config_menu():
    for item in config_menu_options:
        if item["id"] == "sleep":
            item["label"] = core.t("menu_sleep") + f": {sleep_timeout_labels.get(core.SCREEN_TIMEOUT, 'Off')}"
            break
    config_flags = {"Debug"} if core.DEBUG else set()
    core.draw_custom_menu([item["label"] for item in config_menu_options], config_menu_selection, title=core.t("title_config"), multi=config_flags)

def draw_help_screen():
    core.draw_custom_menu(help_lines, help_selection, title=core.t("title_help"))

def draw_renderers_menu():
    active = []
    for item in renderers_menu_options:
        key = item["id"] + "svc"
        if core.global_state.get(key) == "1":
            active.append(item["label"])
    core.draw_custom_menu([item["label"] for item in renderers_menu_options], renderers_menu_selection, title=core.t("title_renderers"), multi=active)

def draw_bluetooth_menu():
    for item in bluetooth_menu_options:
        if item["id"] == "bt_toggle":
            item["label"] = core.t("menu_bt_toggle") + " On" if core.global_state.get("btsvc") == "1" else core.t("menu_bt_toggle") + " Off"
    core.draw_custom_menu([item["label"] for item in bluetooth_menu_options], bluetooth_menu_selection, title=core.t("title_bluetooth"))

def draw_bluetooth_scan_menu():
    core.draw_custom_menu([item["label"] for item in bluetooth_scan_menu_options], bluetooth_scan_menu_selection, title=core.t("title_bt_scan_result"))

def draw_bluetooth_paired_menu():
    core.draw_custom_menu([item["label"] for item in bluetooth_paired_menu_options], bluetooth_paired_menu_selection, title=core.t("title_bt_paired_list"))

def draw_bluetooth_audioout_menu():
    selected = set()
    if core.global_state.get("audioout") == "Bluetooth":
        selected.add(core.t("menu_audioout_bt"))
    else:
        selected.add(core.t("menu_audioout_local"))
    core.draw_custom_menu([item["label"] for item in bluetooth_audioout_menu_options], bluetooth_audioout_menu_selection, title=core.t("title_bt_audio_output"), multi=selected)

def draw_bluetooth_device_actions_menu():
    core.draw_custom_menu([item["label"] for item in bluetooth_device_actions_menu_options], bluetooth_device_actions_menu_selection, title=core.t("title_bt_device_actions"))

def draw_hardware_info():
    core.draw_custom_menu(hardware_info_lines, hardware_info_selection, title=core.t("title_hardware_info"))

def draw_confirm_box():
    core.draw_custom_menu([item["label"] for item in confirm_box_options], confirm_box_selection, title=confirm_box_title)

def draw_nowplaying():
    now = time.time()
    scroll_artist = core.scroll_state["nowplaying_artist"]
    scroll_title = core.scroll_state["nowplaying_title"]

    if core.is_renderer_active():
        if (
            core.global_state.get("btsvc") == "1"
            and core.global_state.get("audioout") == "Local"
            and core.global_state.get("btactive") == "1"
        ):
            artist_album = core.t("show_bt_input")
            title = core.t("show_bt_output_hint")
        else:
            artist_album = core.t("show_renderer_active")
            title = core.t("show_renderer_hint")
    else:
        artist_album = core.global_state.get("artist_album", "")
        title = core.global_state.get("title", "")

    text1_width = core.draw.textlength(artist_album, font=font_artist)
    text2_width = core.draw.textlength(title, font=font_artist)

    state = core.global_state.get("state", "unknown")
    volume = core.global_state.get("volume", "N/A")

    core.draw.rectangle((0, 0, core.width, core.height), fill=0)

    icon1 = icons["play"] if state == "play" else icons["pause"] if state == "pause" else icons["stop"] if state == "stop" else icons["empty"]
    icon2 = icons["random_on"] if core.global_state.get("random", "0") == "1" else icons["empty"]
    repeat = core.global_state.get("repeat", "0")
    single = core.global_state.get("single", "0")
    consume = core.global_state.get("consume", "0")


    if repeat == "1" and single == "1" and consume == "0":
        icon3 = icons["repeat1_on"]; icon4 = icons["empty"]
    elif consume == "1" and repeat == "1" and single == "1":
        icon3 = icons["empty"]; icon4 = icons["empty"]
    elif consume == "1" and single == "1" and repeat == "0":
        icon3 = icons["empty"]; icon4 = icons["single_on"]
    else:
        icon3 = icons["repeat_on"] if repeat == "1" else icons["empty"]
        icon4 = icons["single_on"] if single == "1" else icons["empty"]

    icon5 = icons["consume_on"] if consume == "1" else icons["empty"]
    icon6 = icons["favorite"] if core.global_state.get("favorite") else icons["empty"]
    icon7 = icons["bluetooth"] if core.global_state.get("audioout") == "Bluetooth" else icons["empty"]

    core.image.paste(icon1, (0 * icon_width, -1))
    if menu_context_flag != "local_stream" and not core.is_renderer_active():
        core.image.paste(icon2, (1 * icon_width, 0))
        core.image.paste(icon3, (2 * icon_width + 1, -1))
        core.image.paste(icon4, (3 * icon_width + 1, -1))
        core.image.paste(icon5, (4 * icon_width + 1, -1))
        core.image.paste(icon6, (5 * icon_width + 1, -2))
    core.image.paste(icon7, (6 * icon_width + 1, -1))

    if state == "stop" and not core.is_renderer_active():
        core.draw.text((30, 15), core.global_state["clock"], font=font_clock, fill=255)
        core.draw.text((1, 49), f"Vol: {volume}", font=font_vol, fill=255)
    else:
        if text1_width > core.width:
            full_width = text1_width
            display_width = core.width
            state_a = scroll_artist.get("phase", "pause_start")
            pause_dur = scroll_artist.get("pause_duration", 2)

            if state_a == "pause_start":
                scroll_artist["offset"] = 0
                if now - scroll_artist.get("pause_start_time", 0) > pause_dur:
                    scroll_artist["phase"] = "scrolling"
                    scroll_artist["last_update"] = now
            elif state_a == "scrolling":
                if now - scroll_artist["last_update"] > SCROLL_SPEED_NOWPLAYING:
                    scroll_artist["offset"] += 1
                    scroll_artist["last_update"] = now
                    if scroll_artist["offset"] >= (full_width - display_width):
                        scroll_artist["phase"] = "pause_end"
                        scroll_artist["pause_start_time"] = now
            elif state_a == "pause_end":
                if now - scroll_artist.get("pause_start_time", 0) > 1:
                    scroll_artist["offset"] = 0
                    scroll_artist["phase"] = "pause_start"
                    scroll_artist["pause_start_time"] = now

            if state_a != "pause_end":
                core.draw.text((0 - scroll_artist["offset"], 14), artist_album, font=font_artist, fill=255)
        else:
            centered_x = (core.width - text1_width) // 2
            core.draw.text((centered_x, 14), artist_album, font=font_artist, fill=255)

        if text2_width > core.width:
            full_width = text2_width
            display_width = core.width
            state_t = scroll_title.get("phase", "pause_start")
            pause_dur = scroll_title.get("pause_duration", 2)

            if state_t == "pause_start":
                scroll_title["offset"] = 0
                if now - scroll_title.get("pause_start_time", 0) > pause_dur:
                    scroll_title["phase"] = "scrolling"
                    scroll_title["last_update"] = now
            elif state_t == "scrolling":
                if now - scroll_title["last_update"] > SCROLL_SPEED_NOWPLAYING:
                    scroll_title["offset"] += 1
                    scroll_title["last_update"] = now
                    if scroll_title["offset"] >= (full_width - display_width):
                        scroll_title["phase"] = "pause_end"
                        scroll_title["pause_start_time"] = now
            elif state_t == "pause_end":
                if now - scroll_title.get("pause_start_time", 0) > 1:
                    scroll_title["offset"] = 0
                    scroll_title["phase"] = "pause_start"
                    scroll_title["pause_start_time"] = now

            if state_t != "pause_end":
                core.draw.text((0 - scroll_title["offset"], 31), title, font=font_artist, fill=255)
        else:
            centered_x = (core.width - text2_width) // 2
            core.draw.text((centered_x, 31), title, font=font_artist, fill=255)

        core.draw.text((1, 49), f"Vol: {volume}", font=font_vol, fill=255)
        core.draw.text((83, 49), core.global_state["clock"], font=font_vol, fill=255)

def nav_left_short():
    if menu_context_flag == "local_stream":
        previous_stream(manual_skip=True)
        return
    if now_playing_mode:
        subprocess.run(["mpc", "prev"])

def nav_right_short():
    if menu_context_flag == "local_stream":
        next_stream(manual_skip=True)
        return
    if now_playing_mode:
        subprocess.run(["mpc", "next"])

def nav_up():
    if now_playing_mode:
        subprocess.run(["curl", "-s", "http://127.0.0.1/command/?cmd=set_volume+up+2"])

def nav_down():
    if now_playing_mode:
        subprocess.run(["curl", "-s", "http://127.0.0.1/command/?cmd=set_volume+dn+2"])

def nav_right_long():
    if now_playing_mode:
        subprocess.run(["mpc", "seek", "+00:00:10"])

def nav_left_long():
    if now_playing_mode:
        subprocess.run(["mpc", "seek", "-00:00:10"])
    else:
        core.show_message(core.t("info_back_home"))

        for var in [
            "menu_active", "confirm_box_active", "help_active",
            "songlog_active", "songlog_action_active",
            "tool_menu_active", "language_menu_active", "hardware_info_active", "config_menu_active",
            "power_menu_active", "renderers_menu_active", "bluetooth_menu_active",
            "bluetooth_scan_menu_active", "bluetooth_paired_menu_active",
            "bluetooth_audioout_menu_active", "bluetooth_device_actions_menu_active",
            "stream_profile_menu_active", "playback_modes_menu_active"
        ]:
            globals()[var] = False

        core.message_text = None
        core.message_permanent = False

def nav_ok():
    global menu_active, menu_selection, renderers_menu_active, renderers_menu_selection, bluetooth_menu_active, bluetooth_menu_selection
    if core.is_renderer_active():
        if (
            core.global_state.get("btsvc") == "1"
            and core.global_state.get("audioout") == "Local"
            and core.global_state.get("btactive") == "1"
        ):
            bluetooth_menu_active = True
            bluetooth_menu_selection = 0
        else:
            renderers_menu_active = True
            renderers_menu_selection = 0
        return
    elif now_playing_mode:
        menu_active = True
        menu_selection = 0

def nav_ok_long():
    global tool_menu_active, tool_menu_selection
    if now_playing_mode:
        tool_menu_active = True
        tool_menu_selection = 0
    else:
        return

def nav_channelup():
    if menu_context_flag == "library":
        toggle_favorite()
    elif menu_context_flag == "radio":
        log_song()
    elif menu_context_flag == "local_stream":
        core.show_message(core.t("info_already_in_log"))
    else:
        core.show_message(core.t("info_unknown_fav"))

def nav_channeldown():
    if menu_context_flag == "local_stream":
        return
    else:
        remove_from_queue()

def nav_info():
    global help_active, help_lines, help_selection
    help_base_path = core.MOODEOLED_DIR / f"help_texts/help_nowoled_{core.LANGUAGE}.txt"
    if not help_base_path.exists():
        help_base_path = core.MOODEOLED_DIR / "help_texts/help_nowoled_en.txt"
    context = "nowplaying_mode" if now_playing_mode else "menu"
    try:
        with open(help_base_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        help_lines = []
        in_section = False
        for line in lines:
            line = line.strip()
            if line.startswith("# CONTEXT:"):
                in_section = (line == f"# CONTEXT:{context}")
                continue
            if in_section:
                help_lines.append(line)
        if help_lines:
            help_selection = 0
            help_active = True
        else:
            core.show_message(core.t("info_no_help"))
    except Exception as e:
        core.debug_error("error_help", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def nav_back():
    core.show_message(core.t("info_go_library_screen"))
    render_screen()
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "navoled.service"])
    subprocess.call(["sudo", "systemctl", "stop", "nowoled.service"])
    sys.exit(0)

def nav_back_long():
    core.show_message(core.t("info_go_playlist_screen"))
    render_screen()
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "queoled.service"])
    subprocess.call(["sudo", "systemctl", "stop", "nowoled.service"])
    sys.exit(0)


def finish_press(key):
    global menu_active, menu_selection, songlog_active, songlog_selection, songlog_action_active, songlog_action_selection
    global power_menu_active, power_menu_selection, playback_modes_menu_active, playback_modes_selection
    global stream_queue_active, stream_queue_selection, stream_queue_action_active, stream_queue_action_selection, stream_queue_pos, stream_manual_skip, stream_transition_in_progress
    global tool_menu_selection, tool_menu_active, config_menu_active, config_menu_selection, sleep_timeout_options
    global stream_profile_menu_active, stream_profile_menu_selection, SAVED_STREAM_PROFILE
    global help_active, help_selection, hardware_info_active, hardware_info_selection, language_menu_active, language_menu_selection
    global confirm_box_active, confirm_box_selection, confirm_box_callback, renderers_menu_active, renderers_menu_selection
    global bluetooth_menu_active, bluetooth_menu_selection, bluetooth_scan_menu_active, bluetooth_scan_menu_selection, bluetooth_audioout_menu_active, bluetooth_audioout_menu_selection
    global bluetooth_paired_menu_active, bluetooth_paired_menu_selection, bluetooth_device_actions_menu_active, bluetooth_device_actions_menu_selection
    global blocking_render, screen_on, idle_timer, is_sleeping, last_wake_time

    data = debounce_data.get(key)

    if data is None:
        return
    final_code = data.get("max_code", 0)
    if core.DEBUG:
        print(f"End pressure {key} with final code {final_code}.")

    idle_timer = time.time()

    if core.is_renderer_active():
        if key in ("KEY_LEFT", "KEY_RIGHT", "KEY_UP", "KEY_DOWN"):
            if now_playing_mode:
                core.show_message(core.t("info_action_blocked"))
                if core.DEBUG:
                    print(f"Renderer active → key '{key}' blocked (now_playing_mode)")
                return
        elif key in USED_MEDIA_KEYS:
            core.show_message(core.t("info_action_blocked"))
            if core.DEBUG:
                print(f"Renderer active → key '{key}' blocked")
            return

    if is_sleeping:
        if key in ("KEY_CHANNELUP", "KEY_CHANNELDOWN"):
            screen_on = True
            core.disp.poweron()
            core.reset_scroll("menu_title", "menu_item", "nowplaying_artist", "nowplaying_title")
            is_sleeping = False
            last_wake_time = time.time()
            if core.DEBUG:
                print(f"Wake up on key '{key}' (channel key)")
        elif key in ("KEY_LEFT", "KEY_RIGHT", "KEY_UP", "KEY_DOWN"):
            if now_playing_mode:
                if core.DEBUG:
                    print(f"Direction key '{key}' used in sleep mode (now_playing_mode)")
                pass
            else:
                if core.DEBUG:
                    print(f"Direction key '{key}' ignored in sleep mode (not now_playing_mode)")
                return
        elif key in USED_MEDIA_KEYS:
            if core.DEBUG:
                print(f"Media key '{key}' ignored in sleep mode (no wake)")
            pass
        else:
            screen_on = True
            core.disp.poweron()
            core.reset_scroll("menu_title", "menu_item", "nowplaying_artist", "nowplaying_title")
            is_sleeping = False
            last_wake_time = time.time()
            if core.DEBUG:
                print(f"Wake up on key '{key}' (action skipped)")
            return

    if time.time() - last_wake_time < 2:
        if key in ("KEY_CHANNELUP", "KEY_CHANNELDOWN"):
            if core.DEBUG:
                print(f"Input '{key}' allowed (within post-wake delay)")
            pass
        else:
            if core.DEBUG:
                print(f"Input '{key}' ignored (within post-wake delay)")
            return

    if core.message_permanent:
        if final_code >= 4:
            if key == "KEY_LEFT":
                nav_left_long()
        return

    if core.message_text and not core.message_permanent:
        if key in ("KEY_LEFT", "KEY_OK"):
            core.message_text = None
        return

    if final_code >= 4:
        if key == "KEY_LEFT":
            nav_left_long()
        elif key == "KEY_OK":
            nav_ok_long()
        elif key == "KEY_BACK":
            nav_back_long()
        elif key == "KEY_RIGHT":
            nav_right_long()
        elif key == "KEY_POWER":
            core.show_message(core.t("info_poweroff"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "poweroff"])
        elif handle_audio_keys(key, final_code):
            return
        elif handle_custom_key(key, final_code):
            return
        return

    if key == "KEY_INFO":
        if help_active:
            help_active = False
        else:
            nav_info()
        return
    if key == "KEY_BACK":
        nav_back()
        return

    if help_active:
        if key in ("KEY_LEFT", "KEY_OK", "KEY_INFO"):
            help_active = False
            core.reset_scroll("menu_item")
            return
        if help_lines:
            if key == "KEY_DOWN":
                help_selection = (help_selection + 1) % len(help_lines)
                core.reset_scroll("menu_item")
            elif key == "KEY_UP":
                help_selection = (help_selection - 1) % len(help_lines)
                core.reset_scroll("menu_item")
        return

    if confirm_box_active:
        if key == "KEY_UP" and confirm_box_selection > 0:
            confirm_box_selection -= 1
        elif key == "KEY_DOWN" and confirm_box_selection < 1:
            confirm_box_selection += 1
        elif key == "KEY_LEFT":
            confirm_box_active = False
            if confirm_box_callback:
                confirm_box_callback(cancel=True)
            return
        elif key == "KEY_OK":
            option_id = confirm_box_options[confirm_box_selection]["id"]
            confirm_box_active = False
            if option_id == "confirm_yes":
                confirm_box_callback()
            else:
                core.show_message(core.t("info_cancelled"))
            core.reset_scroll("menu_item", "menu_title")
        return

    if menu_active:
        if key == "KEY_UP" and menu_selection > 0:
            menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and menu_selection < len(menu_options_contextuel) - 1:
            menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            menu_active = False
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            item = menu_options_contextuel[menu_selection]
            option_id = item["id"]
            if option_id in ("add_fav", "remove_fav"):
                menu_active = False
                toggle_favorite()
            elif option_id == "search_artist":
                menu_active = False
                search_artist_from_now()
            elif option_id == "add_songlog":
                menu_active = False
                log_song()
            elif option_id == "show_stream_queue":
                menu_active = False
                stream_queue_active = True
            elif option_id == "remove_queue":
                menu_active = False
                remove_from_queue()
            elif option_id == "playback_modes":
                menu_active = False
                playback_modes_menu_active = True
                playback_modes_selection = 0
            elif option_id == "power":
                menu_active = False
                power_menu_active = True
                power_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if power_menu_active:
        if key == "KEY_UP" and power_menu_selection > 0:
            power_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and power_menu_selection < len(power_menu_options) - 1:
            power_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            power_menu_active = False
            menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            option_id = power_menu_options[power_menu_selection]["id"]
            power_menu_active = False
            if option_id == "poweroff":
                core.show_message(core.t("info_poweroff"))
                subprocess.call(["mpc", "stop"])
                subprocess.call(["sudo", "systemctl", "stop", "nginx"])
                subprocess.call(["sudo", "poweroff"])
            elif option_id == "reboot":
                core.show_message(core.t("info_reboot"))
                subprocess.call(["mpc", "stop"])
                subprocess.call(["sudo", "systemctl", "stop", "nginx"])
                subprocess.call(["sudo", "reboot"])
            elif option_id == "reload_screen":
                core.show_message(core.t("info_reload_screen"))
                subprocess.call(["sudo", "systemctl", "restart", "nowoled.service"])
                sys.exit(0)
            elif option_id == "restart_mpd":
                core.show_message(core.t("info_restart_mpd"))
                subprocess.call(["sudo", "systemctl", "restart", "mpd"])
            core.reset_scroll("menu_item", "menu_title")
        return

    if stream_queue_active:
        if key == "KEY_UP":
            stream_queue_selection = (stream_queue_selection - 1) % len(stream_queue_lines)
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN":
            stream_queue_selection = (stream_queue_selection + 1) % len(stream_queue_lines)
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            stream_queue_active = False
            menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            stream_queue_active = False
            stream_queue_action_active = True
            stream_queue_action_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if stream_queue_action_active:
        if key == "KEY_UP":
            stream_queue_action_selection = (stream_queue_action_selection - 1) % len(stream_queue_action_options)
            core.reset_scroll("menu_item")
            return
        elif key == "KEY_DOWN":
            stream_queue_action_selection = (stream_queue_action_selection + 1) % len(stream_queue_action_options)
            core.reset_scroll("menu_item")
            return
        elif key == "KEY_LEFT":
            stream_queue_action_active = False
            stream_queue_active = True
            core.reset_scroll("menu_item", "menu_title")
            return
        elif key == "KEY_OK":
            selected_action = stream_queue_action_options[stream_queue_action_selection]["id"]
            if selected_action == "play_stream_queue_pos":
                stream_queue_action_active = False
                if core.DEBUG:
                    print(f"▶️ Play from queue at position {stream_queue_selection}")
                stream_manual_skip = True
                stream_transition_in_progress = True
                stream_queue_pos = stream_queue_selection
                yt_search_track(stream_queue_pos, preload=False)
            core.reset_scroll("menu_item", "menu_title")
        return

    if playback_modes_menu_active:
        if key == "KEY_UP" and playback_modes_selection > 0:
            playback_modes_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and playback_modes_selection < len(playback_modes_options) - 1:
            playback_modes_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            playback_modes_menu_active = False
            menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option = playback_modes_options[playback_modes_selection]
            state_key = option["id"]
            new_val = "0" if core.global_state[state_key] == "1" else "1"
            set_mpd_state(state_key, int(new_val))
            core.reset_scroll("menu_item", "menu_title")
        return

    if tool_menu_active:
        if key == "KEY_UP" and tool_menu_selection > 0:
            tool_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and tool_menu_selection < len(tool_menu_options) - 1:
            tool_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            tool_menu_active = False
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option_id = tool_menu_options[tool_menu_selection]["id"]
            #tool_menu_active = False
            if option_id == "renderers":
                tool_menu_active = False
                renderers_menu_active = True
                renderers_menu_selection = 0
            elif option_id == "show_songlog":
                tool_menu_active = False
                show_songlog()
                if not songlog_lines:
                    tool_menu_active = True
                else:
                    songlog_active = True
                songlog_selection = 0
            elif option_id == "hardware_info":
                tool_menu_active = False
                hardware_info_active = True
                threading.Thread(target=update_hardware_info, daemon=True).start()
            elif option_id == "configuration":
                tool_menu_active = False
                config_menu_active = True
                config_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if renderers_menu_active:
        if key == "KEY_UP" and renderers_menu_selection > 0:
            renderers_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and renderers_menu_selection < len(renderers_menu_options) - 1:
            renderers_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            renderers_menu_active = False
            if core.is_renderer_active():
                pass
            else:
                tool_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            renderer = renderers_menu_options[renderers_menu_selection]["id"]
            if renderer == "bluetooth":
                renderers_menu_active = False
                bluetooth_menu_active = True
                bluetooth_menu_selection = 0
            else:
                action = "off" if core.global_state.get(renderer + "svc") == "1" else "on"
                core.show_message(core.t("info_renderer_switched", name=renderer.capitalize(), status=action))
                subprocess.call(["sudo", "php", str(core.MOODEOLED_DIR / f"renderer-toggle.php"), renderer, action])
                core.load_renderer_states_from_db()
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_menu_active:
        if key == "KEY_UP" and bluetooth_menu_selection > 0:
            bluetooth_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_menu_selection < len(bluetooth_menu_options) - 1:
            bluetooth_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_menu_active = False
            if core.is_renderer_active():
                pass
            else:
                renderers_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            item = bluetooth_menu_options[bluetooth_menu_selection]["id"]
            if item == "bt_toggle":
                action = "off" if core.global_state.get("btsvc") == "1" else "on"
                core.show_message(core.t("info_renderer_switched", name="Bluetooth", status=action))
                subprocess.call(["sudo", "php", str(core.MOODEOLED_DIR / "renderer-toggle.php"), "bluetooth", action])
                core.load_renderer_states_from_db()
            elif item == "bt_scan":
                bluetooth_menu_active = False
                perform_bluetooth_scan()
                bluetooth_scan_menu_selection = 0
            elif item == "bt_paired":
                bluetooth_menu_active = False
                update_paired_devices_menu()
                bluetooth_paired_menu_active = True
                bluetooth_paired_menu_selection = 0
            elif item == "bt_audio_output":
                bluetooth_menu_active = False
                core.load_renderer_states_from_db()
                bluetooth_audioout_menu_active = True
                bluetooth_audioout_menu_selection = 0
            elif item == "bt_disconnect_all":
                run_bluetooth_action("-D")
                core.show_message(core.t("info_bt_all_disconnected"))
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_scan_menu_active:
        if key == "KEY_UP" and bluetooth_scan_menu_selection > 0:
            bluetooth_scan_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_scan_menu_selection < len(bluetooth_scan_menu_options) - 1:
            bluetooth_scan_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_scan_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_scan_menu_options[bluetooth_scan_menu_selection]
            bluetooth_scan_menu_active = False
            open_device_actions_menu(selected["mac"], paired=selected.get("paired", False), connected=selected.get("connected", False))
            bluetooth_device_actions_menu_active = True
            bluetooth_device_actions_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_paired_menu_active:
        if key == "KEY_UP" and bluetooth_paired_menu_selection > 0:
            bluetooth_paired_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_paired_menu_selection < len(bluetooth_paired_menu_options) - 1:
            bluetooth_paired_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_paired_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_paired_menu_options[bluetooth_paired_menu_selection]
            bluetooth_paired_menu_active = False
            open_device_actions_menu(selected["mac"], paired=True, connected=selected.get("connected", False))
            bluetooth_device_actions_menu_active = True
            bluetooth_device_actions_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_device_actions_menu_active:
        if key == "KEY_UP" and bluetooth_device_actions_menu_selection > 0:
            bluetooth_device_actions_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_device_actions_menu_selection < len(bluetooth_device_actions_menu_options) - 1:
            bluetooth_device_actions_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_device_actions_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_device_actions_menu_options[bluetooth_device_actions_menu_selection]["id"]
            bluetooth_device_actions_menu_active = False
            if selected.startswith("bt_pair_"):
                run_bt_action_and_msg("-P", selected_bt_mac, "info_bt_paired_ok")
            elif selected.startswith("bt_connect_"):
                run_bt_action_and_msg("-C", selected_bt_mac, "info_bt_connect_ok")
            elif selected.startswith("bt_disconnect_"):
                run_bt_action_and_msg("-d", selected_bt_mac, "info_bt_disconnect_ok")
            elif selected.startswith("bt_remove_"):
                run_bt_action_and_msg("-r", selected_bt_mac, "info_bt_remove_ok")
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_audioout_menu_active:
        if key == "KEY_UP" and bluetooth_audioout_menu_selection > 0:
            bluetooth_audioout_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_audioout_menu_selection < len(bluetooth_audioout_menu_options) - 1:
            bluetooth_audioout_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_audioout_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_audioout_menu_options[bluetooth_audioout_menu_selection]["id"]
            bluetooth_audioout_menu_active = False
            if selected == "audioout_local":
                toggle_audio_output("Local")
            elif selected == "audioout_bt":
                toggle_audio_output("Bluetooth")
            core.reset_scroll("menu_item", "menu_title")
        return

    if songlog_active:
        if key == "KEY_LEFT":
            songlog_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
            return
        if songlog_lines:
            if key == "KEY_UP":
                songlog_selection = (songlog_selection - 1) % len(songlog_lines)
                core.reset_scroll("menu_item")
            elif key == "KEY_DOWN":
                songlog_selection = (songlog_selection + 1) % len(songlog_lines)
                core.reset_scroll("menu_item")
            elif key == "KEY_OK":
                songlog_active = False
                songlog_action_active = True
                songlog_action_selection = 0
                core.reset_scroll("menu_item", "menu_title")
        return

    if songlog_action_active:
        if key == "KEY_UP" and songlog_action_selection > 0:
            songlog_action_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and songlog_action_selection < len(songlog_action_options) - 1:
            songlog_action_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            songlog_action_active = False
            show_songlog()
            songlog_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option_id = songlog_action_options[songlog_action_selection]["id"]
            if option_id == "play_yt_songlog":
                songlog_action_active = False
                ensure_local_stream()
                if not has_internet_connection():
                    core.show_message(core.t("info_no_internet"))
                    return
                stream_queue.clear()
                yt_search_track(songlog_selection)
            elif option_id == "queue_yt_songlog":
                songlog_action_active = False
                ensure_local_stream()
                if not has_internet_connection():
                    core.show_message(core.t("info_no_internet"))
                    return
                stream_queue.clear()
                play_all_songlog_from_queue()
            elif option_id == "show_info_songlog":
                info = songlog_meta[songlog_selection]
                if info:
                    core.show_message(info)
                else:
                    core.show_message(core.t("info_no_additional"))
            elif option_id == "delete_entry_songlog":
                songlog_action_active = False
                delete_songlog_entry(songlog_selection)
                if not songlog_lines:
                    tool_menu_active = True
                else:
                    songlog_active = True
            elif option_id == "delete_all_songlog":
                songlog_action_active = False
                confirm_box_active = True
                confirm_box_selection = 1
                confirm_box_callback = confirm_delete_all_songlog
            core.reset_scroll("menu_item", "menu_title")
        return

    if config_menu_active:
        if key == "KEY_UP" and config_menu_selection > 0:
            config_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and config_menu_selection < len(config_menu_options) - 1:
            config_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            config_menu_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            option_id = config_menu_options[config_menu_selection]["id"]
            if option_id == "sleep":
                idx = sleep_timeout_options.index(core.SCREEN_TIMEOUT)
                idx = (idx + 1) % len(sleep_timeout_options)
                core.SCREEN_TIMEOUT = sleep_timeout_options[idx]
                core.save_config_setting("screen_timeout", core.SCREEN_TIMEOUT, section="settings")
            elif option_id == "stream_quality":
                config_menu_active = False
                stream_profile_menu_active = True
                stream_profile_menu_selection = 0
            elif option_id == "language":
                config_menu_active = False
                language_menu_active = True
                language_menu_selection = 0
            elif option_id == "debug":
                config_menu_active = False
                new_debug = not core.DEBUG
                core.save_config_setting("debug", new_debug, section="settings")
                core.show_message(core.t("info_debug_on") if new_debug else core.t("info_debug_off"))
                time.sleep(1)
                os.execv(sys.executable, ['python3'] + sys.argv)

            core.reset_scroll("menu_item", "menu_title")
        return

    if stream_profile_menu_active:
        if key == "KEY_UP" and stream_profile_menu_selection > 0:
            stream_profile_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and stream_profile_menu_selection < len(stream_profile_menu_options) - 1:
            stream_profile_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            stream_profile_menu_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            SAVED_STREAM_PROFILE = stream_profile_menu_options[stream_profile_menu_selection]["id"]
            core.save_config_setting("stream_profile", SAVED_STREAM_PROFILE, section="settings")
            core.reset_scroll("menu_item", "menu_title")
        return

    if language_menu_active:
        if key == "KEY_UP" and language_menu_selection > 0:
            language_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and language_menu_selection < len(language_menu_options) - 1:
            language_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            language_menu_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            language_menu_active = False
            core.LANGUAGE = language_menu_options[language_menu_selection]["id"]
            core.save_config_setting("language", core.LANGUAGE, section="settings")
            core.show_message(core.t("info_language_set", selected=language_menu_options[language_menu_selection]["label"]))
            time.sleep(1)
            os.execv(sys.executable, ['python3'] + sys.argv)
        return

    if hardware_info_active:
        if key == "KEY_UP" and hardware_info_selection > 0:
            hardware_info_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and hardware_info_selection < len(hardware_info_lines) - 1:
            hardware_info_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            hardware_info_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            if wifi_extra_info:
                core.show_message(wifi_extra_info)
            else:
                core.show_message(core.t("info_wifi_disconnected"))
        return

    else:
        if key == "KEY_OK":
            nav_ok()
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_LEFT":
            nav_left_short()
        elif key == "KEY_RIGHT":
            nav_right_short()
        elif key == "KEY_UP":
            nav_up()
        elif key == "KEY_DOWN":
            nav_down()
        elif key == "KEY_CHANNELUP":
            nav_channelup()
        elif key == "KEY_CHANNELDOWN":
            nav_channeldown()
        elif key == "KEY_POWER":
            core.show_message(core.t("info_reboot"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "reboot"])
        elif handle_audio_keys(key, final_code, menu_context_flag):
            return
        elif handle_custom_key(key, final_code, menu_context_flag):
            return
        else:
            if core.DEBUG:
                print(f"key {key} not used in this script")

    debounce_data.pop(key, None)

core.start_message_updater()

start_inputs(core.config, finish_press, msg_hook=core.show_message)
set_custom_hooks(core.show_message, next_stream, previous_stream, set_stream_manual_stop)

def main():
    global previous_blocking_render, idle_timer
    threading.Thread(target=update_status_info, daemon=True).start()
    try:
        while True:
            if previous_blocking_render != blocking_render:
                idle_timer = time.time()
            previous_blocking_render = blocking_render
            if core.SCREEN_TIMEOUT > 0 and time.time() - idle_timer > core.SCREEN_TIMEOUT:
                if not is_sleeping and not blocking_render:
                    run_sleep_loop()
            elif screen_on:
                run_active_loop()
            time.sleep(0.1 if is_sleeping else 0.05)
    except KeyboardInterrupt:
        core.disp.fill(0)
        core.disp.show()
        if core.DEBUG:
            print("Closing")

if __name__ == '__main__':
    main()
