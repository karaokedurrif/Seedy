import json
import logging
import os
from typing import AsyncIterator

import httpx

from .base import CoderChunk, CoderProvider, CoderRequest

logger = logging.getLogger(__name__)


class VLLMLocalProvider(CoderProvider):
    """
    Provider para vLLM local en puerto 8001 sirviendo Qwen2.5-Coder-32B-AWQ.
    
    Compatible con OpenAI API format (v1/chat/completions).
    Ideal para coding agéntico con concurrencia (hasta 8 sesiones).
    """
    name = "vllm_local"

    MODEL_MAP: dict[str, str] = {
        "vllm:qwen2.5-coder-32b": "/models/qwen2.5-coder-32b-awq",
        "vllm:coder-32b": "/models/qwen2.5-coder-32b-awq",
        "vllm:default": "/models/qwen2.5-coder-32b-awq",
    }

    def __init__(self) -> None:
        self._base_url = os.environ.get("VLLM_LOCAL_BASE_URL", "http://192.168.20.57:8001/v1")
        self._api_key = os.environ.get("VLLM_LOCAL_API_KEY", "")
        # Timeout generoso porque 32B es más lento que 7B
        self._timeout = httpx.Timeout(connect=5.0, read=180.0, write=10.0, pool=5.0)

    def supports_model(self, model_id: str) -> bool:
        return model_id in self.MODEL_MAP

    def estimate_cost(self, model_id: str, in_toks: int, out_toks: int) -> float:
        return 0.0  # Local, sin coste cloud

    async def stream(self, req: CoderRequest) -> AsyncIterator[CoderChunk]:
        vllm_model = self.MODEL_MAP.get(req.model_id, "/models/qwen2.5-coder-32b-awq")

        # vLLM no soporta FIM directamente como Ollama, pero puede usar
        # el formato de Qwen2.5-Coder con chat completion
        if req.prompt_fim is not None:
            async for chunk in self._stream_fim(
                vllm_model, req.prompt_fim, req.suffix_fim or "", req.max_tokens, req.temperature
            ):
                yield chunk
            return

        # Chat normal via /v1/chat/completions (OpenAI-compatible)
        payload = {
            "model": vllm_model,
            "messages": req.messages,
            "stream": True,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "top_p": 0.9,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise RuntimeError(
                            f"vLLM {resp.status_code}: {body[:300].decode(errors='replace')}"
                        )
                    
                    async for line in resp.aiter_lines():
                        if not line or not line.strip():
                            continue
                        if line.startswith("data: "):
                            line = line[6:]  # quitar "data: "
                        
                        if line.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(line)
                            if "choices" not in data or len(data["choices"]) == 0:
                                continue
                            
                            choice = data["choices"][0]
                            delta = choice.get("delta", {})
                            content = delta.get("content") or ""
                            finish_reason = choice.get("finish_reason")
                            
                            yield CoderChunk(
                                content=content,
                                finish_reason=finish_reason,
                            )
                        except json.JSONDecodeError as exc:
                            logger.debug(f"[vLLM] Error parseando chunk: {exc} | line: {line[:100]}")
                            continue
            except httpx.TimeoutException:
                logger.error(f"[vLLM] Timeout after {self._timeout.read}s")
                raise RuntimeError(f"vLLM timeout (modelo 32B puede ser lento, considera aumentar timeout)")

    async def _stream_fim(
        self, 
        model: str, 
        prefix: str, 
        suffix: str, 
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[CoderChunk]:
        """
        FIM usando chat completions con formato Qwen2.5-Coder.
        
        vLLM no tiene endpoint /generate como Ollama, así que usamos
        chat con un mensaje que contiene los tokens FIM.
        """
        fim_prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": fim_prompt}],
            "stream": True,
            "temperature": 0.1,  # FIM casi determinista
            "max_tokens": max_tokens,
            "stop": ["<|file_separator|>", "<|im_end|>", "<|endoftext|>"],
        }
        
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(f"vLLM FIM {resp.status_code}: {body[:200].decode(errors='replace')}")
                
                async for line in resp.aiter_lines():
                    if not line or not line.strip():
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(line)
                        if "choices" in data and len(data["choices"]) > 0:
                            choice = data["choices"][0]
                            delta = choice.get("delta", {})
                            content = delta.get("content") or ""
                            finish_reason = choice.get("finish_reason")
                            yield CoderChunk(
                                content=content,
                                finish_reason=finish_reason,
                            )
                    except json.JSONDecodeError as exc:
                        logger.debug(f"[vLLM FIM] Error parseando chunk: {exc}")
                        continue

    async def health_check(self) -> bool:
        """
        Verifica que vLLM está disponible y sirviendo el modelo 32B.
        """
        try:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Check /v1/models endpoint
                r = await client.get(f"{self._base_url}/models", headers=headers)
                if r.status_code != 200:
                    return False
                
                data = r.json()
                models = [m["id"] for m in data.get("data", [])]
                return any("qwen2.5-coder-32b" in m for m in models)
        except Exception as exc:
            logger.debug(f"[vLLM] Health check failed: {exc}")
            return False
