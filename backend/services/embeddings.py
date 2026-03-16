"""Seedy Backend — Servicio de embeddings vía Ollama (mxbai-embed-large)."""

import httpx
import logging
import unicodedata

from config import get_settings

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normaliza diacríticos para mejorar retrieval.

    Convierte NFD → NFC y opcionalmente strip combining marks
    para que 'sayagüesa' y 'sayaguesa' generen embeddings similares.
    Hace doble búsqueda: la original y la normalizada.
    """
    # NFD descompone: ü → u + combining diaeresis
    nfkd = unicodedata.normalize("NFKD", text)
    # Quitar combining marks (acentos, diéresis, etc.) pero mantener ñ
    cleaned = "".join(
        c for c in nfkd
        if not unicodedata.combining(c) or c == "\u0303"  # conservar tilde de ñ
    )
    # Re-componer para que n+tilde → ñ siga siendo ñ
    return unicodedata.normalize("NFC", cleaned)

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
                json={
                    "model": settings.ollama_embed_model,
                    "input": text,
                    "truncate": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings.append(data["embeddings"][0])
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            raise

    return embeddings


async def embed_query(text: str) -> list[float]:
    """Genera embedding para una query única.

    Genera DOS embeddings (original + normalizada sin diacríticos)
    y devuelve el promedio para mejorar retrieval con tildes/diéresis.
    """
    normalized = normalize_text(text)
    if normalized != text:
        logger.debug(f"Query normalizada: '{text[:50]}' → '{normalized[:50]}'")
        vecs = await embed_texts([text, normalized])
        # Promedio de ambos vectores
        return [(a + b) / 2.0 for a, b in zip(vecs[0], vecs[1])]
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
