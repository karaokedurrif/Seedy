"""Seedy Backend — Reranker local con sentence-transformers (bge-reranker-v2-m3)."""

import logging
import re
from sentence_transformers import CrossEncoder

from config import get_settings

logger = logging.getLogger(__name__)

# ── Detección rápida de idioma ────────────────────────────
_EN_STOPWORDS = re.compile(
    r"\b(the|and|was|were|this|with|from|that|have|for|are|but|not|you|all|can|"
    r"been|which|their|will|each|about|how|than|them|would|these|other|into|has|"
    r"more|two|could|our|also|between|after|those|most|results|using|study|"
    r"treatment|during|effect|compared|showed|group|significantly|obtained)\b",
    re.IGNORECASE,
)

_ES_STOPWORDS = re.compile(
    r"\b(los|las|del|una|con|para|por|que|este|esta|como|más|entre|sobre|"
    r"también|desde|cada|otro|otra|según|estos|estas|ser|han|fue|puede|"
    r"mediante|resultados|estudio|sistema|datos|producción|ganadería|"
    r"explotación|alimentación|manejo|rendimiento|análisis)\b",
    re.IGNORECASE,
)


def _estimate_language(text: str) -> str:
    """Estimación rápida de idioma basada en stopwords. Returns 'es', 'en', or 'other'."""
    sample = text[:400]
    en_hits = len(_EN_STOPWORDS.findall(sample))
    es_hits = len(_ES_STOPWORDS.findall(sample))
    if en_hits > es_hits and en_hits >= 3:
        return "en"
    if es_hits > en_hits and es_hits >= 2:
        return "es"
    return "other"

_model: CrossEncoder | None = None


def warmup():
    """Precarga el modelo reranker (llamar en startup para evitar cold-start)."""
    model = _get_model()
    # Warm run: una predicción dummy para que cargue pesos en GPU/CPU
    model.predict([("test", "test")])
    logger.info("Reranker warm-up completo")


def _get_model() -> CrossEncoder:
    """Carga el modelo de reranking (lazy, singleton). Forzado a CPU para liberar VRAM."""
    global _model
    if _model is None:
        logger.info("Cargando reranker bge-reranker-v2-m3 (CPU)...")
        _model = CrossEncoder(
            "BAAI/bge-reranker-v2-m3", max_length=512, device="cpu"
        )
        logger.info("Reranker cargado en CPU")
    return _model


def rerank(query: str, results: list[dict], top_n: int | None = None) -> list[dict]:
    """
    Re-ordena los resultados RAG usando el cross-encoder.
    Aplica diversificación (max 2 chunks por documento) para evitar
    que un solo PDF domine todo el contexto del LLM.
    Devuelve los top_n mejores diversificados.
    """
    settings = get_settings()
    n = top_n or settings.rag_rerank_top_n

    if not results:
        return []

    if len(results) <= n:
        return results

    model = _get_model()

    # Preparar pares (query, texto)
    pairs = [(query, r["text"]) for r in results]
    scores = model.predict(pairs)

    # Asignar scores de reranking con penalización de idioma
    # Si la query es en español, chunks en inglés reciben -30% score
    query_lang = _estimate_language(query)
    en_penalized = 0
    for r, score in zip(results, scores):
        base_score = float(score)
        chunk_lang = _estimate_language(r.get("text", ""))
        if query_lang == "es" and chunk_lang == "en":
            r["rerank_score"] = base_score * 0.7  # penalizar inglés
            en_penalized += 1
        else:
            r["rerank_score"] = base_score
    if en_penalized:
        logger.info(f"[Rerank] {en_penalized} chunks en inglés penalizados (query={query_lang})")

    # Ordenar por rerank_score
    results.sort(key=lambda x: x["rerank_score"], reverse=True)

    # Diversificación: max 2 chunks por source_file
    # Evita que 5 chunks del mismo PDF dominen el contexto
    seen: dict[str, int] = {}
    diverse: list[dict] = []
    for r in results:
        src = r.get("file", "")
        seen[src] = seen.get(src, 0) + 1
        if seen[src] <= 2:
            diverse.append(r)
        if len(diverse) >= n:
            break

    skipped = len(results[:n]) - len(diverse) if len(diverse) < n else 0
    if skipped:
        logger.info(f"[Rerank] Diversificación: {skipped} chunks redundantes sustituidos")

    return diverse
