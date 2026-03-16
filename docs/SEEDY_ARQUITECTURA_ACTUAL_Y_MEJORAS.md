# SEEDY -- Arquitectura Actual y Propuesta de Mejoras

> Documento generado: 9 de marzo de 2026
> Versión del modelo: seedy:v13 (Qwen2.5-14B-Instruct + LoRA, Q4_K_M, 8.4 GB)

---

## 1. VISIÓN GENERAL

Seedy es un asistente técnico de IA especializado en agrotech, ganadería de precisión y avicultura extensiva, desplegado como stack Docker on-premises sobre una RTX 5080 (16 GB VRAM). Opera a través de Open WebUI y expone una API OpenAI-compatible.

Todo el stack corre en una sola máquina y es accesible remotamente vía Cloudflare Tunnel.

---

## 2. ARQUITECTURA DEL PIPELINE

```
┌──────────────────────────────────────────────────────────────────┐
│                    OPEN WEBUI (:3000)                            │
│              "Seedy -- NeoFarm AI"                               │
│         Modelos: seedy | seedy-vision                            │
└──────────────┬───────────────────────────────────────────────────┘
               │ /v1/chat/completions
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                 SEEDY BACKEND (FastAPI :8000)                     │
│                                                                  │
│  1. DETECCION DE MODALIDAD                                       │
│     ├─ Texto  → Pipeline RAG                                    │
│     └─ Imagen → Gemini 2.5 Flash (visión)                       │
│                                                                  │
│  PIPELINE RAG (texto):                                           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 0a. URL Fetcher (crawl4ai)                                │  │
│  │     Si la query contiene URLs → crawlear y extraer texto  │  │
│  │                                                            │  │
│  │ 0b. Query Rewriter (Together.ai Qwen2.5-7B)              │  │
│  │     Reformula con contexto conversacional para RAG        │  │
│  │                                                            │  │
│  │ 1.  Clasificador de Categoría (Together.ai Qwen2.5-7B)   │  │
│  │     IOT | TWIN | NUTRITION | GENETICS | NORMATIVA |       │  │
│  │     AVICULTURA | GENERAL                                   │  │
│  │     + hint de categoría previa (coherencia multi-turno)   │  │
│  │                                                            │  │
│  │ 2.  Clasificador de Temporalidad (Together.ai Qwen2.5-7B)│  │
│  │     STABLE | SEMI_DYNAMIC | DYNAMIC | BREAKING            │  │
│  │     Determina si forzar búsqueda web                      │  │
│  │                                                            │  │
│  │ 3.  Búsqueda RAG Híbrida en Qdrant                       │  │
│  │     - Dense (mxbai-embed-large, 1024 dim, cosine)         │  │
│  │     - Sparse (BM25)                                       │  │
│  │     - Dual-query: reescrita + original (mejor recall)     │  │
│  │     - Colecciones según categoría                         │  │
│  │     - Si DYNAMIC/BREAKING → incluir fresh_web             │  │
│  │                                                            │  │
│  │ 4.  Búsqueda Web (SearXNG)                               │  │
│  │     Disparada por:                                        │  │
│  │     a) Temporalidad DYNAMIC/BREAKING (forzada)            │  │
│  │     b) RAG insuficiente (score < 0.012 RRF)              │  │
│  │                                                            │  │
│  │ 5.  Reranker (bge-reranker-v2-m3, CrossEncoder)           │  │
│  │     Top K=20 → Top N=8 diversificados                     │  │
│  │     Max 2 chunks por documento (evita monopolio)          │  │
│  │                                                            │  │
│  │ 6.  LLM (Ollama seedy:v13, RTX 5080)                     │  │
│  │     System prompt epistemológico (11 principios)          │  │
│  │     + Worker prompt por dominio                           │  │
│  │                                                            │  │
│  │ 7.  Critic Gate (Together.ai Llama-3.3-70B)              │  │
│  │     PASS → enviar respuesta                               │  │
│  │     BLOCK → fallback seguro                               │  │
│  │     Detecta: confusión de especie, items no-animal,       │  │
│  │     incoherencia, markdown excesivo                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  PIPELINE VISION (imágenes):                                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Gemini 2.5 Flash → identificar raza, especie, sexo, etc. │  │
│  │ Auto-save par (imagen, respuesta) para futuro LoRA        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  JOB DIARIO (Circuito B offline):                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Cada 24h → 32 queries × 7 verticales → SearXNG           │  │
│  │ → Filtro autoridad (min 0.3) + dedup hash                │  │
│  │ → Indexar en colección fresh_web                          │  │
│  │ → Expirar contenido > 60 días                             │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. INFRAESTRUCTURA DOCKER

| Contenedor | Servicio | Puerto | Función |
|------------|----------|--------|---------|
| open-webui | Open WebUI v0.8.8 | :3000 | Frontend chat |
| seedy-backend | FastAPI (Python 3.11) | :8000 | Pipeline RAG + API OpenAI |
| ollama | Ollama | :11434 | LLM local (seedy:v13, seedy-vision) |
| qdrant | Qdrant | :6333 | Base vectorial (9 colecciones) |
| searxng | SearXNG | :8888 | Meta-buscador web |
| crawl4ai | Crawl4AI | :11235 | Extractor de contenido web |
| cloudflared | Cloudflare Tunnel | - | Acceso remoto seguro |
| influxdb | InfluxDB | :8086 | Telemetría IoT |
| grafana | Grafana | :3001 | Dashboards |
| mosquitto | MQTT Broker | :1883 | Mensajería IoT |
| nodered | Node-RED | :1880 | Flujos IoT |

Hardware: NVIDIA GeForce RTX 5080 (16 GB VRAM), 937 GB disco, Linux.

---

## 4. MODELOS

### 4.1 LLM Principal
- **seedy:v13** -- Qwen2.5-14B-Instruct + fine-tune LoRA NeoFarm
- Cuantización: Q4_K_M (8.4 GB en disco, ~9 GB en Ollama)
- Context window: 32K tokens
- GPU: 100% offload a RTX 5080

### 4.2 Embeddings
- **mxbai-embed-large** -- 1024 dimensiones, cosine similarity
- Ejecutado en Ollama (local)

### 4.3 Reranker
- **BAAI/bge-reranker-v2-m3** -- CrossEncoder, max_length=512
- Precargado al inicio (warm-up para evitar cold-start de 150s)
- Ejecutado en CPU (sentence-transformers)

### 4.4 Clasificadores (cloud, Together.ai)
- **Qwen2.5-7B-Instruct-Turbo** -- clasificador de categoría, rewriter, temporalidad
- **Llama-3.3-70B-Instruct-Turbo** -- critic gate (evaluador de calidad)

### 4.5 Visión
- **Gemini 2.5 Flash** (API Google) -- identificación visual de razas
- Fallback: Gemini 2.0 Flash, Gemini 2.0 Flash Lite
- **seedy-vision** (Ollama, llama3.2-vision:11b) -- modelo vision local de backup

---

## 5. BASE DE CONOCIMIENTOS (Qdrant)

9 colecciones con búsqueda híbrida (dense + BM25):

| Colección | Chunks | Dominio |
|-----------|--------|---------|
| avicultura | 169.640 | Capones, razas avícolas, cruces, producción extensiva |
| genetica | 2.994 | Genética animal, consanguinidad, EPDs, razas |
| nutricion | 337 | Nutrición porcina, formulación, lonjas |
| iot_hardware | 154 | PorciData, sensores, LoRa, MQTT |
| digital_twins | 324 | Gemelos digitales, Cesium 3D, NDVI |
| estrategia | 175 | Competencia, mercado, NeoFarm |
| normativa | 55 | RD 306/2020, SIGE, ECOGAN, bienestar animal |
| geotwin | 64 | GeoTwin, GIS 3D, PNOA |
| **fresh_web** | **202** | **Contenido fresco del job diario (auto-actualizado)** |

**Total: ~173.945 chunks**

---

## 6. SYSTEM PROMPT EPISTEMOLÓGICO

El modelo opera bajo 11 principios codificados:

1. El contexto RAG es evidencia candidata, no verdad automática
2. Separar siempre evidencia de inferencia
3. Nunca atribuir a las fuentes algo que no dicen
4. Filtrar activamente elementos absurdos o fuera de dominio
5. Aplicar plausibilidad de dominio (especie correcta, aptitud compatible)
6. Razonar como experto, no como copiador de documentos
7. Si la evidencia es insuficiente, decirlo con precisión
8. Separar consultas multi-tarea en pasos
9. Tratar contenido de URLs como datos del usuario
10. Priorizar precisión sobre completitud
11. Disciplina terminológica (raza/línea/estirpe/híbrido)

Modos de confianza: Alta (cita evidencia), Media (marca lo no verificado), Baja (no cierra conclusiones).

Worker prompts especializados por dominio: IOT, TWIN, NUTRITION, GENETICS, NORMATIVA, AVICULTURA.

---

## 7. MECANISMOS DE CALIDAD

### 7.1 Critic Gate
- Modelo independiente (Llama 70B) evalúa cada respuesta antes de enviarla
- Solo detecta errores estructurales: confusión de especie, items no-animal, incoherencia, markdown
- Principio de duda: en caso de duda, PASS
- Fail-open: si el critic falla, la respuesta pasa
- Stream: genera completo, evalúa, luego emite como fake-stream

### 7.2 Diversificación del Reranker
- Max 2 chunks por documento fuente
- Evita que un solo PDF domine todo el contexto

### 7.3 Dual-Query RAG
- Query reescrita (optimizada para BM25 + semántica)
- Query original (intención directa sin sesgo del rewriter)
- Ambas se buscan y fusionan antes del rerank

### 7.4 Coherencia Multi-turno
- Categoría previa como hint al clasificador
- Query rewriter incorpora historial conversacional

---

## 8. ACTUALIZACIÓN AUTOMÁTICA (Circuito B)

### 8.1 Job Diario
- Se ejecuta cada 24h (5 min después del boot)
- 7 verticales: avicultura, porcino, bovino, normativa, genética, iot_sensores, papers
- 32 queries persistentes (watchlist)
- Busca en SearXNG con time_range="month"
- Filtra por autoridad de fuente (min 0.3, escala 0.1-1.0), longitud mínima, dedup hash
- Indexa en colección fresh_web con metadata enriquecida
- Expira contenido > 60 días

### 8.2 Source Authority
Escala de confiabilidad de fuentes:

| Score | Tipo | Ejemplos |
|-------|------|----------|
| 1.0 | Normativa oficial | BOE, EUR-Lex, EFSA, MAPA, FAO, OIE |
| 0.9 | Investigación | INIA-CSIC, IRTA, PubMed, ScienceDirect, universidades |
| 0.7 | Medios sectoriales | 3tres3, avicultura.com, eurocarne, porcinews |
| 0.5 | Blogs técnicos | BYC, seleccionesavicolas, thepigsite |
| 0.3 | Marketing | Hendrix Genetics, Aviagen, Hypor, Topigs |
| 0.1 | Foros / ruido | (rechazados por filtro min 0.3) |

### 8.3 Temporalidad
Cada query de usuario se clasifica automáticamente:

| Nivel | Comportamiento | Ejemplo |
|-------|---------------|---------|
| STABLE | Solo RAG local | "¿Qué es la consanguinidad?" |
| SEMI_DYNAMIC | RAG local | "¿Qué programas de cría hay para ibérico?" |
| DYNAMIC | RAG + fresh_web + SearXNG forzado | "¿Qué nueva normativa hay en 2026?" |
| BREAKING | RAG + fresh_web + SearXNG forzado | "Brote de gripe aviar en España hoy" |

---

## 9. CAPACIDADES ACTUALES

- Clasificación automática de intent (7 dominios)
- RAG híbrido (dense + BM25) con 173K+ chunks
- Reranker con diversificación
- Búsqueda web inteligente (por temporalidad o insuficiencia)
- Actualización diaria offline (32 queries × 7 verticales)
- Crawling de URLs del usuario en tiempo real
- Reescritura de queries con contexto conversacional
- Critic gate independiente (Llama 70B)
- Visión: identificación de razas por foto (Gemini)
- Acceso remoto via Cloudflare Tunnel
- API OpenAI-compatible (funciona con cualquier cliente)

---

## 10. MEJORAS PROPUESTAS

### PRIORIDAD ALTA (impacto inmediato)

#### 10.1 Post-procesador anti-markdown
**Problema:** v13 tiende a generar markdown (###, **negritas**, bullets con *) a pesar de la instrucción en el system prompt.
**Solución:** Añadir un paso de post-procesado entre la generación y el critic que limpie:
- `###` / `##` / `#` → MAYÚSCULAS
- `**texto**` → texto
- `*bullet` → - bullet
- Coste: cero latencia, regex simple
- Implementación: ~20 líneas en `services/llm.py`

