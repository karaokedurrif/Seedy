"""Seedy Backend — Behavior Serializer

Convierte BehaviorInference a texto compacto para inyectar en prompts RAG
y a JSON para endpoints API.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from services.behavior_inference import BehaviorInference, InferenceResult


def to_rag_chunk(inference: BehaviorInference) -> str:
    """Convierte inferencia a texto en español (~200-400 palabras).

    Formato: resumen → señales → inferencias → anomalías → limitaciones.
    Optimizado para bge-reranker-v2-m3 (no superar 400 tokens).
    """
    lines = []
    lines.append(f"## Análisis conductual: {inference.bird_id}")
    lines.append(f"Ventana: {inference.time_window} | "
                 f"Completitud datos: {inference.data_completeness:.0%}")
    lines.append("")

    # Observaciones
    if inference.observations:
        lines.append("**Observaciones:**")
        for obs in inference.observations[:5]:
            lines.append(f"- {obs}")
        lines.append("")

    # Inferencias relevantes (skip "normal")
    relevant = {k: v for k, v in inference.inferences.items()
                if v.label not in ("normal", "social_normal", "no_nesting", "normal_nesting")}
    if relevant:
        lines.append("**Inferencias:**")
        for dim, result in relevant.items():
            dim_es = _DIM_ES.get(dim, dim)
            conf_es = _CONF_ES.get(result.confidence, result.confidence)
            lines.append(f"- {dim_es}: {result.label} (certeza: {conf_es})")
            if result.evidence:
                for ev in result.evidence[:3]:
                    lines.append(f"  · {ev}")
        lines.append("")

    # Anomalías
    if inference.anomalies:
        lines.append("**Anomalías detectadas:**")
        for anom in inference.anomalies:
            lines.append(f"- ⚠️ {anom}")
        lines.append("")

    # Limitaciones
    if inference.insufficient_data_flags:
        lines.append(f"**Limitaciones:** {', '.join(inference.insufficient_data_flags)}")

    return "\n".join(lines)


def to_llm_context(inferences: list[BehaviorInference]) -> str:
    """Versión comprimida para inyectar en [CONTEXTO] del paso [10] del pipeline RAG.

    Una línea por ave, prioriza anomalías y certezas altas.
    """
    if not inferences:
        return ""

    lines = []
    lines.append(f"📊 Datos conductuales en vivo ({len(inferences)} aves, "
                 f"ventana {inferences[0].time_window}):")

    for inf in inferences:
        # Resumen ultra-compacto
        relevant = []
        for dim, result in inf.inferences.items():
            if result.label not in ("normal", "social_normal", "no_nesting",
                                     "normal_nesting", "inconclusive"):
                dim_short = _DIM_SHORT.get(dim, dim[:4])
                relevant.append(f"{dim_short}={result.label}({result.confidence[0]})")

        status = " | ".join(relevant) if relevant else "normal"
        if inf.anomalies:
            status += f" | ⚠️{len(inf.anomalies)} anomalía(s)"

        completeness = f"[{inf.data_completeness:.0%}]" if inf.data_completeness < 0.8 else ""
        lines.append(f"- {inf.bird_id}: {status} {completeness}")

    return "\n".join(lines)


def to_api_response(inference: BehaviorInference) -> dict:
    """Convierte a dict serializable para endpoints FastAPI."""
    return {
        "bird_id": inference.bird_id,
        "time_window": inference.time_window,
        "window_start": inference.window_start.isoformat(),
        "window_end": inference.window_end.isoformat(),
        "data_completeness": inference.data_completeness,
        "observations": inference.observations,
        "inferences": {
            k: {
                "label": v.label,
                "confidence": v.confidence,
                "score": v.score,
                "evidence": v.evidence,
            }
            for k, v in inference.inferences.items()
        },
        "anomalies": inference.anomalies,
        "insufficient_data_flags": inference.insufficient_data_flags,
        "metadata": {
            "inference_type": _get_inference_type(inference),
        },
    }


def to_dashboard_summary(inferences: list[BehaviorInference]) -> dict:
    """Resumen compacto para dashboard OvoSfera."""
    if not inferences:
        return {"birds": [], "summary": "Sin datos conductuales disponibles"}

    birds = []
    alerts = []
    for inf in inferences:
        bird_summary = {
            "bird_id": inf.bird_id,
            "status": "normal",
            "flags": [],
            "data_completeness": inf.data_completeness,
        }
        for dim, result in inf.inferences.items():
            if result.label not in ("normal", "social_normal", "no_nesting",
                                     "normal_nesting", "inconclusive"):
                bird_summary["flags"].append({
                    "dimension": dim,
                    "label": result.label,
                    "confidence": result.confidence,
                })
                if result.confidence in ("consistent", "high"):
                    bird_summary["status"] = "attention"

        if inf.anomalies:
            bird_summary["status"] = "alert"
            alerts.extend(inf.anomalies)

        birds.append(bird_summary)

    normal_count = sum(1 for b in birds if b["status"] == "normal")
    attention_count = sum(1 for b in birds if b["status"] == "attention")
    alert_count = sum(1 for b in birds if b["status"] == "alert")

    return {
        "birds": birds,
        "summary": {
            "total": len(birds),
            "normal": normal_count,
            "attention": attention_count,
            "alert": alert_count,
        },
        "alerts": alerts[:5],
        "window": inferences[0].time_window if inferences else "",
    }


def _get_inference_type(inf: BehaviorInference) -> str:
    if inf.data_completeness < 0.4:
        return "insufficient_data"
    has_relevant = any(
        v.label not in ("normal", "social_normal", "no_nesting", "normal_nesting", "inconclusive")
        for v in inf.inferences.values()
    )
    if has_relevant:
        return "inferred"
    return "observed"


# ── Traducciones ──

_DIM_ES = {
    "aggressiveness": "Agresividad",
    "dominance": "Dominancia",
    "subordination": "Subordinación",
    "feeding_level": "Nivel de ingesta",
    "stress": "Estrés",
    "sociality": "Socialización",
    "nesting_pattern": "Patrón de nido",
}

_DIM_SHORT = {
    "aggressiveness": "agr",
    "dominance": "dom",
    "subordination": "sub",
    "feeding_level": "feed",
    "stress": "str",
    "sociality": "soc",
    "nesting_pattern": "nest",
}

_CONF_ES = {
    "weak": "débil",
    "consistent": "consistente",
    "high": "alta",
    "inconclusive": "no concluyente",
}
