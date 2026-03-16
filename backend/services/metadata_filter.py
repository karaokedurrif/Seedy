"""Seedy Backend — Metadata Filter: extrae pistas de la query y construye filtros Qdrant.

Fase 2 v14: Reduce ruido de retrieval filtrando chunks irrelevantes
por especie, tipo de documento y fuentes ruidosas.

Funciona SIN llamada a LLM — solo regex y heurísticas.
"""

import re
import logging
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

logger = logging.getLogger(__name__)

# ── Detección de especie ─────────────────────────────────

_SPECIES_PATTERNS: dict[str, list[str]] = {
    "aviar": [
        r"\bgallin[ao]s?\b", r"\bpollos?\b", r"\bcapon(es)?\b", r"\bpulard[ao]s?\b",
        r"\bav[eí]col[ao]s?\b", r"\baves\b", r"\bgallos?\b", r"\bhuevos?\b",
        r"\bponedor[ao]s?\b", r"\bpoultry\b", r"\bchicken\b", r"\bcapon\b",
        r"\bbroiler\b", r"\bincubaci[oó]n\b", r"\bempoll[ao]r?\b",
        r"\bpollitos?\b", r"\bpolluel[ao]s?\b",
        r"\b(bresse|sulmtaler|marans|sussex|orpington|brahma|cornish|plymouth|faverolles)\b",
        r"\b(malines|prat|mos|pita pinta|empordanesa|penedesenca|menorquina)\b",
        r"\b(euskal oiloa|utrerana|castellana negra|sobrarbe)\b",
        r"\b(hy-line|lohmann|isa brown|dekalb|hy line)\b",
    ],
    "porcino": [
        r"\bcerd[oa]s?\b", r"\bporcin[oa]s?\b", r"\bib[eé]ric[oa]s?\b",
        r"\blech[oó]n(es)?\b", r"\bcebad[oa]s?\b", r"\bverrac[oa]s?\b",
        r"\bcerda\b", r"\bpurines?\b", r"\bcebo\b", r"\bengorde\b",
        r"\b(duroc|landrace|pietrain|large white|hampshire|berkshire)\b",
        r"\b(marran[ao]s?|gorrinos?|porks?|swine|pig)\b",
    ],
    "bovino": [
        r"\bvacun[oa]s?\b", r"\bbovin[oa]s?\b", r"\bvac[ao]s?\b",
        r"\btoros?\b", r"\bterneros?\b", r"\bnovillos?\b",
        r"\b(retinta|avile[ñn]a|sayaguesa|cachena|morucha|rubia gallega)\b",
        r"\b(parda de monta[ñn]a|angus|hereford|limousin|charolais)\b",
        r"\b(cattle|cow|bull|beef)\b",
    ],
}

# Fuentes que son ruido puro para preguntas conceptuales
_NOISY_SOURCES = {
    "cda-export (1).csv",   # CSV enorme de sensores CDA
    "cda-export.csv",
}

# Fuentes de baja calidad / idioma incorrecto para preguntas sobre razas
_LOW_QUALITY_FOR_BREEDS = {
    "document_type": ["csv"],  # CSVs no contienen info de razas
}


def detect_species(query: str) -> str | None:
    """
    Detecta la especie predominante en la query.
    Returns: 'aviar', 'porcino', 'bovino', o None si ambiguo.
    """
    query_lower = query.lower()
    scores: dict[str, int] = {}

    for species, patterns in _SPECIES_PATTERNS.items():
        count = 0
        for pattern in patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                count += 1
        if count > 0:
            scores[species] = count

    if not scores:
        return None

    # Si solo hay una especie con hits → esa
    if len(scores) == 1:
        return list(scores.keys())[0]

    # Si hay múltiples, devolver la dominante solo si duplica a la segunda
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if ranked[0][1] >= 2 * ranked[1][1]:
        return ranked[0][0]

    return None  # Ambiguo


def detect_query_type(query: str) -> str:
    """
    Detecta el tipo de consulta para ajustar filtros.
    Returns: 'breed', 'sensor', 'normativa', 'general'
    """
    q = query.lower()

    if re.search(r"\brazas?\b|\bcruce|genétic|capon|breed|variedad|autóctona", q, re.IGNORECASE):
        return "breed"
    if re.search(r"\bsensor|mqtt|iot|esp32|lora|influx|grafana|dato|medir", q, re.IGNORECASE):
        return "sensor"
    if re.search(r"\bnormat|sige|decreto|bienestar|eco\s?gan|purin|legisl", q, re.IGNORECASE):
        return "normativa"

    return "general"


def build_qdrant_filter(
    query: str,
    collection: str,
    category: str | None = None,
) -> Filter | None:
    """
    Construye un filtro Qdrant basado en la query y la colección.

    Estrategia:
    - Excluir fuentes ruidosas (CSVs de sensores) para preguntas de razas
    - No filtrar cuando la query es abierta o sobre sensores/IoT

    Returns: Filter o None (sin filtro).
    """
    species = detect_species(query)
    query_type = detect_query_type(query)

    must_not_conditions = []

    # Para preguntas de razas, excluir CSVs de datos IoT
    if query_type == "breed":
        # Excluir CSVs (no tienen info de razas)
        must_not_conditions.append(
            FieldCondition(key="document_type", match=MatchValue(value="csv"))
        )
        logger.info(f"[MetaFilter] Breed query → excluyendo CSVs")

    # Para preguntas de sensores, excluir PDFs de razas (ayuda menos pero reduce ruido)
    # No filtrar agresivamente aquí — sensor queries suelen ir a colecciones IoT

    # Siempre excluir fuentes conocidas como ruidosas si hay muchos chunks
    if collection == "avicultura" and query_type != "sensor":
        for noisy in _NOISY_SOURCES:
            must_not_conditions.append(
                FieldCondition(key="source_file", match=MatchValue(value=noisy))
            )

    if not must_not_conditions:
        return None

    logger.info(
        f"[MetaFilter] species={species}, type={query_type}, "
        f"collection={collection}, filters={len(must_not_conditions)}"
    )

    return Filter(must_not=must_not_conditions)


def get_species_hint(query: str) -> str | None:
    """Devuelve pista de especie para el evidence builder y critic técnico."""
    return detect_species(query)
