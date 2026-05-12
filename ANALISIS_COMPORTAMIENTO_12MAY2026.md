# 📊 ANÁLISIS SISTEMA COMPORTAMIENTO — 12 Mayo 2026

**Fecha análisis:** 12 mayo 2026 20:35h  
**Solicitado por:** Usuario  
**Objetivo:** Determinar si el sistema está captando realmente pautas de comportamiento

---

## 🎯 RESUMEN EJECUTIVO

### Veredicto: ⚠️ **CAPTURA PARCIAL — PIPELINE INCOMPLETO**

El sistema **SÍ está captando movimiento básico** (tracking de aves), pero **NO está ejecutando el análisis de comportamiento completo**. Es como tener los ojos abiertos pero el cerebro a medio funcionar.

**Analogía:** Jetson = ojos ✅ | Backend análisis = cerebro 🔴 (semi-dormido)

---

## ✅ QUÉ SÍ FUNCIONA

### 1. Jetson Edge Inference
- ✅ **Jetson Orin Nano ONLINE** (192.168.20.68, ping 3-20ms)
- ✅ **Envío de eventos** al backend DGX
- ✅ **Detecciones COCO** activas (clases: bird, dog, cat)
- ✅ **Tracking funcional** (track_id, bbox, confidence, camera_id)
- ✅ **Múltiples cámaras** detectando (dahua_sauna, vigi_nueva)

**Evidencia:**
```json
{"active_count": 2, "tracks": [
  {"track_id": 44, "class_name": "bird", "confidence": 0.50, "edge_camera_id": "vigi_nueva"},
  {"track_id": 54, "class_name": "bird", "confidence": 0.27, "edge_camera_id": "vigi_nueva"}
], "source": "edge"}
```

### 2. Backend Reception
- ✅ **Endpoint `/vision/edge_event`** recibiendo datos
- ✅ **behavior_event_store** guardando snapshots
- ✅ **23,375 líneas** de snapshots hoy (2026-05-12.jsonl)
- ✅ **Alta frecuencia** de capturas (cada 2-5 segundos)

### 3. Dataset Curado
- ✅ **3,000 crops** acumulados para entrenamiento
- ✅ **11 razas** con datos (F1 838, Sussex 576, Pita Pinta 474...)
- ✅ **CaptureManager** activo:
  - Sauna: 10,486 sub-frames procesados, 143 capturas 4K
  - Triggers: 25 new_bird, 96 quality_bird, 8 pest_alert

### 4. Registro de Aves
- ✅ **26 aves registradas** con ai_vision_id
- ✅ **IDs consistentes**: sussexsilv1/2, bresseblan1/2/3, maransnegr1, etc.

---

## 🔴 QUÉ NO FUNCIONA

### 1. Breed Classification ❌
**Estado:** **NO SE EJECUTA**

**Evidencia:**
- Snapshots tienen `"breed": ""` vacío
- 0 logs de "breed classification" en últimas 3h
- YOLO Breed model NO se aplica sobre crops edge

**Impacto:** Sin raza clasificada → no hay base para identidad

### 2. Identity Assignment ❌
**Estado:** **NO SE ASIGNA**

**Evidencia:**
- Todos los tracks: `"identity_locked": false`
- Todos los tracks: `"bird_id": ""` vacío
- VotingBuffer NO está acumulando votos
- IdentityLock NO está bloqueando identidades

**Cobertura actual:** 0% (debería ser 30-50%)

**Excepción:** 2 tracks en `/tracks/live` SÍ tienen identidad:
```json
{"track_id": 213, "ai_vision_id": "sussexsilv1", "identity_locked": true}
{"track_id": 214, "ai_vision_id": "maransnegr1", "identity_locked": true}
```
Pero estos son casos aislados, NO representativos del flujo edge→behavior.

### 3. Mating Detection ❌
**Estado:** **0 EVENTOS**

**Evidencia:**
- 0 archivos `mating_*.jsonl` en últimos 7 días
- 0 logs de "mating" o "mounting" en últimas 3h
- MatingDetector NO está corriendo

**Impacto:** No hay datos de reproducción

### 4. Behavior Analysis ❌
**Estado:** **NO SE INFIERE**

**Evidencia:**
- Snapshots guardan bbox y class_name, pero NO:
  - ❌ breed
  - ❌ sex
  - ❌ bird_id (salvo 2 excepciones)
  - ❌ zone
  - ❌ behavior features (feeding, nesting, social)

**Impacto:** No hay patrones conductuales detectados

---

## 🔍 ANÁLISIS DE CAUSA RAÍZ

### Problema: Pipeline a Medio Completar

