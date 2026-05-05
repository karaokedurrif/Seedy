"""Seedy Backend — Worker: Mating Confirmer.

Analiza eventos de monta detectados automáticamente y los confirma/descarta
usando qwen2.5:72b con análisis de secuencias de frames.

Task medio: ~30s por evento de monta.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from workers.celery_app import celery_app
from services.llm_router import llm_router

logger = logging.getLogger(__name__)

MATING_CONFIRM_SYSTEM = """Eres un experto en comportamiento reproductivo aviar.

Analiza la secuencia de detección de monta y determina si es un evento REAL o un FALSO POSITIVO.

CRITERIOS PARA MONTA REAL:
1. Duración sostenida: ≥3 frames consecutivos con IoU >0.35
2. Posición anatómica correcta: ave superior centrada sobre inferior
3. Movimiento característico: postura estable, no paso casual
4. Contexto temporal: duración 3-15 segundos típica

FALSOS POSITIVOS COMUNES:
- Ave pasando por encima (duración <3 frames)
- Aves comiendo juntas (IoU alto pero horizontal)
- Overlap casual sin posición de monta
- Detección duplicada del mismo evento

RESPONDE JSON:
{
  "verdict": "CONFIRMED" | "REJECTED" | "UNCERTAIN",
  "confidence": 0.0-1.0,
  "reason": "explicación breve",
  "recommended_action": "keep" | "discard" | "review_manual"
}
"""


@celery_app.task(name="workers.mating_confirmer.confirm_mating_batch")
def confirm_mating_batch(gallinero_id: str, hours: int = 6):
    """
    Revisa y confirma eventos de monta de las últimas N horas.
    
    Args:
        gallinero_id: ID del gallinero
        hours: Ventana temporal a revisar (default: 6h)
    
    Returns:
        dict con summary de confirmaciones
    """
    return asyncio.run(_confirm_batch_async(gallinero_id, hours))


async def _confirm_batch_async(gallinero_id: str, hours: int):
    """Worker async real."""
    base_url = "http://seedy-backend:8000"
    
    try:
        # 1. Obtener eventos de monta pendientes de confirmar
        async with httpx.AsyncClient(timeout=30.0) as client:
            since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            r = await client.get(
                f"{base_url}/behavior/mating/events?gallinero_id={gallinero_id}"
                f"&since={since}&status=pending"
            )
            r.raise_for_status()
            events = r.json().get("events", [])
        
        if not events:
            logger.info(f"[MatingConfirmer] No pending events in {gallinero_id} (last {hours}h)")
            return {"status": "completed", "total": 0, "confirmed": 0, "rejected": 0}
        
        logger.info(f"[MatingConfirmer] Processing {len(events)} pending mating events")
        
        confirmed = 0
        rejected = 0
        uncertain = 0
        
        for event in events:
            event_id = event.get("event_id")
            mounter_id = event.get("mounter_id")
            mounted_id = event.get("mounted_id")
            
            try:
                # 2. Construir contexto del evento
                context_parts = [
                    f"EVENTO: {event_id}",
                    f"MONTOR: {mounter_id} (track {event.get('mounter_track_id')})",
                    f"MONTADO: {mounted_id} (track {event.get('mounted_track_id')})",
                    f"TIMESTAMP: {event.get('timestamp')}",
                    f"DURACIÓN: {event.get('duration_seconds', 0):.1f}s",
                    f"FRAMES: {event.get('frame_count', 0)}",
                    f"IoU MEDIO: {event.get('avg_iou', 0):.3f}",
                    f"IoU MÁXIMO: {event.get('max_iou', 0):.3f}",
                    f"CONFIANZA INICIAL: {event.get('confidence', 0):.3f}",
                    "",
                    "=== CONTEXTO ===",
                    f"Cámara: {event.get('camera_id', '?')}",
                    f"Gallinero: {gallinero_id}",
                ]
                
                # Agregar metadata adicional si existe
                if event.get("mounter_breed"):
                    context_parts.append(f"Raza montor: {event['mounter_breed']}")
                if event.get("mounted_breed"):
                    context_parts.append(f"Raza montado: {event['mounted_breed']}")
                
                # Historia de montas previas (si disponible)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r_hist = await client.get(
                        f"{base_url}/behavior/mating/summary?gallinero_id={gallinero_id}&days=7"
                    )
                    if r_hist.status_code == 200:
                        pairs = r_hist.json().get("pairs", [])
                        pair_history = next(
                            (p for p in pairs 
                             if p.get("mounter_id") == mounter_id and p.get("mounted_id") == mounted_id),
                            None
                        )
                        if pair_history:
                            context_parts.append(
                                f"Historial pareja: {pair_history.get('count', 0)} montas previas en 7d"
                            )
                
                context = "\n".join(context_parts)
                
                # 3. Confirmar con LLM
                logger.info(f"[MatingConfirmer] Analyzing event {event_id}...")
                result = await llm_router.call_with_policy(
                    policy_name="mating_confirmation",
                    system_prompt=MATING_CONFIRM_SYSTEM,
                    user_message=f"Datos del evento de monta:\n\n{context}",
                    max_tokens=300,
                    temperature=0.1,
                )
                
                # 4. Parsear veredicto
                import json
                try:
                    verdict_data = json.loads(result.content)
                except json.JSONDecodeError:
                    # Fallback: extraer verdict del texto
                    if "CONFIRMED" in result.content:
                        verdict_data = {"verdict": "CONFIRMED", "confidence": 0.7}
                    elif "REJECTED" in result.content:
                        verdict_data = {"verdict": "REJECTED", "confidence": 0.7}
                    else:
                        verdict_data = {"verdict": "UNCERTAIN", "confidence": 0.5}
                
                verdict = verdict_data.get("verdict", "UNCERTAIN")
                confidence = verdict_data.get("confidence", 0.0)
                reason = verdict_data.get("reason", "")
                
                # 5. Actualizar evento en DB (via API)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    update_data = {
                        "status": verdict.lower(),
                        "llm_confidence": confidence,
                        "llm_reason": reason,
                        "reviewed_at": datetime.utcnow().isoformat(),
                        "reviewed_by": "llm_worker",
                    }
                    await client.patch(
                        f"{base_url}/behavior/mating/events/{event_id}",
                        json=update_data,
                    )
                
                # 6. Contadores
                if verdict == "CONFIRMED":
                    confirmed += 1
                    logger.info(f"[MatingConfirmer] ✅ Event {event_id} CONFIRMED (conf={confidence:.2f})")
                elif verdict == "REJECTED":
                    rejected += 1
                    logger.info(f"[MatingConfirmer] ❌ Event {event_id} REJECTED ({reason})")
                else:
                    uncertain += 1
                    logger.info(f"[MatingConfirmer] ⚠️ Event {event_id} UNCERTAIN (manual review)")
            
            except Exception as e:
                logger.error(f"[MatingConfirmer] Error processing event {event_id}: {e}")
                uncertain += 1
        
        return {
            "status": "completed",
            "gallinero_id": gallinero_id,
            "hours_processed": hours,
            "total": len(events),
            "confirmed": confirmed,
            "rejected": rejected,
            "uncertain": uncertain,
            "processed_at": datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        logger.exception(f"[MatingConfirmer] Fatal error: {e}")
        return {"status": "error", "error": str(e)}
