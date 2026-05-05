# LLM Routing System — Seedy v4.6

Sistema de enrutamiento inteligente de LLMs con hibridación Together.ai + Ollama local.

**Objetivo:** Reducir coste 43% ($207/mes → $120/mes) moviendo pasos pequeños y batch a Ollama local, manteniendo calidad y latencia para chat interactivo.

---

## 📊 Arquitectura

```
Query → LLMRouter.call_with_policy(policy_name)
  ├─ BudgetGuard.check() → Cap diario $7.50, mensual $175
  ├─ Policy.get_primary() → Modelo primario (Together.ai o Ollama)
  ├─ Provider.generate() → Llamada HTTP al modelo
  └─ Policy.get_fallback() → Modelo fallback si falla primary
```

### Componentes

| Componente | Ubicación | Función |
|------------|-----------|---------|
| **LLMRouter** | `backend/services/llm_router/router.py` | Dispatcher central con fallback automático |
| **Policy** | `backend/services/llm_router/policy.py` | 13 policies definidas (rewriter, classifiers, generation, batch) |
| **BudgetGuard** | `backend/services/llm_router/budget_guard.py` | Cap diario/mensual + tracking spend |
| **OllamaProvider** | `backend/services/llm_router/providers/ollama_provider.py` | Cliente HTTP Ollama :11434 |
| **TogetherProvider** | `backend/services/llm_router/providers/together_provider.py` | Cliente Together.ai con pricing real |
| **UsageTracker** | `backend/services/llm_router/usage_tracker.py` | Telemetría InfluxDB (opcional) |

---

## 🎯 Policies Definidas (13)

| Policy | Primary | Fallback | Max Latency | Uso |
|--------|---------|----------|-------------|-----|
| **rewriter** | ollama:qwen2.5-7b | together:qwen2.5-7b-turbo | 5s | Query rewriting conversacional |
| **classifier_category** | ollama:qwen2.5-7b | together:qwen2.5-7b-turbo | 3s | Clasificación categoría (AVICULTURA, IOT, etc.) |
| **classifier_temporal** | ollama:qwen2.5-7b | together:qwen2.5-7b-turbo | 3s | Clasificación temporalidad (STABLE, DYNAMIC, etc.) |
| **evidence_extraction** | ollama:qwen2.5-7b | together:qwen2.5-7b-turbo | 15s | Extracción de hechos de chunks RAG |
| **generation_default** | together:qwen3-235b-tput | together:kimi-k2.5 | 30s | Chat interactivo (modo normal) |
| **generation_think** | together:qwen3-235b-tput | together:deepseek-r1 + ollama:seedy-v16 | 60s | Modo `/think` razonamiento paso a paso |
| **generation_local** | ollama:seedy-v16 | together:qwen2.5-7b-turbo | 20s | Modo `/local` (fine-tuned 14B, rápido) |
| **generation_deep** | ollama:qwen2.5-72b | ollama:seedy-v16 | 300s | Modo `/deep` (análisis profundo, LENTO) |
| **generation_eco** | ollama:seedy-v16 | (none) | 20s | Modo `/eco` (offline, sin web search) |
| **critic_gate** | ollama:seedy-v16 | together:qwen3-235b-tput | 8s | Critic gate estructural + técnico |
| **behavior_7d_analysis** | ollama:qwen2.5-72b | together:qwen3-235b-tput | 600s | Worker batch: análisis comportamiento 7D |
| **mating_confirmation** | ollama:qwen2.5-72b | together:qwen3-235b-tput | 120s | Worker batch: confirmación de montas |
| **weekly_report** | ollama:qwen2.5-72b | together:deepseek-r1 | 900s | Worker batch: informe semanal ejecutivo |

---

## 💰 Cost Optimization

### Antes v4.6 (100% Together.ai)

| Paso | Model | Coste/query | Queries/día | Coste/día | Coste/mes |
|------|-------|-------------|-------------|-----------|-----------|
| Rewriter | Qwen2.5-7B Turbo | $0.0005 | 400 | $0.20 | $6 |
| Classifier Cat | Qwen2.5-7B Turbo | $0.0003 | 400 | $0.12 | $3.60 |
| Classifier Temp | Qwen2.5-7B Turbo | $0.0003 | 400 | $0.12 | $3.60 |
| Evidence | Qwen2.5-7B Turbo | $0.0008 | 300 | $0.24 | $7.20 |
| Generation | Kimi-K2.5 / Qwen3-235B | $0.015 | 400 | $6.00 | $180 |
| Critic | Qwen3-235B | $0.002 | 300 | $0.60 | $18 |
| **TOTAL** | - | - | - | **$7.28** | **$218** |

### Después v4.6 (45% Ollama local)

