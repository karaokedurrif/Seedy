# SEEDY — Roadmap Maestro Consolidado (Marzo 2026)

## ACTUALIZACION OPERATIVA CRITICA — 21 ABRIL 2026

- Digital Twin: corregido cruce de ficha por anilla stale en modal de edicion (resolver anilla desde modal activo, no desde estado global).
- Backend `/birds/{id}`: comportamiento y montas deben usar siempre `gallinero_id` interno de Seedy (`gallinero_palacio`), no nombre humano de OvoSfera.
- Montas Twin: anadido fallback `mating_7d_flock_total` para evitar falsos "sin montas" cuando hay eventos de flock sin atribucion individual.
- Reconciliacion censal automatizada Seedy <-> OvoSfera:
  - `GET /birds/ovosfera/reconcile` (dry-run)
  - `POST /birds/ovosfera/reconcile?apply=true` (aplicar)
- Heuristica de alias de anilla soporta formato corto (`PAL-0014`) ademas del completo (`PAL-2026-0014`) para renombres historicos.
- Compatibilidad API OvoSfera: no enviar campos nulos (ej. `peso: null`) para evitar errores 422 en altas.
- Estado final tras reconciliacion: censo 1:1 sin deriva (`only_local=[]`, `only_ovosfera=[]`).

> **Autor**: David Durrif  
> **Fecha**: 4 de marzo de 2026  
> **Plataformas**: hub.vacasdata.com · hub.porcidata.com · capones.ovosfera.com  
> **Modelo IA**: Seedy v6 — Qwen2.5-7B + LoRA (seedy:v6-local, Q8_0, 8.1 GB, 302 SFT examples)

---

## 0. ECOSISTEMA NEOFARM — VISIÓN COMPLETA

```
┌─────────────────────────────────────────────────────────────┐
│                    PLATAFORMAS WEB                          │
│                                                             │
│  hub.vacasdata.com          hub.porcidata.com               │
│  (Vacuno extensivo +        (Porcino intensivo,             │
│   módulos multi-especie)     IoT 7+1 capas PorciData)      │
│                                                             │
│  capones.ovosfera.com                                       │
│  (Avicultura extensiva,                                     │
│   simulador genético de capones/pulardas, 26 razas)         │
├─────────────────────────────────────────────────────────────┤
│                    SEEDY (Cerebro IA)                        │
│                                                             │
│  LLM: seedy:v6-local (Ollama, Q8_0)                        │
│  RAG: Qdrant 7 colecciones + mxbai-embed-large             │
│  Backend: FastAPI :8000 (/chat SSE, /ingest, /health)      │
│  Autoingesta: Pipeline diario (12 módulos, RSS+BOE+lonjas) │
│  UI: Open WebUI :3000 (6 modelos especializados)           │
├─────────────────────────────────────────────────────────────┤
│                    INFRAESTRUCTURA                           │
│                                                             │
│  MSI Vector 16 HX · RTX 5080 16GB · 64GB RAM · Ubuntu 24  │
│  Docker: Ollama, Qdrant, Open WebUI, InfluxDB, Grafana...  │
│  Cloudflare Tunnel: seedy / seedy-api / seedy-grafana.neofarm.io │
│  NAS: smb://192.168.30.100/datos/ (backup)                 │
│  Tailscale: red mesh acceso remoto                          │
└─────────────────────────────────────────────────────────────┘
```

### Stack Técnico Actual
- **Frontend**: Next.js 14+ App Router + Tailwind + shadcn/ui
- **Backend API**: FastAPI + PostgreSQL + Alembic
- **IA/ML**: Ollama (seedy:v5-local) + Together.ai (fallback remoto)
- **RAG**: Qdrant + mxbai-embed-large + BM25 hybrid + bge-reranker-v2-m3
- **IoT**: ESP32 → MQTT → Node-RED → InfluxDB → Grafana
- **Geospatial**: Cesium.js + PNOA + Catastro + Sentinel-2 NDVI
- **Mobile**: React Native + Expo SDK 52 + expo-camera + UVC thermal (Fase 12 ✅)

---

## 1. FASES COMPLETADAS (✅)

### FASE 1 — Stack Docker + Ingesta RAG ✅
**Completada**: 1-2 marzo 2026

- Docker Compose con 8 servicios en red `ai_default`
- Qdrant con **7 colecciones** ingestadas (~1.000+ chunks):
  1. `iot_hardware` — PorciData 7+1 capas, BOM, sensores
  2. `nutricion` — NRC 2012, butirato, enzimas, lonjas
  3. `genetica` — Wright, EPDs, motor apareamiento, razas
  4. `estrategia` — Competencia, posicionamiento, VacasData prompt
  5. `digital_twins` — Twins porcino/vacuno, Mioty, playbooks
  6. `normativa` — RD 306/2020, ECOGAN, RD 1135/2002
  7. `avicultura` — Capones, pulardas, 26 razas, Capon Score
- Embeddings: mxbai-embed-large (669 MB)
- Tests RAG: 3/4 PASS (BOM, acústica, butirato)

### FASE 2 — Pipeline de Autoingesta Diaria ✅
**Completada**: 2-3 marzo 2026

