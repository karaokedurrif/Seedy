# Seedy — IA Vertical AgriTech integrada en OvoSfera
## Informe técnico del Tenant Palacio
**Fecha:** 24 de marzo de 2026  
**Granja:** El Gallinero del Palacio, La Granja de San Ildefonso, Segovia  
**Coordenadas:** 40.91541°N, −4.06827°E, 1000 m de altitud

---

## 1. Qué es Seedy

Seedy es un sistema de **inteligencia artificial vertical para avicultura de razas heritage**. No es un chatbot genérico conectado a una granja — es un stack completo de ML que observa, identifica, aprende y asesora, diseñado para funcionar en el edge (una sola máquina con GPU) con capacidad de escalar a cloud.

### 1.1 Filosofía de diseño

```
                    ┌─────────────────────────────────┐
                    │      OvoSfera (Next.js SaaS)     │
                    │      hub.ovosfera.com             │
                    │   Multi-tenant: Palacio, ...      │
                    └───────────┬─────────────────────┘
                                │ inject.js (bridge)
                    ┌───────────▼─────────────────────┐
                    │      Seedy Backend (FastAPI)      │
                    │  ┌────┐ ┌────┐ ┌────┐ ┌────────┐│
                    │  │RAG │ │YOLO│ │ReID│ │Genetics ││
                    │  └──┬─┘ └──┬─┘ └──┬─┘ └───┬────┘│
                    └─────┼──────┼──────┼───────┼─────┘
                      ┌───▼──┐ ┌─▼──┐ ┌▼────┐ ┌▼─────┐
                      │Qdrant│ │YOLO│ │Toget│ │Ollama│
                      │9 col.│ │v8s │ │her  │ │v16   │
                      │216K  │ │GPU │ │Qwen3│ │14B   │
                      │vects │ │    │ │VL8B │ │Q4_KM │
                      └──────┘ └────┘ └─────┘ └──────┘
```

Seedy se inyecta en OvoSfera **sin modificar el código de OvoSfera**. Un script JavaScript (`ovosfera-inject.js`) se carga via Cloudflare Workers y añade funcionalidad IA sobre la interfaz existente de gestión de gallineros.

---

## 2. Cómo se integra en OvoSfera — Tenant Palacio

### 2.1 El bridge JavaScript

OvoSfera es un SaaS Next.js multi-tenant. Seedy no tiene acceso al código fuente de OvoSfera. En su lugar:

1. **Cloudflare Workers** intercepta las peticiones a `hub.ovosfera.com/farm/palacio/*`
2. Inyecta `<script src="https://seedy.local/dashboard/ovosfera-inject.js">`
3. El script detecta en qué página está el usuario via URL matching + MutationObserver
4. Inyecta componentes Seedy (cámaras, IA, chat, planos) en el DOM existente

**Páginas detectadas y enriquecidas:**

| Ruta OvoSfera | Seedy inyecta |
|---|---|
| `/farm/palacio/dashboard` | Plano 2D hero + KPIs (aves, gallineros, huevos, temp, alertas) + thumbnails cámaras 84×48px |
| `/farm/palacio/gallineros` | Grid de tarjetas sin streams grandes (escalable a N gallineros) |
| `/farm/palacio/gallineros/:id` | Streams live + tabs YOLO/IA/ID + lista de aves del gallinero |
| `/farm/palacio/aves` | Tabla de aves con botón "Auto-ID" y "Captura IA 4K" |
| `/farm/palacio/digital-twin` | Gemelo digital 2D/3D con simulación |

### 2.2 El proxy de cámaras

OvoSfera no sabe que hay cámaras IP. Seedy actúa de proxy:

```
Cámara Dahua 4K (10.10.10.108) ──RTSP──→ go2rtc ──MSE/H.264──→ WebSocket ──→ OvoSfera
Cámara VIGI II (10.10.10.10)   ──RTSP──→ go2rtc ──MSE/H.264──→ WebSocket ──→ OvoSfera
Cámara VIGI Nueva (pendiente)  ──RTSP──→ go2rtc ──MSE/H.264──→ WebSocket ──→ OvoSfera
```

