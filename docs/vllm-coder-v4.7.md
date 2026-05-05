# Seedy v4.7 — vLLM + Qwen2.5-Coder-32B-AWQ

**Fecha:** 5 mayo 2026  
**Objetivo:** Motor de coding agéntico con concurrencia real (hasta 8 sesiones simultáneas)  
**Hardware:** DGX Spark GB10 (NVIDIA 580.142, 128 GB RAM unificada)

---

## 🎯 Arquitectura Dual-Engine

```
DGX Spark (192.168.20.57)
│
├─ Ollama :11434  [Pipeline Seedy v4.6]
│  ├─ qwen2.5:7b (rewriter, classifiers, evidence)
│  ├─ seedy:v16 (critic gate, /local)
│  ├─ qwen2.5:72b (/deep, behavior 7D async)
│  └─ mxbai-embed-large (RAG embeddings)
│
└─ vLLM :8001  [NUEVO - Coding agéntico]
   └─ Qwen2.5-Coder-32B-Instruct-AWQ
       ├─ Continue.dev (VS Code/Cursor)
       ├─ OpenClaw (mini-PC SOC monitoring)
       ├─ Seedy Coder Router v4.3
       └─ Agentes futuros (CrewAI, AutoGen)
```

---

## 📊 Especificaciones Técnicas

| Parámetro | Valor | Notas |
|-----------|-------|-------|
| **Modelo** | Qwen2.5-Coder-32B-Instruct-AWQ | HumanEval 89.8, SWE-bench 35.2 |
| **Quantización** | AWQ-Int4 (Marlin kernel) | ~22 GB VRAM, 15-22 tok/s |
| **Context length** | 32768 tokens | Suficiente para archivos grandes |
| **Concurrencia** | Hasta 8 sesiones | PagedAttention + continuous batching |
| **GPU utilization** | 85% | Deja 18 GB para Ollama |
| **Puerto** | 8001 | Expuesto externamente |
| **API** | OpenAI-compatible `/v1/*` | Drop-in replacement |

---

## 🚀 Instalación

### Requisitos previos

- ✅ Driver NVIDIA 580+ (actual: 580.142)
- ✅ Docker runtime nvidia
- ✅ 30 GB espacio disco libre
- ✅ git-lfs instalado

### Descarga del modelo

```bash
cd ~/models
git clone https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct-AWQ qwen2.5-coder-32b-awq
# Tamaño: ~22 GB, tarda 10-20 min
```

### Docker Compose

Archivo: `~/seedy/coder-vllm/docker-compose.yml` (ya creado)

```yaml
services:
  vllm-coder:
    image: hellohal2064/vllm-dgx-spark-gb10:latest
    container_name: vllm-coder
    restart: unless-stopped
    runtime: nvidia
    privileged: true
    shm_size: 4g
    ports:
      - "8001:8000"
    volumes:
      - /home/daviddgx/models:/models:ro
      - vllm-cache:/root/.cache
    environment:
      - VLLM_API_KEY=${VLLM_API_KEY}
    command:
      - --model /models/qwen2.5-coder-32b-awq
      - --quantization awq_marlin
      - --max-model-len 32768
      - --gpu-memory-utilization 0.85
      - --max-num-seqs 8
    # ... ver archivo completo
```

### Lanzamiento

```bash
cd ~/seedy/coder-vllm
docker compose up -d
docker compose logs -f vllm-coder
# Esperar "INFO: Application startup complete." (~2-3 min)
```

---

## 🧪 Validación

### 1. Health check

```bash
curl http://192.168.20.57:8001/health
# Esperado: 200 OK
```

### 2. Listar modelos

```bash
source ~/seedy/coder-vllm/.env
curl -H "Authorization: Bearer $VLLM_API_KEY" \
  http://192.168.20.57:8001/v1/models | jq
# Debe mostrar: "id": "qwen2.5-coder-32b"
```

### 3. Test single inferencia

```bash
time curl -s http://192.168.20.57:8001/v1/chat/completions \
  -H "Authorization: Bearer $VLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder-32b",
    "messages": [{
      "role": "user",
      "content": "Write a Python function to detect anomalies in a list of integers."
    }],
    "max_tokens": 200,
    "stream": false
  }' | jq -r '.choices[0].message.content'

# Esperado: <20 segundos
```

