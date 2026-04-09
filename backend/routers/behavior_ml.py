"""Seedy Backend — Router: ML conductual adaptativo."""

import logging
from fastapi import APIRouter

from services.behavior_ml import get_behavior_ml_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/behavior/ml", tags=["behavior_ml"])


@router.post("/train/{gallinero_id}")
async def train_ml(gallinero_id: str, days: int = 14):
    """Entrena modelos ML con los últimos N días de datos conductuales."""
    engine = get_behavior_ml_engine()
    return await engine.train_all(gallinero_id, days)


@router.get("/anomalies/{gallinero_id}")
async def get_anomalies(gallinero_id: str, hours: int = 24):
    """Anomalías detectadas por ML en las últimas N horas."""
    engine = get_behavior_ml_engine()
    anomalies = engine.get_recent_anomalies(gallinero_id, hours)
    return {"gallinero_id": gallinero_id, "hours": hours, "anomalies": anomalies}


@router.get("/hierarchy/{gallinero_id}")
async def get_hierarchy(gallinero_id: str):
    """Ranking de dominancia por PageRank."""
    engine = get_behavior_ml_engine()
    flock = engine._flock_models.get(gallinero_id)
    if not flock:
        return {"gallinero_id": gallinero_id, "hierarchy": [], "status": "no_model"}
    return {"gallinero_id": gallinero_id, "hierarchy": flock.get_hierarchy()}


@router.get("/bird/{bird_id}/profile")
async def get_bird_profile(bird_id: str):
    """Perfil ML de un ave: rutina, baseline, anomalías recientes."""
    engine = get_behavior_ml_engine()
    model = engine._individual_models.get(bird_id)
    if not model:
        return {"bird_id": bird_id, "status": "no_model"}
    return model.get_profile_summary()


@router.get("/predictions/{gallinero_id}")
async def get_predictions(gallinero_id: str):
    """Predicciones activas: puesta probable, estrés inminente, etc."""
    engine = get_behavior_ml_engine()
    return {"gallinero_id": gallinero_id, "predictions": engine.get_active_predictions(gallinero_id)}
