# Seedy — Handoff Summary

> Documento de transferencia de conocimiento. Estado: **31 marzo 2026**.

---

## 1. Qué es Seedy

**Seedy** es una plataforma de inteligencia artificial para ganadería extensiva desarrollada por **NeoFarm**. Combina:

- **Chat RAG** con LLM fine-tuned (Ollama local + Together.ai cloud)
- **Visión por computador** (YOLO local + Gemini 2.5 Flash)
- **Simulación genética** (BLUP/GBLUP, predicción F1-F5, cruces óptimos)
- **Gemelo digital 3D** (BIM-lite, plano 2D, reconocimiento fotográfico)
- **Control de drones** (Parrot Bebop 2, disuasión autónoma de gorriones)
- **IoT/telemetría** (MQTT → InfluxDB → Grafana)
- **Ingesta de conocimiento** (RSS, SearXNG, crawl4ai, 625+ artículos científicos)

El backend es **FastAPI** sobre Docker con GPU NVIDIA (RTX 5080), servido públicamente por Cloudflare Tunnel en `seedy-api.neofarm.io`.

---

## 2. El Piloto: Gallinero del Palacio (Segovia)

Seedy se valida en **"El Gallinero del Palacio"**, una explotación avícola de razas heritage en Segovia:

| Dato | Valor |
|------|-------|
| Ubicación | Segovia, España |
| Gallineros | 2 naves (gallinero_durrif_1, gallinero_durrif_2) |
| Aves registradas | **77 aves** identificadas por IA |
| Razas | Sussex White (19), Vorwerk (11), Bresse (10), Sulmtaler (7), Marans (7), Pita Pinta (6), Araucana (5), Castellana Negra (4), y otras |
| Cámaras | Dahua IP (10.10.10.x), 4K, proxy vía go2rtc |
| Producto | Huevos heritage, capones, venta directa |
| Identificador | `PAL-2026-XXXX` (ej: PAL-2026-0077) |

### Flujo de identificación de aves

```
Cámara Dahua (4K RTSP)
  → go2rtc (WebRTC/MJPEG proxy)
    → YOLO v3 local (14 clases, RTX 5080)
      → Crop del ave detectada
        → Gemini 2.5 Flash (identificación de raza + JSON estructurado)
          → Registro en birds_registry.json
```

Cada ave recibe un ID único, foto de referencia, raza, color, sexo, y puntuación de confianza. El censo se valida contra las razas declaradas en el gallinero.

---

## 3. Arquitectura de Contenedores (Docker Compose)

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Host (MSI, RTX 5080)              │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │  ollama   │  │  qdrant  │  │ go2rtc   │  │ seedy-     │ │
│  │  LLM GPU  │  │  vectors │  │ cámaras  │  │ backend    │ │
│  │  :11434   │  │  :6333   │  │  host-net │  │ FastAPI GPU│ │
│  └──────────┘  └──────────┘  └──────────┘  │  :8000     │ │
│                                             └────────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ open-    │  │ searxng  │  │ crawl4ai │  │ seedy-     │ │
│  │ webui    │  │ búsqueda │  │ crawler  │  │ ingest     │ │
│  │  :3000   │  │  :8888   │  │  :11235  │  │ (batch)    │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ mosquitto│  │ influxdb │  │ nodered  │  │  grafana   │ │
│  │ MQTT     │  │ tsdb     │  │ flujos   │  │  dashboards│ │
│  │ :1883    │  │ :8086    │  │ :1880    │  │  :3001     │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────────┐│
│  │cloudflared│  │ caddy   │  │  edge-tts (síntesis voz)  ││
│  │ tunnel   │  │ local TLS│  │  :8100                    ││
│  └──────────┘  └──────────┘  └────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**16 contenedores** + stack Dify (plataforma de agentes) + Portainer.

---

## 4. Backend: Routers (API)

