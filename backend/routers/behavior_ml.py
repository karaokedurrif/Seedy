"""
Seedy Backend — API endpoints para ML Adaptativo conductual
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/behavior/ml", tags=["behavior_ml"])


@router.post("/train/{gallinero_id}")
async def train_models(gallinero_id: str, days: int = 14):
    """Entrena modelos ML individuales + flock para un gallinero."""
    from services.behavior_ml import get_ml_engine
    engine = get_ml_engine()
    return await engine.train_gallinero(gallinero_id, days)


@router.get("/anomalies/{gallinero_id}")
async def get_anomalies(gallinero_id: str, hours: int = 24):
    """Anomalías ML detectadas en las últimas N horas."""
    from services.behavior_ml import get_ml_engine
    engine = get_ml_engine()
    anomalies = engine.get_anomalies(gallinero_id, hours)
    return {"gallinero": gallinero_id, "hours": hours, "anomalies": anomalies}


@router.get("/hierarchy/{gallinero_id}")
async def get_hierarchy(gallinero_id: str):
    """Jerarquía de dominancia (PageRank) del rebaño."""
    from services.behavior_ml import get_ml_engine
    engine = get_ml_engine()
    hierarchy = engine.get_hierarchy(gallinero_id)
    return {"gallinero": gallinero_id, "hierarchy": hierarchy}


@router.get("/bird/{bird_id}/profile")
async def get_bird_profile(bird_id: str):
    """Perfil ML individual de un ave."""
    from services.behavior_ml import get_ml_engine
    engine = get_ml_engine()
    return engine.get_bird_profile(bird_id)


@router.get("/predictions/{gallinero_id}")
async def get_predictions(gallinero_id: str):
    """Predicciones del modelo (puesta, estrés, actividad circadiana)."""
    from services.behavior_ml import get_ml_engine
    engine = get_ml_engine()
    return engine.get_predictions(gallinero_id)
