"""Seedy Backend — Servicio LLM: Together.ai (principal) + Ollama (fallback local)."""

import json
import re
import httpx
import logging
from typing import AsyncGenerator

from config import get_settings

logger = logging.getLogger(__name__)

# Regex para limpiar bloques <think>...</think> de DeepSeek-R1
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


async def generate(
    system_prompt: str,
    user_message: str,
    context_chunks: list[dict] | None = None,
    history: list[dict] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    evidence_override: str | None = None,
) -> tuple[str, str]:
    """
    Genera respuesta con Together.ai (Kimi-K2.5, principal), fallback a Ollama local.

    Args:
        evidence_override: Si se proporciona (Fase 2 evidence builder),
            se usa como contexto en vez de los chunks crudos.

    Returns:
        (respuesta, modelo_usado) — modelo_usado es "together" u "ollama"
    """
    # Construir mensaje con contexto RAG o evidencia estructurada
    if evidence_override:
        full_user = _build_user_message_with_evidence(user_message, evidence_override)
    else:
        full_user = _build_user_message(user_message, context_chunks)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": full_user})

    # Together.ai primero (Kimi-K2.5 — modelo potente cloud)
    answer = await _call_together(messages, max_tokens, temperature)
    if answer:
        return answer, "together"

    # Fallback a Ollama (modelo fine-tuned local, RTX 5080)
    logger.warning("Together.ai falló, usando Ollama local como fallback")
    answer = await _call_ollama(messages, max_tokens, temperature)
    if answer:
        return answer, "ollama"

    return "Lo siento, no he podido generar una respuesta en este momento. Inténtalo de nuevo.", "none"


async def generate_report(
    system_prompt: str,
    user_message: str,
    context_chunks: list[dict] | None = None,
    history: list[dict] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.5,
    evidence_override: str | None = None,
) -> tuple[str, str]:
    """
    Genera informe ejecutivo usando Together.ai (DeepSeek-R1 — máximo razonamiento).
    Limpia automáticamente los bloques <think>...</think> del output.

    Returns:
        (respuesta, modelo_usado) — modelo_usado es "together-report"
    """
    if evidence_override:
        full_user = (
            f"{evidence_override}\n\n"
            f"SOLICITUD DEL CLIENTE:\n{user_message}"
        )
    else:
        full_user = _build_user_message(user_message, context_chunks)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": full_user})

    settings = get_settings()
    if not settings.together_api_key:
        logger.warning("TOGETHER_API_KEY no configurada — fallback a Ollama para informe")
        answer = await _call_ollama(messages, max_tokens, temperature)
        if answer:
            return answer, "ollama"
        return "No se pudo generar el informe. Verifica la configuración de Together.ai.", "none"

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_report_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": 0.92,
                    "repetition_penalty": 1.0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"].strip()
            # Limpiar bloques <think>...</think> de DeepSeek-R1
            answer = _THINK_RE.sub("", answer).strip()
            logger.info(f"[LLM] Informe generado via Together ({settings.together_report_model}): "
                        f"{len(answer)} chars")
            return answer, "together-report"
    except Exception as e:
        logger.error(f"[LLM] Error Together report: {e} — fallback a Together smart")
        # Fallback a modelo smart (Kimi-K2.5) en vez de Ollama local
        answer = await _call_together(messages, max_tokens, temperature)
        if answer:
            return answer, "together"
        # Último recurso: Ollama
        answer = await _call_ollama(messages, max_tokens, temperature)
        if answer:
            return answer, "ollama"
        return "No se pudo generar el informe en este momento.", "none"


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
        f"Usa el siguiente contexto como fuente principal para responder la pregunta. "
        f"Puedes razonar, deducir y hacer recomendaciones técnicas basándote en los datos "
        f"del contexto y en tu conocimiento zootécnico como experto. "
        f"Si el contexto no cubre algo pero tienes conocimiento fiable del dominio, úsalo "
        f"marcándolo como inferencia experta. Solo inventa datos numéricos específicos "
        f"(pesos exactos, porcentajes, índices) si están en el contexto.\n\n"
        f"IMPORTANTE: Si el contexto contiene datos específicos (pesos, porcentajes, índices, "
        f"roles padre/madre, scores, aptitudes numéricas), INCLUYE esos datos concretos en tu "
        f"respuesta. Evita descripciones genéricas como 'resistente y adaptada' cuando tienes "
        f"cifras reales disponibles.\n\n"
        f"--- CONTEXTO ---\n{context_str}\n--- FIN CONTEXTO ---\n\n"
        f"Pregunta: {query}"
    )


