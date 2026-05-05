"""
Tests unitarios para LLMRouter v4.6 Providers.
Valida Ollama, Together, y cadena de fallback.
"""

import pytest
import asyncio
import sys
sys.path.insert(0, "/app")

from services.llm_router.providers.ollama_provider import OllamaProvider
from services.llm_router.providers.together_provider import TogetherProvider
from services.llm_router.providers.base import LLMRequest
from services.llm_router.router import LLMRouter
from services.llm_router.policy import POLICIES


# ═══════════════════════════════════════════════════════════════════
# TEST 1: OllamaProvider Health Checks
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ollama_health_checks():
    """Verifica que Ollama está up y modelos disponibles."""
    provider = OllamaProvider(base_url="http://localhost:11434")
    
    # Test health check modelos esperados
    assert await provider.health_check("ollama:qwen2.5-7b"), "qwen2.5:7b debe estar disponible"
    assert await provider.health_check("ollama:seedy-v16"), "seedy:v16 debe estar disponible"
    assert await provider.health_check("ollama:qwen2.5-72b"), "qwen2.5:72b debe estar disponible"
    
    # Test modelo inexistente
    assert not await provider.health_check("ollama:fake-model"), "fake-model no debe existir"


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Ollama Inference Básico
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ollama_inference_qwen7b():
    """Test inference con qwen2.5:7b — modelo rápido."""
    provider = OllamaProvider()
    
    request = LLMRequest(
        model_id="ollama:qwen2.5-7b",
        messages=[{"role": "user", "content": "¿Cuánto es 2+2? Responde solo el número."}],
        max_tokens=10,
    )
    
    result = await provider.complete(request)
    
    assert "4" in result.content, f"Respuesta incorrecta: {result.content}"
    assert result.prompt_tokens > 0, "Debe contar tokens de prompt"
    assert result.completion_tokens > 0, "Debe contar tokens de completion"
    assert result.first_token_latency_s > 0, "Debe medir latencia primer token"
    assert result.total_latency_s < 10.0, "qwen2.5:7b debe responder en <10s"
    print(f"✅ Ollama qwen2.5:7b inference OK: {result.total_latency_s:.2f}s, {result.completion_tokens} tokens")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Together Provider Health
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_together_health():
    """Verifica que Together API está accesible."""
    provider = TogetherProvider()
    
    # Health check simplificado (solo verificar que API responde)
    is_healthy = await provider.health_check("together:qwen2.5-7b-turbo")
    assert is_healthy, "Together API debe estar disponible"


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Router con Policy (rewriter)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_router_rewriter_policy():
    """Test del router completo con policy de rewriter."""
    router = LLMRouter()
    policy = POLICIES["rewriter"]
    
    request = LLMRequest(
        messages=[
            {"role": "system", "content": "Eres un asistente que reescribe preguntas de forma clara."},
            {"role": "user", "content": "Reformula: ¿Cómo hago para que las gallinas pongan más?"}
        ],
        max_tokens=80,
    )
    
    result = await router.call_with_policy(policy, request, mode="test")
    
    assert len(result.content) > 10, f"Respuesta muy corta: {result.content}"
    assert result.model_id.startswith("ollama:"), f"Debe usar Ollama primario: {result.model_id}"
    assert result.total_latency_s < policy.max_latency_s, f"Excede latency policy: {result.total_latency_s}s"
    print(f"✅ Router rewriter OK: {result.model_id}, {result.total_latency_s:.2f}s")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Coste estimado (Together vs Ollama)
# ═══════════════════════════════════════════════════════════════════

def test_cost_estimation():
    """Verifica cálculo de costes."""
    ollama = OllamaProvider()
    together = TogetherProvider()
    
    # Ollama debe ser gratis
    assert ollama.estimate_cost("ollama:qwen2.5-7b", 1000, 500) == 0.0
    
    # Together debe cobrar según pricing
    cost_7b = together.estimate_cost("together:qwen2.5-7b-turbo", 1000, 500)
    assert cost_7b > 0, "Together debe tener coste"
    assert cost_7b < 0.001, "Coste 7B debe ser bajo (<$0.001)"
    
    cost_235b = together.estimate_cost("together:qwen3-235b-tput", 1000, 500)
    assert cost_235b > cost_7b, "235B debe costar más que 7B"
    
    print(f"✅ Coste 7B: ${cost_7b:.6f}, 235B: ${cost_235b:.6f}")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Fallback Automático (simulado)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fallback_mechanism():
    """Test que router escala a fallback si primario falla."""
    router = LLMRouter()
    
    # Crear policy que intenta modelo inexistente → debe caer a fallback
    from services.llm_router.policy import StepPolicy
    
    fake_policy = StepPolicy(
        name="test_fallback",
        primary="ollama:nonexistent-model",  # No existe
        fallback=["ollama:seedy-v16"],        # Fallback válido
        max_latency_s=10.0,
        requires_user=True,
    )
    
    request = LLMRequest(
        messages=[{"role": "user", "content": "Di 'hola'"}],
        max_tokens=10,
    )
    
    result = await router.call_with_policy(fake_policy, request, mode="test")
    
    assert result.model_id == "ollama:seedy-v16", f"Debe usar fallback: {result.model_id}"
    print(f"✅ Fallback mechanism OK: escaló a {result.model_id}")


# ═══════════════════════════════════════════════════════════════════
# RUN MANUAL (para ejecutar fuera de pytest)
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧪 Running LLMRouter v4.6 Unit Tests\n")
    
    async def run_tests():
        print("TEST 1: Ollama health checks...")
        await test_ollama_health_checks()
        
        print("\nTEST 2: Ollama inference qwen2.5:7b...")
        await test_ollama_inference_qwen7b()
        
        print("\nTEST 3: Together API health...")
        await test_together_health()
        
        print("\nTEST 4: Router rewriter policy...")
        await test_router_rewriter_policy()
        
        print("\nTEST 5: Cost estimation...")
        test_cost_estimation()
        
        print("\nTEST 6: Fallback mechanism...")
        await test_fallback_mechanism()
        
        print("\n✅ ALL TESTS PASSED")
    
    asyncio.run(run_tests())
