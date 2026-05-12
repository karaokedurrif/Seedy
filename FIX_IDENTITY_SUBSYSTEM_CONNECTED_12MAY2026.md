# FIX Identity Subsystem v4.2 Conectado — 12 mayo 2026

## PROBLEMA DIAGNOSTICADO

El identity subsystem v4.2 **estaba completamente implementado** pero **desconectado** del flujo de edge events.

### Síntomas
- 23,375 edge events/día llegando desde Jetson
- 0% breed classification
- 0% identity coverage
- Todos los tracks con breed="", identity_locked=false, bird_id=""

### Causa Raíz
El endpoint `/edge_event` en `backend/routers/vision.py`:
- ✅ Recibía tracks del Jetson Edge v4.5
- ✅ Guardaba snapshots en behavior_event_store
- ❌ PERO NO invocaba el análisis de identidad

Los módulos v4.2 existentes pero sin usar:
- `backend/services/identity/identity_voting.py` → VotingBuffer
- `backend/services/identity/identity_lock.py` → IdentityLock, AssignmentRegistry
- `backend/services/identity/breed_parser.py` → parse_breed_class
- `backend/services/identity/doubt_escalator.py` → DoubtEscalator
- `backend/services/bird_tracker.py` línea 502-640 → sync_registered_ids() con lógica v4.2 completa

---

## SOLUCIÓN IMPLEMENTADA

### 1. Nueva Función Async en vision.py

```python
async def _process_edge_tracks_async(gallinero_id: str, camera_id: str, tracks: list[dict], timestamp: str):
    """Procesa tracks edge con análisis completo.
    
    Pipeline v4.2 con Jetson Edge v4.5:
    1. Convertir tracks Jetson → formato tracker backend
    2. Actualizar tracker backend (para mantener sincronía con Jetson)
    3. Sync identities con registered birds (usa breed+sex+color del tracker)
    4. Detectar mating entre tracks
    """
```

**Funciones:**
- Convierte tracks del Jetson (bbox[4], track_id, class_name) → detections backend (bbox_norm, category, confidence)
- Llama a `tracker.update(detections)` para sincronizar posiciones y calcular zonas
- Llama a `tracker.sync_registered_ids(registered_birds)` que ejecuta la lógica v4.2:
  - Filtro por breed + sex + color (tolerante a alias silver→plateado, macho→male)
  - AssignmentRegistry.claim() para unicidad (1 ai_vision_id → 1 track activo)
  - IdentityLock con decay ×0.95 cada 10min
  - DoubtEscalator para casos ambiguos (0 o >1 candidatos)
- Llama a `mating_detector.process_frame(tracker)` para detectar montas

**Ejecución:** Fire & forget con `asyncio.create_task()`, no bloquea edge_event endpoint.

### 2. Modificación del Endpoint

```python
@router.post("/edge_event")
async def receive_edge_event(event_data: dict):
    # ... almacenar buffer, MQTT, behavior_event_store ...
    
    if n_tracks > 0 and event_data.get("gallinero_id"):
        # 🆕 v4.2: Procesar tracks con análisis completo (en background)
        asyncio.create_task(_process_edge_tracks_async(
            gallinero_id=event_data["gallinero_id"],
            camera_id=event_data.get("camera_id", "unknown"),
            tracks=event_data.get("tracks", []),
            timestamp=event_data.get("timestamp")
        ))
```

### 3. Correcciones de Bugs

**Bug 1:** Importación incorrecta de mating_detector  
```python
# ❌ ANTES
from services.mating_detector import mating_detector
mating_events = mating_detector.check_tracks(gallinero_id, active_tracks)

# ✅ DESPUÉS
from services.mating_detector import get_mating_detector
mating_det = get_mating_detector(gallinero_id)
mating_events = mating_det.process_frame(tracker)
```

**Bug 2:** API /birds/ devuelve dict, no array directo  
```python
# ❌ ANTES
birds_list = resp.json()  # Esperaba array, era {birds: [...], total: N}

# ✅ DESPUÉS
data = resp.json()
birds_list = data.get("birds", []) if isinstance(data, dict) else []
```

---

## RESULTADOS VERIFICADOS

### Logs de Producción (DGX)

```
[INFO] Edge event 7e284f76 from jetson_orin_nano_01/dahua_sauna: 2 tracks, type=tracking
[INFO] 🚀 Processing 2 tracks from dahua_sauna → gallinero_palacio
[INFO] 🔄 Updated tracker gallinero_palacio with 2 detections from Jetson
```

