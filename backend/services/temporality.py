"""Seedy Backend — Clasificador de temporalidad de queries.

Clasifica cada query en un nivel de temporalidad:
- STABLE: conocimiento estable (qué es consanguinidad, razas existentes)
- SEMI_DYNAMIC: puede cambiar lentamente (programas de cría, ayudas)
- DYNAMIC: requiere actualidad (normativa nueva, precios, papers recientes)
- BREAKING: urgente (brotes sanitarios, alertas, restricciones)

Esto determina si se fuerza búsqueda web aunque Qdrant tenga resultados.
"""

import hashlib
import time
import logging
from config import get_settings
from services.together_client import get_together_client

logger = logging.getLogger(__name__)

# Cache LRU con TTL — misma query no necesita reclasificarse
_TEMP_CACHE_TTL = 600  # 10 min
_TEMP_CACHE_MAX = 256
_temp_cache: dict[str, tuple[str, float]] = {}

TEMPORALITY_LEVELS = ["STABLE", "SEMI_DYNAMIC", "DYNAMIC", "BREAKING"]

TEMPORALITY_SYSTEM = (
    "Eres un clasificador de temporalidad para consultas agrotech. "
    "Dada una pregunta, responde SOLO con UNO de estos niveles:\n"
    "STABLE, SEMI_DYNAMIC, DYNAMIC, BREAKING\n\n"
    "Criterios:\n"
    "- STABLE: conocimiento que no cambia o cambia muy lento. "
    "  Ejemplos: qué es consanguinidad, qué razas de Bresse existen, qué es un cruce terminal, "
    "  anatomía, fisiología, características de raza, técnicas consolidadas.\n\n"
    "- SEMI_DYNAMIC: puede cambiar cada meses/año. "
    "  Ejemplos: qué programas de cría hay para ibérico, qué ayudas hay para extensivo, "
    "  qué líneas genéticas se usan más, precios orientativos, catálogos de proveedores.\n\n"
    "- DYNAMIC: requiere información reciente o actualizada. "
    "  Ejemplos: últimas ayudas, nueva normativa, precios actuales, qué empresas están "
    "  lanzando sensores, qué papers nuevos hay, novedades en genética, cambios regulatorios, "
    "  ferias recientes, convocatorias.\n\n"
    "- BREAKING: urgencia máxima, eventos que acaban de pasar. "
    "  Ejemplos: brotes sanitarios, restricciones regulatorias, cierres de mercado, "
    "  aranceles urgentes, alertas alimentarias, emergencias.\n\n"
    "Pistas lingüísticas para DYNAMIC/BREAKING:\n"
    "- 'último/a', 'nuevo/a', 'actual', 'reciente', 'hoy', 'esta semana', "
    "'2025', '2026', 'acaban de', 'se ha publicado', 'novedades', 'cambios'\n\n"
    "En caso de duda entre STABLE y SEMI_DYNAMIC, elige STABLE.\n"
    "En caso de duda entre SEMI_DYNAMIC y DYNAMIC, elige SEMI_DYNAMIC.\n\n"
    "Responde SOLO el nivel, sin explicación."
)


async def classify_temporality(query: str) -> str:
    """
    Clasifica la temporalidad de una query usando Together.ai.
    Llamada corta (~5 tokens) para decidir si forzar búsqueda web.
    Fallback: STABLE si falla.
    """
    settings = get_settings()

    if not settings.together_api_key:
        return "STABLE"

    # Comprobar cache
    q_hash = hashlib.md5(query.strip().lower()[:200].encode()).hexdigest()
    if q_hash in _temp_cache:
        val, ts = _temp_cache[q_hash]
        if time.time() - ts < _TEMP_CACHE_TTL:
            logger.info(f"Temporalidad: {val} para '{query[:60]}' (cache)")
            return val
        del _temp_cache[q_hash]

    try:
        client = await get_together_client()
        resp = await client.post(
            f"{settings.together_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.together_api_key}"},
            json={
                "model": settings.together_classifier_model,
                "messages": [
                    {"role": "system", "content": TEMPORALITY_SYSTEM},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 10,
                "temperature": 0,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip().upper()

        for level in TEMPORALITY_LEVELS:
            if level in raw:
                logger.info(f"Temporalidad: {level} para '{query[:60]}'")
                # Guardar en cache
                if len(_temp_cache) >= _TEMP_CACHE_MAX:
                    oldest = sorted(_temp_cache, key=lambda k: _temp_cache[k][1])[:50]
                    for k in oldest:
                        del _temp_cache[k]
                _temp_cache[q_hash] = (level, time.time())
                return level

        logger.warning(f"Temporalidad no reconocida '{raw}', usando STABLE")
        return "STABLE"

    except Exception as e:
        logger.error(f"Error en clasificación de temporalidad: {e}. Fallback STABLE")
        return "STABLE"


def needs_web_augmentation(temporality: str) -> bool:
    """Decide si una query necesita búsqueda web obligatoria por su temporalidad."""
    return temporality in ("DYNAMIC", "BREAKING")


def needs_fresh_layer_priority(temporality: str) -> bool:
    """Decide si los resultados de fresh_web deben tener prioridad en el reranking."""
    return temporality in ("DYNAMIC", "BREAKING", "SEMI_DYNAMIC")
