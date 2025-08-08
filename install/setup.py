#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import os
import sys
import subprocess
import shutil

# --- Constantes ---
APT_DEPENDENCIES = [
    "python3-pil", "python3-venv", "python3-pip", "python3-tk",
    "i2c-tools", "libgpiod-dev", "python3-libgpiod", "python3-lgpio", "python3-setuptools"
]

LOW_RAM_THRESHOLD_MB = 1024
ZRAM_RECOMMENDED_MB = 280
DEFAULT_VENV_PATH = os.path.expanduser("~/.moodeoled-venv")
INSTALL_SCRIPT = os.path.expanduser("~/MoodeOled/install/install_services.py")
REQUIRED_MOODE_VERSION = "9.3.7"

# --- Messages multilingues ---
MESSAGES = {
    "choose_language": {"en": "Please choose your language:", "fr": "Veuillez choisir votre langue :"},
    "language_options": {"en": "[1] English\n[2] Français", "fr": "[1] Anglais\n[2] Français"},
    "invalid_choice": {"en": "Invalid choice. Defaulting to English.", "fr": "Choix invalide. Anglais sélectionné par défaut."},
    "install_apt": {"en": "Checking system dependencies...", "fr": "Vérification des dépendances système..."},
    "apt_missing": {"en": "Installing missing dependencies: {}", "fr": "Installation des dépendances manquantes : {}"},
    "moode_detect_fail": {"en": "❌ Unable to detect Moode version. Make sure you're running Moode >= 9.3.7.",
                         "fr": "❌ Impossible de détecter la version de Moode. Assurez-vous d'utiliser Moode ≥ 9.3.7."},
    "moode_too_old": {"en": "❌ Your version of Moode ({}) is too old. Minimum required is 9.3.7.",
                      "fr": "❌ Votre version de Moode ({}) est trop ancienne. La version minimale requise est 9.3.7."},
    "moode_ok": {"en": "✅ Moode version {} detected — OK.", "fr": "✅ Version de Moode {} détectée — OK."},
    "user_detected": {"en": "⇨ Detected user: {}", "fr": "⇨ Utilisateur détecté : {}"},
    "low_ram_warning": {"en": "⚠️  This device has less than {}MB RAM. Enable ZRAM (~{}MB, lz4) for better stability.",
                        "fr": "⚠️  Ce périphérique a moins de {} Mo de RAM. Activez ZRAM (~{} Mo, lz4) pour plus de stabilité."},
    "zram_prompt": {"en": "Would you like to enable ZRAM (~{}MB, lz4) and disable the default swap? [Y/n]",
                    "fr": "Voulez-vous activer ZRAM ({} Mo, lz4) et désactiver le swap par défaut ? [O/n]"},
    "zram_install": {"en": "Installing and configuring ZRAM...", "fr": "Installation et configuration de ZRAM..."},
    "zram_done": {"en": "✅ ZRAM has been configured. A reboot is recommended.", "fr": "✅ ZRAM a été configuré. Un redémarrage est recommandé."},
    "zram_failed": {"en": "❌ Failed to configure ZRAM.","fr": "❌ Échec de la configuration de ZRAM."},
    "venv_found": {"en": "Virtual environment found at {}.", "fr": "Environnement virtuel trouvé à {}."},
    "venv_reuse_choice": {"en": "[1] Reuse\n[2] Delete and recreate\n[3] Cancel installation", "fr": "[1] Réutiliser\n[2] Supprimer et recréer\n[3] Annuler l'installation"},
    "venv_delete": {"en": "🗑 Deleting existing virtual environment...", "fr": "🗑 Suppression de l'environnement virtuel existant..."},
    "venv_main_choice": {"en": "Choose environment:\n[1] Create dedicated venv at {}\n[2] Specify another path\n[3] Cancel installation",
                         "fr": "Choisissez l'environnement :\n[1] Créer un venv dédié à {}\n[2] Spécifier un autre chemin\n[3] Annuler l'installation"},
    "venv_enter_path": {"en": "Enter the full path of the venv (leave empty to cancel):", "fr": "Entrez le chemin complet du venv (laisser vide pour annuler) :"},
    "venv_invalid_parent": {"en": "❌ Parent directory {} does not exist or is not accessible.",
                           "fr": "❌ Le répertoire parent {} n'existe pas ou n'est pas accessible."},
    "venv_confirm_create": {"en": "⚠️  Path '{}' does not exist. Create a new venv here? [Y/n]",
                           "fr": "⚠️  Le chemin '{}' n'existe pas. Créer un nouveau venv ici ? [O/n]"},
    "venv_invalid_path": {"en": "❌ Invalid path, please try again.", "fr": "❌ Chemin invalide, veuillez réessayer."},
    "venv_cancelled": {"en": "❌ Installation cancelled.", "fr": "❌ Installation annulée."},
    "install_pip": {"en": "Installing Python dependencies...", "fr": "Installation des dépendances Python..."},
    "install_continue": {"en": "Launching installation script...", "fr": "Lancement du script d'installation..."},
    "i2c_check": {"en": "Checking I²C configuration...", "fr": "Vérification de la configuration I²C..."},
    "i2c_disabled": {"en": "⚠️  I²C is disabled. Would you like to enable it now? [Y/n]",
                     "fr": "⚠️  L'I²C est désactivé. Voulez-vous l'activer maintenant ? [O/n]"},
    "i2c_enabling": {"en": "Enabling I²C...", "fr": "Activation de l'I²C..."},
    "i2c_enabled": {"en": "✅ I²C is enabled.", "fr": "✅ L'I²C est activé."},
    "i2c_reboot_required": {"en": "⇨ I²C has been enabled. Please reboot your Raspberry Pi and re-run this script.",
                           "fr": "⇨ L'I²C a été activé. Veuillez redémarrer votre Raspberry Pi puis relancer ce script."},
    "i2c_enable_failed": {"en": "❌ Failed to enable I²C. Please enable it manually with 'sudo raspi-config'.",
                         "fr": "❌ Échec de l'activation de l'I²C. Activez-la manuellement avec 'sudo raspi-config'."},
    "i2c_addresses_detected": {"en": "✅ I²C addresses detected: {}", "fr": "✅ Adresses I²C détectées : {}"},
    "i2c_display_ok": {"en": "✅ OLED display detected on I²C bus.", "fr": "✅ Écran OLED détecté sur le bus I²C."},
    "i2c_no_display": {"en": "⚠️  No OLED display detected on I²C bus (expected address 0x3C or 0x3D).",
                       "fr": "⚠️  Aucun écran OLED détecté sur le bus I²C (adresse attendue 0x3C ou 0x3D)."},
    "i2c_check_wiring": {"en": "❌ Check wiring or address jumpers on the OLED module.",
                         "fr": "❌ Vérifiez le câblage ou les cavaliers d'adresse sur le module OLED."},
    "i2c_no_devices": {"en": "❌ No I²C devices detected. Check wiring and connections.",
                       "fr": "❌ Aucun périphérique I²C détecté. Vérifiez le câblage et les connexions."}
}