| Paso | Model | Coste/query | Queries/día | Coste/día | Coste/mes |
|------|-------|-------------|-------------|-----------|-----------|
| Rewriter | **Ollama qwen2.5-7b** | **$0** | 400 | **$0** | **$0** |
| Classifier Cat | **Ollama qwen2.5-7b** | **$0** | 400 | **$0** | **$0** |
| Classifier Temp | **Ollama qwen2.5-7b** | **$0** | 400 | **$0** | **$0** |
| Evidence | **Ollama qwen2.5-7b** | **$0** | 300 | **$0** | **$0** |
| Generation | Together Qwen3-235B | $0.015 | 400 | $6.00 | $180 |
| Critic | **Ollama seedy:v16** | **$0** | 300 | **$0** | **$0** |
| **TOTAL** | - | - | - | **$6.00** | **$180** |

**Ahorro:** $7.28 → $6.00/día = **-18%** en pasos pequeños  
**Ahorro total (con workers batch):** $218 → $120-143/mes = **-31% a -42%**

---

## 🚀 Uso

### Llamada básica

```python
from services.llm_router import llm_router

result = await llm_router.call_with_policy(
    policy_name="rewriter",
    system_prompt="Reescribe la query...",
    user_message="cuantas aves tengo",
    max_tokens=100,
    temperature=0.0,
)

print(result.content)      # "¿Cuántas aves tengo en total?"
print(result.provider)     # "ollama"
print(result.cost)         # 0.0
print(result.latency_ms)   # 360
```

### Prefijos en chat (Open WebUI)

```
/local ¿Cuántas aves hay en el gallinero?
→ Usa seedy:v16 local (rápido, gratis)

/deep Analiza en detalle el comportamiento de PAL-001 esta semana
→ Usa qwen2.5:72b local (lento, warning al usuario)

/eco ¿Qué razas de capones hay?
→ Usa seedy:v16 sin web search (offline mode)

/think ¿Qué cámaras de IA vision son mejores para pollitos?
→ Usa qwen3-235b con razonamiento paso a paso
```

---

## 📈 Monitorización

### Métricas clave

- **Provider distribution:** ollama vs together (target: 45% ollama)
- **Cost per day:** Cap $7.50, objetivo $4-6
- **Latency P95:** Rewriter <5s, classifiers <3s, evidence <15s, critic <8s
- **Fallback rate:** <3% (indica problemas de conectividad o modelo)
- **Budget alerts:** Warning al 80% del cap diario ($6)

### Grafana Dashboard

Ver `docs/grafana_seedy_pipeline_v46.json`

Panels:
1. Cost per day (línea temporal)
2. Provider distribution (pie chart)
3. Latency by policy (heatmap P50/P95/P99)
4. Fallback events (rate por policy)
5. Budget remaining (gauge diario/mensual)

---

## 🔧 Configuración

### Docker Compose

```yaml
ollama:
  environment:
    OLLAMA_NUM_PARALLEL: 2
    OLLAMA_MAX_LOADED_MODELS: 3
    OLLAMA_KEEP_ALIVE: 24h
    OLLAMA_KV_CACHE_TYPE: q8_0
    OLLAMA_FLASH_ATTENTION: true

seedy-backend:
  environment:
    TOGETHER_API_KEY: ${TOGETHER_API_KEY}
    BUDGET_DAILY_CAP: 7.50
    BUDGET_MONTHLY_CAP: 175.00
```

### Models en Ollama

```bash
docker exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M
docker exec ollama ollama pull qwen2.5:72b-instruct-q4_K_M
# seedy:v16 ya disponible (fine-tuned)
```

---

## 🐛 Troubleshooting

### Error: "Ollama model not found"

```bash
docker exec ollama ollama list
docker exec ollama ollama pull <model_name>
```

### Error: "Budget cap exceeded"

- BudgetGuard bloqueó llamada Together.ai
- Check logs: `grep BudgetGuard logs/backend.log`
- Aumentar cap en `.env` o esperar reset diario (00:00 UTC)

### Fallback rate >10%

- Ollama puede estar sobrecargado o sin memoria GPU
- Check: `docker stats ollama`
- Solución temporal: Bajar `OLLAMA_MAX_LOADED_MODELS` a 2

### Latencia alta en modo `/deep`

- **Normal:** qwen2.5:72b en GB10 @ 4.3 tok/s → 2-5 min
- Warning al usuario está activo
- No usar `/deep` para chat interactivo

---

## 📚 Referencias

- [Prompt v4.6 Hybrid](../prompt_seedy_v4.6_hybrid.md)
- [Policy definitions](../backend/services/llm_router/policy.py)
- [Usage tracker schema](../backend/services/llm_router/usage_tracker.py)
- [Together.ai pricing](https://www.together.ai/pricing)
