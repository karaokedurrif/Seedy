# vLLM Optimization Guide v4.7

Guía completa de optimizaciones para vLLM Qwen2.5-Coder-32B-AWQ en producción.

---

## 🎯 Performance Baseline (Pre-Optimization)

**Estado actual (v4.7 initial deployment):**
- Latencia: 8s (simple query), 46s (first inference)
- GPU Memory: 18GB vLLM + 31GB Ollama = 49GB/128GB (38%)
- Max Context: 32,768 tokens
- Max Concurrent: 8 requests
- Throughput: ~5-7 tok/s

**Targets de optimización:**
- Latencia: <5s (simple), <30s (first inference)
- Throughput: >10-15 tok/s
- Max Context: 49K-65K tokens
- Max Concurrent: 12-16 requests

---

## 📊 3 Niveles de Optimización

### Level 1: Conservative (Estabilidad Máxima)
**Cuando usar:** Producción crítica, primeras 24-48h post-deployment

**Parámetros:**
```yaml
--gpu-memory-utilization: 0.55
--max-model-len: 32768
--max-num-seqs: 8
--swap-space: 4
--enable-prefix-caching: true
--enable-chunked-prefill: false
```

**Mejoras esperadas:**
- Latencia: sin cambio (~8s)
- Throughput: +10-15%
- Estabilidad: máxima
- Risk: mínimo

---

### Level 2: Balanced (Recomendado)
**Cuando usar:** Después de 48h estables, uso normal

**Parámetros:**
```yaml
--gpu-memory-utilization: 0.65
--max-model-len: 49152
--max-num-seqs: 12
--swap-space: 8
--enable-prefix-caching: true
--enable-chunked-prefill: true
```

**Mejoras esperadas:**
- Latencia: -20% (~6-7s)
- Throughput: +30-40%
- Context: +50% (32K → 49K)
- Risk: bajo

**GPU Memory:**
- vLLM: 18GB → ~24GB
- Total: 49GB → ~55GB/128GB (43%)
- Safe con Ollama coexistence

---

### Level 3: Aggressive (Máximo Rendimiento)
**Cuando usar:** Solo si Ollama no carga qwen2.5:72b, o en horarios de baja demanda

**Parámetros:**
```yaml
--gpu-memory-utilization: 0.75
--max-model-len: 65536
--max-num-seqs: 16
--swap-space: 16
--enable-prefix-caching: true
--enable-chunked-prefill: true
```

**Mejoras esperadas:**
- Latencia: -30% (~5-6s)
- Throughput: +50-60%
- Context: +100% (32K → 65K)
- Risk: medio (puede causar OOM si Ollama carga 72B)

**GPU Memory:**
- vLLM: 18GB → ~30-35GB
- Total: 49GB → ~65GB/128GB (51%)
- ⚠️ Monitorear Ollama carefully

---

## 🚀 Aplicar Optimizaciones

### Quick Start
```bash
# Conservative (safe)
~/seedy/scripts/optimize-vllm-performance.sh conservative

# Balanced (recomendado)
~/seedy/scripts/optimize-vllm-performance.sh balanced

# Aggressive (experimental)
~/seedy/scripts/optimize-vllm-performance.sh aggressive
```

### Manual Step-by-Step

1. **Backup actual:**
```bash
cd ~/seedy/coder-vllm
cp docker-compose.yml docker-compose.yml.backup
```

2. **Editar docker-compose.yml:**
```yaml
command: >
  --model /models/qwen2.5-coder-32b-awq
  --gpu-memory-utilization 0.65        # ← de 0.60 a 0.65
  --max-model-len 49152                # ← de 32768 a 49152
  --max-num-seqs 12                    # ← de 8 a 12
  --swap-space 8                       # ← NEW
  --enable-prefix-caching              # ← already there
  --enable-chunked-prefill             # ← NEW
  --quantization awq
  --dtype auto
  --tensor-parallel-size 1
  --disable-log-stats
  --trust-remote-code
```

3. **Restart vLLM:**
```bash
docker compose down
docker compose up -d
```

4. **Wait & verify:**
```bash
sleep 180  # 3 min startup
~/seedy/scripts/monitor-vllm-health.sh
```

---

## 🔬 Advanced Optimizations

### 1. Prefix Caching (Already Active)

**Status:** ✅ Enabled por default

**Beneficios:**
- Cache hit rate: 49-66% (observado en logs)
- Reduce latencia en queries repetitivas
- Ideal para Continue.dev (context reutilizado)

**Verificar:**
```bash
docker logs vllm-coder 2>&1 | grep "Prefix cache hit rate"
# Output: Prefix cache hit rate: 66.3%
```

**Tuning:**
```yaml
--enable-prefix-caching        # ya activo
--max-num-batched-tokens 8192  # optional: limitar batch size para mejor cache
```

---

### 2. Chunked Prefill (Level 2+)

