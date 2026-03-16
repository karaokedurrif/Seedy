#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# Seedy AI — Healthcheck & Alertas
# Verifica todos los servicios críticos del stack
# Cron recomendado: */5 * * * * /ruta/scripts/healthcheck.sh
# ─────────────────────────────────────────────────────
set -euo pipefail

# ── Config ───────────────────────────────────────────
SEEDY_DIR="${SEEDY_DIR:-/home/davidia/Documentos/Seedy}"
LOG_DIR="${SEEDY_DIR}/logs"
LOG_FILE="${LOG_DIR}/healthcheck.log"
ALERT_LOG="${LOG_DIR}/healthcheck_alerts.log"

# Telegram (descomenta y rellena para activar alertas)
# TELEGRAM_BOT_TOKEN="tu-bot-token"
# TELEGRAM_CHAT_ID="tu-chat-id"

# Servicios y sus endpoints
declare -A SERVICES=(
  ["ollama"]="http://localhost:11434/api/tags"
  ["qdrant"]="http://localhost:6333/healthz"
  ["open-webui"]="http://localhost:3000"
  ["seedy-backend"]="http://localhost:8000/health"
  ["influxdb"]="http://localhost:8086/health"
  ["grafana"]="http://localhost:3001/api/health"
  ["nodered"]="http://localhost:1880"
)

# ── Funciones ────────────────────────────────────────
mkdir -p "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  echo "[$(timestamp)] $1" | tee -a "$LOG_FILE"
}

log_alert() {
  echo "[$(timestamp)] ALERT: $1" | tee -a "$LOG_FILE" >> "$ALERT_LOG"
}

send_telegram() {
  local msg="$1"
  if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
    curl -s -X POST \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d chat_id="${TELEGRAM_CHAT_ID}" \
      -d text="🚨 Seedy Healthcheck Alert
${msg}" \
      -d parse_mode="Markdown" \
      > /dev/null 2>&1 || true
  fi
}

# ── Check: Docker containers ────────────────────────
check_containers() {
  local failed=0
  local down_list=""

  log "── Verificando containers Docker ──"

  local containers=(ollama open-webui qdrant seedy-backend influxdb mosquitto nodered grafana)
  for ctr in "${containers[@]}"; do
    local status
    status=$(docker inspect -f '{{.State.Status}}' "$ctr" 2>/dev/null || echo "not_found")
    if [[ "$status" != "running" ]]; then
      log_alert "Container '$ctr' no está running (status: $status)"
      down_list+="  - $ctr ($status)\n"
      ((failed++))
    fi
  done

  if [[ $failed -gt 0 ]]; then
    send_telegram "❌ *$failed container(s) caídos:*
$(echo -e "$down_list")"
  else
    log "  ✅ Todos los containers running"
  fi

  return $failed
}

# ── Check: HTTP endpoints ────────────────────────────
check_endpoints() {
  local failed=0
  local down_list=""

  log "── Verificando endpoints HTTP ──"

  for svc in "${!SERVICES[@]}"; do
    local url="${SERVICES[$svc]}"
    local http_code
    http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null || echo "000")

    if [[ "$http_code" =~ ^(200|204|301|302)$ ]]; then
      log "  ✅ $svc → $http_code"
    else
      log_alert "Endpoint '$svc' ($url) → HTTP $http_code"
      down_list+="  - $svc → $http_code\n"
      ((failed++))
    fi
  done

  if [[ $failed -gt 0 ]]; then
    send_telegram "❌ *$failed endpoint(s) no responden:*
$(echo -e "$down_list")"
  fi

  return $failed
}

# ── Check: Mosquitto (MQTT) ──────────────────────────
check_mqtt() {
  log "── Verificando MQTT (Mosquitto) ──"

  if command -v mosquitto_pub &>/dev/null; then
    if mosquitto_pub -h localhost -p 1883 -t "seedy/healthcheck" \
       -m "ping $(timestamp)" -q 0 2>/dev/null; then
      log "  ✅ MQTT publicación OK"
      return 0
    else
      log_alert "MQTT publish falló en localhost:1883"
      send_telegram "❌ *MQTT* no acepta publicaciones"
      return 1
    fi
  else
    # Fallback: verificar puerto TCP
    if timeout 5 bash -c "echo > /dev/tcp/localhost/1883" 2>/dev/null; then
      log "  ✅ MQTT puerto 1883 abierto"
      return 0
    else
      log_alert "MQTT puerto 1883 no accesible"
      send_telegram "❌ *MQTT* puerto 1883 cerrado"
      return 1
    fi
  fi
}

