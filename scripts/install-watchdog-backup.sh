#!/bin/bash
# install-watchdog-backup.sh — Instala watchdog disco 2T y backup Seedy como servicios systemd
# Ejecutar con: sudo bash scripts/install-watchdog-backup.sh

set -e
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== Instalando watchdog y backup Seedy ==="

# Permisos ejecutables
chmod +x "$SCRIPTS_DIR/watchdog-disco2t.sh"
chmod +x "$SCRIPTS_DIR/backup-seedy.sh"

# Copiar units
cp "$SCRIPTS_DIR/systemd/watchdog-disco2t.service" "$SYSTEMD_DIR/"
cp "$SCRIPTS_DIR/systemd/watchdog-disco2t.timer"   "$SYSTEMD_DIR/"
cp "$SCRIPTS_DIR/systemd/backup-seedy.service"     "$SYSTEMD_DIR/"
cp "$SCRIPTS_DIR/systemd/backup-seedy.timer"       "$SYSTEMD_DIR/"

# Crear directorio de montaje NAS
mkdir -p /mnt/nas_seedy

# Crear fichero de credenciales NAS si no existe
if [[ ! -f /home/davidia/.nas_credentials ]]; then
    echo "username=davidia" > /home/davidia/.nas_credentials
    echo "password="       >> /home/davidia/.nas_credentials
    chmod 600 /home/davidia/.nas_credentials
    echo "⚠️  Edita /home/davidia/.nas_credentials con la contraseña del NAS"
fi

# Recargar y activar
systemctl daemon-reload
systemctl enable --now watchdog-disco2t.timer
systemctl enable --now backup-seedy.timer

echo ""
echo "✅ Instalado:"
echo "   watchdog-disco2t.timer  → cada 5 min"
echo "   backup-seedy.timer      → cada 6h (disco 2T + NAS)"
echo ""
echo "Comandos útiles:"
echo "  systemctl status watchdog-disco2t.timer"
echo "  systemctl status backup-seedy.timer"
echo "  journalctl -u backup-seedy.service -f"
echo "  cat /var/log/backup-seedy.log"
