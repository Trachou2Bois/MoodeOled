#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 MoodeOled project / Benoit Toufflet
import os
import sys
import subprocess
import time
import webbrowser
import threading
import configparser
import shlex

CONFIG_INI = os.path.expanduser("~/MoodeOled/config.ini")
LIRC_CONF_DIR = "/etc/lirc/lircd.conf.d"
ITEMS_PER_PAGE = 20

MESSAGES = {
    "language_prompt": {
        "en": "Language / Langue [en/fr] > ",
        "fr": "Langue / Language [fr/en] > "
    },
    "help_unavailable": {
        "en": "⚠️ Cannot open help window.\nEnable X forwarding or check the README:\nhttps://github.com/Trachou2Bois/MoodeOled",
        "fr": "⚠️ Ouverture de l'aide à la configuration des touches impossible.\nActivez la redirection X11 si possible ou consultez le README:\nhttps://github.com/Trachou2Bois/MoodeOled"
    },
    "error_lirc_missing": {
        "en": "❌ LIRC is not installed.",
        "fr": "❌ LIRC n'est pas installé."
    },
    "lirc_prompt": {
        "en": "Would you like to install LIRC now? (requires an IR receiver connected to the GPIO pin) [Y/n] > ",
        "fr": "Voulez-vous installer LIRC maintenant? (nécessite un récepteur ir branché sur broche gpio) [O/n] > "
    },
    "lirc_skip": {
        "en": "⚠️ LIRC configuration canceled. You can configure it later manually or using:\n' python3 ~/MoodeOled/install/install_lirc_remote.py '",
        "fr": "⚠️ Configuration de LIRC annulée. Vous pourrez le configurer plus tard manuellement ou avec:\n' python3 ~/MoodeOled/install/install_lirc_remote.py '"
    },
    "lirc_installed": {
        "en": "✅ LIRC is installed.",
        "fr": "✅ LIRC est installé."
        },
    "start": {
        "en": "⇨ IR Remote configuration",
        "fr": "⇨ Configuration de la télécommande IR"
    },
    "menu": {
        "en": (
            "\n[1] Test IR hardware (mode2) - Check if the IR receiver is working\n"
            "[2] Download a pre-configured remote from the database (irdb-get)\n"
            "[3] Learn a new remote (irrecord) - If no similar config is available\n"
            "[4] Manage configs - Edit, add keys, enable/disable, delete\n"
            "[5] Test key decoding (irw) - Verify that LIRC is properly interpreting keys\n"
            "[6] Map keys to MoodeOLED actions (If your keys do not match those of MoodeOled)\n"
            "[7] Quit\n> "
        ),
        "fr": (
            "\n[1] Test matériel IR (mode2) - Vérifier si le récepteur IR fonctionne\n"
            "[2] Télécharger une configuration de télécommande existante (irdb-get)\n"
            "[3] Apprentissage d'une télécommande (irrecord) - Si aucune config similaire\n"
            "[4] Gérer les configurations - Éditer, ajouter des touches, activer/désactiver, supprimer\n"
            "[5] Test du décodage des touches (irw) - Vérifier que LIRC interprète correctement les touches\n"
            "[6] Mapper les touches avec les actions MoodeOLED (Si vos touches ne correspondent pas à celles de MoodeOled)\n"
            "[7] Quitter\n> "
        ),
    },
    "search_prompt": {
        "en": "Enter brand or model to search: ",
        "fr": "Entrez la marque ou le modèle à rechercher: "
    },
    "search_results": {
        "en": "\nIf your remote is not listed, try a similar model or with *generic*, else use learning.\n⇨ Search results (page {}/{}):",
        "fr": "\nSi votre télécommande n'est pas listée essayez un modèle similaire ou avec *generic*, sinon utilisez l'apprentissage.\n⇨ Résultats de la recherche (page {}/{}):"
    },
    "search_choice": {
        "en": "Enter index to download, 'n' next page, 'p' previous page, 'q' cancel: ",
        "fr": "Entrez l'index pour télécharger, 'n' page suivante, 'p' page précédente, 'q' annuler: "
    },
    "downloading": {
        "en": "⬇️ Downloading {} ...",
        "fr": "⬇️ Téléchargement de {} ..."
    },
    "download_done": {
        "en": "✅ Remote configuration saved to {}",
        "fr": "✅ Configuration de la télécommande enregistrée dans {}"
    },
    "testing_info": {
        "en": "▶️ mode2 will display raw IR pulses to check if your receiver is working.\nIf nothing appears, check your wiring or hardware (Ctrl+C to quit).",
        "fr": "▶️ mode2 affichera les signaux IR bruts pour vérifier si votre récepteur fonctionne.\nSi rien n'apparaît, vérifiez votre câblage ou votre matériel (Ctrl+C pour quitter)."
    },
    "learning_info": {
        "en": "▶️ Learning mode started (irrecord).\nPress the buttons on your remote so LIRC can record them (Ctrl+C to stop).",
        "fr": "▶️ Mode apprentissage démarré (irrecord).\nAppuyez sur les touches de votre télécommande pour que LIRC les enregistre (Ctrl+C pour arrêter)."
    },
    "testing_irw": {
        "en": "▶️ Testing key decoding (irw).\nPress buttons on your remote to verify that LIRC detects them correctly (Ctrl+C to quit).",
        "fr": "▶️ Test du décodage des touches (irw).\nAppuyez sur les touches de votre télécommande pour vérifier que LIRC les détecte correctement (Ctrl+C pour quitter)."
    },
    "config_list": {
        "en": "\nIf your remote is not configured, use learning or search.\n⇨ Select the configuration to be modified (page {}/{}):",
        "fr": "\nSi votre télécommande n'est pas configurée utilisez l'apprentissage ou la recherche.\n⇨ Choisissez la configuration à modifier (page {}/{}):"
    },
    "config_actions": {
    "en": "\n[1] Edit config manually\n[2] Add new keys (irrecord -u)\n[3] Edit key mapping\[4] {}\n[5] Delete config\n[6] Back\nn> ",
    "fr": "\n[1] Éditer la config manuellement\n[2] Ajouter des nouvelles touches (irrecord -u)\n[3] Modifier le mapping des touches\n[4] {}\n[5] Supprimer config\n[6] Retour\n> "
},
    "disable_config": {
        "en": "Disable config (.back)",
        "fr": "Désactiver config (.back)"
    },
    "enable_config": {
        "en": "Enable config",
        "fr": "Réactiver config"
    },
    "disabled": {
        "en": "✅ Config disabled.",
        "fr": "✅ Configuration désactivée."
    },
    "enabled": {
        "en": "✅ Config re-enabled.",
        "fr": "✅ Configuration réactivée."
    },
    "deleted": {
        "en": "✅ Config deleted.",
        "fr": "✅ Configuration supprimée."
    },
    "invalid_choice": {
        "en": "❌ Invalid choice.",
        "fr": "❌ Choix invalide."
    },
    "exiting": {
        "en": "Exiting.",
        "fr": "Sortie."
    },
    "lirc_restart": {
        "en": "✅ LIRC service restarted.",
        "fr": "✅ Service LIRC redémarré."
    },
    "nowoled_restart": {
        "en": "✅ nowoled service restarted.",
        "fr": "✅ Service nowoled redémarré."
    },
    "nowoled_stop": {
        "en": "✅ nowoled service stoped.",
        "fr": "✅ Service nowoled arreté."
    },
    "mapping_start": {
    "en": "🎛 Starting remote key mapping...",
    "fr": "🎛 Démarrage du mappage des touches de la télécommande..."
    },
    "mapping_press_key": {
        "en": "Recording button for '{}', Press ENTER to start (or type 'skip' to ignore): ",
        "fr": "Enregistrement de la touche pour '{}', Appuyez sur ENTREE pour démarrer (ou tapez 'skip' pour ignorer): "
    },
    "mapping_listen": {
        "en": "▶️ Press the remote key for '{}' (Ctrl+C to cancel)...",
        "fr": "▶️ Appuyez sur la touche de la télécommande pour '{}' (Ctrl+C pour annuler)..."
    },
    "mapping_saved": {
        "en": "✅ Mapping saved in config.ini",
        "fr": "✅ Mappage enregistré dans config.ini"
    },
    "mapping_cancelled": {
        "en": "⚠️ Mapping cancelled.",
        "fr": "⚠️ Mappage annulé."
    },
    "mapping_detected": {
        "en": "➡️ Detected key: {}",
        "fr": "➡️ Touche détectée : {}"
    },
    "mapping_conflict": {
        "en": "⚠️ The key '{}' is already assigned to '{}'.",
        "fr": "⚠️ La touche '{}' est déjà assignée à '{}'."
    },
    "mapping_override": {
        "en": "Do you want to reassign it to the new action? (o/N): ",
        "fr": "Voulez-vous la réassigner à la nouvelle action ? (o/N) : "
    },
    "mapping_reassigned": {
        "en": "✅ '{}' reassigned to '{}'.",
        "fr": "✅ '{}' réassignée à '{}'."
    },
    "mapping_reserved": {
        "en": "⚠️ '{}' is a MoodeOLED system key.",
        "fr": "⚠️ '{}' est une touche système de MoodeOLED."
    },
    "mapping_force_reserved": {
        "en": "Do you want to assign it anyway? (o/N): ",
        "fr": "Voulez-vous quand même l'assigner ? (o/N) : "
    },
    "optional_keys_prompt": {
        "en": "Would you like to configure optional multimedia keys (volume, mute, next, prev...)? [Y/n] > ",
        "fr": "Voulez-vous aussi configurer les touches multimédia optionnelles (volume, mute, suivant, précédent...) ? [O/n] > "
    }
}

