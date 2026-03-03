---
document: neofarm_arquitectura_maestra
version: 2026.1
optimized_for: RAG
embedding_strategy: semantic_blocks
recommended_chunk_size: 1200-1500
recommended_overlap: 250-300
domains: [IoT, DigitalTwin, Ganaderia, Porcino, Vacuno, ROI, Genetica, ERP, SIGE]
species_covered: [porcino_intensivo, vacuno_extensivo]
author: NeoFarm
---

# NEOFARM — ARQUITECTURA MAESTRA 2026
## Smart Hub + Digital Twin
### Porcino Intensivo · Vacuno Extensivo

---

# 🐖 SECCIÓN I — PORCINO INTENSIVO

---

## BLOQUE P1 — VISIÓN ESTRATÉGICA PORCINO

[META]
species: porcino  
system: intensivo  
module: estrategia  
priority: alta  
keywords: [SmartHub, DigitalTwin, ROI, Nave, IA, Sensorica]

El modelo NeoFarm para porcino intensivo transforma cada nave en una unidad económica digitalizada.

Objetivo principal:

Convertir datos de sensores en decisiones productivas con impacto económico medible.

Cada nave se convierte en:

- Unidad productiva monitorizada
- Unidad económica modelizada
- Nodo inteligente dentro de la explotación

Componentes estructurales:

- Sensórica IoT ambiental
- IA de visión
- Digital Twin productivo
- Motor económico integrado
- Integración con SIGE
- Integración con trazabilidad
- Integración con ERP

Principio central del sistema:

Sensor → IA → Impacto económico → Recomendación operativa

---

## BLOQUE P2 — ARQUITECTURA SMART HUB POR NAVE

[META]
species: porcino  
module: arquitectura  
layer: SmartHub  
keywords: [Sensores, Edge, IA, Vision, Acustica, Agua, Gases]

Capas del sistema por nave:

### Capa 1 — Sensórica mínima viable

- Temperatura
- Humedad relativa
- NH3
- CO2
- Caudal agua
- Acústica (detección tos)
- Radar actividad nocturna

### Capa 2 — Sensórica avanzada

- Cámara RGB IA
- Cámara térmica
- Nariz electrónica (VOC)
- Calidad agua (pH, EC, turbidez)
- Peso walk-over

### Capa 3 — Procesamiento Edge

- Inferencia local
- Alertas offline
- Reducción ancho de banda
- Funcionamiento sin dependencia cloud permanente

El Smart Hub por nave permite independencia operativa y robustez frente a fallos de red.

---

## BLOQUE P3 — DIGITAL TWIN PRODUCTIVO POR NAVE

[META]
species: porcino  
module: digital_twin  
level: nave  
keywords: [IC, GMD, Mortalidad, Peso, Prediccion, Lote]

Definición formal:

Twin_Productivo_Nave = f(
  numero_animales,
  edad_lote,
  temperatura,
  humedad,
  NH3,
  consumo_agua,
  consumo_pienso,
  actividad,
  mortalidad_acumulada
)

Outputs clave:

- IC estimado en tiempo real
- Peso proyectado a salida
- Fecha óptima de envío
- Riesgo respiratorio (%)
- Impacto económico proyectado €/lote
- Índice bienestar dinámico

El gemelo digital convierte datos crudos en métricas predictivas.

---

## BLOQUE P4 — MOTOR ECONÓMICO PORCINO

[META]
species: porcino  
module: economia  
keywords: [ROI, Coste, Pienso, Medicacion, Energia, Mercado]

Variables económicas integradas:

- Coste pienso real
- Coste energético
- Coste medicación
- Mortalidad acumulada
- Precio mercado kg vivo
- Coste fijo por nave

Ejemplo de alerta estructurada:

Evento: Caída consumo agua -18%  
Probabilidad brote respiratorio: 63%  
Impacto estimado si no intervenir: -3.200€  
Recomendación: Revisión calidad agua + ajuste ventilación

El sistema traduce anomalías técnicas en impacto económico directo.

---

## BLOQUE P5 — KPIs PORCINO

[META]
species: porcino  
module: KPIs  
keywords: [Deteccion, Mortalidad, IC, GMD, ROI]

### KPIs Productivos

- Reducción mortalidad %
- Mejora IC
- Mejora GMD
- Reducción días a peso óptimo
- Precisión estimación peso vs báscula

### KPIs Económicos

- € ahorrados por detección precoz
- ROI por nave
- Payback en meses
- Margen adicional por lote

### KPIs Técnicos