def _build_user_message_with_evidence(query: str, evidence: str) -> str:
    """Construye el mensaje con evidencia estructurada (Fase 2 evidence builder)."""
    return (
        f"Usa la siguiente evidencia estructurada para responder la pregunta. "
        f"Puedes razonar y hacer inferencias técnicas combinando la evidencia con tu "
        f"conocimiento zootécnico experto. Si la evidencia no cubre algo, usa tu "
        f"conocimiento del dominio marcándolo como inferencia propia.\n\n"
        f"IMPORTANTE:\n"
        f"- Si la evidencia contiene datos específicos (pesos, cifras, scores), inclúyelos.\n"
        f"- NO incluyas las referencias [F1], [F2], etc. en tu respuesta — son para tu uso interno.\n"
        f"- Responde como experto, NO como copiador del contexto.\n"
        f"- Si hay contradicciones entre fuentes, menciónalo de forma natural.\n\n"
        f"--- EVIDENCIA ---\n{evidence}\n--- FIN EVIDENCIA ---\n\n"
        f"Pregunta: {query}"
    )


async def _call_together(
    messages: list[dict], max_tokens: int, temperature: float
) -> str | None:
    """Llamada a Together.ai (modelo principal).

    Usa max_tokens directamente sin padding extra de reasoning.
    Si devuelve vacío, reintenta una vez con más tokens.
    """
    settings = get_settings()

    if not settings.together_api_key:
        logger.warning("TOGETHER_API_KEY no configurada")
        return None

    effective_max = max(max_tokens, 2048)

    for attempt in range(2):  # Máx 1 retry
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{settings.together_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.together_api_key}"},
                    json={
                        "model": settings.together_model_id,
                        "messages": messages,
                        "max_tokens": effective_max,
                        "temperature": temperature,
                        "top_p": 0.9,
                        "repetition_penalty": 1.1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                answer = (choice.get("message", {}).get("content") or "").strip()
                finish = choice.get("finish_reason", "unknown")
                logger.info(
                    f"[LLM] Respuesta via Together ({settings.together_model_id}): "
                    f"{len(answer)} chars, finish_reason={finish}, max_tokens={effective_max}"
                )

                if not answer and finish == "length" and attempt == 0:
                    # Reasoning consumió todos los tokens — reintentar con más espacio
                    effective_max = min(effective_max * 2, 16384)
                    logger.warning(
                        f"[LLM] Together: reasoning agotó tokens (finish=length, 0 chars). "
                        f"Reintentando con max_tokens={effective_max}"
                    )
                    continue

                if not answer:
                    logger.warning(
                        f"[LLM] Together devolvió respuesta vacía (finish_reason={finish}). "
                        f"Raw choice: {str(choice)[:300]}"
                    )
                return answer if answer else None
        except Exception as e:
            logger.error(f"Error en Together.ai: {e}")
            return None

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


# ── Streaming ─────────────────────────────────────────

async def generate_stream(
    system_prompt: str,
    user_message: str,
    context_chunks: list[dict] | None = None,
    history: list[dict] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> AsyncGenerator[tuple[str, str], None]:
    """
    Genera respuesta token-a-token en streaming.
    Yields: (token_text, modelo_usado)
    Together.ai primero (Kimi-K2.5), fallback a Ollama local.
    """
    full_user = _build_user_message(user_message, context_chunks)
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": full_user})

    # Together.ai primero (Kimi-K2.5 — modelo potente cloud)
    settings = get_settings()
    if settings.together_api_key:
        try:
            async for token in _stream_together(messages, max_tokens, temperature):
                yield token, "together"
            return
        except Exception as e:
            logger.warning(f"Together streaming falló: {e}")

    # Fallback a Ollama (fine-tuned local, RTX 5080)
    try:
        async for token in _stream_ollama(messages, max_tokens, temperature):
            yield token, "ollama"
        return
    except Exception as e:
        logger.error(f"Ollama streaming falló: {e}")

    yield "Lo siento, no he podido generar una respuesta en este momento.", "none"


async def _stream_together(
    messages: list[dict], max_tokens: int, temperature: float
) -> AsyncGenerator[str, None]:
    """Streaming desde Together.ai (formato SSE OpenAI-compatible)."""
    settings = get_settings()
    effective_max = max(max_tokens, 2048)
    async with httpx.AsyncClient(timeout=90.0) as client:
        async with client.stream(
            "POST",
            f"{settings.together_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.together_api_key}"},
            json={
                "model": settings.together_model_id,
                "messages": messages,
                "max_tokens": effective_max,
                "temperature": temperature,
                "top_p": 0.9,
                "repetition_penalty": 1.1,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                content = (
                    chunk.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if content:
                    yield content


async def _stream_ollama(
    messages: list[dict], max_tokens: int, temperature: float
) -> AsyncGenerator[str, None]:
    """Streaming desde Ollama (/api/chat con stream=true)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                },
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
                if data.get("done", False):
                    break
