"""Seedy Backend — Router /health."""

import httpx
import logging

from fastapi import APIRouter
from qdrant_client import QdrantClient

from config import get_settings
from models.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Comprueba la salud de los servicios dependientes."""
    settings = get_settings()
    status = HealthResponse(status="ok")

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            status.ollama = resp.status_code == 200
    except Exception:
        status.ollama = False

    # Qdrant
    try:
        qc = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=5)
        qc.get_collections()  # simple check
        status.qdrant = True
        qc.close()
    except Exception:
        status.qdrant = False

    # Together.ai
    if settings.together_api_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.together_base_url}/models",
                    headers={"Authorization": f"Bearer {settings.together_api_key}"},
                )
                status.together = resp.status_code == 200
        except Exception:
            status.together = False

    # Si alguno crítico falla, marcar degraded
    if not (status.ollama or status.together):
        status.status = "degraded"
    if not status.qdrant:
        status.status = "degraded"

    return status


@router.get("/health/auto-learn")
async def auto_learn_status():
    """Estado de los tres ciclos de auto-learning (YOLO, DPO, Vision)."""
    from services.auto_learn import get_auto_learn_status
    return get_auto_learn_status()


@router.get("/health/behavior")
async def behavior_health():
    """Estado del sistema de análisis conductual: event store, baselines, frescura."""
    from datetime import datetime as dt
    result = {"status": "ok", "event_store": {}, "baselines": {}, "warnings": []}
    try:
        from services.behavior_event_store import get_event_store
        store = get_event_store()
        stats = store.get_stats()
        result["event_store"] = stats

        # Check freshness
        for gid, gstats in stats.get("gallineros", {}).items():
            newest = gstats.get("newest", "")
            if newest:
                try:
                    days_stale = (dt.now().date() - dt.strptime(newest, "%Y-%m-%d").date()).days
                    if days_stale > 1:
                        result["warnings"].append(f"{gid}: sin snapshots desde hace {days_stale} días")
                except ValueError:
                    pass
            if gstats.get("files", 0) == 0:
                result["warnings"].append(f"{gid}: sin ficheros de eventos")
    except Exception as e:
        result["event_store"] = {"error": str(e)}

    try:
        from services.behavior_baseline import get_baseline
        baseline = get_baseline()
        baseline_path = baseline._base
        if baseline_path.exists():
            files = list(baseline_path.glob("*.json"))
            result["baselines"] = {
                "total_birds": len(files),
                "path": str(baseline_path),
            }
    except Exception as e:
        result["baselines"] = {"error": str(e)}

    if result["warnings"]:
        result["status"] = "degraded"
    return result


@router.get("/health/watchdog")
async def watchdog_status():
    """Ejecuta todos los checks del watchdog bajo demanda."""
    from datetime import datetime as _dt, timezone as _tz
    from services.watchdog import run_checks, NIGHT_START, NIGHT_END

    now = _dt.now(_tz.utc)
    local_hour = (now.hour + 2) % 24  # UTC+2 aprox
    is_night = NIGHT_START <= local_hour < NIGHT_END

    results = await run_checks(skip_cameras=is_night)
    failed = [k for k, v in results.items() if not v["ok"] and not v.get("skipped")]

    return {
        "status": "ok" if not failed else "degraded",
        "timestamp": now.isoformat(),
        "is_night_mode": is_night,
        "checks": results,
        "failed": failed,
    }


@router.get("/health/cpu")
async def cpu_watchdog_status():
    """Estado del CPU watchdog: uso de CPU, throttle level, frame skip."""
    try:
        from services.cpu_watchdog import get_cpu_watchdog
        wd = get_cpu_watchdog()
        return {"status": "ok", **wd.get_status()}
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}