Los streams se sirven como:
- **MSE WebSocket** (tiempo real, ~200ms latencia) para vista live
- **Snapshots JPEG** cada 5s para thumbnails
- **Frames anotados YOLO** cada 4s con bounding boxes de aves detectadas

### 2.3 El túnel Cloudflare

Todo funciona detrás de un tunnel Cloudflare Zero Trust:
- El backend Seedy corre en una máquina local (laptop con RTX 5080)
- `cloudflared` expone el puerto 8000 a Internet sin abrir puertos en el router
- OvoSfera en la nube se comunica con Seedy local de forma segura

---

## 3. Qué datos obtiene y dónde los guarda

### 3.1 Mapa de datos

```
┌─ DATOS EN TIEMPO REAL ─────────────────────────────────────────┐
│                                                                 │
│  Cámaras IP (3×4K) ──→ go2rtc ──→ Frames JPEG ──→ YOLO        │
│       cada 4s              │          │                         │
│                            │     Detecciones                    │
│                            │     (breed, sex,                   │
│                            │      bbox, conf)                   │
│                            │          │                         │
│                            │     Together.ai                    │
│                            │     Qwen3-VL-8B                   │
│                            │          │                         │
│                            │     Re-ID visual                   │
│                            │     (anilla, ID)                   │
│                            ▼          ▼                         │
│  MQTT (Mosquitto) ◄─── Eventos ──→ Node-RED ──→ InfluxDB       │
│  seedy/vision/events       │         │          seedy_iot       │
│  seedy/vision/weights      │         │          (time-series)   │
│  seedy/vision/alerts       │         ▼                          │
│                            │     Telegram alertas               │
│                            │     (bot AI)                       │
│                            ▼                                    │
│  birds_registry.json ◄── Registro de 62 aves identificadas     │
│  bird_gallery/{id}/ ◄─── 20 carpetas, 62+ fotos acumuladas     │
│  bird_photos/{id}.jpg ◄── 87 fotos de captura IA 4K            │
│                                                                 │
├─ BASE DE CONOCIMIENTO (RAG) ───────────────────────────────────┤
│                                                                 │
│  Qdrant (9 colecciones, 215.962 vectores, 1.5 GB en disco):   │
│                                                                 │
│  ┌──────────────────┬─────────┬─────────────────────────────┐  │
│  │ Colección        │ Vectores│ Contenido                   │  │
│  ├──────────────────┼─────────┼─────────────────────────────┤  │
│  │ estrategia       │ 138.490 │ Competencia, mercado,       │  │
│  │                  │         │ planes de negocio           │  │
│  │ avicultura       │  39.501 │ Razas heritage, capones,    │  │
│  │                  │         │ manejo, sanidad             │  │
│  │ genetica         │   8.868 │ Pedigree, COI, selección    │  │
│  │ nutricion        │   8.048 │ Formulación piensos,        │  │
│  │                  │         │ metabolismo aviar           │  │
│  │ normativa        │   6.692 │ MAPA, EU, bioseguridad      │  │
│  │ iot_hardware     │   5.162 │ Sensores, cámaras, IoT      │  │
│  │ digital_twins    │   4.923 │ BIM, GIS, gemelos digitales │  │
│  │ fresh_web        │   2.866 │ Web crawling reciente       │  │
│  │ geotwin          │   1.412 │ GeoTwin, MDT, ortofotos     │  │
│  └──────────────────┴─────────┴─────────────────────────────┘  │
│                                                                 │
│  Embeddings: mxbai-embed-large (1024 dims) + BM25 sparse       │
│  Reranker: bge-reranker-v2-m3 (cross-encoder, GPU CUDA)        │
│                                                                 │
├─ MODELO LLM PROPIO ───────────────────────────────────────────┤
│                                                                 │
│  Seedy v16 (Qwen2.5-14B fine-tuned):                          │
│  - Base: Qwen/Qwen2.5-14B-Instruct                            │
│  - SFT: 4.700 ejemplos (16 iteraciones de dataset)            │
│  - Fine-tune: Together.ai LoRA (r=16, α=32, 3 epochs)        │
│  - Cuantizado: Q4_K_M (9 GB GGUF) para Ollama local           │
│  - Fallback: Together.ai Qwen2.5-72B si Ollama falla          │
│                                                                 │
│  Seedy Vision (Qwen2-VL-7B):                                  │
│  - Análisis de imágenes locales (7.8 GB)                       │
│                                                                 │
├─ MODELO YOLO PROPIO ──────────────────────────────────────────┤
│                                                                 │
│  YOLOv8s breed-tuned (22 MB):                                  │
│  - 12 clases de raza (Sussex ♀♂, Bresse ♀♂, Marans ♀,        │
│    Vorwerk ♀♂, Sulmtaler ♀♂, Andaluza Azul ♀, Pita Pinta ♀)  │
│  - mAP50 = 0.944 (907 imágenes de entrenamiento)              │
│  - Araucana + F1: census fallback (no suficientes fotos)       │
│                                                                 │
├─ GEMELO DIGITAL ──────────────────────────────────────────────┤
│                                                                 │
│  BIM semántico (granja_bim_semantico.json):                    │
│  - 19 elementos (edificios, zonas, vallas, cámaras, equipo)   │
│  - 3 capas dinámicas (animales, sensores IoT, alertas)         │
│  - API CRUD: /api/bim/palacio                                  │
│  - Twin 3D: Three.js r169 (830 líneas)                        │
│  - Twin 2D: SVG 40px/m (10 capas toggleables)                 │
│  - GeoTwin: geoTwin.es, twin ID Yasg5zxsF_                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Cuánto ocupa todo

| Componente | Almacenamiento | Notas |
|---|---|---|
| **Modelos Ollama** | **17 GB** | seedy:v16 (9GB) + seedy-vision (7.8GB) + embeddings (669MB) |
| **Imagen Docker backend** | **9 GB** | PyTorch + YOLO + transformers + FastAPI |
| **Qdrant vectores** | **1.5 GB** | 215.962 vectores × 1024 dims float32 |
| **Datos aplicación** | **231 MB** | Raw corpus (216MB) + bird gallery (8.8MB) + bird photos (2.5MB) + registry (1.3MB) |
| **YOLO breed model** | **22 MB** | YOLOv8s fine-tuned .pt |
| **BIM / Digital Twin** | **48 KB** | JSON + SVG + CSV |
| **Datasets SFT** | **~25 MB** | 16 iteraciones de JSONL acumuladas |
| **InfluxDB** | **188 KB** | Casi vacío (sin sensores IoT reales aún) |
| **Total contenedores** | **31 GB** | Volúmenes Docker (modelos + datos + Qdrant) |
| **Workspace completo** | **62 GB** | Código + datasets + imágenes Docker + builds |

**GPU en uso:** NVIDIA RTX 5080 16GB — actualmente usando 2.5 GB (Ollama embeddings + reranker cargado). El LLM se carga bajo demanda (9 GB adicionales cuando hay query de chat).  
**RAM:** 64 GB DDR5 — margen amplio para embeddings en memoria, caches y batch processing.  
**Almacenamiento:** SSD NVMe 1 TB (sistema + Docker) + SSD NVMe 2 TB alta velocidad (datasets, fotos dron, modelos GGUF, backups locales). Total: 3 TB de almacenamiento rápido.

---

## 4. Cómo hace ML cada día

### 4.1 El ciclo de visión (24/7, cada 4 segundos)

```
┌─ CICLO DE VISIÓN (loop cada 4s) ──────────────────────────┐
│                                                             │
│  1. Capturar frame 4K                                      │
│     ├─ Prioridad: CGI snapshot directo (100ms)             │
│     └─ Fallback: go2rtc frame JPEG                          │
│                                                             │
│  2. YOLOv8s detecta "bird" (class 14 COCO)                │
│     ├─ conf ≥ 0.25, imgsz 1280-1920                       │
│     └─ Output: N bounding boxes + confidence               │
│                                                             │
│  3. Para cada ave detectada:                                │
│     ├─ Crop con 20% padding → hasta 1024px max             │
│     ├─ YOLO breed model → raza + sexo (mAP50=0.944)       │
│     ├─ Census validation → corregir por contexto           │
│     │   (si YOLO dice "Pita Pinta" pero en GI no hay      │
│     │    → reclasifica como Vorwerk por eliminación)        │
│     └─ Si conf < umbral → Together.ai Qwen3-VL-8B         │
│        (envía crop + censo del gallinero como contexto)     │
│                                                             │
│  4. Publicar evento MQTT                                    │
│     seedy/vision/events → {camera, n_detections, breeds}   │
│                                                             │
│  5. Node-RED recibe → escribe InfluxDB                     │
│     measurement: animal_detections                          │
│     tags: camera_id, farm_id                                │
│     fields: n_detections, inference_ms                      │
│                                                             │
│  6. Si alerta → Telegram (bot AI)                          │
│     "⚠️ 0 aves detectadas en GI durante 30 min"           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 El sistema RAG (bajo demanda)