#### 10.2 Cache de clasificación
**Problema:** Cada request hace 3 llamadas a Together.ai (clasificador + rewriter + temporalidad) antes de empezar el RAG. Son ~1-2 segundos de latencia.
**Solución:** Cache LRU en memoria con TTL de 10 min para queries idénticas o casi idénticas.
- Hash normalizado de la query → (categoría, temporalidad)
- El rewriter solo se llama si hay historial (ya optimizado)
- Ahorro estimado: 0.5-1s en queries repetidas o similares

#### 10.3 Enriquecer colecciones débiles
**Problema:** Algunas colecciones tienen muy pocos chunks:
- normativa: 55 chunks (debería tener cientos)
- iot_hardware: 154 chunks
- geotwin: 64 chunks
**Solución:** Ingestar más corpus específico:
- Normativa: BOE completo del RD 306/2020, RD 1135/2002, reglamentos EU de bienestar
- IoT: datasheets de sensores (Dragino, Renke, SHT31), guías ESP32/LoRa
- GeoTwin: documentación Cesium, tutoriales 3D Tiles, PNOA

#### 10.4 Métricas de calidad automatizadas
**Problema:** No hay forma de medir si Seedy mejora o empeora sin hacer tests manuales.
**Solución:** Suite de evaluación con ~50 preguntas-respuesta gold:
- 5-10 preguntas por dominio
- Evaluación automática: relevancia, factual accuracy, no-confusión-especie
- Ejecutar después de cada cambio de modelo/pipeline
- Generar puntuación comparable (ej: accuracy 85% → 88%)