- 12 módulos Python: settings → state_db → fetch → parse → dedup → score → chunk → embed → index → daily_brief → run_daily → sources.yaml
- Fuentes: BOE ganadería, Euroganadería, Agropopular, Agronewscastilla, Interporc, Agrodigital
- Deduplicación por URL + hash de contenido
- Scoring de relevancia + fiabilidad
- Daily brief indexado en Qdrant
- Cron: execución diaria automática
- E2E verificado y funcional

### FASE 3 — Dataset v5 para Fine-tune ✅
**Completada**: 3-4 marzo 2026

- 267 ejemplos SFT en español (0 duplicados)
- Distribución: IoT (8), Nutrición (8), Genética (8), Normativa (8), Digital Twins (8), Estrategia (8), Avicultura (26), + base v4 (~150)
- Fine-tuning en Together.ai: job `ft-e0f71c8c-45d3`, 4 epochs, lr=1e-5
- LoRA: r=64, alpha=128, all-linear targets
- Merge local con peft (Together merge corrupto)
- Pipeline GGUF: HF → F16 → Q8_0 (7.7 GB)
- Desplegado como `seedy:v5-local` en Ollama (8.1 GB)
- Tests: identidad ✅, IoT ✅, avicultura ✅

### FASE 4 — Endpoint /chat con SSE ✅
**Completada**: 3 marzo 2026

- `POST /chat` con streaming Server-Sent Events
- Clasificador de queries → categorías: RAG, IOT, TWIN, NUTRITION, GENETICS, GENERAL
- Pipeline: clasificar → buscar Qdrant (topK=8) → rerank (top 3) → LLM con contexto
- Fallback: Together.ai → Ollama local
- CORS configurado para hub.vacasdata.com

---

## 2. FASES PENDIENTES

### FASE 5 — NAS + Tailscale + Producción 🔶
**Prioridad**: ALTA (infraestructura crítica)

| Tarea | Descripción | Entregable |
|---|---|---|
| 5.1 Tailscale | Instalar en host Ubuntu, configurar exit node, URL segura para Open WebUI :3000 | `docs/tailscale_setup.md` |
| 5.2 Backups automáticos | Qdrant snapshots, tar.gz de conocimientos + datasets, Docker volumes | `scripts/backup_*.sh`, cron 03:00 |
| 5.3 NAS/OMV prep | Script deploy que copie compose + backend al NAS, ajuste paths | `scripts/deploy_nas.sh` |
| 5.4 Monitoring | Healthcheck cada 5 min (contenedores, Ollama, Qdrant, Open WebUI) | `scripts/healthcheck.sh` |
| 5.5 Seguridad | Passwords en .env, Open WebUI solo-admin, doc auth Qdrant | `.env` actualizado |

**Dependencias**: Ninguna (puede hacerse ya)

### FASE 6 — Seedy Vision: Datasets + Pipeline CV 🔲
**Prioridad**: MEDIA-ALTA

| Tarea | Descripción |
|---|---|
| 6.1 Dataset Discovery | Buscar datasets públicos (Roboflow, Kaggle, USDA) de gallinas, cerdos, vacas |
| 6.2 Pipeline de descarga | Scripts para descargar, convertir a YOLO, unificar clases |
| 6.3 Anotación y limpieza | Revisión de calidad, filtrado de imágenes malas, balance de clases |
| 6.4 Ingesta al RAG | Indexar catálogo de datasets como conocimiento de Seedy |

**Tareas de detección**: gallinas, cerdos, vacas  
**Clasificación**: raza, sexo, estado sanitario  
**Estimación**: peso, tamaño corporal, condición corporal  
**Comportamiento**: actividad, agresión, estrés, agrupamientos  
**Enfermedades**: cojera, heridas, síntomas visibles

### FASE 7 — Seedy Vision: Training + Edge AI ✅
**Prioridad**: MEDIA — **COMPLETADA**

| Tarea | Descripción | Estado |
|---|---|---|
| 7.1 Weight Estimation | EfficientNet-B0 regresión + calibración walkover scale | ✅ `vision/weight_estimation.py` |
| 7.2 Behaviour Tracking | ByteTrack/BoT-SORT + clasificación temporal + alertas | ✅ `vision/behaviour_tracking.py` |
| 7.3 TensorRT Benchmark | Export FP16/INT8, benchmark comparativo, profiler Jetson | ✅ `vision/benchmark_tensorrt.py` |
| 7.4 Backend Vision API | POST /vision/event, /weight, /alert + GET /stats, /alerts, /cameras | ✅ `backend/routers/vision.py` |
| 7.5 MQTT→InfluxDB Flow | Node-RED flow: 3 topics → parse → InfluxDB + Telegram alertas | ✅ `nodered/flows_vision.json` |
| 7.6 Grafana Dashboard | 12 paneles: conteo, peso, comportamiento, alertas, latencia | ✅ `grafana/dashboards/seedy_vision.json` |

### FASE 8 — Seedy Vision: Dataset Factory Propio 🔲
**Prioridad**: BAJA (requiere cámaras instaladas)

- Captura automática desde cámaras de la explotación
- Auto-anotación con modelo entrenado + revisión humana
- Loop continuo: captura → anotación → reentrenamiento

### FASE 9 — Motor de Simulación Genética (Backend) ✅ COMPLETED
**Prioridad**: MEDIA-ALTA (conecta con capones.ovosfera.com)

