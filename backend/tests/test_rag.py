"""Seedy Backend — Tests de diagnóstico RAG."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rag import search
from services.reranker import rerank


TESTS = [
    {
        "name": "Test 1: BOM/nave PorciData",
        "query": "¿cuánto cuesta el BOM de PorciData por nave?",
        "collections": ["iot_hardware"],
        "expected_keywords": ["1.420", "EUR", "nave"],
    },
    {
        "name": "Test 2: Capa acústica",
        "query": "¿qué sensor usa la capa acústica de PorciData?",
        "collections": ["iot_hardware"],
        "expected_keywords": ["INMP441", "ESP32"],
    },
    {
        "name": "Test 3: Butirato e inmunidad",
        "query": "¿cómo mejora el butirato sódico la inmunidad intestinal?",
        "collections": ["nutricion"],
        "expected_keywords": ["IgA", "tight junction"],
    },
    {
        "name": "Test 4: 11 planes SIGE",
        "query": "¿cuáles son los 11 planes del SIGE según el RD 306/2020?",
        "collections": ["normativa"],
        "expected_keywords": ["bioseguridad", "bienestar"],
    },
]


async def run_tests():
    print("\n" + "=" * 60)
    print("🧪 TESTS DE DIAGNÓSTICO RAG")
    print("=" * 60)

    passed = 0
    total = len(TESTS)

    for test in TESTS:
        print(f"\n📋 {test['name']}")
        print(f"   Query: {test['query']}")

        try:
            results = await search(test["query"], test["collections"], top_k=8)

            if not results:
                print(f"   ❌ FAIL — Sin resultados RAG")
                continue

            # Rerank
            top = rerank(test["query"], results, top_n=3)

            # Verificar keywords en los chunks
            all_text = " ".join(r["text"].lower() for r in top)
            found = [kw for kw in test["expected_keywords"] if kw.lower() in all_text]
            missing = [kw for kw in test["expected_keywords"] if kw.lower() not in all_text]

            if len(found) >= len(test["expected_keywords"]) * 0.5:
                print(f"   ✅ PASS — Keywords encontradas: {found}")
                passed += 1
            else:
                print(f"   ⚠️  PARCIAL — Encontradas: {found}, Faltan: {missing}")

            # Mostrar top chunk
            if top:
                print(f"   Top chunk [{top[0]['collection']}]: {top[0]['text'][:120]}...")

        except Exception as e:
            print(f"   ❌ ERROR — {e}")

    print(f"\n{'=' * 60}")
    print(f"Resultado: {passed}/{total} tests pasados")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
