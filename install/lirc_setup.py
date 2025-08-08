#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import os
import sys
import subprocess
import shutil
import argparse
import tempfile
import re
import glob
import time

MESSAGES = {
    "start": {
        "en": "⇨ Configuring GPIO IR receiver (LIRC)...",
        "fr": "⇨ Configuration du récepteur IR GPIO (LIRC)..."
    },
    "explain": {
        "en": (
            "This will configure LIRC for IR remotes connected to a GPIO receiver.\n"
            "Steps:\n"
            "  1. Install LIRC if missing\n"
            "  2. Add or update dtoverlay=gpio-ir,gpio_pin=<pin> to /boot/firmware/config.txt\n"
            "  3. Update /etc/lirc/lirc_options.conf\n"
            "  4. Create backups of modified files\n"
            "  5. Reboot required before remote setup\n"
        ),
        "fr": (
            "Cette opération configure LIRC pour les télécommandes IR connectées sur GPIO.\n"
            "Étapes:\n"
            "  1. Installer LIRC si nécessaire\n"
            "  2. Ajouter ou mettre à jour dtoverlay=gpio-ir,gpio_pin=<pin> dans /boot/firmware/config.txt\n"
            "  3. Mettre à jour /etc/lirc/lirc_options.conf\n"
            "  4. Créer des sauvegardes des fichiers modifiés\n"
            "  5. Reboot requis avant la configuration de la télécommande\n"
        )
    },
    "accept_prompt": {
        "en": "⚠️ Do you want to continue? [Y/n] > ",
        "fr": "⚠️ Voulez-vous continuer ? [O/n] > "
    },
    "accept_cancelled": {
        "en": "⚠️ LIRC configuration skipped. You can configure it later manually or via:\n' python3 ~/MoodeOled/install/lirc_setup.py --lang {} '",
        "fr": "⚠️ Configuration de LIRC ignorée. Vous pourrez la configurer plus tard manuellement ou via :\n' python3 ~/MoodeOled/install/lirc_setup.py --lang {} '"
    },
    "enter_pin": {
        "en": "Enter the GPIO pin number for IR receiver (BCM): ",
        "fr": "Entrez le numéro de GPIO du récepteur IR (BCM) : "
    },
    "keep_existing_pin": {
        "en": "⚙️ Found existing gpio-ir overlay with gpio_pin={}. Keep this value? [Y/n] > ",
        "fr": "⚙️ Overlay gpio-ir existant détecté avec gpio_pin={}. Conserver cette valeur ? [O/n] > "
    },
    "lirc_installed": {
        "en": "📦 LIRC already installed.",
        "fr": "📦 LIRC déjà installé."
    },
    "installing_lirc": {
        "en": "📦 Installing LIRC...",
        "fr": "📦 Installation de LIRC..."
    },
    "updating_config": {
        "en": "🛠 Updating /boot/firmware/config.txt...",
        "fr": "🛠 Mise à jour de /boot/firmware/config.txt..."
    },
    "backup_created": {
        "en": "🔒 Backup created: {}",
        "fr": "🔒 Sauvegarde créée : {}"
    },
    "lirc_conf_update": {
        "en": "🛠 Updating /etc/lirc/lirc_options.conf...",
        "fr": "🛠 Mise à jour de /etc/lirc/lirc_options.conf..."
    },
    "remote_setup_info": {
        "en": "ℹ️ After reboot, run ' python3 ~/MoodeOled/install/install_lirc_remote.py ' to configure your remote.",
        "fr": "ℹ️ Après redémarrage, exécutez ' python3 ~/MoodeOled/install/install_lirc_remote.py ' pour configurer votre télécommande."
    },
    "moode_reminder": {
        "en": "⚠️ Reminder: In Moode, enable:\n  - Ready Script (System)\n  - LCD Updater (Peripherals)",
        "fr": "⚠️ Rappel : Dans Moode, activez :\n  - Ready Script (Système)\n  - LCD Updater (Périphériques)"
    },
    "reboot_prompt": {
        "en": "⚠️ Reboot required for IR changes. Reboot now? [Y/n] > ",
        "fr": "⚠️ Redémarrage requis pour les changements IR. Redémarrer maintenant ? [O/n] > "
    },
    "rebooting": {
        "en": "⇨ Rebooting...",
        "fr": "⇨ Redémarrage en cours..."
    },
    "reboot_cancelled": {
        "en": "⚠️ Reboot cancelled. Please reboot manually later.",
        "fr": "⚠️ Redémarrage annulé. Veuillez redémarrer manuellement plus tard."
    }
}

CONFIG_TXT = "/boot/firmware/config.txt"
LIRC_OPTIONS = "/etc/lirc/lirc_options.conf"

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

def safe_read_file(path):
    result = subprocess.run(f"sudo cat {path}", shell=True, capture_output=True, text=True)
    return result.stdout.splitlines()

