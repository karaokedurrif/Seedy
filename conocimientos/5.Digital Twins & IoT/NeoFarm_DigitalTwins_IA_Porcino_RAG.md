---
title: "NeoFarm — Digital Twin & IA (Porcino intensivo)"
version: "1.0-rag"
updated: "2026-03-02"
scope:
  species: ["porcino"]
  production_system: ["intensivo", "cebadero", "reproductoras", "transición", "destete"]
  themes: ["IoT", "Digital Twins", "ML/IA", "bienestar", "sanidad", "producción", "energía", "automatización"]
rag:
  chunking: "manual"
  preferred_chunk_size_chars: 1200-2000
  overlap_chars: 150-300
  retrieval_tags: ["porcino", "swine", "PLF", "barn", "sows", "engorde", "ambiental", "amoniaco", "tos", "conducta", "consumo", "crecimiento", "bioseguridad"]
sources:
  - id: "animals-15-02138"
    file: "animals-15-02138.pdf"
    note: "Revisión sobre Precision Livestock Farming en porcino (sensores, analítica, bienestar)."
  - id: "IoT_sows_mioty"
    file: "IoT_System_for_Monitoring_Breeding_Sows_in_Swine_F.pdf"
    note: "Sistema IoT para monitorizar cerdas reproductoras."
---

# Objetivo
Este documento sirve como **base de conocimiento** para un agente NeoFarm especializado en **Porcino Intensivo**: diseño de sistemas IoT, gemelo digital (digital twin), analítica y ML para **producción + bienestar + sanidad + eficiencia**.

---

## CHUNK P1 — Contexto y casos de uso prioritarios
**metadata**
- species: porcino
- system: intensivo
- lifecycle: [cerdas, transición, engorde]
- goals: [bienestar, rendimiento, bioseguridad, costes, cumplimiento]
- kpi: [GMD, IC, mortalidad, tos, cojeras, temperatura, humedad, NH3/CO2, consumo pienso/agua]

**contenido**
Casos de uso con mayor ROI en porcino intensivo (orden recomendado):
1) **Ambiente y ventilación**: predicción de estrés térmico y control (setpoints, ventilación, cooling); alertas por NH3/CO2/PM.
2) **Consumo agua/pienso**: detección temprana de fallos en bebederos y anorexia (patrones por corral/lote).
3) **Enfermedad respiratoria**: analítica acústica (tos) + ambiente + mortalidad para alertas tempranas.
4) **Crecimiento y uniformidad**: estimación de peso por visión (2D/3D) y curvas esperadas por genética/sexo.
5) **Bienestar y conducta**: anomalías (agresión/colas mordidas), densidad efectiva, actividad/descanso.
6) **Reproductoras**: celo/parto, actividad, ingesta, temperatura; soporte a manejo (IA asistida).

---

## CHUNK P2 — Arquitectura IoT recomendada (nave intensiva)
**metadata**
- layer: arquitectura
- components: [edge, red, broker, time-series, data-lake, feature-store, model-serving]
- protocols: [MQTT, HTTP, OPC-UA (si aplica), Modbus (si aplica)]

**contenido**
Arquitectura de referencia (de campo a IA):
- **Capa Sensor**: T/RH, NH3, CO2, PM2.5/PM10, caudal ventilación (si hay), caudalímetros agua, contadores pienso (si existen), cámaras (pasillo/corral), micrófonos (tos), energía (kWh), presión/estado de ventiladores.
- **Edge/Gateway**: buffer local + reintentos; normalización de timestamps; reglas básicas “siempre-on” (umbral NH3, fallo bebedero).
- **Red**: WiFi/ETH en nave; en instalaciones grandes, VLAN/segmentación.
- **Broker**: MQTT (topics por granja/nave/corral/dispositivo).
- **Datos**:
  - **Series temporales** (InfluxDB/Timescale) para sensores.
  - **Objetos** (S3/MinIO) para vídeo/audio.
  - **Relacional** (Postgres) para maestros (lotes, movimientos, tratamientos, vacunación).
- **IA**:
  - feature store (derivadas: THI, delta agua 24h, score tos 1h, tasa ventilación).
  - model serving (API) para inferencia y alertas.
- **Gemelo digital**:
  - estado por nave/corral/lote (variables actuales + “salud esperada” vs real).
  - simulación simple (balances térmicos y ventilación) y predicción (ML).

---