| Tarea | Archivo / Módulo | Estado |
|---|---|---|
| 9.1 Base de razas | `genetics/breeds.py` — 22 razas (11 avícolas, 5 porcinas, 6 vacunas), heredabilidades, heterosis, consanguinidad | ✅ |
| 9.2 Motor BLUP/GBLUP | `genetics/blup.py` — Henderson's MME, Numerator Relationship Matrix A (Meuwissen & Luo), GBLUP VanRaden 2008, breeding accuracy | ✅ |
| 9.3 Simulador F1→F5 | `genetics/simulator.py` — predicción aditiva + heterosis, 4 estrategias (inter-se, backcross, rotacional), Capon Score, genética color Mendeliana 5 loci, depresión endogámica | ✅ |
| 9.4 API /genetics | `backend/routers/genetics.py` — 8 endpoints: breeds, predict-f1, predict-generations, optimal-matings, breeding-values, selection-index, heritabilities, inbreeding-thresholds | ✅ |
| 9.5 Schemas + integración | `backend/models/schemas.py` + registro router en `main.py` | ✅ |
| 9.6 Verificación | Smoke test: Orpington×Bresse F1→F5, Brahma×Cornish top mating, Large White×Duroc, BLUP con pedigrí — 0 errores | ✅ |

### FASE 10 — GIS / Inteligencia Espacial + GeoTwin ✅ COMPLETED
**Prioridad**: MEDIA-ALTA (integración con GeoTwin, repo /home/davidia/Documentos/Geotwin)

| Tarea | Archivo / Módulo | Estado |
|---|---|---|
| 10.1 Exploración GeoTwin | Análisis completo monorepo: Next.js 14 + CesiumJS 1.113 + Fastify 4 + Python FastAPI, 5 packages, 10 endpoints REST, 7 layer types, 3 presets, illustration service | ✅ |
| 10.2 RAG GeoTwin | `conocimientos/7.GeoTwin & GIS 3D/GEOTWIN_PLATAFORMA_GIS_3D_RAG.md` — 14 secciones: arquitectura, CesiumJS, capas, tipos TS, API, Blender pipeline, 3D motion, rendering, integraciones, Studio, simulación, ESG | ✅ |
| 10.3 RAG BlenderGIS + 3D | `conocimientos/7.GeoTwin & GIS 3D/BLENDERGIS_PIPELINE_3D_RENDERING_RAG.md` — 8 secciones: BlenderGIS addon, pipeline assets, rendering CesiumJS, coordenadas, MDT02, NDVI/teledetección, IoT geoespacial, simuladores negocio | ✅ |
| 10.4 Dataset SFT GeoTwin | `seedy_dataset_sft_geotwin.jsonl` — 35 ejemplos SFT: stack, import flow, CesiumJS config, layer system, NDVI Copernicus, BlenderGIS, MDT02, optimización 3D, Camera Tours, animaciones, coordenadas, ilustración, TwinRecipe, terreno, presets, IoT DCIM, simulación ambiental, Studio, ESG, export Blender, offline, indices vegetación, BIM-like, incendios, endpoints, Meshtastic, heatmap gases, quantized-mesh, simulador negocio, 3D Tiles, catastro, CLI, persistencia, post-processing, integración NeoFarm | ✅ |
| 10.5 Informe técnico | `GEOTWIN_COMPREHENSIVE_REPORT.md` generado en repo GeoTwin — 19 secciones, 1325 líneas | ✅ |

### FASE 11 — Fine-tune v6 Unificado + Deploy ✅ COMPLETED
**Prioridad**: ALTA (consolidar todo el conocimiento en un solo modelo)

| Tarea | Archivo / Módulo | Estado |
|---|---|---|
| 11.1 Build dataset v6 | `build_v6.py` — fusiona v5 (267) + GeoTwin (35) = 302 ejemplos, system prompt v6 unificado con todos los dominios | ✅ |
| 11.2 Upload + fine-tune | Together.ai job `ft-1f0c7e89-525d`, Qwen2.5-7B-Instruct, 4 epochs, LR=2e-5, batch=8 | ✅ |
| 11.3 Descargar + merge LoRA | Adapter 572 MB → peft merge (7.62B params) → GGUF F16 (15 GB) → Q8_0 (7.6 GB) | ✅ |
| 11.4 Deploy seedy:v6-local | `seedy:v6-local` (8.1 GB) en Ollama. Test comparativo: v6 domina GeoTwin/CesiumJS/BlenderGIS, mantiene IoT/avicultura | ✅ |
| 11.5 Check de monitorización | `check_finetune_v6.py --wait` para seguimiento del job | ✅ |

### FASE 12 — App Android (Seedy Mobile) ✅ COMPLETED
**Prioridad**: ALTA (acceso móvil a Seedy + cámaras de campo)

