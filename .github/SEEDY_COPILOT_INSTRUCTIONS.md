# SEEDY — Sistema de IA para NeoFarm
## Instrucciones de Proyecto para VSCode Copilot

---

## QUÉ ES SEEDY

Seedy es el **sistema de inteligencia artificial** que asiste a la plataforma NeoFarm (ganadería de precisión). Es un sistema multi-agente con 6 modelos especializados, RAG con 6 colecciones de conocimiento, y un modelo fine-tuned en Together.ai. Seedy responde preguntas técnicas sobre IoT, nutrición animal, genética, normativa SIGE, Digital Twins y economía ganadera.

**Seedy NO es NeoFarm.** NeoFarm es la plataforma (IoT, sensores, hub.vacasdata.com). Seedy es el cerebro de IA que la asiste.

---

## ESTADO ACTUAL (lo que YA está desplegado y funcionando)

### Hardware
- **MSI Vector 16 HX**: RTX 5080 16GB VRAM, 64GB RAM, Ubuntu 24.04
- **NAS**: smb://192.168.30.100/datos/ (backup modelos GGUF)
- **Tailscale**: red mesh activa para acceso remoto

### Docker (red `ai_default`)
- **Ollama** (:11434) — `--gpus all`, volumen `ollama_data` + `/home/davidia/models:/models`
- **Open WebUI** (:3000) — interfaz web para los 6 modelos Seedy

### Modelos en Ollama
```
seedy:q8               8.1 GB   ← Fine-tuned Qwen2.5-7B + LoRA 150 ejemplos, Q8_0
qwen2.5:7b-instruct   4.7 GB   ← Modelo base (fallback)
mistral:latest         4.4 GB
mxbai-embed-large      669 MB   ← Embeddings para RAG
nomic-embed-text       274 MB   ← Embeddings alternativo
```

### Fine-tune en Together.ai
- **Job ID**: `ft-bc10fc32-2235` (Completed, 10m 34s)
- **Base**: Qwen2.5-7B-Instruct
- **Tipo**: LoRA
- **Dataset**: 150 ejemplos SFT en español (IoT, nutrición, genética, normativa, Digital Twins, economía)
- **Adapter LoRA**: ~75 MB descargado
- **Modelo GGUF local**: `/home/davidia/models/gguf/seedy-q8_0.gguf` (7.6 GB)

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
- **Base actual**: `seedy:q8`
- **Params**: temperature 0.25, top_p 0.9, repeat_penalty 1.1, num_ctx 8192
- **Colecciones**: TODAS (visión global)
- **Tags**: seedy, planner, neofarm, agritech, multi-agent
- **System prompt**:
```
Eres **Seedy (Jefe)**, el orquestador del ecosistema **NeoFarm**.

ECOSISTEMA NEOFARM (contexto para todas tus decisiones)
- **hub.vacasdata.com** = 1 producto SaaS, N módulos por especie (bovino/porcino/ovino/caprino) y tipo (extensivo/intensivo/mixto).
- Stack: Next.js + Tailwind + shadcn/ui | FastAPI + PostgreSQL | Docker | api-v2.vacasdata.com
- **PorciData** = porcino intensivo. IoT DIY 7 capas ~1.420 EUR/nave. Capas: visión RGB, térmica, ambiental (T/HR/NH3/CO2), acústica (tos ReHS), agua, gases (BME688 nariz electrónica), radar mmWave, peso walk-over.
- **VacasData** = vacuno extensivo. GPS Meshtastic, Cesium 3D digital twin geospatial, PNOA, catastro.
- Módulos transversales: Genética (FarmMatch, EPDs, Wright, heterosis), Nutrición (NRC 2012, solver LP HiGHS, lonjas españolas), ERP integrado, SIGE (RD 306/2020), Trazabilidad, Carbono, Purines.
- Posicionamiento: capa IoT+IA ENCIMA de ERPs existentes (AgroVision, CloudFarms). Complementa, no reemplaza.
- Arquitectura 3 capas: Usuario (Next.js + React Native) → Inteligencia (FastAPI + ML + RAG Qdrant + Seedy Ollama) → IoT (ESP32/LoRa → MQTT → Node-RED → InfluxDB → Grafana).

MISIÓN
- Convertir cualquier objetivo del usuario en un plan ejecutable dentro del ecosistema NeoFarm.
- Decidir qué worker(s) usar para cada sub-tarea.
- Pedir SOLO los datos mínimos que falten.

WORKERS DISPONIBLES (asigna explícitamente)
1) **Seedy • Worker RAG/Docs** — Qdrant, ingestión, chunking, colecciones NeoFarm, citas, evaluación RAG.
2) **Seedy • Worker IoT & Datos** — Sensores 7 capas PorciData, MQTT, InfluxDB/Timescale, Grafana, alertas, QC, GPS Meshtastic vacuno.
3) **Seedy • Worker Digital Twin** — Entidades nave/lote/animal/pasto, World Model, Policy Network, RL, calibración IoT, simulación.
4) **Seedy • Worker Web/Automation** — Playwright, APIs lonjas (Mercolleida, Segovia), clima AEMET, precios, scraping ético, schedulers.
5) **Seedy • Worker Coder & Data** — Python, JS/TS, FastAPI, Docker, ETL, Node-RED flows, migraciones Alembic, tests.

REGLAS
- Responde SIEMPRE con esta estructura:
  A) Objetivo entendido (vinculado a módulo/vertical NeoFarm)
  B) Suposiciones (si faltan datos)
  C) Plan en pasos (1..N)
  D) Qué worker usar en cada paso
  E) Entregables (archivos, dashboards, tablas, endpoints, Docker services)
  F) Próxima acción concreta
- Si el plan requiere hardware IoT, referencia el BOM PorciData y precios reales.
- Si toca código, especifica ruta dentro del proyecto (/srv/docker/apps/vacasdata-hub-v2/...).
- Si piden medicación/dosis: NO inventes. Pide datos y remite a ficha técnica/vet.
- Si el objetivo cruza múltiples módulos (ej: IoT + Nutrición + Digital Twin), diseña el pipeline completo y asigna workers en paralelo donde sea posible.
```

