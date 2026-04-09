"""Seedy Backend — Gold Capture: feedback loop 70B → 14B.

Captura respuestas de alta calidad del 70B para re-entrenar el 14B vía SFT/DPO.

Tres modos de captura:

1. **Regeneración on-block**: Cuando el critic bloquea al 14B, regenera con
   70B (Together) y guarda la respuesta gold como "chosen" en el par DPO
   (en vez del fallback genérico inútil "No puedo darte respuesta fiable").

2. **INFORME gold**: Cada respuesta del 70B que pasa el critic de informes
   se guarda como ejemplo SFT positivo (son las mejores respuestas del sistema).

3. **Expert snapshot**: Cada N respuestas gold, exporta un JSONL listo para
   fine-tune con Together.ai.

Formato SFT: {"messages": [{"role":"system","content":"..."}, {"role":"user","content":"..."}, {"role":"assistant","content":"..."}]}
Formato DPO: {"prompt":"...", "chosen":"...", "rejected":"...", "metadata":{...}}
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio de datos
_DATA_DIR = Path("/app/data") if Path("/app/data").exists() else Path("data")
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_GOLD_SFT_FILE = _DATA_DIR / "gold_sft.jsonl"
_GOLD_DPO_FILE = _DATA_DIR / "gold_dpo.jsonl"  # Reemplaza el dpo_pairs.jsonl inútil

# Stats en memoria
_stats = {
    "regenerations": 0,
    "regen_success": 0,
    "regen_failed": 0,
    "informe_captured": 0,
    "sft_total": 0,
    "dpo_total": 0,
}

# System prompt SFT (el mismo del fine-tune v16, para consistencia)
_SFT_SYSTEM = (
    "Eres Seedy, un asistente experto en ganadería de precisión, avicultura extensiva, "
    "genética animal, IoT agropecuario y normativa ganadera española. "
    "Respondes siempre en español con datos concretos y verificables."
)


async def regenerate_on_block(
    query: str,
    system_prompt: str,
    blocked_draft: str,
    top_chunks: list[dict],
    history: list[dict] | None,
    category: str,
    species_hint: str | None,
    block_reasons: list[str],
) -> str | None:
    """
    Regenera una respuesta bloqueada usando el modelo brain (DeepSeek-R1).

    Si el brain genera una respuesta válida (>200 chars, no genérica),
    la guarda como par DPO (chosen=brain gold, rejected=draft bloqueado)
    Y como ejemplo SFT positivo.

    Returns:
        Respuesta gold del brain, o None si falla/es insuficiente.
    """
    from services.llm import generate_report
    from services.evidence import deduplicate_chunks, build_evidence_context

    _stats["regenerations"] += 1
    t0 = time.time()

    try:
        filtered_chunks = deduplicate_chunks(top_chunks)

        # Construir contexto enriquecido para el 70B
        regen_hint = (
            "CONTEXTO: El modelo anterior generó una respuesta que fue bloqueada "
            f"por estas razones: {'; '.join(block_reasons)}. "
            "Tu tarea es generar una respuesta CORRECTA, específica y basada "
            "exclusivamente en la evidencia proporcionada. "
            "Si la evidencia es insuficiente, di exactamente qué falta y qué sí puedes afirmar."
        )

        # Construir evidence context con los chunks
        evidence_parts = []
        for i, chunk in enumerate(filtered_chunks[:10], 1):
            source = chunk.get("file", chunk.get("source_file", "desconocido"))
            text = chunk.get("text", "")[:1500]
            evidence_parts.append(f"[F{i}: {source}]\n{text}")

        evidence_context = (
            f"{regen_hint}\n\n"
            "EVIDENCIA DISPONIBLE:\n" + "\n\n".join(evidence_parts)
        )

        answer, model_used = await generate_report(
            system_prompt=system_prompt,
            user_message=query,
            context_chunks=filtered_chunks,
            history=history,
            max_tokens=2048,
            temperature=0.4,
            evidence_override=evidence_context,
        )

        elapsed = time.time() - t0

        # Validar calidad mínima de la respuesta del 70B
        if not answer or len(answer) < 200:
            logger.warning(
                f"[GoldCapture] Regeneración corta ({len(answer or '')} chars) — descartada"
            )
            _stats["regen_failed"] += 1
            return None

        # Verificar que no sea el fallback genérico
        if "No puedo darte una respuesta fiable" in answer:
            logger.warning("[GoldCapture] Brain devolvió fallback genérico — descartada")
            _stats["regen_failed"] += 1
            return None

        _stats["regen_success"] += 1
        logger.info(
            f"[GoldCapture] 70B regeneró OK: {len(answer)} chars en {elapsed:.1f}s "
            f"(cat={category})"
        )

        # Guardar par DPO: chosen=70B gold, rejected=14B draft bloqueado
        _save_dpo_pair(
            query=query,
            chosen=answer,
            rejected=blocked_draft,
            category=category,
            species_hint=species_hint,
            block_reasons=block_reasons,
            source="regen_on_block",
        )

        # Guardar como ejemplo SFT positivo
        _save_sft_example(
            query=query,
            answer=answer,
            category=category,
            source="regen_on_block",
        )

        return answer

    except Exception as e:
        logger.error(f"[GoldCapture] Error en regeneración: {e}", exc_info=True)
        _stats["regen_failed"] += 1
        return None


def capture_informe_gold(
    query: str,
    answer: str,
    category: str,
):
    """
    Captura una respuesta de INFORME del 70B como ejemplo SFT.
    Solo si supera calidad mínima (>1000 chars, tiene estructura).
    """
    if not answer or len(answer) < 1000:
        return

    # Verificar estructura mínima de informe (headers, listas, datos)
    has_headers = answer.count("#") >= 2 or answer.count("**") >= 3
    has_data = any(c.isdigit() for c in answer[:500])

    if not has_headers:
        logger.debug("[GoldCapture] Informe sin estructura — no capturado")
        return

    _stats["informe_captured"] += 1
    _save_sft_example(
        query=query,
        answer=answer,
        category=category,
        source="informe_70b",
    )
    logger.info(
        f"[GoldCapture] Informe capturado: {len(answer)} chars (cat={category})"
    )


def _save_sft_example(
    query: str,
    answer: str,
    category: str,
    source: str,
):
    """Guarda un ejemplo SFT en formato Together.ai."""
    example = {
        "messages": [
            {"role": "system", "content": _SFT_SYSTEM},
            {"role": "user", "content": query},
            {"role": "assistant", "content": answer},
        ],
        "metadata": {
            "category": category,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "answer_length": len(answer),
        },
    }

    try:
        with open(_GOLD_SFT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
        _stats["sft_total"] += 1
    except Exception as e:
        logger.error(f"[GoldCapture] Error escribiendo SFT: {e}")


def _save_dpo_pair(
    query: str,
    chosen: str,
    rejected: str,
    category: str,
    species_hint: str | None,
    block_reasons: list[str],
    source: str,
):
    """Guarda un par DPO con respuesta gold real (no fallback genérico)."""
    pair = {
        "prompt": query,
        "chosen": chosen,
        "rejected": rejected,
        "metadata": {
            "category": category,
            "species": species_hint,
            "block_reasons": block_reasons,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        with open(_GOLD_DPO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        _stats["dpo_total"] += 1
    except Exception as e:
        logger.error(f"[GoldCapture] Error escribiendo DPO: {e}")


def export_sft_dataset(output_path: str | None = None) -> dict:
    """
    Exporta el dataset SFT gold acumulado.

    Returns:
        {"path": str, "count": int, "categories": dict}
    """
    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = str(_DATA_DIR / f"gold_sft_export_{ts}.jsonl")

    if not _GOLD_SFT_FILE.exists():
        return {"path": output_path, "count": 0, "categories": {}}

    categories: dict[str, int] = {}
    count = 0

    with open(_GOLD_SFT_FILE, encoding="utf-8") as src:
        with open(output_path, "w", encoding="utf-8") as dst:
            for line in src:
                try:
                    example = json.loads(line)
                    # Exportar solo messages (formato Together.ai SFT)
                    sft_line = {"messages": example["messages"]}
                    dst.write(json.dumps(sft_line, ensure_ascii=False) + "\n")

                    cat = example.get("metadata", {}).get("category", "unknown")
                    categories[cat] = categories.get(cat, 0) + 1
                    count += 1
                except json.JSONDecodeError:
                    continue

    logger.info(f"[GoldCapture] Exportado: {count} ejemplos SFT → {output_path}")
    return {"path": output_path, "count": count, "categories": categories}


def get_stats() -> dict:
    """Estadísticas del gold capture."""
    return {
        **_stats,
        "sft_file_exists": _GOLD_SFT_FILE.exists(),
        "dpo_file_exists": _GOLD_DPO_FILE.exists(),
    }
