"""
Seedy Backend — ML Adaptativo conductual

Modelos ligeros que aprenden patrones individuales y de rebaño:

Individual (1 por ave):
  - Rutina espacial diaria (GMM sobre zonas × hora)
  - Patrón de alimentación (frecuencia, duración, hora pico)
  - Detector de anomalías (IsolationForest, contamination=5%)
  - Predictor de puesta (correlación nesting + feeding → huevo 24h)

Rebaño (1 por gallinero):
  - Perfil circadiano (actividad media × hora, 24 bins)
  - Grafo social (co-ocurrencia en zona → PageRank de dominancia)
  - Anomalía de grupo (z-score > 2.5 del perfil circadiano)

Entrenamiento: cada 6h automático, ventana de 14 días.
Persistencia: pickle en data/ml_models/.
"""

import json
import logging
import os
import pickle
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

ML_MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", "data/ml_models"))
BEHAVIOR_DATA_DIR = Path(os.getenv("BEHAVIOR_DATA_DIR", "data/behavior_events"))
MIN_EVENTS_TO_TRAIN = 100
TRAINING_WINDOW_DAYS = 14
ANOMALY_Z_THRESHOLD = 2.5


class IndividualModel:
    """Modelo conductual individual para un ave."""

    def __init__(self, bird_id: str):
        self.bird_id = bird_id
        self.routine_model = None      # GMM de zonas × hora
        self.anomaly_model = None      # IsolationForest
        self.feeding_pattern = None    # Stats de alimentación
        self.last_trained: Optional[float] = None
        self.event_count = 0

    def train(self, events: List[dict]) -> bool:
        """Entrena modelos individuales con eventos del ave."""
        if len(events) < MIN_EVENTS_TO_TRAIN:
            return False

        try:
            from sklearn.mixture import GaussianMixture
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler

            # Extraer features: [hora, zona_id, actividad, duración_zona]
            features = []
            for e in events:
                ts = e.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts)
                        hour = dt.hour + dt.minute / 60.0
                    except (ValueError, TypeError):
                        continue
                else:
                    hour = datetime.fromtimestamp(ts).hour

                zone_id = self._zone_to_id(e.get("zone", "zona_libre"))
                activity = e.get("activity_level", 0.5)
                features.append([hour, zone_id, activity])

            if len(features) < MIN_EVENTS_TO_TRAIN:
                return False

            X = np.array(features)

            # GMM: patrones de rutina (3-5 componentes)
            n_components = min(5, max(2, len(features) // 50))
            self.routine_model = GaussianMixture(
                n_components=n_components,
                covariance_type="full",
                random_state=42,
            )
            self.routine_model.fit(X)

            # IsolationForest: detector de anomalías
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            self.anomaly_model = IsolationForest(
                contamination=0.05,
                random_state=42,
                n_estimators=100,
            )
            self.anomaly_model.fit(X_scaled)
            self._scaler = scaler

            # Patrón de alimentación
            feeding_events = [e for e in events if e.get("zone") == "comedero"]
            if feeding_events:
                hours = [
                    datetime.fromtimestamp(e["timestamp"]).hour
                    if isinstance(e["timestamp"], (int, float))
                    else datetime.fromisoformat(e["timestamp"]).hour
                    for e in feeding_events
                    if e.get("timestamp")
                ]
                if hours:
                    self.feeding_pattern = {
                        "peak_hour": max(set(hours), key=hours.count),
                        "frequency": len(feeding_events) / max(1, TRAINING_WINDOW_DAYS),
                        "total": len(feeding_events),
                    }

            self.last_trained = time.time()
            self.event_count = len(events)
            logger.info(f"🧠 Modelo individual entrenado: {self.bird_id} ({len(events)} eventos)")
            return True

        except ImportError:
            logger.warning("scikit-learn no disponible — ML deshabilitado")
            return False
        except Exception as e:
            logger.error(f"Error entrenando modelo individual {self.bird_id}: {e}")
            return False

    def predict_anomaly(self, event: dict) -> Optional[dict]:
        """Evalúa si un evento es anómalo."""
        if self.anomaly_model is None:
            return None

        try:
            ts = event.get("timestamp", time.time())
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
                hour = dt.hour + dt.minute / 60.0
            else:
                hour = datetime.fromtimestamp(ts).hour

            zone_id = self._zone_to_id(event.get("zone", "zona_libre"))
            activity = event.get("activity_level", 0.5)

            X = np.array([[hour, zone_id, activity]])
            X_scaled = self._scaler.transform(X)
            score = self.anomaly_model.decision_function(X_scaled)[0]
            is_anomaly = self.anomaly_model.predict(X_scaled)[0] == -1

            if is_anomaly:
                return {
                    "bird_id": self.bird_id,
                    "type": "individual_anomaly",
                    "score": float(score),
                    "event": event,
                    "timestamp": datetime.now().isoformat(),
                }
            return None
        except Exception:
            return None

    @staticmethod
    def _zone_to_id(zone: str) -> int:
        zones = {"comedero": 0, "bebedero": 1, "aseladero": 2, "nido": 3, "zona_libre": 4}
        return zones.get(zone, 4)


class FlockModel:
    """Modelo conductual del rebaño (1 por gallinero)."""

    def __init__(self, gallinero_id: str):
        self.gallinero_id = gallinero_id
        self.circadian_profile: Optional[np.ndarray] = None  # 24 bins
        self.circadian_std: Optional[np.ndarray] = None
        self.social_graph: Dict[str, Dict[str, int]] = {}  # bird_a → bird_b → co-occurrences
        self.hierarchy: Dict[str, float] = {}  # bird_id → PageRank score
        self.last_trained: Optional[float] = None

    def train(self, events: List[dict]) -> bool:
        """Entrena modelos de rebaño."""
        if len(events) < MIN_EVENTS_TO_TRAIN:
            return False

        try:
            # Perfil circadiano: actividad media por hora
            hourly_activity = defaultdict(list)
            for e in events:
                ts = e.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        hour = datetime.fromisoformat(ts).hour
                    except (ValueError, TypeError):
                        continue
                else:
                    hour = datetime.fromtimestamp(ts).hour
                hourly_activity[hour].append(e.get("bird_count", e.get("activity_level", 1)))

            self.circadian_profile = np.zeros(24)
            self.circadian_std = np.zeros(24)
            for h in range(24):
                vals = hourly_activity.get(h, [0])
                self.circadian_profile[h] = np.mean(vals)
                self.circadian_std[h] = max(np.std(vals), 0.1)

            # Grafo social: co-ocurrencias en misma zona
            social_graph_tmp = defaultdict(lambda: defaultdict(int))
            zone_snapshots = defaultdict(list)  # timestamp_rounded → [(bird_id, zone)]

            for e in events:
                bird = e.get("bird_id", "")
                zone = e.get("zone", "")
                ts = e.get("timestamp", 0)
                if not bird or not zone:
                    continue
                # Convertir timestamp a unix para agrupar por minuto
                if isinstance(ts, str):
                    try:
                        ts_unix = datetime.fromisoformat(ts).timestamp()
                    except (ValueError, TypeError):
                        continue
                else:
                    ts_unix = float(ts)
                ts_key = int(ts_unix) // 60
                zone_snapshots[ts_key].append((bird, zone))

            for ts_key, entries in zone_snapshots.items():
                by_zone = defaultdict(list)
                for bird, zone in entries:
                    by_zone[zone].append(bird)
                for zone, birds_in_zone in by_zone.items():
                    for i, b1 in enumerate(birds_in_zone):
                        for b2 in birds_in_zone[i + 1:]:
                            social_graph_tmp[b1][b2] += 1
                            social_graph_tmp[b2][b1] += 1

            # Convertir a dict plano para que sea serializable con pickle
            self.social_graph = {k: dict(v) for k, v in social_graph_tmp.items()}

            # PageRank simplificado para jerarquía
            self._compute_hierarchy()

            self.last_trained = time.time()
            logger.info(
                f"🧠 Modelo flock entrenado: {self.gallinero_id} "
                f"({len(events)} eventos, {len(self.social_graph)} aves en grafo)"
            )
            return True

        except Exception as e:
            logger.error(f"Error entrenando modelo flock {self.gallinero_id}: {e}")
            return False

    def detect_group_anomaly(self, current_hour: int, current_activity: float) -> Optional[dict]:
        """Detecta anomalía de grupo por desviación del perfil circadiano."""
        if self.circadian_profile is None:
            return None

        expected = self.circadian_profile[current_hour % 24]
        std = self.circadian_std[current_hour % 24]

        if std > 0:
            z_score = abs(current_activity - expected) / std
            if z_score > ANOMALY_Z_THRESHOLD:
                return {
                    "type": "flock_anomaly",
                    "gallinero": self.gallinero_id,
                    "hour": current_hour,
                    "expected_activity": float(expected),
                    "actual_activity": float(current_activity),
                    "z_score": float(z_score),
                    "timestamp": datetime.now().isoformat(),
                }
        return None

    def _compute_hierarchy(self):
        """PageRank simplificado sobre grafo de co-ocurrencias."""
        birds = list(self.social_graph.keys())
        if not birds:
            self.hierarchy = {}
            return

        n = len(birds)
        bird_idx = {b: i for i, b in enumerate(birds)}
        damping = 0.85
        iterations = 20

        # Matriz de adyacencia normalizada
        matrix = np.zeros((n, n))
        for b1, connections in self.social_graph.items():
            total = sum(connections.values())
            if total > 0:
                for b2, count in connections.items():
                    if b2 in bird_idx:
                        matrix[bird_idx[b1]][bird_idx[b2]] = count / total

        # PageRank iterativo
        ranks = np.ones(n) / n
        for _ in range(iterations):
            new_ranks = (1 - damping) / n + damping * matrix.T @ ranks
            if np.allclose(ranks, new_ranks, atol=1e-6):
                break
            ranks = new_ranks

        self.hierarchy = {birds[i]: float(ranks[i]) for i in range(n)}

    def get_hierarchy(self) -> List[dict]:
        """Jerarquía de dominancia ordenada."""
        return sorted(
            [{"bird_id": bid, "rank": rank} for bid, rank in self.hierarchy.items()],
            key=lambda x: x["rank"],
            reverse=True,
        )


class BehaviorMLEngine:
    """Motor principal de ML adaptativo."""

    def __init__(self):
        ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        BEHAVIOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._individual_models: Dict[str, IndividualModel] = {}
        self._flock_models: Dict[str, FlockModel] = {}
        self._load_models()

    def _load_models(self):
        """Carga modelos persistidos desde disco."""
        for f in ML_MODELS_DIR.glob("individual_*.pkl"):
            try:
                with open(f, "rb") as fh:
                    model = pickle.load(fh)
                    if isinstance(model, IndividualModel):
                        self._individual_models[model.bird_id] = model
            except Exception as e:
                logger.debug(f"Error cargando modelo {f.name}: {e}")

        for f in ML_MODELS_DIR.glob("flock_*.pkl"):
            try:
                with open(f, "rb") as fh:
                    model = pickle.load(fh)
                    if isinstance(model, FlockModel):
                        self._flock_models[model.gallinero_id] = model
            except Exception as e:
                logger.debug(f"Error cargando modelo {f.name}: {e}")

        logger.info(
            f"ML models loaded: {len(self._individual_models)} individual, "
            f"{len(self._flock_models)} flock"
        )

    def _save_models(self):
        """Persiste modelos a disco."""
        for bird_id, model in self._individual_models.items():
            path = ML_MODELS_DIR / f"individual_{bird_id}.pkl"
            with open(path, "wb") as f:
                pickle.dump(model, f)

        for gid, model in self._flock_models.items():
            path = ML_MODELS_DIR / f"flock_{gid}.pkl"
            with open(path, "wb") as f:
                pickle.dump(model, f)

    # Mapeo gallinero → camera_ids (las 3 cámaras cubren el mismo espacio)
    GALLINERO_CAMERAS = {
        "gallinero_palacio": ["sauna_durrif_1", "gallinero_durrif_1", "gallinero_durrif_2"],
        "gallinero_durrif": ["sauna_durrif_1", "gallinero_durrif_1", "gallinero_durrif_2"],
    }

    def _load_events(self, gallinero_id: str, days: int = TRAINING_WINDOW_DAYS) -> List[dict]:
        """Carga eventos de comportamiento desde ficheros JSONL.

        Busca en subdirectorios por camera_id y en ficheros planos.
        Mapea gallinero_id a las cámaras que lo cubren.
        Normaliza snapshots (con tracks[]) a eventos planos por ave.
        """
        raw_records = []
        cutoff = datetime.now() - timedelta(days=days)

        # Resolver qué camera_ids buscar
        camera_ids = self.GALLINERO_CAMERAS.get(gallinero_id, [gallinero_id])

        for cam_id in camera_ids:
            # Buscar en subdirectorio: data/behavior_events/{cam_id}/*.jsonl
            cam_dir = BEHAVIOR_DATA_DIR / cam_id
            if cam_dir.is_dir():
                for f in sorted(cam_dir.glob("*.jsonl")):
                    try:
                        # Filtrar por fecha en nombre (YYYY-MM-DD.jsonl)
                        date_str = f.stem
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                            if file_date < cutoff:
                                continue
                        except ValueError:
                            pass

                        with open(f) as fh:
                            for line in fh:
                                if line.strip():
                                    try:
                                        raw_records.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        continue
                    except Exception:
                        continue

            # Fallback: ficheros planos {cam_id}_*.jsonl en raíz
            for f in sorted(BEHAVIOR_DATA_DIR.glob(f"{cam_id}_*.jsonl")):
                try:
                    with open(f) as fh:
                        for line in fh:
                            if line.strip():
                                try:
                                    raw_records.append(json.loads(line))
                                except json.JSONDecodeError:
                                    continue
                except Exception:
                    continue

        # Normalizar: snapshots con tracks[] → eventos planos por ave
        return self._normalize_events(raw_records)

    @staticmethod
    def _normalize_events(raw_records: List[dict]) -> List[dict]:
        """Convierte snapshots (con tracks[]) en eventos planos para el ML.

        Formato snapshot: {ts, ts_unix, gallinero_id, active_count, tracks[{track_id, bird_id, center, zone, confidence, area}]}
        Formato plano:    {timestamp, bird_id, zone, activity_level, bird_count}
        """
        events = []
        for rec in raw_records:
            tracks = rec.get("tracks")
            if tracks and isinstance(tracks, list):
                # Es un snapshot con tracks → aplanar a 1 evento por track
                ts = rec.get("ts", "")
                ts_unix = rec.get("ts_unix", 0)
                active_count = rec.get("active_count", len(tracks))
                cam_id = rec.get("gallinero_id", "")

                for t in tracks:
                    bird_id = t.get("bird_id", "")
                    if not bird_id:
                        # Usar track_id + cam como ID temporal
                        track_id = t.get("track_id", 0)
                        bird_id = f"{cam_id}_t{track_id}" if cam_id else f"t{track_id}"

                    events.append({
                        "timestamp": ts or ts_unix,
                        "bird_id": bird_id,
                        "zone": t.get("zone", "zona_libre"),
                        "activity_level": min(1.0, t.get("area", 0.01) * 100),
                        "bird_count": active_count,
                        "confidence": t.get("confidence", 0),
                    })
            elif "timestamp" in rec or "ts" in rec:
                # Ya es un evento plano o formato legacy
                if "timestamp" not in rec and "ts" in rec:
                    rec["timestamp"] = rec["ts"]
                events.append(rec)

        return events

    async def train_gallinero(self, gallinero_id: str, days: int = TRAINING_WINDOW_DAYS) -> dict:
        """Entrena todos los modelos para un gallinero."""
        events = self._load_events(gallinero_id, days)

        if not events:
            return {
                "gallinero": gallinero_id,
                "status": "no_data",
                "events_found": 0,
            }

        results = {"gallinero": gallinero_id, "events_total": len(events)}

        # Flock model
        flock = self._flock_models.get(gallinero_id)
        if flock is None:
            flock = FlockModel(gallinero_id)
        flock_ok = flock.train(events)
        self._flock_models[gallinero_id] = flock
        results["flock_trained"] = flock_ok

        # Individual models: agrupar eventos por bird_id
        by_bird = defaultdict(list)
        for e in events:
            bird_id = e.get("bird_id", "")
            if bird_id:
                by_bird[bird_id].append(e)

        individual_results = []
        for bird_id, bird_events in by_bird.items():
            model = self._individual_models.get(bird_id)
            if model is None:
                model = IndividualModel(bird_id)
            ok = model.train(bird_events)
            self._individual_models[bird_id] = model
            individual_results.append({
                "bird_id": bird_id,
                "trained": ok,
                "events": len(bird_events),
            })

        results["individual_models"] = individual_results
        results["individual_trained"] = sum(1 for r in individual_results if r["trained"])

        # Persistir
        self._save_models()

        logger.info(
            f"🧠 ML training complete: {gallinero_id}, "
            f"flock={'OK' if flock_ok else 'SKIP'}, "
            f"{results['individual_trained']}/{len(individual_results)} individual"
        )

        return results

    def get_anomalies(self, gallinero_id: str, hours: int = 24) -> List[dict]:
        """Detecta anomalías recientes."""
        anomalies = []
        events = self._load_events(gallinero_id, days=max(1, hours // 24))

        # Anomalías individuales
        for e in events[-500:]:  # Últimos 500 eventos
            bird_id = e.get("bird_id", "")
            model = self._individual_models.get(bird_id)
            if model:
                anomaly = model.predict_anomaly(e)
                if anomaly:
                    anomalies.append(anomaly)

        # Anomalía de grupo
        flock = self._flock_models.get(gallinero_id)
        if flock:
            now = datetime.now()
            recent = [e for e in events if e.get("timestamp")]
            if recent:
                recent_count = len([
                    e for e in recent[-100:]
                    if e.get("bird_count", 0) > 0
                ])
                group_anomaly = flock.detect_group_anomaly(now.hour, recent_count / max(1, 100))
                if group_anomaly:
                    anomalies.append(group_anomaly)

        return anomalies

    def get_hierarchy(self, gallinero_id: str) -> List[dict]:
        """Jerarquía de dominancia del rebaño."""
        flock = self._flock_models.get(gallinero_id)
        if flock:
            return flock.get_hierarchy()
        return []

    def get_bird_profile(self, bird_id: str) -> dict:
        """Perfil ML de un ave individual."""
        model = self._individual_models.get(bird_id)
        if not model:
            return {"bird_id": bird_id, "status": "no_model"}

        return {
            "bird_id": bird_id,
            "last_trained": datetime.fromtimestamp(model.last_trained).isoformat() if model.last_trained else None,
            "event_count": model.event_count,
            "has_routine_model": model.routine_model is not None,
            "has_anomaly_model": model.anomaly_model is not None,
            "feeding_pattern": model.feeding_pattern,
        }

    def get_predictions(self, gallinero_id: str) -> dict:
        """Predicciones del modelo (puesta, estrés, etc.)."""
        flock = self._flock_models.get(gallinero_id)
        individual_count = sum(
            1 for m in self._individual_models.values()
            if m.routine_model is not None
        )

        return {
            "gallinero": gallinero_id,
            "individual_models_trained": individual_count,
            "flock_model_trained": flock is not None and flock.last_trained is not None,
            "circadian_profile": flock.circadian_profile.tolist() if flock and flock.circadian_profile is not None else None,
            "hierarchy_top5": flock.get_hierarchy()[:5] if flock else [],
        }


# ── Singleton ──
_engine_instance: Optional[BehaviorMLEngine] = None


def get_ml_engine() -> BehaviorMLEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = BehaviorMLEngine()
    return _engine_instance
