#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Seedy CPU Watchdog — Protege el host de bloqueos por Docker
# Ejecutar como: systemctl --user start seedy-watchdog
# O manualmente: ./scripts/seedy-watchdog.sh &
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuración ──
CPU_WARN=300        # % CPU total (3 cores) antes de avisar
CPU_KILL=500        # % CPU total (5 cores) antes de actuar
CHECK_INTERVAL=30   # Segundos entre checks
CONTAINERS="seedy-backend go2rtc"
MAX_CPU_BACKEND=4   # Límite máximo CPUs para seedy-backend
MAX_CPU_GO2RTC=2    # Límite máximo CPUs para go2rtc
MAX_MEM_BACKEND="8g"
MAX_MEM_GO2RTC="2g"
LOG_FILE="/tmp/seedy-watchdog.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

get_container_cpu() {
    local name="$1"
    docker stats --no-stream --format "{{.CPUPerc}}" "$name" 2>/dev/null | tr -d '%' || echo "0"
}

get_total_docker_cpu() {
    docker stats --no-stream --format "{{.CPUPerc}}" 2>/dev/null | tr -d '%' | awk '{s+=$1} END {printf "%.0f", s}'
}

throttle_container() {
    local name="$1"
    local max_cpu="$2"
    local max_mem="$3"
    local current_cpu
    current_cpu=$(get_container_cpu "$name")
    
    if (( $(echo "$current_cpu > $CPU_WARN" | bc -l 2>/dev/null || echo 0) )); then
        log "⚠️  $name usa ${current_cpu}% CPU — throttling a ${max_cpu} CPUs"
        docker update --cpus "$max_cpu" --memory "$max_mem" --memory-swap "$((${max_mem%g} + 2))g" "$name" 2>/dev/null
    fi
}

kill_training() {
    # Matar procesos de entrenamiento YOLO dentro del backend
    docker exec seedy-backend python3 -c "
import os, signal
for pid_dir in os.listdir('/proc'):
    if not pid_dir.isdigit() or pid_dir == '1':
        continue
    try:
        with open(f'/proc/{pid_dir}/cmdline', 'r') as f:
            cmdline = f.read()
        if 'ultralytics' in cmdline or '/train' in cmdline:
            os.kill(int(pid_dir), signal.SIGTERM)
            print(f'Killed training PID {pid_dir}')
    except:
        pass
" 2>/dev/null || true
}

# ── Aplicar límites al arranque ──
log "🐕 Seedy Watchdog iniciado (warn=${CPU_WARN}%, kill=${CPU_KILL}%, interval=${CHECK_INTERVAL}s)"

for c in $CONTAINERS; do
    if docker inspect "$c" &>/dev/null; then
        case "$c" in
            seedy-backend)
                docker update --cpus "$MAX_CPU_BACKEND" --memory "$MAX_MEM_BACKEND" --memory-swap "10g" "$c" 2>/dev/null && \
                    log "✅ $c: límite ${MAX_CPU_BACKEND} CPUs, ${MAX_MEM_BACKEND} RAM"
                ;;
            go2rtc)
                docker update --cpus "$MAX_CPU_GO2RTC" --memory "$MAX_MEM_GO2RTC" --memory-swap "3g" "$c" 2>/dev/null && \
                    log "✅ $c: límite ${MAX_CPU_GO2RTC} CPUs, ${MAX_MEM_GO2RTC} RAM"
                ;;
        esac
    fi
done

# ── Loop principal ──
consecutive_high=0

while true; do
    sleep "$CHECK_INTERVAL"
    
    total_cpu=$(get_total_docker_cpu)
    
    if (( total_cpu > CPU_KILL )); then
        consecutive_high=$((consecutive_high + 1))
        log "🔴 Docker CPU total: ${total_cpu}% (>$CPU_KILL%) — alerta $consecutive_high/3"
        
        if (( consecutive_high >= 3 )); then
            log "🛑 CPU crítica sostenida — matando entrenamientos y throttling"
            kill_training
            throttle_container "seedy-backend" "$MAX_CPU_BACKEND" "$MAX_MEM_BACKEND"
            throttle_container "go2rtc" "$MAX_CPU_GO2RTC" "$MAX_MEM_GO2RTC"
            consecutive_high=0
        fi
    elif (( total_cpu > CPU_WARN )); then
        consecutive_high=0
        log "⚠️  Docker CPU total: ${total_cpu}% (>$CPU_WARN%) — monitorizando"
        # Throttle individual containers
        throttle_container "seedy-backend" "$MAX_CPU_BACKEND" "$MAX_MEM_BACKEND"
    else
        consecutive_high=0
    fi
done