lang = "en"

# --- Fonctions utilitaires ---

def run_command(cmd):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True)

def choose_language():
    global lang
    print(MESSAGES["choose_language"][lang])
    print(MESSAGES["language_options"][lang])
    choice = input(" > ").strip()
    if choice == "2":
        lang = "fr"
    elif choice != "1":
        print(MESSAGES["invalid_choice"][lang])

def install_apt_dependencies():
    print(MESSAGES["install_apt"][lang])
    missing = [pkg for pkg in APT_DEPENDENCIES if run_command(f"dpkg -s {pkg}").returncode != 0]
    if missing:
        print(MESSAGES["apt_missing"][lang].format(", ".join(missing)))
        subprocess.run(f"sudo apt update && sudo apt install -y {' '.join(missing)}", shell=True, check=True)

def get_moode_version():
    result = run_command("moodeutl --mooderel")
    if result.returncode == 0:
        return result.stdout.strip().split()[0]
    return None

def check_moode_version():
    current = get_moode_version()
    if not current:
        print(MESSAGES["moode_detect_fail"][lang])
        sys.exit(1)
    if tuple(map(int, current.split("."))) < tuple(map(int, REQUIRED_MOODE_VERSION.split("."))):
        print(MESSAGES["moode_too_old"][lang].format(current))
        sys.exit(1)
    print(MESSAGES["moode_ok"][lang].format(current))

def detect_user():
    user = os.getenv("SUDO_USER") or os.getenv("USER") or "unknown"
    print(MESSAGES["user_detected"][lang].format(user))
    return user

