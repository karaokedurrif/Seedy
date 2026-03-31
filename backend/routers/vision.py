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


# ─── Helpers ──────────────────────────────────────────

def _count_species(event: VisionEvent) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for d in event.detections:
        counts[d.class_name] += 1
    return dict(counts)
