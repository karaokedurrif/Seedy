"""Seedy Backend — Servicio de embeddings vía Ollama (mxbai-embed-large)."""

import httpx
import logging

from config import get_settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Genera embeddings para una lista de textos usando Ollama."""
    settings = get_settings()
    client = await _get_client()
    embeddings = []

    for text in texts:
        try:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={"model": settings.ollama_embed_model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings.append(data["embeddings"][0])
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            raise

    return embeddings


async def embed_query(text: str) -> list[float]:
    """Genera embedding para una query única."""
    result = await embed_texts([text])
    return result[0]


async def get_embedding_dimension() -> int:
    """Obtiene la dimensión del modelo de embeddings."""
    test = await embed_query("test")
    return len(test)


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
