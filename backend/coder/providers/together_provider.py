"""Seedy Coder — Provider Together.ai: GLM-5.1, Qwen3-Coder-Next, Qwen3-Coder-480B, MiniMax M2.7."""

import logging
import os
import time
from typing import AsyncIterator

import httpx

from .base import CoderChunk, CoderProvider, CoderRequest

logger = logging.getLogger(__name__)


class TogetherProvider(CoderProvider):
    name = "together"

    # USD por 1M tokens (input, output) — abril 2026
    PRICING: dict[str, tuple[float, float]] = {
        "zai-org/GLM-5.1":                                (1.00, 3.20),
        "zai-org/GLM-5":                                  (1.00, 3.20),
        "Qwen/Qwen3-Coder-Next-FP8":                      (0.50, 1.20),
        "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8":        (0.60, 2.50),
        "MiniMaxAI/MiniMax-M2.7":                         (0.30, 1.20),
        "Qwen/Qwen3.5-397B-A17B":                         (0.60, 3.60),
    }

    # alias interno → modelo Together
    MODEL_MAP: dict[str, str] = {
        "together:glm-5.1":          "zai-org/GLM-5.1",
        "together:glm-5":            "zai-org/GLM-5",
        "together:qwen3-coder-next": "Qwen/Qwen3-Coder-Next-FP8",
        "together:qwen3-coder-480b": "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        "together:minimax-m2.7":     "MiniMaxAI/MiniMax-M2.7",
    }

    BASE_URL = "https://api.together.xyz/v1"
    TIMEOUT_FIRST_TOKEN = 30.0
    TIMEOUT_TOTAL = 180.0

    def __init__(self) -> None:
        self._api_key = os.environ.get("TOGETHER_API_KEY", "")

    def supports_model(self, model_id: str) -> bool:
        return model_id in self.MODEL_MAP

    def estimate_cost(self, model_id: str, in_toks: int, out_toks: int) -> float:
        together_model = self.MODEL_MAP.get(model_id, "")
        pin, pout = self.PRICING.get(together_model, (1.00, 3.20))
        return (in_toks * pin + out_toks * pout) / 1_000_000

    async def stream(self, req: CoderRequest) -> AsyncIterator[CoderChunk]:
        if not self._api_key:
            raise RuntimeError("TOGETHER_API_KEY no configurada")

        together_model = self.MODEL_MAP[req.model_id]

        payload: dict = {
            "model": together_model,
            "messages": req.messages,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "stream": True,
        }
        if req.tools:
            payload["tools"] = req.tools

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(
            connect=10.0, read=self.TIMEOUT_TOTAL, write=10.0, pool=5.0
        )) as client:
            async with client.stream(
                "POST",
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Together {resp.status_code}: {body[:200].decode(errors='replace')}"
                    )

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        import json
                        data = json.loads(raw)
                        choice = data["choices"][0]
                        delta = choice.get("delta", {})
                        content = delta.get("content") or ""
                        finish_reason = choice.get("finish_reason")
                        tool_calls = delta.get("tool_calls")
                        yield CoderChunk(
                            content=content,
                            finish_reason=finish_reason,
                            tool_calls=tool_calls,
                        )
                    except Exception as exc:
                        logger.debug(f"[Together] Error parseando chunk: {exc}")
                        continue

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return r.status_code == 200
        except Exception:
            return False