| Ruta | Función |
|------|---------|
| `/chat` | Chat principal con RAG multi-colección |
| `/v1/chat/completions` | Endpoint OpenAI-compatible (Open WebUI lo usa como "modelo") |
| `/vision/identify` | Captura de cámara → YOLO → Gemini → registro de ave |
| `/vision` | Eventos de visión, alertas MQTT, estimación de peso |
| `/birds` | CRUD del registro de aves (JSON persistido) |
| `/genetics` | Simulación genética: F1 prediction, BLUP, cruces óptimos |
| `/api/bim` | BIM-lite: elementos geométricos del gemelo digital |
| `/api/renders` | Generación de renders vía FLUX.1.1 Pro (Together AI) |
| `/api/birds` (3d) | Pipeline foto → modelo 3D (.glb) vía Tripo3D |
| `/api/dron` | Control del Bebop 2 (status, conectar, vuelo disuasión) |
| `/ovosfera` | Bridge a OvoSfera: mapeo cámaras↔gallineros, proxy visión |
| `/survey` | Encuesta fotográfica + generación de plano SVG |
| `/ingest` | Trigger manual de la pipeline de ingesta de conocimiento |
| `/runtime` | Observabilidad: logs de agente, registro de herramientas |
| `/health` | Health check (Ollama, Qdrant, Together.ai) |

---

## 5. Backend: Servicios Clave

### Visión e IA
- **yolo_detector.py** — YOLO v3 local (14 clases), detección tileada para 4K
- **gemini_vision.py** — Gemini 2.5 Flash para identificación de razas
- **together_vision.py** — Together VL (Qwen 72B), actualmente caído → fallback a Gemini
- **bird_tracker.py** — Seguimiento de aves individuales entre frames
- **flock_census.py** — Censo validado del gallinero
- **pest_alert.py** — Detección de plagas (gorriones) con alertas
- **sparrow_deterrent.py** — Disuasión autónoma de gorriones vía dron

### RAG y LLM
- **classifier.py** — Clasifica consultas → colecciones de conocimiento
- **rag.py** — Búsqueda vectorial Qdrant + BM25 híbrido
- **reranker.py** — Cross-encoder para reordenar resultados
- **llm.py** — Generación con Together.ai + Ollama (streaming)
- **critic.py** — Evaluador de calidad de respuestas (Llama 70B)
- **embeddings.py** — Embeddings vía Ollama mxbai-embed-large
- **web_search.py** — Búsqueda web SearXNG cuando RAG no basta
- **daily_update.py** — Ingesta diaria automática de fuentes configuradas

---

## 6. Base de Conocimiento (conocimientos/)

15+ categorías indexadas en Qdrant, 625+ artículos científicos:

| Colección | Contenido |
|-----------|-----------|
| Prompts & Arquitectura | Diseño de Seedy, pipeline RAG, estructura del repo |
| PorciData IoT | Hardware IoT para porcino |
| Nutrición & Formulación | Alimentación animal, formulación de piensos |
| NeoFarm Genética | Módulos genéticos BLUP, porcino/vacuno |
| Estrategia & Competencia | Economía ganadera, Label Rouge, PEPAC, prospección (DAGU, Vitartis) |
| Digital Twins & IoT | Arquitectura de gemelos digitales |
| Normativa & SIGE | RD306/2020, ECOGAN, RD1135/2002 |
| Avicultura Extensiva | Catálogos Hubbard/SASSO (30+ PDFs), cruces para gourmet, capones |
| GeoTwin & GIS 3D | Datos GIS para el gemelo digital |

---

## 7. Integración con OvoSfera

Seedy se integra en **OvoSfera** (hub.ovosfera.com) mediante inyección de JavaScript:

- `ovosfera-inject.js` (3500+ líneas) se carga en el `<head>` de OvoSfera
- Usa MutationObserver para inyectar elementos en el DOM de Next.js
- Añade: cámaras en vivo (MJPEG/MSE), botones YOLO/Seedy/ID, panel de dron, enlace al Site
- Mapeo de gallineros → streams de cámara vía API del backend
- Captura + identificación de aves desde la interfaz de OvoSfera

---

## 8. Hardware de Red

```
Internet ← Cloudflare Tunnel ← MSI (192.168.30.x, RTX 5080)
                                  ├── Cámaras Dahua (10.10.10.x)
                                  ├── NAS OMV (192.168.30.100)
                                  └── Dell Latitude (192.168.20.102)
                                        └── Dongle WiFi Atheros AR9271
                                              └── Parrot Bebop 2 (WiFi directo)
```

- **MSI con RTX 5080**: Host principal, ejecuta Docker, YOLO, Ollama
- **Dell Latitude**: Puente HTTP para el dron Bebop 2 (Olympe SDK)
- **NAS OMV**: Backup rsync cada 6h (192.168.30.100)
- **Dahua IPC**: 2+ cámaras IP en subred 10.10.10.x

