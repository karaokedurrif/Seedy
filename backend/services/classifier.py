"""Seedy Backend — Clasificador de queries vía Together.ai."""

import httpx
import logging

from config import get_settings
from models.prompts import CLASSIFIER_SYSTEM, CATEGORIES

logger = logging.getLogger(__name__)


async def classify_query(query: str) -> str:
    """
    Clasifica la query del usuario en una categoría usando Together.ai.
    Llamada corta (~10 tokens) para decidir qué colecciones RAG consultar.
    Fallback: GENERAL si falla la clasificación.
    """
    settings = get_settings()

    if not settings.together_api_key:
        logger.warning("TOGETHER_API_KEY no configurada, usando categoría GENERAL")
        return "GENERAL"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_model_id,
                    "messages": [
                        {"role": "system", "content": CLASSIFIER_SYSTEM},
                        {"role": "user", "content": query},
                    ],
                    "max_tokens": 10,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip().upper()

            # Extraer categoría válida
            for cat in CATEGORIES:
                if cat in raw:
                    logger.info(f"Query clasificada como: {cat}")
                    return cat

            logger.warning(f"Categoría no reconocida '{raw}', usando GENERAL")
            return "GENERAL"

    except Exception as e:
        logger.error(f"Error en clasificación: {e}. Fallback a GENERAL")
        return "GENERAL"
