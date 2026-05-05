"""Seedy Backend — Worker: Weekly Report Generator.

Genera informe semanal ejecutivo del gallinero usando qwen2.5:72b o deepseek-r1.

Task muy pesado: 5-10 min, genera informe completo con todas las métricas.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from workers.celery_app import celery_app
from services.llm_router import llm_router

logger = logging.getLogger(__name__)

WEEKLY_REPORT_SYSTEM = """Eres el director técnico de una explotación avícola de precisión.

Genera un INFORME EJECUTIVO SEMANAL completo y profesional en español
que un ganadero pueda usar para tomar decisiones de manejo.

ESTRUCTURA DEL INFORME (máx 2000 palabras):

1. RESUMEN EJECUTIVO (200 palabras)
   - KPIs principales de la semana
   - Alertas críticas (si las hay)
   - 3-5 recomendaciones clave

2. CENSO Y DEMOGRAFÍA
   - Total de aves, distribución por raza y sexo
   - Bajas/altas de la semana
   - Estructura poblacional

3. PRODUCCIÓN
   - Huevos totales (si aplica)
   - Tendencia vs semana anterior
   - Aves ponedoras activas

4. SALUD Y BIENESTAR
   - Anomalías comportamentales detectadas
   - Aves con alertas de salud
   - Condiciones ambientales (temp, humedad, calidad aire)

5. COMPORTAMIENTO SOCIAL
   - Jerarquía del grupo (Top 5 dominantes)
   - Eventos de monta confirmados
   - Interacciones conflictivas

6. ANÁLISIS PREDICTIVO
   - Predicciones de puesta para próxima semana
   - Aves en riesgo de problemas de salud
   - Recomendaciones de intervención

7. MÉTRICAS TÉCNICAS
   - Cobertura de identificación por visión IA
   - Calidad de datos (completeness behavior 7D)
   - Uptime sistemas IoT

