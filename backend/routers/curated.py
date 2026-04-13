"""
Seedy Backend — API endpoints para dataset curado

Endpoints para consultar estadísticas de curación,
ver gaps de dataset, y navegar crops curados.
"""

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision/curated", tags=["curated"])


@router.get("/stats")
async def curated_stats():
    """Estadísticas del dataset curado (crops + frames)."""
    from services.crop_curator import get_curator
    curator = get_curator()
    return curator.get_stats()


@router.get("/gaps")
async def dataset_gaps():
    """Razas con pocos crops + progreso de frames para entrenamiento de detector."""
    from services.crop_curator import get_curator
    curator = get_curator()
    return curator.get_dataset_gaps()


@router.get("/browse/{breed}")
async def browse_breed(breed: str, limit: int = 20):
    """Lista crops curados de una raza específica."""
    if limit > 200:
        limit = 200
    from services.crop_curator import get_curator
    curator = get_curator()
    items = curator.browse_breed(breed, limit)
    return {"breed": breed, "count": len(items), "items": items}


@router.get("/frames/stats")
async def frames_stats():
    """Estadísticas de frames anotados para entrenamiento de detector."""
    from services.crop_curator import get_curator, CURATED_FRAMES_DIR
    curator = get_curator()
    stats = curator.get_stats()

    # Contar labels
    labels_dir = CURATED_FRAMES_DIR / "labels"
    label_count = len(list(labels_dir.glob("*.txt"))) if labels_dir.exists() else 0

    return {
        "frames_annotated": stats.get("frames_annotated", 0),
        "labels_count": label_count,
        "target": 500,
        "ready_to_train": stats.get("frames_annotated", 0) >= 500,
    }
