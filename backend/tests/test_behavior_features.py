"""Tests para behavior_features y behavior_event_store."""

import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Mock settings antes de importar módulos
os.environ.setdefault("TOGETHER_API_KEY", "test")

from services.behavior_event_store import BehaviorEventStore
from services.behavior_features import (
    BirdBehaviorFeatures,
    compute_bird_features,
    _detect_displacement_events,
    _detect_chase_events,
    _compute_social_metrics,
)


@pytest.fixture
def tmp_store(tmp_path):
    """Event store con directorio temporal."""
    return BehaviorEventStore(base_path=str(tmp_path))


@pytest.fixture
def sample_snapshots():
    """Genera 60 snapshots simulados (~1 hora a 60s intervals)."""
    now = time.time()
    snapshots = []
    for i in range(60):
        ts = now - (60 - i) * 60
        # Ave 1: se mueve entre comedero y zona_libre
        zone1 = "comedero" if i % 10 < 4 else "zona_libre"
        cx1 = 0.15 if zone1 == "comedero" else 0.5 + (i % 5) * 0.02
        # Ave 2: mayormente en bebedero/nido
        zone2 = "bebedero" if i % 8 < 3 else "nido" if i % 8 < 5 else "zona_libre"
        cx2 = 0.4 if zone2 == "bebedero" else 0.85 if zone2 == "nido" else 0.6

        snapshots.append({
            "ts": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "ts_unix": round(ts, 2),
            "gallinero_id": "gallinero_durrif_1",
            "active_count": 2,
            "tracks": [
                {
                    "track_id": 1,
                    "bird_id": "PAL-2026-0001",
                    "center": [cx1, 0.7],
                    "zone": zone1,
                    "confidence": 0.85,
                    "area": 0.02,
                },
                {
                    "track_id": 2,
                    "bird_id": "PAL-2026-0002",
                    "center": [cx2, 0.3],
                    "zone": zone2,
                    "confidence": 0.78,
                    "area": 0.018,
                },
            ],
        })
    return snapshots


class TestBehaviorEventStore:

    def test_snapshot_and_query(self, tmp_store):
        """Escribe y lee snapshots correctamente."""
        from unittest.mock import MagicMock
        from collections import deque

        # Mock tracker
        tracker = MagicMock()
        track1 = MagicMock()
        track1.active = True
        track1.track_id = 1
        track1.ai_vision_id = "PAL-2026-0001"
        pt = MagicMock()
        pt.center = (0.5, 0.5)
        pt.zone = "comedero"
        pt.confidence = 0.9
        pt.area_norm = 0.02
        track1.history = deque([pt])
        tracker.tracks = {1: track1}

        # Forzar que se escriba (reset interval)
        tmp_store._last_snapshot["test"] = 0
        with patch("services.behavior_event_store._settings") as mock_settings:
            mock_settings.behavior_snapshot_interval_sec = 0
            mock_settings.behavior_retention_days = 7
            tmp_store.snapshot("test", tracker)

        # Leer
        now = datetime.now(timezone.utc)
        results = tmp_store.query("test", now - timedelta(hours=1), now + timedelta(hours=1))
        assert len(results) == 1
        assert results[0]["tracks"][0]["bird_id"] == "PAL-2026-0001"

    def test_cleanup(self, tmp_store, tmp_path):
        """Limpia ficheros antiguos."""
        old_dir = tmp_path / "test_gall"
        old_dir.mkdir()
        # Crear fichero "antiguo"
        old_file = old_dir / "2025-01-01.jsonl"
        old_file.write_text('{"test": 1}\n')
        # Crear fichero "reciente"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_file = old_dir / f"{today}.jsonl"
        new_file.write_text('{"test": 2}\n')

        deleted = tmp_store.cleanup(max_age_days=7)
        assert deleted == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_stats(self, tmp_store, tmp_path):
        """Estadísticas correctas."""
        gall_dir = tmp_path / "gall1"
        gall_dir.mkdir()
        (gall_dir / "2026-04-05.jsonl").write_text('{"test": 1}\n')
        (gall_dir / "2026-04-06.jsonl").write_text('{"test": 2}\n' * 10)

        stats = tmp_store.get_stats("gall1")
        assert stats["gallineros"]["gall1"]["files"] == 2


class TestBehaviorFeatures:

    def test_empty_features(self, tmp_store, tmp_path):
        """Ave sin datos → completeness=0, sin crashes."""
        with patch("services.behavior_features.get_event_store", return_value=tmp_store):
            features = compute_bird_features(
                "PAL-2026-9999", "gallinero_durrif_1", "1h"
            )
        assert features.data_completeness == 0.0
        assert features.feeder_visits_count == 0
        assert features.distance_traveled == 0.0

    def test_features_from_snapshots(self, tmp_store, tmp_path, sample_snapshots):
        """Features calculadas correctamente con datos sintéticos."""
        # Escribir snapshots al store
        gall_dir = tmp_path / "gallinero_durrif_1"
        gall_dir.mkdir(parents=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = gall_dir / f"{today}.jsonl"
        with open(filepath, "w") as f:
            for snap in sample_snapshots:
                f.write(json.dumps(snap) + "\n")

        with patch("services.behavior_features.get_event_store", return_value=tmp_store):
            with patch("services.behavior_features._enrich_climate"):
                features = compute_bird_features(
                    "PAL-2026-0001", "gallinero_durrif_1", "1h"
                )

        assert features.data_completeness > 0.0
        assert features.feeder_visits_count > 0
        assert features.feeder_total_time_sec > 0
        assert features.zone_switch_count > 0
        assert features.distance_traveled > 0

    def test_displacement_detection(self):
        """Heurística de displacement con datos sintéticos."""
        snapshots = [
            {"tracks": [
                {"bird_id": "A", "center": [0.5, 0.5]},
                {"bird_id": "B", "center": [0.8, 0.5]},
            ]},
            {"tracks": [
                {"bird_id": "A", "center": [0.6, 0.5]},  # A se acerca
                {"bird_id": "B", "center": [0.7, 0.5]},
            ]},
            {"tracks": [
                {"bird_id": "A", "center": [0.65, 0.5]},
                {"bird_id": "B", "center": [0.95, 0.5]},  # B se aleja rápido
            ]},
        ]
        count = _detect_displacement_events("A", snapshots, threshold=0.2)
        assert count >= 1

    def test_social_metrics_single_bird(self):
        """Con 1 sola ave, métricas sociales = 0."""
        snapshots = [
            {"tracks": [{"bird_id": "A", "center": [0.5, 0.5]}]},
        ]
        cohesion, centrality = _compute_social_metrics("A", snapshots)
        assert cohesion == 0.0
        assert centrality == 0.0
