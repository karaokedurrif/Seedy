# Seedy — Documentación Técnica de Pipelines

> Documento generado el 6 de abril de 2026 · Versión actual: seedy:v16 (Q4_K_M)

---

## Índice

1. [Pipeline de Texto (RAG)](#1-pipeline-de-texto-rag)
2. [Pipeline de Visión](#2-pipeline-de-visión)
3. [Mejoras Propuestas](#3-mejoras-propuestas)

---

## 1. Pipeline de Texto (RAG)

### 1.1 Flujo completo

```
Usuario (Open WebUI / API)
    │
    ▼
[0] Extracción de URLs ──────── Si la query contiene URLs → crawl4ai (:11235)
    │                            extrae contenido y lo inyecta como contexto extra
    ▼
[1] Reescritura de query ────── Together.ai (Qwen2.5-7B, temp=0, max_tokens=40)
    │                            Corrige typos de razas (sulmtahler → Sulmtaler)
    │                            Usa últimos 4 mensajes como contexto multi-turno
    ▼
[2] Clasificación Multi-Label ─ Together.ai (Qwen2.5-7B, temp=0, max_tokens=40)
    │                            Formato: "AVICULTURA:0.85,GENETICS:0.70"
    │                            Umbral mínimo: 0.3, máx 3 categorías
    │                            Cache LRU (TTL=600s, max=256)
    ▼
[3] Clasificación Temporal ──── Together.ai (Qwen2.5-7B, temp=0, max_tokens=10)
    │                            → STABLE | SEMI_DYNAMIC | DYNAMIC | BREAKING
    │                            Determina si se fuerza búsqueda web
    ▼
[4] Selección de colecciones ── Mapeo categoría → colecciones Qdrant
    │
    │   IOT           → {iot_hardware, digital_twins}
    │   TWIN          → {digital_twins, iot_hardware, geotwin}
    │   NUTRITION     → {nutricion}
    │   GENETICS      → {genetica, avicultura}
    │   AVICULTURA    → {avicultura, genetica, nutricion, estrategia}
    │   AVI_INTENSIVA → {avicultura_intensiva, nutricion, normativa}
    │   VINO          → {bodegas_vino, estrategia, normativa}
    │   NORMATIVA     → {normativa}
    │   INFORME       → todas las colecciones
    │   GENERAL       → todas las colecciones
    ▼
[5] Filtrado de metadatos ──── Heurísticas pre-búsqueda por colección:
    │                           • Queries de razas → excluir CSVs de sensores
    │                           • Colección avicultura → excluir fuentes ruidosas
    │                           • Detección de especie (aviar/porcino/vacuno/ovino)
    ▼
[6] Búsqueda Híbrida (Qdrant) ─ DUAL-QUERY con fusión RRF
    │
    │   ┌─ Dense (query reescrita) ─── mxbai-embed-large 1024d ──┐
    │   ├─ Dense (query original)  ─── si ≠ reescrita ───────────┤ RRF
    │   └─ Sparse BM25 (query reescrita) ─── hash-based TF ─────┘ k=60
    │
    │   Búsqueda por colección: limit = top_k × 2 (60 hits/col)
    │   Fusión RRF: score += 1/(60 + rank + 1) por cada ranking list
    │   BM25 weight: 1.0 (igual que dense)
    │   Top-K final: 30 resultados fusionados
    ▼
[7] Búsqueda Web (SearXNG) ── CONDICIONAL
    │
    │   Se activa si:
    │   • Mejor score RAG < 0.012
    │   • Temporalidad = DYNAMIC o BREAKING
    │   • Intent de producto (comprar, precio, tienda...)
    │   • Modo INFORME + keywords de hardware
    │
    │   SearXNG (:8888) → solo motores ES → max 5 resultados (8 si producto)
    ▼
[8] Reranking ──────────────── bge-reranker-v2-m3 (CrossEncoder, max_length=512)
    │
    │   • Scoring: cross-encoder(query, chunk_text) → 0.0-1.0
    │   • Penalización idioma: chunk en inglés + query en español → ×0.7
    │   • Diversificación: máx 2 chunks por source_file
    │   • Top-N: 8 chunks (15 para INFORME)
    ▼
[9] Extracción de evidencia ── Together.ai (Qwen-7B)
    │                           Extrae hechos verificables del contexto RAG
    │                           Deduplicación por similitud textual (umbral 0.75)
    ▼
[10] Ensamblaje de contexto ── Se compone el prompt:
    │
    │   [SYSTEM PROMPT]
    │   ├─ SEEDY_SYSTEM (prompt general con prohibiciones y reglas epistémicas)
    │   └─ WORKER_PROMPT (específico por categoría: AVICULTURA, GENETICS, etc.)
    │
    │   [CONTEXTO]
    │   ├─ Chunks RAG (con [Fuente N] para citación)
    │   ├─ Chunks Web (si los hay)
    │   ├─ Chunks URL (si el usuario envió enlaces)
    │   └─ Evidencia extraída
    │
    │   [HISTORIAL]
    │   └─ Últimos mensajes del usuario
    ▼
[11] Generación LLM
    │
    │   Modo normal:
    │   └─ Ollama local → seedy:v16 (RTX 5080)
    │      temp=0.3, top_p=0.9, max_tokens=1024, repeat_penalty=1.1
    │
    │   Modo INFORME:
    │   └─ Together.ai → Llama-3.3-70B-Instruct-Turbo
    │      temp=0.5, max_tokens=4096 (salida Markdown rica)
    │
    │   Fallback (si Ollama falla):
    │   └─ Together.ai → Qwen2.5-7B-Instruct-Turbo
    ▼
[12] Critic Gate ───────────── Together.ai (Llama-3.3-70B, timeout=30s)
    │
    │   Veredicto binario: PASS o BLOCK
    │   Detecta: especie_incorrecta, ruido_rag, incoherencia
    │   Bypass: si la respuesta admite "no tengo información"
    │   Si BLOCK → respuesta fallback o captura para DPO
    ▼
[13] Critic Técnico ────────── Validación adicional de datos técnicos
    │
    ▼
[14] Post-procesamiento ────── Strip Markdown excepto en INFORME
    │
    ▼
Respuesta (formato OpenAI-compatible)
```

### 1.2 Parámetros clave

| Parámetro | Valor | Fichero |
|-----------|-------|---------|
| Embedding model | mxbai-embed-large (1024d) | config.py |
| Embedding max tokens | ~512 | mxbai-embed-large limit |
| RRF k | 60 | rag.py |
| Top-K pre-rerank | 30 | config.py |
| Top-N post-rerank | 8 (normal), 15 (INFORME) | config.py |
| BM25 weight | 1.0 | config.py |
| Reranker | bge-reranker-v2-m3 | reranker.py |
| Reranker max length | 512 tokens | reranker.py |
| Diversificación | max 2 chunks/source | reranker.py |
| Penalización EN→ES | ×0.7 | reranker.py |
| Web search threshold | score < 0.012 | web_search.py |
| Classifier cache TTL | 600s | classifier.py |
| LLM temperature | 0.3 (normal) / 0.5 (INFORME) | llm.py |
| LLM max tokens | 1024 (normal) / 4096 (INFORME) | llm.py |
| Repeat penalty | 1.1 | llm.py |
| Critic timeout | 30s | critic.py |
| Chunk size (ingesta) | 1500 chars / 300 overlap | chunker.py |

### 1.3 Colecciones Qdrant (11)

| Colección | ~Chunks | Dominio |
|-----------|---------|---------|
| avicultura | ~170K | Capones, razas, cruces, extensiva |
| genetica | ~3K | BLUP/EPDs, consanguinidad |
| nutricion | ~340 | Formulación, piensos |
| iot_hardware | ~155 | PorciData, sensores, MQTT |
| digital_twins | ~325 | Gemelos digitales, Cesium |
| estrategia | ~175 | Competencia, mercado, PEPAC |
| normativa | ~55 | RD 306/2020, SIGE, ECOGAN |
| geotwin | ~65 | GIS 3D, PNOA |
| avicultura_intensiva | — | Producción intensiva |
| bodegas_vino | — | Viticultura, bodegas |
| fresh_web | ~200 | Contenido web diario (expira 60d) |

### 1.4 Modelos involucrados

| Modelo | Uso | Ubicación |
|--------|-----|-----------|
| seedy:v16 (Q4_K_M) | Generación principal | Ollama (RTX 5080) |
| mxbai-embed-large | Embeddings 1024d | Ollama |
| Qwen2.5-7B-Instruct-Turbo | Rewriter, classifier, evidence | Together.ai |
| Llama-3.3-70B-Instruct-Turbo | Critic, INFORME | Together.ai |
| bge-reranker-v2-m3 | Cross-encoder reranking | Local (CUDA) |

---

## 2. Pipeline de Visión

### 2.1 Infraestructura de cámaras

```
Cámaras físicas (subred 10.10.10.x)
    │
    ├── TP-Link VIGI C340 (10.10.10.11) ─── Gallinero Durrif I (4K H.265)
    ├── TP-Link VIGI C340 (10.10.10.10) ─── Gallinero Durrif II (4K H.265)
    └── Dahua WizSense (10.10.10.108) ───── Sauna Durrif (4K H.265)
    │
    ▼
go2rtc (:1984, host network) ─── Proxy RTSP → WebRTC/MJPEG/MSE
    │
    │   Cada cámara tiene 3 streams:
    │   • Main: 4K H.265 original
    │   • Sub: resolución reducida H.264
    │   • Web: stream optimizado para navegador
    │
    ▼
Métodos de captura:
    • CGI snapshot: 704×576, ~100ms (rápido, baja res)
    • go2rtc frame: 4K JPEG, ~1s
    • MJPEG: streaming continuo
    • MSE WebSocket: real-time para navegador
```

### 2.2 Pipeline de identificación

```
[1] CAPTURA ─────── CGI snapshot (704×576) o go2rtc frame (4K)
    │
    ▼
[2] YOLO COCO ──── Detección general (YOLOv8s)
    │               Clases: bird(14), cat(15), dog(16), cow(21)
    │               imgsz: 1280 (normal) o 1920 (cámara lejana)
    │               Latencia: ~150ms en RTX 5080
    │
    │   ¿Detección lejana/pequeña?
    │   └─ Sí → detect_tiled() (SAHI, solapamiento de tiles)
    ▼
[3] CROP ────────── Recorte de cada detección (bbox → imagen individual)
    │               estimate_body_size() → pollito/juvenil/adulto
    ▼
[4] YOLO RAZAS ─── seedy_breeds_best.pt (12 clases de razas locales)
    │
    │   12 clases: Vorwerk♀♂, Sussex Silver♀♂, Sussex White♀,
    │              Sulmtaler♀♂, Marans♀, Bresse♀♂,
    │              Andaluza Azul♀, Pita Pinta♀
    │
    │   ¿Confianza suficiente?
    │   ├─ Sí → Raza identificada localmente (~70ms)
    │   └─ No → paso 5
    ▼
[5] GEMINI ──────── Gemini 2.0 Flash (→ 2.5 Flash → Lite como fallback)
    │               Prompt de experto veterinario (26 razas definidas)
    │               Output JSON: {breed, color, sex, confidence, features}
    │               Latencia: 2-5s
    │               Guarda imagen+respuesta en /vision_dataset/ para LoRA
    ▼
[6] VALIDACIÓN ─── Contraste contra flock_census.json
    │               25 aves esperadas en 2 gallineros
    │               Corrección fuzzy de nombres de razas
    ▼
[7] TRACKING ───── bird_tracker.py (centroide + IoU)
    │               IOU_THRESHOLD: 0.25
    │               Historial: 120 frames por track
    │               Zonas: comedero, bebedero, aseladero, nido, zona_libre
    ▼
[8] REGISTRO ───── POST /birds/register → PAL-2026-XXXX
    │               Persistido en data/birds_registry.json
    │               ai_vision_id: sussexwh1 (raza + color + secuencia)
    ▼
[9] SYNC ────────── POST /ovosfera/sync/vision-id → hub.ovosfera.com
    │
    ▼
Salida: Ave identificada, rastreada y registrada
```

### 2.3 Sistema de alertas y plagas

```
YOLO detecta gorrión/paloma/rata
    │
    ▼
pest_alert.py ─────── Debouncing: 60s entre alertas del mismo tipo
    │                   Escalación: 3 frames consecutivos → severidad alta
    │                   MQTT → seedy/vision/alerts/{severity}
    │
    │   ¿3+ gorriones detectados en 3 ciclos YOLO consecutivos?
    │   └─ Sí → disparar disuasión
    ▼
sparrow_deterrent.py ── Plan de vuelo Bebop 2:
                         • 20m adelante, 2.5m altitud, 5s hover, retorno
                         • Seguridad: max 5 vuelos/hora, 20/día
                         • Horario: solo 07:00-22:00
                         • Cooldown: 120s entre vuelos
                         • Min batería: 30%, max viento: 25 km/h
                         • Bridge HTTP → Dell Latitude (192.168.20.102)
                                          → Olympe SDK → Bebop 2
```

### 2.4 Análisis de salud

```
bird_tracker.py (posiciones) + telemetry.py (clima)
    │
    ▼
health_analyzer.py
    │
    │   Score = 0.35×movilidad + 0.30×alimentación + 0.20×social + 0.15×zonas
    │
    │   Alertas:
    │   • Salud < 60%
    │   • Nadie alimentándose
    │   • Estrés excesivo
    │   • Inmovilidad prolongada
    │   • Aislamiento del grupo
    │   • Permanencia excesiva en nido
    ▼
Modelo de crecimiento Gompertz por raza+sexo → /birds/{id}/gompertz
```

### 2.5 Telemetría IoT (Zigbee)

```
Sensores eWeLink CK-TLSR8656 (gallinero_durrif_1/2)
    │
    ▼
Zigbee2MQTT (mini PC 192.168.40.128, canal 15)
    │   Routers mesh: 2× Tuya TS011F plugs
    ▼
MQTT (Mosquitto :1883) ── topic: zigbee2mqtt/{friendly_name}
    │                       payload: {temperature, humidity, battery, linkquality}
    ▼
telemetry.py ──── Subscriber MQTT → escritura InfluxDB
    │              measurement: gallinero_climate
    │              tags: sensor, gallinero, gallinero_id
    ▼
InfluxDB (:8086) ── org=neofarm, bucket=porcidata
    │
    ├── API: GET /ovosfera/devices/status → resumen por gallinero
    ├── API: GET /ovosfera/devices/history → series temporales
    └── Grafana (:3001) → seedy-grafana.neofarm.io
```

### 2.6 Endpoints principales

| Endpoint                              | Método | Función                              |
|---------------------------------------|--------|--------------------------------------|
| `/vision/identify/snapshot/{s}/detect`| GET    | Solo YOLO (~150ms)                   |
| `/vision/identify/snapshot/{s}/yolo`  | GET    | Frame anotado con YOLO               |
| `/vision/identify/snapshot/{s}/identify`| GET  | Pipeline completo (YOLO+Gemini)      |
| `/vision/identify/start-loop`         | POST   | Captura continua (cada 4s)           |
| `/vision/identify/auto-identify`      | POST   | Identificar todas las aves (batch)   |
| `/vision/event`                       | POST   | Ingestar detecciones                 |
| `/vision/weight`                      | POST   | Estimaciones de peso                 |
| `/vision/alert`                       | POST   | Alertas de comportamiento            |
| `/birds/`                             | GET    | Listar aves (filtros: gallinero, raza)|
| `/birds/register`                     | POST   | Registrar ave → PAL-2026-XXXX        |
| `/birds/{id}/gompertz`                | GET    | Curva de crecimiento                 |
| `/ovosfera/camera/{id}/snapshot`      | GET    | Proxy snapshot cámara                |
| `/ovosfera/camera/{id}/mjpeg`         | GET    | Proxy MJPEG live                     |
| `/ovosfera/stream/{name}/mse`         | WS     | WebSocket MSE para navegador         |
| `/ovosfera/devices/status`            | GET    | Clima por gallinero                  |
| `/ovosfera/devices/history`           | GET    | Serie temporal InfluxDB              |
| `/api/dron/sparrow-deterrent`         | POST   | Vuelo disuasión manual               |
| `/api/dron/status`                    | GET    | Estado del dron                      |

### 2.7 Modelos de visión

| Modelo | Uso | Latencia | Ubicación |
|--------|-----|----------|-----------|
| YOLOv8s (COCO) | Detección general (bird/cat/dog/cow) | ~150ms | Local RTX 5080 |
| seedy_breeds_best.pt | Clasificación raza (12 clases) | ~70ms | Local RTX 5080 |
| Gemini 2.0 Flash | ID de razas (26 razas) | 2-5s | Google API |
| Gemini 2.5 Flash | Fallback si 429 | 2-5s | Google API |

---

## 3. Mejoras Propuestas

### 3.1 Pipeline de Texto — Mejoras Críticas

#### A. Chunking adaptativo por tipo de documento

**Problema actual**: `chunker.py` usa 1500 chars / 300 overlap para todo. Los PDFs avícolas franceses se fragmentan rompiendo tablas y secciones. Documentos de referencia concisos (markdown) obtienen pocos hits BM25 al no repetir keywords.

**Mejora**: Chunking adaptativo según tipo:
- **Markdown**: split por headers `##` (mantener secciones completas)
- **PDF con tablas**: detectar bloques tabulares y no cortarlos
- **PDFs grandes**: 1500/300 (actual) pero con sliding window semántico
- **Documentos de referencia**: añadir prefijo de keywords automáticamente (como se hizo con RAZAS_FRANCESAS)

#### B. Modelo de embeddings mejorado

**Problema actual**: `mxbai-embed-large` tiene contexto de ~512 tokens. Chunks > 1800 chars fallan. Además, su rendimiento en español es inferior a modelos bilingües especializados.

**Mejora**: Migrar a `multilingual-e5-large-instruct` (1024d, 8192 tokens de contexto) o `nomic-embed-text-v2` (2048 tokens). Ambos tienen mejor rendimiento multilingüe y admitirían chunks más largos sin error.

#### C. Late Interaction o ColBERT para retrieval

**Problema actual**: Dense (single-vector) pierde información local de tokens. Una query "razas francesas para capones" activa "razas" y "capones" pero el vector solo captura el significado global.

**Mejora**: Implementar ColBERT-style late interaction como tercer canal en RRF. Qdrant ya soporta multi-vectors. Esto mejoraría el recall para queries con múltiples conceptos específicos (raza + origen + uso).

#### D. Query routing con Few-Shot y LLM más potente

**Problema actual**: El clasificador Qwen-7B parsea texto libre ("AVICULTURA:0.85") que a veces falla en formato. Las 10 categorías no siempre mapean bien a las 11 colecciones.

**Mejora**:
- Usar structured output (JSON mode) del clasificador
- Añadir few-shot examples al prompt del clasificador
- Considerar Llama-3.1-8B-Instruct para clasificación (mejor instruction following que Qwen-7B)

#### E. Reranker con contexto de historial

**Problema actual**: El reranker solo ve `(query, chunk)`. No sabe que el usuario lleva 5 mensajes hablando de capones franceses.

**Mejora**: Concatenar los últimos 2-3 mensajes del historial a la query del reranker: `(query + historial_resumen, chunk)`. Esto mejoraría la relevancia en conversaciones multi-turno.

#### F. Generación con citación forzada

**Problema actual**: El modelo a veces ignora el contexto RAG y genera de su conocimiento parametric (que puede ser incorrecto).

**Mejora**:
- Forzar citación con instrucción explícita: "Responde SOLO basándote en las [Fuente N]. Si ninguna fuente cubre la pregunta, di que no tienes información."
- Implementar Attributed QA: el post-procesamiento verifica que cada afirmación tenga una cita a una fuente.
- Considerar CRAG (Corrective RAG): si la respuesta no cita fuentes, re-generar con instrucciones más estrictas.

#### G. Fine-tune v17 con correcciones SFT

**Problema actual**: El modelo fine-tuned (v16) ha aprendido patrones incorrectos (llamar Sulmtaler "francesa", añadir presupuestos no solicitados). Las correcciones de prompt solo mitigan parcialmente.

**Mejora**: Incorporar `seedy_dataset_corrections_chat_quality.jsonl` (6 ejemplos correctivos) + generar 20-30 más basados en errores reales del chat → entrenar v17 con estos ejemplos + dataset existente. Evaluar con los mismos 6 chats como benchmark.

#### H. Graph RAG para relaciones entre razas

**Problema actual**: Los cruces (Sulmtaler × Bresse → capón premium) se almacenan como texto plano. No hay forma de hacer queries relacionales ("¿qué cruces dan capones >5 kg?").

**Mejora**: Construir un knowledge graph (Neo4j o NetworkX) con:
- Nodos: razas, cruces, características
- Aristas: "produce_F1", "aporta_genes", "origen_país"
- El retriever consulta el grafo + Qdrant, fusionando resultados

### 3.2 Pipeline de Visión — Mejoras Críticas

#### A. YOLO v11 + entrenamiento con más clases

**Problema actual**: `seedy_breeds_best.pt` tiene 12 clases, todas del gallinero actual. No detecta razas nuevas que se añadan al rebaño.

**Mejora**:
- Migrar a YOLOv11 (mejor precision en objetos pequeños)
- Ampliar dataset con las fotos que Gemini ya acumula en `/vision_dataset/`
- Ciclo automático: 500+ imágenes etiquetadas por Gemini → reentrenar breed YOLO → reload modelo (endpoint ya existe: `/vision/identify/yolo/reload-breed`)

#### B. Re-identificación individual (Re-ID)

**Problema actual**: El tracker usa centroide + IoU entre frames consecutivos, pero pierde el tracking si el ave sale de cuadro y vuelve. No distingue dos Sussex White entre sí.

**Mejora**: Implementar un modelo de Re-ID basado en embeddings visuales:
- Extraer embedding (512d) por crop de ave
- Comparar contra galería de embeddings registrados (por bird_id)
- Usar ArcFace o similar entrenado en las fotos del propio gallinero
- Esto permitiría identificar aves individualmente sin anillas físicas

#### C. Estimación de peso por visión

**Problema actual**: El endpoint `/vision/weight` existe pero la estimación es heurística (tamaño de bbox → categoría pollito/juvenil/adulto).

**Mejora**:
- Entrenar un regresor (MLP sobre features YOLO + dimensiones bbox + raza) con pesajes reales
- Usar calibración de cámara (distancia conocida) para convertir pixels → cm
- Integrar con la curva Gompertz: el modelo predice peso, Gompertz valida si está en rango esperado para la edad

#### D. Visión nocturna con IR

**Problema actual**: Las cámaras TP-Link VIGI tienen IR pero YOLO se entrena con imágenes diurnas. La detección nocturna baja drásticamente.

**Mejora**:
- Incluir imágenes IR/nocturnas en el dataset de entrenamiento
- Domain adaptation: fine-tune YOLO con imágenes nocturnas anotadas
- Alternativamente, un pre-procesador que normalice la imagen IR a pseudo-diurna (histogram equalization + color mapping)

#### E. Multi-cámara fusión 3D

**Problema actual**: Cada cámara procesa de forma independiente. Un ave visible en 2 cámaras podría registrarse dos veces.

**Mejora**:
- Calibración estéreo de cámaras (homografía plano del gallinero)
- Fusión de detecciones multi-cámara por posición 3D estimada
- Mapa de presencia en planta del gallinero (heatmap de actividad)
- Integrar con los planos 2D ya cargados (`gallinero_durrif_1.json`, `gallinero_durrif_2.json`)

#### F. Edge processing para latencia

**Problema actual**: Los frames 4K viajan por red al host MSI, se procesan en GPU y el resultado vuelve. Latencia total ~2.5s.

**Mejora**: Desplegar un modelo YOLO cuantizado (INT8, TensorRT) en modo streaming directamente sobre go2rtc. Procesar cada N frames (no todos) y solo enviar detecciones al backend para ID por Gemini.

### 3.3 Mejoras Transversales

#### A. Observabilidad end-to-end

**Mejora**: Implementar tracing con OpenTelemetry o un sistema similar:
- Cada request genera un trace_id
- Cada paso del pipeline (rewriter, classifier, rag, reranker, llm, critic) se registra con latencia y payload resumen
- Dashboard en Grafana con métricas: latencia P50/P95 por paso, tasa de BLOCK del critic, score medio de reranker

#### B. AutoEval continuo

**Mejora**: Crear un benchmark de 50 preguntas (las 6 de los chats fallidos + 44 más cubriendo todas las categorías). Ejecutar semanalmente tras cada actualización del RAG o fine-tune. Evaluar con LLM-as-judge (Llama-70B) en 3 dimensiones: precisión factual, relevancia, completitud.

#### C. DPO automatizado

**Mejora**: Los BLOCKs del critic + los thumbs-down de Open WebUI ya se capturan. Automatizar:
1. Recopilar pares (prompt, respuesta_rechazada)
2. Generar respuesta_preferida con Llama-70B + contexto RAG completo
3. Cada 2 semanas: entrenar DPO sobre seedy:v16 → v17
4. Evaluar con AutoEval antes de poner en producción

#### D. Capa de Análisis Conductual por Ave

**Problema actual**: El tracker (`bird_tracker.py`) calcula posiciones y zonas, y el health analyzer genera un score agregado (movilidad + alimentación + social + zonas). Pero no hay análisis conductual individual: no podemos responder "¿la gallina negra come poco?" ni detectar dominancia, subordinación, estrés o aislamiento de un ave concreta. Cuando el usuario pregunta por comportamiento, el RAG no tiene chunks conductuales que servir.

**Mejora**: Implementar una capa completa de análisis conductual, incremental sobre la arquitectura existente. Spec detallada en `SEEDY_COMPORTAMIENTO_COPILOT_PROMPT.md`.

**Componentes nuevos (6 ficheros)**:

| Fichero | Función |
|---------|---------|
| `behavior_features.py` | Calcula ~25 features por ave y ventana temporal (visitas comedero/bebedero, movilidad, interacciones sociales, ratios vs grupo, delta vs baseline propio). Dataclass `BirdBehaviorFeatures` con `data_completeness` como gate |
| `behavior_inference.py` | Transforma features en etiquetas conductuales (`possible_aggressive`, `probable_dominant`, `low_feeding`, `possible_stress`, `relevant_isolation`, `anomalous_nesting`) con nivel de certeza (weak/consistent/high/inconclusive). Reglas heurísticas multi-señal: nunca inferir por un evento aislado |
| `behavior_baseline.py` | Historial individual + grupo para comparación temporal. Persistencia en JSON (`data/behavior_baselines/`). Gate: si <3 ventanas de historial → "insufficient_history" |
| `behavior_serializer.py` | Convierte inferencias a texto compacto (<400 tokens) para inyectar en contexto RAG o como chunk de Qdrant |
| `tests/test_behavior_features.py` | Tests con fixtures sintéticos (ave normal, baja completitud, gallinero con 1 ave, ventana <30 min) |
| `tests/test_behavior_inference.py` | Tests de reglas heurísticas (umbrales, edge cases, no crashear con datos faltantes) |

**Modificaciones quirúrgicas al pipeline existente**:
- `classifier.py`: Nueva categoría `COMPORTAMIENTO` con keywords (comedero, agresiva, aislada, estrés...)
- `rag.py`: Mapeo `COMPORTAMIENTO → {behavior_events, vision_events, avicultura}`
- Paso [10] (ensamblaje): Inyectar `BehaviorSummary` como contexto privilegiado cuando la query es conductual

**4 endpoints nuevos**:
- `GET /birds/{id}/behavior?window=24h` → Inferencia conductual completa
- `GET /birds/{id}/behavior/features?window=24h` → Features raw
- `GET /birds/behavior/group?gallinero_id=...&window=24h` → Grupo completo
- `GET /vision/behavior/summary?gallinero_id=...&window=24h` → Resumen dashboard

**Reglas de seguridad epistémica**:
- `data_completeness < 0.4` → todas las inferencias "inconclusive"
- Agresividad requiere ≥2 señales simultáneas (displacement + chase o social indicators)
- Dominancia requiere ≥3 señales consistentes a lo largo de la ventana
- Nivel de ingesta compara 3 fuentes independientes (baseline propio, media grupo, franja horaria)

**Puntos a refinar antes de implementar**:
1. **Persistencia del tracking**: El tracker mantiene 120 frames en RAM (~8 min a 4s/frame). Para ventanas de 6-24h hay que persistir posiciones agregadas por sub-ventanas (sugerencia: buckets de 15 min en JSON)
2. **Approach de inyección RAG**: Mejor inyectar on-demand en el contexto del paso [10] cuando la query es COMPORTAMIENTO, en lugar de generar chunks periódicos en Qdrant — reduce coste y garantiza frescura
3. **Correlación con clima**: Vincular `telemetry.py` (temperatura, humedad del Zigbee) con behavior_inference. Si hace >35°C y las aves comen menos, es termorregulación, no estrés
4. **Calibración de umbrales**: Los valores de displacement (50px), chase (3 frames), isolation (10th percentile) son iniciales. Necesitan calibración con datos reales del gallinero

---

> **Prioridad recomendada**: G (fine-tune v17) > F (citación forzada) > A (chunking adaptativo) > B (embeddings mejorados) para texto. A (YOLO v11) > B (Re-ID) > D (análisis conductual) > C (peso por visión) para visión. D transversal (conductual) es la mejora de mayor impacto funcional.
