"""
Seedy Backend — Router /vision

Endpoints para recibir eventos de visión artificial desde Jetson/cámaras,
consultar estadísticas y gestionar alertas.

Topics MQTT publicados:
  seedy/vision/events     → Cada evento de detección
  seedy/vision/weights    → Estimaciones de peso
  seedy/vision/alerts     → Alertas de comportamiento/salud
  seedy/vision/stats      → Resúmenes periódicos
"""

import uuid
import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    VisionEvent,
    VisionEventResponse,
    WeightEvent,
    BehaviourAlert,
    VisionStats,
)

# Behavior event store para guardar snapshots
from services.behavior_event_store import behavior_event_store

logger = logging.getLogger(__name__)

try:
    from runtime.logger import log_agent_run
except ImportError:
    log_agent_run = None

router = APIRouter(prefix="/vision", tags=["vision"])

# ─── In-memory stores (en producción: InfluxDB via MQTT) ──────

_recent_events: list[dict] = []
_recent_weights: list[dict] = []
_recent_alerts: list[dict] = []
_MAX_BUFFER = 5000  # Máximo eventos en memoria


def _trim(buffer: list, max_size: int = _MAX_BUFFER):
    """Mantiene el buffer acotado."""
    if len(buffer) > max_size:
        del buffer[: len(buffer) - max_size]



def _try_publish_mqtt(topic: str, payload: dict):
    """Publica a MQTT si el broker está disponible (fire & forget)."""
    try:
        import paho.mqtt.publish as publish

        publish.single(
            topic,
            payload=json.dumps(payload),
            hostname="mosquitto",
            port=1883,
            qos=0,
        )
    except Exception as e:
        logger.debug(f"MQTT publish failed ({topic}): {e}")


async def _process_edge_tracks_async(gallinero_id: str, camera_id: str, tracks: list[dict], timestamp: str):
    """Procesa tracks edge con análisis completo.
    
    Pipeline v4.2 con Jetson Edge v4.5:
    1. Convertir tracks Jetson → formato tracker backend
    2. Actualizar tracker backend (para mantener sincronía con Jetson)
    3. Sync identities con registered birds (usa breed+sex+color del tracker)
    4. Detectar mating entre tracks
    
    El breed classification lo hace capture_manager cuando captura frames 4K.
    Esta función sincroniza el tracker backend con los tracks del Jetson.
    
    Se ejecuta en background (fire & forget) para no bloquear edge_event.
    """
    logger.info(f"🚀 Processing {len(tracks)} tracks from {camera_id} → {gallinero_id}")
    try:
        from services.bird_tracker import get_tracker, get_zones
        from services.mating_detector import get_mating_detector
        
        # 1. Obtener tracker y zones
        tracker = get_tracker(gallinero_id)
        zones = get_zones(gallinero_id)
        
        # 2. Convertir tracks Jetson → detecciones formato backend
        # Los tracks del Jetson vienen con {track_id, bbox[4], confidence, class_name}
        # El tracker backend espera {bbox_norm[4], confidence, category, ...}
        detections = []
        for t in tracks:
            # Asumir bbox ya normalizado (0-1) - Jetson debería normalizarlo
            bbox = t.get("bbox", [])
            if len(bbox) != 4:
                continue
                
            det = {
                "bbox_norm": bbox,  # [x1, y1, x2, y2] normalizado
                "confidence": t.get("confidence", 0.5),
                "category": "poultry",  # bird/dog/cat del COCO → poultry
                "class_name": t.get("class_name", "bird"),
                "jetson_track_id": t.get("track_id"),  # Preservar track_id original
            }
            detections.append(det)
        
        # 3. Actualizar tracker backend
        # Esto sincroniza posiciones, calcula zonas, detecta comportamiento
        if detections:
            enriched_dets = tracker.update(detections)
            logger.info(
                f"🔄 Updated tracker {gallinero_id} with {len(enriched_dets)} detections from Jetson"
            )
        
        # 4. Sync identities con registered birds
        # El tracker ahora tiene tracks activos, algunos con breed (si fueron clasificados antes)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "http://localhost:8000/birds/",
                    params={"gallinero_id": gallinero_id}
                )
                if resp.status_code == 200:
                    birds_list = resp.json()
                    registered_birds = [
                        {
                            "ai_vision_id": b.get("ai_vision_id"),
                            "breed": b.get("raza", ""),
                            "color": b.get("color", ""),
                            "sex": b.get("sexo", "")
                        }
                        for b in birds_list
                        if b.get("ai_vision_id")
                    ]
                    
                    if registered_birds:
                        synced = tracker.sync_registered_ids(registered_birds)
                        if synced > 0:
                            logger.info(f"🔗 Synced {synced} identities en {gallinero_id}")
        except Exception as e:
            logger.info(f"Error en sync_registered_ids: {e}")
        
        # 5. Detectar mating
        try:
            active_tracks = [t for t in tracker.tracks.values() if t.active]
            if len(active_tracks) >= 2:
                mating_det = get_mating_detector(gallinero_id)
                mating_events = mating_det.check_tracks(gallinero_id, active_tracks)
                if mating_events:
                    logger.info(f"💑 Detectadas {len(mating_events)} montas en {gallinero_id}")
        except Exception as e:
            logger.info(f"Error en mating detection: {e}")
            
    except Exception as e:
        logger.error(f"Error en _process_edge_tracks_async: {e}", exc_info=True)