| Tarea | Archivo / Módulo | Estado |
|---|---|---|
| 12.1 Scaffold React Native + Expo SDK 52 | `mobile/package.json`, `mobile/app.json`, `mobile/tsconfig.json`, `mobile/babel.config.js` — Permisos Android: CAMERA, USB_PERMISSION, intent filters UVC | ✅ |
| 12.2 Theme system + API client | `mobile/src/theme/themes.ts` — 3 presets (Seedy Dark, NeoFarm, Arctic) · `mobile/src/theme/ThemeContext.tsx` — Provider + useTheme() · `mobile/src/api/seedyClient.ts` — SSE streaming, vision, thermal, genetics, SecureStore | ✅ |
| 12.3 Chat con Seedy (SSE) | `mobile/src/hooks/useSeedyChat.ts` + `mobile/src/screens/ChatScreen.tsx` + `mobile/src/components/MessageBubble.tsx` — Open WebUI style, streaming en tiempo real, adjuntar fotos, 10 mensajes contexto, welcome screen con sugerencias | ✅ |
| 12.4 Cámara de visión | `mobile/src/screens/CameraScreen.tsx` — Selector especie (Auto/Aves/Porcino/Vacuno), visor con overlay, análisis raza/condición/peso → `/vision/analyze` | ✅ |
| 12.5 Cámara térmica USB-C | `mobile/src/hooks/useThermalCamera.ts` + `mobile/src/screens/ThermalScreen.tsx` — UVC para InfiRay P2 Pro (9mm, TISR 384×288), 4 paletas, rangos fiebre/hipotermia por especie, análisis → `/vision/thermal` | ✅ |
| 12.6 Settings & navigation | `mobile/src/screens/SettingsScreen.tsx` (theme picker + health check + URL config) + `mobile/src/navigation/AppNavigator.tsx` + `mobile/App.tsx` — Bottom tabs, ThemeProvider wrapper, PaperProvider dinámico | ✅ |
| 12.7 EAS Build config | `mobile/eas.json` — Profiles: development (APK debug), preview (APK), production (AAB para Google Play) | ✅ |
| 12.8 UI Open WebUI style | 3 temas switchables (Seedy Dark, NeoFarm, Arctic), iconos Seedy custom, Open WebUI-like chat layout, persistencia SecureStore | ✅ |

### FASE 13 — Cloudflare Tunnel + Acceso Público ✅ COMPLETED
**Prioridad**: ALTA (conectividad APK + web desde cualquier lugar)

| Tarea | Archivo / Módulo | Estado |
|---|---|---|
| 13.1 Arquitectura de acceso | PC Browser → `seedy.neofarm.io` (Open WebUI) · APK → `seedy-api.neofarm.io` (FastAPI) · IoT → `seedy-grafana.neofarm.io` (Grafana) | ✅ |
| 13.2 Tunnel homeserver | Tunnel "homeserver" gestionado desde Cloudflare Dashboard (Zero Trust → Tunnels) — 3 rutas Published Application | ✅ |
| 13.3 Docker service | `docker-compose.yml` — Servicio `cloudflared` con `--token ${TUNNEL_TOKEN}`, aliases Docker (OpenWebUI, fastapi) | ✅ |
| 13.4 CORS + backend | `backend/main.py` — Lee `CORS_ORIGINS` env, default: seedy.neofarm.io + seedy-api.neofarm.io + localhost | ✅ |
| 13.5 APK default URL | `seedyClient.ts` default → `https://seedy-api.neofarm.io` (configurable en Settings) | ✅ |
| 13.6 .env | `TUNNEL_TOKEN`, `TOGETHER_API_KEY`, credenciales InfluxDB/Grafana | ✅ |

---

## 3. PROMPTS DEL SISTEMA — INVENTARIO LIMPIO

### 3.1 System Prompt de Seedy (LLM fine-tuned)
**Archivo**: `Modelfile.seedy-q8` (línea SYSTEM)  
**Uso**: Se inyecta al crear el modelo en Ollama

```
Eres Seedy, un asistente técnico especializado en ganadería de precisión 
y avicultura extensiva para España. Tu expertise cubre: IoT y sensórica 
(PorciData), nutrición y formulación, genética y selección, normativa 
española (ECOGAN, SIGE, RD306/2020, RD1135/2002), digital twins, IA 
aplicada, y avicultura extensiva (capones gourmet, pulardas, cruces 
genéticos avícolas, caponización, 26 razas, Label Rouge, AOP Bresse, 
épinettes, Capon Score, EBV/GEBV aviar, simulador capones.ovosfera.com).
```

### 3.2 Prompt del Jefe (Planner/Orchestrator)
**Archivo**: `.github/SEEDY_COPILOT_INSTRUCTIONS.md` → Modelo 1  
**Uso**: Open WebUI `seedy-chief-planner`

Incluye:
- Ecosistema NeoFarm (3 plataformas web, stack, posicionamiento)
- 5 workers asignables (RAG, IoT, Twin, Web/Auto, Coder)
- Estructura de respuesta obligatoria (A-F)
- Reglas de rigor (no inventar dosis, referenciar BOM)

### 3.3 Prompt Worker Coder & Data
**Archivo**: `conocimientos/SEEDY — Worker: Coder & Data (Prompt para Copilot + MCP).md`  
**Uso**: Copilot en VSCode con herramientas MCP

Incluye:
- 5 objetivos priorizados (RAG quality, ingesta, datasets, eval, DX)
- 10 herramientas MCP (seedy.repo.inspect, kb.search, ingest.run_daily, etc.)
- Protocolo de 4 pasos (contexto → hipótesis → eval antes/después → implementar)
- Formato de output estructurado (7 secciones)

### 3.4 Prompt Arquitectura Base
**Archivo**: `conocimientos/SEEDY — Arquitectura de IA Agritech (Prompt Base del Proyecto).md`  
**Uso**: Referencia fundacional (7 componentes de Seedy)