---

## 9. Modelos de IA

| Modelo | Uso | Ubicación |
|--------|-----|-----------|
| seedy:v16 | Chat principal fine-tuned | Ollama local (GPU) |
| mxbai-embed-large | Embeddings RAG | Ollama local |
| YOLO v3 Seedy (14 clases) | Detección de aves/plagas | Local (RTX 5080) |
| Gemini 2.5 Flash | Identificación de razas (principal) | Google API |
| Qwen/Qwen2.5-VL-72B | Identificación de razas (backup) | Together.ai (no disponible) |
| Qwen/Qwen2.5-7B-Instruct-Turbo | Chat cloud, clasificación | Together.ai |
| Llama-3.3-70B-Instruct-Turbo | Crítico de respuestas | Together.ai |
| FLUX.1.1 Pro | Generación de renders | Together.ai |
| Tripo3D | Foto → modelo 3D (.glb) | API Tripo |

---

## 10. Datos Persistidos

| Fichero/DB | Contenido |
|------------|-----------|
| `data/birds_registry.json` | 77 aves identificadas con fotos y metadatos |
| `data/bird_photos/PAL-2026-*.jpg` | Fotos de referencia de cada ave |
| `data/ingest_state.db` | SQLite con estado de ingesta |
| `data/critic_log.jsonl` | Log del crítico de respuestas |
| `science_articles/` | 625+ artículos científicos descargados |
| `conocimientos/` | 15+ carpetas de documentos de knowledge base |
| `briefs/` | 28 briefings diarios operacionales (marzo 2026) |
| Qdrant (Docker volume) | Colecciones vectoriales de RAG |
| InfluxDB (Docker volume) | Telemetría IoT histórica |

---

## 11. Estado Actual del Desarrollo

### Completado (marzo 2026)
- RAG multi-colección con 6+ colecciones Qdrant
- Pipeline de visión completa: YOLO → Gemini → registro
- 77 aves identificadas en 2 gallineros
- Gemelo digital 3D + plano 2D
- Interfaz OvoSfera con cámaras en vivo
- Simulación genética con BLUP
- Modelo Ollama fine-tuned v16
- Ingesta automática diaria
- Backup a NAS cada 6h

### En progreso
- Generación de imágenes FLUX para landing page
- Conexión del dron Bebop 2 vía puente HTTP
- Pipeline foto → modelo 3D de aves

### Pendiente
- Tracking de aves por cámara (seguimiento continuo)
- Together VL models (requiere endpoint dedicado de pago)
- Integración IoT real con sensores de campo

---

## 12. Cómo Arrancar

```bash
cd /home/davidia/Documentos/Seedy
docker compose up -d

# Verificar
curl http://localhost:8000/health
curl http://localhost:8000/birds/
```

Dashboard: `https://seedy-api.neofarm.io/dashboard/`
OvoSfera: `https://hub.ovosfera.com/farm/palacio/gallineros`
Open WebUI: `http://localhost:3000`

---

## 13. Ficheros Clave

```
backend/
├── main.py                    # FastAPI app, middleware, lifespan
├── config.py                  # Settings desde .env (pydantic)
├── routers/
│   ├── vision_identify.py     # Pipeline captura→YOLO→Gemini→registro (127KB)
│   ├── chat.py                # Chat RAG principal
│   ├── openai_compat.py       # Endpoint OpenAI-compatible
│   ├── genetics.py            # Simulación genética
│   └── ...
├── services/
│   ├── yolo_detector.py       # YOLO local GPU
│   ├── gemini_vision.py       # Gemini 2.5 Flash vision
│   ├── rag.py                 # Búsqueda vectorial
│   ├── llm.py                 # LLM generation
│   └── ...
├── dashboard/
│   ├── ovosfera-inject.js     # Inyección en OvoSfera (3500+ líneas)
│   ├── digital_twin_3d.html   # Gemelo digital 3D
│   └── ...
docker-compose.yml             # 16+ servicios
data/
├── birds_registry.json        # 77 aves registradas
└── bird_photos/               # Fotos de referencia
conocimientos/                 # Knowledge base (15+ categorías)
```

---

*Generado automáticamente por Seedy AI — 31 marzo 2026*