**Pipeline esperado (v4.2):**
```
Jetson Edge (COCO detector)
  ↓
Backend receive edge_event
  ↓
behavior_event_store.store_edge_snapshot()  ← AQUÍ ESTÁ
  ↓
❌ CaptureManager debería capturar frame 4K
❌ YOLODetectorV4 debería clasificar breed sobre crop
❌ VotingBuffer debería acumular votos
❌ IdentityLock debería asignar bird_id
❌ MatingDetector debería buscar montas
❌ BehaviorInference debería calcular 7 dimensiones
  ↓
Frontend Digital Twin (https://seedy-api.neofarm.io/dashboard/ave_twin.html?id=PAL-2026-0001)
```

**Pipeline actual (12 mayo):**
```
Jetson Edge (COCO detector) ✅
  ↓
Backend receive edge_event ✅
  ↓
behavior_event_store.store_edge_snapshot() ✅
  ↓
❌ ← SE DETIENE AQUÍ
```

### ¿Por qué se detiene?

**Hipótesis 1: Falta integración edge→behavior pipeline**
- `vision.py/edge_event` solo guarda snapshots, no invoca análisis
- No hay llamada a `_detect_with_yolo()` desde edge events
- No hay trigger a CaptureManager para capturas 4K

**Hipótesis 2: Dual-stream desconectado**
- Edge envía detecciones de sub-stream (continuo)
- PERO no hay trigger para capturas main-stream (4K) con breed classification

**Hipótesis 3: Falta loop periódico**
- `capture_manager.py` tiene lógica de triggers
- PERO no hay loop que revise edge events y decida cuándo capturar

---

## 📊 MÉTRICAS ACTUALES

| Métrica | Valor Actual | Target | Estado |
|---------|--------------|--------|--------|
| **Edge events/día** | ~23,000 | >10,000 | ✅ |
| **Tracks con breed** | 0% | 80% | 🔴 |
| **Tracks con identity** | 0% (2/∞ aislados) | 30-50% | 🔴 |
| **Eventos monta 7d** | 0 | 5-20 | 🔴 |
| **Crops curados** | 3,000 | 2,000+ | ✅ |
| **Dataset frames anotados** | ? | 500+ | ⚠️ |
| **Jetson uptime** | 100% | >95% | ✅ |
| **Backend uptime** | 100% | >99% | ✅ |

---

## 🎯 IMPACTO EN FRONTEND

### Digital Twin (https://seedy-api.neofarm.io/dashboard/ave_twin.html?id=PAL-2026-0001)

**Datos disponibles para el frontend:**
- ✅ Registro estático del ave (anilla, raza, sexo, fecha_nac)
- ✅ Foto de perfil (si fue capturada manualmente)
- ⚠️ Tracks live (solo 2 aves con identidad)
- ❌ Historial de comportamiento (feeding, nesting, social)
- ❌ Eventos de monta
- ❌ Anomalías detectadas
- ❌ Predicciones (puesta, estrés)
- ❌ Jerarquía social (PageRank)

**Conclusión:** El digital twin está **desnutrido de datos en tiempo real**.

---

## ✅ RECOMENDACIONES — Plan de Acción

### 🔥 PRIORIDAD CRÍTICA — Conectar edge→behavior pipeline

**Objetivo:** Que cada edge event con tracks active el análisis completo.

#### Acción 1: Modificar `/vision/edge_event` endpoint

**Archivo:** `backend/routers/vision.py`

**Cambio necesario:**
```python
@router.post("/edge_event")
async def receive_edge_event(event_data: dict):
    # ... código actual ...
    
    # NUEVO: Procesar tracks con análisis completo
    if n_tracks > 0:
        asyncio.create_task(_process_edge_tracks_async(
            gallinero_id=event_data["gallinero_id"],
            camera_id=event_data["camera_id"],
            tracks=event_data["tracks"],
            timestamp=event_data["timestamp"]
        ))
```

#### Acción 2: Implementar `_process_edge_tracks_async()`

