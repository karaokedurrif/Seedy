"""Seedy Backend — Helpers SSE para streaming OpenAI-compatible.

Funciones reutilizables para emitir respuestas en formato SSE (Server-Sent Events)
siguiendo la especificación de la API de OpenAI.
"""

import json
import uuid
from typing import AsyncGenerator


def oai_response(answer: str, model: str, t0: float) -> dict:
    """Respuesta no-streaming en formato OpenAI."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(t0),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": len(answer.split()),
            "total_tokens": len(answer.split()),
        },
    }


async def fake_stream_answer(answer: str, model: str, t0: float) -> AsyncGenerator[str, None]:
    """Emite una respuesta ya completa palabra a palabra como fake-stream SSE.

    Formato OpenAI chat.completion.chunk compatible con Open WebUI.
    """
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Primer chunk con role
    first = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": int(t0),
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(first)}\n\n"

    # Emitir por palabras
    words = answer.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else f" {word}"
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": int(t0),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    # Chunk final
    done = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": int(t0),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done)}\n\n"
    yield "data: [DONE]\n\n"


def error_response(msg: str) -> dict:
    """Respuesta de error en formato OpenAI."""
    return {
        "error": {
            "message": msg,
            "type": "invalid_request_error",
            "param": None,
            "code": None,
        }
    }