def can_open_tkinter():
    return "DISPLAY" in os.environ and os.environ["DISPLAY"]

def show_help_window(lang):
    def open_help():
        try:
            import tkinter as tk
            from tkinter import scrolledtext

            help_text = {
                "en": (
                    "ℹ️ LIRC Remote Configuration Help\n\n"
                    "Required keys for MoodeOLED scripts:\n\n"
                    "• KEY_UP        → Navigate up / Volume + (outside menu)\n"
                    "• KEY_DOWN      → Navigate down / Volume - (outside menu)\n"
                    "• KEY_LEFT      → Previous / Seek -10s (long press) or menu left\n"
                    "• KEY_RIGHT     → Next / Seek +10s (long press) or menu right\n"
                    "• KEY_OK        → Open menu / Tools menu (long press) / Confirm\n"
                    "• KEY_BACK      → Switch between nowoled/navoled/queoled (short/long)\n"
                    "• KEY_INFO      → Show context help\n"
                    "• KEY_CHANNELUP → Context action (e.g. add to favorites)\n"
                    "• KEY_CHANNELDOWN → Context action (e.g. remove from queue)\n"
                    "• KEY_PLAY      → Play/Pause or Shutdown (long press)\n\n"
                    "Optional keys (if available on remote):\n\n"
                    "• KEY_STOP      → Stop playback\n"
                    "• KEY_NEXT      → Next / Seek +10s (long press)\n"
                    "• KEY_PREVIOUS  → Previous / Seek -10s (long press)\n"
                    "• KEY_FORWARD   → Seek +10s\n"
                    "• KEY_REWIND    → Seek -10s\n"
                    "• KEY_VOLUMEUP  → Volume +\n"
                    "• KEY_VOLUMEDOWN → Volume -\n"
                    "• KEY_MUTE      → Mute\n"
                    "• KEY_POWER     → Reboot or Shutdown (long press)\n\n"
                    "⚠️ After any change in LIRC configuration, LIRC and nowoled will be restarted automatically.\n"
                ),
                "fr": (
                    "ℹ️ Aide configuration télécommande LIRC\n\n"
                    "(Liste des noms de touches à renseigner lors de l'apprentissage via irrecord)\n\n"
                    "Touches indispensables pour les scripts MoodeOLED:\n"
                    "• KEY_UP        → Navigation haut / Volume + (hors menu)\n"
                    "• KEY_DOWN      → Navigation bas / Volume - (hors menu)\n"
                    "• KEY_LEFT      → Précédent / Seek -10s (appui long) ou menu gauche\n"
                    "• KEY_RIGHT     → Suivant / Seek +10s (appui long) ou menu droit\n"
                    "• KEY_OK        → Ouvrir menu / Menu Outils (appui long) / Validation\n"
                    "• KEY_BACK      → Basculer entre nowoled/navoled/queoled (court/long)\n"
                    "• KEY_INFO      → Afficher l'aide contextuelle\n"
                    "• KEY_CHANNELUP → Action contextuelle (ex: ajouter favoris)\n"
                    "• KEY_CHANNELDOWN → Action contextuelle (ex: retirer de la file)\n"
                    "• KEY_PLAY      → Lecture/Pause ou Extinction (appui long)\n\n"
                    "Touches optionnelles (si présentes sur la télécommande):\n"
                    "• KEY_STOP      → Arrêter lecture\n"
                    "• KEY_NEXT      → Suivant / Seek +10s (appui long)\n"
                    "• KEY_PREVIOUS  → Précédent / Seek -10s (appui long)\n"
                    "• KEY_FORWARD   → Seek +10s\n"
                    "• KEY_REWIND    → Seek -10s\n"
                    "• KEY_VOLUMEUP  → Volume +\n"
                    "• KEY_VOLUMEDOWN → Volume -\n"
                    "• KEY_MUTE      → Mute\n"
                    "• KEY_POWER     → Redémarrer ou Éteindre (appui long)\n\n"
                    "⚠️ Après toute modification de configuration LIRC, les services LIRC et nowoled seront redémarrés automatiquement.\n"
                )
            }

            window = tk.Tk()
            window.title("Help - LIRC" if lang == "en" else "Aide - LIRC")
            window.geometry("600x400")

            text_area = scrolledtext.ScrolledText(window, wrap=tk.WORD, font=("Arial", 12))
            text_area.insert(tk.END, help_text[lang])
            text_area.configure(state="disabled")
            text_area.pack(expand=True, fill="both")

            btn_close = tk.Button(window, text="OK", command=window.destroy)
            btn_close.pack(pady=5)

            window.mainloop()
        except Exception:
            pass

    thread = threading.Thread(target=open_help, daemon=True)
    thread.start()

