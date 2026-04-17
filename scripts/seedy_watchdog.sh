#!/bin/bash
# ═══════════════════════════════════════════════════════
# Seedy Watchdog — Evita bloqueos de CPU/VRAM
# Se ejecuta cada 30s vía systemd timer
# ═══════════════════════════════════════════════════════

LOG="/tmp/seedy_watchdog.log"
MAX_CPU=300          # % total CPU (4 cores = 400% max)
MAX_CONTAINER_CPU=200  # % por contenedor
BACKEND="seedy-backend"

log() { echo "$(date '+%H:%M:%S') $1" >> "$LOG"; }

# ── 1. Limitar contenedores Docker que superen MAX_CONTAINER_CPU ──
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' 2>/dev/null | while read name cpu; do
    cpu_num=$(echo "$cpu" | tr -d '%' | cut -d. -f1)
    if [ "$cpu_num" -gt "$MAX_CONTAINER_CPU" ] 2>/dev/null; then
        log "WARN: $name at ${cpu} — limiting to 2 CPUs"
        docker update --cpus 2 "$name" >/dev/null 2>&1
    fi
done

# ── 2. Si el backend supera 250% CPU, reiniciarlo ──
backend_cpu=$(docker stats --no-stream --format '{{.CPUPerc}}' "$BACKEND" 2>/dev/null | tr -d '%' | cut -d. -f1)
if [ "${backend_cpu:-0}" -gt 250 ] 2>/dev/null; then
    log "CRITICAL: $BACKEND at ${backend_cpu}% — restarting"
    docker restart "$BACKEND" >/dev/null 2>&1
fi

# ── 3. Verificar VRAM — si >14GB usado, matar entrenamiento ──
vram_used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
if [ "${vram_used:-0}" -gt 14000 ] 2>/dev/null; then
    log "CRITICAL: VRAM ${vram_used}MB — killing training processes"
    # Kill YOLO training inside backend container
    docker exec "$BACKEND" python3 -c "
import os, signal
for p in os.listdir('/proc'):
    if not p.isdigit() or p == '1': continue
    try:
        cmd = open(f'/proc/{p}/cmdline').read()
        if 'train' in cmd.lower() and ('yolo' in cmd.lower() or 'ultralytics' in cmd.lower()):
            os.kill(int(p), signal.SIGTERM)
    except: pass
" 2>/dev/null
fi

# ── 4. Si carga del sistema > 10, log warning ──
load=$(cat /proc/loadavg | cut -d' ' -f1 | cut -d. -f1)
if [ "${load:-0}" -gt 10 ] 2>/dev/null; then
    log "WARN: System load ${load}"
fi

# ── 5. Mantener log pequeño (últimas 200 líneas) ──
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 200 ]; then
    tail -100 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