Cuando un usuario pregunta algo a Seedy:

```
"¿Cuál es la mejor alimentación para mis Sussex en invierno?"
                    │
    ┌───────────────▼───────────────┐
    │ 1. Clasificar query (Together)│
    │    → [NUTRICION: 0.85,        │
    │       AVICULTURA: 0.60]       │
    └───────────────┬───────────────┘
                    │
    ┌───────────────▼───────────────┐
    │ 2. Seleccionar colecciones    │
    │    → {nutricion, avicultura}  │
    └───────────────┬───────────────┘
                    │
    ┌───────────────▼───────────────┐
    │ 3. Búsqueda híbrida           │
    │    Dense: mxbai-embed (1024d) │
    │    Sparse: BM25               │
    │    Fusión: RRF (k=60)         │
    │    → Top 40 candidatos        │
    └───────────────┬───────────────┘
                    │
    ┌───────────────▼───────────────┐
    │ 4. Reranking (bge-v2-m3)     │
    │    Cross-encoder GPU          │
    │    → Top 8 (max 2 por fuente) │
    └───────────────┬───────────────┘
                    │
    ┌───────────────▼───────────────┐
    │ 5. Generar respuesta          │
    │    Seedy v16 (Ollama local)   │
    │    14B params, Q4_K_M, GPU    │
    │    Fallback: Together.ai 72B  │
    │    Temp: 0.3, max 1024 tok    │
    └───────────────────────────────┘
```