USA LENGUAJE CLARO Y PROFESIONAL. INCLUYE DATOS NUMÉRICOS CONCRETOS.
SOPORTA RECOMENDACIONES CON EVIDENCIA DEL ANÁLISIS.
"""


@celery_app.task(name="workers.weekly_report.generate_weekly_report")
def generate_weekly_report(gallinero_id: str, send_email: bool = False):
    """
    Genera informe semanal ejecutivo del gallinero.
    
    Args:
        gallinero_id: ID del gallinero
        send_email: Si True, envía el informe por email (futuro)
    
    Returns:
        dict con el informe generado
    """
    return asyncio.run(_generate_report_async(gallinero_id, send_email))


async def _generate_report_async(gallinero_id: str, send_email: bool):
    """Worker async real."""
    base_url = "http://seedy-backend:8000"
    
    try:
        logger.info(f"[WeeklyReport] Generating report for {gallinero_id}...")
        
        # 1. Recopilar datos de múltiples endpoints
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Censo
            r_census = await client.get(f"{base_url}/behavior/census?gallinero_id={gallinero_id}")
            census = r_census.json() if r_census.status_code == 200 else {}
            
            # Anomalías 7D
            r_anom = await client.get(f"{base_url}/behavior/ml/anomalies/{gallinero_id}?hours=168")
            anomalies = r_anom.json() if r_anom.status_code == 200 else {}
            
            # Jerarquía
            r_hier = await client.get(f"{base_url}/behavior/ml/hierarchy/{gallinero_id}")
            hierarchy = r_hier.json() if r_hier.status_code == 200 else {}
            
            # Montas 7D
            r_mat = await client.get(
                f"{base_url}/behavior/mating/summary?gallinero_id={gallinero_id}&days=7"
            )
            mating = r_mat.json() if r_mat.status_code == 200 else {}
            
            # Predicciones
            r_pred = await client.get(f"{base_url}/behavior/ml/predictions/{gallinero_id}")
            predictions = r_pred.json() if r_pred.status_code == 200 else {}
            
            # Devices IoT
            r_dev = await client.get(f"{base_url}/ovosfera/devices/status")
            devices = r_dev.json() if r_dev.status_code == 200 else {}
            
            # Tracks de visión (cobertura ID)
            r_tracks = await client.get(f"{base_url}/vision/identify/tracks/live?gallinero_id={gallinero_id}")
            tracks = r_tracks.json() if r_tracks.status_code == 200 else []
        
        # 2. Construir contexto consolidado
        context_parts = [
            f"INFORME SEMANAL: {gallinero_id.upper()}",
            f"PERIODO: {(datetime.utcnow() - timedelta(days=7)).date()} a {datetime.utcnow().date()}",
            "",
            "=" * 60,
            "DATOS CENSO",
            "=" * 60,
            f"Total aves: {census.get('total_birds', 0)}",
            f"Distribución por sexo: {census.get('by_sex', {})}",
            f"Distribución por raza: {census.get('by_breed', {})}",
            "",
            "=" * 60,
            "ANOMALÍAS COMPORTAMENTALES (7D)",
            "=" * 60,
            f"Total anomalías detectadas: {len(anomalies.get('anomalies', []))}",
        ]
        
        # Top 10 anomalías
        for a in anomalies.get("anomalies", [])[:10]:
            context_parts.append(
                f"  - {a.get('timestamp', '?')}: Ave {a.get('bird_id', '?')} - {a.get('description', '?')}"
            )
        
        context_parts.extend([
            "",
            "=" * 60,
            "JERARQUÍA DEL GRUPO (PageRank dominancia)",
            "=" * 60,
        ])
        for i, h in enumerate(hierarchy.get("hierarchy", [])[:10], 1):
            context_parts.append(
                f"  {i}. {h.get('bird_id', '?')} (score: {h.get('score', 0):.3f})"
            )
        
        context_parts.extend([
            "",
            "=" * 60,
            "ACTIVIDAD REPRODUCTIVA (7D)",
            "=" * 60,
            f"Total eventos de monta: {mating.get('total_events', 0)}",
            f"Parejas activas: {len(mating.get('pairs', []))}",
        ])
        for p in mating.get("pairs", [])[:10]:
            mounter = p.get("mounter_breed") or p.get("mounter_id", "?")
            mounted = p.get("mounted_breed") or p.get("mounted_id", "?")
            context_parts.append(
                f"  - {mounter} sobre {mounted}: {p.get('count', 0)} eventos"
            )
        
        context_parts.extend([
            "",
            "=" * 60,
            "PREDICCIONES ML",
            "=" * 60,
        ])
        for pred in predictions.get("predictions", [])[:10]:
            bird_id = pred.get("bird_id", "?")
            egg_prob = pred.get("egg_laying_24h", {}).get("probability", 0)
            stress = pred.get("stress_risk", "bajo")
            context_parts.append(
                f"  - {bird_id}: Puesta 24h={egg_prob:.1%}, Estrés={stress}"
            )
        
        context_parts.extend([
            "",
            "=" * 60,
            "CONDICIONES AMBIENTALES (última lectura)",
            "=" * 60,
        ])
        
        # Sensores Zigbee
        for sensor_id, data in devices.get("sensors", {}).items():
            if sensor_id.startswith("gallinero"):
                temp = data.get("last_temperature", "N/A")
                hum = data.get("last_humidity", "N/A")
                context_parts.append(f"  - {sensor_id}: {temp}°C, {hum}% RH")
        
        # Weather Ecowitt
        weather = devices.get("weather", {})
        if weather:
            context_parts.extend([
                f"  - Exterior: {weather.get('outdoor', {}).get('temperature', '?')}°C, "
                f"{weather.get('outdoor', {}).get('humidity', '?')}% RH"
            ])
        
        context_parts.extend([
            "",
            "=" * 60,
            "COBERTURA IDENTIFICACIÓN IA VISION",
            "=" * 60,
            f"Aves con identidad confirmada: {len([t for t in tracks if t.get('identity_locked')])} / {census.get('total_birds', 0)}",
            f"Cobertura: {len([t for t in tracks if t.get('identity_locked')]) / max(census.get('total_birds', 1), 1) * 100:.1f}%",
        ])
        
        context = "\n".join(context_parts)
        
        logger.info(f"[WeeklyReport] Context built ({len(context)} chars), calling LLM...")
        
        # 3. Generar informe con LLM (policy weekly_report)
        result = await llm_router.call_with_policy(
            policy_name="weekly_report",
            system_prompt=WEEKLY_REPORT_SYSTEM,
            user_message=f"Datos consolidados de la semana:\n\n{context}",
            max_tokens=4000,
            temperature=0.6,
        )
        
        report = result.content
        
        logger.info(
            f"[WeeklyReport] ✅ Report generated for {gallinero_id} "
            f"({len(report)} chars, ${result.cost:.4f}, provider: {result.provider})"
        )
        
        # 4. Guardar informe en DB o filesystem (futuro)
        # Por ahora, solo devolver en response
        
        # 5. Enviar email si se solicita (futuro)
        if send_email:
            logger.info("[WeeklyReport] Email sending not implemented yet")
        
        return {
            "status": "success",
            "gallinero_id": gallinero_id,
            "report": report,
            "generated_at": datetime.utcnow().isoformat(),
            "provider": result.provider,
            "cost": result.cost,
            "word_count": len(report.split()),
        }
    
    except Exception as e:
        logger.exception(f"[WeeklyReport] Fatal error: {e}")
        return {"status": "error", "error": str(e)}
