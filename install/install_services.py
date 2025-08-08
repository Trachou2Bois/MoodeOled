#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import os
import sys
import subprocess
import shutil
import argparse

# --- Messages multilingues ---
MESSAGES = {
    "install_services": {
        "en": "⇨ Installing required services...",
        "fr": "⇨ Installation des services requis..."
    },
    "service_menu": {
        "en": "Service {}:\n[1] Install\n[2] View content\n[3] Cancel",
        "fr": "Service {}:\n[1] Installer\n[2] Afficher le contenu\n[3] Annuler"
    },
    "service_view_header": {
        "en": "----- {}.service -----",
        "fr": "----- {}.service -----"
    },
    "service_created": {
        "en": "✅ Service {} created successfully.",
        "fr": "✅ Service {} créé avec succès."
    },
    "service_enabled": {
        "en": "✅ Service {} enabled.",
        "fr": "✅ Service {} activé."
    },
    "service_skipped": {
        "en": "⚠️  Service {} installation cancelled.",
        "fr": "⚠️  Installation du service {} annulée."
    },
    "permission_denied": {
        "en": "❌ Permission denied. Please run this script with sudo.",
        "fr": "❌ Permission refusée. Veuillez exécuter ce script avec sudo."
    },
    "ready_script_update": {
        "en": "⇨ Updating ready-script...",
        "fr": "⇨ Mise à jour du ready-script..."
    },
    "ready_script_backup": {
        "en": "🔒 Backup of original ready-script created: {}",
        "fr": "🔒 Sauvegarde du ready-script original créée : {}"
    },
    "ready_script_done": {
        "en": "✅ ready-script updated.",
        "fr": "✅ ready-script mis à jour."
    },
    "hardware_explanation": {
        "en": "\n⚙️ Hardware configuration:\n"
              "- GPIO buttons or rotary: configure pins in config.ini.\n"
              "- IR Remote: requires LIRC. You can configure it now or later.\n",
        "fr": "\n⚙️ Configuration matérielle :\n"
              "- Boutons GPIO ou encodeur rotatif: configurez les broches dans config.ini.\n"
              "- Télécommande IR: nécessite LIRC. Vous pouvez le configurer maintenant ou plus tard.\n"
    },
    "lirc_prompt": {
        "en": "Would you like to instrall and configure LIRC now? (requires an IR receiver connected to the GPIO pin) [Y/n] > ",
        "fr": "Voulez-vous installer et configurer LIRC maintenant? (nécessite un récepteur ir branché sur broche gpio) [O/n] > "
    },
    "lirc_skip": {
        "en": "⚠️ LIRC configuration skipped. You can configure it later manually or via:\n' python3 ~/MoodeOled/install/lirc_setup.py --lang {} '",
        "fr": "⚠️ Configuration de LIRC ignorée. Vous pourrez le configurer plus tard manuellement ou via:\n' python3 ~/MoodeOled/install/lirc_setup.py --lang {} '"
    },
    "moode_reminder": {
        "en": "⚠️ Reminder: In Moode, enable:\n  - Ready Script (System)\n  - LCD Updater (Peripherals)",
        "fr": "⚠️ Rappel : Dans Moode, activez :\n  - Ready Script (Système)\n  - LCD Updater (Périphériques)"
    },
    "install_done": {
        "en": "✅ Installation complete.",
        "fr": "✅ Installation terminée."
    },
    "profile_update": {
        "en": "⇨ Updating ~/.profile with useful MoodeOled commands...",
        "fr": "⇨ Mise à jour de ~/.profile avec les commandes utiles pour MoodeOled..."
    },
    "profile_updated": {
        "en": "✅ ~/.profile updated successfully.",
        "fr": "✅ ~/.profile mis à jour avec succès."
    },
    "profile_update_error": {
        "en": "❌ Failed to update ~/.profile: {}",
        "fr": "❌ Échec de la mise à jour de ~/.profile : {}"
    },
    "reboot_prompt": {
        "en": "⇨ Do you want to reboot now? [Y/n] > ",
        "fr": "⇨ Voulez-vous redémarrer maintenant ? [O/n] > "
    },
    "rebooting": {
        "en": "⇨ Rebooting...",
        "fr": "⇨ Redémarrage en cours..."
    },
    "reboot_cancelled": {
        "en": "⚠️  Reboot cancelled. Please reboot manually later.",
        "fr": "⚠️  Redémarrage annulé. Veuillez redémarrer manuellement plus tard."
    }
}

# --- Définition des services ---
SERVICES = {
    "nowoled": """[Unit]
Description=MoOde Audio OLED Display (nowoled)
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/nowoled.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=200
StartLimitBurst=10

[Install]
WantedBy=multi-user.target
""",
    "navoled": """[Unit]
Description=MPD Navigation OLED Display (navoled)
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/navoled.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=200
StartLimitBurst=10

[Install]
WantedBy=multi-user.target
""",
    "queoled": """[Unit]
Description=MPD Queue OLED Display (queoled)
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/queoled.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=200
StartLimitBurst=10

[Install]
WantedBy=multi-user.target
""",
    "pioled-off": """[Unit]
Description=pioled-off

[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/bin/true
ExecStop={venv}/bin/python3 {project}/pioled-off.py

[Install]
WantedBy=multi-user.target
"""
}

