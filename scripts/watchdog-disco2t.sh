#!/bin/bash
# watchdog-disco2t.sh — Watchdog para el disco de 2T (nvme1n1p1)
# Comprueba si está montado. Si no, intenta montarlo y envía alerta MQTT.
# Ejecutado por systemd cada 5 minutos.

MOUNT_POINT="/media/davidia/Disco de 2T"
UUID="1b3d439a-5ab6-46bb-a6b3-af91334f8617"
MQTT_BROKER="localhost"
MQTT_PORT="1883"
LOG="/var/log/watchdog-disco2t.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"
}

# Comprobar si está montado
if mountpoint -q "$MOUNT_POINT"; then
    # Montado — verificar que es escribible haciendo touch
    if touch "$MOUNT_POINT/.watchdog_ok" 2>/dev/null; then
        rm -f "$MOUNT_POINT/.watchdog_ok"
        exit 0
    else
        log "WARN: Disco 2T montado pero no escribible — posible error I/O"
        mosquitto_pub -h "$MQTT_BROKER" -p "$MQTT_PORT" -t "seedy/alerts/disco2t" \
            -m '{"status":"not_writable","mount":"'"$MOUNT_POINT"'"}' 2>/dev/null || true
        exit 1
    fi
fi

# No montado — intentar montar
log "WARN: Disco 2T no montado. Intentando montar UUID=$UUID..."
if mount UUID="$UUID" "$MOUNT_POINT" 2>>"$LOG"; then
    log "OK: Disco 2T montado correctamente en $MOUNT_POINT"
    mosquitto_pub -h "$MQTT_BROKER" -p "$MQTT_PORT" -t "seedy/alerts/disco2t" \
        -m '{"status":"remounted","mount":"'"$MOUNT_POINT"'"}' 2>/dev/null || true
    exit 0
else
    log "ERROR: No se pudo montar el disco 2T"
    mosquitto_pub -h "$MQTT_BROKER" -p "$MQTT_PORT" -t "seedy/alerts/disco2t" \
        -m '{"status":"mount_failed","mount":"'"$MOUNT_POINT"'"}' 2>/dev/null || true
    exit 2
fi
