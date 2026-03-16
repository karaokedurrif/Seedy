"""Seedy Backend — Router /ingest (trigger manual y monitorización)."""

import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from services.daily_update import run_daily_update, WATCHLIST

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Estado interno del último crawl (en memoria, no persiste entre reinicios)
_last_runs: list[dict] = []
_MAX_HISTORY = 20
_running = False


class IngestTriggerRequest(BaseModel):
    topic: str | None = Field(None, description="Vertical específico (avicultura, porcino, etc.) o None para todos")
    dry_run: bool = Field(False, description="Si True, busca pero no indexa")


class IngestStatusResponse(BaseModel):
    running: bool
    available_topics: list[str]
    last_runs: list[dict]


class IngestTriggerResponse(BaseModel):
    status: str
    message: str


async def _run_and_track(topic: str | None, dry_run: bool):
    """Ejecuta daily_update y registra el resultado."""
    global _running
    _running = True
    t0 = time.time()
    entry = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic or "ALL",
        "dry_run": dry_run,
        "status": "running",
        "new_chunks": 0,
        "elapsed_s": 0,
    }
    _last_runs.insert(0, entry)
    if len(_last_runs) > _MAX_HISTORY:
        _last_runs.pop()

    try:
        count = await run_daily_update(target_topic=topic, dry_run=dry_run)
        entry["status"] = "completed"
        entry["new_chunks"] = count or 0
    except Exception as e:
        entry["status"] = "error"
        entry["error"] = str(e)
        logger.exception(f"Error en ingest trigger: {e}")
    finally:
        entry["elapsed_s"] = round(time.time() - t0, 1)
        _running = False


@router.post("/trigger", response_model=IngestTriggerResponse)
async def trigger_update(req: IngestTriggerRequest, background_tasks: BackgroundTasks):
    """
    Dispara una actualización de conocimientos bajo demanda.
    Se ejecuta en background para no bloquear la API.
    """
    if _running:
        return IngestTriggerResponse(
            status="busy",
            message="Ya hay una actualización en curso. Consulta /ingest/status.",
        )

    background_tasks.add_task(_run_and_track, req.topic, req.dry_run)
    target = req.topic or "todos los verticales"
    mode = "dry-run" if req.dry_run else "indexación completa"
    return IngestTriggerResponse(
        status="started",
        message=f"Actualización iniciada para {target} ({mode})",
    )


@router.get("/status", response_model=IngestStatusResponse)
async def ingest_status():
    """Estado del sistema de ingestión: si está corriendo y últimas ejecuciones."""
    return IngestStatusResponse(
        running=_running,
        available_topics=list(WATCHLIST.keys()),
        last_runs=_last_runs[:10],
    )