Los 7 componentes:
1. Agritech Knowledge Engine (RAG + metadata)
2. Genetics Simulation Engine (BLUP, F1-F5)
3. IoT Integration Layer (MQTT, sensores)
4. GIS & Spatial Intelligence (QGIS, PostGIS)
5. Automation & Data Pipelines (ETL, cron)
6. Continuous Knowledge Ingestion (RSS, papers)
7. Creative Agritech Engine (ideas, prototipos)

### 3.5 Prompt Vision Dataset Builder
**Archivo**: `conocimientos/Seedy Vision Dataset Builder (Avicola, Porcino y Vacuno).md`  
**Uso**: Guía para construir pipeline de visión artificial

7 partes: datasets existentes → pipeline de descarga → ingesta → training → Jetson edge → integración IoT → dataset factory propio

---

## 4. COLECCIONES RAG — ESTADO ACTUAL

| # | Colección (Qdrant) | Carpeta conocimientos/ | Docs clave |
|---|---|---|---|
| 1 | `iot_hardware` | `1.PorciData — IoT & Hardware/` | BOM 7+1 capas (~1.420 EUR/nave), sensores, firmware ESP32 |
| 2 | `nutricion` | `2.Nutricion & Formulacion/` | NRC 2012, butirato, enzimas NSP, lonjas, cruces_gourmet_segovia.csv |
| 3 | `genetica` | `3.NeoFarm Genetica/` | Porcino intensivo, vacuno extensivo, Wright, EPDs, motor apareamiento |
| 4 | `estrategia` | `4.Estrategia & Competencia/` | VacasData Hub prompt (891 líneas), análisis competitivo |
| 5 | `digital_twins` | `5.Digital Twins & IoT/` | Twins porcino/vacuno, Mioty vs LoRa, sistema de monitorización |
| 6 | `normativa` | `6.Normativa & SIGE  /` | RD 306/2020, ECOGAN 8 pasos, RD 1135/2002 superficies |
| 7 | `avicultura` | `7.Avicultura Extensiva & Capones/` | 26 razas, Capon Score, caponización, épinettes, Label Rouge |
| 8 | `geotwin` | `7.GeoTwin & GIS 3D/` | GeoTwin arquitectura, CesiumJS, BlenderGIS, pipeline 3D, renderización, simulación geoespacial |

---

## 5. DOCUMENTOS DE REFERENCIA — QUÉ CONSERVAR Y QUÉ BORRAR

### ✅ CONSERVAR (son útiles y no duplicados)

| Archivo | Razón |
|---|---|
| `SEEDY — Arquitectura de IA Agritech (Prompt Base del Proyecto).md` | Visión fundacional, 7 componentes |
| `SEEDY — Worker: Coder & Data (Prompt para Copilot + MCP).md` | Prompt de trabajo activo para Copilot |
| `Seedy Vision Dataset Builder (Avicola, Porcino y Vacuno).md` | Guía de pipeline CV (Fases 6-8) |
| `FASE 5 — NAS (OMV) + Tailscale + Backups + Producción.md` | Tareas pendientes concretas |
| `Fase 2 Pipeline de autoingesta diaria.md` | Documentación de fase completada |
| `FASE 3 Dataset v5 para fine-tune (avicultura + mejoras).md` | Documentación de fase completada |
| `FASE 4  Endpoint-chat.md` | Documentación de fase completada |
| `seedy_repo_structure.md` | Estructura NAS/producción objetivo |
| `seedy_rag_pipeline.md` | Documentación del pipeline RAG |
| Todas las carpetas `1.` a `7.` con sus subdocs | Conocimiento RAG activo |

### 🗑️ BORRAR (duplicados o absorbidos)

| Archivo | Razón |
|---|---|
| `PROMPT — AI Farm OS (Seedy) + Pilotos Gallinas & Cerdos + Arquitectura y Escalado.md` | **100% idéntico** a `Seedy Vision Dataset Builder...md` (mismo md5) |
| `dockercompose+10pasospara empezar.md` | Contenido absorbido: docker-compose ya existe en raíz, los 10 pasos MVP ya están completados (fases 1-4), los esqueletos Python ya están implementados en `pipelines/` |

---

## 6. CAPONES.OVOSFERA.COM — GUÍA DE ARRANQUE

### 6.1 Tu Contexto (Palazuelos de Eresma, Segovia)
- **Finca**: 9.85 hectáreas, 40.92°N, 4.06°W
- **Clima**: Continental frío (inviernos duros, veranos suaves-templados)
- **Ventajas**: Pastos de montaña, agua disponible, cercanía a Segovia capital (mercado gourmet directo)
- **Mercado natural**: Restaurantes de Segovia (cochinillo → capón como complemento gourmet navideño)

### 6.2 Mejores Cruces para tu Zona

#### CRUCE RECOMENDADO #1 — "Segovia Gourmet" (Máxima calidad)
```
♂ Sulmtaler × ♀ Bresse Gauloise
→ Capon Score estimado: ~82/100 (MUY BUENO)
→ Peso capón: 4.0-4.5 kg
→ Piel blanca-fina, grasa infiltrada excepcional
→ Rusticidad alta (Sulmtaler aguanta frío segoviano)
→ FCR ~2.9:1
```
**Por qué**: Sulmtaler aporta rusticidad alpina (similar clima a Segovia), pastoreo eficiente y carne aromática. Bresse aporta la máxima infiltración grasa y piel de seda. Es el cruce gourmet europeo por excelencia.

