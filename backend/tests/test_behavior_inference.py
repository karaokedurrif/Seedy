"""Tests para behavior_inference."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("TOGETHER_API_KEY", "test")

from services.behavior_features import BirdBehaviorFeatures
from services.behavior_inference import (
    infer_behavior,
    BehaviorInference,
    InferenceResult,
    _infer_aggressiveness,
    _infer_dominance,
    _infer_feeding,
    _infer_stress,
    _infer_sociality,
    _infer_nesting,
)


def _make_features(**kwargs) -> BirdBehaviorFeatures:
    """Helper para crear features con defaults."""
    now = datetime.now(timezone.utc)
    defaults = {
        "bird_id": "PAL-2026-0001",
        "gallinero_id": "gallinero_durrif_1",
        "window_start": now - timedelta(hours=24),
        "window_end": now,
        "data_completeness": 0.9,
    }
    defaults.update(kwargs)
    return BirdBehaviorFeatures(**defaults)


# Fixture: ave normal
NORMAL_HEN = _make_features(
    feeder_visits_count=8,
    feeder_total_time_sec=420,
    feeder_avg_duration_sec=52.5,
    drinker_visits_count=5,
    drinker_total_time_sec=200,
    distance_traveled=0.15,
    activity_score=0.05,
    inactivity_time_sec=3600,
    zone_switch_count=20,
    proximity_events_count=15,
    displacement_events_count=1,
    chase_like_events_count=0,
    isolation_time_sec=1800,
    group_cohesion_score=0.6,
    centrality_score=0.5,
    feeding_vs_group_ratio=1.0,
    drinking_vs_group_ratio=1.0,
    mobility_vs_group_ratio=1.0,
)


class TestInferenceGate:

    def test_low_completeness_all_inconclusive(self):
        """data_completeness < 0.4 → todas las inferencias inconclusive."""
        features = _make_features(data_completeness=0.3)
        with patch("services.behavior_inference.get_baseline") as mock_bl:
            mock_bl.return_value = MagicMock(
                has_sufficient_history=MagicMock(return_value=False),
                compute_delta=MagicMock(return_value=0),
                update_baseline=MagicMock(),
            )
            result = infer_behavior(features)

        assert "data_completeness_below_0.4" in result.insufficient_data_flags
        for dim, inf in result.inferences.items():
            assert inf.label == "inconclusive"

    def test_single_bird_no_crash(self):
        """Gallinero con 1 sola ave → no crash, group ratios = 1.0."""
        features = _make_features()
        with patch("services.behavior_inference.get_baseline") as mock_bl:
            mock_bl.return_value = MagicMock(
                has_sufficient_history=MagicMock(return_value=False),
                compute_delta=MagicMock(return_value=0),
                update_baseline=MagicMock(),
            )
            result = infer_behavior(features, group_features=[features])
        assert result.bird_id == "PAL-2026-0001"


class TestAggressiveness:

    def test_normal(self):
        """Sin señales → normal."""
        result = _infer_aggressiveness(NORMAL_HEN, {
            "displacement_events_count": 2,
            "proximity_events_count": 20,
        })
        assert result.label == "normal"

    def test_possible_with_two_signals(self):
        """2 señales → possible_aggressive weak."""
        aggressive = _make_features(
            displacement_events_count=5,
            chase_like_events_count=2,
        )
        result = _infer_aggressiveness(aggressive, {
            "displacement_events_count": 2,
            "proximity_events_count": 10,
        })
        assert result.label == "possible_aggressive"
        assert result.confidence in ("weak", "consistent")


class TestFeeding:

    def test_normal_feeding(self):
        """Ingesta normal."""
        with patch("services.behavior_inference.get_baseline") as mock_bl:
            mock_bl.return_value = MagicMock(
                get_individual_baseline=MagicMock(return_value=None),
            )
            result = _infer_feeding(NORMAL_HEN, {
                "feeder_total_time_sec": 420,
            }, has_baseline=False)
        assert result.label == "normal"

    def test_low_feeding(self):
        """Ingesta baja vs grupo."""
        low_feeder = _make_features(
            feeding_vs_group_ratio=0.4,
            feeder_total_time_sec=100,
        )
        with patch("services.behavior_inference.get_baseline") as mock_bl:
            baseline = MagicMock()
            baseline.get_individual_baseline.return_value = {
                "feeder_total_time_sec": 400,
                "n_updates": 5,
            }
            mock_bl.return_value = baseline
            result = _infer_feeding(low_feeder, {
                "feeder_total_time_sec": 420,
            }, has_baseline=True)
        assert "low_feeding" in result.label

    def test_heat_adjusts_threshold(self):
        """Con calor extremo, umbral bajo se reduce."""
        hot_feeder = _make_features(
            feeding_vs_group_ratio=0.6,  # below normal 0.7 but above heat 0.5
            climate_data_available=True,
            ambient_temperature=38.0,
        )
        with patch("services.behavior_inference.get_baseline") as mock_bl:
            mock_bl.return_value = MagicMock(
                get_individual_baseline=MagicMock(return_value=None),
            )
            result = _infer_feeding(hot_feeder, {}, has_baseline=False)
        # 0.6 > 0.5 (heat override) → should NOT be low_feeding
        assert result.label == "normal"
        assert any("heat_adjusted" in e for e in result.evidence)


class TestStress:

    def test_heat_discards_inactivity(self):
        """Calor extremo descarta inmovilidad como señal de estrés."""
        hot_bird = _make_features(
            climate_data_available=True,
            ambient_temperature=37.0,
            inactivity_time_sec=7200,
            feeder_visits_count=2,
        )
        result = _infer_stress(hot_bird, {
            "isolation_time_sec": 1000,
        }, has_baseline=False)
        # Sin baseline → no hay señales calculables
        assert result.label in ("normal", "inconclusive")


class TestSociality:

    def test_isolation(self):
        """Ave aislada >70% del tiempo."""
        isolated = _make_features(
            isolation_time_sec=70000,  # > 70% of 86400s
            proximity_events_count=1,
        )
        result = _infer_sociality(isolated, {
            "proximity_events_count": 20,
        })
        assert "isolation" in result.label


class TestNesting:

    def test_no_nesting(self):
        """Sin tiempo en nido → no_nesting."""
        result = _infer_nesting(
            _make_features(nest_total_time_sec=0),
            has_baseline=False,
        )
        assert result.label == "no_nesting"
