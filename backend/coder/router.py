"""Seedy Coder — Router de modelos: elige el provider/modelo según task_type y tier."""

import logging
from typing import AsyncIterator

from .policy import (
    CONTEXT_LIMITS,
    DEGRADATION_CHAIN,
    DEGRADATION_CHAIN_LOCAL,
    DEGRADATION_CHAIN_MAX,
    TOOL_USE_MODELS,
    CoderTier,
    TaskType,
)
from .providers.base import CoderChunk, CoderRequest
from .providers.together_provider import TogetherProvider
from .providers.ollama_provider import OllamaProvider
from .providers.anthropic_provider import AnthropicProvider

logger = logging.getLogger(__name__)

# Singletons de providers
_together = TogetherProvider()
_ollama = OllamaProvider()
_anthropic = AnthropicProvider()

_PROVIDERS = [_together, _ollama, _anthropic]


def _get_chain(task_type: TaskType, tier: CoderTier) -> list[str]:
    """Devuelve la cadena de modelos a intentar según tier."""
    if tier == CoderTier.LOCAL:
        return DEGRADATION_CHAIN_LOCAL.get(task_type, ["ollama:agritech"])
    if tier == CoderTier.MAX:
        return DEGRADATION_CHAIN_MAX.get(task_type, DEGRADATION_CHAIN[task_type])
    # auto y balanced usan la cadena estándar
    return DEGRADATION_CHAIN.get(task_type, ["together:qwen3-coder-next"])


def _provider_for(model_id: str):
    """Devuelve el provider que soporta el model_id dado."""
    for p in _PROVIDERS:
        if p.supports_model(model_id):
            return p
    return None


def _filter_by_context(chain: list[str], context_tokens: int) -> list[str]:
    """Elimina modelos cuyo límite de contexto sea insuficiente."""
    filtered = [m for m in chain if CONTEXT_LIMITS.get(m, 32_768) >= context_tokens]
    return filtered if filtered else chain  # si todos fallan, no filtrar


def _filter_by_tools(chain: list[str], needs_tools: bool) -> list[str]:
    """Si el request necesita tools, prioriza los que los soportan."""
    if not needs_tools:
        return chain
    capable = [m for m in chain if m in TOOL_USE_MODELS]
    incapable = [m for m in chain if m not in TOOL_USE_MODELS]
    return capable + incapable


async def choose_model(
    task_type: TaskType,
    tier: CoderTier,
    context_tokens: int = 0,
    needs_tools: bool = False,
    force_model: str | None = None,
) -> str:
    """
    Elige el model_id interno a usar para este request.

    Args:
        task_type: Tipo de tarea clasificado.
        tier: Tier del usuario (auto/local/balanced/max).
        context_tokens: Tokens estimados en el contexto.
        needs_tools: Si el request usa tool_use.
        force_model: Si se especifica X-Seedy-Force-Model, bypasa el router.

    Returns:
        model_id interno (ej: "together:glm-5.1").
    """
    if force_model:
        logger.info(f"[Router] Modelo forzado: {force_model}")
        return force_model

    chain = _get_chain(task_type, tier)
    chain = _filter_by_context(chain, context_tokens)
    chain = _filter_by_tools(chain, needs_tools)

    # Intentar el primer modelo de la cadena (health check rápido)
    for model_id in chain:
        provider = _provider_for(model_id)
        if provider is None:
            continue
        is_healthy = await provider.health_check()
        if is_healthy:
            logger.info(f"[Router] {task_type.value} → {model_id} (tier={tier.value})")
            return model_id
        logger.warning(f"[Router] {model_id} no disponible, degradando...")

    # Último recurso: Ollama local
    logger.warning("[Router] Todos los modelos fallaron, usando ollama:agritech como último recurso")
    return "ollama:agritech"


async def stream_with_fallback(
    req: CoderRequest,
    task_type: TaskType,
    tier: CoderTier,
    budget_degrade: bool = False,
) -> AsyncIterator[tuple[CoderChunk, str]]:
    """
    Genera chunks con fallback automático en caso de error del provider primario.

    Yields:
        (CoderChunk, model_id_used) — model_id para telemetría.
    """
    chain = _get_chain(task_type, tier)
    if budget_degrade:
        chain = ["ollama:agritech"]

    chain = _filter_by_context(chain, _estimate_req_tokens(req))
    chain = _filter_by_tools(chain, bool(req.tools))

    for model_id in chain:
        provider = _provider_for(model_id)
        if provider is None:
            continue
        try:
            req.model_id = model_id
            async for chunk in provider.stream(req):
                yield chunk, model_id
            return  # éxito, salir
        except Exception as exc:
            logger.warning(f"[Router] {model_id} falló durante stream: {exc}. Fallback...")
            continue

    # Si llegamos aquí, todos fallaron
    yield CoderChunk(
        content="// ⚠️ Seedy: todos los providers fallaron. Verifica tu conexión o tier=local.",
        finish_reason="error",
    ), "none"


def _estimate_req_tokens(req: CoderRequest) -> int:
    total = 0
    for m in req.messages:
        content = m.get("content", "") or ""
        total += len(content) // 4
    return total
