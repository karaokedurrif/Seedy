"""Seedy Backend — Tests del clasificador."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.classifier import classify_query


TESTS = [
    ("¿cuánto cuesta el BOM de PorciData?", ["IOT", "RAG"]),
    ("¿qué es el butirato sódico?", ["NUTRITION", "RAG"]),
    ("¿cómo calculo la consanguinidad de Wright?", ["GENETICS", "RAG"]),
    ("¿cuáles son los 11 planes del SIGE?", ["NORMATIVA", "RAG"]),
    ("¿qué es un digital twin en porcino?", ["TWIN", "RAG"]),
    ("hola, ¿qué puedes hacer?", ["GENERAL"]),
]


async def run_tests():
    print("\n" + "=" * 60)
    print("🧪 TESTS DEL CLASIFICADOR")
    print("=" * 60)

    passed = 0

    for query, expected_cats in TESTS:
        category = await classify_query(query)
        ok = category in expected_cats
        status = "✅" if ok else "❌"
        print(f"  {status} '{query[:50]}...' → {category} (esperado: {expected_cats})")
        if ok:
            passed += 1

    print(f"\nResultado: {passed}/{len(TESTS)} tests pasados")
    print("=" * 60)

    return passed == len(TESTS)


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
