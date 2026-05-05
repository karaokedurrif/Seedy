# 🌱 Seedy — IA Técnica para NeoFarm

**Seedy** es el sistema de inteligencia artificial multi-agente para ganadería de precisión (porcino, vacuno, avicultura extensiva) que asiste a la plataforma [NeoFarm](https://hub.ovosfera.com). Arquitectura híbrida Ollama + Together.ai con RAG, visión por computadora, ML adaptativo y gemelo digital.

> **v4.6** (mayo 2026) — LLMRouter híbrido (13 policies, -30% coste), Celery workers automatizados, RAG contextual fix, visión dual-stream v4.2, identity subsystem, behavior ML 7D

🔗 **Producción:** [seedy.neofarm.io](https://seedy.neofarm.io) | **API:** [seedy-api.neofarm.io](https://seedy-api.neofarm.io) | **Grafana:** [seedy-grafana.neofarm.io](https://seedy-grafana.neofarm.io)

---

## 🎯 Características v4.6

### LLMRouter Híbrido (-30% coste)
- **Ollama local** (GPU RTX 5080): qwen2.5:7b/72b, seedy:v16, mxbai-embed-large
- **Together.ai cloud**: Kimi-K2.5, DeepSeek-R1, Qwen3-235B
- **13 policies** con fallback automático (rewriter, classifiers, generation, batch)
- **Ahorro:** $10→$7/mes por 80 queries (solo pasos pequeños a local)

### Celery Workers Automatizados
- **behavior_7d_analysis**: Análisis ML 7 días por ave (rutinas, anomalías, jerarquía PageRank) — Monday 3 AM
- **mating_confirmation**: Confirmación batch eventos de monta — every 6h
- **weekly_report**: Informe ejecutivo semanal — Sunday 8 PM

### RAG Contextual Fix
- Smart truncate preserva referencias numéricas en historial conversacional
- Queries multi-turno 100% deterministas ("háblame del punto 9" → encuentra contexto automáticamente)
- 11 colecciones Qdrant (~173K chunks): IoT, Nutrición, Genética, Estrategia, Twins, Normativa, Avicultura, BIM, Renders, Science Articles, Prospectiva

### Visión v4.2 — Dual Stream + Identity Subsystem
- **YOLO COCO v8s** (detector: bird+dog+cat conf 0.20) + **YOLO Breed v3** (clasificador: 20 clases)
- **Dual stream:** sub-stream 15fps tracking continuo + main-stream 4K event-triggered
- **Curación DUAL:** Track A (crops → clasificación breed) + Track B (frames anotados → entrenar detector)
- **Identity subsystem:** IdentityLock + VotingBuffer + AssignmentRegistry + DoubtEscalator (breed+sex+color matching)
- **Tracker:** centroide+IoU 120 frames, mating detection, behavior features 30+
- **Gemini 2.5 Flash** para identificación primaria

### Behavior ML Adaptativo
- **Individual:** GMM rutinas espaciales, IsolationForest anomalías, predictor de puesta
- **Flock:** Perfil circadiano, PageRank dominancia, anomalía de grupo
- **Entrenamiento:** cada 6h automático, ventana 14 días

### IoT + GeoTwin
- **Zigbee2MQTT:** 7 sensores (temp, humedad, CO2, VOC, formaldehído) + Ecowitt GW2000A meteo
- **Flujo:** MQTT → InfluxDB → Grafana + OvoSfera pilot
- **GeoTwin:** Cesium 3D + PNOA + DEM (40.91541°N, -4.06827°E)

---

## 📋 Estructura del repositorio

| Carpeta/Archivo | Descripción |
|---|---|
| `backend/` | FastAPI GPU (25+ routers, services, workers) |
| `backend/services/llm_router/` | **v4.6** — Arquitectura híbrida Ollama + Together.ai |
| `backend/workers/` | **v4.6** — Celery workers (behavior, mating, reports) |
| `backend/services/identity/` | **v4.2** — IdentityLock, VotingBuffer, AssignmentRegistry, DoubtEscalator |
| `genetics/` | Motor genético BLUP/GBLUP |
| `conocimientos/` | 11 colecciones RAG (IoT, Nutrición, Genética, etc.) |
| `data/curated_crops/` | **v4.1** — Dataset crops breed classifier |
| `data/curated_frames/` | **v4.1** — Dataset frames anotados para detector |
| `docs/` | Documentación deployment, LLM routing, dashboards Grafana |
| `scripts/` | Deploy, backup, monitoring |
| `seedy_dataset_sft_v6.jsonl` | Dataset fine-tune (302 ejemplos) |
| `.github/agents/ia-expert.agent.md` | **v4.6** — Instrucciones completas Copilot |

---

## 🧠 Dominios de conocimiento (11 colecciones)

1. **IoT**: BOM sensores ESP32, Zigbee, firmware, telemetría MQTT
2. **Nutrición**: Formulación piensos, NRC 2012, enzimas, lonjas
3. **Genética**: BLUP/GBLUP, consanguinidad Wright, EPDs, razas autóctonas
4. **Estrategia**: Posicionamiento, análisis competitivo
5. **Digital Twins**: BIM-lite, plano 2D, gemelo digital
6. **Normativa**: RD 306/2020, ECOGAN, RD 1135/2002, bienestar animal
7. **Avicultura**: Manejo gallinas, ponedoras, producción huevos
8. **BIM**: Renders, modelos 3D
9. **Renders**: FLUX.1.1 Pro generación imágenes
10. **Science Articles**: Papers científicos ganadería
11. **Prospectiva**: Trends, predicciones sector

---

## 🔧 Fine-tune

- **Plataforma**: Together.ai
- **Modelo base**: Qwen2.5-7B-Instruct
- **Tipo**: LoRA (r=16, alpha=32)
- **Dataset**: seedy_dataset_sft_v6.jsonl (302 ejemplos)
- **Modelo desplegado**: `seedy:v16` en Ollama (9 GB GGUF Q4_K_M)
- **Uso:** Critic gate, modos `/local` y `/eco`, fallback generation

---

## 🏗️ Stack desplegado (17 contenedores Docker)

### Core
- **ollama** (:11434) — LLM GPU (seedy:v16, qwen2.5:7b/72b, mxbai-embed-large)
- **open-webui** (:3000) — Interfaz ganadero (custom 0.8.8-local, 6 workers Seedy)
- **seedy-backend** (:8000) — FastAPI GPU (25+ routers, async/await)
- **qdrant** (:6333) — Vector store (11 colecciones, ~173K chunks)

### Vision
- **go2rtc** (host network) — RTSP proxy 3 cámaras → WebRTC/MJPEG (dual stream config)

### LLM v4.6
- **redis** (:6379) — Cola tareas Celery (broker + backend, maxmemory 512MB)
- **celery-worker** — Worker async GPU (behavior, mating, reports)
- **celery-beat** — Scheduler cron (Monday 3AM, every 6h, Sunday 8PM)

### IoT
- **influxdb** (:8086) — Series temporales (org=neofarm, bucket=porcidata)
- **mosquitto** (:1883) — MQTT broker
- **nodered** (:1880) — Flujos IoT
- **grafana** (:3001) — Dashboards + métricas LLMRouter v4.6

### Utilidades
- **searxng** (:8888) — Meta-buscador web para RAG dinámico
- **crawl4ai** (:11235) — Extractor contenido web
- **edge-tts** (:8100) — Síntesis de voz
- **cloudflared** — Tunnel "homeserver" (ID 60b6373e, QUIC, 4 conn Madrid)
- **caddy-local** (:443) — TLS local (certs mkcert), split-horizon

### Gestión
- **portainer** (:9000) — Gestión Docker web

---

## 🖥️ Hardware

| Elemento | Detalle |
|---|---|
| **Host principal** | MSI Vector 16 HX — RTX 5080 16 GB VRAM, 64 GB RAM, Ubuntu 24.04 |
| **GPU** | NVIDIA RTX 5080, runtime nvidia, 100% offload |
| **NAS** | smb://192.168.30.100/datos/ — backup rsync cada 6h (OMV) |
| **Cámaras** | Dahua IPC 4K + 2× TP-Link VIGI → go2rtc (dual stream) |
| **Zigbee gateway** | Mini PC 192.168.40.128 (Zigbee2MQTT v2.9.2, CH340/CC2652 dongle, canal 15) |
| **Sensores Zigbee** | 2× eWeLink temp+humedad + 2× Tuya calidad aire (CO2, VOC, formaldehído) |
| **Meteo** | Ecowitt GW2000A (WiFi, API v3) — temp, humedad, viento, presión, lluvia, UV, radiación |

---

## 📐 Arquitectura v4.6

```
Usuario (Open WebUI / OvoSfera / API)
    ↓
Backend FastAPI → LLMRouter v4.6 (Ollama/Together.ai híbrido)
    ↓
Query Rewriter → Classifier → RAG Qdrant (dense + BM25)
    ↓
Web Search (SearXNG) → Reranker (bge-reranker-v2-m3) → LLM Generation
    ↓
Critic Gate (seedy:v16) → Response

Paralelo:
- Vision Pipeline: Cámaras → go2rtc → YOLO → Tracker → Identity → Behavior ML
- IoT Pipeline: Zigbee/MQTT → Node-RED → InfluxDB → Grafana
- Celery Workers: Redis queue → behavior_7d / mating / weekly_report
- GeoTwin: Cesium 3D + PNOA + DEM
```

---

## 📊 Métricas v4.6

| Métrica | Valor |
|---|---|
| **Coste mensual LLM** | ~$40 (80 queries/mes, -30% vs v4.5) |
| **Latencia rewriter** | 0.36-0.59s (Ollama local, -80% vs Together.ai) |
| **Latencia classifiers** | <0.3s (Ollama local, -70%) |
| **RAG chunks** | 173K en 11 colecciones |
| **Vision frames procesados** | ~2M/mes (3 cámaras, dual stream) |
| **Identity Re-ID coverage** | 30% (7-8/25 aves, v4.2) |
| **Behavior ML training** | Cada 6h automático |
| **IoT sensors** | 8 devices (7 Zigbee + 1 Ecowitt meteo) |
| **Docker containers** | 17 operacionales |
| **GPU utilization** | 95% (Ollama 81/81 capas en CUDA0) |

---

## 🚀 Deployment

### Cloudflare Tunnel (producción)
- `seedy.neofarm.io` → Open WebUI :3000
- `seedy-api.neofarm.io` → FastAPI :8000 (+ inject.js)
- `seedy-grafana.neofarm.io` → Grafana :3001

### Local (desarrollo)
```bash
docker compose up -d
curl localhost:8000/health
```

### Health checks
```bash
# Backend
curl localhost:8000/health | python -m json.tool

# Ollama
docker exec ollama ollama list

# Qdrant collections
curl localhost:6333/collections | jq '.result.collections[].name'

# Celery workers
docker compose logs celery-worker | grep 'ready'
```

---

## 📝 Documentación

- **ia-expert agent**: `.github/agents/ia-expert.agent.md` — Instrucciones completas v4.6
- **Deployment**: `docs/DEPLOYMENT_v4.6_SUMMARY.md`
- **LLM Routing**: `docs/llm_routing.md`
- **Grafana dashboard**: `docs/grafana_seedy_pipeline_v46.json`
- **Master roadmap**: `conocimientos/SEEDY_MASTER_ROADMAP_2026.md`

---

## 🤝 Contribuir

Proyecto privado NeoFarm. Para acceso, contactar: david@neofarm.io

---

## 📄 Licencia

Proyecto privado — NeoFarm / OvoSfera © 2024-2026
