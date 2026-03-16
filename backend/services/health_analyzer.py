"""
Seedy Backend — Analizador de salud y comportamiento avícola

A partir de los datos del tracker (bird_tracker.py) y del detector
(yolo_detector.py), genera puntuaciones de salud, detecta patrones
anómalos y construye perfiles de crecimiento.

Fase 1: heurísticas basadas en movimiento, zona y tamaño.
Fase 2: modelo clasificador de comportamiento (train con datos propios).
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Indicadores de referencia (se calibran con datos reales) ──

REFERENCE = {
    # Porcentaje tiempo esperado por zona (para gallinas adultas)
    "zone_balance": {
        "comedero": (0.10, 0.30),   # entre 10% y 30% del tiempo
        "bebedero": (0.05, 0.15),
        "aseladero": (0.20, 0.50),
        "nido": (0.02, 0.15),
        "zona_libre": (0.10, 0.40),
    },
    # Movimiento normalizado esperado (por frame)
    "movement": {
        "min_healthy": 0.005,       # menos = posible letargia
        "max_healthy": 0.10,        # más = posible estrés/pelea
    },
    # Crecimiento (area_norm por semana de edad, para pollitos)
    "growth_curve": {
        1: (0.001, 0.003),
        2: (0.002, 0.005),
        4: (0.004, 0.010),
        8: (0.008, 0.020),
        12: (0.012, 0.030),
        16: (0.015, 0.040),
    },
}


@dataclass
class HealthScore:
    """Puntuación de salud de un ave."""
    track_id: int
    timestamp: float = field(default_factory=time.time)

    # Puntuaciones parciales (0-100)
    mobility_score: int = 100
    feeding_score: int = 100
    social_score: int = 100
    zone_balance_score: int = 100

    # Score global
    overall: int = 100

    # Issues detectados
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "timestamp": self.timestamp,
            "overall": self.overall,
            "mobility": self.mobility_score,
            "feeding": self.feeding_score,
            "social": self.social_score,
            "zone_balance": self.zone_balance_score,
            "issues": self.issues,
        }


def analyze_bird_health(track_profile: dict, track_data) -> HealthScore:
    """
    Analiza la salud de un ave a partir de su perfil de tracking.

    Args:
        track_profile: dict devuelto por BirdTrack.get_profile()
        track_data: BirdTrack completo (para acceder al historial)

    Returns:
        HealthScore con puntuaciones y alertas
    """
    score = HealthScore(track_id=track_profile["track_id"])

    # Necesitamos suficientes datos
    if track_profile["total_frames"] < 5:
        score.issues.append("insufficient_data")
        return score

    # 1. Movilidad
    avg_mov = track_profile.get("avg_movement", 0)
    ref = REFERENCE["movement"]
    if avg_mov < ref["min_healthy"]:
        score.mobility_score = max(20, int(100 * avg_mov / ref["min_healthy"]))
        score.issues.append("low_mobility")
    elif avg_mov > ref["max_healthy"]:
        score.mobility_score = max(30, int(100 - 50 * (avg_mov - ref["max_healthy"]) / ref["max_healthy"]))
        score.issues.append("excessive_movement")

    # 2. Alimentación (tiempo en comedero + bebedero)
    zone_time = track_profile.get("zone_time", {})
    total_frames = track_profile["total_frames"]
    if total_frames > 10:
        feeding_pct = zone_time.get("comedero", 0) / total_frames
        drinking_pct = zone_time.get("bebedero", 0) / total_frames

        food_ref = REFERENCE["zone_balance"]["comedero"]
        water_ref = REFERENCE["zone_balance"]["bebedero"]

        if feeding_pct < food_ref[0]:
            score.feeding_score -= 30
            score.issues.append("low_feeding")
        elif feeding_pct > food_ref[1]:
            score.feeding_score -= 15
            score.issues.append("excessive_feeding")

        if drinking_pct < water_ref[0]:
            score.feeding_score -= 20
            score.issues.append("low_drinking")
        elif drinking_pct > water_ref[1]:
            score.feeding_score -= 10
            score.issues.append("excessive_drinking")

    # 3. Socialización
    activity = track_profile.get("activity", "normal")
    if activity == "quieta" and track_profile.get("total_distance", 0) < 0.01:
        score.social_score -= 40
        score.issues.append("isolated_inactive")

    # 4. Balance de zonas
    if total_frames > 20:
        main_zone = track_profile.get("main_zone", "")
        if main_zone:
            main_pct = zone_time.get(main_zone, 0) / total_frames
            if main_pct > 0.8:
                score.zone_balance_score -= 40
                score.issues.append(f"stuck_in_{main_zone}")

    # Score global
    score.overall = int(
        0.35 * score.mobility_score +
        0.30 * score.feeding_score +
        0.20 * score.social_score +
        0.15 * score.zone_balance_score
    )

    return score


def analyze_flock_health(tracker) -> dict:
    """
    Análisis de salud del rebaño completo.

    Args:
        tracker: GallineroTracker instance

    Returns:
        Dict con scores individuales, alertas y métricas del grupo
    """
    active = [t for t in tracker.tracks.values() if t.active]
    if not active:
        return {
            "gallinero": tracker.gallinero_id,
            "active_birds": 0,
            "scores": [],
            "flock_alerts": [],
            "avg_health": 0,
        }

    scores = []
    for t in active:
        profile = t.get_profile()
        health = analyze_bird_health(profile, t)
        scores.append(health)

    # Métricas del rebaño
    overall_scores = [s.overall for s in scores]
    avg_health = sum(overall_scores) / len(overall_scores)

    flock_alerts = []

    # Alerta: muchas aves con baja salud
    low_health = [s for s in scores if s.overall < 60]
    if len(low_health) > len(scores) * 0.3:
        flock_alerts.append({
            "type": "flock_health_warning",
            "severity": "warning",
            "detail": (
                f"{len(low_health)}/{len(scores)} aves con salud <60. "
                "Revisar condiciones del gallinero."
            ),
        })

    # Alerta: nadie comiendo
    issue_counts = defaultdict(int)
    for s in scores:
        for issue in s.issues:
            issue_counts[issue] += 1

    if issue_counts.get("low_feeding", 0) > len(scores) * 0.5:
        flock_alerts.append({
            "type": "feeding_problem",
            "severity": "alert",
            "detail": "Más del 50% de las aves no están comiendo. ¿Comedero vacío? ¿Pienso en mal estado?",
        })

    if issue_counts.get("low_drinking", 0) > len(scores) * 0.5:
        flock_alerts.append({
            "type": "water_problem",
            "severity": "alert",
            "detail": "Más del 50% de las aves no beben. ¿Bebedero vacío o bloqueado?",
        })

    if issue_counts.get("excessive_movement", 0) > len(scores) * 0.4:
        flock_alerts.append({
            "type": "stress_indicator",
            "severity": "warning",
            "detail": "Muchas aves con movimiento excesivo — posible estrés, depredador cerca, o pelea.",
        })

    # Anomalías del tracker
    tracker_anomalies = tracker.detect_anomalies()

    return {
        "gallinero": tracker.gallinero_id,
        "timestamp": time.time(),
        "active_birds": len(active),
        "avg_health": round(avg_health, 1),
        "scores": [s.to_dict() for s in scores],
        "flock_alerts": flock_alerts,
        "tracker_anomalies": tracker_anomalies,
        "issue_summary": dict(issue_counts),
    }


# ── Tracking de crecimiento ──

class GrowthTracker:
    """
    Registra el tamaño corporal estimado de aves a lo largo del tiempo
    para construir curvas de crecimiento.
    """

    def __init__(self):
        # track_id → lista de (timestamp, avg_size)
        self._records: dict[int, list[tuple[float, float]]] = defaultdict(list)

    def record(self, track_id: int, avg_size: float):
        """Registra una medida de tamaño."""
        self._records[track_id].append((time.time(), avg_size))

    def get_growth_curve(self, track_id: int) -> list[dict]:
        records = self._records.get(track_id, [])
        return [
            {"timestamp": ts, "size": round(sz, 6)}
            for ts, sz in records
        ]

    def get_growth_rate(self, track_id: int) -> Optional[float]:
        """Calcula tasa de crecimiento (cambio de tamaño / hora)."""
        records = self._records.get(track_id, [])
        if len(records) < 2:
            return None
        first_ts, first_sz = records[0]
        last_ts, last_sz = records[-1]
        elapsed_h = (last_ts - first_ts) / 3600
        if elapsed_h < 0.01:
            return None
        return (last_sz - first_sz) / elapsed_h

    def compare_growth(self) -> list[dict]:
        """Compara crecimiento entre aves trackadas."""
        result = []
        for tid, records in self._records.items():
            if len(records) < 3:
                continue
            rate = self.get_growth_rate(tid)
            current_size = records[-1][1]
            result.append({
                "track_id": tid,
                "current_size": round(current_size, 6),
                "growth_rate": round(rate, 8) if rate else None,
                "measurements": len(records),
            })
        result.sort(key=lambda x: x.get("growth_rate") or 0, reverse=True)
        return result


# Singleton
_growth_tracker = GrowthTracker()


def get_growth_tracker() -> GrowthTracker:
    return _growth_tracker
