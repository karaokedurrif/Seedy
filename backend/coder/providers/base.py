"""Seedy Coder — Interfaz base para proveedores de LLM de coding."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class CoderRequest:
    messages: list[dict]
    model_id: str           # id interno tipo "together:glm-5.1"
    max_tokens: int = 2048
    temperature: float = 0.2
    tools: list[dict] | None = None
    stream: bool = True
    # FIM (Fill-In-the-Middle)
    prompt_fim: str | None = None    # prefix
    suffix_fim: str | None = None    # suffix


@dataclass
class CoderChunk:
    content: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None


@dataclass
class CoderUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class CoderProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def stream(self, req: CoderRequest) -> AsyncIterator[CoderChunk]:
        """Stream de chunks de respuesta."""
        ...

    @abstractmethod
    def supports_model(self, model_id: str) -> bool:
        """¿Este provider soporta el model_id interno dado?"""
        ...

    @abstractmethod
    def estimate_cost(self, model_id: str, in_toks: int, out_toks: int) -> float:
        """Estima el coste en USD para los tokens dados."""
        ...

    async def health_check(self) -> bool:
        """Comprueba que el provider está disponible. True = ok."""
        return True
