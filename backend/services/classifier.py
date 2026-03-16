"""Seedy Backend — Clasificador de queries vía Together.ai (con cache LRU).

Soporta clasificación single-label (legacy) y multi-label (v15+).
Multi-label devuelve lista de categorías con pesos para buscar en
múltiples colecciones Qdrant simultáneamente.
"""

import hashlib
import time
import httpx
import logging

from config import get_settings
from models.prompts import CLASSIFIER_SYSTEM, CLASSIFIER_MULTI_SYSTEM, CATEGORIES

logger = logging.getLogger(__name__)

# Cache LRU con TTL — evita llamadas duplicadas a Together.ai
_CACHE_TTL = 600  # 10 minutos
_CACHE_MAX = 256
_classify_cache: dict[str, tuple[str, float]] = {}  # hash → (category, timestamp)
_classify_multi_cache: dict[str, tuple[list[tuple[str, float]], float]] = {}


def _query_hash(query: str, prev_cat: str | None) -> str:
    """Hash normalizado de query + context para cache key."""
    normalized = query.strip().lower()[:200]
    key = f"{normalized}|{prev_cat or ''}"
    return hashlib.md5(key.encode()).hexdigest()


def _cache_get(h: str) -> str | None:
    """Lee del cache si no ha expirado."""
    if h in _classify_cache:
        val, ts = _classify_cache[h]
        if time.time() - ts < _CACHE_TTL:
            return val
        del _classify_cache[h]
    return None


def _cache_get_multi(h: str) -> list[tuple[str, float]] | None:
    """Lee del cache multi-label si no ha expirado."""
    if h in _classify_multi_cache:
        val, ts = _classify_multi_cache[h]
        if time.time() - ts < _CACHE_TTL:
            return val
        del _classify_multi_cache[h]
    return None


def _cache_put(h: str, val: str):
    """Escribe en cache, purgando si se excede tamaño."""
    if len(_classify_cache) >= _CACHE_MAX:
        sorted_keys = sorted(_classify_cache, key=lambda k: _classify_cache[k][1])
        for k in sorted_keys[:50]:
            del _classify_cache[k]
    _classify_cache[h] = (val, time.time())


def _cache_put_multi(h: str, val: list[tuple[str, float]]):
    """Escribe en cache multi-label."""
    if len(_classify_multi_cache) >= _CACHE_MAX:
        sorted_keys = sorted(_classify_multi_cache, key=lambda k: _classify_multi_cache[k][1])
        for k in sorted_keys[:50]:
            del _classify_multi_cache[k]
    _classify_multi_cache[h] = (val, time.time())


def _parse_multi_response(raw: str) -> list[tuple[str, float]]:
    """
    Parsea respuesta multi-label del LLM.
    Formato esperado: "AVICULTURA:0.85,GENETICS:0.60,NUTRITION:0.30"
    Returns lista de (categoría, peso) ordenada por peso desc, filtrada por umbral 0.3.
    """
    results: list[tuple[str, float]] = []
    for part in raw.replace(" ", "").split(","):
        if ":" not in part:
            # Fallback: solo categoría sin peso
            cat = part.strip().upper()
            if cat in CATEGORIES:
                results.append((cat, 1.0))
            continue
        cat_str, score_str = part.split(":", 1)
        cat_str = cat_str.strip().upper()
        try:
            score = float(score_str.strip())
        except ValueError:
            score = 0.5
        if cat_str in CATEGORIES and score >= 0.3:
            results.append((cat_str, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:3]  # Máximo 3 categorías


async def classify_query(query: str, prev_category: str | None = None) -> str:
    """
    Clasifica la query del usuario en una categoría usando Together.ai.
    Llamada corta (~10 tokens) para decidir qué colecciones RAG consultar.

    Si prev_category se proporciona (conversación multi-turno), se añade
    como hint al clasificador para mantener coherencia temática.
    Fallback: GENERAL si falla la clasificación.
    """
    settings = get_settings()

    if not settings.together_api_key:
        logger.warning("TOGETHER_API_KEY no configurada, usando categoría GENERAL")
        return "GENERAL"

    # Comprobar cache
    h = _query_hash(query, prev_category)
    cached = _cache_get(h)
    if cached:
        logger.info(f"Query clasificada como: {cached} (cache)")
        return cached

    # Añadir hint de categoría previa para coherencia conversacional
    classifier_prompt = CLASSIFIER_SYSTEM
    if prev_category and prev_category != "GENERAL":
        classifier_prompt += (
            f"\n\nIMPORTANTE: La conversación actual está en el dominio {prev_category}. "
            f"Si la pregunta sigue siendo del mismo tema (follow-up, profundización, "
            f"cruces dentro del mismo dominio), mantén {prev_category}. "
            f"Solo cambia si la pregunta claramente pertenece a otro dominio."
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_classifier_model,
                    "messages": [
                        {"role": "system", "content": classifier_prompt},
                        {"role": "user", "content": query},
                    ],
                    "max_tokens": 10,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip().upper()

            for cat in CATEGORIES:
                if cat in raw:
                    logger.info(f"Query clasificada como: {cat}")
                    _cache_put(h, cat)
                    return cat

            logger.warning(f"Categoría no reconocida '{raw}', usando GENERAL")
            return "GENERAL"

    except Exception as e:
        logger.error(f"Error en clasificación: {e}. Fallback a GENERAL")
        return "GENERAL"


async def classify_query_multi(
    query: str, prev_category: str | None = None
) -> list[tuple[str, float]]:
    """
    Clasificación multi-label: devuelve hasta 3 categorías con pesos.
    
    Ejemplo: "nutrición de capones en extensivo"
     → [("AVICULTURA", 0.85), ("NUTRITION", 0.70)]
    
    El chat router usa los pesos para combinar colecciones de múltiples
    categorías y mejorar el recall del RAG.
    Fallback: devuelve resultado de classify_query single-label.
    """
    settings = get_settings()

    if not settings.together_api_key:
        return [("GENERAL", 1.0)]

    h = _query_hash(query, prev_category)
    cached = _cache_get_multi(h)
    if cached:
        logger.info(f"Query multi-clasificada como: {cached} (cache)")
        return cached

    classifier_prompt = CLASSIFIER_MULTI_SYSTEM
    if prev_category and prev_category != "GENERAL":
        classifier_prompt += (
            f"\n\nCONTEXTO: La conversación viene del dominio {prev_category}. "
            f"Inclúyelo con peso alto si la pregunta sigue en ese tema."
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_classifier_model,
                    "messages": [
                        {"role": "system", "content": classifier_prompt},
                        {"role": "user", "content": query},
                    ],
                    "max_tokens": 40,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            results = _parse_multi_response(raw)

            if results:
                logger.info(f"Query multi-clasificada: {results}")
                _cache_put_multi(h, results)
                return results

    except Exception as e:
        logger.error(f"Error en clasificación multi-label: {e}")

    # Fallback: single-label
    single = await classify_query(query, prev_category)
    return [(single, 1.0)]
