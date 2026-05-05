"""
LLM Router v4.6 — Hibridación Inteligente
Componente central para enrutamiento inteligente entre Together.ai y Ollama local.
"""

from .router import llm_router
from .policy import POLICIES, StepPolicy
from .providers.base import LLMProvider, LLMRequest, LLMChunk, LLMResult

__all__ = [
    "llm_router",
    "POLICIES",
    "StepPolicy",
    "LLMProvider",
    "LLMRequest",
    "LLMChunk",
    "LLMResult",
]