# ── Check: Ollama model loaded ───────────────────────
check_ollama_model() {
  log "── Verificando modelo Ollama ──"

  local models
  models=$(curl -s --max-time 10 http://localhost:11434/api/tags 2>/dev/null || echo "{}")
  
  if echo "$models" | grep -q "seedy"; then
    log "  ✅ Modelo seedy disponible en Ollama"
    return 0
  else
    log_alert "Modelo 'seedy' no encontrado en Ollama"
    send_telegram "⚠️ *Modelo seedy* no disponible en Ollama"
    return 1
  fi
}

# ── Check: Qdrant collections ───────────────────────
check_qdrant_collections() {
  log "── Verificando colecciones Qdrant ──"

  local collections
  collections=$(curl -s --max-time 10 http://localhost:6333/collections 2>/dev/null || echo "{}")
  
  local count
  count=$(echo "$collections" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cols = data.get('result', {}).get('collections', [])
    print(len(cols))
except:
    print(0)
" 2>/dev/null || echo "0")

  if [[ "$count" -ge 7 ]]; then
    log "  ✅ Qdrant: $count colecciones activas"
    return 0
  elif [[ "$count" -gt 0 ]]; then
    log "  ⚠️  Qdrant: solo $count colecciones (esperadas ≥7)"
    return 0
  else
    log_alert "Qdrant: 0 colecciones encontradas"
    send_telegram "❌ *Qdrant* sin colecciones"
    return 1
  fi
}

# ── Check: Disk space ───────────────────────────────
check_disk() {
  log "── Verificando espacio en disco ──"

  local usage
  usage=$(df / | tail -1 | awk '{print $5}' | tr -d '%')

  if [[ "$usage" -lt 80 ]]; then
    log "  ✅ Disco: ${usage}% utilizado"
    return 0
  elif [[ "$usage" -lt 90 ]]; then
    log "  ⚠️  Disco: ${usage}% utilizado (alerta amarilla)"
    send_telegram "⚠️ *Disco* al ${usage}% — limpiar pronto"
    return 0
  else
    log_alert "Disco al ${usage}% — CRÍTICO"
    send_telegram "🔴 *DISCO CRÍTICO* al ${usage}%"
    return 1
  fi
}

# ── Check: GPU status ───────────────────────────────
check_gpu() {
  log "── Verificando GPU ──"

  if command -v nvidia-smi &>/dev/null; then
    local gpu_info
    gpu_info=$(nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total \
               --format=csv,noheader,nounits 2>/dev/null || echo "error")

    if [[ "$gpu_info" != "error" ]]; then
      local temp
      temp=$(echo "$gpu_info" | awk -F', ' '{print $2}')
      local mem_used
      mem_used=$(echo "$gpu_info" | awk -F', ' '{print $4}')
      local mem_total
      mem_total=$(echo "$gpu_info" | awk -F', ' '{print $5}')

      log "  ✅ GPU: ${gpu_info}"

      if [[ "$temp" -gt 85 ]]; then
        log_alert "GPU temperatura alta: ${temp}°C"
        send_telegram "🌡️ *GPU* temperatura ${temp}°C — riesgo thermal throttle"
        return 1
      fi
      return 0
    else
      log_alert "nvidia-smi falló"
      return 1
    fi
  else
    log "  ⏭️  nvidia-smi no disponible (NAS/servidor sin GPU)"
    return 0
  fi
}

# ── Check: RAM ───────────────────────────────────────
check_ram() {
  log "── Verificando RAM ──"

  local total used pct
  read -r total used <<< $(free -m | awk '/^Mem:/ {print $2, $3}')
  pct=$((used * 100 / total))

  if [[ "$pct" -lt 85 ]]; then
    log "  ✅ RAM: ${used}MB / ${total}MB (${pct}%)"
    return 0
  else
    log_alert "RAM al ${pct}%: ${used}MB / ${total}MB"
    send_telegram "⚠️ *RAM* al ${pct}% (${used}/${total} MB)"
    return 1
  fi
}

# ── Main ─────────────────────────────────────────────
main() {
  log "════════════════════════════════════════════"
  log "  SEEDY HEALTHCHECK — Inicio"
  log "════════════════════════════════════════════"

  local total_errors=0

  # Checks del sistema
  check_disk    || ((total_errors++))
  check_ram     || ((total_errors++))
  check_gpu     || ((total_errors++))

  # Checks Docker
  check_containers || ((total_errors++))

  # Checks servicios
  check_endpoints         || ((total_errors++))
  check_mqtt              || ((total_errors++))
  check_ollama_model      || ((total_errors++))
  check_qdrant_collections || ((total_errors++))

  log "────────────────────────────────────────────"
  if [[ $total_errors -eq 0 ]]; then
    log "✅ HEALTHCHECK OK — Todo operativo"
  else
    log "❌ HEALTHCHECK: $total_errors grupo(s) con errores"
    send_telegram "📊 *Resumen healthcheck:* $total_errors grupo(s) con problemas"
  fi
  log "════════════════════════════════════════════"

  # Rotación de log (mantener últimas 5000 líneas)
  if [[ -f "$LOG_FILE" ]]; then
    local lines
    lines=$(wc -l < "$LOG_FILE")
    if [[ $lines -gt 5000 ]]; then
      tail -n 3000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
  fi

  return $total_errors
}

main "$@"
