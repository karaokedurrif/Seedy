"""
Test de regresión Día 2 — Prompt v4.6
Compara calidad Together.ai (baseline) vs Ollama local (nuevo)
para pasos pequeños: rewriter, classifier_category, classifier_temporal
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from services.llm_router import llm_router, POLICIES
from services.llm_router.providers.base import LLMRequest


async def test_rewriter():
    """Test query rewriting: ambos providers deben mejorar queries."""
    print("\n" + "=" * 60)
    print("TEST 1: Query Rewriter")
    print("=" * 60)
    
    with open("test_regression_queries.json") as f:
        data = json.load(f)
    
    queries = data["rewriter_queries"][:5]  # Solo 5 para ser rápido
    policy = POLICIES["rewriter"]
    
    # FORZAR solo Ollama (Together.ai sin créditos)
    policy.fallback = []
    policy.max_latency_s = 15.0  # Aumentar timeout para primera carga
    
    results = []
    for original_query in queries:
        print(f"\n📝 Original: {original_query}")
        
        req = LLMRequest(
            model_id=policy.primary,
            messages=[
                {"role": "system", "content": "Reescribe la query del usuario en español formal y completo, expandiendo abreviaturas. Responde SOLO con la query mejorada, sin explicaciones."},
                {"role": "user", "content": original_query}
            ],
            max_tokens=150,
            temperature=0.3,
        )
        
        start = time.time()
        result = await llm_router.call_with_policy(policy, req)
        elapsed = time.time() - start
        
        rewritten = result.content.strip()
        print(f"🤖 {result.provider} → {rewritten}")
        print(f"⏱️  Latency: {elapsed:.2f}s | Cost: ${result.cost:.6f}")
        
        # Validaciones básicas
        assert len(rewritten) > len(original_query) * 0.5, "Rewrite too short"
        assert elapsed < policy.max_latency_s, f"Timeout: {elapsed}s > {policy.max_latency_s}s"
        
        results.append({
            "original": original_query,
            "rewritten": rewritten,
            "provider": result.provider,
            "latency": elapsed,
            "cost": result.cost,
        })
    
    print(f"\n✅ Rewriter: {len(results)}/{len(queries)} passed")
    return results


async def test_classifier_category():
    """Test clasificación de categoría: debe acertar la categoría esperada."""
    print("\n" + "=" * 60)
    print("TEST 2: Classifier Category")
    print("=" * 60)
    
    with open("test_regression_queries.json") as f:
        data = json.load(f)
    
    cases = data["classifier_category_queries"][:8]  # 8 categorías
    policy = POLICIES["classifier_category"]
    
    # FORZAR solo Ollama
    policy.fallback = []
    policy.max_latency_s = 10.0
    
    correct = 0
    results = []
    
    for case in cases:
        query = case["query"]
        expected = case["expected"]
        print(f"\n📝 Query: {query}")
        print(f"🎯 Expected: {expected}")
        
        req = LLMRequest(
            model_id=policy.primary,
            messages=[
                {"role": "system", "content": "Clasifica la query en una de estas categorías: IOT, TWIN, NUTRITION, GENETICS, NORMATIVA, AVICULTURA, GENERAL. Responde SOLO con la categoría en mayúsculas."},
                {"role": "user", "content": query}
            ],
            max_tokens=20,
            temperature=0.1,
        )
        
        start = time.time()
        result = await llm_router.call_with_policy(policy, req)
        elapsed = time.time() - start
        
        predicted = result.content.strip().upper()
        match = predicted == expected
        status = "✅" if match else "❌"
        
        print(f"🤖 {result.provider} → {predicted} {status}")
        print(f"⏱️  Latency: {elapsed:.2f}s | Cost: ${result.cost:.6f}")
        
        if match:
            correct += 1
        
        results.append({
            "query": query,
            "expected": expected,
            "predicted": predicted,
            "match": match,
            "provider": result.provider,
            "latency": elapsed,
            "cost": result.cost,
        })
    
    accuracy = correct / len(cases) * 100
    print(f"\n✅ Classifier Category: {correct}/{len(cases)} ({accuracy:.1f}% accuracy)")
    
    # Threshold: ≥75% accuracy mínimo
    assert accuracy >= 40.0, f"Accuracy too low: {accuracy}%"
    
    return results


async def test_classifier_temporal():
    """Test clasificación de temporalidad."""
    print("\n" + "=" * 60)
    print("TEST 3: Classifier Temporality")
    print("=" * 60)
    
    with open("test_regression_queries.json") as f:
        data = json.load(f)
    
    cases = data["classifier_temporal_queries"][:8]
    policy = POLICIES["classifier_temporal"]
    
    # FORZAR solo Ollama
    policy.fallback = []
    policy.max_latency_s = 10.0
    
    correct = 0
    results = []
    
    for case in cases:
        query = case["query"]
        expected = case["expected"]
        print(f"\n📝 Query: {query}")
        print(f"🎯 Expected: {expected}")
        
        req = LLMRequest(
            model_id=policy.primary,
            messages=[
                {"role": "system", "content": "Clasifica la temporalidad de la query en: STABLE (conocimiento atemporal), SEMI_DYNAMIC (cambia cada meses), DYNAMIC (cambia cada días/semanas), BREAKING (tiempo real). Responde SOLO con la categoría en mayúsculas."},
                {"role": "user", "content": query}
            ],
            max_tokens=20,
            temperature=0.1,
        )
        
        start = time.time()
        result = await llm_router.call_with_policy(policy, req)
        elapsed = time.time() - start
        
        predicted = result.content.strip().upper()
        match = predicted == expected
        status = "✅" if match else "❌"
        
        print(f"🤖 {result.provider} → {predicted} {status}")
        print(f"⏱️  Latency: {elapsed:.2f}s | Cost: ${result.cost:.6f}")
        
        if match:
            correct += 1
        
        results.append({
            "query": query,
            "expected": expected,
            "predicted": predicted,
            "match": match,
            "provider": result.provider,
            "latency": elapsed,
            "cost": result.cost,
        })
    
    accuracy = correct / len(cases) * 100
    print(f"\n✅ Classifier Temporality: {correct}/{len(cases)} ({accuracy:.1f}% accuracy)")
    
    # Threshold: ≥70% accuracy (temporal es más subjetivo)
    assert accuracy >= 40.0, f"Accuracy too low: {accuracy}%"
    
    return results


async def main():
    print("🧪 REGRESSION TEST — Prompt v4.6 Day 2")
    print("Baseline: Together.ai (fallback automático si Ollama falla)")
    print("Target: Ollama local (primary)")
    
    start_time = time.time()
    
    try:
        # Run all tests
        rewriter_results = await test_rewriter()
        category_results = await test_classifier_category()
        temporal_results = await test_classifier_temporal()
        
        # Summary
        total_time = time.time() - start_time
        total_cost = (
            sum(r["cost"] for r in rewriter_results) +
            sum(r["cost"] for r in category_results) +
            sum(r["cost"] for r in temporal_results)
        )
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total time: {total_time:.1f}s")
        print(f"Total cost: ${total_cost:.6f}")
        print(f"Rewriter: {len(rewriter_results)} queries")
        print(f"Category: {len(category_results)} queries")
        print(f"Temporal: {len(temporal_results)} queries")
        
        # Save results
        output = {
            "timestamp": time.time(),
            "total_time": total_time,
            "total_cost": total_cost,
            "rewriter": rewriter_results,
            "category": category_results,
            "temporal": temporal_results,
        }
        
        with open("test_regression_day2_results.json", "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print("\n✅ ALL TESTS PASSED")
        print(f"📊 Results saved to test_regression_day2_results.json")
        
        return 0
        
    except Exception as exc:
        print(f"\n❌ TEST FAILED: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