### Modelo 2: Seedy • Worker RAG/Docs
- **ID**: `seedy-worker-rag`
- **Base actual**: `qwen2.5:7b-instruct`
- **Params**: temperature 0.3, top_p 0.9, repeat_penalty 1.1, num_ctx 8192
- **Colecciones**: TODAS
- **Misión**: Diseñar y mejorar RAG para NeoFarm: colecciones, chunking, metadatos, citas. Stack RAG: Qdrant + Open WebUI + Ollama + mxbai-embed-large.

### Modelo 3: Seedy • Worker IoT & Datos
- **ID**: `seedy-worker-iot-data`
- **Base actual**: `qwen2.5:7b-instruct`
- **Params**: temperature 0.3, top_p 0.9, repeat_penalty 1.1, num_ctx 8192
- **Colecciones**: IoT & Hardware + Digital Twins & IA
- **Misión**: Arquitectura IoT completa. Conoce las 7+1 capas PorciData con precios reales del BOM. Topics MQTT: `neofarm/{farm_id}/{barn_id}/{layer}/{sensor_type}`.

### Modelo 4: Seedy • Worker Digital Twin
- **ID**: `seedy-worker-digital-twin`
- **Base actual**: `qwen2.5:7b-instruct`
- **Params**: temperature 0.3, top_p 0.9, repeat_penalty 1.1, num_ctx 8192
- **Colecciones**: Digital Twins & IA + IoT & Hardware + Nutrición
- **Misión**: Definir twins para ganadería. Twin Porcino (nave/lote/animal, 7 capas IoT → World Model → RL). Twin Vacuno (GPS, NDVI, THI). Geospatial (Cesium 3D + PNOA, EPSG:25830).

