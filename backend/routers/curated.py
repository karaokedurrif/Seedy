"""Seedy Backend — Router: Gestión de crops curados para training."""

import logging
from fastapi import APIRouter

from services.crop_curator import get_crop_curator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision/curated", tags=["curated"])


@router.get("/stats")
async def curated_stats():
    """Stats del dataset curado: total, por raza, última actualización."""
    curator = get_crop_curator()
    return curator.get_stats()


@router.get("/gaps")
async def curated_gaps(target: int = 100):
    """Razas que necesitan más datos de entrenamiento (<target crops)."""
    curator = get_crop_curator()
    return {"gaps": curator.get_dataset_gaps(target), "target": target}


@router.get("/browse/{breed}")
async def browse_curated(breed: str, limit: int = 20):
    """Lista los últimos N crops curados de una raza."""
    curator = get_crop_curator()
    return {"breed": breed, "crops": curator.browse(breed, limit)}


@router.delete("/reject/{breed}/{filename}")
async def reject_curated(breed: str, filename: str):
    """Mueve un crop mal etiquetado a _rejected/."""
    curator = get_crop_curator()
    return curator.reject(breed, filename)
