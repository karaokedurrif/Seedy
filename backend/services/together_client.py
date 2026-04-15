"""Seedy Backend — Singleton httpx.AsyncClient para llamadas a Together.ai.

Reutiliza una conexión persistente para evitar TLS handshake (~50ms)
en cada llamada al clasificador, rewriter y temporality.
"""

import httpx
import logging

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def get_together_client() -> httpx.AsyncClient:
    """Devuelve un AsyncClient persistente para Together.ai."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
        logger.info("Together.ai httpx client creado")
    return _client


async def close():
    """Cierra el cliente Together.ai."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Together.ai httpx client cerrado")
