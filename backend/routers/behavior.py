"""Seedy Backend — Router de Análisis Conductual

Endpoints para consultar comportamiento individual y de grupo.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from services.behavior_inference import get_bird_behavior, get_group_behavior_summary
from services.behavior_features import compute_bird_features, compute_group_features, compute_group_statistics
from services.behavior_serializer import to_api_response, to_dashboard_summary
from services.behavior_event_store import get_event_store
from services.mating_detector import query_mating_events, get_mating_summary, scan_mating_retrospective

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/behavior", tags=["behavior"])


@router.get("/bird/{bird_id}")
async def get_bird_behavior_endpoint(
    bird_id: str,
    gallinero_id: str = Query(..., description="ID del gallinero"),
    window: str = Query("24h", description="Ventana temporal: 1h, 6h, 24h"),
):
    """Análisis conductual completo de un ave."""
    inference = get_bird_behavior(bird_id, gallinero_id, window)
    response = to_api_response(inference)
    response["metadata"]["window_analyzed"] = {
        "start": inference.window_start.isoformat(),
        "end": inference.window_end.isoformat(),
    }
    response["metadata"]["events_used"] = _count_events(gallinero_id, inference)
    logger.info(f"[behavior] bird={bird_id} window={window} completeness={inference.data_completeness:.2f}")
    return response


@router.get("/bird/{bird_id}/features")
async def get_bird_features_endpoint(
    bird_id: str,
    gallinero_id: str = Query(..., description="ID del gallinero"),
    window: str = Query("24h", description="Ventana temporal"),
):
    """Features conductuales raw (sin inferencias)."""
    from dataclasses import asdict
    features = compute_bird_features(bird_id, gallinero_id, window)
    result = asdict(features)
    # Serializar datetimes
    result["window_start"] = features.window_start.isoformat()
    result["window_end"] = features.window_end.isoformat()
    return result


@router.get("/group")
async def get_group_behavior_endpoint(
    gallinero_id: str = Query(..., description="ID del gallinero"),
    window: str = Query("24h", description="Ventana temporal"),
):
    """Análisis conductual de todas las aves del gallinero."""
    inferences = get_group_behavior_summary(gallinero_id, window)
    results = []
    for inf in inferences:
        resp = to_api_response(inf)
        resp["metadata"]["events_used"] = _count_events(gallinero_id, inf)
        results.append(resp)
    logger.info(f"[behavior] group gallinero={gallinero_id} window={window} birds={len(results)}")
    return {
        "gallinero_id": gallinero_id,
        "window": window,
        "birds": results,
        "total": len(results),
    }


@router.get("/summary")
async def get_behavior_summary_endpoint(
    gallinero_id: str = Query(..., description="ID del gallinero"),
    window: str = Query("24h", description="Ventana temporal"),
):
    """Resumen compacto para dashboard."""
    inferences = get_group_behavior_summary(gallinero_id, window)
    return to_dashboard_summary(inferences)


@router.get("/stats")
async def get_group_stats_endpoint(
    gallinero_id: str = Query(..., description="ID del gallinero"),
    window: str = Query("24h", description="Ventana temporal"),
):
    """Estadísticas de grupo (percentiles) para calibración."""
    return compute_group_statistics(gallinero_id, window)


@router.get("/store/stats")
async def get_store_stats(
    gallinero_id: str = Query(None, description="Filtrar por gallinero"),
):
    """Estadísticas del event store (ficheros, tamaño, rango)."""
    store = get_event_store()
    return store.get_stats(gallinero_id)


def _count_events(gallinero_id: str, inference) -> int:
    """Cuenta snapshots en el rango de la inferencia."""
    try:
        store = get_event_store()
        snapshots = store.query(gallinero_id, inference.window_start, inference.window_end)
        return len(snapshots)
    except Exception as e:
        logger.warning(f"[behavior] Error counting events for {gallinero_id}: {e}")
        return 0


# ═══════════════════════════════════════════════════════
# Mating endpoints
# ═══════════════════════════════════════════════════════


@router.get("/mating/events")
async def get_mating_events(
    gallinero_id: str = Query(..., description="ID del gallinero"),
    days: int = Query(7, description="Días hacia atrás"),
    bird_id: str = Query(None, description="Filtrar por ave (mounter o mounted)"),
):
    """Lista eventos de monta registrados."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    events = query_mating_events(gallinero_id, start, end, bird_id)
    return {
        "gallinero_id": gallinero_id,
        "period_days": days,
        "total": len(events),
        "events": events,
    }


@router.get("/mating/summary")
async def get_mating_summary_endpoint(
    gallinero_id: str = Query(..., description="ID del gallinero"),
    days: int = Query(7, description="Días hacia atrás"),
):
    """Resumen de montas: qué gallos montan a qué gallinas, cuántas veces."""
    summary = get_mating_summary(gallinero_id, days)
    return summary


@router.get("/mating/bird/{bird_id}")
async def get_bird_mating_history(
    bird_id: str,
    gallinero_id: str = Query(..., description="ID del gallinero"),
    days: int = Query(30, description="Días hacia atrás"),
):
    """Historial de monta de un ave específica (como mounter o mounted)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    events = query_mating_events(gallinero_id, start, end, bird_id)

    as_mounter = [e for e in events if e.get("mounter", {}).get("bird_id") == bird_id]
    as_mounted = [e for e in events if e.get("mounted", {}).get("bird_id") == bird_id]

    return {
        "bird_id": bird_id,
        "gallinero_id": gallinero_id,
        "period_days": days,
        "total_events": len(events),
        "as_mounter": len(as_mounter),
        "as_mounted": len(as_mounted),
        "events": events,
    }


@router.post("/mating/scan")
async def scan_mating_retrospective_endpoint(
    gallinero_id: str = Query(..., description="ID del gallinero"),
    hours: int = Query(24, description="Horas hacia atrás a escanear"),
    persist: bool = Query(True, description="Persistir eventos encontrados"),
):
    """Escanea behavior snapshots buscando montas retrospectivamente.

    Útil cuando el detector real-time perdió estado por reinicios.
    Usa IoU de bboxes (si disponible) o distancia de centros como proxy.
    Solo genera eventos nuevos que no solapen con ya registrados.
    """
    events = scan_mating_retrospective(gallinero_id, hours, persist)
    return {
        "gallinero_id": gallinero_id,
        "hours_scanned": hours,
        "events_found": len(events),
        "persisted": persist,
        "events": events,
    }