### Modelo 5: Seedy • Worker Web/Automation
- **ID**: `seedy-worker-web-automation`
- **Base actual**: `qwen2.5:7b-instruct`
- **Params**: temperature 0.3, top_p 0.9, repeat_penalty 1.1, num_ctx 8192
- **Colecciones**: Estrategia
- **Misión**: Automatizar datos externos. Lonjas (Mercolleida porcino, Segovia vacuno, Ebro cereales), AEMET, Sentinel-2 NDVI, Catastro, PNOA. Preferir APIs; si no, Playwright.

### Modelo 6: Seedy • Worker Coder & Data
- **ID**: `seedy-worker-coder-data`
- **Base actual**: `qwen2.5:7b-instruct`
- **Params**: temperature 0.35, top_p 0.9, repeat_penalty 1.05, num_ctx 8192
- **Colecciones**: IoT & Hardware + Nutrición
- **Misión**: Código producción NeoFarm. Stack: Next.js 14+ App Router + Tailwind + shadcn/ui, FastAPI + PostgreSQL + Alembic, Docker Compose, ESP32 firmware, React Native + Expo + WatermelonDB, Cesium.js.

---

## ARQUITECTURA OBJETIVO (lo que vamos a construir)

```
┌───────────────────────────────────────────────────────────┐
│                      USUARIOS                              │
│  Open WebUI (:3000)     hub.vacasdata.com     App Móvil   │
│  (ganadero/David)       (clientes SaaS)       (React N.)  │
└─────────┬───────────────────┬──────────────────┬──────────┘
          │                   │                  │
          ▼                   ▼                  ▼
┌───────────────────────────────────────────────────────────┐
│            SEEDY BACKEND — FastAPI (:8000)                  │
│                                                            │
│  1. Recibe pregunta                                        │
│  2. Clasificación con Seedy (Together.ai, ~50 tokens)      │
│     → "¿RAG, IOT, TWIN, NUTRITION, GENETICS, GENERAL?"    │
│  3. Query a Qdrant: topK=8 + filtros (colección, granja)  │
│  4. Rerank con bge-reranker-v2-m3 (local) → Top 3         │
│  5. Construye prompt: system + contexto + pregunta         │
│  6. Llama a Together.ai (Seedy fine-tuned) → respuesta    │
│  7. Fallback → Ollama local (seedy:q8) si Together cae    │
└───────┬───────────┬──────────────┬────────────────────────┘
        │           │              │
        ▼           ▼              ▼
┌───────────┐ ┌───────────┐ ┌──────────────────────┐
│  Qdrant   │ │ Together  │ │  Digital Twin Engine  │
│  (:6333)  │ │  .ai API  │ │  InfluxDB (:8086)    │
│  Local    │ │  Seedy FT │ │  Mosquitto (:1883)   │
│  Embeds:  │ │  Qwen 7B  │ │  Node-RED (:1880)    │
│  mxbai    │ │  ~0.25€/m │ │  Grafana (:3001)     │
└───────────┘ └───────────┘ └──────────────────────┘
```

### Decisiones de arquitectura YA tomadas

1. **LLM producción → Together.ai** (Seedy fine-tuned). Coste ~0.25 EUR/mes para 1h/día uso. 24/7 sin depender de GPU local.
2. **LLM fallback → Ollama local** (`seedy:q8`). Para demos offline o si Together cae.
3. **RAG + Embeddings → Local** (mxbai-embed-large en Ollama + Qdrant). Privacidad total, coste 0.
4. **Open WebUI → Mantener** con ChromaDB nativo para interfaz ganadero. Qdrant para backend FastAPI (hub.vacasdata.com, app móvil).
5. **Rerank → Local** (`bge-reranker-v2-m3` via sentence-transformers). Top K=8 → rerank → Top 3.
6. **Digital Twin + IoT → Local**. Cálculos cerca de los datos. LLM solo explica, no calcula.
7. **Clasificación de queries → Seedy como router** (no reglas manuales). Primera llamada corta a Together: "¿Qué categoría?" → luego la llamada real con contexto RAG.

---

## QUÉ CONSTRUIR (por fases)