### 4.3 El Re-ID visual (bajo demanda)

Cuando el usuario pulsa "Auto-ID" o "Captura IA 4K":

1. **Multi-frame capture**: 3 intentos × N cámaras, selecciona el crop más grande
2. **4K main stream** (3840×2160) via go2rtc, JPEG 92%
3. **YOLO COCO detect** → crop ave con 20% padding → hasta 1024px
4. **Together.ai Qwen3-VL-8B** compara crop contra:
   - Contact sheet (mosaico de fotos del gallinero)
   - Censo del gallinero (restricción de razas posibles)
5. **Output**: anilla, breed, sex, confidence (98% accuracy en tests)
6. **Guarda** foto en gallery + actualiza registro

### 4.4 El fine-tuning del LLM (periódico)

```
Evolución del modelo (16 iteraciones en 3 semanas):

  v3 ─→ v4 ─→ v5 ─→ v6 ─→ v7 ─→ v8 ─→ v9 ─→ v10 ─→ v11 ─→ ... ─→ v15 ─→ v16
  │      │      │      │                        │                        │
  60     340    340    346 ejemplos             3200                     4700 ejemplos
  │                                              │                        │
  Llama-2-7B                                  Qwen2.5-14B             Qwen2.5-14B
  (primeras pruebas)                          (salto de calidad)       (actual)

Pipeline:
  1. build_dataset_v*.py → genera JSONL desde:
     ├─ Q&A manuales (dominio avicultura heritage)
     ├─ HuggingFace datasets (KisanVaani, CROP, empathetic)
     ├─ Correcciones manuales (v14: 15, v16: 5 corrections)
     └─ Corpus específico (capones, CEP, CDA)

  2. Upload a Together.ai → fine-tune LoRA
     - r=16, α=32, 3 epochs, batch=8, lr=2e-5

  3. Descargar checkpoint → convertir a GGUF Q4_K_M

  4. Ollama create seedy:v16 -f Modelfile.seedy-v16

  5. Test con check_finetune_v16.py → validar calidad
```