### 4. Test concurrencia

```bash
for i in 1 2 3; do
  curl -s http://192.168.20.57:8001/v1/chat/completions \
    -H "Authorization: Bearer $VLLM_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"qwen2.5-coder-32b\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi number $i\"}],\"max_tokens\":20}" \
    -o /tmp/vllm_test_$i.json &
done
wait
cat /tmp/vllm_test_*.json | jq -r '.choices[0].message.content'

# Esperado: 3 respuestas en <5 segundos total
```

**Criterio de éxito:** Test 3 <20s, Test 4 <5s.

---

## 🔧 Configuración Clientes

### OpenClaw (mini-PC 192.168.20.54)

Ver: `/home/davidia/Documentos/Seedy/docs/OPENCLAW_MINIPC_VLLM_CONFIG.md`

Resumen:
```bash
# En el mini-PC, editar .env de OpenClaw
OLLAMA_BASE_URL=http://192.168.20.57:8001/v1
OLLAMA_MODEL=qwen2.5-coder-32b
OLLAMA_API_KEY=<VLLM_API_KEY del DGX>
```

### Continue.dev (VS Code)

```yaml
# ~/.continue/config.yaml
models:
  - name: Seedy Local Coder
    provider: openai
    apiBase: http://192.168.20.57:8001/v1
    apiKey: ${{ secrets.VLLM_API_KEY }}
    model: qwen2.5-coder-32b
    roles: [chat, edit]
    defaultCompletionOptions:
      temperature: 0.2
      maxTokens: 2048
```

Usar "Seedy Local Coder" cuando estés en casa (cero coste), "Seedy Auto" cuando estés fuera (vía Cloudflare).

### Seedy Coder Router v4.3

Añadir vLLM al degradation chain:

```python
# backend/coder/policy.py
DEGRADATION_CHAIN = {
    "REFACTOR_MULTI": [
        "vllm:qwen2.5-coder-32b",  # ← NUEVO: local primero
        "together:qwen3-coder-480b",
        "together:glm-5.1",
    ],
    "DEBUG": [
        "vllm:qwen2.5-coder-32b",
        "together:glm-5.1",
    ],
    # ...
}
```

Ver implementación completa en `backend/coder/providers/vllm_local_provider.py`

---

## 📈 Métricas y Monitorización

### Uso de memoria

```bash
# Ver VRAM actual
ssh daviddgx@192.168.20.57 "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader"

# Inventario completo (worst-case):
# - OS + Docker: 12 GB
# - qwen2.5:7b: 5 GB
# - seedy:v16: 9 GB
# - qwen2.5-coder-32b-awq (vLLM): 22 GB
# - KV cache vLLM (8 sesiones): 6 GB
# - qwen2.5:72b (on-demand): 50 GB
# Total worst-case: 104 GB / 128 GB = 81% utilización
```

### Healthcheck automático

```bash
# Cron cada 5 min
*/5 * * * * curl -fs http://localhost:8001/health || systemctl restart coder-vllm
```

### Dashboard Grafana

Métricas clave:
- Tokens/segundo (P50, P95, P99)
- Sesiones concurrentes activas
- Tasa de fallos (timeouts, OOM)
- Latencia first-token vs total
- GPU memory utilization

---

## 🐛 Troubleshooting

### Problema 1: "Connection refused" a :8001

**Causa:** Contenedor no arrancó correctamente.

**Solución:**
```bash
cd ~/seedy/coder-vllm
docker compose logs vllm-coder --tail=100

# Buscar errores tipo:
# - "CUDA out of memory" → bajar gpu_memory_utilization a 0.75
# - "Model not found" → verificar ruta /models/qwen2.5-coder-32b-awq
# - "Driver version mismatch" → actualizar driver a 595+ (no debería pasar)
```

### Problema 2: Respuestas muy lentas (<10 tok/s)

**Causa posible 1:** Ollama + vLLM compitiendo por VRAM (72B cargado simultáneamente).

**Solución:**
```bash
# Descargar 72B de Ollama si está cargado
ssh daviddgx@192.168.20.57 "docker exec ollama ollama stop qwen2.5:72b"

# Reducir gpu_memory_utilization de vLLM
# En docker-compose.yml: 0.85 → 0.75
```

**Causa posible 2:** CPU throttling por temperatura.

