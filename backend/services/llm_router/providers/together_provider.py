"""
Together.ai Provider — Cliente para API de Together.
Extracción y refactor del código actual de openai_client.py.
"""

import httpx
import time
import json
import logging
import os
from typing import AsyncIterator
from .base import LLMProvider, LLMRequest, LLMChunk

log = logging.getLogger(__name__)


class TogetherProvider(LLMProvider):
    """Cliente para Together.ai API."""
    
    name = "together"
    
    # Pricing Together.ai (USD per million tokens)
    PRICING = {
        "together:qwen3-235b-tput": {"input": 1.20, "output": 1.60},
        "together:deepseek-r1": {"input": 3.50, "output": 14.00},
        "together:qwen2.5-7b-turbo": {"input": 0.30, "output": 0.30},
        "together:kimi-k2.5": {"input": 0.50, "output": 2.80},
    }
    
    MODEL_MAP = {
        "together:qwen3-235b-tput": "Qwen/Qwen3-235B-A22B-Instruct-2507-tput",
        "together:deepseek-r1": "deepseek-ai/DeepSeek-R1-0528",
        "together:qwen2.5-7b-turbo": "Qwen/Qwen2.5-7B-Instruct-Turbo",
        "together:kimi-k2.5": "moonshotai/Kimi-K2.5",
    }
    
    def __init__(self, api_key: str = None, base_url: str = "https://api.together.xyz/v1"):
        self.api_key = api_key or os.getenv("TOGETHER_API_KEY")
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    def supports_model(self, model_id: str) -> bool:
        return model_id in self.MODEL_MAP
    
    async def health_check(self, model_id: str) -> bool:
        """Simple check: ¿API responde?"""
        try:
            # Minimal test: list models endpoint
            r = await self.client.get(f"{self.base_url}/models", timeout=3.0)
            return r.status_code == 200
        except Exception as exc:
            log.warning(f"Together health check failed: {exc}")
            return False
    
    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMChunk]:
        together_model = self.MODEL_MAP[req.model_id]
        
        payload = {
            "model": together_model,
            "messages": req.messages,
            "stream": True,
            "temperature": req.temperature or 0.3,
            "top_p": 0.9,
        }
        
        if req.max_tokens:
            payload["max_tokens"] = req.max_tokens
        
        if req.format_json:
            payload["response_format"] = {"type": "json_object"}
        
        start = time.time()
        first_token_at = None
        prompt_tokens = 0
        completion_tokens = 0
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    # Together usa SSE format: "data: {...}"
                    if line.startswith("data: "):
                        line = line[6:]
                    
                    if line.strip() == "[DONE]":
                        continue
                    
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
                    
                    if first_token_at is None and content:
                        first_token_at = time.time() - start
                    
                    if finish_reason:
                        # Last chunk con usage
                        usage = chunk.get("usage", {})
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                        
                        yield LLMChunk(
                            content="",
                            done=True,
                            first_token_latency_s=first_token_at,
                            total_latency_s=time.time() - start,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                        )
                    else:
                        if content:
                            yield LLMChunk(
                                content=content,
                                done=False,
                            )
        
        except Exception as exc:
            log.exception(f"Together stream failed for {together_model}: {exc}")
            raise
    
    def estimate_cost(self, model_id: str, in_tok: int, out_tok: int) -> float:
        """Calcula coste en USD."""
        pricing = self.PRICING.get(model_id, {"input": 0.0, "output": 0.0})
        cost = (in_tok * pricing["input"] / 1_000_000) + (out_tok * pricing["output"] / 1_000_000)
        return cost
