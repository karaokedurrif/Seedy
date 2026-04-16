"""Seedy Backend — Motor ML adaptativo sobre datos conductuales.

Aprende patrones individuales (por ave) y de grupo (por gallinero)
a partir de los datos acumulados en behavior_events/ (JSONL).

Modelos:
  - IndividualModel: rutina diaria (GMM), anomalía (IsolationForest),
    patrón alimentación, predicción de puesta
  - FlockModel: ritmo circadiano, grafo social, jerarquía PageRank
"""

import json
import logging
import pickle
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

ML_MODELS_DIR = Path("data/ml_models")
ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Constantes
MIN_EVENTS_FOR_INDIVIDUAL = 30
MIN_EVENTS_FOR_FLOCK = 100
ANOMALY_CONTAMINATION = 0.05
GMM_MAX_COMPONENTS = 5
PAGERANK_ITERATIONS = 20
PAGERANK_DAMPING = 0.85


class IndividualModel:
    """Modelo ML para un ave individual."""

    def __init__(self, bird_id: str):
        self.bird_id = bird_id
        self._zone_gmm = None
        self._isolation_forest = None
        self._scaler = None
        self._baseline_features: np.ndarray | None = None
        self._feeding_pattern: dict[str, Any] = {
            "hours": [], "durations": [], "frequency_per_day": 0,
        }
        self._fitted = False

    def fit(self, events: list[dict]):
        """Entrena el modelo con eventos históricos del ave."""
        features = self._extract_features(events)
        if len(features) < MIN_EVENTS_FOR_INDIVIDUAL:
            return

        try:
            from sklearn.mixture import GaussianMixture
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            logger.warning("[BehaviorML] scikit-learn no disponible")
            return

        # Normalizar
        self._scaler = StandardScaler()
        scaled = self._scaler.fit_transform(features)
        self._baseline_features = np.mean(scaled, axis=0)

        # Rutina espacial: GMM sobre (zona, hora)
        zone_hour = self._extract_zone_hour(events)
        if len(zone_hour) > MIN_EVENTS_FOR_INDIVIDUAL:
            n_comp = min(GMM_MAX_COMPONENTS, len(zone_hour) // 5)
            if n_comp >= 1:
                self._zone_gmm = GaussianMixture(n_components=n_comp, random_state=42)
                self._zone_gmm.fit(zone_hour)

        # Isolation Forest para anomalías
        self._isolation_forest = IsolationForest(
            n_estimators=50,
            contamination=ANOMALY_CONTAMINATION,
            random_state=42,
        )
        self._isolation_forest.fit(scaled)

        self._fit_feeding_pattern(events)
        self._fitted = True

    def anomaly_score(self, snapshot: dict) -> float:
        """Score 0-1 de anomalía (1 = muy anómalo)."""
        if not self._fitted or self._isolation_forest is None or self._scaler is None:
            return 0.0
        try:
            features = self._extract_single_features(snapshot)
            scaled = self._scaler.transform([features])
            raw = -self._isolation_forest.score_samples(scaled)[0]
            return float(min(1.0, max(0.0, (raw + 0.5) / 1.0)))
        except Exception:
            return 0.0

    def predict_laying(self, snapshot: dict) -> float:
        """Probabilidad de puesta en las próximas 24h."""
        if not self._fitted:
            return 0.0

        nesting_baseline = self._get_baseline("zone_nido_pct")
        nesting_ratio = snapshot.get("zone_nido_pct", 0) / max(nesting_baseline, 0.01)
        hour = datetime.now().hour
        hour_factor = 1.0 if 6 <= hour <= 14 else 0.3
        feeding_anomaly = self._feeding_anomaly(snapshot)

        return min(1.0, 0.4 * min(nesting_ratio / 3.0, 1.0) + 0.3 * hour_factor + 0.3 * feeding_anomaly)

    def explain_anomaly(self, snapshot: dict) -> str:
        """Explicación textual de la anomalía detectada."""
        if self._baseline_features is None or self._scaler is None:
            return "sin_baseline"

        features = self._extract_single_features(snapshot)
        scaled = self._scaler.transform([features])
        diff = scaled[0] - self._baseline_features
        names = ["speed", "distance", "comedero", "bebedero", "aseladero",
                 "nido", "libre", "social", "interactions", "hour"]
        max_idx = int(np.argmax(np.abs(diff)))
        direction = "alto" if diff[max_idx] > 0 else "bajo"
        return f"{names[max_idx]}_{direction}"

    def get_profile_summary(self) -> dict:
        """Resumen del perfil ML del ave."""
        return {
            "bird_id": self.bird_id,
            "fitted": self._fitted,
            "feeding_pattern": self._feeding_pattern,
            "has_zone_gmm": self._zone_gmm is not None,
            "has_isolation_forest": self._isolation_forest is not None,
        }

    def _get_baseline(self, feature_name: str) -> float:
        """Devuelve valor baseline de un feature."""
        idx_map = {
            "zone_nido_pct": 5, "zone_comedero_pct": 2,
            "zone_bebedero_pct": 3, "avg_speed": 0,
        }
        idx = idx_map.get(feature_name, -1)
        if idx >= 0 and self._baseline_features is not None and idx < len(self._baseline_features):
            return float(self._baseline_features[idx])
        return 0.0

    def _feeding_anomaly(self, snapshot: dict) -> float:
        """Desviación del patrón alimentario (0-1)."""
        feeding_time = snapshot.get("zone_comedero_pct", 0)
        baseline = self._get_baseline("zone_comedero_pct")
        if baseline == 0:
            return 0.0
        ratio = abs(feeding_time - baseline) / max(abs(baseline), 0.01)
        return min(1.0, ratio / 2.0)

    def _fit_feeding_pattern(self, events: list[dict]):
        """Ajusta patrón de alimentación desde los eventos."""
        hours = []
        for e in events:
            if e.get("zone_comedero_pct", 0) > 0.1:
                try:
                    ts = e.get("ts", e.get("timestamp", ""))
                    if isinstance(ts, str) and ts:
                        h = datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
                        hours.append(h)
                except Exception:
                    pass
        self._feeding_pattern["hours"] = hours
        if hours:
            self._feeding_pattern["frequency_per_day"] = len(hours) / max(1, len(events) // 1440)

    @staticmethod
    def _extract_features(events: list[dict]) -> np.ndarray:
        """Vector de features numéricas por evento."""
        rows = []
        for e in events:
            ts_str = e.get("ts", e.get("timestamp", "2026-01-01"))
            try:
                hour = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).hour / 24.0
            except Exception:
                hour = 0.0
            rows.append([
                e.get("avg_speed", 0),
                e.get("distance_moved", 0),
                e.get("zone_comedero_pct", 0),
                e.get("zone_bebedero_pct", 0),
                e.get("zone_aseladero_pct", 0),
                e.get("zone_nido_pct", 0),
                e.get("zone_libre_pct", 0),
                e.get("social_proximity", 0),
                e.get("interactions_count", 0),
                hour,
            ])
        return np.array(rows, dtype=np.float64)

    @staticmethod
    def _extract_single_features(snapshot: dict) -> list[float]:
        """Extrae features de un solo snapshot."""
        ts_str = snapshot.get("ts", snapshot.get("timestamp", ""))
        try:
            hour = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).hour / 24.0
        except Exception:
            hour = datetime.now().hour / 24.0
        return [
            snapshot.get("avg_speed", 0),
            snapshot.get("distance_moved", 0),
            snapshot.get("zone_comedero_pct", 0),
            snapshot.get("zone_bebedero_pct", 0),
            snapshot.get("zone_aseladero_pct", 0),
            snapshot.get("zone_nido_pct", 0),
            snapshot.get("zone_libre_pct", 0),
            snapshot.get("social_proximity", 0),
            snapshot.get("interactions_count", 0),
            hour,
        ]

    @staticmethod
    def _extract_zone_hour(events: list[dict]) -> np.ndarray:
        """Extrae (zone_code, hour) para GMM."""
        zone_map = {"comedero": 0, "bebedero": 1, "aseladero": 2, "nido": 3, "zona_libre": 4}
        rows = []
        for e in events:
            zone = e.get("zone", "zona_libre")
            zone_code = zone_map.get(zone, 4)
            ts_str = e.get("ts", e.get("timestamp", ""))
            try:
                hour = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).hour
            except Exception:
                hour = 12
            rows.append([zone_code, hour])
        return np.array(rows, dtype=np.float64) if rows else np.empty((0, 2))


