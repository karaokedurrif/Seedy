"""Seedy Backend — Worker: Behavior Analyzer 7D.

Genera análisis profundo de comportamiento individual de cada ave
usando datos de los últimos 7 días con qwen2.5:72b local.

Task pesado: 2-5 min/ave, batch completo puede tardar 1-2 horas.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from workers.celery_app import celery_app
from services.llm_router import llm_router

logger = logging.getLogger(__name__)

# System prompt para análisis de comportamiento 7D
BEHAVIOR_7D_SYSTEM = """Eres un experto etólogo especializado en comportamiento aviar.

Analiza los datos de comportamiento de un ave individual durante los últimos 7 días
y genera un informe ejecutivo en español.

ESTRUCTURA DEL INFORME (máx 800 palabras):

1. RESUMEN EJECUTIVO (3-4 líneas)
   - Estado general del ave
   - Cambios significativos detectados

2. PATRONES DE ACTIVIDAD
   - Rutina espacial diaria (zonas preferidas × hora)
   - Patrones de alimentación (frecuencia, duración, hora pico)
   - Ciclo circadiano (actividad diurna/nocturna)

3. COMPORTAMIENTOS SOCIALES
   - Interacciones con otras aves (dominancia, sumisión, neutrales)
   - Posición en la jerarquía del grupo
   - Eventos de monta (como montor o montado)

4. ANOMALÍAS Y ALERTAS
   - Comportamientos fuera de la norma
   - Posibles indicadores de estrés, enfermedad o problemas
   - Anomalías detectadas por ML (z-score > 2.5)

5. PREDICCIONES
   - Puesta estimada (si aplica)
   - Riesgos de salud próximos
   - Recomendaciones de manejo

