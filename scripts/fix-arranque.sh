#!/bin/bash
# fix-arranque.sh — Repara watchdog disco 2T y montaje NAS tras update Ubuntu
# Ejecutar con: sudo bash scripts/fix-arranque.sh
# Fecha: 26 abril 2026

set -e
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }
h()    { echo -e "\n${BOLD}$*${NC}"; }

if [[ $EUID -ne 0 ]]; then
    err "Ejecuta con sudo: sudo bash scripts/fix-arranque.sh"
    exit 1
fi

# ── 1. FSTAB — descomentar disco 2T ─────────────────────────────────────────
h "1. Reparando fstab (disco 2T)"

FSTAB=/etc/fstab
UUID_DISCO2T="1b3d439a-5ab6-46bb-a6b3-af91334f8617"
MOUNT_DISCO2T="/media/davidia/Disco de 2T"

# Backup fstab
cp "$FSTAB" "${FSTAB}.bak-$(date +%Y%m%d-%H%M%S)"
ok "Backup fstab creado"

# Verificar si la línea está comentada
if grep -q "^#UUID=${UUID_DISCO2T}" "$FSTAB"; then
    # Descomentar y simplificar opciones (quitar x-systemd.automount que retrasa el montaje)
    sed -i "s|^#UUID=${UUID_DISCO2T}.*|UUID=${UUID_DISCO2T} /media/davidia/Disco\\\\ de\\\\ 2T ext4 defaults,nofail,noatime 0 2|" "$FSTAB"
    ok "Línea disco 2T descomentada en fstab"
elif grep -q "^UUID=${UUID_DISCO2T}" "$FSTAB"; then
    ok "Disco 2T ya activo en fstab"
else
    # Añadir la línea si no existe
    echo "UUID=${UUID_DISCO2T} /media/davidia/Disco\\ de\\ 2T ext4 defaults,nofail,noatime 0 2" >> "$FSTAB"
    warn "Línea disco 2T añadida al fstab"
fi

# Asegurar que el mountpoint existe
mkdir -p "/media/davidia/Disco de 2T"
chown davidia:davidia "/media/davidia/Disco de 2T" 2>/dev/null || true

# Recargar units systemd generadas por fstab
systemctl daemon-reload

# Montar si no está ya montado
if ! mountpoint -q "/media/davidia/Disco de 2T"; then
    mount "/media/davidia/Disco de 2T" && ok "Disco 2T montado ahora" || warn "No se pudo montar (puede que udisks2 lo tenga cogido — OK)"
else
    ok "Disco 2T ya estaba montado"
fi

# ── 2. WATCHDOG SERVICE — añadir condición de seguridad ─────────────────────
h "2. Actualizando watchdog-disco2t.service"

SERVICE_FILE=/etc/systemd/system/watchdog-disco2t.service
SOURCE_SERVICE="$(dirname "$0")/systemd/watchdog-disco2t.service"

# Actualizar con ConditionPathIsDirectory para no fallar si el mountpoint no existe aún
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=Watchdog disco 2T (nvme1n1p1)
After=local-fs.target network.target
# Si el disco no está montado, el watchdog intentará montarlo (no abortar)
# ConditionPathIsMountPoint omitido intencionalmente para que el script actúe

[Service]
Type=oneshot
ExecStart=/home/davidia/Documentos/Seedy/scripts/watchdog-disco2t.sh
User=root
StandardOutput=journal
StandardError=journal
# No marcar como fallido si el disco no está disponible temporalmente
SuccessExitStatus=0 2

[Install]
WantedBy=multi-user.target
EOF

# También actualizar la copia del repo
cp "$SERVICE_FILE" "$(dirname "$0")/systemd/watchdog-disco2t.service" 2>/dev/null || true
ok "Service actualizado (SuccessExitStatus=0 2 — exit 2 = disco no montable, no crítico)"

# ── 3. WATCHDOG TIMER — aumentar OnBootSec a 3min ───────────────────────────
h "3. Ajustando timer (OnBootSec: 2min → 3min)"