**Nueva función en `vision.py`:**
```python
async def _process_edge_tracks_async(gallinero_id, camera_id, tracks, timestamp):
    """
    Procesa tracks edge con análisis completo:
    1. Captura frame 4K
    2. Classify breed sobre cada crop
    3. Sync identities con VotingBuffer
    4. Detect mating
    5. Update behavior baseline
    """
    from services.capture_manager import capture_manager
    from services.yolo_detector_v4 import yolo_detector_v4
    from services.identity.identity_voting import voting_buffer
    from services.identity.identity_lock import identity_lock
    from services.mating_detector import mating_detector
    
    # 1. Capturar frame 4K si hay quality track
    quality_tracks = [t for t in tracks if t['confidence'] > 0.40]
    if quality_tracks:
        result = await capture_manager.capture_main_stream(camera_id)
        if result and result.get('crops'):
            # 2. Clasificar breed sobre cada crop
            for crop in result['crops']:
                breed_result = yolo_detector_v4.classify_breed_crop(crop['image'])
                if breed_result:
                    # 3. VotingBuffer.add_vote()
                    voting_buffer.add_vote(
                        track_id=crop['track_id'],
                        breed=breed_result['breed'],
                        sex=breed_result['sex'],
                        color=breed_result['color'],
                        confidence=breed_result['confidence']
                    )
                    
                    # 4. Check si alcanzó consenso → IdentityLock
                    bird_id = voting_buffer.check_consensus(crop['track_id'])
                    if bird_id:
                        identity_lock.lock(crop['track_id'], bird_id)
    
    # 5. Detect mating entre todos los tracks
    mating_events = mating_detector.check_tracks(tracks)
    if mating_events:
        for event in mating_events:
            behavior_event_store.store_mating_event(gallinero_id, event)
```

#### Acción 3: Verificar módulos importables

**Verificar que existen:**
- `backend/services/capture_manager.py` ✅ (existe)
- `backend/services/yolo_detector_v4.py` ✅ (existe)
- `backend/services/identity/identity_voting.py` ✅ (existe)
- `backend/services/identity/identity_lock.py` ✅ (existe)
- `backend/services/mating_detector.py` ✅ (existe)

#### Acción 4: Test del flujo completo

**Comando:**
```bash
# 1. Deploy en DGX
ssh daviddgx@192.168.20.57
cd ~/seedy
git pull origin main
docker compose restart seedy-backend

# 2. Monitorear logs (debe aparecer breed classification)
docker compose logs -f seedy-backend | grep -E 'breed|identity|mating'

# 3. Verificar snapshots tienen breed
tail -1 data/behavior_events/gallinero_palacio/snapshots/2026-05-12.jsonl | python3 -m json.tool

# 4. Verificar tracks tienen identity
curl -s http://localhost:8000/vision/identify/tracks/live?gallinero_id=gallinero_palacio | python3 -m json.tool
```

**Resultado esperado:**
- Logs muestran "Breed classified: sussex_silver_gallo (0.72)"
- Snapshots tienen `"breed": "Sussex", "sex": "male", "bird_id": "sussexsilv1"`
- `/tracks/live` muestra >10 tracks con `identity_locked: true`

---

### 🔧 PRIORIDAD ALTA — Activar mating detection

**Problema:** MatingDetector existe pero no se ejecuta.

**Solución:** Integrar en `_process_edge_tracks_async()` (ver Acción 2 arriba).

---

### 📊 PRIORIDAD MEDIA — Dashboard de monitorización

**Crear:** Panel Grafana con métricas behavior en tiempo real

**Métricas:**
- Tracks/min con breed clasificado
- % identity_locked
- Eventos monta/día
- Anomalías detectadas/día
- Cobertura Re-ID por gallinero

**Propósito:** Detectar rápido si el pipeline se "duerme" de nuevo.

---

### 📈 PRIORIDAD BAJA — Optimizaciones

1. **Batch processing:** Procesar N tracks juntos en vez de 1 a 1
2. **Cache breeds:** No reclasificar tracks que ya tienen breed estable
3. **Async capture:** No bloquear edge_event esperando captura 4K
4. **Rate limiting:** Max 1 captura 4K cada 10s por cámara

---

## 📝 CONCLUSIÓN

### Estado actual: 🟡 **AMARILLO — INFRAESTRUCTURA OK, LÓGICA INCOMPLETA**

**Lo bueno:**
- Hardware funciona (Jetson + DGX + cámaras)
- Datos llegan (23K events/día)
- Módulos de análisis existen (yolo_detector_v4, identity, mating)
- Dataset creciendo (3K crops)

**Lo malo:**
- Pipeline desconectado (edge→behavior)
- Análisis NO se ejecuta automáticamente
- Frontend digital twin sin datos live
- 0 eventos de comportamiento complejos (monta, anomalías)

**Acción inmediata:** Implementar `_process_edge_tracks_async()` en `vision.py` para conectar el pipeline.

**Timeline estimado:** 2-3 horas de desarrollo + 1 día de testing/ajuste

**Impacto esperado:** Pasar de 0% a 30-50% cobertura Re-ID, comenzar a detectar montas, alimentar frontend con datos live.

---

**Generado por:** ia-expert agent  
**Para:** Proyecto Seedy v4.2  
**Última actualización docs:** DIAGNOSTICO_COMPORTAMIENTO_7MAY2026.md, JETSON_ESTADO_ACTUAL_07MAY2026.md
