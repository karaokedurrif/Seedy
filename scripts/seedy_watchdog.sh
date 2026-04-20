#!/bin/bash
# ═══════════════════════════════════════════════════════
# Seedy Watchdog v2 — CPU + RAM + VRAM + spawn leak
# Crontab: * * * * * /home/davidia/Documentos/Seedy/scripts/seedy_watchdog.sh
# ═══════════════════════════════════════════════════════

LOG="/tmp/seedy_watchdog.log"
BACKEND="seedy-backend"

# Umbrales
MAX_BACKEND_CPU=250      # % CPU del contenedor para restart (4 CPUs = 400% max)
MAX_BACKEND_RAM_GB=6     # GB RAM del contenedor para restart (limit=8GB, uso normal ~3.5GB con YOLO)
MAX_SPAWN_CPU=80         # % CPU de un solo spawn para matarlo
MAX_SPAWN_RAM_GB=2       # GB RAM de un solo spawn para matarlo
MAX_SPAWN_AGE_MIN=15     # Minutos: spawn > esto + > 50% CPU = leaked
MAX_VRAM_MB=14000        # MB VRAM para matar training
MAX_LOAD=10              # Load average para warning

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

# ── 1. Matar spawns desbocados del backend (el bug recurrente) ──
ps aux | grep "multiprocessing.spawn" | grep -v grep | while read user pid cpu mem vsz rss rest; do
    rss_gb=$(awk "BEGIN {printf \"%.1f\", $rss / 1048576}")
    rss_gb_int=$(echo "$rss_gb" | cut -d. -f1)
    cpu_int=$(echo "$cpu" | cut -d. -f1)
    age_sec=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
    age_min=$(( ${age_sec:-0} / 60 ))

    kill_reason=""

    # RAM > 4GB → matar siempre
    if [ "${rss_gb_int:-0}" -ge "$MAX_SPAWN_RAM_GB" ] 2>/dev/null; then
        kill_reason="RAM=${rss_gb}GB>=${MAX_SPAWN_RAM_GB}GB"
    fi

    # CPU > 80% → matar siempre
    if [ "${cpu_int:-0}" -ge "$MAX_SPAWN_CPU" ] 2>/dev/null; then
        kill_reason="${kill_reason:+$kill_reason + }CPU=${cpu}%>=${MAX_SPAWN_CPU}%"
    fi

    # Viejo (>30min) + CPU > 50% = leaked process
    if [ "${age_min:-0}" -ge "$MAX_SPAWN_AGE_MIN" ] && [ "${cpu_int:-0}" -ge 50 ] 2>/dev/null; then
        kill_reason="${kill_reason:+$kill_reason + }LEAKED(age=${age_min}min,cpu=${cpu}%)"
    fi

    if [ -n "$kill_reason" ]; then
        log "KILL spawn PID=$pid: $kill_reason"
        kill -9 "$pid" 2>/dev/null
        if kill -0 "$pid" 2>/dev/null; then
            log "KILL failed (Docker ns) — restarting $BACKEND"
            docker restart "$BACKEND" >/dev/null 2>&1
            break
        fi
    fi
done

# ── 2. Monitorizar contenedor backend: CPU + RAM ──
backend_stats=$(docker stats --no-stream --format '{{.CPUPerc}} {{.MemUsage}}' "$BACKEND" 2>/dev/null)
if [ -n "$backend_stats" ]; then
    backend_cpu=$(echo "$backend_stats" | awk '{print $1}' | tr -d '%' | cut -d. -f1)
    backend_mem_raw=$(echo "$backend_stats" | grep -oP '[\d.]+[GM]iB' | head -1)
    backend_mem_unit=$(echo "$backend_mem_raw" | grep -oP '[GM]')
    backend_mem_num=$(echo "$backend_mem_raw" | grep -oP '[\d.]+')

    if [ "$backend_mem_unit" = "G" ]; then
        backend_mem_gb=$(echo "$backend_mem_num" | cut -d. -f1)
    else
        backend_mem_gb=0
    fi

    if [ "${backend_cpu:-0}" -gt "$MAX_BACKEND_CPU" ] 2>/dev/null; then
        log "CRITICAL: $BACKEND CPU=${backend_cpu}% — restarting"
        docker restart "$BACKEND" >/dev/null 2>&1
    fi

    if [ "${backend_mem_gb:-0}" -ge "$MAX_BACKEND_RAM_GB" ] 2>/dev/null; then
        log "CRITICAL: $BACKEND RAM=${backend_mem_raw} — restarting"
        docker restart "$BACKEND" >/dev/null 2>&1
    fi
fi

# ── 3. Limitar otros contenedores ──
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' 2>/dev/null | while read name cpu; do
    [ "$name" = "$BACKEND" ] && continue
    cpu_num=$(echo "$cpu" | tr -d '%' | cut -d. -f1)
    if [ "${cpu_num:-0}" -gt 150 ] 2>/dev/null; then
        log "WARN: $name at ${cpu} — limiting to 2 CPUs"
        docker update --cpus 2 "$name" >/dev/null 2>&1
    fi
done

# ── 4. VRAM — si >14GB, matar training ──
vram_used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
if [ "${vram_used:-0}" -gt "$MAX_VRAM_MB" ] 2>/dev/null; then
    log "CRITICAL: VRAM ${vram_used}MB — killing training"
    docker exec "$BACKEND" bash -c 'for p in /proc/[0-9]*/cmdline; do pid=$(echo $p|cut -d/ -f3);[ "$pid" = "1" ]&&continue;grep -qiE "train|ultralytics" "$p" 2>/dev/null&&kill -9 "$pid" 2>/dev/null;done' 2>/dev/null
fi

# ── 5. Matar tracker-extract si vuelve ──
pkill -f tracker-extract 2>/dev/null

# ── 6. Load average warning ──
load=$(cut -d' ' -f1 /proc/loadavg | cut -d. -f1)
if [ "${load:-0}" -gt "$MAX_LOAD" ] 2>/dev/null; then
    log "WARN: load=$(cut -d' ' -f1 /proc/loadavg)"
fi

# ── 7. Log rotation ──
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG" 2>/dev/null)" -gt 500 ]; then
    tail -200 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