**¿Qué hace?** Divide el prompt en chunks, permite intercalar prefill con decode.

**Beneficios:**
- Menor latencia para primeros tokens (TTFT)
- Mejor utilización GPU
- Reduce memory spikes

**Enable:**
```yaml
--enable-chunked-prefill
--max-num-batched-tokens 4096  # chunk size
```

**Trade-off:** Ligeramente mayor latencia total (+5-10%), pero mejor UX (streaming más fluido)

---

### 3. Speculative Decoding (Experimental)

**¿Qué es?** Usa modelo pequeño (draft) para predecir tokens, modelo grande verifica.

**Setup (requiere draft model):**
```yaml
--speculative-model qwen2.5-coder-7b-awq  # draft model
--num-speculative-tokens 5
```

**Beneficios:**
- Latencia: -30-50% en casos ideales
- Mayor throughput

**Downsides:**
- Requiere modelo draft compatible
- Mayor GPU memory (+5-8GB)
- Ganancia varía según query

**TODO:** Descargar qwen2.5-coder-7b-awq como draft model

---

### 4. FlashAttention (Already Active)

**Status:** ✅ Enabled automáticamente (vLLM detecta soporte GPU)

**Verificar:**
```bash
docker logs vllm-coder 2>&1 | grep -i "flash"
# Should see: "Using FlashAttention-2"
```

**Si no está activo:**
```yaml
--use-v2-block-manager  # force FlashAttention v2
```

---

### 5. Continuous Batching (Already Active)

**Status:** ✅ vLLM lo hace por default

**Tuning:**
```yaml
--max-num-seqs 12              # máx requests simultáneos
--max-num-batched-tokens 8192  # máx tokens procesados en batch
```

**Monitorear:**
```bash
docker logs vllm-coder 2>&1 | grep "Running:"
# Running: 3 reqs, Waiting: 0 reqs
```

**Si "Waiting" > 0 frecuentemente:** aumentar `--max-num-seqs`

---

## 🧪 Benchmarking

### Simple Query Benchmark
```bash
#!/bin/bash
echo "Benchmarking simple query (2+2)..."

for i in {1..10}; do
  START=$(date +%s%N)
  curl -s -X POST http://localhost:8001/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4" \
    -d '{
      "model": "qwen2.5-coder-32b",
      "messages": [{"role": "user", "content": "2+2="}],
      "max_tokens": 10
    }' > /dev/null
  END=$(date +%s%N)
  LATENCY_MS=$(( (END - START) / 1000000 ))
  echo "Run $i: ${LATENCY_MS}ms"
done
```

**Baseline:** 8000ms promedio  
**Target Level 2:** 6000ms promedio (-25%)  
**Target Level 3:** 5000ms promedio (-37%)

---

### Concurrent Request Benchmark
```bash
#!/bin/bash
echo "Benchmarking 10 concurrent requests..."

START=$(date +%s)
for i in {1..10}; do
  (curl -s -X POST http://localhost:8001/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4" \
    -d "{
      \"model\": \"qwen2.5-coder-32b\",
      \"messages\": [{\"role\": \"user\", \"content\": \"Escribe función fibonacci recursiva\"}],
      \"max_tokens\": 100
    }" > /tmp/resp_$i.json) &
done
wait
END=$(date +%s)
TOTAL_TIME=$(( END - START ))
echo "Total time: ${TOTAL_TIME}s"
echo "Throughput: $(bc <<< "scale=2; 10 / $TOTAL_TIME") req/s"
```

**Baseline:** ~1.2 req/s (10 requests en ~8s cada uno)  
**Target Level 2:** ~1.8 req/s (+50%)  
**Target Level 3:** ~2.4 req/s (+100%)

---

## 🎯 TensorRT-LLM (Ultimate Optimization)

**Latencia target:** <3s (simple query), <20s (first inference)

### Pre-requisitos
```bash
# Check TensorRT support
nvidia-smi | grep "CUDA Version"
# Requiere CUDA 12.0+

# Check vLLM version
docker exec vllm-coder python -c "import vllm; print(vllm.__version__)"
# Requiere vLLM 0.3.0+ para TensorRT backend
```

### Conversión a TensorRT

**⚠️ EXPERIMENTAL — No implementado en v4.7 initial**

```bash
# 1. Instalar TensorRT-LLM (en contenedor o host)
pip install tensorrt-llm

# 2. Convertir modelo AWQ → TensorRT
python convert_checkpoint.py \
  --model_dir ~/models/qwen2.5-coder-32b-awq \
  --dtype float16 \
  --output_dir ~/models/qwen2.5-coder-32b-trt \
  --tp_size 1

# 3. Build TensorRT engine
trtllm-build \
  --checkpoint_dir ~/models/qwen2.5-coder-32b-trt \
  --output_dir ~/models/qwen2.5-coder-32b-trt-engine \
  --gemm_plugin auto \
  --max_batch_size 16 \
  --max_input_len 32768 \
  --max_output_len 2048

# 4. Deploy con vLLM TensorRT backend
# (Requiere imagen Docker especial vllm-tensorrt)
```

