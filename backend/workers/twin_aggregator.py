"""Seedy Workers — Twin Metrics Aggregator.

Task diario para calcular dimensiones de comportamiento y persistir métricas
de gemelos digitales.
"""

import logging
from celery import Task

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class AggregatorTask(Task):
    """Task class con retry automático y logging."""
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True


@celery_app.task(base=AggregatorTask, bind=True)
def aggregate_twin_metrics_all(self, gallinero_id: str = "gallinero_palacio") -> dict:
    """Agrega métricas de twin para todos los birds del gallinero.
    
    Ejecutado diariamente a las 02:00 por Celery Beat.
    
    Args:
        gallinero_id: ID del gallinero a procesar.
    
    Returns:
        {"birds_processed": N, "errors": M}
    """
    from services.behavior_aggregator import run_for_all_birds
    
    logger.info(f"[Celery] Iniciando agregación diaria twin metrics para {gallinero_id}")
    
    try:
        # Run aggregation
        results = run_for_all_birds(gallinero_id)
        birds_processed = results.get("birds_processed", 0)
        errors = results.get("errors", 0)
        
        logger.info(
            f"[Celery] Agregación twin completada: "
            f"{birds_processed} aves, {errors} errores en {gallinero_id}"
        )
        
        return {
            "status": "ok",
            "birds_processed": birds_processed,
            "errors": errors,
            "gallinero_id": gallinero_id,
        }
    
    except Exception as e:
        logger.error(f"[Celery] Error en agregación twin: {e}", exc_info=True)
        raise
