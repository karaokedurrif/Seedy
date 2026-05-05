"""
Ollama Provider — Cliente HTTP para Ollama local del DGX.
Soporta streaming OpenAI-style y health checks.
"""

import httpx
import time
import json
import logging
from typing import AsyncIterator
from .base import LLMProvider, LLMRequest, LLMChunk

log = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Cliente HTTP del Ollama del DGX."""
    
    name = "ollama"
    
    MODEL_MAP = {
        "ollama:qwen2.5-7b":  "qwen2.5:7b-instruct-q4_K_M",
        "ollama:seedy-v16":   "seedy:v16",
        "ollama:qwen2.5-72b": "qwen2.5:72b-instruct-q4_K_M",
    }
    
    DEFAULT_OPTIONS = {
        "qwen2.5:7b-instruct-q4_K_M": {
            "num_ctx": 8192,
            "temperature": 0.3,
            "top_p": 0.9,
        },
        "seedy:v16": {
            "num_ctx": 16384,
            "temperature": 0.3,
            "top_p": 0.9,
        },
        "qwen2.5:72b-instruct-q4_K_M": {
            "num_ctx": 32768,
            "temperature": 0.3,
            "top_p": 0.9,
            "keep_alive": "24h",  # Crítico para no descargar
        },
    }
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=5.0))
    
    def supports_model(self, model_id: str) -> bool:
        return model_id in self.MODEL_MAP
    
    async def health_check(self, model_id: str) -> bool:
        """¿Ollama up + modelo disponible?"""
        try:
            r = await self.client.get(f"{self.base_url}/api/tags", timeout=2.0)
            if r.status_code != 200:
                return False
            ollama_model = self.MODEL_MAP.get(model_id)
            if not ollama_model:
                return False
            models = r.json().get("models", [])
            return any(m["name"] == ollama_model for m in models)
        except Exception as exc:
            log.warning(f"Ollama health check failed: {exc}")
            return False
    
    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMChunk]:
        ollama_model = self.MODEL_MAP[req.model_id]
        opts = self.DEFAULT_OPTIONS.get(ollama_model, {}).copy()
        
        if req.max_tokens:
            opts["num_predict"] = req.max_tokens
        if req.temperature is not None:
            opts["temperature"] = req.temperature
        
        payload = {
            "model": ollama_model,
            "messages": req.messages,
            "stream": True,
            "options": opts,
        }
        
        if req.format_json:
            payload["format"] = "json"
        
        start = time.time()
        first_token_at = None
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    if first_token_at is None and chunk.get("message", {}).get("content"):
                        first_token_at = time.time() - start
                    
                    if chunk.get("done"):
                        yield LLMChunk(
                            content="",
                            done=True,
                            first_token_latency_s=first_token_at,
                            total_latency_s=time.time() - start,
                            prompt_tokens=chunk.get("prompt_eval_count", 0),
                            completion_tokens=chunk.get("eval_count", 0),
                        )
                    else:
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield LLMChunk(
                                content=content,
                                done=False,
                            )
        
        except Exception as exc:
            log.exception(f"Ollama stream failed for {ollama_model}: {exc}")
            raise
    
    def estimate_cost(self, model_id: str, in_tok: int, out_tok: int) -> float:
        return 0.0  # Local, gratis (consumo eléctrico aparte)