- Tiempo medio detección temprana
- Falsos positivos
- Uptime sistema

---

# 🐄 SECCIÓN II — VACUNO EXTENSIVO

---

## BLOQUE V1 — VISIÓN ESTRATÉGICA EXTENSIVO

[META]
species: bovino  
system: extensivo  
module: estrategia  
keywords: [Centinelas, Territorial, Autonomia, LoRa, Pastoreo]

Objetivo:

Digitalizar la finca como unidad territorial inteligente.

Principio estructural:

No instrumentar todos los animales.  
Aplicar estrategia de animales centinela (10–20 representativos).

Filosofía:

Cobertura territorial + comportamiento lote > sensor individual masivo.

---

## BLOQUE V2 — ARQUITECTURA DE RED AUTÓNOMA

[META]
species: bovino  
module: conectividad  
keywords: [LoRaWAN, Solar, Edge, Satelite, Offline]

Infraestructura recomendada:

- 2–3 gateways LoRa solares
- Baterías LiFePO4
- Edge local en caseta
- Backhaul satélite bajo ancho de banda

Características:

- Operación offline
- Sin red móvil fiable
- Sin luz distribuida en campo
- Sin dependencia cloud permanente

---

## BLOQUE V3 — DIGITAL TWIN TERRITORIAL

[META]
species: bovino  
module: digital_twin  
level: finca  
keywords: [Actividad, Pastoreo, Parto, Agua, Clima, Parcelas]

Definición:

Twin_Extensivo = f(
  clima,
  actividad_centilenas,
  agua_abrevaderos,
  uso_parcelas,
  reproduccion
)

Outputs:

- Índice bienestar lote
- Riesgo parto
- Estrés térmico
- Uso real parcelas
- Carga ganadera óptima
- Predicción déficit hídrico

El gemelo territorial modela dinámica de finca, no de individuo aislado.

---

## BLOQUE V4 — MÓDULO GENÉTICO EXTENSIVO

[META]
species: bovino  
module: genetica  
keywords: [Consanguinidad, GrafoContacto, Cubriciones, Wright]

Funciones:

- Registro sementales
- Registro cubriciones
- Grafo de contacto por co-presencia
- Cálculo coeficiente Wright
- Simulación 3 generaciones
- Alertas por riesgo endogámico

Objetivo:

Evitar cruces no deseados y depresión endogámica en razas autóctonas.

---

## BLOQUE V5 — KPIs EXTENSIVO

[META]
species: bovino  
module: KPIs  
keywords: [Localizacion, Parto, Agua, Autonomia, Preñez]

### KPIs Operativos

- Tiempo medio localizar animal
- Incidencias agua detectadas
- Días autonomía sistema
- Cobertura IoT efectiva %

### KPIs Productivos

- % preñez
- Intervalo entre partos
- Mortalidad terneros
- Peso destete

### KPIs Económicos

- Reducción pérdidas extravío
- Ahorro desplazamientos
- Optimización uso parcela
- Justificación automática subvenciones

---

# 🔄 BLOQUE TRANSVERSAL — LOOP INTELIGENTE NEOFARM

[META]
species: multi  
module: aprendizaje  
keywords: [ClosedLoop, MejoraContinua, Datos, IA]

Loop estructural del sistema:

Sensor → IA → Decisión → Impacto económico → Aprendizaje → Ajuste modelo

Aplicable a:

- Porcino (nave)
- Vacuno (finca)
- Ibérico (lote territorial)

El sistema mejora en cada ciclo productivo.

---

# DIFERENCIACIÓN ESTRUCTURAL ENTRE ESPECIES

| Aspecto | Porcino Intensivo | Vacuno Extensivo |
|----------|------------------|------------------|
| Unidad de análisis | Nave | Finca |
| Control | Microambiente | Macroterritorio |
| IA principal | Visión + ambiente | Localización + actividad |
| Red | Local estable | Autónoma solar |
| ROI | Directo por lote | Operativo + prevención |
| Digital Twin | Productivo | Territorial + reproductivo |

---

# OPTIMIZACIÓN RAG IMPLEMENTADA

Este documento está diseñado para:

- Recuperación por especie
- Recuperación por módulo
- Recuperación por palabra clave
- Chunking semántico independiente
- Búsqueda híbrida BM25 + embeddings

Cada bloque es autónomo y no depende del contexto completo.

Configuración recomendada:

Chunk size: 1200–1500  
Overlap: 250–300  
Búsqueda híbrida: ON  
Top K: 6–8  

---

FIN DEL DOCUMENTO