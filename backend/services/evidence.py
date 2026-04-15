"""Seedy Backend — Evidence Builder (Fase 2 v14).

Transforma chunks RAG brutos en evidencia estructurada antes de pasarlos al LLM.
En lugar de enviar 8 chunks crudos (con ruido, duplicados, contexto irrelevante),
extrae y agrupa los hechos relevantes.

Estrategia:
1. Deduplicar chunks con alta similitud textual
2. Extraer hechos clave con Together.ai (Qwen 7B, rápido)
3. Agrupar por tema/fuente
4. Devolver evidencia comprimida y citada

Resultado: el LLM recibe 1/3 del contexto pero con 3x más señal.
"""

import logging
import hashlib
import httpx
from difflib import SequenceMatcher

from config import get_settings

logger = logging.getLogger(__name__)

# Umbral de similitud para considerar chunks duplicados
_DEDUP_THRESHOLD = 0.75

# Máximo de hechos extraídos
_MAX_FACTS = 20

# System prompt para el extractor de hechos
_EXTRACTOR_SYSTEM = (
    "Eres un extractor de hechos para un asistente de ganadería y agricultura. "
    "Tu trabajo: dado un CONTEXTO recuperado y una PREGUNTA, extraer TODOS los hechos "
    "relevantes para responder la pregunta.\n\n"
    "REGLAS:\n"
    "- Extrae TODOS los hechos concretos: nombres de razas, datos, cifras, características, "
    "relaciones, aptitudes, pesos, regiones, clasificaciones.\n"
    "- Sé EXHAUSTIVO: si una fuente menciona 5 razas, extrae las 5 con sus datos.\n"
    "- Ignora solo texto claramente irrelevante (publicidad, metadatos técnicos).\n"
    "- Atribuye cada hecho a su fuente [F1], [F2], etc.\n"
    "- Sin límite rígido de hechos — extrae todo lo relevante.\n"
    "- Si detectas contradicciones entre fuentes, anótalas.\n"
    "- NO inventes hechos — solo extrae lo que dice el contexto.\n"
    "- Incluye información de TODAS las fuentes, no solo las primeras.\n\n"
    "Formato de salida (texto plano, un hecho por línea):\n"
    "[F1] Hecho concreto extraído\n"
    "[F2] Otro hecho relevante\n"
    "[F1,F3] Hecho que aparece en dos fuentes\n"
    "CONTRADICCION: [F2] dice X pero [F4] dice Y\n\n"
    "Si no hay hechos relevantes, responde: SIN_HECHOS_RELEVANTES"
)


def _text_similarity(a: str, b: str) -> float:
    """Similitud rápida entre dos textos (primeros 200 chars)."""
    return SequenceMatcher(None, a[:200].lower(), b[:200].lower()).ratio()


def _text_hash(text: str) -> str:
    """Hash corto para deduplicación rápida."""
    return hashlib.md5(text[:300].encode()).hexdigest()[:12]


def deduplicate_chunks(chunks: list[dict]) -> list[dict]:
    """
    Elimina chunks muy similares (>75% overlap).
    Conserva el chunk con mayor rerank_score de cada grupo.
    """
    if len(chunks) <= 1:
        return chunks

    seen_hashes: set[str] = set()
    unique: list[dict] = []

    for chunk in chunks:
        h = _text_hash(chunk.get("text", ""))

        # Dedup exacta
        if h in seen_hashes:
            continue

        # Dedup fuzzy: comparar con chunks ya aceptados
        is_dup = False
        for existing in unique:
            sim = _text_similarity(chunk.get("text", ""), existing.get("text", ""))
            if sim > _DEDUP_THRESHOLD:
                # Conservar el de mayor score
                if chunk.get("rerank_score", 0) > existing.get("rerank_score", 0):
                    unique.remove(existing)
                    unique.append(chunk)
                is_dup = True
                break

        if not is_dup:
            unique.append(chunk)
            seen_hashes.add(h)

    removed = len(chunks) - len(unique)
    if removed > 0:
        logger.info(f"[Evidence] Dedup: {removed} chunks eliminados ({len(unique)} quedan)")

    return unique


# Keywords que indican especie de cada chunk (para filtrado pre-extracción)
_SPECIES_KEYWORDS = {
    "bovino": {
        "positive": ["bovino", "vacuno", "vaca", "ternero", "ternera", "toro", "novillo",
                      "buey", "bos taurus", "vacas", "cebadero", "cebo bovino"],
        "negative": ["caprino", "cabra", "cabrito", "capra aegagrus", "capra", "cabritos",
                      "ovino", "oveja", "cordero"],
    },
    "porcino": {
        "positive": ["porcino", "cerdo", "cerda", "lechón", "verraco", "sus scrofa",
                      "porcina", "cerdos"],
        "negative": ["caprino", "cabra", "ovino"],
    },
    "aviar": {
        "positive": ["avícola", "aviar", "gallina", "pollo", "gallo", "ponedora",
                      "broiler", "gallinas", "ave", "aves"],
        "negative": [],
    },
    "caprino": {
        "positive": ["caprino", "cabra", "cabrito", "capra", "cabritos"],
        "negative": ["bovino", "vacuno", "vaca"],
    },
}