# ─── Endpoints ────────────────────────────────────────


@router.post("/event", response_model=VisionEventResponse)
async def receive_vision_event(event: VisionEvent):
    """
    Recibe un evento de detección desde Jetson/cámara edge.
    Almacena en buffer y publica a MQTT.
    """
    event_id = str(uuid.uuid4())[:8]
    event_data = event.model_dump()
    event_data["event_id"] = event_id
    event_data["received_at"] = datetime.now(timezone.utc).isoformat()

    _recent_events.append(event_data)
    _trim(_recent_events)

    # Contar alertas potenciales (baja confianza general)
    alerts = 0
    for det in event.detections:
        if det.confidence < 0.3:
            alerts += 1

    # Publicar a MQTT
    _try_publish_mqtt("seedy/vision/events", {
        "event_id": event_id,
        "camera_id": event.camera_id,
        "farm_id": event.farm_id,
        "timestamp": event.timestamp,
        "n_detections": len(event.detections),
        "species_counts": _count_species(event),
        "inference_ms": event.inference_ms,
    })

    logger.info(
        f"Vision event {event_id}: cam={event.camera_id} "
        f"dets={len(event.detections)} inference={event.inference_ms:.1f}ms"
    )

    if log_agent_run:
        log_agent_run(
            task_type="vision",
            expert_used="expert_vision",
            model_used="yolov8s",
            tools_invoked=["yolo_detect"],
            input_summary=f"cam={event.camera_id} farm={event.farm_id}",
            output_summary=f"{len(event.detections)} detections, {alerts} alerts",
            latency_ms=int(event.inference_ms),
            confidence=max((d.confidence for d in event.detections), default=0.0),
            tenant_id=event.farm_id or "palacio",
        )

    return VisionEventResponse(
        status="ok",
        event_id=event_id,
        alerts_triggered=alerts,
    )


@router.post("/weight")
async def receive_weight_event(event: WeightEvent):
    """Recibe una estimación de peso desde la pipeline de visión."""
    weight_data = event.model_dump()
    weight_data["received_at"] = datetime.now(timezone.utc).isoformat()

    _recent_weights.append(weight_data)
    _trim(_recent_weights)

    # Publicar a MQTT
    _try_publish_mqtt("seedy/vision/weights", {
        "camera_id": event.camera_id,
        "farm_id": event.farm_id,
        "species": event.species,
        "weight_kg": event.estimated_weight_kg,
        "confidence": event.confidence,
        "calibrated": event.calibrated,
        "timestamp": event.timestamp,
    })

    logger.info(
        f"Weight: cam={event.camera_id} species={event.species} "
        f"weight={event.estimated_weight_kg:.1f}kg conf={event.confidence:.2f}"
    )

    return {"status": "ok", "weight_kg": event.estimated_weight_kg}