READY_SCRIPT_PATH = "/var/local/www/commandw/ready-script.sh"
READY_SCRIPT_BACKUP = "/var/local/www/commandw/ready-script.sh.bak"
INSTALL_DIR = os.path.expanduser("~/MoodeOled/install/ready-script.sh")

# --- Fonctions utilitaires ---
def run_sudo(cmd):
    return subprocess.run(cmd, shell=True, check=True)

def write_service(name, content):
    path = f"/etc/systemd/system/{name}.service"
    tmp_path = f"/tmp/{name}.service"

    with open(tmp_path, "w") as f:
        f.write(content)

    run_sudo(f"sudo mv {tmp_path} {path}")
    run_sudo(f"sudo chown root:root {path}")
    run_sudo("sudo systemctl daemon-reload")

    print(MESSAGES["service_created"][lang].format(name))

def update_ready_script():
    print(MESSAGES["ready_script_update"][lang])

    if os.path.exists(READY_SCRIPT_PATH):
        run_sudo(f"sudo cp {READY_SCRIPT_PATH} {READY_SCRIPT_BACKUP}")
        print(MESSAGES["ready_script_backup"][lang].format(READY_SCRIPT_BACKUP))

    run_sudo(f"sudo cp {INSTALL_DIR} {READY_SCRIPT_PATH}")
    run_sudo(f"sudo chmod 755 {READY_SCRIPT_PATH}")
    run_sudo(f"sudo chown root:root {READY_SCRIPT_PATH}")

    print(MESSAGES["ready_script_done"][lang])

def configure_hardware():
    print(MESSAGES["hardware_explanation"][lang])
    choice = input(MESSAGES["lirc_prompt"][lang]).strip().lower()

    if choice in ["", "o", "y"]:
        lirc_script = os.path.expanduser("~/MoodeOled/install/lirc_setup.py")
        if os.path.exists(lirc_script):
            run_sudo(f"python3 {lirc_script} --lang {lang}")
        else:
            print("⚠️ lirc_setup.py not found.")
    else:
        print(MESSAGES["lirc_skip"][lang].format(lang))
        print(MESSAGES["moode_reminder"][lang])

        # Reboot prompt (moved here)
        print(MESSAGES["install_done"][lang])
        reboot = input(MESSAGES["reboot_prompt"][lang]).strip().lower()
        if reboot in ["", "o", "y"]:
            print(MESSAGES["rebooting"][lang])
            run_sudo("sudo reboot")
        else:
            print(MESSAGES["reboot_cancelled"][lang])

def append_to_profile():
    profile_path = os.path.expanduser("~/.profile")
    lines_to_add = [
        'echo " "',
        'echo "Moode debug => moodeutl -l"',
        'echo "Force Moode update => sudo /var/www/util/system-updater.sh moode9"',
        'echo "Configure IR remote => python3 ~/MoodeOled/install/install_lirc_remote.py"'
    ]

    print(MESSAGES["profile_update"][lang])

    try:
        # Lire contenu existant (si présent)
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = ""

        # Écriture uniquement si manquant
        with open(profile_path, "a", encoding="utf-8") as f:
            for line in lines_to_add:
                if line not in content:
                    f.write("\n" + line)

        print(MESSAGES["profile_updated"][lang])

    except Exception as e:
        print(MESSAGES["profile_update_error"][lang].format(e))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--venv", required=True)
    args = parser.parse_args()

    global lang, venv
    lang = args.lang
    user = args.user
    venv = args.venv
    project_path = os.path.expanduser("~/MoodeOled")

    print(MESSAGES["install_services"][lang])

    for name, template in SERVICES.items():
        while True:
            print(MESSAGES["service_menu"][lang].format(name))
            choice = input(" > ").strip()
            if choice == "2":
                print(MESSAGES["service_view_header"][lang].format(name))
                print(template.format(venv=venv, project=project_path, user=user))
                print("--------------------")
            elif choice == "1":
                service_content = template.format(venv=venv, project=project_path, user=user)
                try:
                    write_service(name, service_content)

                    # Activer uniquement pioled-off
                    if name == "pioled-off":
                        run_sudo(f"sudo systemctl enable {name}")
                        print(MESSAGES["service_enabled"][lang].format(name))

                except PermissionError:
                    print(MESSAGES["permission_denied"][lang])
                    sys.exit(1)
                break
            else:
                print(MESSAGES["service_skipped"][lang].format(name))
                break

    update_ready_script()
    configure_hardware()
    append_to_profile()

if __name__ == "__main__":
    main()