def _filter_chunks_by_species(
    chunks: list[dict], species_hint: str
) -> list[dict]:
    """
    Filtra chunks que claramente pertenecen a una especie diferente.
    Solo excluye un chunk si tiene keywords negativas y NO tiene keywords positivas.
    """
    if species_hint not in _SPECIES_KEYWORDS:
        return chunks

    pos_kws = _SPECIES_KEYWORDS[species_hint]["positive"]
    neg_kws = _SPECIES_KEYWORDS[species_hint]["negative"]

    if not neg_kws:
        return chunks

    filtered = []
    removed_count = 0
    for chunk in chunks:
        text_lower = chunk.get("text", "").lower()
        has_negative = any(kw in text_lower for kw in neg_kws)
        has_positive = any(kw in text_lower for kw in pos_kws)

        if has_negative and not has_positive:
            removed_count += 1
            logger.info(
                f"[Evidence] Chunk de '{chunk.get('file', '?')}' excluido: "
                f"especie diferente a {species_hint}"
            )
        else:
            filtered.append(chunk)

    if removed_count > 0:
        logger.info(
            f"[Evidence] Species filter ({species_hint}): {removed_count} chunks excluidos, "
            f"{len(filtered)} quedan"
        )

    # Nunca dejar vacío — si todo se filtró, devolver los originales
    return filtered if filtered else chunks


async def extract_evidence(
    query: str,
    chunks: list[dict],
    species_hint: str | None = None,
) -> tuple[str, list[dict], bool]:
    """
    Transforma chunks RAG en evidencia estructurada.

    Returns:
        (evidence_text, filtered_chunks, extracted)
        - evidence_text: hechos extraídos y citados para el LLM
        - filtered_chunks: chunks deduplicados (para el critic)
        - extracted: True si se extrajeron hechos con LLM, False si fallback
    """
    if not chunks:
        return "", [], False

    # 1. Deduplicar
    unique_chunks = deduplicate_chunks(chunks)

    # 1b. Filtrar chunks de especie incorrecta
    if species_hint:
        unique_chunks = _filter_chunks_by_species(unique_chunks, species_hint)

    # 2. Construir contexto para el extractor
    ctx_parts = []
    total_len = 0
    for i, chunk in enumerate(unique_chunks, 1):
        source = chunk.get("file", "desconocido")
        text = chunk.get("text", "")
        if total_len + len(text) > 6000:
            remaining = 6000 - total_len
            if remaining > 100:
                ctx_parts.append(f"[F{i}: {source}]\n{text[:remaining]}…")
            break
        ctx_parts.append(f"[F{i}: {source}]\n{text}")
        total_len += len(text)

    if not ctx_parts:
        return "", unique_chunks, False

    context_str = "\n\n".join(ctx_parts)

    # 3. Pista de especie para dirigir extracción
    species_note = ""
    if species_hint:
        _species_map = {
            "bovino": ("bovino/vacuno", "caprino, porcino, aviar"),
            "porcino": ("porcino/cerdo", "caprino, bovino, aviar"),
            "aviar": ("aviar/gallinas/pollos", "caprino, bovino, porcino"),
            "caprino": ("caprino/cabras", "bovino, porcino, aviar"),
        }
        target, excluded = _species_map.get(species_hint, (species_hint, "otras"))
        species_note = (
            f"\nIMPORTANTE: La pregunta es sobre especie {target}. "
            f"EXCLUYE cualquier hecho sobre {excluded}. "
            f"Si un nombre de raza (p.ej. Retinta) existe en varias especies, "
            f"extrae SOLO los hechos de la especie {target}.\n"
        )

    user_msg = (
        f"PREGUNTA: {query}\n{species_note}\n"
        f"CONTEXTO:\n{context_str}"
    )

    # 4. Llamar al extractor (Together.ai Qwen 7B — rápido)
    settings = get_settings()
    if not settings.together_api_key:
        logger.warning("[Evidence] Sin TOGETHER_API_KEY — usando chunks crudos")
        return _fallback_evidence(unique_chunks), unique_chunks, False

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_model_id,  # Qwen 7B Turbo
                    "messages": [
                        {"role": "system", "content": _EXTRACTOR_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 1200,
                    "temperature": 0.0,
                    "top_p": 0.9,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            evidence = data["choices"][0]["message"]["content"].strip()

        # Si no hay hechos relevantes, usar chunks crudos como fallback
        if "SIN_HECHOS_RELEVANTES" in evidence.upper():
            logger.info("[Evidence] Extractor dice: sin hechos relevantes")
            return _fallback_evidence(unique_chunks), unique_chunks, False

        # Contar hechos extraídos
        fact_count = evidence.count("[F")
        logger.info(
            f"[Evidence] {fact_count} hechos extraídos de {len(unique_chunks)} chunks "
            f"(compresión {len(context_str)}→{len(evidence)} chars)"
        )

        return evidence, unique_chunks, True

    except Exception as e:
        logger.error(f"[Evidence] Error extrayendo hechos: {e}")
        return _fallback_evidence(unique_chunks), unique_chunks, False


def _fallback_evidence(chunks: list[dict]) -> str:
    """Fallback: devuelve chunks concatenados con fuente (sin extracción LLM)."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("file", "desconocido")
        text = chunk.get("text", "")
        parts.append(f"[Fuente {i}: {source}]\n{text}")
    return "\n\n".join(parts)


def build_evidence_context(evidence: str, chunks: list[dict]) -> str:
    """
    Construye el contexto formateado para el LLM.
    Si hay evidencia extraída, la usa. Si no, usa chunks crudos.
    """
    if evidence and "[F" in evidence:
        # Evidencia estructurada del extractor
        return (
            "EVIDENCIA ESTRUCTURADA (hechos extraídos de las fuentes):\n"
            f"{evidence}\n\n"
            "INSTRUCCION: Basa tu respuesta SOLO en estos hechos. "
            "Si un hecho tiene atribución [Fn], es una fuente. "
            "Si hay CONTRADICCIONES, menciónalo. "
            "Si los hechos no cubren la pregunta, dilo con franqueza."
        )

    # Fallback: chunks crudos
    return evidence
