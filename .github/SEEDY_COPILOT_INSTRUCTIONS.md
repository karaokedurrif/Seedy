# SEEDY — Sistema de IA para NeoFarm
## Instrucciones Maestras para VSCode Copilot (Jefe/Orchestrator)

---

## QUÉ ES SEEDY

Seedy es el **sistema de inteligencia artificial multi-agente** que asiste a la plataforma NeoFarm (ganadería de precisión: porcino intensivo, vacuno extensivo, avicultura). Incluye: LLM fine-tuned (Qwen2.5 + LoRA), RAG (Qdrant + mxbai-embed-large), 6 workers especializados en Open WebUI, backend FastAPI, pipeline CV (YOLO), motor genético, GIS/GeoTwin, y app móvil React Native.

**Seedy NO es NeoFarm.** NeoFarm es la plataforma (IoT, sensores, hub.vacasdata.com). Seedy es el cerebro de IA que la asiste.

---

## ESTADO ACTUAL (Junio 2025)

### Hardware
- **MSI Vector 16 HX**: RTX 5080 16GB VRAM, 64GB RAM, Ubuntu 24.04
- **NAS**: smb://192.168.30.100/datos/ (backup modelos GGUF)
- **Tailscale**: red mesh activa para acceso remoto

### Docker (red `ai_default`, external)
| Servicio | Puerto | Notas |
|----------|--------|-------|
| ollama | :11434 | GPU, vol `ollama_data` + `/home/davidia/models:/models` |
| open-webui | :3000→8080 | Vol `ai_openwebui_data` (external), alias `OpenWebUI` |
| qdrant | :6333/:6334 | Vector store RAG backend |
| seedy-backend | :8000 | FastAPI, alias `fastapi`, monta `./genetics`, `./conocimientos` |
| cloudflared | — | Tunnel "seedy" (token-based), ID: 60b6373e |
| influxdb | :8086 | Series temporales IoT, org=neofarm, bucket=porcidata |
| mosquitto | :1883/:9001 | MQTT broker IoT |
| nodered | :1880 | Flujos IoT |
| grafana | :3001→3000 | Dashboards |
| seedy-ingest | — | Autoingesta diaria |

### Acceso público (Cloudflare Tunnel "seedy")
- `seedy.neofarm.io` → Open WebUI
- `seedy-api.neofarm.io` → FastAPI backend
- `seedy-grafana.neofarm.io` → Grafana

### Modelos en Ollama
```
seedy:v6-local         8.1 GB   ← Fine-tuned Qwen2.5-7B + LoRA v6, 302 ej., Q8_0
qwen2.5:7b             4.7 GB   ← Modelo base (fallback)
mxbai-embed-large      669 MB   ← Embeddings para RAG
```
GGUF producción: `/home/davidia/models/seedy_v6_q8_0.gguf`

### Fine-tune en Together.ai
- **Job v6**: `ft-1f0c7e89-525d` ← **ACTUAL** (302 ej., Qwen2.5-7B-Instruct + LoRA)
- **Job v5**: `ft-e0f71c8c-45d3` (267 ej.)
- **Job v4**: `ft-o1bf79da-6ofa` (187 ej.)
- **Job v3**: `ft-bc10fc32-2235` (200 ej.)
- **Base actual**: Qwen2.5-7B-Instruct (próximo: Qwen2.5-14B-Instruct)
- **Tipo**: LoRA (r=16, alpha=32)

### Datasets SFT en disco
```
seedy_dataset_sft_v6.jsonl        302 ejemplos  ← PRODUCCIÓN
seedy_dataset_sft_v5.jsonl        267 ejemplos
seedy_dataset_sft_v4.jsonl        187 ejemplos
seedy_dataset_sft_v3_plus60.jsonl 200 ejemplos
seedy_dataset_sft_geotwin.jsonl    35 ejemplos
```
**Distribución v6:** IoT 83, Avicultura 36, GeoTwin 36, Porcino 30, Vacuno 24, Twins 18, Normativa 17, Nutrición 16, Genética 13, **VISION 0**, **Malines 0**
⚠️ **Gaps identificados:** VISION (0 ej.), Malines/avicultura específica (0 ej.), Genética cruzada (débil)

### RAG — Open WebUI Admin Settings (ACTUALES)
```
Embedding Model Engine: ollama
Embedding Model: mxbai-embed-large
Top K: 8
Hybrid Search: ON
BM25 Weight: 0.7
Chunk Size: 1500
Chunk Overlap: 300
Relevance Threshold: 0.25
```

### 6 Colecciones de Conocimiento (en Open WebUI)