@router.post("/alert")
async def receive_behaviour_alert(alert: BehaviourAlert):
    """Recibe una alerta de comportamiento anómalo."""
    alert_data = alert.model_dump()
    alert_data["alert_id"] = str(uuid.uuid4())[:8]
    alert_data["received_at"] = datetime.now(timezone.utc).isoformat()

    _recent_alerts.append(alert_data)
    _trim(_recent_alerts)

    # Publicar a MQTT con topic por severidad
    _try_publish_mqtt(f"seedy/vision/alerts/{alert.severity}", {
        "alert_id": alert_data["alert_id"],
        "camera_id": alert.camera_id,
        "farm_id": alert.farm_id,
        "behaviour": alert.behaviour,
        "severity": alert.severity,
        "species": alert.species,
        "confidence": alert.confidence,
        "duration_s": alert.duration_seconds,
        "timestamp": alert.timestamp,
    })

    logger.warning(
        f"🚨 Alert [{alert.severity}]: cam={alert.camera_id} "
        f"behaviour={alert.behaviour} species={alert.species} "
        f"conf={alert.confidence:.2f} dur={alert.duration_seconds:.1f}s"
    )

    return {"status": "ok", "alert_id": alert_data["alert_id"], "severity": alert.severity}


@router.get("/stats", response_model=VisionStats)
async def get_vision_stats(
    camera_id: str = Query(..., description="ID de la cámara"),
    hours: int = Query(1, ge=1, le=168, description="Ventana temporal en horas"),
):
    """
    Estadísticas agregadas de visión para una cámara
    en la ventana temporal indicada.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()

    # Filtrar eventos
    cam_events = [
        e for e in _recent_events
        if e.get("camera_id") == camera_id
        and e.get("timestamp", "") >= cutoff_iso
    ]

    cam_weights = [
        w for w in _recent_weights
        if w.get("camera_id") == camera_id
        and w.get("timestamp", "") >= cutoff_iso
    ]

    cam_alerts = [
        a for a in _recent_alerts
        if a.get("camera_id") == camera_id
        and a.get("timestamp", "") >= cutoff_iso
    ]

    # Agregar
    total_dets = 0
    species_counts: dict[str, int] = defaultdict(int)
    confidences: list[float] = []

    for e in cam_events:
        dets = e.get("detections", [])
        total_dets += len(dets)
        for d in dets:
            species_counts[d["class_name"]] += 1
            confidences.append(d["confidence"])

    # Pesos medios por especie
    weight_sums: dict[str, list[float]] = defaultdict(list)
    for w in cam_weights:
        weight_sums[w["species"]].append(w["estimated_weight_kg"])

    avg_weights = {
        sp: round(sum(vals) / len(vals), 1)
        for sp, vals in weight_sums.items()
    }

    # Distribución de comportamientos
    behaviour_dist: dict[str, int] = defaultdict(int)
    for a in cam_alerts:
        behaviour_dist[a["behaviour"]] += 1

    return VisionStats(
        camera_id=camera_id,
        period_start=cutoff_iso,
        period_end=now.isoformat(),
        total_detections=total_dets,
        species_counts=dict(species_counts),
        avg_confidence=round(sum(confidences) / max(len(confidences), 1), 3),
        alerts_count=len(cam_alerts),
        avg_weight_kg=avg_weights,
        behaviour_distribution=dict(behaviour_dist),
    )


@router.get("/alerts")
async def list_alerts(
    farm_id: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Lista las alertas recientes, filtrables por granja y severidad."""
    filtered = _recent_alerts.copy()

    if farm_id:
        filtered = [a for a in filtered if a.get("farm_id") == farm_id]
    if severity:
        filtered = [a for a in filtered if a.get("severity") == severity]

    # Las más recientes primero
    filtered.sort(key=lambda a: a.get("timestamp", ""), reverse=True)

    return {"alerts": filtered[:limit], "total": len(filtered)}


