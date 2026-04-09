"""
Seedy Backend — Router /genetics/merit

Índice de Mérito Genético (IM) para selección de aves heritage.
Score compuesto 0.00–1.00 que combina peso, conformación, conversión,
viabilidad y docilidad. Umbrales: ≥0.85 reproductor, 0.60–0.84 producción,
<0.60 descarte.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from models.merit_index import MeritInput, MeritResult, MeritWeights, MeritRankingResponse
from services.merit_index import calculate_merit_index, get_history, get_target_weight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genetics/merit", tags=["genetics", "merit-index"])


# ── Request wrappers para multi-body ─────────────────

class BatchRequest(BaseModel):
    inputs: List[MeritInput]
    weights: Optional[MeritWeights] = None


class RankingRequest(BaseModel):
    inputs: List[MeritInput]
    weights: Optional[MeritWeights] = None


@router.post("/calculate", response_model=MeritResult)
async def calculate_im(inp: MeritInput):
    """Calcula el Índice de Mérito para un ave individual."""
    return calculate_merit_index(inp)


@router.post("/batch", response_model=List[MeritResult])
async def calculate_batch(body: BatchRequest):
    """Calcula el IM para un lote de aves, ordenadas por score descendente."""
    if not body.inputs:
        raise HTTPException(400, "La lista de aves no puede estar vacía")
    results = [calculate_merit_index(inp, body.weights) for inp in body.inputs]
    results.sort(key=lambda r: r.im_score, reverse=True)
    return results


@router.post("/ranking")
async def get_ranking(body: RankingRequest):
    """
    Genera ranking completo con resumen estadístico.
    Devuelve reproductores, producción, descarte y estadísticas.
    """
    if not body.inputs:
        raise HTTPException(400, "La lista de aves no puede estar vacía")

    results = [calculate_merit_index(inp, body.weights) for inp in body.inputs]
    results.sort(key=lambda r: r.im_score, reverse=True)

    reproductores = [r for r in results if r.category == "reproductor"]
    produccion = [r for r in results if r.category == "produccion"]
    descarte = [r for r in results if r.category == "descarte"]

    scores = [r.im_score for r in results]

    return {
        "total_aves": len(results),
        "reproductores": {
            "count": len(reproductores),
            "aves": [r.model_dump() for r in reproductores],
        },
        "produccion": {
            "count": len(produccion),
            "aves": [r.model_dump() for r in produccion],
        },
        "descarte": {
            "count": len(descarte),
            "aves": [r.model_dump() for r in descarte],
        },
        "stats": {
            "im_medio": round(sum(scores) / len(scores), 3),
            "im_max": max(scores),
            "im_min": min(scores),
            "pct_reproductores": round(len(reproductores) / len(results) * 100, 1),
        },
        "weights_used": (body.weights or MeritWeights()).model_dump(),
    }


@router.get("/history/{bird_id}")
async def get_bird_im_history(bird_id: str):
    """Historial temporal del IM de un ave (evolución semana a semana)."""
    records = get_history(bird_id)
    return {
        "bird_id": bird_id,
        "records": records,
        "total": len(records),
    }


@router.get("/gompertz-target")
async def gompertz_target(
    age_weeks: int = Query(..., ge=0, description="Edad en semanas"),
    gallinero: Optional[str] = Query(None, description="Gallinero (G1-G5)"),
    breed: Optional[str] = Query(None, description="Raza (sussex, bresse, etc.)"),
):
    """Devuelve el peso objetivo Gompertz para una edad/gallinero/raza."""
    target = get_target_weight(age_weeks, gallinero, breed)
    return {
        "age_weeks": age_weeks,
        "gallinero": gallinero,
        "breed": breed,
        "target_weight_grams": round(target, 1),
    }
