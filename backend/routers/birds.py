"""
Seedy Backend — Router /birds

Gestión del registro de aves identificadas por IA Vision.
Asigna IDs PAL-2026-XXXX secuenciales y agrupa por raza.
Los datos persisten en un fichero JSON en /app/data/.
"""

import json
import logging
from datetime import datetime, timezone
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
    """Obtiene un ave por su ID."""
    for b in _registry:
        if b["bird_id"] == bird_id:
            return b
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
            if photo_b64 and confidence > bird.get("confidence", 0):
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
