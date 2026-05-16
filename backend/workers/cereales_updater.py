"""Seedy Workers — Cereales Updater.

Task diario para ingestar precios de cereales desde Mercolleida, Lonja Segovia, MAPA.
"""

import logging
from celery import Task

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class CerealesTask(Task):
    """Task class con retry automático y logging."""
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True


@celery_app.task(base=CerealesTask, bind=True)
def ingest_cereales_daily(self) -> dict:
    """Ingesta precios de cereales desde fuentes externas.
    
    Ejecutado diariamente a las 06:00 por Celery Beat.
    
    Returns:
        {"mercolleida": N, "lonja_segovia": M, "mapa": K}
    """
    import asyncio
    from ingestion.cereales_ingester import ingest_all_cereales
    
    logger.info("[Celery] Iniciando ingesta diaria de precios de cereales")
    
    try:
        # Run async ingestion (Celery worker usa asyncio.run)
        results = asyncio.run(ingest_all_cereales())
        total = sum(results.values())
        
        logger.info(
            f"[Celery] Ingesta cereales completada: {total} registros "
            f"(Mercolleida: {results.get('mercolleida', 0)}, "
            f"Lonja Segovia: {results.get('lonja_segovia', 0)}, "
            f"MAPA: {results.get('mapa', 0)})"
        )
        
        return {
            "status": "ok",
            "total": total,
            **results,
        }
    
    except Exception as e:
        logger.error(f"[Celery] Error en ingesta cereales: {e}", exc_info=True)
        raise
