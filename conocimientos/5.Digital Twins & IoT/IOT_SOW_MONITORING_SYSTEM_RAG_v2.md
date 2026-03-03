---
document_id: porcino_iot_sow_monitoring_master
document_type: scientific_system_structured
version: 2026.1
species: porcino
production_stage: breeding_sows
production_model: intensivo
domain: IoT + Behaviour + Environmental Monitoring
rag_optimized: true
chunk_strategy: semantic_blocks
recommended_chunk_size: 800
recommended_overlap: 200
retrieval_tags: [porcino, reproductoras, sows, IoT, monitoring, behaviour, environmental, SmartHub]
---

# IOT SYSTEM FOR MONITORING BREEDING SOWS  
## Versión estructurada y optimizada para RAG  
NeoFarm Knowledge System

---

# BLOQUE 1 — CONTEXTO Y PROPÓSITO DEL SISTA

[META]  
section: context  
importance: high  
keywords: [breeding_sows, farm_monitoring, welfare, productivity]

Este sistema IoT está diseñado para monitorizar cerdas reproductoras en sistemas intensivos.

Objetivos principales:

- Monitorización continua del estado ambiental
- Análisis de comportamiento individual y colectivo
- Detección precoz de eventos anómalos
- Reducción de inspecciones manuales
- Mejora de bienestar animal

El sistema actúa como capa tecnológica base para granjas reproductoras.

---

# BLOQUE 2 — ARQUITECTURA GENERAL

[META]  
section: architecture  
layer: full_system  
keywords: [sensor_node, gateway, wireless_network, cloud_platform]

Arquitectura estructural:

1. Nodo sensor individual
2. Red inalámbrica de bajo consumo
3. Gateway central
4. Plataforma de almacenamiento
5. Interfaz de visualización

Flujo operativo:

Sensor → Transmisión → Gateway → Servidor → Dashboard → Alerta

El diseño permite escalabilidad modular por número de animales.

---

# BLOQUE 3 — SENSORES AMBIENTALES

[META]  
section: sensors_environmental  
data_type: ambient  
keywords: [temperature, humidity, ammonia, barn_environment]

Variables ambientales medidas:

- Temperatura
- Humedad relativa
- Concentración de gases
- Condiciones generales del establo

Impacto directo sobre:

- Estrés térmico
- Salud respiratoria
- Consumo de alimento
- Rendimiento reproductivo

---

# BLOQUE 4 — MONITORIZACIÓN DE COMPORTAMIENTO

[META]  
section: behaviour_monitoring  
data_type: activity  
keywords: [movement, posture, behaviour_patterns, anomaly_detection]

El sistema analiza:

- Nivel de actividad
- Cambios de postura
- Patrones diarios
- Variaciones respecto a baseline individual

Aplicaciones clave:

- Detección precoz de enfermedad
- Identificación de estrés
- Anomalías reproductivas
- Cambios de consumo indirectos

---

# BLOQUE 5 — RED DE COMUNICACIÓN

[META]  
section: communication_layer  
network_type: low_power_wireless  
keywords: [low_power, wireless, transmission, IoT_network]

Características técnicas:

- Comunicación inalámbrica de bajo consumo
- Arquitectura multi-nodo
- Centralización en gateway
- Envío periódico de datos

Diseñado para ambientes ganaderos con:

- Alta humedad
- Polvo
- Interferencias estructurales metálicas

---

# BLOQUE 6 — GESTIÓN Y PROCESAMIENTO DE DATOS

[META]  
section: data_processing  
keywords: [data_collection, storage, visualization, alerts]

Pipeline de datos:

Datos crudos → Procesamiento → Generación indicadores → Visualización → Alertas

Funcionalidades:

- Almacenamiento histórico
- Análisis temporal
- Dashboard visual
- Alertas automatizadas

El sistema no incluye modelado económico integrado.

---

# BLOQUE 7 — VALIDACIÓN Y RESULTADOS

[META]  
section: validation  
keywords: [accuracy, detection_efficiency, field_testing]

Resultados observados en entorno real:

- Mejora en detección temprana de anomalías
- Reducción de inspección manual
- Mejor control ambiental
- Trazabilidad continua

Se demuestra viabilidad técnica del sistema IoT en entorno reproductivo.

---

# BLOQUE 8 — LIMITACIONES IDENTIFICADAS

[META]  
section: limitations  
keywords: [battery_life, interference, calibration, scalability]

Limitaciones técnicas:

- Dependencia de batería en nodos
- Interferencias en estructuras metálicas
- Necesidad de calibración periódica
- No incorpora modelo predictivo económico

---

# BLOQUE 9 — INTEGRACIÓN PROPUESTA EN NEOFARM

[META]  
section: neofarm_integration  
system: SmartHub  
keywords: [DigitalTwin, porcino_intensivo, economic_layer]

Adaptación al ecosistema NeoFarm:

Este sistema puede funcionar como:

- Capa sensórica base del Smart Hub
- Alimentador del Digital Twin productivo
- Fuente de datos para predicción sanitaria

Extensiones recomendadas:

- Cálculo IC estimado en tiempo real
- Proyección GMD
- Modelo económico por lote
- Predicción impacto financiero por alerta

---

# BLOQUE 10 — DIFERENCIA ESTRUCTURAL CON ARQUITECTURA NEOFARM

[META]  
section: comparison  
keywords: [economic_model, predictive_system, ROI]

Sistema del estudio:

✔ Monitoriza  
✔ Detecta cambios  
✔ Genera alertas  
✘ No cuantifica impacto económico  
✘ No modeliza lote completo  
✘ No integra ERP  

NeoFarm añade:

- Motor económico integrado
- Simulación de escenarios
- ROI cuantificado por nave
- Digital Twin predictivo completo

---

# BLOQUE 11 — MAPA DE RECUPERACIÓN SEMÁNTICA

[META]  
section: rag_mapping  
purpose: retrieval_optimization  

Consultas que este documento resuelve:

- "monitorización IoT en cerdas reproductoras"
- "sensores ambientales en porcino"
- "detección comportamiento anómalo en sows"
- "arquitectura IoT para granja intensiva"
- "cómo integrar IoT reproductoras en SmartHub"
- "limitaciones técnicas IoT porcino"

---

# CONFIGURACIÓN RECOMENDADA EN OPEN WEBUI

Chunk Size: 800  
Overlap: 200  
Hybrid Search: ON  
Top K: 6–8  
Relevance Threshold: 0.25  

---

# FIN DEL DOCUMENTO
NeoFarm RAG Optimized Knowledge File