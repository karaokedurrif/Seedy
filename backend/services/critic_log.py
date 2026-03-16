"""Seedy Backend — Critic Log para dataset DPO (Fase 2 v14).

Guarda cada evaluación del critic (estructural y técnico) con contexto completo.
Los bloqueos se convierten en pares negativos para DPO:
  - chosen: respuesta corregida (fallback) o futura respuesta mejorada
  - rejected: el draft que fue bloqueado

Los PASS se guardan como pares positivos (para contrastar).

Formato: JSONL en /app/data/critic_log.jsonl (o data/ en desarrollo).
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Directorio para logs (dentro del contenedor: /app/data, dev: ./data)
_LOG_DIR = Path("/app/data")
if not _LOG_DIR.exists():
    _LOG_DIR = Path("data")
    _LOG_DIR.mkdir(exist_ok=True)

_LOG_FILE = _LOG_DIR / "critic_log.jsonl"
_DPO_FILE = _LOG_DIR / "dpo_pairs.jsonl"

# Contador en memoria
_stats = {"pass": 0, "block_structural": 0, "block_technical": 0, "total": 0}


def log_critic_result(
    query: str,
    evidence_summary: str,
    draft_answer: str,
    structural_verdict: dict,
    technical_verdict: dict | None = None,
    final_answer: str | None = None,
    category: str = "",
    species_hint: str | None = None,
    latency_ms: int = 0,
):
    """
    Registra el resultado del critic en el log.

    Args:
        query: pregunta del usuario
        evidence_summary: evidencia usada (≤2000 chars)
        draft_answer: respuesta draft del LLM
        structural_verdict: resultado del critic estructural
        technical_verdict: resultado del critic técnico (puede ser None)
        final_answer: respuesta final enviada al usuario
        category: categoría clasificada
        species_hint: especie detectada
        latency_ms: latencia total del pipeline
    """
    _stats["total"] += 1

    # Determinar veredicto final
    s_verdict = structural_verdict.get("verdict", "PASS")
    t_verdict = (technical_verdict or {}).get("verdict", "PASS")
    was_blocked = s_verdict == "BLOCK" or t_verdict == "BLOCK"

    if was_blocked:
        block_source = "structural" if s_verdict == "BLOCK" else "technical"
        _stats[f"block_{block_source}"] += 1
    else:
        _stats["pass"] += 1

    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "query": query,
        "category": category,
        "species_hint": species_hint,
        "evidence": evidence_summary[:2000],
        "draft": draft_answer,
        "final": final_answer or draft_answer,
        "structural": structural_verdict,
        "technical": technical_verdict,
        "blocked": was_blocked,
        "block_source": block_source if was_blocked else None,
        "latency_ms": latency_ms,
    }

    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"[CriticLog] Error escribiendo log: {e}")

    # Si fue bloqueado, generar par DPO
    if was_blocked:
        _write_dpo_pair(record)

    # Log periódico de stats
    if _stats["total"] % 50 == 0:
        logger.info(
            f"[CriticLog] Stats: {_stats['total']} total, "
            f"{_stats['pass']} pass, "
            f"{_stats['block_structural']} block_struct, "
            f"{_stats['block_technical']} block_tech"
        )


def _write_dpo_pair(record: dict):
    """
    Genera un par DPO a partir de un bloqueo.
    Formato compatible con TRL DPOTrainer.
    """
    dpo_pair = {
        "prompt": record["query"],
        "chosen": record["final"],  # El fallback (correcto, aunque genérico)
        "rejected": record["draft"],  # El draft bloqueado (incorrecto)
        "metadata": {
            "category": record["category"],
            "species": record["species_hint"],
            "block_source": record["block_source"],
            "reasons": (
                record.get("structural", {}).get("reasons", [])
                + record.get("technical", {}).get("reasons", [])
            ),
            "timestamp": record["timestamp"],
        },
    }

    try:
        with open(_DPO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(dpo_pair, ensure_ascii=False) + "\n")
        logger.info(f"[CriticLog] Par DPO guardado (block={record['block_source']})")
    except Exception as e:
        logger.error(f"[CriticLog] Error escribiendo DPO pair: {e}")


def get_stats() -> dict:
    """Devuelve estadísticas acumuladas del critic."""
    return dict(_stats)


def get_log_path() -> str:
    """Devuelve la ruta del archivo de log."""
    return str(_LOG_FILE)


def get_dpo_path() -> str:
    """Devuelve la ruta del archivo DPO."""
    return str(_DPO_FILE)
