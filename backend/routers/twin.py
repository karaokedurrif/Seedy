"""Seedy Backend — Router Digital Twin

Endpoints para acceso a métricas agregadas del gemelo digital individual.

OBJ5: Devolver las 7 dimensiones de comportamiento con scores y completeness.
"""

from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta
import logging

router = APIRouter(prefix="/twin", tags=["DigitalTwin"])
logger = logging.getLogger(__name__)


@router.get("/{bird_id}/dimensions")
async def get_dimensions(bird_id: str):
    """Devuelve las 7 dimensiones del ave (snapshot más reciente).
    
    Args:
        bird_id: ai_vision_id del ave
        
    Returns:
        JSON con bird_id, ts, window_hours, dimensions{name: {score, completeness, sample_size}}
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    f = Path(f"data/twin_metrics/{bird_id}/{today}.json")
    
    if not f.exists():
        # Caer al día anterior si hoy aún no se ha agregado
        ayer = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        f = Path(f"data/twin_metrics/{bird_id}/{ayer}.json")
    
    if not f.exists():
        raise HTTPException(
            404,
            detail=f"No hay métricas agregadas para {bird_id}. "
                   "Las métricas se calculan diariamente a las 02:00 UTC."
        )
    
    try:
        data = json.loads(f.read_text())
        logger.info(f"[Twin] Dimensiones devueltas para {bird_id}")
        return data
    except Exception as e:
        logger.error(f"[Twin] Error leyendo métricas de {bird_id}: {e}")
        raise HTTPException(500, detail="Error leyendo métricas del gemelo digital")


@router.get("/{bird_id}/history")
async def get_history(bird_id: str, days: int = 7):
    """Devuelve historial de dimensiones de los últimos N días.
    
    Args:
        bird_id: ai_vision_id del ave
        days: días de historial (default 7)
        
    Returns:
        Lista de snapshots diarios con ts y dimensions
    """
    metrics_dir = Path(f"data/twin_metrics/{bird_id}")
    
    if not metrics_dir.exists():
        raise HTTPException(404, detail=f"No hay métricas para {bird_id}")
    
    # Obtener últimos N días
    history = []
    for i in range(days):
        date = (datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat()
        f = metrics_dir / f"{date}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text())
                history.append(data)
            except Exception as e:
                logger.warning(f"[Twin] Error leyendo {f}: {e}")
                continue
    
    if not history:
        raise HTTPException(
            404,
            detail=f"No hay historial de métricas para {bird_id} en los últimos {days} días"
        )
    
    logger.info(f"[Twin] Historial devuelto para {bird_id}: {len(history)} días")
    return {
        "bird_id": bird_id,
        "days_requested": days,
        "days_available": len(history),
        "history": history,
    }


@router.post("/aggregate/{gallinero_id}")
async def trigger_aggregation(gallinero_id: str):
    """Trigger manual de agregación para todas las aves de un gallinero.
    
    Este endpoint es útil para testing o para forzar una actualización inmediata
    sin esperar al cron diario.
    
    Args:
        gallinero_id: ID del gallinero
        
    Returns:
        Número de aves procesadas
    """
    try:
        from services.behavior_aggregator import run_for_all_birds
        import httpx
        
        # Obtener lista de aves registradas
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "http://localhost:8000/birds/",
                params={"gallinero_id": gallinero_id}
            )
            if resp.status_code != 200:
                raise HTTPException(503, "No se pudo obtener lista de aves")
            
            data = resp.json()
            birds_list = data.get("birds", []) if isinstance(data, dict) else []
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
        
        # Ejecutar agregación
        n = run_for_all_birds(gallinero_id, registered_birds)
        logger.info(f"[Twin] Agregación manual completada para {gallinero_id}: {n} aves")
        
        return {
            "gallinero_id": gallinero_id,
            "birds_processed": n,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"[Twin] Error en agregación manual: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Error ejecutando agregación: {str(e)}")