class FlockModel:
    """Modelo ML para el comportamiento del grupo en un gallinero."""

    def __init__(self, gallinero_id: str):
        self.gallinero_id = gallinero_id
        self._circadian_profile: np.ndarray | None = None
        self._social_graph: dict[tuple[str, str], float] = {}
        self._hierarchy: list[dict] = []
        self._fitted = False

    def fit(self, events: list[dict]):
        """Entrena modelo de grupo."""
        # Perfil circadiano
        hourly_activity: dict[int, list[float]] = defaultdict(list)
        for e in events:
            ts_str = e.get("ts", e.get("timestamp", ""))
            try:
                hour = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).hour
            except Exception:
                continue
            activity = e.get("avg_speed", 0) + e.get("interactions_count", 0) * 0.1
            hourly_activity[hour].append(activity)

        self._circadian_profile = np.array([
            float(np.mean(hourly_activity.get(h, [0]))) for h in range(24)
        ])

        # Grafo social
        self._build_social_graph(events)
        self._fitted = True

    def check_group_anomaly(self, snapshot: dict) -> Optional[dict]:
        """Detecta anomalías a nivel de grupo."""
        if self._circadian_profile is None:
            return None

        hour = datetime.now().hour
        expected = self._circadian_profile[hour]
        actual = snapshot.get("group_avg_speed", 0)

        std = max(float(np.std(self._circadian_profile)), 0.01)
        z_score = abs(actual - expected) / std

        if z_score > 2.5:
            return {
                "gallinero_id": self.gallinero_id,
                "type": "circadian_deviation",
                "z_score": round(z_score, 2),
                "expected": round(expected, 4),
                "actual": round(actual, 4),
                "hour": hour,
                "direction": "hyperactive" if actual > expected else "lethargic",
            }
        return None

    def get_hierarchy(self) -> list[dict]:
        """Ranking de dominancia por PageRank."""
        return self._hierarchy

    def _build_social_graph(self, events: list[dict]):
        """Grafo social desde co-ocurrencia en zona."""
        pairs: dict[tuple[str, str], float] = defaultdict(float)
        for e in events:
            bird_id = e.get("bird_id", "")
            neighbors = e.get("nearby_birds", [])
            if not bird_id:
                continue
            for n in neighbors:
                key = tuple(sorted([bird_id, n]))
                pairs[key] += 1.0

        self._social_graph = dict(pairs)

        # PageRank simplificado
        nodes: set[str] = set()
        for a, b in pairs:
            nodes.add(a)
            nodes.add(b)

        if not nodes:
            self._hierarchy = []
            return

        rank = {n: 1.0 / len(nodes) for n in nodes}

        for _ in range(PAGERANK_ITERATIONS):
            new_rank: dict[str, float] = {}
            for node in nodes:
                incoming = sum(
                    pairs.get(tuple(sorted([node, other])), 0) * rank[other]
                    for other in nodes if other != node
                )
                new_rank[node] = (1 - PAGERANK_DAMPING) / len(nodes) + PAGERANK_DAMPING * incoming
            total = sum(new_rank.values()) or 1.0
            rank = {k: v / total for k, v in new_rank.items()}

        self._hierarchy = sorted(
            [{"bird_id": k, "dominance_score": round(v, 6)} for k, v in rank.items()],
            key=lambda x: -x["dominance_score"],
        )


