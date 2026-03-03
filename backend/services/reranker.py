"""Seedy Backend — Reranker local con sentence-transformers (bge-reranker-v2-m3)."""

import logging
from sentence_transformers import CrossEncoder

from config import get_settings

logger = logging.getLogger(__name__)

_model: CrossEncoder | None = None


def _get_model() -> CrossEncoder:
    """Carga el modelo de reranking (lazy, singleton)."""
    global _model
    if _model is None:
        logger.info("Cargando reranker bge-reranker-v2-m3...")
        _model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
        logger.info("Reranker cargado")
    return _model


def rerank(query: str, results: list[dict], top_n: int | None = None) -> list[dict]:
    """
    Re-ordena los resultados RAG usando el cross-encoder.
    Devuelve los top_n mejores.
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

    # Asignar scores de reranking
    for r, score in zip(results, scores):
        r["rerank_score"] = float(score)

    # Ordenar por rerank_score y devolver top_n
    results.sort(key=lambda x: x["rerank_score"], reverse=True)
    return results[:n]
