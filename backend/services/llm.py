"""Seedy Backend — Servicio LLM: Together.ai (principal) + Ollama (fallback)."""

import httpx
import logging

from config import get_settings

logger = logging.getLogger(__name__)


async def generate(
    system_prompt: str,
    user_message: str,
    context_chunks: list[dict] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> tuple[str, str]:
    """
    Genera respuesta con Together.ai, fallback a Ollama.
    
    Returns:
        (respuesta, modelo_usado) — modelo_usado es "together" o "ollama"
    """
    # Construir mensaje con contexto RAG
    full_user = _build_user_message(user_message, context_chunks)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_user},
    ]

    # Intentar Together.ai primero
    answer = await _call_together(messages, max_tokens, temperature)
    if answer:
        return answer, "together"

    # Fallback a Ollama
    logger.warning("Together.ai falló, usando Ollama como fallback")
    answer = await _call_ollama(messages, max_tokens, temperature)
    if answer:
        return answer, "ollama"

    return "Lo siento, no he podido generar una respuesta en este momento. Inténtalo de nuevo.", "none"


def _build_user_message(query: str, chunks: list[dict] | None) -> str:
    """Construye el mensaje del usuario con contexto RAG inyectado."""
    if not chunks:
        return query

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("file", "desconocido")
        text = chunk.get("text", "")
        context_parts.append(f"[Fuente {i}: {source}]\n{text}")

    context_str = "\n\n".join(context_parts)

    return (
        f"Usa el siguiente contexto para responder la pregunta. "
        f"Si el contexto no contiene la información necesaria, responde con tu conocimiento "
        f"pero indica que no encontraste la fuente específica.\n\n"
        f"--- CONTEXTO ---\n{context_str}\n--- FIN CONTEXTO ---\n\n"
        f"Pregunta: {query}"
    )


async def _call_together(
    messages: list[dict], max_tokens: int, temperature: float
) -> str | None:
    """Llamada a Together.ai."""
    settings = get_settings()

    if not settings.together_api_key:
        logger.warning("TOGETHER_API_KEY no configurada")
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": 0.9,
                    "repetition_penalty": 1.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error en Together.ai: {e}")
        return None


async def _call_ollama(
    messages: list[dict], max_tokens: int, temperature: float
) -> str | None:
    """Llamada a Ollama (fallback local)."""
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "top_p": 0.9,
                        "repeat_penalty": 1.1,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error en Ollama: {e}")
        return None