def configure_zram():
    print(MESSAGES["zram_install"][lang])

    try:
        # Installer zram-tools
        subprocess.run("sudo apt install -y zram-tools", shell=True, check=True)

        # Configurer /etc/default/zramswap
        config_content = f"""# Compression algorithm selection
# speed: lz4 > zstd > lzo
# compression: zstd > lzo > lz4
# This is not inclusive of all that is available in latest kernels
# See /sys/block/zram0/comp_algorithm (when zram module is loaded) to see
# what is currently set and available for your kernel[1]
# [1]  https://github.com/torvalds/linux/blob/master/Documentation/blockdev/zram.txt#L86
#ALGO=lz4

# Specifies the amount of RAM that should be used for zram
# based on a percentage the total amount of available memory
# This takes precedence and overrides SIZE below
#PERCENT=50

# Specifies a static amount of RAM that should be used for
# the ZRAM devices, this is in MiB
# Use 256 for a Raspberry Pi Zero 2 with 512MB of RAM
SIZE={ZRAM_RECOMMENDED_MB}
# Use 1024 for a Raspberry Pi 4 or Raspberry Pi 5 with 4GB of RAM
#SIZE=1024

# Specifies the priority for the swap devices, see swapon(2)
# for more details. Higher number = higher priority
# This should be higher than hdd/ssd swaps.
PRIORITY=100
"""
        with open("/tmp/zramswap", "w") as f:
            f.write(config_content)
        subprocess.run("sudo mv /tmp/zramswap /etc/default/zramswap", shell=True, check=True)
        subprocess.run("sudo dphys-swapfile swapoff || true", shell=True)
        subprocess.run("sudo systemctl disable dphys-swapfile || true", shell=True)
        subprocess.run("sudo systemctl restart zramswap", shell=True, check=True)
        print(MESSAGES["zram_done"][lang])
    except subprocess.CalledProcessError:
        print(MESSAGES["zram_failed"][lang])

def check_ram():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    mem_mb = int(line.split()[1]) // 1024
                    if mem_mb < LOW_RAM_THRESHOLD_MB:
                        print(MESSAGES["low_ram_warning"][lang].format(LOW_RAM_THRESHOLD_MB, ZRAM_RECOMMENDED_MB))
                        choice = input(MESSAGES["zram_prompt"][lang].format(ZRAM_RECOMMENDED_MB) + " > ").strip().lower()
                        if choice in ["", "y", "o"]:
                            configure_zram()
                    break
    except Exception:
        pass

def is_valid_venv(path):
    return os.path.isfile(os.path.join(path, "bin", "python"))

def validate_venv_path(path):
    try:
        path = os.path.expanduser(path.strip())
        path = os.path.abspath(path)
        path = path.rstrip("/")

        parent_dir = os.path.dirname(path)
        if not os.path.exists(parent_dir):
            print(MESSAGES["venv_invalid_parent"][lang].format(parent_dir))
            return None
        if not os.access(parent_dir, os.W_OK):
            print(MESSAGES["venv_invalid_parent"][lang].format(parent_dir))
            return None
        return path
    except Exception as e:
        print(f"❌ Exception during path validation: {e}")
        return None

def prompt_yes_no(message):
    while True:
        response = input(message + " > ").strip().lower()
        if response in ["", "y", "o"]:
            return True
        elif response == "n":
            return False
        else:
            print(MESSAGES["venv_invalid_path"][lang])