---

## 5. Preparación para escalar datos

### 5.1 Lo que ya está preparado

| Componente | Capacidad actual | Diseñado para |
|---|---|---|
| **Qdrant** | 216K vectores (1.5 GB) | Millones de vectores, sharding automático |
| **InfluxDB** | ~vacío (188 KB) | Años de time-series a alta frecuencia |
| **Bird registry** | 62 aves (JSON file) | OK para <500; migración a PostgreSQL prevista |
| **YOLO dataset** | 907 imágenes | Se auto-acumula con cada detección |
| **SFT dataset** | 4.700 ejemplos | Crece con correcciones manuales |
| **BIM** | 19 elementos | Extensible vía API CRUD |

### 5.2 La estrategia de crecimiento

```
FASE ACTUAL (1 granja, 26 aves, 3 cámaras):
  └─ Todo en 1 máquina local (laptop RTX 5080 + 64GB RAM + 3TB SSD)
  └─ ~62 GB usados de 3 TB, 2.5 GB GPU idle, 16 GB GPU pico
  └─ Disco 2 TB nuevo disponible para: ortofotos dron, dataset YOLO, backups

FASE 2 (5-10 granjas, 200 aves):
  └─ Migrar bird_registry.json → PostgreSQL
  └─ Sensores IoT reales en InfluxDB
  └─ Particionado temporal en InfluxDB por granja
  └─ YOLO breed model retraining con 5000+ imágenes
  └─ Dataset SFT ~10.000 ejemplos, fine-tune semanal

FASE 3 (50+ granjas, 2000+ aves):
  └─ Seedy backend → Kubernetes (GPU nodes)
  └─ Qdrant → cluster distribuido (3 nodos)
  └─ go2rtc → 1 instancia por granja
  └─ Ollama → LLM serving con vLLM/TGI (batching)
  └─ Fine-tune continuo con DPO (Direct Preference Optimization)
  └─ Modelos predictivos: Gompertz real, mortalidad, producción
```

### 5.3 Cómo se acumularán los datos

| Dato | Frecuencia | Volumen estimado/año |
|---|---|---|
| Detecciones YOLO | 4s × 3 cámaras = 64.800/día | ~24M registros/año → InfluxDB |
| Fotos Re-ID | ~10/día (nuevas capturas) | ~3.600 fotos → 1.5 GB/año |
| Pesajes | semanal × 26 aves | ~1.350 registros/año |
| Sensores IoT | 30s × N sensores | ~1M registros/año por sensor |
| Vectores RAG | ingesta periódica | +50K vectores/año |
| SFT corrections | manual | +200 ejemplos/año |

---

## 6. El Gemelo Digital

### 6.1 Componentes desplegados

| Capa | Archivo | Tecnología | Estado |
|---|---|---|---|
| **2D SVG** | `plano_digital_2d_base.svg` | SVG 40px/m, 10 capas, dark theme | ✅ Producción |
| **3D WebGL** | `digital_twin_3d.html` | Three.js r169, 830 líneas | ✅ Producción |
| **BIM JSON** | `granja_bim_semantico.json` | IFC-like, 19 elementos | ✅ Producción |
| **BIM API** | `/api/bim/palacio` | FastAPI CRUD | ✅ Producción |
| **BIM CSV** | `granja_bim_elementos.csv` | 19 filas sincronizadas | ✅ Producción |
| **Ave Twin** | `ave_twin.html` | HTML standalone por ave | ✅ Producción |
| **GeoTwin** | `geoTwin.es` ID Yasg5zxsF_ | MDT 2m + KML parcela | ✅ Externo |
| **Simulación** | Integrada en 3D twin | Meteo/Bioseg/Expansión/Financiero | ✅ Producción |
| **Ortofoto** | `/api/bim/palacio/ortofoto` | Endpoint listo, esperando dron DJI | ⏳ Pendiente |

### 6.2 El twin 3D