| # | Colección | Docs | Contenido clave |
|---|-----------|------|-----------------|
| 1 | PorciData — IoT & Hardware | 5 | BOM 7+1 capas (~1.420 EUR/nave), sensores, firmware ESP32, piloto 3 naves |
| 2 | NeoFarm — Nutrición & Formulación | 8 | Butirato sódico, enzimas NSP, NRC 2012, solver LP HiGHS, lonjas |
| 3 | NeoFarm — Genética | 7 | Wright consanguinidad, EPDs, motor apareamiento, razas autóctonas |
| 4 | NeoFarm — Estrategia & Competencia | 4 | Análisis competitivo, Fancom vs Nedap, posicionamiento |
| 5 | NeoFarm — Digital Twins & IoT | 9 | Twins porcino/vacuno, Mioty vs LoRa, playbooks, centinelas |
| 6 | Normativa & SIGE | 4 | RD 306/2020 (11 planes SIGE), ECOGAN 8 pasos, RD 1135/2002 superficies |

Cada colección incluye archivos `_RESUMEN_*.md` con keywords y sinónimos que actúan como índices RAG optimizados.

### Tests de RAG (resultados actuales)
```
Test 1 (BOM/nave):          ✅ PASS → 1.420 EUR
Test 2 (Capa acústica):     ✅ PASS → INMP441 + ESP32, ~15 EUR  
Test 3 (Butirato inmunidad): ✅ PASS → IgA, tight junctions, TNF-α, IL-6
Test 4 (11 planes SIGE):    ⚠️ PARCIAL → Lista 11 pero inventa algunos nombres
```

---

## 6 MODELOS SEEDY EN OPEN WEBUI

### Modelo 1: Seedy • Jefe (Planner/Orchestrator)
- **ID**: `seedy-chief-planner`
- **Base actual**: `seedy:v6-local` (migración a 14B planificada)
- **Params**: temperature 0.25, top_p 0.9, repeat_penalty 1.1, num_ctx 8192
- **Colecciones**: TODAS (visión global)
- **System prompt**: Ver system prompt embebido en Open WebUI (incluye ecosistema NeoFarm, workers 1-5, reglas de respuesta estructurada)

### Modelo 2: Seedy • Worker RAG/Docs
- **Base**: `qwen2.5:7b` | **Misión**: RAG, chunking, metadatos, citas, evaluación | **Colecciones**: TODAS

### Modelo 3: Seedy • Worker IoT & Datos
- **Base**: `qwen2.5:7b` | **Misión**: IoT 7+1 capas PorciData, MQTT, InfluxDB, Grafana | **Colecciones**: IoT + Twins

### Modelo 4: Seedy • Worker Digital Twin
- **Base**: `qwen2.5:7b` | **Misión**: Twins porcino/vacuno, World Model, RL, GIS Cesium 3D | **Colecciones**: Twins + IoT + Nutrición

### Modelo 5: Seedy • Worker Web/Automation
- **Base**: `qwen2.5:7b` | **Misión**: Lonjas, AEMET, NDVI, Catastro, Playwright | **Colecciones**: Estrategia

### Modelo 6: Seedy • Worker Coder & Data
- **Base**: `qwen2.5:7b` | **Misión**: Python, FastAPI, Docker, datasets SFT, Together.ai, infra | **Colecciones**: IoT + Nutrición
- **Prompt detallado**: Ver `conocimientos/SEEDY — Worker: Coder & Data (Prompt para Copilot + MCP).md`

---

## ARQUITECTURA ACTUAL (desplegada y funcionando)

```
┌───────────────────────────────────────────────────────────────┐
│                         USUARIOS                               │
│  seedy.neofarm.io         seedy-api.neofarm.io    App Móvil   │
│  (Open WebUI ganadero)    (FastAPI backend)       (React N.)  │
│  seedy-grafana.neofarm.io                                     │
└─────────┬──────────────────────┬──────────────────┬───────────┘
          │    Cloudflare Tunnel "seedy"             │
          ▼                      ▼                   ▼
┌───────────────────────────────────────────────────────────────┐
│  Docker (ai_default) — MSI Vector 16 HX, RTX 5080 16GB       │
│                                                               │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────────┐ │
│  │  Ollama     │ │  Open WebUI  │ │  Seedy Backend FastAPI │ │
│  │  :11434     │ │  :3000→8080  │ │  :8000                 │ │
│  │  seedy:v6   │ │  6 workers   │ │  /chat SSE /health     │ │
│  │  GPU all    │ │  RAG embeds  │ │  RAG Qdrant + Together │ │
│  └─────────────┘ └──────────────┘ └────────────────────────┘ │
│  ┌─────────┐ ┌───────────┐ ┌───────┐ ┌──────┐ ┌──────────┐ │
│  │ Qdrant  │ │ InfluxDB  │ │ MQTT  │ │ N-R  │ │ Grafana  │ │
│  │ :6333   │ │ :8086     │ │ :1883 │ │:1880 │ │ :3001    │ │
│  └─────────┘ └───────────┘ └───────┘ └──────┘ └──────────┘ │
│  ┌──────────────┐ ┌────────────────┐                         │
│  │ cloudflared  │ │  seedy-ingest  │                         │
│  │ tunnel token │ │  diario        │                         │
│  └──────────────┘ └────────────────┘                         │
└───────────────────────────────────────────────────────────────┘
          │
          ▼ (fine-tune + inference producción)
   ┌──────────────┐
   │  Together.ai │  Seedy fine-tuned (Qwen2.5-7B → 14B planificado)
   │  API v1      │  ~0.25 EUR/mes (1h/día uso)
   └──────────────┘
```

