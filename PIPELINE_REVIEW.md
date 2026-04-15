# Seedy — Revisión Completa del Pipeline (15 Abr 2026)

## Arquitectura General

Sistema de IA para ganadería de precisión (NeoFarm). **26 contenedores Docker** organizados en:

| Componente | Tech Stack | Función |
|---|---|---|
| **Seedy Backend** | FastAPI + RTX 5080 | Orquestador central: RAG, visión, IoT |
| **Ollama** | seedy:v16 (Qwen2.5-14B LoRA Q4_K_M) | LLM local fine-tuned + embeddings (mxbai-embed-large) |
| **Together.ai** | Kimi-K2.5 / DeepSeek-R1 / Qwen3-235B | LLM cloud principal / informes / critic |
| **Qdrant** | 11 colecciones, 222K+ chunks | Vector store híbrido (dense + BM25 sparse) |
| **Open WebUI** | v0.8.12 | Interfaz usuario, expone modelo "seedy-rag" |
| **SearXNG** | Metabuscador | Búsqueda web complementaria |
| **Crawl4AI** | Crawler JS | Extracción texto completo de URLs |
| **IoT Stack** | Mosquitto + InfluxDB + Grafana + Node-RED | Telemetría Zigbee (sensores gallineros) |
| **go2rtc** | Proxy RTSP | H.265→H.264 transcoding para 3 cámaras 4K |
| **Cloudflared** | Tunnel público | Acceso externo seguro |

---

## Pipeline de Chat (flujo principal)

```
Usuario → Open WebUI → /v1/chat/completions (OpenAI compat)
                                    ↓
                          1. classify_query_multi()        ← Together.ai (Qwen 7B, ~10 tokens)
                             Multi-label: hasta 3 categorías con peso
                                    ↓
                          2. _merge_collections()           ← Fusiona colecciones Qdrant sin duplicados
                                    ↓
                          3. rewrite_query()                ← Together.ai (reformula con historial)
                                    ↓
                          4. rag_search()                   ← Qdrant: dual-query (reescrita + original)
                             Dense (mxbai-embed-large) + Sparse BM25 + RRF fusion
                             + metadata_filter (especie, documento, fuentes ruidosas)
                                    ↓
                          5. rerank()                       ← bge-reranker-v2-m3 (CrossEncoder local, GPU)
                             Diversificación: max 2 chunks/doc
                             Penalización idioma: EN -30% si query ES
                                    ↓
                          6. evidence.extract_evidence()    ← Together.ai (Qwen 7B): deduplica + extrae hechos
                                    ↓
                          7. generate()                     ← Together.ai (Kimi-K2.5) → fallback Ollama (seedy:v16)
                                    ↓
                          8. critic.evaluate_response()     ← Together.ai (Qwen3-235B): PASS/BLOCK
                                    ↓
                          9. postprocess.clean_markdown()   ← Limpia formato
                                    ↓
                          Respuesta → Open WebUI → Usuario
```

### Detalle de cada etapa

**1. Clasificación multi-label** (`services/classifier.py`)
- Usa Together.ai (Qwen2.5-7B-Instruct-Turbo) para clasificar la query
- Devuelve hasta 3 categorías con peso (ej: `AVICULTURA:0.85, NUTRITION:0.70`)
- Cache LRU con TTL de 10 min (256 entradas)
- Hint de categoría previa para coherencia conversacional
- Fallback: `GENERAL` si falla Together.ai

**2. Merge colecciones** (`routers/chat.py`)
- Fusiona colecciones de todas las categorías sin duplicados
- Preserva orden de prioridad (categoría con mayor peso primero)
- Mapeo en `CATEGORY_COLLECTIONS` (models/prompts.py)

**3. Query rewriter** (`services/query_rewriter.py`)
- Reformula la query incorporando contexto de los últimos 4 mensajes del historial
- Ejemplo: "y cómo la ves para capón gourmet?" → "Sulmtaler gallina para capón gourmet cruces"
- Solo actúa si hay historial ≥ 2 mensajes
- Fallback: devuelve query original