USA LENGUAJE TÉCNICO PERO CLARO. SOPORTA CONCLUSIONES CON DATOS CONCRETOS.
"""


@celery_app.task(name="workers.behavior_analyzer.analyze_bird_behavior_7d")
def analyze_bird_behavior_7d(gallinero_id: str, bird_id: str | None = None):
    """
    Genera análisis de comportamiento 7D para un ave o todas las aves del gallinero.
    
    Args:
        gallinero_id: ID del gallinero
        bird_id: ID del ave específica (None = todas las aves)
    
    Returns:
        dict con {bird_id: analysis_text, ...} o mensaje de error
    """
    return asyncio.run(_analyze_behavior_async(gallinero_id, bird_id))


async def _analyze_behavior_async(gallinero_id: str, bird_id: str | None):
    """Worker async real."""
    base_url = "http://seedy-backend:8000"  # Docker service name
    
    try:
        # 1. Obtener lista de aves si no se especificó bird_id
        async with httpx.AsyncClient(timeout=30.0) as client:
            if bird_id:
                birds = [{"bird_id": bird_id}]
            else:
                # Obtener censo del gallinero
                r = await client.get(f"{base_url}/behavior/census?gallinero_id={gallinero_id}")
                r.raise_for_status()
                census = r.json()
                birds = [{"bird_id": b["bird_id"]} for b in census.get("birds", [])]
        
        if not birds:
            logger.warning(f"[BehaviorAnalyzer] No birds found in {gallinero_id}")
            return {"error": "No birds found"}
        
        logger.info(f"[BehaviorAnalyzer] Analyzing {len(birds)} birds from {gallinero_id}")
        
        results = {}
        
        for bird in birds:
            bid = bird["bird_id"]
            logger.info(f"[BehaviorAnalyzer] Processing {bid}...")
            
            try:
                # 2. Obtener datos de comportamiento 7D
                async with httpx.AsyncClient(timeout=60.0) as client:
                    # Perfil ML
                    r_profile = await client.get(f"{base_url}/behavior/ml/bird/{bid}/profile")
                    profile = r_profile.json() if r_profile.status_code == 200 else {}
                    
                    # Anomalías 7D
                    r_anom = await client.get(
                        f"{base_url}/behavior/ml/anomalies/{gallinero_id}?bird_id={bid}&hours=168"
                    )
                    anomalies = r_anom.json().get("anomalies", []) if r_anom.status_code == 200 else []
                    
                    # Montas 7D
                    r_mat = await client.get(
                        f"{base_url}/behavior/mating/summary?gallinero_id={gallinero_id}&days=7"
                    )
                    mating_data = r_mat.json() if r_mat.status_code == 200 else {}
                    
                    # Predicciones
                    r_pred = await client.get(f"{base_url}/behavior/ml/predictions/{gallinero_id}")
                    predictions = r_pred.json() if r_pred.status_code == 200 else {}
                
                # 3. Construir contexto para el LLM
                context_parts = [
                    f"AVE: {bid}",
                    f"GALLINERO: {gallinero_id}",
                    f"PERIODO: Últimos 7 días",
                    "",
                    "=== PERFIL ML ===",
                    f"Modelo entrenado: {profile.get('model_trained', False)}",
                    f"Datos de entrenamiento: {profile.get('training_samples', 0)} eventos",
                ]
                
                if profile.get("routine"):
                    context_parts.append(f"Rutina espacial: {profile['routine']}")
                if profile.get("feeding_pattern"):
                    context_parts.append(f"Patrón alimentación: {profile['feeding_pattern']}")
                
                context_parts.extend([
                    "",
                    f"=== ANOMALÍAS (7D) ===",
                    f"Total anomalías detectadas: {len(anomalies)}",
                ])
                for a in anomalies[:10]:  # Top 10 anomalías
                    context_parts.append(f"  - {a.get('timestamp', '?')}: {a.get('description', '?')}")
                
                # Montas
                bird_matings = [
                    p for p in mating_data.get("pairs", [])
                    if p.get("mounter_id") == bid or p.get("mounted_id") == bid
                ]
                context_parts.extend([
                    "",
                    f"=== MONTAS (7D) ===",
                    f"Total eventos: {len(bird_matings)}",
                ])
                for m in bird_matings[:5]:
                    context_parts.append(
                        f"  - {m.get('mounter_id')} sobre {m.get('mounted_id')}: {m.get('count')} veces"
                    )
                
                # Predicciones
                bird_pred = next(
                    (p for p in predictions.get("predictions", []) if p.get("bird_id") == bid),
                    None
                )
                if bird_pred:
                    context_parts.extend([
                        "",
                        "=== PREDICCIONES ===",
                        f"Puesta próxima 24h: {bird_pred.get('egg_laying_24h', {}).get('probability', 0):.2%}",
                        f"Estrés elevado: {bird_pred.get('stress_risk', 'bajo')}",
                    ])
                
                context = "\n".join(context_parts)
                
                # 4. Generar análisis con qwen2.5:72b
                logger.info(f"[BehaviorAnalyzer] Generating analysis for {bid} with Qwen 72B...")
                result = await llm_router.call_with_policy(
                    policy_name="behavior_7d_analysis",
                    system_prompt=BEHAVIOR_7D_SYSTEM,
                    user_message=f"Datos de comportamiento:\n\n{context}",
                    max_tokens=2000,
                    temperature=0.5,
                )
                
                analysis = result.content
                results[bid] = {
                    "status": "success",
                    "analysis": analysis,
                    "provider": result.provider,
                    "cost": result.cost,
                    "generated_at": datetime.utcnow().isoformat(),
                }
                
                logger.info(
                    f"[BehaviorAnalyzer] ✅ {bid} analysis completed "
                    f"({len(analysis)} chars, ${result.cost:.4f}, provider: {result.provider})"
                )
            
            except Exception as e:
                logger.error(f"[BehaviorAnalyzer] ❌ Error analyzing {bid}: {e}")
                results[bid] = {"status": "error", "error": str(e)}
        
        return {
            "status": "completed",
            "gallinero_id": gallinero_id,
            "total_birds": len(birds),
            "successful": len([r for r in results.values() if r.get("status") == "success"]),
            "results": results,
        }
    
    except Exception as e:
        logger.exception(f"[BehaviorAnalyzer] Fatal error: {e}")
        return {"status": "error", "error": str(e)}
