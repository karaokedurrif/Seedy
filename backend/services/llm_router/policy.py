"""
Step Policies — Reglas de routing para cada paso del pipeline RAG.
Define qué modelo usar (primario + fallbacks) y umbrales de latencia.
"""

from dataclasses import dataclass


@dataclass
class StepPolicy:
    """
    Política de routing para un paso del pipeline.
    
    Attributes:
        name: Identificador del paso
        primary: Modelo primario (ej: "ollama:qwen2.5-7b")
        fallback: Lista de fallbacks en orden
        max_latency_s: Si primario excede este tiempo en dar primer token, escala a fallback
        requires_user: True = usuario esperando (crítico). False = batch async.
    """
    name: str
    primary: str
    fallback: list[str]
    max_latency_s: float
    requires_user: bool


# ═══════════════════════════════════════════════════════════════════
# POLÍTICAS v4.6 — MIGRACIÓN GRADUAL: PASOS PEQUEÑOS A OLLAMA LOCAL
# ═══════════════════════════════════════════════════════════════════

POLICIES = {
    # ── PASO 1: Query Rewriter ──
    "rewriter": StepPolicy(
        name="rewriter",
        primary="ollama:qwen2.5-7b",  # ~40 tokens output, 2-3s esperados
        fallback=["together:qwen2.5-7b-turbo"],
        max_latency_s=5.0,
        requires_user=True,
    ),
    
    # ── PASO 2a: Clasificador Categoría ──
    "classifier_category": StepPolicy(
        name="classifier_category",
        primary="ollama:qwen2.5-7b",  # ~15 tokens output, <1s esperado
        fallback=["together:qwen2.5-7b-turbo"],
        max_latency_s=3.0,
        requires_user=True,
    ),
    
    # ── PASO 2b: Clasificador Temporalidad ──
    "classifier_temporal": StepPolicy(
        name="classifier_temporal",
        primary="ollama:qwen2.5-7b",  # ~10 tokens output, <1s esperado
        fallback=["together:qwen2.5-7b-turbo"],
        max_latency_s=3.0,
        requires_user=True,
    ),
    
    # ── PASO 8: Evidence Extraction ──
    "evidence_extraction": StepPolicy(
        name="evidence_extraction",
        primary="ollama:qwen2.5-7b",  # ~300 tokens output, ~10s aceptable
        fallback=["together:qwen2.5-7b-turbo"],
        max_latency_s=15.0,
        requires_user=True,
    ),
    
    # ── PASO 10: Generación Principal (CHAT) — NO TOCAR ──
    "generation_default": StepPolicy(
        name="generation_default",
        primary="together:qwen3-235b-tput",  # Velocidad crítica para UX
        fallback=["together:kimi-k2.5", "ollama:seedy-v16"],
        max_latency_s=30.0,
        requires_user=True,
    ),
    
    "generation_think": StepPolicy(
        name="generation_think",
        primary="together:deepseek-r1",  # Modo /think profundo
        fallback=["together:qwen3-235b-tput", "ollama:seedy-v16"],
        max_latency_s=60.0,
        requires_user=True,
    ),
    
    # ── PASO 10: Modos Locales (NUEVO v4.6) ──
    "generation_local": StepPolicy(
        name="generation_local",
        primary="ollama:seedy-v16",  # Modo /local — Fine-tuned 14B
        fallback=["together:qwen2.5-7b-turbo"],
        max_latency_s=20.0,
        requires_user=True,
    ),
    
    "generation_deep": StepPolicy(
        name="generation_deep",
        primary="ollama:qwen2.5-72b",  # Modo /deep — 72B local, LENTO
        fallback=["ollama:seedy-v16"],  # NO cae a Together (usuario eligió local)
        max_latency_s=300.0,  # 5 min de techo
        requires_user=True,
    ),
    
    "generation_eco": StepPolicy(
        name="generation_eco",
        primary="ollama:seedy-v16",  # Modo /eco — Sin web, sin coste
        fallback=[],  # Sin fallback, falla limpio si DGX cae
        max_latency_s=20.0,
        requires_user=True,
    ),
    
    # ── PASO 11: Critic Gate — CAMBIO IMPORTANTE v4.6 ──
    "critic_gate": StepPolicy(
        name="critic_gate",
        primary="ollama:seedy-v16",  # Fine-tuned en avicultura, perfecto para esto
        fallback=["together:qwen3-235b-tput"],
        max_latency_s=8.0,
        requires_user=True,
    ),
    
    # ══════════════════════════════════════════════════════════════
    # ANÁLISIS BATCH ASYNC — NUEVOS v4.6
    # ══════════════════════════════════════════════════════════════
    
    "behavior_7d_analysis": StepPolicy(
        name="behavior_7d_analysis",
        primary="ollama:qwen2.5-72b",  # 72B ideal para análisis profundo async
        fallback=["together:qwen3-235b-tput"],
        max_latency_s=600.0,  # 10 min, no bloquea nada
        requires_user=False,
    ),
    
    "mating_confirmation": StepPolicy(
        name="mating_confirmation",
        primary="ollama:qwen2.5-72b",  # Validación multimodal con Re-ID
        fallback=["together:qwen3-235b-tput"],
        max_latency_s=120.0,  # 2 min aceptable
        requires_user=False,
    ),
    
    "weekly_report": StepPolicy(
        name="weekly_report",
        primary="ollama:qwen2.5-72b",  # Informe largo, corre de noche
        fallback=["together:deepseek-r1"],
        max_latency_s=900.0,  # 15 min
        requires_user=False,
    ),
}


def get_policy(step_name: str) -> StepPolicy:
    """Helper para obtener policy con validación."""
    if step_name not in POLICIES:
        raise ValueError(f"Unknown step: {step_name}. Available: {list(POLICIES.keys())}")
    return POLICIES[step_name]