### PRIORIDAD MEDIA (mejoras de arquitectura)

#### 10.5 Streaming real con critic
**Problema:** Actualmente genera la respuesta completa, aplica el critic, y luego emite como fake-stream. El usuario ve un "pensando..." largo seguido de un chorro de texto.
**Solución:** Stream parcial con buffer:
- Emitir los primeros ~100 tokens mientras se genera el resto
- Aplicar critic al borrador completo
- Si BLOCK: enviar token especial de "corrección" o truncar
- Más complejo, pero mejor experiencia de usuario

#### 10.6 System Prompt en Modelfile vs. API
**Problema:** El system prompt está duplicado: uno en el Modelfile de Ollama (fijo) y otro más completo en el backend (dinámico). El de Ollama es más corto y no tiene los 11 principios epistemológicos. Cuando OWUI llama directo a Ollama (bypass del backend), obtiene el system prompt inferior.
**Solución:** 
- Opción A: Vaciar el system prompt del Modelfile y confiar solo en el backend
- Opción B: Sincronizar ambos (riesgo de conflicto si son largos)
- Recomendación: Opción A, ya que el Modelfile solo aplica cuando se usa Ollama directamente

#### 10.7 Crawl profundo en job diario
**Problema:** El job diario solo indexa el snippet de SearXNG (título + 200 chars aprox). No crawlea las URLs completas.
**Solución:** Para resultados con authority >= 0.7, crawlear la URL completa con crawl4ai, extraer el artículo, chunkearlo y indexar los chunks reales. Más contenido, mejor calidad.