def run(cmd, sudo=False, check=True):
    if sudo:
        cmd = "sudo " + cmd
    subprocess.run(cmd, shell=True, check=True)

def check_lirc_installed():
    try:
        subprocess.run("dpkg -s lirc", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def restart_lirc_and_nowoled(lang):
    try:
        run("systemctl restart lircd", sudo=True)
        print(MESSAGES["lirc_restart"][lang])
        time.sleep(0.5)
        run("systemctl restart nowoled", sudo=True)
        print(MESSAGES["nowoled_restart"][lang])
    except subprocess.CalledProcessError:
        pass

def stop_nowoled(lang):
    run("systemctl stop nowoled", sudo=True)
    print(MESSAGES["nowoled_stop"][lang])

def test_ir(lang):
    print(MESSAGES["testing_info"][lang])
    stop_nowoled(lang)
    try:
        run("mode2 -d /dev/lirc0", sudo=False, check=False)
    except KeyboardInterrupt:
        pass
    restart_lirc_and_nowoled(lang)

def search_remotes(query):
    result = subprocess.run(f"irdb-get find '{query}'", shell=True, capture_output=True, text=True)
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    return lines

def download_remote(selected, lang):
    print(MESSAGES["downloading"][lang].format(selected))
    run(f"cd {LIRC_CONF_DIR} && sudo irdb-get download '{selected}'", sudo=False)
    print(MESSAGES["download_done"][lang].format(LIRC_CONF_DIR))
    restart_lirc_and_nowoled(lang)

def learn_ir(lang):
    print(MESSAGES["learning_info"][lang])
    stop_nowoled(lang)
    try:
        run(f"cd {LIRC_CONF_DIR} && sudo irrecord -k -d /dev/lirc0", sudo=False, check=False)
    except KeyboardInterrupt:
        pass
    restart_lirc_and_nowoled(lang)

def list_configs():
    files = sorted(
        [f for f in os.listdir(LIRC_CONF_DIR) if f.endswith(".lircd.conf") or f.endswith(".lircd.conf.back")]
    )
    return [os.path.join(LIRC_CONF_DIR, f) for f in files]

def test_irw(lang):
    print(MESSAGES["testing_irw"][lang])
    stop_nowoled(lang)
    try:
        run("irw", sudo=False, check=False)
    except KeyboardInterrupt:
        pass
    restart_lirc_and_nowoled(lang)

def toggle_config_state(config_file, lang):
    if config_file.endswith(".back"):
        new_file = config_file[:-5]
        run(f"mv '{config_file}' '{new_file}'", sudo=True)
        print(MESSAGES["enabled"][lang])
    else:
        new_file = config_file + ".back"
        run(f"mv '{config_file}' '{new_file}'", sudo=True)
        print(MESSAGES["disabled"][lang])
    restart_lirc_and_nowoled(lang)

def delete_config(config_file, lang):
    run(f"rm '{config_file}'", sudo=True)
    print(MESSAGES["deleted"][lang])
    restart_lirc_and_nowoled(lang)

def manage_configs(lang):
    configs = list_configs()
    if not configs:
        print("❌ " + ("No configs found." if lang == "en" else "Aucune configuration trouvée."))
        return

    total_pages = (len(configs) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = 0

    while True:
        start = page * ITEMS_PER_PAGE
        end = min(start + ITEMS_PER_PAGE, len(configs))
        print(MESSAGES["config_list"][lang].format(page + 1, total_pages))
        for i, conf in enumerate(configs[start:end]):
            status = "[DISABLED]" if conf.endswith(".back") else "[ACTIVE]"
            print(f"[{i}] {status} {conf}")

        choice = input("Entrez l'index, 'n' page suivante, 'p' page précédente, 'q' annuler: ").strip().lower()
        if choice == "q":
            break
        elif choice == "n" and page + 1 < total_pages:
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice.isdigit():
            idx = int(choice)
            if 0 <= idx < (end - start):
                config_file = configs[start + idx]
                while True:
                    toggle_label = MESSAGES["enable_config"][lang] if config_file.endswith(".back") else MESSAGES["disable_config"][lang]
                    action = input(MESSAGES["config_actions"][lang].format(toggle_label)).strip()
                    if action == "1":
                        run(f"nano '{config_file}'", sudo=True)
                        restart_lirc_and_nowoled(lang)
                    elif action == "2":
                        stop_nowoled(lang)
                        run(f"cd {LIRC_CONF_DIR} && sudo irrecord -k -d /dev/lirc0 -u '{config_file}'", sudo=False)
                        restart_lirc_and_nowoled(lang)
                    elif action == "3":
                        map_remote_keys(lang, edit_mode=True)
                        break
                    elif action == "4":
                        toggle_config_state(config_file, lang)
                        break
                    elif action == "5":
                        delete_config(config_file, lang)
                    elif action == "6":
                        break
                    else:
                        print(MESSAGES["invalid_choice"][lang])
                break
            else:
                print(MESSAGES["invalid_choice"][lang])
        else:
            print(MESSAGES["invalid_choice"][lang])

def save_remote_mapping(config, required_keys, optional_keys):
    if os.path.exists(CONFIG_INI):
        with open(CONFIG_INI, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = []

    new_section = []
    new_section.append("[remote_mapping]\n")

    # Required keys
    new_section.append("\n# Required keys (essential for MoodeOLED navigation)\n")
    for key in required_keys:
        value = config["remote_mapping"].get(key, "—")
        new_section.append(f"{key} = {value}\n")

    # Optional keys
    new_section.append("\n# Optional keys (additional multimedia controls)\n")
    for key in optional_keys:
        value = config["remote_mapping"].get(key, "—")
        new_section.append(f"{key} = {value}\n")

    # Identifier les bornes de la section [remote_mapping]
    start_idx, end_idx = None, None
    for i, line in enumerate(lines):
        if line.strip().lower() == "[remote_mapping]":
            start_idx = i
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith("[") and j > i:
                    end_idx = j
                    break
            if end_idx is None:
                end_idx = len(lines)
            break

    if start_idx is not None:
        lines = lines[:start_idx] + new_section + lines[end_idx:]
    else:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines += ["\n"] + new_section

    with open(CONFIG_INI, "w", encoding="utf-8") as f:
        f.writelines(lines)

def map_remote_keys(lang, edit_mode=False):
    print(MESSAGES["mapping_start"][lang])
    required_keys = [
        "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
        "KEY_OK", "KEY_BACK", "KEY_INFO",
        "KEY_CHANNELUP", "KEY_CHANNELDOWN", "KEY_PLAY"
    ]
    optional_keys = [
        "KEY_PAUSE", "KEY_STOP", "KEY_NEXT", "KEY_PREVIOUS",
        "KEY_FORWARD", "KEY_REWIND", "KEY_VOLUMEUP",
        "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_POWER"
    ]
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_INI):
        config.read(CONFIG_INI)
    if "remote_mapping" not in config:
        config["remote_mapping"] = {}
    stop_nowoled(lang)
    try:
        if not edit_mode:
            # Mapping des touches obligatoires
            for key in required_keys:
                map_single_key(key, config, lang)
            choice = input(MESSAGES["optional_keys_prompt"][lang]).strip().lower()
            if choice in ["", "y", "o"]:
                for key in optional_keys:
                    map_single_key(key, config, lang)
        # === Mode édition ===
        while True:
            print("\n" + ("📋 Required keys:" if lang == "en" else "📋 Touches indispensables :"))
            for idx, key in enumerate(required_keys, 1):
                mapped = config["remote_mapping"].get(key, "—")
                display_value = mapped if mapped != "—" else ("Not mapped" if lang == "en" else "Non mappée")
                print(f"[{idx}] {key} → {display_value}")

            print("\n" + ("📋 Optional keys:" if lang == "en" else "📋 Touches optionnelles :"))
            for idx, key in enumerate(optional_keys, len(required_keys) + 1):
                mapped = config["remote_mapping"].get(key, "—")
                display_value = mapped if mapped != "—" else ("Not mapped" if lang == "en" else "Non mappée")
                print(f"[{idx}] {key} → {display_value}")

            prompt = "Enter index to re-map, 's' to save, 'c' to cancel:" if lang == "en" else \
                    "Entrez l'index pour re-mapper, 's' pour sauvegarder, 'c' pour annuler :"
            action = input(f"\n{prompt}\n> ").strip().lower()
            if action == "s":
                save_remote_mapping(config, required_keys, optional_keys)
                print(MESSAGES["mapping_saved"][lang])
                break
            elif action == "c":
                print(MESSAGES["mapping_cancelled"][lang])
                break
            elif action.isdigit():
                idx = int(action)
                if 1 <= idx <= len(required_keys) + len(optional_keys):
                    all_keys = required_keys + optional_keys
                    key_to_remap = all_keys[idx - 1]
                    map_single_key(key_to_remap, config, lang)
                else:
                    print(MESSAGES["invalid_choice"][lang])
            else:
                print(MESSAGES["invalid_choice"][lang])
    finally:
        restart_lirc_and_nowoled(lang)

def map_single_key(key_name, config, lang):
    """Demande à l'utilisateur d'appuyer sur la touche correspondante et met à jour config."""
    user_input = input(MESSAGES["mapping_press_key"][lang].format(key_name)).strip().lower()
    if user_input == "skip":
        return  # Ne change pas la config

    print(MESSAGES["mapping_listen"][lang].format(key_name))
    irw = subprocess.Popen(["irw"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        for line in irw.stdout:
            parts = line.strip().split()
            if len(parts) >= 3:
                detected_key = parts[2].upper()

                # 1️⃣ Conflit avec un autre mappage existant
                for moodeoled_action, assigned_key in config["remote_mapping"].items():
                    if assigned_key == detected_key and moodeoled_action != key_name:
                        print(MESSAGES["mapping_conflict"][lang].format(detected_key, moodeoled_action))
                        choice = input(MESSAGES["mapping_override"][lang]).strip().lower()
                        if choice.startswith("o"):  # Oui → supprime ancien mappage
                            config["remote_mapping"][moodeoled_action] = ""
                            print(MESSAGES["mapping_reassigned"][lang].format(detected_key, key_name))
                        else:
                            print(MESSAGES["mapping_cancelled"][lang])
                            return

                # 2️⃣ Vérification des touches système MoodeOLED
                moodeoled_keys = [
                    "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
                    "KEY_OK", "KEY_BACK", "KEY_INFO",
                    "KEY_CHANNELUP", "KEY_CHANNELDOWN", "KEY_PLAY",
                    "KEY_PAUSE", "KEY_STOP", "KEY_NEXT", "KEY_PREVIOUS",
                    "KEY_FORWARD", "KEY_REWIND", "KEY_VOLUMEUP",
                    "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_POWER"
                ]

                if detected_key in moodeoled_keys and detected_key != key_name:
                    print(MESSAGES["mapping_reserved"][lang].format(detected_key))
                    choice = input(MESSAGES["mapping_force_reserved"][lang]).strip().lower()
                    if not choice.startswith("o"):  # Non → on annule
                        print(MESSAGES["mapping_cancelled"][lang])
                        return

                print(MESSAGES["mapping_detected"][lang].format(detected_key))
                config["remote_mapping"][key_name] = detected_key
                break

    except KeyboardInterrupt:
        print("\n" + MESSAGES["mapping_cancelled"][lang])
        raise
    finally:
        irw.terminate()

def main():
    lang = input(MESSAGES["language_prompt"]["en"]).strip().lower()
    if lang not in ("en", "fr"):
        lang = "en"
    print(MESSAGES["start"][lang])

    if not check_lirc_installed():
        print(MESSAGES["error_lirc_missing"][lang])
        choice = input(MESSAGES["lirc_prompt"][lang]).strip().lower()
        if choice in ["", "o", "y"]:
            lirc_script = os.path.expanduser("~/MoodeOled/install/lirc_setup.py")
            if os.path.exists(lirc_script):
                run(f"python3 {lirc_script} --lang {lang}")
            else:
                print("⚠️ lirc_setup.py not found.")
        else:
            print(MESSAGES["lirc_skip"][lang])
        sys.exit(1)
    else:
        print(MESSAGES["lirc_installed"][lang])

    if can_open_tkinter():
        show_help_window(lang)
    else:
        print(MESSAGES["help_unavailable"][lang])

    while True:
        choice = input(MESSAGES["menu"][lang]).strip()
        if choice == "1":
            test_ir(lang)
        if choice == "2":
            query = input(MESSAGES["search_prompt"][lang]).strip()
            lines = search_remotes(query)
            if not lines:
                print("❌ " + ("No results found." if lang == "en" else "Aucun résultat trouvé."))
                continue
            total_pages = (len(lines) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            page = 0
            while True:
                start = page * ITEMS_PER_PAGE
                end = min(start + ITEMS_PER_PAGE, len(lines))
                print(MESSAGES["search_results"][lang].format(page + 1, total_pages))
                for i, line in enumerate(lines[start:end]):
                    print(f"[{i}] {line}")
                choice_dl = input(MESSAGES["search_choice"][lang]).strip().lower()
                if choice_dl == "q":
                    break
                elif choice_dl == "n" and page + 1 < total_pages:
                    page += 1
                elif choice_dl == "p" and page > 0:
                    page -= 1
                elif choice_dl.isdigit():
                    idx = int(choice_dl)
                    if 0 <= idx < (end - start):
                        selected = lines[start + idx]
                        download_remote(selected, lang)
                        break
                    else:
                        print(MESSAGES["invalid_choice"][lang])
                else:
                    print(MESSAGES["invalid_choice"][lang])
        elif choice == "3":
            learn_ir(lang)
        elif choice == "4":
            manage_configs(lang)
        elif choice == "5":
            test_irw(lang)
        elif choice == "6":
            map_remote_keys(lang)
        elif choice == "7":
            print(MESSAGES["exiting"][lang])
            break
        else:
            print(MESSAGES["invalid_choice"][lang])

if __name__ == "__main__":
    main()
