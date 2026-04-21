#!/bin/bash
# backup-seedy.sh — Backup rsync de Seedy a disco 2T y NAS OMV
# Ejecutado por systemd timer cada 6h.

SEEDY_SRC="/home/davidia/Documentos/Seedy/"
DISCO2T_DST="/media/davidia/Disco de 2T/proyectos/Seedy/"
NAS_DST="//192.168.30.100/datos/Seedy/"
NAS_MOUNT="/mnt/nas_seedy"
NAS_USER="davidia"
NAS_CREDENTIALS="/home/davidia/.nas_credentials"
LOG="/var/log/backup-seedy.log"
MQTT_BROKER="localhost"

EXCLUDES=(
    '--exclude=.git'
    '--exclude=__pycache__'
    '--exclude=.venv'
    '--exclude=.venv-1'
    '--exclude=hf_datasets/'
    '--exclude=data/tiles'
    '--exclude=data/dem'
    '--exclude=data/raw'
)

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
mqtt() { mosquitto_pub -h "$MQTT_BROKER" -t "seedy/backup/status" -m "$1" 2>/dev/null || true; }

# ── Backup disco 2T ──────────────────────────────────────────────────────────
if mountpoint -q "/media/davidia/Disco de 2T"; then
    log "INFO: Iniciando rsync → disco 2T"
    if rsync -av --delete "${EXCLUDES[@]}" "$SEEDY_SRC" "$DISCO2T_DST" >> "$LOG" 2>&1; then
        log "OK: Backup disco 2T completado"
        mqtt '{"target":"disco2t","status":"ok"}'
    else
        log "ERROR: Backup disco 2T falló (exit $?)"
        mqtt '{"target":"disco2t","status":"error"}'
    fi
else
    log "WARN: Disco 2T no montado, saltando backup local"
    mqtt '{"target":"disco2t","status":"not_mounted"}'
fi

# ── Backup NAS OMV ───────────────────────────────────────────────────────────
mkdir -p "$NAS_MOUNT"

# Montar NAS si no está montado
if ! mountpoint -q "$NAS_MOUNT"; then
    log "INFO: Montando NAS $NAS_DST → $NAS_MOUNT"
    if [[ -f "$NAS_CREDENTIALS" ]]; then
        mount -t cifs "$NAS_DST" "$NAS_MOUNT" \
            -o "credentials=$NAS_CREDENTIALS,uid=davidia,gid=davidia,vers=3.0,nofail" >> "$LOG" 2>&1
    else
        mount -t cifs "$NAS_DST" "$NAS_MOUNT" \
            -o "guest,uid=davidia,gid=davidia,vers=3.0,nofail" >> "$LOG" 2>&1
    fi
fi

if mountpoint -q "$NAS_MOUNT"; then
    log "INFO: Iniciando rsync → NAS OMV"
    if rsync -av --delete "${EXCLUDES[@]}" "$SEEDY_SRC" "$NAS_MOUNT/" >> "$LOG" 2>&1; then
        log "OK: Backup NAS completado"
        mqtt '{"target":"nas","status":"ok"}'
    else
        log "ERROR: Backup NAS falló (exit $?)"
        mqtt '{"target":"nas","status":"error"}'
    fi
    # Desmontar NAS tras el backup
    umount "$NAS_MOUNT" 2>/dev/null || true
else
    log "WARN: NAS no accesible, saltando backup NAS"
    mqtt '{"target":"nas","status":"not_reachable"}'
fi

log "INFO: Ciclo de backup completado"