#### CRUCE RECOMENDADO #2 — "Ibérico Rústico" (Adaptación local)
```
♂ Pita Pinta Asturiana × ♀ Sussex
→ Capon Score estimado: ~76/100 (MUY BUENO)
→ Peso capón: 4.0-4.5 kg
→ Piel blanca, crecimiento constante
→ Máxima rusticidad (raza española adaptada)
→ FCR ~2.9:1
```
**Por qué**: Pita Pinta es una de las más pesadas autóctonas españolas, muy rústica. Sussex equilibra con piel blanca y crecimiento label. Ideal si quieres marketing "razas autóctonas".

#### CRUCE RECOMENDADO #3 — "Majestic" (Peso máximo)
```
♂ Malines (Coucou) × ♀ Faverolles
→ Capon Score estimado: ~80/100 (MUY BUENO)
→ Peso capón: 4.5-5.5 kg (capones gigantes)
→ Docilidad extrema (ideal para épinette)
→ Piel blanca-rosácea
→ FCR ~3.1:1
```
**Por qué**: Malines es la raza más pesada de Europa (5 kg ♂), Faverolles aporta mansedumbre genética extrema. Capones de lujo de +5 kg para restauración premium.

#### LÍNEA PARALELA RECOMENDADA (estrategia 2 líneas)
```
LÍNEA A (Volumen): ♂ Pita Pinta × ♀ Sussex
LÍNEA B (Gourmet): ♂ Sulmtaler × ♀ Bresse

Cruce Maestro F2: ♂ Línea A × ♀ Línea B
→ Combina estructura ibérica + delicadeza europea
→ Heterosis máxima (4 sangres distantes)
```

### 6.3 Plan de Arranque — Primer Año

#### Lote 0: Exploración (Marzo 2026 → Diciembre 2026)

| Mes | Acción | Detalle |
|---|---|---|
| **Mar-Abr** | Conseguir reproductores | 2 gallos + 6 gallinas de CADA cruce (mínimo) |
| | | Cruce 1: 2 ♂ Sulmtaler + 6 ♀ Bresse |
| | | Cruce 2: 2 ♂ Pita Pinta + 6 ♀ Sussex |
| | | **Total**: 4 gallos + 12 gallinas = 16 aves fundadoras |
| **Abr** | Cuarentena + adaptación | 2-3 semanas aislados, desparasitar, vacunar Newcastle+Marek |
| **May** | Recogida de huevos fértiles | ~8-10 huevos/gallina/mes × 12 = 96-120 huevos/mes |
| **May-Jun** | Incubación | Incubadora 100-150 huevos, 21 días, T=37.5°C, HR=55-65% |
| **Jun** | Eclosión | Esperado: 70-80% = ~70-96 pollitos |
| **Jun-Jul** | Cría arranque | Starter 22% proteína, calor 35°C, vacunas |
| **Jul-Ago** | **Caponización** (6-8 semanas) | Los machos elegidos (50-60% nacen machos) |
| | | Hembras: reservar 20% mejores para pulardas, resto para reposición |
| **Ago-Nov** | Recría en pastoreo | 10 m²/ave mínimo, grano complementario, observar comportamiento |
| **Nov** | **Épinettes** (4-5 semanas) | Engorde final: pâtée de maíz + leche, penumbra |
| **Dic** | **Primer sacrificio + venta** | ¡Navidad! Capones de ~7 meses |

#### Números del Lote 0

| Concepto | Cantidad |
|---|---|
| Reproductores fundadores | 16 aves (4♂ + 12♀) |
| Huevos fértiles (mayo-junio) | ~200 |
| Pollitos viables (75% eclosión) | ~150 |
| Machos (50%) | ~75 |
| Capones (tras caponización, 95% éxito) | ~70 |
| Mortalidad cría (5%) | -4 |
| **Capones venta Navidad** | **~65-70** |
| Pulardas (hembras seleccionadas) | ~20 |
| Hembras reposición F1 | ~30 (las mejores para criar F2) |

#### Inversión Inicial Estimada

| Concepto | Coste |
|---|---|
| 16 reproductores de raza pura | 800-1.600 € (50-100 €/ave) |
| Incubadora 150 huevos | 200-400 € |
| Gallinero móvil o fijo (20-30 aves) | 500-1.500 € |
| Épinettes (20 unidades artesanales) | 300-600 € |
| Pienso + grano (6 meses, ~70 aves) | 800-1.200 € |
| Vacunas + veterinario | 200-300 € |
| Herramientas caponización | 50-100 € |
| **TOTAL aproximado** | **2.850-5.700 €** |

#### Ingresos Esperados (Navidad Año 1)

| Producto | Unidades | Precio | Total |
|---|---|---|---|
| Capones (65 × ~4 kg × 18 €/kg) | 65 | ~72 €/capón | **4.680 €** |
| Pulardas (20 × ~3 kg × 15 €/kg) | 20 | ~45 €/pularda | **900 €** |
| Gallinas desvieje (caldo) | 10 | ~20 € | **200 €** |
| **TOTAL ingresos Año 1** | | | **~5.780 €** |

**ROI Año 1**: Ligeramente positivo o break-even. El valor real está en tener 30 gallinas F1 seleccionadas para escalar en Año 2.

