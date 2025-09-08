#!/bin/bash
set -e

DRY_RUN=false
if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo "=== DRY-RUN mode activé : aucune suppression réelle ne sera effectuée ==="
fi

run_cmd() {
    if $DRY_RUN; then
        echo "[DRY-RUN] $*"
    else
        eval "$@"
    fi
}

echo "=== MoodeOLED Uninstallation Script ==="

# --- Détection utilisateur ---
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
else
    REAL_USER="$USER"
fi
USER_HOME=$(eval echo "~$REAL_USER")
echo "Utilisateur détecté : $REAL_USER"
echo "Home détecté : $USER_HOME"

# --- 1. Arrêt et désactivation des services ---
echo ">> Désactivation et suppression des services systemd"
SERVICES=("nowoled" "navoled" "queoled" "pioled-off")
for svc in "${SERVICES[@]}"; do
    if systemctl list-unit-files | grep -q "${svc}.service"; then
        run_cmd "sudo systemctl stop $svc || true"
        run_cmd "sudo systemctl disable $svc || true"
        run_cmd "sudo rm -f /etc/systemd/system/${svc}.service"
    fi
done
run_cmd "sudo systemctl daemon-reload"
run_cmd "sudo systemctl reset-failed"

# --- 2. Nettoyage de ~/.profile ---
PROFILE_FILE="$USER_HOME/.profile"
if [ -f "$PROFILE_FILE" ]; then
    echo ">> Nettoyage de $PROFILE_FILE"
    run_cmd "sudo -u $REAL_USER sed -i '/install_lirc_remote.py/d' $PROFILE_FILE"
fi

# --- 3. Suppression du venv ---
echo ">> Suppression de l'environnement virtuel"
run_cmd "sudo rm -rf $USER_HOME/.moodeoled-venv"

# --- 4. Nettoyage du ready script ---
READY_SCRIPT="/var/local/www/commandw/ready-script.sh"
if [ -f "$READY_SCRIPT" ]; then
    echo ">> Nettoyage du ready-script"
    run_cmd "sudo sed -i '/# Start the OLED display service/,/systemctl start nowoled/d' $READY_SCRIPT"
fi

# --- 5. Suppression des backups anciens ---
echo ">> Nettoyage des backups"
for path in "/boot/firmware" "/etc/lirc"; do
    if [ -d "$path" ]; then
        backups=( $(ls -t "$path" 2>/dev/null | grep '\.moodeoled-back-' || true) )
        if [ ${#backups[@]} -gt 1 ]; then
            echo "   - Suppression des backups anciens dans $path"
            for file in "${backups[@]:1}"; do
                run_cmd "sudo rm -rf $path/$file"
            done
        fi
    fi
done
if [ -f "/var/local/www/commandw/ready-script.sh.bak" ]; then
    echo "   - Suppression de ready-script.sh.bak"
    run_cmd "sudo rm -f /var/local/www/commandw/ready-script.sh.bak"
fi

# --- 6. Suppression du dossier principal ---
echo ">> Suppression du dossier MoodeOled"
run_cmd "sudo rm -rf $USER_HOME/MoodeOled"

echo "=== Désinstallation terminée ==="
if $DRY_RUN; then
    echo ">>> (aucune modification n'a été appliquée, car --dry-run était activé)"
fi
