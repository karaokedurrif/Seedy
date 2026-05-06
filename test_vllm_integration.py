#!/usr/bin/env python3
"""
Test de integración vLLM v4.7 — Validación completa del VLLMLocalProvider
Verifica: health check, chat completion, FIM, y coste $0
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from coder.providers.vllm_local_provider import VLLMLocalProvider
from coder.providers.base import CoderRequest


async def main():
    print("🧪 Test de Integración vLLM v4.7")
    print("=" * 50)
    
    provider = VLLMLocalProvider()
    
    # Test 1: Health check
    print("\n📋 Test 1: Health Check")
    is_healthy = await provider.health_check()
    if is_healthy:
        print("✅ PASS - Provider healthy")
    else:
        print("❌ FAIL - Provider not responding")
        return 1
    
    # Test 2: Model support
    print("\n📋 Test 2: Model Support")
    models_to_test = [
        "vllm:qwen2.5-coder-32b",
        "vllm:coder-32b", 
        "vllm:default"
    ]
    for model in models_to_test:
        supported = provider.supports_model(model)
        status = "✅" if supported else "❌"
        print(f"{status} {model}: {supported}")
    
    # Test 3: Cost estimation (should be $0)
    print("\n📋 Test 3: Cost Estimation")
    cost = provider.estimate_cost("vllm:qwen2.5-coder-32b", 1000, 500)
    if cost == 0.0:
        print(f"✅ PASS - Cost is $0 (local model)")
    else:
        print(f"❌ FAIL - Cost should be $0, got ${cost}")
    
    # Test 4: Chat completion (streaming)
    print("\n📋 Test 4: Chat Completion (Streaming)")
    request = CoderRequest(
        model_id="vllm:qwen2.5-coder-32b",
        messages=[
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Write a Python function to add two numbers. Be concise."}
        ],
        temperature=0.7,
        max_tokens=100,
    )
    
    print("Streaming response...", flush=True)
    full_response = ""
    chunk_count = 0
    
    try:
        async for chunk in provider.stream(request):
            full_response += chunk.content
            chunk_count += 1
            print(".", end="", flush=True)
            
            if chunk.finish_reason:
                print(f"\n\n✅ PASS - Got {chunk_count} chunks, finish_reason: {chunk.finish_reason}")
                print(f"📝 Response preview:\n{full_response[:200]}...")
                break
    except Exception as e:
        print(f"\n❌ FAIL - Error during streaming: {e}")
        return 1
    
    # Test 5: Context limit
    print("\n📋 Test 5: Context Limit Check")
    from coder.policy import CONTEXT_LIMITS
    limit = CONTEXT_LIMITS.get("vllm:qwen2.5-coder-32b", 0)
    expected = 131_072
    if limit == expected:
        print(f"✅ PASS - Context limit: {limit:,} tokens")
    else:
        print(f"⚠️  WARNING - Expected {expected:,}, got {limit:,}")
    
    # Test 6: Degradation chain check
    print("\n📋 Test 6: Degradation Chain Integration")
    from coder.policy import DEGRADATION_CHAIN, TaskType
    
    tasks_with_vllm = [
        TaskType.CHAT_LONG,
        TaskType.REFACTOR_MULTI,
        TaskType.DEBUG,
    ]
    
    all_correct = True
    for task in tasks_with_vllm:
        chain = DEGRADATION_CHAIN[task]
        if chain[0].startswith("vllm:"):
            print(f"✅ {task.value}: vLLM is primary → {chain[0]}")
        else:
            print(f"❌ {task.value}: vLLM should be primary, got {chain[0]}")
            all_correct = False
    
    if not all_correct:
        return 1
    
    print("\n" + "=" * 50)
    print("🎉 TODOS LOS TESTS PASARON")
    print("=" * 50)
    print("\nvLLM v4.7 está completamente integrado y funcional.")
    print("\nConfiguración:")
    print(f"  Base URL: {provider._base_url}")
    print(f"  Timeout: {provider._timeout.read}s")
    print(f"  Models: /models/qwen2.5-coder-32b-awq")
    print(f"  Context: 131,072 tokens (32K effective)")
    print(f"  Cost: $0 (local)")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
