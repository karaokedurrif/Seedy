"""Seedy Coder — Provider Anthropic: Claude Opus 4.7 / Sonnet 4.6 (tier max)."""

import json
import logging
import os
from typing import AsyncIterator

import httpx

from .base import CoderChunk, CoderProvider, CoderRequest

logger = logging.getLogger(__name__)


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extrae system message del array OpenAI-format para Anthropic API."""
    system = ""
    user_msgs = []
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "")
        else:
            user_msgs.append(m)
    return system, user_msgs


class AnthropicProvider(CoderProvider):
    name = "anthropic"

    PRICING: dict[str, tuple[float, float]] = {
        "claude-opus-4-7":   (15.0, 75.0),
        "claude-sonnet-4-6": (3.0,  15.0),
    }

    MODEL_MAP: dict[str, str] = {
        "anthropic:claude-opus-4-7":   "claude-opus-4-7",
        "anthropic:claude-sonnet-4-6": "claude-sonnet-4-6",
    }

    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self) -> None:
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def supports_model(self, model_id: str) -> bool:
        return model_id in self.MODEL_MAP

    def estimate_cost(self, model_id: str, in_toks: int, out_toks: int) -> float:
        anthropic_model = self.MODEL_MAP.get(model_id, "claude-opus-4-7")
        pin, pout = self.PRICING.get(anthropic_model, (15.0, 75.0))
        return (in_toks * pin + out_toks * pout) / 1_000_000

    async def stream(self, req: CoderRequest) -> AsyncIterator[CoderChunk]:
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY no configurada")

        anthropic_model = self.MODEL_MAP[req.model_id]
        system_prompt, messages = _split_system(req.messages)

        payload: dict = {
            "model": anthropic_model,
            "messages": messages,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(
            connect=10.0, read=180.0, write=10.0, pool=5.0
        )) as client:
            async with client.stream(
                "POST",
                self.ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Anthropic {resp.status_code}: {body[:200].decode(errors='replace')}"
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() in ("[DONE]", ""):
                        continue
                    try:
                        data = json.loads(raw)
                        event_type = data.get("type", "")
                        if event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            content = delta.get("text") or ""
                            yield CoderChunk(content=content)
                        elif event_type == "message_delta":
                            stop_reason = data.get("delta", {}).get("stop_reason")
                            if stop_reason:
                                yield CoderChunk(content="", finish_reason=stop_reason)
                    except Exception as exc:
                        logger.debug(f"[Anthropic] Error parseando chunk: {exc}")
                        continue

    async def health_check(self) -> bool:
        return bool(self._api_key)