@router.get("/cameras")
async def list_cameras():
    """Lista las cámaras activas (que han enviado eventos recientemente)."""
    cameras: dict[str, dict] = {}

    for e in _recent_events:
        cam_id = e.get("camera_id", "")
        if cam_id not in cameras:
            cameras[cam_id] = {
                "camera_id": cam_id,
                "farm_id": e.get("farm_id"),
                "barn_id": e.get("barn_id"),
                "first_seen": e.get("timestamp"),
                "last_seen": e.get("timestamp"),
                "total_events": 0,
            }
        cameras[cam_id]["last_seen"] = e.get("timestamp")
        cameras[cam_id]["total_events"] += 1

    return {"cameras": list(cameras.values())}


@router.post("/edge_event")
async def receive_edge_event(event_data: dict):
    """
    Recibe eventos desde Jetson Edge v4.5 (Seedy Edge).
    
    Schema v4.5:
        schema_version: "4.5"
        timestamp: ISO8601
        edge_node_id: str (ej: "jetson_orin_nano_01")
        camera_id: str
        gallinero_id: str
        event_type: "detection" | "snapshot" | "heartbeat"
        tracks: [ {track_id, bbox[4], confidence, class_name, class_id} ]
    
    Almacena en buffer y publica a MQTT (seedy/vision/edge_events).
    v4.2: Procesa tracks con análisis completo (breed, identity, mating).
    """
    event_id = str(uuid.uuid4())[:8]
    event_data["event_id"] = event_id
    event_data["backend_received_at"] = datetime.now(timezone.utc).isoformat()
    
    # Validar schema_version
    if event_data.get("schema_version") != "4.5":
        logger.warning(f"Edge event schema version mismatch: {event_data.get('schema_version')}")
    
    # Almacenar en buffer
    _recent_events.append(event_data)
    _trim(_recent_events)
    
    # Publicar a MQTT
    _try_publish_mqtt("seedy/vision/edge_events", event_data)
    
    # Log stats
    n_tracks = len(event_data.get("tracks", []))
    logger.info(
        f"Edge event {event_id} from {event_data.get('edge_node_id')}/{event_data.get('camera_id')}: "
        f"{n_tracks} tracks, type={event_data.get('event_type')}"
    )
    
    # Guardar snapshot en behavior_event_store si hay tracks
    if n_tracks > 0 and event_data.get("gallinero_id"):
        try:
            behavior_event_store.store_edge_snapshot(
                gallinero_id=event_data["gallinero_id"],
                camera_id=event_data.get("camera_id", "unknown"),
                tracks=event_data.get("tracks", []),
                timestamp=event_data.get("timestamp")
            )
        except Exception as e:
            logger.error(f"Error guardando edge snapshot: {e}")
        
        # 🆕 v4.2: Procesar tracks con análisis completo (en background)
        asyncio.create_task(_process_edge_tracks_async(
            gallinero_id=event_data["gallinero_id"],
            camera_id=event_data.get("camera_id", "unknown"),
            tracks=event_data.get("tracks", []),
            timestamp=event_data.get("timestamp")
        ))
    
    return {
        "status": "ok",
        "event_id": event_id,
        "tracks_received": n_tracks,
        "backend_timestamp": event_data["backend_received_at"],
    }


# ─── Helpers ──────────────────────────────────────────

def _count_species(event: VisionEvent) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for d in event.detections:
        counts[d.class_name] += 1
    return dict(counts)