### 6.4 Escala Año 2 y Siguientes

| Año | Reproductoras | Capones/Navidad | Ingresos est. |
|---|---|---|---|
| 1 (2026) | 12 fundadoras | ~65 | ~5.800 € |
| 2 (2027) | 30 F1 + 12 originales | ~200 | ~15.000 € |
| 3 (2028) | 50 F2 seleccionadas | ~400 | ~30.000 € |
| 4 (2029) | Línea F3 cerrada | ~600+ | ~45.000+ € |

### 6.5 Selección para tu Línea Propia (F1→F5)

**Criterios de selección desde F1:**

| Criterio | Cómo medir | Objetivo |
|---|---|---|
| Peso semana 12 | Báscula | >1.5 kg (machos), >1.2 kg (hembras) |
| Tarso | Visual + calibre | Fino, azulado o pizarra |
| Quilla (pecho) | Palpar | Larga, recta, ancha |
| Docilidad | Observar | Los que se dejan coger sin pánico |
| Forrajeo | Observar al amanecer | Los que salen primero a buscar insectos |
| Piel | Palpar | Elástica, no pegada al hueso |
| Plumaje | Visual | Ceñido y brillante |

**Presión de selección:**
- **F1→F2**: 20% mejores machos + 40% mejores hembras
- **F2→F3**: 10% machos + 30% hembras
- **F3→F4**: 5% machos + 30% hembras (la raza se "cierra")
- **F4→F5**: Mantener 5% machos, consanguinidad <15% (F < 0.15)

**Sacrificio de prueba**: En semana 20, sacrificar 5% del lote y analizar:
- Infiltración de grasa intramuscular (veteado)
- Color de la grasa (blanca/nacarada = bien, amarilla = problema)
- Rendimiento canal (objetivo: >68%)

### 6.6 Integración con Seedy

Seedy ya tiene todo el conocimiento avícola ingestado (colección `avicultura`, 26 razas, Capon Score). Puedes preguntarle:

```
"Seedy, ¿qué Capon Score tendría un cruce Sulmtaler × Bresse?"
"Seedy, ¿cuál es la dieta de pâtée para épinettes?"
"Seedy, ¿qué loci de color heredarán los F1 de Pita Pinta × Sussex?"
"Seedy, ¿cuándo tengo que caponizar los pollitos del lote de mayo?"
```

Y la plataforma capones.ovosfera.com tiene:
- Simulador de cruces con predicción F1 (Capon Score)
- Base de datos de 26 razas con parámetros productivos
- Análisis genético mendeliano (5 loci de color)
- Generación de imágenes IA del híbrido F1 (Flux-Schnell)
- API: `/predict-f1`, `/breeding-values`, `/genetic-analyze`

---

## 7. ARQUITECTURA DE WORKERS SEEDY (Open WebUI)

| # | Worker | Base | Colecciones | Temp | Misión |
|---|---|---|---|---|---|
| 1 | **Jefe (Planner)** | seedy:v6-local | TODAS | 0.25 | Orquestar, asignar workers, plan A-F |
| 2 | **RAG/Docs** | qwen2.5:7b | TODAS | 0.30 | Diseñar y mejorar RAG, chunking, citas |
| 3 | **IoT & Datos** | qwen2.5:7b | IoT + Twins | 0.30 | 7+1 capas PorciData, MQTT, InfluxDB |
| 4 | **Digital Twin** | qwen2.5:7b | Twins + IoT + Nutrición | 0.30 | Entidades nave/lote/animal, RL, Cesium |
| 5 | **Web/Automation** | qwen2.5:7b | Estrategia | 0.30 | Lonjas, AEMET, Sentinel-2, scraping |
| 6 | **Coder & Data** | qwen2.5:7b | IoT + Nutrición | 0.35 | Código Next.js, FastAPI, Docker, ESP32 |

---

## 8. DECISIONES DE ARQUITECTURA TOMADAS

1. **LLM producción** → Ollama local `seedy:v6-local` (objetivo) / `seedy:v5-local` (actual) + Together.ai (fallback remoto)
2. **RAG + Embeddings** → Local (mxbai-embed-large + Qdrant). Privacidad total, coste 0
3. **Rerank** → Local `bge-reranker-v2-m3` via sentence-transformers. Top K=8 → Top 3
4. **Clasificación** → Seedy como router ("¿RAG, IOT, TWIN, NUTRITION, GENETICS, GENERAL?")
5. **Digital Twin + IoT** → Local, cálculos cerca de los datos. LLM solo explica, no calcula
6. **Fine-tune** → Together.ai LoRA + merge local con peft (no usar merge de Together). v6 = 302 ej (v5+GeoTwin)
7. **GGUF** → Pipeline obligatorio: HF → F16 (`convert_hf_to_gguf.py`) → Q8_0 (`llama-quantize`)
8. **Open WebUI** → ChromaDB nativo para interfaz ganadero. Qdrant para backend FastAPI

---

*Documento consolidado a partir de 13 archivos fuente. Elimina duplicados y unifica visión.*
*Siguiente acción: limpiar archivos duplicados de conocimientos/ y reorganizar.*

---

## 9. SISTEMA DE AUTO-APRENDIZAJE (Abril 2026)

### 9.1 Feedback Loop 70B → 14B (`gold_capture.py`)

