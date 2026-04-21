"""Seedy Coder — Provider Ollama local: seedy-coder:agritech (Qwen2.5-Coder-14B)."""

import json
import logging
import os
from typing import AsyncIterator

import httpx

from .base import CoderChunk, CoderProvider, CoderRequest

logger = logging.getLogger(__name__)


class OllamaProvider(CoderProvider):
    name = "ollama"

    MODEL_MAP: dict[str, str] = {
        "ollama:agritech": "seedy-coder:agritech",
        "ollama:default":  "seedy-coder:agritech",
    }

    def __init__(self) -> None:
        self._base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")

    def supports_model(self, model_id: str) -> bool:
        return model_id in self.MODEL_MAP

    def estimate_cost(self, model_id: str, in_toks: int, out_toks: int) -> float:
        return 0.0  # local, gratis salvo electricidad

    async def stream(self, req: CoderRequest) -> AsyncIterator[CoderChunk]:
        ollama_model = self.MODEL_MAP.get(req.model_id, "seedy-coder:agritech")

        # FIM (Fill-In-the-Middle) via /api/generate con suffix
        if req.prompt_fim is not None:
            async for chunk in self._stream_fim(
                ollama_model, req.prompt_fim, req.suffix_fim or "", req.max_tokens
            ):
                yield chunk
            return

        # Chat normal via /api/chat
        payload = {
            "model": ollama_model,
            "messages": req.messages,
            "stream": True,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(
            connect=5.0, read=120.0, write=10.0, pool=5.0
        )) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Ollama {resp.status_code}: {body[:200].decode(errors='replace')}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        message = data.get("message", {})
                        content = message.get("content") or ""
                        done = data.get("done", False)
                        yield CoderChunk(
                            content=content,
                            finish_reason="stop" if done else None,
                        )
                    except Exception as exc:
                        logger.debug(f"[Ollama] Error parseando chunk: {exc}")
                        continue

    async def _stream_fim(
        self, model: str, prefix: str, suffix: str, max_tokens: int
    ) -> AsyncIterator[CoderChunk]:
        """FIM usando /api/generate con tokens especiales de Qwen2.5-Coder."""
        fim_prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
        payload = {
            "model": model,
            "prompt": fim_prompt,
            "stream": True,
            "options": {
                "temperature": 0.1,  # FIM: casi determinista
                "num_predict": max_tokens,
                "stop": ["<|file_separator|>", "<|im_end|>", "<|endoftext|>"],
            },
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(
            connect=5.0, read=60.0, write=10.0, pool=5.0
        )) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/generate",
                json=payload,
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("response") or ""
                        done = data.get("done", False)
                        yield CoderChunk(
                            content=content,
                            finish_reason="stop" if done else None,
                        )
                    except Exception as exc:
                        logger.debug(f"[Ollama FIM] Error parseando chunk: {exc}")
                        continue

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self._base_url}/api/tags")
                if r.status_code != 200:
                    return False
                data = r.json()
                models = [m["name"] for m in data.get("models", [])]
                return any("seedy-coder" in m for m in models)
        except Exception:
            return False