**Solución:**
```bash
# Verificar temperatura
nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader
# Si >80°C, mejorar ventilación o bajar 72B keep_alive
```

### Problema 3: OpenAI SDK incompatibilidad

**Causa:** Algún cliente espera campo específico que vLLM no emula perfectamente.

**Solución temporal:** Usar LiteLLM como proxy:
```bash
pip install litellm
litellm --model vllm/qwen2.5-coder-32b \
  --api_base http://192.168.20.57:8001 \
  --port 8002
# Cliente apunta a :8002 en lugar de :8001
```

### Problema 4: "Model loading failed" al arrancar

**Causa:** Descarga del modelo incompleta o corrupta.

**Solución:**
```bash
cd ~/models/qwen2.5-coder-32b-awq
git lfs pull  # Re-descargar archivos LFS
du -sh .      # Verificar ~22 GB
```

---

## 🔒 Seguridad

### API Key

- Generada con `openssl rand -hex 32`
- Guardada en `.env` con permisos 600
- **No commitear a git** (añadir `.env` a `.gitignore`)
- Rotar cada 3 meses

### Red

- Puerto 8001 expuesto solo en LAN (192.168.20.x)
- Para acceso externo: Cloudflare Tunnel + autenticación adicional
- Rate limit: considerar nginx reverse proxy con `limit_req`

### Aislamiento

- vLLM en compose separado → falla de vLLM no afecta Seedy v4.6
- Volumen cache separado → limpieza independiente
- Logs separados → troubleshooting más sencillo

---

## 📝 Comparativa vLLM vs Ollama

| Característica | Ollama :11434 | vLLM :8001 |
|----------------|---------------|------------|
| **Modelos servidos** | 7B, 14B, 72B (Qwen2.5 + seedy) | 32B-Coder (Qwen2.5) |
| **Quantización** | GGUF (q4_K_M, q8_0) | AWQ-Int4 (Marlin kernel) |
| **Concurrencia** | 1-2 sesiones (OLLAMA_NUM_PARALLEL=2) | 8-10 sesiones (PagedAttention) |
| **Throughput** | 15-35 tok/s (single user) | 15-22 tok/s (multi-user) |
| **Uso típico** | Pipeline RAG Seedy, chat, fine-tunes | Coding agéntico, refactors, SOC |
| **API** | `/api/generate`, `/api/chat` | `/v1/chat/completions` (OpenAI) |
| **Estado** | Producción estable GB10 | Funcional, requiere workarounds (--enforce-eager) |

**Conclusión:** No son competencia, son complementarios. Ollama para pipeline estable, vLLM para coding concurrente.

---

## 🚀 Roadmap

### v4.7.1 (próximos 7 días)
- [ ] systemd unit para auto-start en reboot
- [ ] Dashboard Grafana vLLM tokens/sesiones
- [ ] OpenClaw 5 test cases SOC (comparar 7B vs 32B)
- [ ] Continue.dev migration 50% queries a local

### v4.7.2 (próximos 30 días)
- [ ] Explorar FP8 (32 GB) vs AWQ (22 GB) calidad
- [ ] Benchmark formal HumanEval-X en modelo local
- [ ] MCP server para agentic tasks (CrewAI integration)
- [ ] Backup automático modelo a NAS cada domingo

### v4.8 (futuro)
- [ ] Evaluar Qwen3.6-Coder cuando esté disponible
- [ ] Fine-tune 32B-Coder en SOC logs reales (si OpenClaw lo justifica)
- [ ] Explorar modelos MoE cuando vLLM soporte sm_121 maduro
- [ ] GPU P2P si se añade segunda GPU al DGX

---

## 📚 Referencias

- **Qwen2.5-Coder Paper:** https://arxiv.org/abs/2409.12186
- **vLLM Documentation:** https://docs.vllm.ai/
- **GB10 (sm_121) status:** NVIDIA forums thread #4721892
- **AWQ Quantization:** https://arxiv.org/abs/2306.00978
- **PagedAttention:** https://arxiv.org/abs/2309.06180
- **Seedy v4.6 Hybrid Pipeline:** `PROGRESO_PROMPT_V4.6.md`

---

**Última actualización:** 5 mayo 2026  
**Autor:** Seedy Team  
**Versión:** v4.7.0
