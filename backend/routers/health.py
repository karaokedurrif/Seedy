"""Seedy Backend — Router /health."""

import httpx
import logging

from fastapi import APIRouter
from qdrant_client import QdrantClient

from config import get_settings
from models.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Comprueba la salud de los servicios dependientes."""
    settings = get_settings()
    status = HealthResponse(status="ok")

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            status.ollama = resp.status_code == 200
    except Exception:
        status.ollama = False

    # Qdrant
    try:
        qc = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=5)
        qc.get_collections()  # simple check
        status.qdrant = True
        qc.close()
    except Exception:
        status.qdrant = False

    # Together.ai
    if settings.together_api_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.together_base_url}/models",
                    headers={"Authorization": f"Bearer {settings.together_api_key}"},
                )
                status.together = resp.status_code == 200
        except Exception:
            status.together = False

    # Si alguno crítico falla, marcar degraded
    if not (status.ollama or status.together):
        status.status = "degraded"
    if not status.qdrant:
        status.status = "degraded"

    return status