def safe_write_file(path, lines):
    with tempfile.NamedTemporaryFile('w', delete=False) as tmp:
        if isinstance(lines, list):
            tmp.writelines(line if line.endswith("\n") else line + "\n" for line in lines)
        else:
            tmp.write(lines if lines.endswith("\n") else lines + "\n")
        tmp_path = tmp.name
    run(f"sudo cp {tmp_path} {path}")
    run(f"sudo rm {tmp_path}")

def create_backup(file_path, lang, keep=5):
    if not os.path.exists(file_path):
        return

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{file_path}.moodeoled-back-{timestamp}"
    # Utiliser sudo cp pour copier avec droits root
    run(f"sudo cp -p {file_path} {backup_path}")
    print(MESSAGES["backup_created"][lang].format(backup_path))

    # Supprimer les anciennes sauvegardes si > keep
    backups = sorted(
        glob.glob(f"{file_path}.moodeoled-back-*"),
        key=os.path.getmtime,
        reverse=True
    )

    for old_backup in backups[keep:]:
        try:
            # Utiliser sudo rm pour supprimer avec droits root
            run(f"sudo rm -f {old_backup}")
        except subprocess.CalledProcessError:
            pass

def ensure_lirc_installed(lang):
    try:
        subprocess.run("dpkg -s lirc", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(MESSAGES["lirc_installed"][lang])
    except subprocess.CalledProcessError:
        print(MESSAGES["installing_lirc"][lang])
        run("sudo apt update && sudo apt install -y lirc")

def update_config_txt(lang):
    create_backup(CONFIG_TXT, lang)
    lines = safe_read_file(CONFIG_TXT)

    regex = re.compile(r"dtoverlay=gpio-ir,gpio_pin=(\d+)")
    existing_pin = None
    for line in lines:
        match = regex.search(line)
        if match:
            existing_pin = int(match.group(1))
            break

    if existing_pin is not None:
        choice = input(MESSAGES["keep_existing_pin"][lang].format(existing_pin)).strip().lower()
        gpio_pin = existing_pin if choice not in ["n", "no"] else ask_gpio_pin(lang)
    else:
        gpio_pin = ask_gpio_pin(lang)

    lines = [line for line in lines if not regex.search(line)]
    insert_index = len(lines)
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("# do not alter this section"):
            insert_index = i
            break
    lines.insert(insert_index, f"dtoverlay=gpio-ir,gpio_pin={gpio_pin}\n")

    safe_write_file(CONFIG_TXT, lines)
    print(MESSAGES["updating_config"][lang])

def ask_gpio_pin(lang):
    while True:
        pin = input(MESSAGES["enter_pin"][lang]).strip()
        if pin.isdigit() and 0 <= int(pin) <= 40:
            return int(pin)
        print("❌ Invalid GPIO pin. Please enter a number between 0 and 40.")

def update_lirc_options(lang):
    create_backup(LIRC_OPTIONS, lang)
    lines = safe_read_file(LIRC_OPTIONS)
    updated_lines = []
    in_lircd_section = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[lircd]"):
            in_lircd_section = True
            updated_lines.append(line + "\n" if not line.endswith("\n") else line)
            continue
        if stripped.startswith("[") and stripped != "[lircd]":
            in_lircd_section = False
            updated_lines.append(line + "\n" if not line.endswith("\n") else line)
            continue

        if in_lircd_section:
            if stripped.startswith("driver"):
                updated_lines.append("driver          = default\n")
            elif stripped.startswith("device"):
                updated_lines.append("device          = /dev/lirc0\n")
            else:
                updated_lines.append(line + "\n" if not line.endswith("\n") else line)
        else:
            updated_lines.append(line + "\n" if not line.endswith("\n") else line)

    safe_write_file(LIRC_OPTIONS, updated_lines)
    print(MESSAGES["lirc_conf_update"][lang])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", required=True, choices=["en", "fr"])
    args = parser.parse_args()

    lang = args.lang
    print(MESSAGES["start"][lang])
    print(MESSAGES["explain"][lang])

    accept = input(MESSAGES["accept_prompt"][lang]).strip().lower()
    if accept not in ["", "y", "o"]:
        print(MESSAGES["accept_cancelled"][lang].format(lang))
        sys.exit(1)

    ensure_lirc_installed(lang)
    update_config_txt(lang)
    update_lirc_options(lang)

    print(MESSAGES["moode_reminder"][lang])
    print(MESSAGES["remote_setup_info"][lang])

    reboot = input(MESSAGES["reboot_prompt"][lang]).strip().lower()
    if reboot in ["", "y", "o"]:
        print(MESSAGES["rebooting"][lang])
        run("sudo reboot")
    else:
        print(MESSAGES["reboot_cancelled"][lang])

if __name__ == "__main__":
    main()
