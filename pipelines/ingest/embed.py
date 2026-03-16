"""Pipeline de autoingesta — Embeddings vía Ollama (con retry)."""

import asyncio
import logging
import httpx

from pipelines.ingest.settings import get_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY = 10  # segundos entre reintentos


async def _post_with_retry(client: httpx.AsyncClient, url: str, payload: dict) -> dict:
    """POST con reintentos para tolerar arranques lentos de Ollama."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as e:
            if attempt == MAX_RETRIES:
                raise
            logger.warning(
                f"  Embed intento {attempt}/{MAX_RETRIES} falló ({e}). "
                f"Reintentando en {RETRY_DELAY}s..."
            )
            await asyncio.sleep(RETRY_DELAY)
    raise RuntimeError("Embed: máximo de reintentos alcanzado")


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Genera embeddings para una lista de textos usando Ollama."""
    settings = get_settings()
    url = f"{settings.ollama_url}/api/embed"
    embeddings = []

    async with httpx.AsyncClient(timeout=120) as client:
        for i in range(0, len(texts), settings.embed_batch_size):
            batch = texts[i : i + settings.embed_batch_size]
            data = await _post_with_retry(
                client,
                url,
                {
                    "model": settings.embed_model,
                    "input": batch,
                    "truncate": True,
                },
            )
            embeddings.extend(data["embeddings"])

    return embeddings


async def embed_query(text: str) -> list[float]:
    """Genera embedding para un solo texto."""
    result = await embed_texts([text])
    return result[0]


async def get_embedding_dimension() -> int:
    """Obtiene la dimensión del modelo de embeddings."""
    test_emb = await embed_texts(["test"])
    return len(test_emb[0])