- **Orbit**, **Isométrica**, **Planta**, **WASD first-person**, **POV por cámara** (3 cámaras)
- Geometría cargada dinámicamente desde la API BIM (no hardcoded)
- WebSocket para posiciones de animales (2 Hz, lerp interpolation)
- Simulación: 4 modos (meteorología con partículas de lluvia, bioseguridad SIR, expansión con ghost buildings, financiero)

---

## 7. Stack completo — 15 servicios Docker

| Servicio | Puerto | GPU | RAM | Función |
|---|---|---|---|---|
| **seedy-backend** | 8000 | ✅ | ~2 GB | FastAPI: RAG, visión, genética, bridge |
| **ollama** | 11434 | ✅ | 1-10 GB | LLM seedy:v16 + embeddings mxbai |
| **qdrant** | 6333 | — | ~800 MB | Vector store (9 colecciones, 216K vecs) |
| **go2rtc** | 1984 | — | ~100 MB | RTSP→WebRTC/MSE proxy (3 cámaras) |
| **influxdb** | 8086 | — | ~50 MB | Time-series IoT |
| **mosquitto** | 1883 | — | ~10 MB | MQTT broker |
| **nodered** | 1880 | — | ~100 MB | Automatización IoT + alertas |
| **grafana** | 3001 | — | ~50 MB | Dashboards IoT |
| **open-webui** | 3000 | — | ~200 MB | Chat UI para Seedy |
| **edge-tts** | 8100 | — | ~30 MB | Text-to-speech (Microsoft neural) |
| **searxng** | 8888 | — | ~100 MB | Meta-búsqueda web |
| **crawl4ai** | 11235 | — | ~200 MB | Web crawling con browser |
| **cloudflared** | — | — | ~30 MB | Tunnel Cloudflare Zero Trust |

**Hardware:** Laptop con NVIDIA RTX 5080 16GB, 64 GB RAM, SSD NVMe 1 TB (sistema) + SSD NVMe 2 TB (datos, alta velocidad).

---

## 8. Mejoras que propongo (Opus)

Después de analizar el codebase completo, los datos y la arquitectura, estas son las mejoras que considero más impactantes ordenadas por prioridad:

### 8.1 CRÍTICAS — Hacer ya

#### A. Migrar `birds_registry.json` a SQLite/PostgreSQL
**Problema:** Un JSON de 1.3 MB con 62 aves funciona, pero cada escritura serializa todo el archivo. Con 200+ aves y escrituras concurrentes desde YOLO (cada 4s), habrá race conditions y pérdida de datos.  
**Solución:** SQLite como paso intermedio (cero dependencias, backup trivial), luego PostgreSQL cuando haya multi-tenant real.  
**Esfuerzo:** 4-6 horas. Impacto: elimina el mayor punto de fallo del sistema.

#### B. Persistir detecciones YOLO en InfluxDB de verdad
**Problema:** InfluxDB tiene 188 KB. Los eventos MQTT se publican pero Node-RED apenas escribe. Estás perdiendo todos los datos de detección de las últimas 3 semanas.  
**Solución:** Verificar los flows de Node-RED (puede ser un bug de conexión), y añadir un fallback de escritura directa desde Python (`influxdb-client`) para no depender solo de MQTT→Node-RED.  
**Esfuerzo:** 2-3 horas. Impacto: sin datos históricos no hay predicciones futuras.

#### C. Backup automatizado
**Problema:** No hay backup automático. Si la laptop falla, se pierden 62 GB de datos, 216K vectores, 62 aves registradas, y 20 días de fotos.  
**Solución:** Cron diario: `birds_registry.json` + Qdrant snapshot + bird_gallery/ → rsync a NAS o S3.  
**Esfuerzo:** 1-2 horas.

### 8.2 IMPORTANTES — Próximas semanas

#### D. Pipeline de retraining YOLO automatizado
**Problema:** Cada detección YOLO genera crops que se podrían usar para reentrenar, pero el proceso es 100% manual (descargar, limpiar, anotar, entrenar).  
**Solución:** Auto-labeling pipeline: cuando Re-ID confirma un ave con >90% confidence, guardar el crop con metadata de raza → acumulador automático → cuando hay 200+ nuevas imágenes, lanzar job de retraining.  
**Esfuerzo:** 8-12 horas. Impacto: mAP50 subirá con cada mes de operación.