def check_virtualenv():
    if os.path.exists(DEFAULT_VENV_PATH):
        print(MESSAGES["venv_found"][lang].format(DEFAULT_VENV_PATH))
        print(MESSAGES["venv_reuse_choice"][lang])
        while True:
            choice = input(" > ").strip()
            if choice == "1":
                return DEFAULT_VENV_PATH
            elif choice == "2":
                print(MESSAGES["venv_delete"][lang])
                try:
                    shutil.rmtree(DEFAULT_VENV_PATH)
                except Exception as e:
                    print(f"❌ Failed to delete {DEFAULT_VENV_PATH}: {e}")
                    sys.exit(1)
                break
            elif choice == "3":
                print(MESSAGES["venv_cancelled"][lang])
                sys.exit(0)
            else:
                print(MESSAGES["invalid_choice"][lang])

    print(MESSAGES["venv_main_choice"][lang].format(DEFAULT_VENV_PATH))
    while True:
        choice = input(" > ").strip()
        if choice in ["1", ""]:
            return DEFAULT_VENV_PATH
        elif choice == "2":
            while True:
                print(MESSAGES["venv_enter_path"][lang])
                user_path = input(" > ").strip()
                if user_path == "":
                    print(MESSAGES["venv_cancelled"][lang])
                    sys.exit(0)

                venv_path = validate_venv_path(user_path)
                if not venv_path:
                    continue

                if os.path.exists(venv_path):
                    if is_valid_venv(venv_path):
                        return venv_path
                    else:
                        print(MESSAGES["venv_invalid_path"][lang])
                        continue
                else:
                    if prompt_yes_no(MESSAGES["venv_confirm_create"][lang].format(venv_path)):
                        return venv_path
                    else:
                        print(MESSAGES["venv_invalid_path"][lang])
                        continue
        elif choice == "3":
            print(MESSAGES["venv_cancelled"][lang])
            sys.exit(0)
        else:
            print(MESSAGES["invalid_choice"][lang])

def check_i2c():
    print(MESSAGES["i2c_check"][lang])
    result = run_command("sudo raspi-config nonint get_i2c")

    if result.returncode != 0 or result.stdout.strip() != "0":
        choice = input(MESSAGES["i2c_disabled"][lang] + " > ").strip().lower()
        if choice in ["", "y", "o"]:
            print(MESSAGES["i2c_enabling"][lang])
            try:
                subprocess.run("sudo raspi-config nonint do_i2c 0", shell=True, check=True)
                print(MESSAGES["i2c_enabled"][lang])
                print(MESSAGES["i2c_reboot_required"][lang])
            except Exception:
                print(MESSAGES["i2c_enable_failed"][lang])
            sys.exit(0)
        else:
            print(MESSAGES["i2c_enable_failed"][lang])
            sys.exit(1)

    result = run_command("i2cdetect -y 1")
    detected_addresses = []

    for line in result.stdout.splitlines():
        if ":" in line:
            parts = line.split(":")[1].split()
            for part in parts:
                if part != "--":
                    detected_addresses.append(part.lower())

    if detected_addresses:
        print(MESSAGES["i2c_addresses_detected"][lang].format(", ".join(["0x" + addr for addr in detected_addresses])))
        if "3c" in detected_addresses or "3d" in detected_addresses:
            print(MESSAGES["i2c_display_ok"][lang])
        else:
            print(MESSAGES["i2c_no_display"][lang])
            print(MESSAGES["i2c_check_wiring"][lang])
            sys.exit(1)
    else:
        print(MESSAGES["i2c_no_display"][lang])
        print(MESSAGES["i2c_no_devices"][lang])
        sys.exit(1)

def setup_virtualenv(venv_path):
    requirements_path = os.path.expanduser("~/MoodeOled/requirements.txt")

    if not os.path.exists(venv_path):
        print(f"Creating virtual environment at {venv_path} ...")
        try:
            subprocess.run(f"python3 -m venv {venv_path}", shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create virtual environment: {e}")
            sys.exit(1)

    pip_path = os.path.join(venv_path, "bin", "pip")
    if not os.path.isfile(pip_path):
        print(f"❌ pip not found in the virtual environment at {pip_path}.")
        sys.exit(1)

    try:
        subprocess.run(f"{pip_path} install --upgrade pip", shell=True, check=True)
        print(MESSAGES["install_pip"][lang])
        subprocess.run(f"{pip_path} install --requirement {requirements_path}", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Python dependencies: {e}")
        sys.exit(1)

def launch_install_script(lang, user, venv_path):
    print(MESSAGES["install_continue"][lang])
    python_path = os.path.join(venv_path, "bin", "python")
    if not os.path.isfile(python_path):
        print(f"❌ Python executable not found in virtualenv at {python_path}.")
        sys.exit(1)

    try:
        subprocess.run(f"{python_path} {INSTALL_SCRIPT} --lang {lang} --user {user} --venv {venv_path}", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation script failed: {e}")
        sys.exit(1)

# --- Programme principal ---
if __name__ == "__main__":
    choose_language()
    install_apt_dependencies()
    check_moode_version()
    check_i2c()
    user = detect_user()
    check_ram()
    venv_path = check_virtualenv()
    setup_virtualenv(venv_path)
    launch_install_script(lang, user, venv_path)