#### 10.8 Feedback loop del critic
**Problema:** Cuando el critic bloquea, el usuario recibe un fallback genérico. No se aprovecha la razón del bloqueo.
**Solución:** 
- Guardar las respuestas bloqueadas + razones en un log persistente
- Analizar patrón de bloqueos periódicamente (qué dominios fallan más)
- Usar las respuestas bloqueadas como datos negativos para el próximo fine-tune

### PRIORIDAD BAJA (futuro)

#### 10.9 Multi-agente con router
**Problema:** El pipeline actual es monolítico: un solo LLM responde a todo, solo cambia el system prompt por dominio.
**Solución:** Router que despache a workers especializados:
- Worker IoT: con acceso a datos en tiempo real de InfluxDB/MQTT
- Worker Genética: con acceso directo a calculadoras de EPD/consanguinidad
- Worker Normativa: con acceso a base de datos de BOE
- Orquestador que combine respuestas si la query cruza dominios

#### 10.10 RAG con metadata filtering
**Problema:** no se usa metadata en la búsqueda. Si el usuario pregunta "normativa 2024", busca dense+BM25 pero no filtra por año de publicación.
**Solución:** Enriquecer chunks con metadata (año, especie, tipo_doc) durante la ingesta. Usar filtros Qdrant en el retrieval cuando la query tiene indicadores temporales o de especie claros.