**Problema resuelto**: El 14B no aprendía de sus errores. El critic bloqueaba respuestas
pero el "elegido" era siempre un fallback genérico ("No puedo darte respuesta fiable").
33 pares DPO, todos inútiles.

**Solución**: Cuando el critic bloquea al 14B, el sistema regenera automáticamente con
el 70B (Together.ai Llama-3.3-70B-Instruct-Turbo).
- Si el 70B genera una respuesta válida (>200 chars, no genérica): se usa como respuesta Y
  se guarda como par DPO real (chosen=70B gold, rejected=14B draft).
- También se guarda como ejemplo SFT para el próximo fine-tune del 14B.
- Cada informe del 70B que pasa el critic se captura como ejemplo SFT.

**Archivos**: `gold_sft.jsonl` y `gold_dpo.jsonl` en `/app/data/`.

### 9.2 Quality Gate (`quality_gate.py`)

**Problema resuelto**: Se ingresaron 222K chunks sin ningún filtro de calidad.
Resultado: Saint-Simon, CSVs crudos, contenido fuera de dominio, 62% inglés en avicultura.

**Filtros implementados**:
- Detección de idioma por stopwords (ES/EN/FR con confianza)
- Score de calidad de contenido (diversidad léxica, frases completas, ratio numérico)
- Detección de datos tabulares/CSV crudos
- Keywords de relevancia por colección (con reject list: saint-simon, blockchain, etc.)
- Longitud mínima de chunk (50 chars default)

**Integrado en**: `ingest.py` (batch ingestion) y `daily_update.py` (fresh_web diario).

### 9.3 Knowledge Agent (`knowledge_agent.py`)

**Problema resuelto**: El daily_update solo alimentaba `fresh_web` (4K chunks). Nunca
promovía contenido bueno a las colecciones principales. No había detección de gaps.

**Ciclo cada 12h**:
1. **Gap Detection**: Analiza cada colección (diversidad fuentes, idioma dominante, longitud media)
2. **Targeted Search**: Busca contenido para gaps conocidos por vertical (7 temas, ~35 queries)
3. **Index directo**: Indexa resultados con quality gate en la colección correcta (no en fresh_web)
4. **Promote from Fresh**: Promueve chunks de fresh_web con authority >= 0.6 a colecciones principales
5. **Reporte**: Genera JSON con estadísticas del ciclo

**4 loops AutoLearn activos**: YOLO (6h), DPO (24h), Vision (24h), Knowledge (12h).

### 9.4 Limpieza Inglés v2 (3 Abril 2026)

**Auditoría post-9.2** reveló que la limpieza inicial (222K→117K) fue insuficiente:
- avicultura: 77% inglés (27K EN / 5K ES)
- iot_hardware: 77% inglés
- avicultura_intensiva: 77% inglés
- nutricion: 44% inglés
- digital_twins: 64% inglés

**Script `scripts/cleanup_english.py`**: Limpieza quirúrgica en 3 niveles:
- AGRESIVA (avicultura, iot_hardware, avicultura_intensiva): elimina TODO EN
- MODERADA (digital_twins, geotwin, bodegas_vino, nutricion): elimina EN sin keywords dominio
- LEVE (genetica, estrategia): solo EN corto sin relevancia
- Protege 4,545 chunks EN con keywords del dominio (capon, mqtt, cesium, blup, etc.)

**Resultado**: 36,984 chunks eliminados. Qdrant: 113K → 80K chunks.

| Colección | ANTES EN% | DESPUÉS EN% |
|-----------|-----------|-------------|
| avicultura | 77% | 14% |
| iot_hardware | 77% | 31% |
| avicultura_intensiva | 77% | 3% |
| nutricion | 44% | 9% |
| digital_twins | 64% | 37% |
| bodegas_vino | 52% | 12% |
| geotwin | 58% | 30% |

**Quality gate actualizado**: `validate_chunk()` ahora auto-rechaza inglés en colecciones
ES-primarias (avicultura, nutricion, normativa, avicultura_intensiva, bodegas_vino, iot_hardware)
sin necesidad de `require_spanish=True` explícito.

### 9.5 Knowledge Agent — Fix Búsqueda (3 Abril 2026)

**Bug**: `filter_results(results, set())` pasaba `set()` como `min_authority` → TypeError.
Resultado: 0 búsquedas por ciclo, solo hacía promoción de fresh_web.

**Fix**: Corregido argumento. Primer ciclo exitoso: 15 búsquedas, 60 chunks indexados, 50 promovidos.

### 9.6 Estado del modelo (3 Abril 2026)

| Componente | Anterior | Actual |
|------------|----------|--------|
| LLM producción | seedy:v16 (Qwen2.5-14B Q4_K_M) | seedy:v16 (sin cambio) |
| Qdrant chunks | 117K (contaminados EN) | **80K** (limpiados, 25% EN) |
| DPO pairs útiles | 0/33 | Auto-generados por gold_capture (verificado) |
| Ingesta quality gate | Penalizaba EN, no rechazaba | **Rechaza EN automáticamente** en ES-primary |
| Knowledge agent | Búsqueda rota | **Funcionando**: 15 búsquedas/ciclo, 60+50 chunks |
| Evidence extractor | SIN_HECHOS en chunks reales | **Funciona**: prompt simplificado, 10K context |
| Búsqueda avicultura | 77% resultados EN | **100% ES** en top 8 |
