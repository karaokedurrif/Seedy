"""Seedy Backend — Reranker local con sentence-transformers (bge-reranker-v2-m3)."""

import logging
from sentence_transformers import CrossEncoder

from config import get_settings

logger = logging.getLogger(__name__)

_model: CrossEncoder | None = None


def warmup():
    """Precarga el modelo reranker (llamar en startup para evitar cold-start)."""
    model = _get_model()
    # Warm run: una predicción dummy para que cargue pesos en GPU/CPU
    model.predict([("test", "test")])
    logger.info("Reranker warm-up completo")


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

    # Asignar scores de reranking
    for r, score in zip(results, scores):
        r["rerank_score"] = float(score)

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