**4. RAG search** (`services/rag.py`)
- Búsqueda híbrida en Qdrant:
  - Dense: embedding vía mxbai-embed-large (1024d)
  - Sparse: BM25 con peso configurable (`rag_bm25_weight: 1.0`)
- Dual-query: busca con query reescrita + query original (si difieren)
- Fusión RRF (Reciprocal Rank Fusion, k=60)
- `rag_top_k: 30` resultados antes de rerank
- Metadata filter (`services/metadata_filter.py`): filtra por especie detectada (aviar/porcino/bovino), excluye fuentes ruidosas (CSVs)

**5. Reranker** (`services/reranker.py`)
- CrossEncoder local: `BAAI/bge-reranker-v2-m3` (max_length=512)
- Diversificación: max 2 chunks por documento fuente
- Penalización idioma: chunks EN reciben -30% score si query es ES
- `rag_rerank_top_n: 8` chunks finales

**6. Evidence builder** (`services/evidence.py`)
- Deduplicación fuzzy (>75% similitud → conserva mayor score)
- Extracción de hechos con Together.ai (Qwen 7B): reduce 8 chunks a ~20 hechos citados
- Formato: `[F1] La raza Dorking pesa 4-5 kg y tiene 5 dedos.`
- Resultado: 1/3 del contexto con 3× más señal

**7. Generación LLM** (`services/llm.py`)
- Principal: Together.ai → Kimi-K2.5 (MoE, 262k ctx)
  - Necesita mín 4096 max_tokens para reasoning interno
  - Retry si finish_reason=length
- Fallback: Ollama local → seedy:v16 (Qwen2.5-14B LoRA)
- Para informes: DeepSeek-R1 (máximo razonamiento) con limpieza de `<think>...</think>`
- System prompt dinámico según categoría (`models/prompts.py`)

**8. Critic gate** (`services/critic.py`)
- Together.ai (Qwen3-235B) como juez independiente
- Veredicto binario: PASS o BLOCK
- Solo bloquea por: confusión de especie, item no-animal como raza, respuesta incoherente
- Frases de admisión honesta → PASS directo (sin evaluar)
- Si BLOCK: respuesta sustituida por fallback seguro

