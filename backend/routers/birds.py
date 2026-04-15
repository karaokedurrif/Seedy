"""
Seedy Backend — Router /birds

Gestión del registro de aves identificadas por IA Vision.
Asigna IDs PAL-2026-XXXX secuenciales y agrupa por raza.
Los datos persisten en un fichero JSON en /app/data/.
"""

import json
import logging
import math
import mimetypes
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

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


# ─── Assets estáticos de aves (imágenes de referencia, modelos 3D) ────────

_BIRD_3D_DIR = Path("/app/data/bird_3d_refs")
_ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _find_bird_asset(bird_id: str, base_dir: Path, extensions: tuple[str, ...]) -> Path | None:
    """Busca el primer archivo que exista para bird_id probando las extensiones en orden."""
    for ext in extensions:
        candidate = base_dir / f"{bird_id}{ext}"
        if candidate.is_file():
            return candidate
    return None


@router.head("/{bird_id}/reference-image")
@router.get("/{bird_id}/reference-image")
async def get_reference_image(bird_id: str, request: Request):
    """Devuelve la imagen de referencia del ave con el Content-Type real del archivo.

    Busca en data/bird_3d_refs/ probando .jpg, .jpeg, .png, .webp en ese orden.
    Soporta HEAD (para comprobación rápida desde el frontend) y GET.
    """
    path = _find_bird_asset(bird_id, _BIRD_3D_DIR, _ALLOWED_IMAGE_EXTENSIONS)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No reference image for {bird_id}")

    # Determinar MIME real a partir de la extensión del archivo encontrado
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"

    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Content-Type": mime,
                "Content-Length": str(path.stat().st_size),
                "Cache-Control": "public, max-age=3600",
            },
        )

    return FileResponse(
        path=str(path),
        media_type=mime,
        filename=path.name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.head("/{bird_id}/model.glb")
@router.get("/{bird_id}/model.glb")
async def get_bird_model(bird_id: str, request: Request):
    """Devuelve el modelo 3D GLB del ave si existe."""
    glb_path = _BIRD_3D_DIR / f"{bird_id}.glb"
    if not glb_path.is_file():
        raise HTTPException(status_code=404, detail=f"No 3D model for {bird_id}")

    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Content-Type": "model/gltf-binary",
                "Content-Length": str(glb_path.stat().st_size),
                "Cache-Control": "public, max-age=3600",
            },
        )

    return FileResponse(
        path=str(glb_path),
        media_type="model/gltf-binary",
        filename=glb_path.name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ─── Fotos, tracking, eventos, Gompertz, generate-3d ─────────────────────

_PHOTOS_DIR = Path("/app/data/bird_photos")
_GALLERY_DIR = Path("/app/data/bird_gallery")
_BEHAVIOR_DIR = Path("/app/data/behavior_events")


def _find_bird(bird_id: str) -> dict | None:
    """Busca un ave en el registro."""
    for b in _registry:
        if b["bird_id"] == bird_id:
            return b
    return None


@router.get("/{bird_id}/photos")
async def get_bird_photos(bird_id: str):
    """Devuelve las fotos disponibles de un ave.

    Busca en:
    1. data/bird_photos/{bird_id}.jpg (foto principal de registro)
    2. data/bird_gallery/{ovo_num}/ (galería de capturas OvoSfera)
    """
    photos: list[dict] = []

    # Foto principal del registro
    main_photo = _find_bird_asset(bird_id, _PHOTOS_DIR, _ALLOWED_IMAGE_EXTENSIONS)
    if main_photo:
        stat = main_photo.stat()
        photos.append({
            "url": f"/birds/{bird_id}/photo/main",
            "filename": main_photo.name,
            "is_main": True,
            "timestamp": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    # Galería OvoSfera (las carpetas son IDs numéricos de OvoSfera)
    # Intentar mapear bird_id → número secuencial final
    seq_str = bird_id.split("-")[-1].lstrip("0") or "0"
    gallery_dir = _GALLERY_DIR / seq_str
    if gallery_dir.is_dir():
        for img_path in sorted(gallery_dir.iterdir()):
            if img_path.suffix.lower() in _ALLOWED_IMAGE_EXTENSIONS:
                stat = img_path.stat()
                photos.append({
                    "url": f"/birds/{bird_id}/gallery/{img_path.name}",
                    "filename": img_path.name,
                    "is_main": False,
                    "timestamp": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })

    return {"photos": photos, "total": len(photos)}


@router.get("/{bird_id}/photo/main")
async def get_bird_main_photo(bird_id: str):
    """Sirve la foto principal del ave."""
    path = _find_bird_asset(bird_id, _PHOTOS_DIR, _ALLOWED_IMAGE_EXTENSIONS)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No main photo for {bird_id}")
    mime, _ = mimetypes.guess_type(path.name)
    return FileResponse(path=str(path), media_type=mime or "image/jpeg")


@router.get("/{bird_id}/gallery/{filename}")
async def get_bird_gallery_photo(bird_id: str, filename: str):
    """Sirve una foto de la galería OvoSfera del ave."""
    seq_str = bird_id.split("-")[-1].lstrip("0") or "0"
    photo_path = _GALLERY_DIR / seq_str / filename

    # Prevenir path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail=f"Photo not found: {filename}")

    mime, _ = mimetypes.guess_type(photo_path.name)
    return FileResponse(path=str(photo_path), media_type=mime or "image/jpeg")


@router.get("/{bird_id}/tracking")
async def get_bird_tracking(bird_id: str, hours: int = Query(24, ge=1, le=168)):
    """Devuelve las posiciones de tracking del ave en las últimas N horas.

    Lee los archivos JSONL de behavior_events buscando tracks con bird_id o ai_vision_id.
    """
    bird = _find_bird(bird_id)
    if bird is None:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    gallinero = bird.get("gallinero", "")
    ai_vid = bird.get("ai_vision_id", "")
    gall_dir = _BEHAVIOR_DIR / gallinero

    if not gall_dir.is_dir():
        return {"positions": [], "summary": {"total_detections": 0, "cameras_seen": []}}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    positions: list[dict] = []
    cameras_seen: set[str] = set()

    # Leer ficheros JSONL de los últimos días
    for day_offset in range(min(hours // 24 + 1, 8)):
        day = (datetime.now(timezone.utc) - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        jsonl_path = gall_dir / f"{day}.jsonl"
        if not jsonl_path.is_file():
            continue
        try:
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = event.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue
                if ts < cutoff:
                    continue

                for track in event.get("tracks", []):
                    tid = track.get("bird_id", "")
                    if tid == bird_id or tid == ai_vid or (not tid and track.get("track_id")):
                        center = track.get("center", [0.5, 0.5])
                        # Mapear coordenadas normalizadas (0-1) → plano (0-30, 0-15)
                        positions.append({
                            "x": round(center[0] * 30, 2),
                            "y": round(center[1] * 15, 2),
                            "ts": ts_str,
                            "zone": track.get("zone", ""),
                            "confidence": track.get("confidence", 0),
                        })
                        camera = event.get("camera_id", event.get("gallinero_id", ""))
                        if camera:
                            cameras_seen.add(camera)
        except Exception as e:
            logger.warning(f"Error reading tracking data {jsonl_path}: {e}")
            continue

    # Limitar a las últimas 200 posiciones para el minimap
    positions = positions[-200:]

    return {
        "positions": positions,
        "summary": {
            "total_detections": len(positions),
            "cameras_seen": sorted(cameras_seen),
        },
    }


# Parámetros Gompertz teóricos por raza (A=peso asintótico kg, b=desplazamiento, k=tasa crecimiento)
_GOMPERTZ_PARAMS: dict[str, dict] = {
    "marans":       {"A": 3.5, "b": 4.2, "k": 0.018},
    "sussex":       {"A": 3.8, "b": 4.0, "k": 0.017},
    "vorwerk":      {"A": 2.8, "b": 4.1, "k": 0.020},
    "orpington":    {"A": 4.2, "b": 4.3, "k": 0.016},
    "bresse":       {"A": 3.2, "b": 4.0, "k": 0.019},
    "araucana":     {"A": 2.5, "b": 3.9, "k": 0.021},
    "castellana":   {"A": 2.3, "b": 3.8, "k": 0.022},
    "pita_pinta":   {"A": 3.0, "b": 4.1, "k": 0.018},
    # Genérico para razas no mapeadas
    "_default":     {"A": 3.0, "b": 4.0, "k": 0.019},
}


@router.get("/{bird_id}/gompertz")
async def get_bird_gompertz(bird_id: str):
    """Devuelve los parámetros de la curva Gompertz para el ave.

    Usa parámetros teóricos por raza. En el futuro, se ajustarán con
    registros reales de peso del ave.
    """
    bird = _find_bird(bird_id)
    if bird is None:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    breed_key = bird.get("breed", "").lower().replace(" ", "_")
    params = _GOMPERTZ_PARAMS.get(breed_key, _GOMPERTZ_PARAMS["_default"])

    # Ajustar peso asintótico si es macho (+20% teórico)
    sex = bird.get("sex", "")
    if sex in ("male", "M"):
        params = {**params, "A": round(params["A"] * 1.2, 2)}

    return {
        "gompertz_params": params,
        "breed": bird.get("breed", ""),
        "sex": sex,
        "weight_records": [],  # TODO: integrar con pesajes reales de OvoSfera
        "note": "Parámetros teóricos por raza. Se ajustarán con datos reales de peso.",
    }


@router.get("/{bird_id}/events")
async def get_bird_events(bird_id: str):
    """Devuelve eventos de la línea temporal del ave.

    Genera eventos a partir de:
    - Datos del registro (first_seen, last_seen)
    - Fotos capturadas
    - Futuros: vacunaciones, pesajes, tratamientos desde OvoSfera
    """
    bird = _find_bird(bird_id)
    if bird is None:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    events: list[dict] = []

    # Evento de primera detección
    if bird.get("first_seen"):
        events.append({
            "date": bird["first_seen"],
            "type": "reid",
            "description": f"Primera identificación IA — {bird.get('breed', '?')} {bird.get('color', '')}".strip(),
        })

    # Fotos capturadas (de bird_photos y gallery)
    main_photo = _find_bird_asset(bird_id, _PHOTOS_DIR, _ALLOWED_IMAGE_EXTENSIONS)
    if main_photo:
        stat = main_photo.stat()
        events.append({
            "date": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "type": "photo",
            "description": "Foto de registro capturada",
        })

    seq_str = bird_id.split("-")[-1].lstrip("0") or "0"
    gallery_dir = _GALLERY_DIR / seq_str
    if gallery_dir.is_dir():
        for img_path in sorted(gallery_dir.iterdir()):
            if img_path.suffix.lower() in _ALLOWED_IMAGE_EXTENSIONS:
                stat = img_path.stat()
                events.append({
                    "date": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "type": "photo",
                    "description": f"Captura OvoSfera — {img_path.name}",
                })

    # Ordenar cronológicamente
    events.sort(key=lambda e: e.get("date", ""))

    return {"events": events, "total": len(events)}


@router.post("/{bird_id}/generate-3d")
async def generate_bird_3d(bird_id: str):
    """Genera (o devuelve) el modelo 3D / imagen de referencia del ave.

    - Si ya existe un .glb → status: exists
    - Si existe imagen de referencia FLUX → status: ref_only (devuelve URL)
    - Si no hay nada → status: no_source (necesita captura primero)

    TODO: integrar con Tripo3D API cuando se active la key.
    """
    bird = _find_bird(bird_id)
    if bird is None:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no encontrada")

    # ¿Ya existe el GLB?
    glb_path = _BIRD_3D_DIR / f"{bird_id}.glb"
    if glb_path.is_file():
        return {"status": "exists", "model_url": f"/birds/{bird_id}/model.glb"}

    # ¿Existe imagen de referencia FLUX?
    ref_image = _find_bird_asset(bird_id, _BIRD_3D_DIR, _ALLOWED_IMAGE_EXTENSIONS)
    if ref_image:
        return {
            "status": "ref_only",
            "reference_image": f"/birds/{bird_id}/reference-image",
            "message": "Imagen de referencia FLUX disponible. Modelo 3D pendiente de Tripo3D.",
        }

    # ¿Tiene foto principal? Podría usarse como base para generar
    main_photo = _find_bird_asset(bird_id, _PHOTOS_DIR, _ALLOWED_IMAGE_EXTENSIONS)
    if main_photo:
        return {
            "status": "no_3d",
            "message": "Foto disponible pero aún no se ha generado imagen de referencia ni modelo 3D.",
            "hint": "Se requiere generar imagen FLUX primero y luego el modelo Tripo3D.",
        }

    return {
        "status": "no_source",
        "message": "No hay foto ni referencia para generar modelo 3D. Captura el ave primero.",
    }
