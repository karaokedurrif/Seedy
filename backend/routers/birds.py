"""
Seedy Backend — Router /birds

Gestión del registro de aves identificadas por IA Vision.
Asigna IDs PAL-2026-XXXX secuenciales y agrupa por raza.
Los datos persisten en un fichero JSON en /app/data/.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from models.schemas import BirdRecord, BirdRegisterRequest, BirdUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/birds", tags=["birds"])

# ─── Persistencia ────────────────────────────────────

_DATA_PATH = Path("/app/data/birds_registry.json")
_registry: list[dict] = []
_next_seq: int = 1  # Siguiente número secuencial global


def _load_registry():
    """Carga el registro desde disco al iniciar."""
    global _registry, _next_seq
    if _DATA_PATH.exists():
        try:
            data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
            _registry = data.get("birds", [])
            _next_seq = data.get("next_seq", 1)
            logger.info(f"Birds registry loaded: {len(_registry)} aves, next_seq={_next_seq}")
        except Exception as e:
            logger.error(f"Error loading birds registry: {e}")
            _registry = []
            _next_seq = 1
    else:
        _registry = []
        _next_seq = 1


def _save_registry():
    """Guarda el registro a disco."""
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATA_PATH.write_text(
        json.dumps({"birds": _registry, "next_seq": _next_seq}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# Cargar al importar
_load_registry()


# ─── Helpers ─────────────────────────────────────────

def _generate_bird_id(seq: int) -> str:
    """Genera ID del tipo PAL-2026-XXXX."""
    year = datetime.now(timezone.utc).year
    return f"PAL-{year}-{seq:04d}"


def _get_ia_vision_number(breed: str, color: str) -> int:
    """Calcula el siguiente número IA Vision para una raza+color.
    Si hay 3 Sussex blanco (ia_vision_number 1,2,3), el siguiente es 4.
    """
    same_group = [
        b for b in _registry
        if b["breed"].lower() == breed.lower()
        and b.get("color", "").lower() == color.lower()
    ]
    if not same_group:
        return 1
    return max(b["ia_vision_number"] for b in same_group) + 1


# ─── Endpoints ───────────────────────────────────────

@router.get("/")
async def list_birds(
    gallinero: str | None = Query(None, description="Filtrar por gallinero"),
    breed: str | None = Query(None, description="Filtrar por raza"),
    color: str | None = Query(None, description="Filtrar por color/variedad"),
):
    """Lista todas las aves registradas."""
    birds = _registry.copy()
    if gallinero:
        birds = [b for b in birds if b["gallinero"] == gallinero]
    if breed:
        birds = [b for b in birds if b["breed"].lower() == breed.lower()]
    if color:
        birds = [b for b in birds if b.get("color", "").lower() == color.lower()]
    return {"birds": birds, "total": len(birds)}


@router.get("/{bird_id}")
async def get_bird(bird_id: str):
    """Obtiene un ave por su ID, incluyendo comportamiento, montas y datos OvoSfera."""
    for b in _registry:
        if b["bird_id"] == bird_id:
            result = {**b}
            gallinero = b.get("gallinero", "")

            # Datos OvoSfera (fuente de verdad del ganadero)
            try:
                import httpx
                import os
                ovo_api = os.environ.get("OVOSFERA_API_URL", "https://hub.ovosfera.com/api/ovosfera")
                ovo_farm = os.environ.get("OVOSFERA_FARM_SLUG", "palacio")
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(f"{ovo_api}/farms/{ovo_farm}/aves")
                    if resp.status_code == 200:
                        aves = resp.json()
                        ovo = next((a for a in aves if a.get("anilla") == bird_id), None)
                        if ovo:
                            result["ovosfera"] = {
                                "id": ovo.get("id"),
                                "raza": ovo.get("raza"),
                                "color": ovo.get("color"),
                                "sexo": ovo.get("sexo"),
                                "tipo": ovo.get("tipo"),
                                "gallinero": ovo.get("gallinero"),
                                "peso": ovo.get("peso"),
                                "fecha_nacimiento": ovo.get("fecha_nacimiento"),
                                "estado": ovo.get("estado"),
                                "notas": ovo.get("notas"),
                                "foto": ovo.get("foto"),
                            }
                            gallinero = ovo.get("gallinero") or gallinero
            except Exception:
                pass  # OvoSfera not available, use Seedy data only

            # Comportamiento (7 dimensiones, 24h)
            try:
                from services.behavior_inference import get_bird_behavior
                from services.behavior_serializer import to_api_response

                inference = get_bird_behavior(bird_id, gallinero, "24h")
                beh_resp = to_api_response(inference)
                result["behavior"] = beh_resp
            except Exception:
                result["behavior"] = None

            # Montas (últimos 7 días)
            try:
                from services.mating_detector import query_mating_events

                end_ts = datetime.now(timezone.utc)
                start_ts = end_ts - timedelta(days=7)
                events = query_mating_events(gallinero, start_ts, end_ts, bird_id=bird_id)
                as_mounter = sum(1 for e in events if e.get("mounter", {}).get("bird_id") == bird_id)
                as_mounted = sum(1 for e in events if e.get("mounted", {}).get("bird_id") == bird_id)
                partners = set()
                for e in events:
                    m_id = e.get("mounter", {}).get("bird_id", "")
                    f_id = e.get("mounted", {}).get("bird_id", "")
                    if m_id == bird_id and f_id:
                        partners.add(f_id)
                    elif f_id == bird_id and m_id:
                        partners.add(m_id)
                result["mating_7d"] = {
                    "as_mounter": as_mounter,
                    "as_mounted": as_mounted,
                    "total_events": len(events),
                    "partners": sorted(partners),
                    "recent_events": events[-5:],  # Últimos 5 eventos
                }
            except Exception:
                result["mating_7d"] = None

            return result
    raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")


@router.post("/register", response_model=BirdRecord)
async def register_bird(req: BirdRegisterRequest):
    """
    Registra un ave nueva detectada por IA Vision.
    Asigna ID PAL-2026-XXXX y ai_vision_id como sussexbl1, maransnc2, etc.
    """
    global _next_seq

    # Importar el generador de vision_id desde vision_identify
    from routers.vision_identify import _build_vision_id

    now = datetime.now(timezone.utc).isoformat()
    bird_id = _generate_bird_id(_next_seq)
    ia_number = _get_ia_vision_number(req.breed, req.color)
    ai_vid = _build_vision_id(req.breed, req.color, ia_number)

    bird = {
        "bird_id": bird_id,
        "breed": req.breed,
        "color": req.color,
        "sex": req.sex,
        "gallinero": req.gallinero,
        "first_seen": now,
        "last_seen": now,
        "ia_vision_number": ia_number,
        "ai_vision_id": ai_vid,
        "confidence": req.confidence,
        "photo_path": None,
        "photo_b64": req.photo_b64,
        "notes": "",
    }

    # Guardar foto si viene
    if req.photo_b64:
        photo_dir = Path("/app/data/bird_photos")
        photo_dir.mkdir(parents=True, exist_ok=True)
        photo_path = photo_dir / f"{bird_id}.jpg"
        try:
            import base64
            photo_path.write_bytes(base64.b64decode(req.photo_b64))
            bird["photo_path"] = str(photo_path)
        except Exception as e:
            logger.warning(f"Error saving bird photo: {e}")

    _registry.append(bird)
    _next_seq += 1
    _save_registry()

    logger.info(
        f"🐔 Registered {bird_id}: {req.breed} {req.color} → {ai_vid} "
        f"gallinero={req.gallinero} conf={req.confidence:.2f}"
    )
    return BirdRecord(**bird)


@router.patch("/{bird_id}")
async def update_bird(bird_id: str, req: BirdUpdateRequest):
    """Actualiza datos de un ave."""
    for bird in _registry:
        if bird["bird_id"] == bird_id:
            updates = req.model_dump(exclude_none=True)
            bird.update(updates)
            bird["last_seen"] = datetime.now(timezone.utc).isoformat()
            _save_registry()
            return bird
    raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")


@router.post("/{bird_id}/sighting")
async def record_sighting(bird_id: str, confidence: float = 0.0, photo_b64: str | None = None):
    """Registra un avistamiento (actualiza last_seen y opcionalmente la foto)."""
    for bird in _registry:
        if bird["bird_id"] == bird_id:
            bird["last_seen"] = datetime.now(timezone.utc).isoformat()
            if confidence > bird.get("confidence", 0):
                bird["confidence"] = confidence
                if photo_b64:
                    bird["photo_b64"] = photo_b64
            _save_registry()
            return {"status": "ok", "bird_id": bird_id}
    raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")


@router.get("/stats/summary")
async def bird_stats():
    """Resumen de aves por gallinero y raza."""
    from collections import Counter
    by_gallinero = Counter(b["gallinero"] for b in _registry)
    by_breed = Counter(b["breed"] for b in _registry)
    return {
        "total": len(_registry),
        "by_gallinero": dict(by_gallinero),
        "by_breed": dict(by_breed),
    }


@router.delete("/{bird_id}")
async def delete_bird(bird_id: str):
    """Elimina un ave del registro."""
    global _registry
    before = len(_registry)
    _registry = [b for b in _registry if b["bird_id"] != bird_id]
    if len(_registry) == before:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")
    _save_registry()
    return {"status": "ok", "deleted": bird_id}


@router.post("/reset")
async def reset_registry():
    """Resetea el registro completo de aves (para reempezar con censo limpio)."""
    global _registry, _next_seq
    count = len(_registry)
    _registry = []
    _next_seq = 1
    _save_registry()
    logger.info(f"🗑️ Bird registry reset: {count} records cleared")
    return {"status": "reset", "cleared": count}


# ─── Per-bird digital twin endpoints (Task E) ───────

@router.get("/{bird_id}/photos")
async def get_bird_photos(bird_id: str):
    """Gallery of IA-captured photos for a bird."""
    bird = None
    for b in _registry:
        if b["bird_id"] == bird_id:
            bird = b
            break
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    # Check gallery directory
    gallery_dir = Path(f"/app/data/bird_gallery/{bird.get('ai_vision_id', bird_id)}")
    photos = []
    if gallery_dir.exists():
        for f in sorted(gallery_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True):
            photos.append({
                "filename": f.name,
                "url": f"/birds/{bird_id}/photos/{f.name}",
                "timestamp": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                "size": f.stat().st_size,
            })
    # Include the main photo_b64 if available
    if bird.get("photo_b64"):
        photos.insert(0, {
            "filename": "main_capture.jpg",
            "url": f"/birds/{bird_id}/photo",
            "timestamp": bird.get("last_seen", ""),
            "size": len(bird["photo_b64"]) * 3 // 4,
            "is_main": True,
        })
    return {"bird_id": bird_id, "photos": photos, "total": len(photos)}


@router.get("/{bird_id}/tracking")
async def get_bird_tracking(bird_id: str, hours: int = Query(24, ge=1, le=168)):
    """Tracking positions from YOLO detections (last N hours)."""
    bird = None
    for b in _registry:
        if b["bird_id"] == bird_id:
            bird = b
            break
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    # Tracking data comes from InfluxDB or stored detections
    # For now return structure ready for real data integration
    return {
        "bird_id": bird_id,
        "hours": hours,
        "positions": [],  # [{x, y, timestamp, camera, confidence}]
        "summary": {
            "total_detections": 0,
            "cameras_seen": [],
            "most_active_zone": None,
        },
    }


@router.get("/{bird_id}/detections")
async def get_bird_detections(bird_id: str, limit: int = Query(50, ge=1, le=500)):
    """Re-ID detection history."""
    bird = None
    for b in _registry:
        if b["bird_id"] == bird_id:
            bird = b
            break
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    return {
        "bird_id": bird_id,
        "detections": [],  # [{timestamp, camera, confidence, breed, color, photo_url}]
        "total": 0,
    }


@router.get("/{bird_id}/gompertz")
async def get_bird_gompertz(bird_id: str):
    """Growth curve data (Gompertz model) for weight tracking."""
    bird = None
    for b in _registry:
        if b["bird_id"] == bird_id:
            bird = b
            break
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    # Gompertz parameters vary by breed
    breed = bird.get("breed", "").lower()
    sex = bird.get("sex", "").lower()

    # Default parameters (capón/heritage breeds)
    # W(t) = A * exp(-b * exp(-k * t))
    # A = asymptotic weight, b = displacement, k = growth rate
    gompertz_params = {
        "sussex":   {"A": 4.2, "b": 4.5, "k": 0.020},
        "bresse":   {"A": 3.8, "b": 4.3, "k": 0.022},
        "marans":   {"A": 3.5, "b": 4.1, "k": 0.021},
        "sulmtaler": {"A": 3.2, "b": 4.0, "k": 0.019},
    }

    params = gompertz_params.get(breed, {"A": 3.5, "b": 4.2, "k": 0.020})
    if sex in ("h", "hembra", "gallina"):
        params["A"] *= 0.75  # Hens are smaller

    return {
        "bird_id": bird_id,
        "breed": bird.get("breed", ""),
        "sex": bird.get("sex", ""),
        "gompertz_params": params,
        "weight_records": [],  # [{date, weight_kg, source}]
        "predicted_curve": [],  # Will be computed client-side from params
    }


@router.get("/{bird_id}/events")
async def get_bird_events(bird_id: str):
    """Timeline events for a bird: detections, weigh-ins, vaccinations, transfers."""
    bird = None
    for b in _registry:
        if b["bird_id"] == bird_id:
            bird = b
            break
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    events = []
    # Registration event
    if bird.get("registered_at"):
        events.append({
            "type": "registration",
            "date": bird["registered_at"],
            "description": f"Registrada como {bird.get('breed', '?')} {bird.get('sex', '?')}",
        })
    # Last sighting
    if bird.get("last_seen"):
        events.append({
            "type": "reid",
            "date": bird["last_seen"],
            "description": f"Última detección Re-ID (confianza {bird.get('last_confidence', 0):.0%})",
        })
    # Sightings history
    for s in bird.get("sightings", []):
        events.append({
            "type": "detection",
            "date": s.get("timestamp", ""),
            "description": f"Detectada por {s.get('camera', 'IA Vision')} ({s.get('confidence', 0):.0%})",
        })

    # Sort chronologically
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    return {"bird_id": bird_id, "events": events}


# ─── v4.2: Identity management endpoints ────────────


@router.post("/{bird_id}/reset_ai_vision_id")
async def reset_ai_vision_id(bird_id: str):
    """Resetea el ai_vision_id de un ave, liberando su IdentityLock.

    Útil cuando la IA asignó mal una identidad (e.g., Sussex Silver → bresseblan1).
    Tras el reset, el sistema re-evaluará la identidad en el siguiente ciclo sync.
    """
    bird = None
    for b in _registry:
        if b["bird_id"] == bird_id:
            bird = b
            break
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    old_vid = bird.get("ai_vision_id", "")

    # Liberar del AssignmentRegistry en todos los trackers activos
    try:
        from services.bird_tracker import get_tracker
        from services.identity.identity_lock import get_registry

        for gallinero_id in ["gallinero_palacio"]:
            tracker = get_tracker(gallinero_id)
            registry = get_registry(gallinero_id)
            # Limpiar tracks que tenían este ai_vision_id
            for t in tracker.tracks.values():
                if t.ai_vision_id == old_vid:
                    registry.release(t.track_id)
                    t.ai_vision_id = ""
                    t.identity_lock = None
                    logger.info(
                        f"🔄 Reset: track#{t.track_id} liberado de {old_vid} "
                        f"en {gallinero_id}"
                    )
    except ImportError:
        pass

    # No borrar el ai_vision_id del registro — solo forzar re-evaluación
    logger.info(f"🔄 Reset ai_vision_id para {bird_id} (was: {old_vid})")

    return {
        "status": "ok",
        "bird_id": bird_id,
        "old_ai_vision_id": old_vid,
        "message": "IdentityLock liberado. Re-sync en el próximo ciclo (≤60s).",
    }
