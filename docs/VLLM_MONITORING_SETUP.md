# vLLM Monitoring Setup v4.7

## 📊 Overview

Sistema de monitorización completo para vLLM Qwen2.5-Coder-32B en producción. Incluye health checks automáticos, dashboards Grafana, y alerting.

---

## 🔧 Componentes

### 1. Health Check Script

**Ubicación:** `~/seedy/scripts/monitor-vllm-health.sh`

**Verifica:**
- ✅ Health endpoint (`/health`)
- ✅ Container Docker status
- ✅ GPU memory usage
- ✅ Inference test simple (2+2)

**Uso:**
```bash
# Manual
~/seedy/scripts/monitor-vllm-health.sh

# Con alerting (Slack/Discord webhook)
~/seedy/scripts/monitor-vllm-health.sh https://hooks.slack.com/...
```

**Output:**
```
[2026-05-05 19:00:00] 🔍 Checking vLLM health...
✅ Health endpoint: OK
✅ Container: running
✅ GPU Memory: 49GB / 128GB (38%)
🧪 Testing inference (2+2)...
✅ Inference: OK (3s) — Response: 4
[2026-05-05 19:00:03] ✅ All checks passed
```

---

### 2. Systemd Services (opcional)

**Health Check Periódico:**
```bash
# Instalar (requiere sudo)
sudo cp /tmp/vllm-healthcheck.service /etc/systemd/system/
sudo cp /tmp/vllm-healthcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vllm-healthcheck.timer

# Verificar
sudo systemctl status vllm-healthcheck.timer
journalctl -u vllm-healthcheck.service -f
```

**Frecuencia:** Cada 10 minutos

---

### 3. Métricas a InfluxDB (opcional)

**Ubicación:** `~/seedy/scripts/vllm-metrics-exporter.py`

**Exports:**
- GPU memory usage (MB, %)
- Container CPU/memory
- Health check status

**Setup:**
```bash
# Configurar token InfluxDB
export INFLUXDB_TOKEN="your-token"

# Test manual
python3 ~/seedy/scripts/vllm-metrics-exporter.py

# Automatizar con cron (cada 30s)
echo "* * * * * /usr/bin/python3 ~/seedy/scripts/vllm-metrics-exporter.py" | crontab -
echo "* * * * * sleep 30; /usr/bin/python3 ~/seedy/scripts/vllm-metrics-exporter.py" | crontab -
```

---

### 4. Dashboard Grafana

**Archivo:** `docs/grafana-vllm-v4.7.json`

**Paneles:**
1. 🚀 **Request Rate** — Requests/min
2. ⏱️ **Inference Latency** — P50/P95/P99
3. 💾 **GPU Memory** — Ollama + vLLM coexistence
4. 💰 **Cost Comparison** — vLLM vs Together.ai savings
5. 🎯 **Provider Distribution** — vLLM vs Ollama vs Together
6. 📊 **Task Type Breakdown** — CHAT/REFACTOR/DEBUG
7. ❌ **Error Rate** — Errors/hour
8. 🔥 **Container Health** — Docker stats table

**Importar:**
```bash
# Desde DGX
curl -X POST http://localhost:3001/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <grafana-api-key>" \
  -d @~/seedy/docs/grafana-vllm-v4.7.json
```

---

## 📈 Métricas Clave

### GPU Memory Coexistence

| Servicio | Memoria | % Total |
|----------|---------|---------|
| Ollama | 31 GB | 24% |
| vLLM | 18 GB | 14% |
| **Total** | **49 GB** | **38%** |
| Disponible | 79 GB | 62% |

**Thresholds:**
- ⚠️ Warning: 100GB (78%)
- 🚨 Critical: 115GB (90%)

### Latency SLOs

| Operation | P50 | P95 | P99 |
|-----------|-----|-----|-----|
| First Inference | 30-50s | 60s | 90s |
| Subsequent | 3-8s | 15s | 30s |
| Health Check | <1s | 2s | 5s |

**torch.compile:** Primera inferencia tarda 10-20× más (CUDA graph compilation). Normal.

### Cost Comparison

| Provider | Input | Output | Savings |
|----------|-------|--------|---------|
| vLLM Local | $0.00 | $0.00 | 100% |
| Together.ai (DeepSeek-Coder) | $0.50 | $1.50 | — |