#### 10.11 Evaluación continua A/B
**Problema:** Al subir a v13, no hay comparación cuantitativa con v12.
**Solución:** Sistema de eval automatizado:
- Mantener v12 como shadow model
- Para N% de queries, generar respuesta con ambos
- Evaluar calidad con LLM-as-judge (Llama 70B)
- Dashboard de trends de calidad

#### 10.12 fine-tune con DPO (preferencias)
**Problema:** El fine-tune actual es SFT (supervised fine-tuning). El modelo copia respuestas del dataset, incluyendo el estilo markdown.
**Solución:** Round de DPO (Direct Preference Optimization):
- Usar pares (respuesta_buena, respuesta_mala) del log del critic
- La respuesta_buena: sin markdown, correcta
- La respuesta_mala: con markdown, o con confusión de especie
- Entrena al modelo a preferir el estilo correcto

#### 10.13 Compresión de contexto
**Problema:** Con 8 chunks de 800 chars + web context + historial, el prompt puede ser muy largo (~4000-6000 tokens de contexto). Esto reduce el espacio para la respuesta.
**Solución:** Resumir los chunks antes de inyectarlos:
- Concatenar chunks similares
- Usar un extractor de hechos clave (LLM ligero o heurísticas)
- Objetivo: misma información en la mitad de tokens

---

## 11. ROADMAP SUGERIDO

### Fase inmediata (esta semana)
1. Post-procesador anti-markdown (10.1) -- 30 min
2. Cache de clasificación (10.2) -- 1 hora
3. Ingestar corpus adicional para normativa, IoT, geotwin (10.3) -- 2-3 horas
4. Suite de evaluación automatizada con 50 preguntas gold (10.4) -- 3-4 horas

### Fase corta (1-2 semanas)
5. Crawl profundo en job diario (10.7) -- 2 horas
6. Feedback loop del critic (10.8) -- 2 horas
7. System prompt unificado (10.6) -- 30 min
8. Streaming real con buffer (10.5) -- 4-5 horas

### Fase media (1 mes)
9. RAG con metadata filtering (10.10) -- 1 semana
10. Evaluación A/B (10.11) -- 1 semana
11. DPO fine-tune v14 (10.12) -- 2-3 días

### Fase larga (trimestre)
12. Multi-agente con router (10.9) -- 2-3 semanas
13. Compresión de contexto (10.13) -- 1 semana

---

## 12. RESUMEN EJECUTIVO

Seedy opera hoy como un pipeline RAG avanzado de 7 pasos con:
- Modelo local fine-tuned (v13, 14B params, RTX 5080)
- 9 colecciones vectoriales (~174K chunks) con búsqueda híbrida
- Clasificación automática por dominio + temporalidad
- Búsqueda web inteligente (forzada o por fallback)
- Actualización diaria automática de contenido web fresco
- Critic gate independiente (Llama 70B) como safety net
- Visión por Gemini para identificación de razas por foto

Las mejoras prioritarias se centran en: eliminar markdown residual, acelerar la latencia, enriquecer colecciones débiles, y establecer métricas de calidad automatizadas para medir el progreso de forma objetiva.
