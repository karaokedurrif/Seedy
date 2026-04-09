"""Seedy Backend — Behavior Baseline

Gestiona histórico de features para comparación individual y de grupo.
Persistencia en JSON en data/behavior_baselines/ (mismo patrón que birds_registry.json).
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import get_settings
from services.behavior_features import BirdBehaviorFeatures

logger = logging.getLogger(__name__)

_settings = get_settings()
_BASE_PATH = Path(_settings.behavior_baseline_path)


class BehaviorBaseline:
    """Almacena y consulta baselines conductuales."""

    def __init__(self, base_path: str | None = None):
        self._base = Path(base_path) if base_path else _BASE_PATH
        self._base.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}  # bird_id → baseline data

    def _load(self, bird_id: str) -> dict:
        if bird_id in self._cache:
            return self._cache[bird_id]
        filepath = self._base / f"{bird_id}.json"
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cache[bird_id] = data
                return data
            except Exception as e:
                logger.warning(f"[Baseline] Error loading {filepath}: {e}")
        return {"bird_id": bird_id, "windows": {}, "updated_at": None}

    def _save(self, bird_id: str, data: dict):
        filepath = self._base / f"{bird_id}.json"
        try:
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            self._cache[bird_id] = data
        except Exception as e:
            logger.warning(f"[Baseline] Error saving {filepath}: {e}")

    def get_individual_baseline(
        self,
        bird_id: str,
        window: str = "24h",
    ) -> Optional[dict]:
        """Devuelve baseline promedio de un ave para una ventana."""
        data = self._load(bird_id)
        return data.get("windows", {}).get(window)

    def get_group_baseline(
        self,
        gallinero_id: str,
        window: str = "24h",
    ) -> dict[str, float]:
        """Devuelve medias por feature de todas las aves del gallinero."""
        group_data: dict[str, list[float]] = {}

        if not self._base.exists():
            return {}

        for filepath in self._base.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                baseline = data.get("windows", {}).get(window)
                if not baseline:
                    continue
                # Solo aves de este gallinero
                if baseline.get("gallinero_id") != gallinero_id:
                    continue
                for key, val in baseline.items():
                    if isinstance(val, (int, float)):
                        group_data.setdefault(key, []).append(float(val))
            except Exception:
                continue

        return {k: sum(v) / len(v) for k, v in group_data.items() if v}

    def update_baseline(self, features: BirdBehaviorFeatures) -> None:
        """Actualiza baseline con nuevas features (media móvil exponencial)."""
        if features.data_completeness < 0.4:
            logger.debug(f"[Baseline] Skipping update for {features.bird_id}: completeness={features.data_completeness}")
            return

        window = _window_label(features.window_start, features.window_end)
        data = self._load(features.bird_id)

        if "windows" not in data:
            data["windows"] = {}

        existing = data["windows"].get(window)
        feat_dict = _features_to_dict(features)

        if existing and existing.get("n_updates", 0) > 0:
            # Media móvil exponencial (alpha=0.3 — da más peso a lo reciente)
            alpha = 0.3
            merged = {}
            for key in feat_dict:
                old_val = existing.get(key, feat_dict[key])
                new_val = feat_dict[key]
                if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                    merged[key] = round(alpha * new_val + (1 - alpha) * old_val, 4)
                else:
                    merged[key] = new_val
            merged["n_updates"] = existing.get("n_updates", 0) + 1
            merged["gallinero_id"] = features.gallinero_id
            data["windows"][window] = merged
        else:
            feat_dict["n_updates"] = 1
            feat_dict["gallinero_id"] = features.gallinero_id
            data["windows"][window] = feat_dict

        self._save(features.bird_id, data)

    def has_sufficient_history(
        self,
        bird_id: str,
        min_windows: int | None = None,
    ) -> bool:
        """Verifica si hay suficiente historial para inferencias con baseline."""
        if min_windows is None:
            min_windows = _settings.behavior_min_history_windows
        data = self._load(bird_id)
        windows = data.get("windows", {})
        # Contar ventanas con al menos 3 updates
        sufficient = sum(1 for w in windows.values() if w.get("n_updates", 0) >= 3)
        return sufficient >= min_windows

    def compute_delta(
        self,
        features: BirdBehaviorFeatures,
    ) -> float:
        """Calcula desviación de features actuales respecto al baseline."""
        window = _window_label(features.window_start, features.window_end)
        baseline = self.get_individual_baseline(features.bird_id, window)
        if not baseline or baseline.get("n_updates", 0) < 3:
            return 0.0

        # Comparar features clave
        keys = [
            "feeder_total_time_sec", "drinker_total_time_sec",
            "distance_traveled", "activity_score",
            "inactivity_time_sec", "zone_switch_count",
        ]
        deltas = []
        for key in keys:
            current = getattr(features, key, 0)
            base_val = baseline.get(key, 0)
            if base_val > 0:
                deltas.append(abs(current - base_val) / base_val)

        return round(sum(deltas) / len(deltas), 4) if deltas else 0.0


def _window_label(start: datetime, end: datetime) -> str:
    """Genera etiqueta de ventana: '1h', '6h', '24h'."""
    hours = (end - start).total_seconds() / 3600
    if hours <= 1.5:
        return "1h"
    if hours <= 8:
        return "6h"
    return "24h"


def _features_to_dict(features: BirdBehaviorFeatures) -> dict:
    """Convierte features a dict, excluyendo campos no numéricos."""
    result = {}
    for key, val in asdict(features).items():
        if key in ("bird_id", "gallinero_id", "window_start", "window_end", "climate_data_available"):
            continue
        if isinstance(val, (int, float)) and val is not None:
            result[key] = val
    return result


    def prune_stale(self, max_age_days: int = 30) -> int:
        """Elimina baselines de aves que no se han actualizado en max_age_days."""
        if not self._base.exists():
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cutoff_iso = cutoff.isoformat()
        pruned = 0

        for filepath in list(self._base.glob("*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                updated_at = data.get("updated_at", "")
                if updated_at and updated_at < cutoff_iso:
                    filepath.unlink()
                    bird_id = filepath.stem
                    self._cache.pop(bird_id, None)
                    pruned += 1
            except Exception as e:
                logger.debug(f"[Baseline] Prune skip {filepath}: {e}")

        return pruned


# ── Singleton ──

_baseline: BehaviorBaseline | None = None


def get_baseline() -> BehaviorBaseline:
    global _baseline
    if _baseline is None:
        _baseline = BehaviorBaseline()
    return _baseline