TIMER_FILE=/etc/systemd/system/watchdog-disco2t.timer

cat > "$TIMER_FILE" << 'EOF'
[Unit]
Description=Watchdog disco 2T — timer cada 5 minutos

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF

cp "$TIMER_FILE" "$(dirname "$0")/systemd/watchdog-disco2t.timer" 2>/dev/null || true
ok "Timer actualizado (3min tras arranque para que udisks2 pueda montar antes)"

# ── 4. NAS — credenciales y mountpoint ──────────────────────────────────────
h "4. Preparando NAS OMV (192.168.30.100)"

mkdir -p /mnt/nas_seedy
ok "Directorio /mnt/nas_seedy listo"

if [[ ! -f /home/davidia/.nas_credentials ]]; then
    printf "username=davidia\npassword=\n" > /home/davidia/.nas_credentials
    chmod 600 /home/davidia/.nas_credentials
    chown davidia:davidia /home/davidia/.nas_credentials
    warn ".nas_credentials creado con password vacío (guest). Si el NAS tiene password edítalo: nano /home/davidia/.nas_credentials"
else
    ok ".nas_credentials ya existe"
fi

# Intentar montar NAS ahora
if mountpoint -q /mnt/nas_seedy; then
    ok "NAS ya montado en /mnt/nas_seedy"
else
    if ping -c 1 -W 2 192.168.30.100 &>/dev/null; then
        if mount -t cifs //192.168.30.100/datos /mnt/nas_seedy \
            -o "credentials=/home/davidia/.nas_credentials,uid=davidia,gid=davidia,vers=3.0,nofail" 2>/tmp/nas_mount_err; then
            ok "NAS montado en /mnt/nas_seedy"
            df -h /mnt/nas_seedy
        else
            # Intentar sin credenciales (guest anónimo)
            if mount -t cifs //192.168.30.100/datos /mnt/nas_seedy \
                -o "guest,uid=davidia,gid=davidia,vers=3.0,nofail" 2>>/tmp/nas_mount_err; then
                ok "NAS montado como guest en /mnt/nas_seedy"
                df -h /mnt/nas_seedy
            else
                err "No se pudo montar el NAS. Error: $(cat /tmp/nas_mount_err)"
                warn "El NAS puede requerir contraseña. Edita: /home/davidia/.nas_credentials"
            fi
        fi
    else
        warn "NAS no alcanzable en red ahora. Se montará cuando esté disponible."
    fi
fi

# ── 5. REINICIAR SERVICIOS ───────────────────────────────────────────────────
h "5. Recargando systemd y reseteando estado fallido"

systemctl daemon-reload

# Resetear estado failed del watchdog
systemctl reset-failed watchdog-disco2t.service 2>/dev/null || true

# Asegurar timer activo
systemctl enable --now watchdog-disco2t.timer
ok "watchdog-disco2t.timer activo"

# Verificar estado
echo ""
systemctl status watchdog-disco2t.timer --no-pager -l
echo ""
systemctl status watchdog-disco2t.service --no-pager -l 2>/dev/null | head -15

# ── 6. RESUMEN ───────────────────────────────────────────────────────────────
h "=== RESUMEN ==="
echo ""
echo "Disco 2T:"
df -h "/media/davidia/Disco de 2T" 2>/dev/null && ok "Montado OK" || warn "No montado (se intentará en próximo reinicio via fstab)"
echo ""
echo "NAS:"
mountpoint -q /mnt/nas_seedy && df -h /mnt/nas_seedy && ok "Montado OK" || warn "No montado (backup rsync fallará hasta que esté disponible)"
echo ""
echo "Watchdog:"
systemctl is-active watchdog-disco2t.timer && ok "Timer activo" || err "Timer inactivo"
echo ""
ok "Reparación completada. En el próximo arranque el disco 2T se montará vía fstab (nofail)"
echo ""
echo "  Verifica fstab: cat /etc/fstab"
echo "  Logs watchdog:  journalctl -u watchdog-disco2t.service -n 20"
echo "  Logs backup:    cat /var/log/backup-seedy.log"
