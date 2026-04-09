"""Seedy Backend — Behavior Inference

Transforma BirdBehaviorFeatures en etiquetas conductuales.
Reglas heurísticas puras, testables, sin dependencias externas.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import get_settings
from services.behavior_features import BirdBehaviorFeatures, compute_bird_features, compute_group_features
from services.behavior_baseline import get_baseline

logger = logging.getLogger(__name__)

_settings = get_settings()


@dataclass
class InferenceResult:
    label: str  # p.ej. "possible_aggressive", "normal", "inconclusive"
    confidence: str  # "weak" | "consistent" | "high" | "inconclusive"
    score: float  # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class BehaviorInference:
    bird_id: str
    time_window: str  # "1h" | "6h" | "24h"
    window_start: datetime
    window_end: datetime
    data_completeness: float
    observations: list[str] = field(default_factory=list)
    inferences: dict[str, InferenceResult] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)
    insufficient_data_flags: list[str] = field(default_factory=list)


def infer_behavior(
    features: BirdBehaviorFeatures,
    group_features: list[BirdBehaviorFeatures] | None = None,
) -> BehaviorInference:
    """Genera inferencias conductuales a partir de features.

    Args:
        features: Features del ave objetivo.
        group_features: Features de todas las aves del gallinero (para comparar).
    """
    inference = BehaviorInference(
        bird_id=features.bird_id,
        time_window=_window_label(features),
        window_start=features.window_start,
        window_end=features.window_end,
        data_completeness=features.data_completeness,
    )

    # Gate: datos insuficientes → todo inconclusive
    if features.data_completeness < 0.4:
        inference.insufficient_data_flags.append("data_completeness_below_0.4")
        for dim in ("aggressiveness", "dominance", "subordination",
                     "feeding_level", "stress", "sociality", "nesting_pattern"):
            inference.inferences[dim] = InferenceResult(
                label="inconclusive",
                confidence="inconclusive",
                score=0.0,
                evidence=["Datos insuficientes (completeness < 0.4)"],
            )
        return inference

    # Ventana mínima
    window_secs = (features.window_end - features.window_start).total_seconds()
    if window_secs < 1800:  # < 30 min
        inference.insufficient_data_flags.append("window_below_30min")

    # Build observations
    _build_observations(features, inference)

    # Baseline
    baseline = get_baseline()
    has_baseline = baseline.has_sufficient_history(features.bird_id)
    if not has_baseline:
        inference.insufficient_data_flags.append("insufficient_baseline_history")

    features.behavior_baseline_delta = baseline.compute_delta(features)

    # Group stats
    group_avg = _group_averages(group_features) if group_features else {}

    # ── Inferencias ──
    inference.inferences["aggressiveness"] = _infer_aggressiveness(features, group_avg)
    inference.inferences["dominance"] = _infer_dominance(features, group_avg, has_baseline)
    inference.inferences["subordination"] = _infer_subordination(features, group_avg)
    inference.inferences["feeding_level"] = _infer_feeding(features, group_avg, has_baseline)
    inference.inferences["stress"] = _infer_stress(features, group_avg, has_baseline)
    inference.inferences["sociality"] = _infer_sociality(features, group_avg)
    inference.inferences["nesting_pattern"] = _infer_nesting(features, has_baseline)

    # Detectar anomalías
    _detect_anomalies(features, group_avg, has_baseline, inference)

    # Update baseline con estos features
    baseline.update_baseline(features)

    return inference


def get_bird_behavior(
    bird_id: str,
    gallinero_id: str,
    window: str = "24h",
) -> BehaviorInference:
    """Endpoint-friendly: calcula features + inferencias para un ave."""
    group_features = compute_group_features(gallinero_id, window)
    bird_features = None
    for f in group_features:
        if f.bird_id == bird_id:
            bird_features = f
            break

    if not bird_features:
        bird_features = compute_bird_features(bird_id, gallinero_id, window)

    return infer_behavior(bird_features, group_features)


def get_group_behavior_summary(
    gallinero_id: str,
    window: str = "6h",
) -> list[BehaviorInference]:
    """Calcula inferencias para todas las aves de un gallinero."""
    group_features = compute_group_features(gallinero_id, window)
    if not group_features:
        return []

    results = []
    for feat in group_features:
        inf = infer_behavior(feat, group_features)
        results.append(inf)

    return results


# ── Reglas heurísticas ──

def _infer_aggressiveness(
    f: BirdBehaviorFeatures,
    group_avg: dict,
) -> InferenceResult:
    """AGRESIVIDAD — "possible_aggressive" solo si ≥2 señales."""
    signals = []
    avg_disp = group_avg.get("displacement_events_count", 0)
    aggr_mult = _settings.behavior_aggressiveness_multiplier

    if avg_disp > 0 and f.displacement_events_count > avg_disp * aggr_mult:
        signals.append(f"displacement_events ({f.displacement_events_count}) > media×{aggr_mult} ({avg_disp:.1f})")
    if f.chase_like_events_count > 0:
        signals.append(f"chase_like_events ({f.chase_like_events_count}) en ventana")
    # Proximidad alta + aislamiento de otras aves sube
    avg_prox = group_avg.get("proximity_events_count", 0)
    if avg_prox > 0 and f.proximity_events_count > avg_prox * aggr_mult:
        signals.append(f"proximity alta ({f.proximity_events_count}) vs media ({avg_prox:.1f})")

    if len(signals) >= 3:
        return InferenceResult("possible_aggressive", "consistent", 0.7, signals)
    elif len(signals) >= 2:
        return InferenceResult("possible_aggressive", "weak", 0.4, signals)
    return InferenceResult("normal", "consistent", 0.1, ["Sin señales de agresividad significativas"])


def _infer_dominance(
    f: BirdBehaviorFeatures,
    group_avg: dict,
    has_baseline: bool,
) -> InferenceResult:
    """DOMINANCIA — "probable_dominant" si ≥N señales consistentes."""
    signals = []
    feeder_high = _settings.behavior_feeder_ratio_high
    min_signals = _settings.behavior_dominance_min_signals

    if f.feeding_vs_group_ratio > feeder_high:
        signals.append(f"feeding_ratio ({f.feeding_vs_group_ratio:.2f}) > {feeder_high}")
    if f.displacement_events_count > 0:
        signals.append(f"displacement_events ({f.displacement_events_count})")
    # Centralidad top 25%
    if f.centrality_score > 0.6:
        signals.append(f"centrality alta ({f.centrality_score:.3f})")
    if has_baseline and f.behavior_baseline_delta < 0.3:
        signals.append("baseline estable (delta < 0.3)")

    if len(signals) >= min_signals:
        return InferenceResult("probable_dominant", "consistent", 0.7, signals)
    elif len(signals) >= 2:
        return InferenceResult("possible_dominant", "weak", 0.4, signals)
    return InferenceResult("normal", "consistent", 0.1, ["Sin señales claras de dominancia"])


def _infer_subordination(
    f: BirdBehaviorFeatures,
    group_avg: dict,
) -> InferenceResult:
    """SUBORDINACIÓN — si ≥2 señales."""
    signals = []
    feeder_low = _settings.behavior_feeder_ratio_low
    iso_mult = _settings.behavior_subordination_isolation_multiplier

    if f.feeding_vs_group_ratio < feeder_low:
        signals.append(f"feeding_ratio ({f.feeding_vs_group_ratio:.2f}) < {feeder_low}")
    if f.centrality_score < 0.3:
        signals.append(f"centrality baja ({f.centrality_score:.3f})")
    avg_iso = group_avg.get("isolation_time_sec", 0)
    if avg_iso > 0 and f.isolation_time_sec > avg_iso * iso_mult:
        signals.append(f"isolation ({f.isolation_time_sec:.0f}s) > media×{iso_mult} ({avg_iso:.0f}s)")

    if len(signals) >= 2:
        return InferenceResult("possible_subordinate", "weak", 0.5, signals)
    return InferenceResult("normal", "consistent", 0.1, ["Sin señales de subordinación"])


def _infer_feeding(
    f: BirdBehaviorFeatures,
    group_avg: dict,
    has_baseline: bool,
) -> InferenceResult:
    """NIVEL DE INGESTA — comparar 4 fuentes (baseline, grupo, ventana, clima)."""
    low_signals = []
    high_signals = []
    flags = []

    feeder_low = _settings.behavior_feeder_ratio_low
    feeder_high = _settings.behavior_feeder_ratio_high

    # Ajustar umbrales por clima
    if f.climate_data_available and f.ambient_temperature is not None:
        if f.ambient_temperature > _settings.behavior_heat_threshold:
            feeder_low = _settings.behavior_heat_feeder_override
            flags.append(f"heat_adjusted (>{_settings.behavior_heat_threshold}°C → low={feeder_low})")
        elif f.ambient_temperature < _settings.behavior_cold_threshold:
            feeder_high = _settings.behavior_cold_feeder_override
            flags.append(f"cold_adjusted (<{_settings.behavior_cold_threshold}°C → high={feeder_high})")
    elif not f.climate_data_available:
        flags.append("climate_not_factored")

    # 1. vs grupo
    if f.feeding_vs_group_ratio < feeder_low:
        low_signals.append(f"vs grupo: ratio {f.feeding_vs_group_ratio:.2f} < {feeder_low}")
    elif f.feeding_vs_group_ratio > feeder_high:
        high_signals.append(f"vs grupo: ratio {f.feeding_vs_group_ratio:.2f} > {feeder_high}")

    # 2. vs baseline propio
    if has_baseline:
        baseline_data = get_baseline().get_individual_baseline(f.bird_id)
        if baseline_data and baseline_data.get("feeder_total_time_sec", 0) > 0:
            baseline_feed = baseline_data["feeder_total_time_sec"]
            ratio = f.feeder_total_time_sec / baseline_feed
            if ratio < feeder_low:
                low_signals.append(f"vs baseline: ratio {ratio:.2f} < {feeder_low}")
            elif ratio > feeder_high:
                high_signals.append(f"vs baseline: ratio {ratio:.2f} > {feeder_high}")
    else:
        flags.append("no_baseline_available")

    # 3. vs ventana mínima (6h recomendada)
    window_hours = (f.window_end - f.window_start).total_seconds() / 3600
    if window_hours < 1:
        flags.append("short_window (<1h)")

    # 4. Temperatura ambiental ya ajustó umbrales arriba

    if len(low_signals) >= 2:
        evidence = low_signals + flags
        return InferenceResult("low_feeding", "consistent", 0.7, evidence)
    elif len(low_signals) == 1:
        return InferenceResult("low_feeding", "weak", 0.35, low_signals + flags)
    elif len(high_signals) >= 2:
        return InferenceResult("high_feeding", "consistent", 0.7, high_signals + flags)
    elif len(high_signals) == 1:
        return InferenceResult("high_feeding", "weak", 0.35, high_signals + flags)

    return InferenceResult("normal", "consistent", 0.1, ["Ingesta dentro de rangos normales"] + flags)


def _infer_stress(
    f: BirdBehaviorFeatures,
    group_avg: dict,
    has_baseline: bool,
) -> InferenceResult:
    """ESTRÉS — solo con combinación de señales. Clima descarta falsos positivos."""
    signals = []
    flags = []

    # Termorregulación: descartar señales normales en calor/frío extremo
    is_hot = (f.climate_data_available and f.ambient_temperature is not None
              and f.ambient_temperature > _settings.behavior_heat_threshold)
    is_cold = (f.climate_data_available and f.ambient_temperature is not None
               and f.ambient_temperature < _settings.behavior_cold_threshold)

    if not f.climate_data_available:
        flags.append("climate_not_factored")

    # Hiperactividad o inmovilidad
    hyperactive = False
    immobile = False
    if has_baseline:
        baseline_data = get_baseline().get_individual_baseline(f.bird_id)
        if baseline_data:
            base_activity = baseline_data.get("activity_score", 0)
            base_inactivity = baseline_data.get("inactivity_time_sec", 0)
            if base_activity > 0 and f.activity_score > base_activity * _settings.behavior_stress_activity_multiplier:
                if not is_cold:  # Frío → hiperactividad leve es normal
                    hyperactive = True
                    signals.append(f"hiperactividad: activity {f.activity_score:.3f} > baseline×{_settings.behavior_stress_activity_multiplier} ({base_activity:.3f})")
                else:
                    flags.append("cold_hyperactivity_discarded")
            if base_inactivity > 0 and f.inactivity_time_sec > base_inactivity * _settings.behavior_stress_activity_multiplier:
                if not is_hot:  # Calor → inmovilidad es normal
                    immobile = True
                    signals.append(f"inmovilidad: {f.inactivity_time_sec:.0f}s > baseline×{_settings.behavior_stress_activity_multiplier} ({base_inactivity:.0f}s)")
                else:
                    flags.append("heat_inactivity_discarded")

    # Baja ingesta
    if has_baseline:
        baseline_data = get_baseline().get_individual_baseline(f.bird_id)
        if baseline_data and baseline_data.get("feeder_visits_count", 0) > 0:
            if f.feeder_visits_count < baseline_data["feeder_visits_count"] * 0.5:
                if not is_hot:  # Calor extremo → baja ingesta es termorregulación
                    signals.append(f"baja ingesta: {f.feeder_visits_count} < baseline×0.5")
                else:
                    flags.append("heat_low_feeding_discarded")

    # Aislamiento
    avg_iso = group_avg.get("isolation_time_sec", 0)
    if avg_iso > 0 and f.isolation_time_sec > avg_iso * 1.5:
        signals.append(f"aislamiento: {f.isolation_time_sec:.0f}s > media ({avg_iso:.0f}s)")

    if len(signals) >= 3:
        return InferenceResult("possible_stress", "consistent", 0.7, signals + flags)
    elif len(signals) >= 2:
        return InferenceResult("possible_stress", "weak", 0.4, signals + flags)
    elif len(signals) == 1:
        return InferenceResult("inconclusive", "inconclusive", 0.2, signals + flags)

    return InferenceResult("normal", "consistent", 0.1, ["Sin señales de estrés"] + flags)


def _infer_sociality(
    f: BirdBehaviorFeatures,
    group_avg: dict,
) -> InferenceResult:
    """AISLAMIENTO — "relevant_isolation" si tiempo aislada > 70% ventana."""
    window_secs = (f.window_end - f.window_start).total_seconds()
    if window_secs <= 0:
        return InferenceResult("inconclusive", "inconclusive", 0.0, [])

    iso_ratio = f.isolation_time_sec / window_secs
    signals = []

    if iso_ratio > 0.7:
        signals.append(f"isolation {iso_ratio:.0%} de la ventana (> 70%)")
    avg_prox = group_avg.get("proximity_events_count", 0)
    if avg_prox > 0:
        prox_pct = f.proximity_events_count / avg_prox if avg_prox > 0 else 1.0
        if prox_pct < _settings.behavior_isolation_percentile:
            signals.append(f"proximity ({f.proximity_events_count}) < P10 grupo ({avg_prox:.0f})")

    if len(signals) >= 2:
        return InferenceResult("relevant_isolation", "consistent", 0.7, signals)
    elif signals:
        return InferenceResult("mild_isolation", "weak", 0.35, signals)

    return InferenceResult("social_normal", "consistent", 0.1, ["Socialización normal"])


def _infer_nesting(
    f: BirdBehaviorFeatures,
    has_baseline: bool,
) -> InferenceResult:
    """PATRÓN NIDO — anomalía si tiempo en nido > baseline×2 fuera de horario."""
    if f.nest_total_time_sec == 0:
        return InferenceResult("no_nesting", "consistent", 0.0, ["Sin tiempo en nido"])

    signals = []

    if has_baseline:
        baseline_data = get_baseline().get_individual_baseline(f.bird_id)
        if baseline_data and baseline_data.get("nest_total_time_sec", 0) > 0:
            ratio = f.nest_total_time_sec / baseline_data["nest_total_time_sec"]
            if ratio > 2.0:
                signals.append(f"nest_time ({f.nest_total_time_sec:.0f}s) > baseline×2")

    # Franja horaria (parametrizable)
    nest_hours = [int(h) for h in _settings.behavior_nest_anomaly_hours.split(",")]
    if len(nest_hours) == 2:
        current_hour = f.window_end.hour
        if not (nest_hours[0] <= current_hour <= nest_hours[1]):
            signals.append(f"fuera de franja esperada ({nest_hours[0]}-{nest_hours[1]}h)")

    # TODO: nest_anomaly_hours parametrizar por raza (Bresse vs Sussex)

    if len(signals) >= 2:
        return InferenceResult("anomalous_nesting", "consistent", 0.6, signals)
    elif signals:
        return InferenceResult("anomalous_nesting", "weak", 0.3, signals)

    return InferenceResult("normal_nesting", "consistent", 0.1, ["Patrón de nido normal"])


# ── Helpers ──

def _build_observations(f: BirdBehaviorFeatures, inf: BehaviorInference):
    """Construye observaciones factuales en lenguaje neutro."""
    obs = inf.observations
    obs.append(f"Observada en {f.feeder_visits_count} visitas al comedero ({f.feeder_total_time_sec:.0f}s total)")
    obs.append(f"Bebedero: {f.drinker_visits_count} visitas ({f.drinker_total_time_sec:.0f}s)")
    obs.append(f"Distancia recorrida: {f.distance_traveled:.4f} (normalizada)")
    obs.append(f"Cambios de zona: {f.zone_switch_count}")
    if f.inactivity_time_sec > 0:
        obs.append(f"Tiempo inactiva: {f.inactivity_time_sec:.0f}s")
    if f.isolation_time_sec > 0:
        obs.append(f"Tiempo aislada: {f.isolation_time_sec:.0f}s")
    if f.climate_data_available:
        obs.append(f"Clima: {f.ambient_temperature}°C, {f.ambient_humidity}% humedad")


def _detect_anomalies(
    f: BirdBehaviorFeatures,
    group_avg: dict,
    has_baseline: bool,
    inf: BehaviorInference,
):
    """Detecta desviaciones vs baseline."""
    if not has_baseline:
        return
    if f.behavior_baseline_delta > 0.5:
        inf.anomalies.append(
            f"Desviación general respecto al baseline: {f.behavior_baseline_delta:.2f} (> 0.5)"
        )
    # Cambio brusco de zona favorita
    baseline_data = get_baseline().get_individual_baseline(f.bird_id)
    if baseline_data:
        base_nest = baseline_data.get("nest_total_time_sec", 0)
        if base_nest > 0 and f.nest_total_time_sec > base_nest * 3:
            inf.anomalies.append(
                f"Tiempo en nido ×{f.nest_total_time_sec/base_nest:.1f} respecto al baseline"
            )


def _group_averages(group_features: list[BirdBehaviorFeatures] | None) -> dict:
    """Calcula medias del grupo."""
    if not group_features:
        return {}
    n = len(group_features)
    return {
        "displacement_events_count": sum(f.displacement_events_count for f in group_features) / n,
        "chase_like_events_count": sum(f.chase_like_events_count for f in group_features) / n,
        "proximity_events_count": sum(f.proximity_events_count for f in group_features) / n,
        "isolation_time_sec": sum(f.isolation_time_sec for f in group_features) / n,
        "feeder_total_time_sec": sum(f.feeder_total_time_sec for f in group_features) / n,
        "drinker_total_time_sec": sum(f.drinker_total_time_sec for f in group_features) / n,
        "distance_traveled": sum(f.distance_traveled for f in group_features) / n,
        "activity_score": sum(f.activity_score for f in group_features) / n,
        "inactivity_time_sec": sum(f.inactivity_time_sec for f in group_features) / n,
        "centrality_score": sum(f.centrality_score for f in group_features) / n,
    }


def _window_label(f: BirdBehaviorFeatures) -> str:
    hours = (f.window_end - f.window_start).total_seconds() / 3600
    if hours <= 1.5:
        return "1h"
    if hours <= 8:
        return "6h"
    return "24h"