### Pipeline Completo Activo

1. ✅ Edge events llegan cada 5 segundos (Jetson Edge v4.5)
2. ✅ Tracks se convierten y actualizan en tracker backend
3. ✅ sync_registered_ids() se ejecuta SIN errores
4. ✅ mating_detector.process_frame() se ejecuta SIN errores

### Próximos Pasos para Verificar Eficacia

1. **Captura 4K necesaria:** El CaptureManager debe capturar frames 4K cuando hay quality tracks (conf > 0.40)
2. **Breed classification:** El backend debe clasificar breed sobre crops 4K con `classify_breed_crop()`
3. **VotingBuffer:** Cuando breed se clasifica, debe añadir votos al VotingBuffer
4. **Identity sync:** Con breeds confirmados (≥3 votos consistentes), sync_registered_ids asignará identidades

**Estado actual:** Pipeline conectado, esperando capturas 4K + breed classification para ver identidades asignadas.

---

## ARQUITECTURA v4.2 — FLUJO COMPLETO

```
Jetson Edge (sub-stream 10-15fps)
  ↓ YOLO COCO (bird+dog+cat, conf 0.20)
  ↓ Tracking (centroide+IoU, 120 frames)
  ↓ Edge events schema v4.5 → /edge_event endpoint
    ↓
Backend (DGX)
  ├─ behavior_event_store.store_edge_snapshot()  [ACTIVO]
  ├─ _process_edge_tracks_async()               [🆕 CONECTADO]
  │   ├─ tracker.update(detections)              [ACTIVO]
  │   ├─ tracker.sync_registered_ids()           [ACTIVO v4.2]
  │   │   ├─ Filtro breed+sex+color
  │   │   ├─ AssignmentRegistry.claim()
  │   │   ├─ IdentityLock (decay, unlock)
  │   │   └─ DoubtEscalator (casos ambiguos)
  │   └─ mating_detector.process_frame()         [ACTIVO]
  │
  └─ CaptureManager (4K event-triggered)
      ↓ capture_main_stream()
      ↓ classify_breed_crop()                    [PENDIENTE VERIFICAR]
      ↓ VotingBuffer.add_vote()                  [PENDIENTE VERIFICAR]
      └─ IdentityLock.confirm()                  [PENDIENTE VERIFICAR]
```

---

## COMMITS

1. `6f2badf` — FIX v4.2: Conectar edge events con identity subsystem
2. `7b7fbf8` — FIX: Corregir import de mating_detector
3. `9cf3c0d` — DEBUG: Cambiar logger.debug → logger.info para visibilidad
4. `0f92bf7` — DEBUG: Agregar log de inicio en _process_edge_tracks_async
5. `23ac94b` — FIX: Corregir API birds y método mating_detector (VERSIÓN FINAL)

---

## ARCHIVOS MODIFICADOS

- `backend/routers/vision.py` (+102 líneas)
  - Nueva función `_process_edge_tracks_async()` (95 líneas)
  - Modificación `receive_edge_event()` para invocar análisis (7 líneas)

---

## DEPLOYMENT

```bash
# Commit
git add backend/routers/vision.py
git commit -m "FIX: Corregir API birds y método mating_detector"

# Sync al DGX
rsync -avz backend/routers/vision.py daviddgx@192.168.20.57:~/seedy/backend/routers/

# Restart backend
ssh daviddgx@192.168.20.57 "cd ~/seedy && docker compose restart seedy-backend"
```

**Servidor:** daviddgx@192.168.20.57 (password: 4431)  
**Path:** ~/seedy/ (aka /home/davidia/Documentos/Seedy/)  
**Stack:** 17 contenedores Docker, ai_default network

---

## CONCLUSIÓN

El identity subsystem v4.2 **ya estaba implementado** desde abril 2026 pero nunca fue conectado al flujo de edge events. Este fix de **102 líneas** conecta toda la infraestructura existente.

**Impacto esperado:**
- 0% → 30-50% identity coverage (según análisis previo)
- 7-8 aves con identidad determinística (4 gallos + razas únicas)
- DoubtEscalator registrando casos ambiguos para revisión manual

**Status:** ✅ DEPLOYED y ACTIVO en producción (DGX MSI Vector 16 HX)