class BehaviorMLEngine:
    """Motor principal: entrena modelos y ejecuta inferencia."""

    def __init__(self):
        self._individual_models: dict[str, IndividualModel] = {}
        self._flock_models: dict[str, FlockModel] = {}
        self._recent_anomalies: list[dict] = []
        self._load_models()

    async def train_all(self, gallinero_id: str, days: int = 14) -> dict:
        """Entrena/actualiza todos los modelos con los últimos N días."""
        events = self._load_events(gallinero_id, days)
        if len(events) < MIN_EVENTS_FOR_FLOCK:
            return {"status": "insufficient_data", "events": len(events)}

        # Modelos individuales
        birds = self._group_by_bird(events)
        trained_birds = 0
        for bird_id, bird_events in birds.items():
            if len(bird_events) >= MIN_EVENTS_FOR_INDIVIDUAL:
                model = self._get_or_create_individual(bird_id)
                model.fit(bird_events)
                trained_birds += 1

        # Modelo de rebaño
        flock = self._get_or_create_flock(gallinero_id)
        flock.fit(events)

        self._save_models()
        return {
            "status": "trained",
            "gallinero_id": gallinero_id,
            "individuals_trained": trained_birds,
            "total_birds": len(birds),
            "events_used": len(events),
        }

    async def analyze_snapshot(self, gallinero_id: str, snapshot: dict) -> dict:
        """Analiza un snapshot y devuelve anomalías/predicciones."""
        results: dict[str, list] = {
            "anomalies": [],
            "predictions": [],
            "insights": [],
        }

        bird_id = snapshot.get("bird_id", "")
        if bird_id and bird_id in self._individual_models:
            model = self._individual_models[bird_id]
            score = model.anomaly_score(snapshot)
            if score > 0.8:
                anomaly = {
                    "bird_id": bird_id,
                    "score": round(score, 3),
                    "type": model.explain_anomaly(snapshot),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                results["anomalies"].append(anomaly)
                self._recent_anomalies.append(anomaly)
                # Mantener buffer limitado
                if len(self._recent_anomalies) > 500:
                    self._recent_anomalies = self._recent_anomalies[-250:]

            laying_prob = model.predict_laying(snapshot)
            if laying_prob > 0.7:
                results["predictions"].append({
                    "bird_id": bird_id,
                    "type": "laying_likely",
                    "probability": round(laying_prob, 3),
                    "window": "next_24h",
                })

        flock = self._flock_models.get(gallinero_id)
        if flock:
            group_anomaly = flock.check_group_anomaly(snapshot)
            if group_anomaly:
                results["anomalies"].append(group_anomaly)

        return results

    def get_recent_anomalies(self, gallinero_id: str, hours: int = 24) -> list[dict]:
        """Anomalías recientes."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()
        return [
            a for a in self._recent_anomalies
            if a.get("timestamp", "") >= cutoff_str
        ]

    def get_active_predictions(self, gallinero_id: str) -> list[dict]:
        """Predicciones activas: puesta probable, estrés inminente, anomalía de grupo."""
        predictions: list[dict] = []
        now = datetime.now(timezone.utc)
        hour = now.hour

        # Cargar últimas 4h de eventos
        events = self._load_events(gallinero_id, days=1)
        cutoff = now - timedelta(hours=4)
        events = [
            e for e in events
            if e.get("ts", "") >= cutoff.isoformat()
        ]
        if len(events) < 10:
            return predictions

        # Agregar features por track
        track_feats = self._aggregate_track_features(events)

        for track_id, feat in track_feats.items():
            bird_id = feat.get("bird_id", "")
            label = bird_id if bird_id else f"track_{track_id}"

            # ── Predicción de PUESTA ──
            nesting_pct = feat.get("zone_nido_pct", 0)
            feeding_pct = feat.get("zone_comedero_pct", 0)
            morning_factor = 1.0 if 6 <= hour <= 14 else 0.3

            laying_score = (
                0.45 * min(nesting_pct / 0.15, 1.0)
                + 0.25 * morning_factor
                + 0.15 * min(feeding_pct / 0.08, 1.0)
                + 0.15 * feat.get("nesting_trend", 0)
            )

            # Si hay modelo individual entrenado, ponderar con su predicción
            if bird_id and bird_id in self._individual_models:
                model = self._individual_models[bird_id]
                if model._fitted:
                    ml_score = model.predict_laying(feat)
                    laying_score = 0.6 * ml_score + 0.4 * laying_score

            if laying_score > 0.55:
                evidence = []
                if nesting_pct > 0.10:
                    evidence.append(f"nido {nesting_pct:.0%} del tiempo")
                if feeding_pct > 0.05:
                    evidence.append(f"alimentación {feeding_pct:.0%}")
                if morning_factor > 0.5:
                    evidence.append("horario matutino típico de puesta")
                predictions.append({
                    "type": "laying_likely",
                    "bird_id": label,
                    "probability": round(min(1.0, laying_score), 3),
                    "window": "next_24h",
                    "evidence": evidence,
                    "timestamp": now.isoformat(),
                })

            # ── Predicción de ESTRÉS ──
            isolation_pct = feat.get("isolation_pct", 0)
            activity = feat.get("activity_anomaly", 0)
            zone_stuck = feat.get("zone_diversity_drop", 0)
            feeding_low = 1.0 - min(feeding_pct / 0.08, 1.0) if feeding_pct < 0.08 else 0

            stress_score = (
                0.35 * min(isolation_pct / 0.5, 1.0)
                + 0.25 * feeding_low
                + 0.20 * min(activity, 1.0)
                + 0.20 * zone_stuck
            )

            if stress_score > 0.55:
                evidence = []
                if isolation_pct > 0.30:
                    evidence.append(f"aislada {isolation_pct:.0%} del tiempo")
                if feeding_low > 0.3:
                    evidence.append(f"baja alimentación ({feeding_pct:.0%})")
                if activity > 0.3:
                    evidence.append("actividad anómala")
                if zone_stuck > 0.5:
                    evidence.append("permanece en una sola zona")
                predictions.append({
                    "type": "stress_likely",
                    "bird_id": label,
                    "probability": round(min(1.0, stress_score), 3),
                    "window": "current",
                    "evidence": evidence,
                    "timestamp": now.isoformat(),
                })

        # ── Anomalía de GRUPO (circadiano) ──
        flock = self._flock_models.get(gallinero_id)
        if flock and flock._circadian_profile is not None and events:
            recent_count = [e.get("active_count", 0) for e in events[-10:]]
            avg_active = sum(recent_count) / max(len(recent_count), 1)
            expected = float(flock._circadian_profile[hour])
            std = max(float(np.std(flock._circadian_profile)), 0.5)
            z = abs(avg_active - expected) / std
            if z > 2.0 and expected > 0.5:  # Solo si hay baseline significativo
                direction = "alta" if avg_active > expected else "baja"
                predictions.append({
                    "type": "flock_anomaly",
                    "gallinero_id": gallinero_id,
                    "probability": round(min(1.0, z / 4.0), 3),
                    "window": "current",
                    "evidence": [
                        f"actividad {direction} ({avg_active:.1f} vs esperado {expected:.1f})",
                        f"z-score: {z:.2f}",
                    ],
                    "timestamp": now.isoformat(),
                })

        predictions.sort(key=lambda p: -p.get("probability", 0))
        return predictions[:10]  # Top 10 más relevantes

    def _aggregate_track_features(self, events: list[dict]) -> dict[int, dict]:
        """Agrega eventos raw del event store en features por track."""
        tracks: dict[int, dict[str, Any]] = {}
        for e in events:
            track_list = e.get("tracks", [])
            active = len(track_list)
            for t in track_list:
                tid = t.get("track_id")
                if tid is None:
                    continue
                if tid not in tracks:
                    tracks[tid] = {
                        "snapshots": 0, "bird_id": "",
                        "zones": Counter(), "centers": [],
                        "nearby_counts": [], "zone_seq": [],
                    }
                entry = tracks[tid]
                entry["snapshots"] += 1
                if t.get("bird_id"):
                    entry["bird_id"] = t["bird_id"]
                zone = t.get("zone", "zona_libre")
                entry["zones"][zone] += 1
                entry["zone_seq"].append(zone)
                entry["centers"].append(t.get("center", [0.5, 0.5]))
                entry["nearby_counts"].append(max(0, active - 1))

        result: dict[int, dict] = {}
        for tid, data in tracks.items():
            total = data["snapshots"]
            if total < 10:
                continue  # Ignorar tracks efímeros (<10 min)
            zones = data["zones"]

            feat: dict[str, Any] = {
                "bird_id": data["bird_id"],
                "snapshots": total,
                "zone_nido_pct": zones.get("nido", 0) / total,
                "zone_comedero_pct": zones.get("comedero", 0) / total,
                "zone_bebedero_pct": zones.get("bebedero", 0) / total,
                "zone_aseladero_pct": zones.get("aseladero", 0) / total,
                "zone_libre_pct": zones.get("zona_libre", 0) / total,
            }

            # Velocidad estimada desde deltas de centro
            centers = data["centers"]
            if len(centers) > 1:
                deltas = [
                    ((c2[0] - c1[0]) ** 2 + (c2[1] - c1[1]) ** 2) ** 0.5
                    for c1, c2 in zip(centers[:-1], centers[1:])
                ]
                feat["avg_speed"] = sum(deltas) / len(deltas)
                feat["distance_moved"] = sum(deltas)
            else:
                feat["avg_speed"] = 0.0
                feat["distance_moved"] = 0.0

            # Contexto social
            nearby = data["nearby_counts"]
            feat["social_proximity"] = sum(nearby) / len(nearby) if nearby else 0
            feat["isolation_pct"] = (
                sum(1 for n in nearby if n == 0) / len(nearby) if nearby else 0
            )

            # Diversidad de zonas (0-1)
            used = sum(1 for v in zones.values() if v / total > 0.05)
            feat["zone_diversity_drop"] = max(0.0, 1.0 - used / 5.0)

            # Anomalía de actividad (>0.05 hiper, <0.002 letárgico)
            speed = feat["avg_speed"]
            if speed > 0.05:
                feat["activity_anomaly"] = min(1.0, (speed - 0.05) / 0.10)
            elif speed < 0.002:
                feat["activity_anomaly"] = min(1.0, (0.002 - speed) / 0.002)
            else:
                feat["activity_anomaly"] = 0.0

            # Tendencia de nido: segunda mitad vs primera mitad
            half = total // 2
            if half > 2:
                seq = data["zone_seq"]
                first_nido = sum(1 for z in seq[:half] if z == "nido") / half
                second_nido = sum(1 for z in seq[half:] if z == "nido") / max(len(seq) - half, 1)
                feat["nesting_trend"] = min(1.0, max(0.0, second_nido - first_nido))
            else:
                feat["nesting_trend"] = 0.0

            result[tid] = feat
        return result

    def _get_or_create_individual(self, bird_id: str) -> IndividualModel:
        if bird_id not in self._individual_models:
            self._individual_models[bird_id] = IndividualModel(bird_id)
        return self._individual_models[bird_id]

    def _get_or_create_flock(self, gallinero_id: str) -> FlockModel:
        if gallinero_id not in self._flock_models:
            self._flock_models[gallinero_id] = FlockModel(gallinero_id)
        return self._flock_models[gallinero_id]

    @staticmethod
    def _group_by_bird(events: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for e in events:
            # Events from behavior store contain tracks[]
            for track in e.get("tracks", []):
                bid = track.get("bird_id", "")
                if bid:
                    # Merge track data into event-level dict for features
                    merged = {**e, **track}
                    groups[bid].append(merged)
        return groups

    @staticmethod
    def _load_events(gallinero_id: str, days: int) -> list[dict]:
        """Carga eventos JSONL del behavior event store."""
        from services.behavior_event_store import get_event_store
        store = get_event_store()
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        return store.query(gallinero_id, start, end)

    def _save_models(self):
        """Persiste modelos a disco."""
        try:
            path = ML_MODELS_DIR / "behavior_models.pkl"
            data = {
                "individual": self._individual_models,
                "flock": self._flock_models,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(path, "wb") as f:
                pickle.dump(data, f)
            logger.info(f"[BehaviorML] Models saved ({len(self._individual_models)} individual, {len(self._flock_models)} flock)")
        except Exception as e:
            logger.warning(f"[BehaviorML] Save failed: {e}")

    def _load_models(self):
        """Carga modelos desde disco si existen."""
        path = ML_MODELS_DIR / "behavior_models.pkl"
        if not path.exists():
            return
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)  # noqa: S301
            self._individual_models = data.get("individual", {})
            self._flock_models = data.get("flock", {})
            logger.info(
                f"[BehaviorML] Models loaded ({len(self._individual_models)} individual, "
                f"{len(self._flock_models)} flock)"
            )
        except Exception as e:
            logger.warning(f"[BehaviorML] Load failed: {e}")


# ── Singleton ──

_engine: BehaviorMLEngine | None = None


def get_behavior_ml_engine() -> BehaviorMLEngine:
    global _engine
    if _engine is None:
        _engine = BehaviorMLEngine()
    return _engine