### Decisiones de arquitectura YA tomadas
1. **LLM producción → Together.ai** (fine-tuned). 24/7 sin GPU local.
2. **LLM fallback → Ollama local** (`seedy:v6-local`). Demos offline o Together caído.
3. **RAG + Embeddings → Local** (mxbai-embed-large + Qdrant). Privacidad total, coste 0.
4. **Open WebUI** = interfaz ganadero con ChromaDB nativo. Qdrant para backend FastAPI.
5. **Rerank → Local** (`bge-reranker-v2-m3`). Top K=8 → rerank → Top 3.
6. **Digital Twin + IoT → Local**. LLM solo explica, no calcula.
7. **Clasificación → Seedy como router** (no reglas manuales).
8. **Tunnel → Cloudflare** token-based, subdominios 1 nivel bajo `*.neofarm.io`.
9. **Migración 14B** planificada: Qwen2.5-14B-Instruct, Q4_K_M (~8.5 GB, cabe en RTX 5080).

---

## FASES DEL PROYECTO (estado actual)

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Docker Compose + RAG Qdrant + Ingestión | ✅ Completada |
| 2 | Autoingesta diaria (RSS/APIs/briefs) | ✅ Completada |
| 3 | Dataset v5 fine-tune + LoRA merge | ✅ Completada |
| 4 | /chat SSE endpoint FastAPI | ✅ Completada |
| 5 | NAS + Tailscale + Backup | 🔶 Parcial |
| 6 | Vision CV pipeline (YOLO) | ✅ Completada (código, datos SFT pendientes) |
| 7 | Training + Edge AI + IoT | ✅ Completada |
| 8 | Cámaras físicas (hardware) | ⏭️ Pendiente hardware |
| 9 | Motor de Simulación Genética | ✅ Completada |
| 10 | GIS/GeoTwin (Cesium 3D + PNOA) | ✅ Completada |
| 11 | Fine-tune v6 Unificado (302 ej.) | ✅ Completada |
| 12 | App Android (React Native + Expo) | ✅ Completada |
| 13 | Cloudflare Tunnel (dominios públicos) | ✅ Completada |
| 14 | **Dataset v7 + migración 14B** | 🔜 Siguiente |

### Fase 14 — Plan (próximo)
1. Expandir dataset de 302 → ~500 ejemplos (VISION +25, Malines +10, Genética +15, cross-domain +50)
2. Fine-tune Qwen2.5-14B-Instruct en Together.ai
3. Merge LoRA + GGUF Q4_K_M local
4. Evaluar con golden set y comparar vs v6

---

## REGLAS PARA COPILOT

### Técnicas
- **Python 3.11+**, **FastAPI** con async/await, **httpx** para HTTP async
- **qdrant-client** para Qdrant, **sentence-transformers** para reranker
- Docker Compose, type hints estrictos, Pydantic models
- Todos los archivos en `/home/davidia/Documentos/Seedy/`
- Los parámetros RAG: chunk 1500/300, Top K 8, hybrid ON, BM25 0.7

### Operativas
- **Ejecuta, no supongas** — verifica estado con comandos reales antes de actuar
- **Prioriza end-to-end** — que funcione primero, optimizar después
- **Responde en español** para documentación y comentarios al usuario
- **Documenta** cambios significativos en `conocimientos/SEEDY_MASTER_ROADMAP_2026.md`
- **No inventes** cifras de genética/nutrición/normativa — busca en `/conocimientos/`

### Dataset y Fine-tune
- Dataset actual: `seedy_dataset_sft_v6.jsonl` (302 ej.)
- Builder: `build_v4.py` (base para futuros builders)
- System prompt SFT: definido en builder, NO inventar otro
- Together.ai API: `https://api.together.xyz/v1/`, key en `.env`
- Workflow detallado de fine-tune: ver `conocimientos/SEEDY — Worker: Coder & Data (Prompt para Copilot + MCP).md`

### Infraestructura
- Red Docker: `ai_default` (external)
- Volumes critical: `ai_openwebui_data` (external), `ollama_data`, `qdrant_data`
- Tunnel: token en `.env` como `TUNNEL_TOKEN`
- GGUF: `/home/davidia/models/`
- Conocimientos RAG: `/home/davidia/Documentos/Seedy/conocimientos/` (6 carpetas temáticas)