**Beneficios esperados:**
- Latencia: -50-70% (8s → 2-3s)
- Throughput: +100-200%
- GPU memory: sin cambio

**Downsides:**
- Conversión tarda 2-4h
- Requiere rebuild al cambiar parámetros
- Mayor complejidad deployment

**Status:** Roadmap para v4.8 (junio 2026)

---

## 📊 Monitoring Post-Optimization

### Key Metrics to Watch

1. **Latency P95:**
```bash
# Extraer de logs
docker logs vllm-coder 2>&1 | grep "throughput" | tail -20
```

2. **GPU Memory:**
```bash
watch -n 5 'nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv'
```

3. **Cache Hit Rate:**
```bash
docker logs vllm-coder 2>&1 | grep "Prefix cache" | tail -1
# Target: >50%
```

4. **Throughput:**
```bash
docker logs vllm-coder 2>&1 | grep "Avg.*throughput" | tail -10
# Avg prompt throughput: XXX tokens/s
# Avg generation throughput: XXX tokens/s
```

---

## 🚨 Troubleshooting

### OOM (Out of Memory)
```
Error: CUDA out of memory
```

**Fix:**
1. Reducir `--gpu-memory-utilization` (0.65 → 0.60 → 0.55)
2. Reducir `--max-num-seqs` (12 → 8)
3. Reducir `--max-model-len` (49152 → 32768)
4. Unload Ollama qwen2.5:72b temporalmente

---

### High Latency Spikes
```
P95 latency suddenly >30s
```

**Diagnose:**
```bash
# Check concurrent requests
docker logs vllm-coder | grep "Running:"
# Si "Running: >8", hay contention

# Check Ollama
curl localhost:11434/api/ps
# Si qwen2.5:72b cargado, puede competir por GPU
```

**Fix:**
1. Aumentar `--max-num-seqs` si hay muchas "Waiting"
2. Reducir Ollama keep-alive: `OLLAMA_KEEP_ALIVE=5m`

---

### Container Crash
```
Container exited with code 137 (OOM killed)
```

**Fix:**
1. Rollback a config anterior:
```bash
cd ~/seedy/coder-vllm
docker compose down
cp docker-compose.yml.backup docker-compose.yml
docker compose up -d
```

2. Aplicar Level 1 (conservative) primero

---

## ✅ Optimization Checklist

- [ ] **Pre-optimization:**
  - [ ] Backup docker-compose.yml
  - [ ] Baseline benchmarks guardados
  - [ ] Health check pasando 10/10

- [ ] **Apply Level 1 (24-48h):**
  - [ ] Aplicar conservative config
  - [ ] Monitorear latency P95 cada 4h
  - [ ] Verificar GPU memory no excede 55GB
  - [ ] Cache hit rate >40%

- [ ] **Apply Level 2 (recommended):**
  - [ ] Después de 48h stable Level 1
  - [ ] Aplicar balanced config
  - [ ] Benchmark: latency debe bajar -20%
  - [ ] Verificar GPU memory <60GB
  - [ ] Cache hit rate >50%

- [ ] **Optional Level 3:**
  - [ ] Solo si Ollama unload 72B
  - [ ] Aplicar aggressive config
  - [ ] Benchmark: latency debe bajar -30%
  - [ ] Monitorear OOM risk (alerting activo)

- [ ] **Post-optimization:**
  - [ ] Grafana dashboard actualizado
  - [ ] Alerting configurado (GPU >90%)
  - [ ] Documentar mejoras reales
  - [ ] User validation (Continue.dev + Openclaw)

---

## 📈 Expected Results Summary

| Métrica | Baseline | Level 1 | Level 2 | Level 3 |
|---------|----------|---------|---------|---------|
| Latency simple | 8s | 8s | 6-7s | 5-6s |
| Latency first | 46s | 46s | 35-40s | 30-35s |
| Throughput | 5-7 tok/s | 6-8 tok/s | 8-12 tok/s | 12-15 tok/s |
| Max context | 32K | 32K | 49K | 65K |
| Concurrent | 8 | 8 | 12 | 16 |
| GPU memory | 18GB | 18GB | 24GB | 30-35GB |
| Cache hit | 49% | 55% | 60% | 65% |

---

## 🔗 Referencias

- [vLLM Performance Tuning](https://docs.vllm.ai/en/latest/performance.html)
- [Prefix Caching](https://docs.vllm.ai/en/latest/automatic_prefix_caching.html)
- [Chunked Prefill](https://docs.vllm.ai/en/latest/chunked_prefill.html)
- [TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM)

---

**Última actualización:** 5 mayo 2026  
**Autor:** daviddgx  
**Versión:** v4.7 optimization guide
