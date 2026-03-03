---
title: "NeoFarm — Digital Twin & IA (Vacuno extensivo)"
version: "1.0-rag"
updated: "2026-03-02"
scope:
  species: ["vacuno"]
  production_system: ["extensivo", "dehesa", "rangelands", "vaca-cría", "cebo en pasto"]
  themes: ["IoT", "Digital Twins", "ML/IA", "bienestar", "sanidad", "reproducción", "pastos", "agua", "geoposición"]
rag:
  chunking: "manual"
  preferred_chunk_size_chars: 1200-2200
  overlap_chars: 150-300
  retrieval_tags: ["vacuno", "beef", "extensivo", "dehesa", "collar", "GPS", "virtual fencing", "pastos", "abrevaderos", "rumiación", "parto"]
sources:
  - id: "Nyamuryekunge_etal_2024Rangelands"
    file: "Nyamuryekunge_etal_2024Rangelands.pdf"
    note: "Contexto de monitorización en rangelands (vacuno extensivo)."
  - id: "animals-14-03071"
    file: "animals-14-03071.pdf"
    note: "Revisión/estudio sobre tecnologías de monitorización en ganadería (incluye escenarios no estabulados)."
---

# Objetivo
Base de conocimiento para un agente NeoFarm enfocado en **vacuno extensivo**: IoT en campo, gemelo digital espacial (geo), predicción y soporte a decisiones (manejo, pastos, agua, sanidad y reproducción).

---

## CHUNK V1 — Diferencias clave vs intensivo
**metadata**
- species: vacuno
- system: extensivo
- constraints: [cobertura, energía, latencia, logística]
- success_factors: [autonomía, robustez, coste, simplicidad]

**contenido**
En extensivo cambian las reglas:
- conectividad irregular (LTE/LoRa/Mioty/mesh),
- energía crítica (solar + baterías; duty cycle),
- datos más “espaciados” y con ruido,
- importancia de **geolocalización** (movimiento, pastoreo, distribución),
- foco en **eventos** (parto, fuga, enfermedad, falta de agua) más que en control ambiental.

---

## CHUNK V2 — Casos de uso (ROI alto) en dehesa / rangelands
**metadata**
- layer: casos_uso
- kpi: [pérdidas, partos, reposición, ganancia, tiempo_manejo, agua]
- alerts: [no_movimiento, geofence, fiebre_sospechada, falta_agua, parto_inminente]

**contenido**
Prioridades:
1) **Localización y geocercas**: animales fuera de área, robos/escape, control de lotes.
2) **Agua y abrevaderos**: nivel/caudal, predicción de fallos (sin agua = riesgo alto).
3) **Parto y distocia**: detección por patrón de actividad + temperatura (si disponible).
4) **Enfermedad/lesión**: caída de actividad y rumiación; detección temprana.
5) **Gestión de pastos**: presión de pastoreo, rotaciones, correlación con NDVI (satélite) y clima.
6) **Bioseguridad**: entradas/salidas, cuarentenas, contactos (si hay proximidad).

---

## CHUNK V3 — Arquitectura IoT para campo (robusta y barata)
**metadata**
- layer: arquitectura
- devices: [collar, ear_tag, gateway_solar, beacons, water_station]
- comms: [LTE-M/NB-IoT, LoRaWAN, Mioty, mesh, satélite(opcional)]

**contenido**
Componentes:
- **Dispositivo animal** (collar o crotal inteligente):
  - GPS (cada 5–30 min),
  - acelerómetro (actividad),
  - rumiación (si hardware lo permite),
  - temperatura (opcional).
- **Estación de agua**:
  - nivel/caudal + batería/solar + comunicación.
- **Gateway**:
  - solar, 4G, buffer local, envío por lotes; healthcheck.
- **Plataforma**:
  - series temporales + geodatos (PostGIS),
  - almacenamiento de eventos,
  - motor de reglas + ML (edge o cloud).

Diseño: “**offline-first**” (si no hay cobertura, no pierdas datos).

---

## CHUNK V4 — Gemelo Digital (Digital Twin) en extensivo
**metadata**
- layer: digital_twin
- twin_entities: [animal, herd, paddock, water_point, pasture_patch]
- state_vars: [pos, activity, grazing_proxy, water_access, risk_scores]

**contenido**
Modelo de gemelo digital recomendado:
- **Animal twin**: estado (posición, actividad, rumiación proxy, riesgo sanitario, estado reproductivo probable).
- **Herd twin**: distribución espacial, cohesión, comportamiento anómalo (subgrupos).
- **Terreno**: parcelas/paddocks, pendientes, sombra, agua, pasto (NDVI/biomasa estimada).
- **Riesgos**:
  - estrés térmico (clima + sombra/agua + movimiento),
  - riesgo de falta de agua,
  - riesgo sanitario (baja actividad/rumiación + historial).

---

## CHUNK V5 — Modelos IA recomendados (vacuno extensivo)
**metadata**
- layer: ml
- tasks: [event_detection, anomaly_detection, geospatial_forecasting, clustering]
- labels: [parto, enfermedad, fuga, sin_agua]

**contenido**
- **Detección de eventos**:
  - parto: ventana de alta actividad + cambios abruptos (depende del sensor).
  - fuga/escape: geofence + velocidad + persistencia fuera de área.
- **Anomalías**:
  - “no movimiento” / caída de actividad (posible enfermedad, atrapamiento, muerte).
  - patrones de visita a abrevaderos (riesgo de fallo si la frecuencia cae).
- **Geoespacial**:
  - clustering de zonas de pastoreo por estación; optimización de rotación.
  - predicción de presión de pastoreo combinando clima + NDVI + historial.
- **Priorización operativa**:
  - score de “ir primero a ver” (beneficio/tiempo).

---

## CHUNK V6 — Integración con RAG (protocolos y decisiones)
**metadata**
- layer: rag
- knowledge_types: [protocolos, normativa, manejo, guías campo, incidencias]
- retrieval_hints: [zona, parcela, fecha, evento, riesgo]

**contenido**
Usos prácticos de RAG en extensivo:
- “Qué hacer” ante alertas (animal inmóvil, fuera de área, parto probable, sin agua).
- SOPs por estación (verano: calor/agua; invierno: suplementación).
- Checklist de manejo (movimientos, vacunaciones, desparasitaciones).
Metadatos útiles por documento:
- `species=vacuno_extensivo`
- `module=campo|sanidad|reproduccion|pastos|agua`
- `season=verano|invierno|transicion`
- `risk=alto|medio|bajo`