**Ahorro mensual estimado:** $50/mes (Continue.dev) + $10/mes (Coder Router) = **$60/mes**

---

## 🚨 Alerting

### Condiciones de Alerta

1. **Health Check Fail** (3 intentos consecutivos)
   - Container stopped
   - GPU OOM
   - Inference test timeout

2. **High GPU Memory** (>90% por 5 min)
   - Risk de OOM
   - Considerar reload o reducir `--gpu-memory-utilization`

3. **High Error Rate** (>10 errors/hour)
   - Check logs: `docker logs coder-vllm`
   - Posible modelo corrupto o GPU issue

4. **Latency Spike** (P95 >60s por 10 min)
   - Check GPU utilization: `nvidia-smi dmon`
   - Posible contention con Ollama

### Webhook Setup (Slack/Discord)

```bash
# Slack
WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/HERE"

# Discord
WEBHOOK="https://discord.com/api/webhooks/YOUR/WEBHOOK"

# Test
curl -X POST $WEBHOOK -d '{"text":"vLLM test alert"}'
```

---

## 📝 Logs

### Docker Logs
```bash
# Real-time
docker logs -f coder-vllm

# Filtrar errores
docker logs coder-vllm 2>&1 | grep -i "error\|warning"

# Últimas 100 líneas
docker logs --tail=100 coder-vllm
```

### Health Check Logs
```bash
tail -f /tmp/vllm_health.log
```

### Journal (systemd)
```bash
journalctl -u vllm-healthcheck.service -f
```

---

## 🔍 Troubleshooting

### Container Not Starting

```bash
# Check logs
docker logs coder-vllm

# Common issues:
# 1. Model files missing
ls -lh ~/models/qwen2.5-coder-32b-awq/

# 2. GPU not available
nvidia-smi

# 3. Port conflict
sudo lsof -i :8001

# 4. Memory issue
docker stats --no-stream
```

### High Latency

```bash
# Check GPU utilization
nvidia-smi dmon -s mu -c 10

# Check Ollama contention
docker exec ollama curl -s localhost:11434/api/ps

# Check concurrent requests
docker stats coder-vllm --no-stream
```

### GPU OOM

```bash
# Current usage
nvidia-smi

# Solutions:
# 1. Reduce vLLM memory
docker compose down
# Edit docker-compose.yml: --gpu-memory-utilization 0.50
docker compose up -d

# 2. Unload Ollama models
docker exec ollama curl -X DELETE localhost:11434/api/generate -d '{"model":"qwen2.5:72b-instruct-q4_K_M","keep_alive":0}'
```

### Inference Errors

```bash
# Test endpoint
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4" \
  -d '{
    "model": "qwen2.5-coder-32b",
    "messages": [{"role": "user", "content": "test"}],
    "max_tokens": 10
  }'

# Check vLLM process
docker exec coder-vllm ps aux | grep python

# Restart
docker restart coder-vllm
```

---

## ✅ Daily Checks

```bash
# Morning routine (5 min)
cd ~/seedy

# 1. Health check
./scripts/monitor-vllm-health.sh

# 2. GPU memory
nvidia-smi

# 3. Container status
docker compose ps | grep -E 'vllm|ollama'

# 4. Recent errors
docker logs --since=24h coder-vllm 2>&1 | grep -i error | wc -l

# 5. Disk space (model files)
df -h ~/models/
```

---

## 📊 Performance Baselines

### First Deployment (5 mayo 2026)

| Métrica | Valor |
|---------|-------|
| Cold Start | 140s |
| First Inference | 46s (79 tokens) |
| GPU Memory (vLLM) | 18.14 GB |
| GPU Memory (Total) | 49 GB / 128 GB (38%) |
| Model Size | 22 GB |
| Docker Image | vllm/vllm-openai:latest |
| vLLM Version | v0.20.1 |

---

## 🔗 Enlaces

- [vLLM Docs](https://docs.vllm.ai/)
- [Grafana Dashboard JSON](./grafana-vllm-v4.7.json)
- [Architecture Docs](./vllm-coder-v4.7.md)
- [Success Report](./V4.7_SUCCESS_REPORT.md)

---

**Última actualización:** 5 mayo 2026  
**Responsable:** daviddgx  
**Entorno:** DGX Spark GB10 (192.168.20.57)