**9. Postprocesado** (`services/postprocess.py`)
- Elimina markdown (###, **, *, ~~, ```)
- Convierte headers a MAYÚSCULAS
- Normaliza bullets a guiones numerados
- Limpia artefactos de generación

---

## Pipeline de Ingesta (3 vías paralelas)

### A. Daily Update (backend, cada 24h)

**Archivo:** `services/daily_update.py` (592 líneas)

```
WATCHLIST de queries por vertical (avicultura, porcino, bovino, normativa, genetica, iot, papers)
     ↓
SearXNG búsqueda → resultados con URL + snippet
     ↓
Source Authority scoring (0.1-1.0 por dominio)
     ↓
Deep crawl con Crawl4AI (solo si authority ≥ 0.7)
     ↓
Chunker (1500 chars, 300 overlap) + Quality Gate
     ↓
Embed vía Ollama (mxbai-embed-large)
     ↓
Qdrant → colección fresh_web
```

- Ejecuta 5 min tras arranque, luego cada 24h
- Source Authority: BOE/EFSA/FAO=1.0, INIA/PubMed=0.9, 3tres3=0.7, blogs=0.5, marketing=0.3
- Quality Gate (`services/quality_gate.py`): detecta idioma, filtra contenido corto/ruidoso/duplicado

### B. Knowledge Agent (backend, cada 4-12h)

**Archivo:** `services/knowledge_agent.py` (577 líneas)

```
Gap detection en colecciones Qdrant
     ↓
Targeted search (SearXNG) con queries específicas para gaps
     ↓
Promote from fresh_web → colecciones temáticas
     ↓
Quality audit de chunks existentes
```

- Detecta temas débiles (pocas fuentes, baja diversidad)
- Promueve chunks de `fresh_web` a colección temática si authority ≥ 0.6
- Máx 15-25 queries por ejecución

### C. Pipeline de Autoingesta (pipelines/ingest/, cron)

**Directorio:** `pipelines/ingest/` (11 módulos)

```
sources.yaml (RSS + URLs verificadas)
     ↓
fetch.py → descarga RSS feeds y páginas web
     ↓
dedup.py → filtra URLs ya procesadas (SQLite state_db)
     ↓
parse.py → extrae texto limpio (trafilatura + pymupdf)
     ↓
score.py → scoring fiabilidad (0-60) + relevancia por keywords (0-40)
     ↓
chunk.py → segmenta texto + compute_sparse_vector (BM25)
     ↓
embed.py → embeddings vía Ollama
     ↓
qdrant_index.py → indexa en colección temática directa
     ↓
daily_brief.py → genera resumen diario
```

- Fuentes: BOE, Agropopular, AgronewsCastilla, Feagas, Porcinews, MAPA, 3tres3, Avicultura.com, Vinetur...
- Cron: lunes 03:00 science, mié/sáb 04:00 agro, diario 06:00 ingest
- Scoring: reliability de fuente (YAML) + keyword match por dominio
- Mapeo a 8 colecciones Qdrant (avicultura, genetica, nutricion, normativa, iot_hardware, digital_twins, estrategia, bodegas_vino)

---

## Pipeline de Visión (YOLO)

**Módulos principales:** `services/yolo_detector.py` (818 líneas), `routers/vision_identify.py` (3540 líneas)

```
Cámaras 4K (2× TP-Link VIGI + 1× Dahua WizSense)
     ↓
go2rtc (RTSP proxy, H.265→H.264 transcoding)
     ↓
Capture Manager (services/capture_manager.py)
├── Sub-stream: continuo, procesa 1 de cada N frames
└── Main-stream: 4K event-driven (triggered por detección)
     ↓
YOLO COCO (yolov8s.pt) — detector primario
├── Tiled detection (tiles 960-1280px por cámara)
├── Clases: bird, cat, dog (conf=0.20)
└── Artifact filter: >45% tile-artifact, noise, border, aspect ratio
     ↓
Breed classifier (seedy_breeds_best.pt) — en cada crop
├── task=detect (boxes, NO probs)
├── 14 clases: vorwerk ♀♂, sussex ♀♂, sulmtaler ♀♂, marans ♀, bresse ♀♂, etc.
├── Crop padding: 15% + grey border
└── BREED_MIN_CONF=0.20
     ↓
Bird tracker (services/bird_tracker.py)
├── Centroid + IoU matching entre frames consecutivos
├── Zone occupancy (comedero, bebedero, nido, aseladero, zona_libre)
├── Activity level + anomalías (inmovilidad, aislamiento, hiperactividad)
└── Multi-object tracker por gallinero
     ↓
Behavior ML (services/behavior_ml.py, 705 líneas)
├── GMM routines (Gaussian Mixture Models)
├── IsolationForest anomalías
├── PageRank hierarchy (dominancia social)
└── Entrena cada 6h con datos de 14 días
     ↓
Pest alert (services/pest_alert.py)
├── Debouncing 60s, escalation 3+ frames
├── MQTT → seedy/vision/alerts/pest/{gallinero}
└── Node-RED suscrito
     ↓
Visual Re-ID (services/together_vision.py)
├── Contact sheet del gallery (/app/data/bird_gallery/)
├── Qwen2.5-VL-72B compara crop vs contact sheet
└── POST /auto-identify, POST /smart-match
```

### Crop Curator (`services/crop_curator.py`)
- Dual-track: crops para breed training + annotated frames para detection training
- POST /vision/curated/curate-frame/{camera_id}

### Health Analyzer (`services/health_analyzer.py`)
- `HealthScore`: mobility, feeding, social, zone_balance → overall (0-100)
- Growth tracker: curvas de crecimiento, comparación entre aves

---

## Pipeline de Auto-Aprendizaje (5 loops)

**Orquestador:** `services/auto_learn.py` (562 líneas)

| Loop | Intervalo | Trigger | Acción |
|---|---|---|---|
| YOLO retrain | 6h | ≥100 frames nuevos | `yolo_trainer.train_model()` + hot-reload breed model |
| DPO snapshot | 24h | ≥20 pares nuevos | Snapshot fechado + `training_config.json` para TRL DPOTrainer |
| Vision stats | 24h | Siempre | Conteo imágenes/pares en vision_dataset/, log progreso |
| Knowledge Agent | 4-12h | Siempre | Gap detection → targeted search → promote from fresh_web |
| Reporting Agent | 24h | Siempre | Lee chats Open WebUI + critic_log → mejoras + email |

---

## Pipeline de Informes

**Archivo:** `services/reporting_agent.py` (1320 líneas)

```
Trigger: cada 24h o POST /report/generate
     ↓
Lee webui.db (Open WebUI SQLite) → chats últimas 24h
Lee critic_log.jsonl → bloqueos y sus motivos
Lee knowledge_reports/ → resultados del Knowledge Agent
     ↓
Análisis: patrones conversacionales, queries recurrentes, bloqueos, gaps RAG
     ↓
Genera queries para Knowledge Agent (cierre de gaps detectados)
Propone nuevos SFT examples de queries frecuentes
     ↓
Generación informe: DeepSeek-R1 (máximo razonamiento)
├── _build_report_context(): 18000 chars
├── _decompose_report_requirements(): keyword→checklist
├── _check_report_quality(): lightweight critic (regenera si pobre)
├── max_tokens=8192, repetition_penalty=1.0
└── Source attribution by doc name
     ↓
Markdown → WeasyPrint PDF (routers/report.py, NeoFarm branding CSS)
     ↓
Email HTML al admin (SMTP Gmail)
```

---

## Módulos adicionales

### OvoSfera Bridge (`routers/ovosfera_bridge.py`, 606 líneas)
- Proxy API entre Seedy Backend y hub.ovosfera.com
- Gestión de aves, gallineros, compras, ventas, lotes
- Zigbee data: WebSocket seed + MQTT listener para sensores en vivo
- Ecowitt weather station: async httpx + 60s cache
- Endpoints: `/ovosfera/devices`, `/ovosfera/devices/status`

### OpenAI Compatibility Layer (`routers/openai_compat.py`, 1407 líneas)
- Emula API OpenAI (`/v1/chat/completions`, `/v1/models`)
- Open WebUI lo usa como si fuera un modelo más
- Streaming SSE integrado

### Web Search Fallback (`services/web_search.py`)
- SearXNG cuando RAG score < 0.012
- Detección de intención comercial/producto → búsqueda web obligatoria
- Regex de 20+ patrones comerciales (comprar, precio, tienda, proveedor...)

### Temporality Classifier (`services/temporality.py`)
- 4 niveles: STABLE, SEMI_DYNAMIC, DYNAMIC, BREAKING
- Determina si forzar búsqueda web aunque Qdrant tenga resultados
- BREAKING: brotes sanitarios, alertas, restricciones urgentes

### Sparrow Deterrent (`services/sparrow_deterrent.py`, 311 líneas)
- Sistema de disuasión de gorriones basado en detecciones YOLO

### Mating Detector (`services/mating_detector.py`, 409 líneas)
- Detección de comportamiento de apareamiento por análisis de frames

### Merit Index (`services/merit_index.py`)
- Índice de mérito genético para aves

---

## Configuración RAG

| Parámetro | Valor | Descripción |
|---|---|---|
| `rag_top_k` | 30 | Resultados de retrieval antes de rerank |
| `rag_rerank_top_n` | 8 | Chunks finales tras diversificación |
| `rag_bm25_weight` | 1.0 | Peso del BM25 en fusión RRF |
| `rag_chunk_size` | 800 | Tamaño de chunk (config base) |
| `rag_chunk_overlap` | 150 | Overlap entre chunks |
| `rag_relevance_threshold` | 0.25 | Umbral mínimo de relevancia |
| Embed model | mxbai-embed-large | 1024 dimensiones |
| Reranker | bge-reranker-v2-m3 | max_length=512 |

### Colecciones Qdrant (11)

| Colección | Contenido |
|---|---|
| `avicultura` | Avicultura extensiva, capones, razas autóctonas |
| `avicultura_intensiva` | Broilers, integradoras, naves industriales |
| `bodegas_vino` | Viticultura, enología, DO |
| `genetica` | Mejora genética, BLUP, consanguinidad |
| `nutricion` | Formulación piensos, raciones, aminoácidos |
| `normativa` | BOE, EFSA, regulación bienestar animal |
| `iot_hardware` | Sensores, MQTT, precision farming |
| `digital_twins` | Gemelos digitales, GIS, CDA |
| `estrategia` | Mercado, competencia, tendencias |
| `geotwin` | GeoTwin, Cesium 3D, PNOA, DEM |
| `fresh_web` | Contenido web fresco (staging) |

---

## Modelos LLM usados

| Modelo | Rol | Provider |
|---|---|---|
| Kimi-K2.5 | Chat principal (MoE, 262k ctx) | Together.ai |
| DeepSeek-R1-0528 | Informes ejecutivos (max razonamiento) | Together.ai |
| Qwen3-235B-A22B | Critic gate | Together.ai |
| Qwen2.5-7B-Instruct-Turbo | Clasificador + evidence extractor | Together.ai |
| Qwen2.5-VL-72B-Instruct | Visión (re-ID aves) | Together.ai |
| seedy:v16 | Fallback local (Qwen2.5-14B LoRA Q4_K_M) | Ollama |
| mxbai-embed-large | Embeddings (1024d) | Ollama |
| bge-reranker-v2-m3 | Reranking (CrossEncoder) | Local GPU |
| yolov8s.pt | Detector COCO primario | Local GPU |
| seedy_breeds_best.pt | Clasificador de razas (14 clases) | Local GPU |

---

## Propuestas de Mejora

### Alta prioridad (impacto rápido)

#### 1. Eliminar `warnings.filterwarnings("ignore")` en rag.py
- **Archivo:** `services/rag.py` línea 14
- **Problema:** Suprime el warning de versión qdrant-client que ya está corregido (actualizado a 1.17.x)
- **Acción:** Eliminar la línea. Es un anti-pattern ocultar warnings.

#### 2. Async batch embeddings
- **Archivo:** `services/embeddings.py`
- **Problema:** `embed_texts()` hace llamadas secuenciales a Ollama (1 texto por request HTTP)
- **Impacto:** La ingesta de 100 chunks tarda 100 requests en vez de 1
- **Acción:** Usar batch nativo de `/api/embed` con lista de inputs. Aceleración 5-10×.

#### 3. httpx.AsyncClient singleton en classifier/temporality/rewriter
- **Archivos:** `services/classifier.py`, `services/temporality.py`, `services/query_rewriter.py`
- **Problema:** Cada llamada a Together.ai crea y destruye un `AsyncClient` (`async with httpx.AsyncClient()`)
- **Impacto:** ~50ms extra por TLS handshake en cada request
- **Acción:** Reutilizar un singleton como ya hace `services/embeddings.py`

#### 4. Mapeo porcino→iot_hardware y vacuno→digital_twins inconsistente
- **Archivo:** `pipelines/ingest/qdrant_index.py` línea 19-20
- **Problema:** "porcino" va a `iot_hardware` y "vacuno" a `digital_twins`. Contamina colecciones con contenido no relacionado.
- **Impacto:** Búsquedas de IoT devuelven artículos de porcino. Búsquedas de digital twins devuelven artículos de vacuno.
- **Acción:** Crear colecciones propias `porcino` y `bovino`.

#### 5. vision_identify.py tiene 3540 líneas — God Object
- **Archivo:** `routers/vision_identify.py`
- **Problema:** Un solo archivo con loop de identificación, breed classification, API endpoints, OvoSfera photo capture, visual re-ID...
- **Acción:** Dividir en módulos: `identification_loop.py`, `breed_classifier.py`, `ovosfera_photo.py`, `vision_endpoints.py`

---

### Media prioridad (mejora robustez)

#### 6. Qdrant singleton sin reconexión
- **Archivo:** `services/rag.py`
- **Problema:** `get_qdrant()` crea un singleton sin retry/reconnect. Si Qdrant se reinicia, el cliente queda roto hasta reiniciar el backend.
- **Acción:** Añadir health check simple con reconexión automática.

#### 7. Cache de clasificación no thread-safe
- **Archivo:** `services/classifier.py`
- **Problema:** LRU manual con dict Python puro (no thread-safe). Purga manual de 50 entradas cuando llega a 256.
- **Acción:** Usar `cachetools.TTLCache` con lock, o `functools.lru_cache` con wrapper TTL.

#### 8. fresh_web nunca se limpia
- **Archivos:** `services/daily_update.py`, `services/knowledge_agent.py`
- **Problema:** `daily_update` añade a `fresh_web` continuamente. Knowledge Agent promueve algunos, pero no hay TTL ni limpieza.
- **Impacto:** Acumulación de ruido con el tiempo. fresh_web crece indefinidamente.
- **Acción:** Job de limpieza con TTL de 30 días para chunks en fresh_web no promovidos.

#### 9. Evidence builder con fallback silencioso
- **Archivo:** `services/evidence.py`
- **Problema:** Si Together.ai falla en `extract_evidence()`, los chunks crudos van directos al LLM sin deduplicación.
- **Acción:** Aplicar `deduplicate_chunks()` local aunque falle la extracción de hechos.

#### 10. Reranker compite por VRAM con YOLO y Ollama
- **Archivo:** `services/reranker.py`
- **Problema:** CrossEncoder `bge-reranker-v2-m3` carga en GPU. Compite con YOLO (yolov8s + breed) y Ollama por la RTX 5080 (16GB).
- **Acción:** Forzar reranker a CPU (`device="cpu"`) — es ligero (~500MB) y el batch es pequeño (~20 pares). Libera VRAM para modelos más pesados.

---

### Baja prioridad (arquitectura a medio plazo)

#### 11. Pipeline de ingesta duplicado
- **Archivos:** `services/daily_update.py` (backend) vs `pipelines/ingest/run_daily.py`
- **Problema:** Dos implementaciones distintas del mismo pipeline de ingesta con lógicas diferentes.
- **Acción:** Consolidar en uno solo (preferiblemente `pipelines/ingest/` que es más modular).

#### 12. openai_compat.py tiene 1407 líneas
- **Archivo:** `routers/openai_compat.py`
- **Problema:** La lógica de streaming SSE mezclada con routing y business logic.
- **Acción:** Extraer streaming SSE a un servicio dedicado.

#### 13. Reporting Agent accede directamente a webui.db
- **Archivo:** `services/reporting_agent.py`
- **Problema:** Acceso directo a SQLite de Open WebUI con `sqlite3`. Frágil ante cambios de schema.
- **Acción:** Usar API de Open WebUI o exportar métricas a InfluxDB vía middleware.

#### 14. Sin tests automatizados significativos
- **Directorio:** `backend/tests/`
- **Problema:** ~14k líneas de servicios y 9.4k de routers sin CI. Cambios en rag.py o classifier.py pueden romper el chat sin detectarse.
- **Acción:** Tests de integración mínimos para flujos críticos: chat E2E, ingesta → Qdrant, visión → detección.

#### 15. Streaming bypasea el critic gate
- **Archivo:** `routers/chat.py` (chat_stream), `routers/openai_compat.py`
- **Problema:** `/chat/stream` genera tokens vía SSE directo. El critic solo se aplica en `/chat` síncrono. Open WebUI usa streaming por defecto → **todas las queries de producción bypasean el control de calidad**.
- **Impacto:** El critic gate (la protección contra confusión de especie, incoherencia, etc.) no actúa en el flujo real de usuarios.
- **Acción:** Implementar critic post-stream (acumular respuesta completa, evaluar, y si BLOCK sustituir en el último chunk SSE) o pre-flight check de la query.