## CHUNK P3 — Modelo de datos mínimo (NeoFarm)
**metadata**
- layer: datos
- tables: [farm, barn, pen, batch, animal_group, sensor, measurement, event, treatment, alarm]
- join_keys: [farm_id, barn_id, pen_id, batch_id, device_id]

**contenido**
Entidades (mínimo viable):
- **farm** (ubicación, altitud, tipo)
- **barn** (tipo, ventilación, capacidad, orientación)
- **pen** (m2, comederos, bebederos, densidad)
- **batch** (lote, entrada/salida, genética, sexo, nº animales)
- **sensor/device** (tipo, calibración, ubicación)
- **measurement** (timestamp, variable, valor, calidad, fuente)
- **event** (movimientos, incidencias, partos, destetes)
- **treatment** (medicaciones, vacunas, retirada)
- **alarm** (reglas/ML, severidad, evidencia, acción sugerida)
Consejo: guarda **lineage** (de dónde viene cada dato y cómo se transformó) para auditoría y mejora del modelo.

---

## CHUNK P4 — Analítica y modelos ML (porcino)
**metadata**
- layer: ml
- tasks: [anomaly_detection, forecasting, classification, regression, computer_vision, audio]
- deployment: [edge, cloud]

**contenido**
Modelos recomendados:
- **Anomalías**:
  - agua: detección de cambios (CUSUM / STL + z-score) por pen/lote.
  - ambiente: outliers por sensor + correlación cruzada (ej. T sube, ventilación cae).
- **Predicción**:
  - **mortalidad/retirada**: riesgo 7 días con variables de ambiente + consumo + historial.
  - **THI/estrés térmico** y efecto en ingesta.
- **Visión**:
  - peso/condición corporal estimada; ocupación/actividad; detección de colas mordidas si hay dataset.
- **Audio**:
  - tos: clasificación por ventanas (1–5s) + agregación horaria; combinar con NH3/PM.
- **Reproductoras**:
  - predicción de parto y eventos (actividad + temperatura + ingesta).

Regla práctica: empieza con **baselines simples** (reglas y modelos ligeros) y sólo sube complejidad cuando tengas datos suficientes y etiquetado.

---

## CHUNK P5 — Playbooks de alerta (qué hacer cuando salta una alarma)
**metadata**
- layer: operaciones
- alert_types: [ambiente, agua, tos, calor, ventilacion, energia]
- outputs: [acciones, checklist, escalado]

**contenido**
Cada alerta debe incluir:
- **qué pasó** (variable/s afectadas + magnitud + duración),
- **dónde** (granja/nave/corral),
- **por qué** (hipótesis: bebedero obstruido, ventilador parado, sobrecarga animal),
- **evidencia** (gráficas, comparativa con histórico, correlaciones),
- **acción inmediata** (checklist),
- **acción correctiva** (mantenimiento / ajuste),
- **seguimiento** (verificar en 30–60 min y a 24h).

Ejemplos:
- “Agua cae 35% en Pen 3”: revisar presión, filtro, bebedero, fugas; comprobar consumo resto pens.
- “NH3 alto + tos al alza”: verificar ventilación/compuertas, cama/estiércol, densidad, protocolo respiratorio.

---

## CHUNK P6 — Integración con RAG (NeoFarm)
**metadata**
- layer: rag
- knowledge_types: [protocolos, normativa, manuales, incidencias, SOP]
- retrieval_hints: [tags, ids, fechas, granja, lote]

**contenido**
Cómo aprovechar RAG en porcino intensivo:
- Guarda SOPs y protocolos por **tema** (bioseguridad, ventilación, respiratorio, colas mordidas).
- En cada documento, añade metadatos: `farm_type=porcino_intensivo`, `module=operaciones/sanidad/IoT`, `severity`, `last_reviewed`.
- Para consultas operativas, el prompt debe pedir:
  1) **resumen**,
  2) **pasos**,
  3) **riesgos**,
  4) **qué datos mirar en NeoFarm**.

---

## CHUNK P7 — Checklist de implementación (0–90 días)
**metadata**
- layer: roadmap
- phases: [0-14d, 15-45d, 46-90d]
- deliverables: [instalacion, dashboards, alertas, primer_modelo]

**contenido**
0–14 días:
- inventario de sensores existentes; instalar T/RH + NH3 (mínimo) + agua; definir topics MQTT.
15–45 días:
- dashboards (ambiente, agua, energía); alertas umbral; etiquetado básico de incidencias.
46–90 días:
- primer modelo: anomalías agua o tos; playbooks; evaluación de impacto (reducción tiempo respuesta).