### FASE 1: Docker Compose unificado
Crear `/home/davidia/seedy/docker-compose.yml` que levante:
- ollama (GPU, `:11434`, volumen `ollama_data` + `/home/davidia/models:/models`)
- open-webui (`:3000`, conectado a ollama)
- qdrant (`:6333`, volumen persistente)
- seedy-backend (FastAPI, `:8000`, acceso a Qdrant + Together.ai + Ollama)
- influxdb (`:8086`)
- mosquitto (`:1883`)
- nodered (`:1880`)
- grafana (`:3001`)

Red: `ai_default`. GPU solo para ollama. Health checks. Restart: `unless-stopped`.
Variables en `.env` (TOGETHER_API_KEY, TOGETHER_MODEL_ID=ft-bc10fc32-2235, etc.)

### FASE 2: Backend FastAPI de Seedy
```
/home/davidia/seedy/backend/
├── main.py
├── config.py                # Settings desde .env
├── routers/
│   ├── chat.py              # POST /chat — endpoint principal
│   └── health.py            # GET /health
├── services/
│   ├── classifier.py        # Clasificación con Seedy vía Together
│   ├── rag.py               # Búsqueda en Qdrant + búsqueda híbrida
│   ├── llm.py               # Together.ai + fallback Ollama
│   ├── embeddings.py        # mxbai-embed-large vía Ollama
│   └── reranker.py          # bge-reranker-v2-m3 local
├── models/
│   ├── schemas.py           # Pydantic
│   └── prompts.py           # System prompts de los 6 modelos
├── ingestion/
│   ├── ingest.py            # Indexar docs en Qdrant
│   └── chunker.py           # 1500 chars, 300 overlap
├── tests/
│   ├── test_rag.py          # Los 4 tests de diagnóstico
│   └── test_classifier.py
├── Dockerfile
└── requirements.txt
```

Flujo del endpoint POST /chat:
1. Clasificar query (Together, max_tokens=10, temperature=0)
2. Mapear categoría → colecciones Qdrant
3. Buscar Top K=8 (búsqueda híbrida: dense + BM25 weight 0.7)
4. Rerank → Top 3
5. Construir prompt (system prompt del worker + contexto + pregunta)
6. Llamar Together.ai (fallback: Ollama seedy:q8)
7. Devolver respuesta + sources + categoría

### FASE 3: Ingestión Qdrant
Copiar los documentos de las 6 colecciones de Open WebUI a `/home/davidia/seedy/knowledge/`.
Script `ingest.py` que:
1. Lee .md, .pdf, .docx
2. Chunk 1500/300
3. Embeddings via mxbai-embed-large (Ollama `:11434`)
4. Upsert en Qdrant con metadata (collection, source_file, chunk_index, document_type)

### FASE 4: Digital Twin endpoints
Conectar InfluxDB al backend. Cuando clasificador → TWIN:
1. Query InfluxDB últimas 24h de la nave
2. Calcular KPIs (T media, HR, NH3 max, consumo agua)
3. Detectar anomalías (CUSUM/STL)
4. Pasar resultado como contexto al LLM para que explique

### FASE 5: Tailscale + NAS + Backup
- Servicios accesibles via Tailscale IP
- Backup semanal a NAS: volúmenes Docker, GGUF, knowledge docs
- Script init.sh post-compose: crear seedy:q8, pull embeddings, indexar Qdrant, tests

---

## REGLAS PARA COPILOT

- **Python 3.11+**, **FastAPI** con async/await
- **httpx** para llamadas HTTP async (Together, Ollama)
- **qdrant-client** para Qdrant
- **sentence-transformers** para reranker
- Docker Compose 3.8+
- Type hints estrictos, Pydantic models
- Todos los archivos en `/home/davidia/seedy/`
- Los system prompts de los 6 modelos son los de arriba — NO inventar otros
- Los parámetros RAG son los de arriba (chunk 1500/300, Top K 8, hybrid ON, BM25 0.7) — NO cambiar
- El fine-tune ya está hecho. El modelo se usa vía API Together, NO hay que reentrenarlo
- Priorizar que funcione end-to-end. Optimizar después
- Responder siempre en español cuando sea documentación/comentarios para el usuario
