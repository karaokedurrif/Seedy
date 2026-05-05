"""
LLM Router — Dispatcher central con fallback automático y health checks.
Core del sistema híbrido Together + Ollama.
"""

import asyncio
import logging
from typing import Dict, Optional
from .policy import StepPolicy, POLICIES
from .providers.base import LLMProvider, LLMRequest, LLMResult
from .providers.ollama_provider import OllamaProvider
from .providers.together_provider import TogetherProvider
from .budget_guard import get_budget_guard
from .usage_tracker import track_usage_influx, track_error_influx

log = logging.getLogger(__name__)


class LLMRouter:
    """
    Router inteligente que elige provider según policy, con fallback automático.
    
    Flow:
    1. Recibe StepPolicy + LLMRequest
    2. Intenta primary model
    3. Si falla (timeout/error/unhealthy), intenta fallbacks en orden
    4. Registra telemetría y coste
    5. Devuelve LLMResult o lanza exception si todos fallan
    """
    
    def __init__(
        self,
        ollama_base_url: str = "http://ollama:11434",  # Nombre servicio Docker
        together_api_key: Optional[str] = None,
    ):
        self.providers: Dict[str, LLMProvider] = {
            "ollama": OllamaProvider(base_url=ollama_base_url),
            "together": TogetherProvider(api_key=together_api_key),
        }
        self.budget = get_budget_guard()
    
    async def call_with_policy(
        self,
        policy: StepPolicy,
        request: LLMRequest,
        mode: str = "default",
    ) -> LLMResult:
        """
        Ejecuta request según policy, con cadena de fallback automática.
        
        Args:
            policy: StepPolicy con primary + fallbacks
            request: LLMRequest con messages, etc
            mode: Modo de generación (default|think|local|deep|eco)
        
        Returns:
            LLMResult con contenido + tokens + latencias
        
        Raises:
            RuntimeError: Si todos los providers fallan
        """
        candidates = [policy.primary, *policy.fallback]
        last_error = None
        
        for model_id in candidates:
            provider_name = model_id.split(":")[0]  # "ollama" | "together"
            provider = self.providers.get(provider_name)
            
            if not provider:
                log.warning(f"Unknown provider: {provider_name} for {model_id}")
                continue
            
            # Skip si provider no soporta el modelo
            if not provider.supports_model(model_id):
                log.warning(f"Provider {provider_name} doesn't support {model_id}")
                continue
            
            # Skip si no está sano
            is_healthy = await provider.health_check(model_id)
            if not is_healthy:
                log.warning(f"provider.unhealthy | {model_id} | step={policy.name}")
                track_error_influx(policy.name, model_id, "unhealthy", mode)
                continue
            
            # Skip Together si presupuesto agotado
            if provider_name == "together" and self.budget.is_capped():
                log.warning(
                    f"provider.budget_capped | {model_id} | step={policy.name} | "
                    f"daily=${self.budget.usage_today():.2f}"
                )
                track_error_influx(policy.name, model_id, "budget_capped", mode)
                continue
            
            # Intentar llamada
            try:
                request.model_id = model_id
                
                # Wrap con timeout = max_latency_s para detectar primer-token lento
                result = await asyncio.wait_for(
                    provider.complete(request),
                    timeout=policy.max_latency_s + 5.0,  # +5s buffer para overhead
                )
                
                # Telemetría + Budget
                cost = provider.estimate_cost(model_id, result.prompt_tokens, result.completion_tokens)
                result.cost = cost  # Añadir coste al resultado
                self.budget.record(model_id, cost)
                track_usage_influx(policy.name, model_id, result, cost, status="ok", mode=mode)
                
                log.info(
                    f"llm.call.ok | step={policy.name} | model={model_id} | "
                    f"latency={result.total_latency_s:.2f}s | cost=${cost:.4f} | "
                    f"tokens={result.prompt_tokens}+{result.completion_tokens}"
                )
                
                return result
            
            except asyncio.TimeoutError:
                log.warning(
                    f"llm.call.timeout | step={policy.name} | model={model_id} | "
                    f"timeout={policy.max_latency_s}s"
                )
                track_error_influx(policy.name, model_id, "timeout", mode)
                last_error = "timeout"
                continue
            
            except Exception as exc:
                log.exception(
                    f"llm.call.error | step={policy.name} | model={model_id} | error={exc}"
                )
                track_error_influx(policy.name, model_id, "error", mode)
                last_error = str(exc)
                continue
        
        # Todos los candidatos fallaron
        raise RuntimeError(
            f"All providers failed for step {policy.name}. "
            f"Candidates: {candidates}. Last error: {last_error}"
        )
    
    async def get_health_status(self) -> Dict:
        """Devuelve estado de salud de todos los providers."""
        status = {}
        
        for provider_name, provider in self.providers.items():
            # Test con un modelo representativo
            test_models = {
                "ollama": "ollama:seedy-v16",
                "together": "together:qwen2.5-7b-turbo",
            }
            
            test_model = test_models.get(provider_name, "")
            if test_model:
                is_healthy = await provider.health_check(test_model)
                status[provider_name] = {
                    "healthy": is_healthy,
                    "test_model": test_model,
                }
            else:
                status[provider_name] = {"healthy": False, "reason": "no_test_model"}
        
        return status


# Singleton global
_llm_router = None


def get_llm_router() -> LLMRouter:
    """Obtiene instancia singleton del LLMRouter."""
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router


# Export conveniente
llm_router = get_llm_router()
