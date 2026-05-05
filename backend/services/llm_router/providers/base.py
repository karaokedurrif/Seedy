"""
Base classes para LLM providers.
Define interfaz común para Together, Ollama, y futuros providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Any
import time


@dataclass
class LLMRequest:
    """Request estándar para cualquier provider."""
    messages: list[dict[str, str]]
    model_id: str = ""  # Se setea en runtime por el router
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    format_json: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMChunk:
    """Chunk de streaming response."""
    content: str
    done: bool = False
    first_token_latency_s: Optional[float] = None
    total_latency_s: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class LLMResult:
    """Resultado completo acumulado."""
    content: str
    prompt_tokens: int
    completion_tokens: int
    first_token_latency_s: float
    total_latency_s: float
    model_id: str
    provider: str = ""  # Nombre del provider que generó la respuesta
    cost: float = 0.0  # Coste estimado en USD


class LLMProvider(ABC):
    """Interfaz abstracta para un provider de LLM."""
    
    name: str = "base"
    
    @abstractmethod
    def supports_model(self, model_id: str) -> bool:
        """¿Este provider soporta el model_id dado?"""
        pass
    
    @abstractmethod
    async def health_check(self, model_id: str) -> bool:
        """¿El provider está sano y el modelo disponible?"""
        pass
    
    @abstractmethod
    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMChunk]:
        """Stream de chunks. Siempre devuelve al menos un chunk con done=True al final."""
        pass
    
    async def complete(self, req: LLMRequest) -> LLMResult:
        """Helper para acumular stream en un solo resultado."""
        content = ""
        first_token = None
        total_latency = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        
        async for chunk in self.stream(req):
            if chunk.first_token_latency_s is not None and first_token is None:
                first_token = chunk.first_token_latency_s
            if chunk.done:
                total_latency = chunk.total_latency_s or 0.0
                prompt_tokens = chunk.prompt_tokens
                completion_tokens = chunk.completion_tokens
            else:
                content += chunk.content
        
        return LLMResult(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            first_token_latency_s=first_token or 0.0,
            total_latency_s=total_latency,
            model_id=req.model_id,
            provider=self.name,
        )
    
    def estimate_cost(self, model_id: str, in_tok: int, out_tok: int) -> float:
        """Estima coste en USD. Providers locales retornan 0.0."""
        return 0.0