#### E. Gompertz real con datos de pesaje
**Problema:** El endpoint `/gompertz` devuelve curvas teóricas con peso vacío. No hay integración con pesajes reales.  
**Solución:** Conectar pesajes (manual o con báscula IoT) → ajustar curva Gompertz por mínimos cuadrados → alertar si el ave se desvía >15% de la curva predicha.  
**Esfuerzo:** 4 horas para el fitting, 2 horas para el frontend.

#### F. Deduplicación y cleanup de colecciones Qdrant
**Problema:** `estrategia` tiene 138K vectores (64% del total). Probablemente hay mucha redundancia de ingesta repetida.  
**Solución:** Script de deduplicación: por cada vector, buscar los 5 más cercanos en la misma colección; si cosine > 0.98, eliminar el duplicado más reciente.  
**Esfuerzo:** 3-4 horas. Impacto: RAG más rápido y menos ruido.

### 8.3 ESTRATÉGICAS — Próximos meses

#### G. DPO (Direct Preference Optimization) para Seedy v17+
**Problema:** El fine-tuning actual es SFT (supervised). Las correcciones manuales (5-15 por versión) son pocas para mejorar significativamente.  
**Solución:** Implementar un sistema de feedback en el chat: 👍/👎 en cada respuesta → acumular pares (preferred, rejected) → DPO training cada 500 pares.  
**Impacto:** El modelo mejora continuamente con uso real, no solo con datos manuales.

#### H. Tracking de trayectorias real
**Problema:** El YOLO detecta aves cada 4s pero no asocia detecciones entre frames (no hay tracking temporal).  
**Solución:** Añadir ByteTrack o BoT-SORT encima de YOLO → asignar track_id por frame → correlacionar con Re-ID para trayectorias continuas → almacenar en InfluxDB como `bird_trajectory(bird_id, x, y, timestamp)`.  
**Impacto:** Desbloquea el mapa de calor de actividad, detección de anomalías de comportamiento, y alimenta al gemelo digital con posiciones reales.

#### I. Federación multi-granja
**Problema:** Todo el sistema asume una granja. El tenant en la URL existe pero el backend no partiona datos por tenant.  
**Solución:** Namespace por tenant en: Qdrant (metadata filter), InfluxDB (bucket por tenant), birds_registry (tabla con columna tenant), BIM (directorio por tenant, ya soportado).  
**Esfuerzo:** 2-3 días. Impacto: habilita OvoSfera multi-granja real.

#### J. Modelo predictivo de producción
**Problema:** Con datos acumulados de detecciones + pesajes + clima, se pueden predecir: producción de huevos, fecha óptima de sacrificio de capones, necesidad de calefacción.  
**Solución:** Cuando haya 6+ meses de datos en InfluxDB, entrenar modelo temporal (Prophet/LSTM) por gallinero. Integrar predicciones como capa en el gemelo digital.  
**Impacto:** Diferenciador real frente a toda la competencia AgTech.

### 8.4 Resumen de prioridades

```
AHORA:
  [A] birds_registry → SQLite          ← elimina el mayor riesgo
  [B] InfluxDB detections pipeline      ← sin datos no hay futuro
  [C] Backup automatizado               ← seguro ante fallos

MES 1:
  [D] YOLO auto-retraining pipeline     ← mejora continua de detección
  [E] Gompertz con datos reales         ← primer valor predictivo
  [F] Dedup Qdrant                       ← RAG más limpio

MES 2-3:
  [G] DPO feedback loop                 ← LLM que mejora con uso
  [H] ByteTrack trayectorias            ← tracking real en digital twin
  [I] Multi-tenant real                  ← escalar a más granjas

MES 6+:
  [J] Modelos predictivos               ← el verdadero diferenciador
```

---

*Generado el 24 de marzo de 2026 por Claude Opus 4.6 a partir del análisis completo del codebase, contenedores, bases de datos y configuración de Seedy + OvoSfera tenant Palacio.*
