"""Seedy Backend — Behavior Features

Calcula features conductuales por ave y ventana temporal.
Consume datos de BehaviorEventStore.query() (ventanas > 2 min)
o de BirdTrack.history directamente (ventanas < 2 min).
"""

import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import get_settings
from services.behavior_event_store import get_event_store

logger = logging.getLogger(__name__)

_settings = get_settings()


@dataclass
class BirdBehaviorFeatures:
    """Features conductuales calculadas para un ave en una ventana temporal."""

    bird_id: str
    gallinero_id: str
    window_start: datetime
    window_end: datetime
    data_completeness: float  # 0.0-1.0

    # Zona comedero
    feeder_visits_count: int = 0
    feeder_total_time_sec: float = 0.0
    feeder_avg_duration_sec: float = 0.0

    # Zona bebedero
    drinker_visits_count: int = 0
    drinker_total_time_sec: float = 0.0

    # Otras zonas
    nest_total_time_sec: float = 0.0
    roost_total_time_sec: float = 0.0
    free_zone_time_sec: float = 0.0

    # Movilidad
    distance_traveled: float = 0.0
    activity_score: float = 0.0
    inactivity_time_sec: float = 0.0
    zone_switch_count: int = 0

    # Social
    proximity_events_count: int = 0
    displacement_events_count: int = 0
    chase_like_events_count: int = 0
    isolation_time_sec: float = 0.0
    group_cohesion_score: float = 0.0
    centrality_score: float = 0.0

    # Ratios vs grupo (se rellenan en compute_group_features)
    feeding_vs_group_ratio: float = 1.0
    drinking_vs_group_ratio: float = 1.0
    mobility_vs_group_ratio: float = 1.0

    # Comparación con baseline propio
    behavior_baseline_delta: float = 0.0

    # Clima
    ambient_temperature: Optional[float] = None
    ambient_humidity: Optional[float] = None
    climate_data_available: bool = False


# ── Mapeo zona → tipo ──
_ZONE_TYPE = {
    "comedero": "feeder",
    "bebedero": "drinker",
    "aseladero": "roost",
    "nido": "nest",
    "zona_libre": "free",
}


def _parse_window(window: str) -> timedelta:
    """Convierte '1h', '6h', '24h' a timedelta."""
    if window.endswith("h"):
        return timedelta(hours=int(window[:-1]))
    if window.endswith("m"):
        return timedelta(minutes=int(window[:-1]))
    return timedelta(hours=24)


_REGISTRY_PATH = Path("/app/data/birds_registry.json")
_bird_id_to_vision: dict[str, str] = {}
_registry_mtime: float = 0.0


def _resolve_ai_vision_id(bird_id: str) -> str | None:
    """Traduce PAL-2026-XXXX → ai_vision_id (bresseblan2, etc).

    Cachea en memoria y refresca si el fichero cambia.
    Devuelve None si no encuentra mapping (el caller usa bird_id tal cual).
    """
    global _bird_id_to_vision, _registry_mtime
    try:
        mtime = _REGISTRY_PATH.stat().st_mtime
        if mtime != _registry_mtime:
            data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
            _bird_id_to_vision = {
                b["bird_id"]: b["ai_vision_id"]
                for b in data.get("birds", [])
                if b.get("bird_id") and b.get("ai_vision_id")
            }
            _registry_mtime = mtime
            logger.debug("Bird registry cache refreshed: %d mappings", len(_bird_id_to_vision))
    except Exception as e:
        logger.warning("Cannot load bird registry for ID resolution: %s", e)
    return _bird_id_to_vision.get(bird_id)


def compute_bird_features(
    bird_id: str,
    gallinero_id: str,
    window: str = "24h",
    end_time: datetime | None = None,
) -> BirdBehaviorFeatures:
    """Calcula features conductuales para un ave en una ventana temporal.

    Consume snapshots del BehaviorEventStore.
    Acepta tanto bird_id (PAL-2026-0011) como ai_vision_id (bresseblan2).
    """
    store = get_event_store()
    end = end_time or datetime.now(timezone.utc)
    delta = _parse_window(window)
    start = end - delta

    # Resolver ai_vision_id: los snapshots almacenan ai_vision_id en el campo bird_id
    search_id = _resolve_ai_vision_id(bird_id) or bird_id

    snapshots = store.query(gallinero_id, start, end)

    # Filtrar solo snapshots que contengan esta ave
    bird_snapshots = []
    for snap in snapshots:
        for track in snap.get("tracks", []):
            if track.get("bird_id") == search_id:
                bird_snapshots.append({
                    "ts_unix": snap["ts_unix"],
                    "center": track["center"],
                    "zone": track["zone"],
                    "confidence": track.get("confidence", 0),
                    "area": track.get("area", 0),
                })
                break

    # Data completeness: snapshots observados vs esperados (1 cada 60s)
    expected = delta.total_seconds() / _settings.behavior_snapshot_interval_sec
    completeness = min(1.0, len(bird_snapshots) / max(expected, 1))

    features = BirdBehaviorFeatures(
        bird_id=bird_id,
        gallinero_id=gallinero_id,
        window_start=start,
        window_end=end,
        data_completeness=round(completeness, 3),
    )

    if not bird_snapshots:
        return features

    # ── Calcular features de zona ──
    zone_visits: dict[str, list[float]] = defaultdict(list)  # zone → [durations]
    prev_zone = ""
    visit_start = 0.0
    interval = _settings.behavior_snapshot_interval_sec

    for i, snap in enumerate(bird_snapshots):
        zone = snap["zone"]
        ts = snap["ts_unix"]

        if zone != prev_zone:
            # Cerrar visita anterior
            if prev_zone and visit_start > 0:
                duration = ts - visit_start
                zone_visits[prev_zone].append(duration)
            visit_start = ts
            features.zone_switch_count += 1
            prev_zone = zone
        elif i == len(bird_snapshots) - 1:
            # Cerrar última visita
            duration = ts - visit_start + interval
            zone_visits[zone].append(duration)

    # Mapear zones a features
    for zone, durations in zone_visits.items():
        total_sec = sum(durations)
        ztype = _ZONE_TYPE.get(zone, "free")
        if ztype == "feeder":
            features.feeder_visits_count = len(durations)
            features.feeder_total_time_sec = total_sec
            features.feeder_avg_duration_sec = total_sec / len(durations) if durations else 0.0
        elif ztype == "drinker":
            features.drinker_visits_count = len(durations)
            features.drinker_total_time_sec = total_sec
        elif ztype == "nest":
            features.nest_total_time_sec = total_sec
        elif ztype == "roost":
            features.roost_total_time_sec = total_sec
        elif ztype == "free":
            features.free_zone_time_sec = total_sec

    # ── Movilidad ──
    total_dist = 0.0
    inactive_time = 0.0
    INACTIVITY_THRESHOLD = 0.005  # normalized distance

    for i in range(1, len(bird_snapshots)):
        prev = bird_snapshots[i - 1]
        curr = bird_snapshots[i]
        dx = curr["center"][0] - prev["center"][0]
        dy = curr["center"][1] - prev["center"][1]
        dist = math.sqrt(dx**2 + dy**2)
        total_dist += dist
        if dist < INACTIVITY_THRESHOLD:
            dt = curr["ts_unix"] - prev["ts_unix"]
            inactive_time += dt

    features.distance_traveled = round(total_dist, 4)
    features.inactivity_time_sec = round(inactive_time, 1)

    # Activity score: distancia normalizada por tiempo
    window_secs = delta.total_seconds()
    features.activity_score = round(total_dist / (window_secs / 3600), 4) if window_secs > 0 else 0.0

    # ── Social: proximidad con otros tracks en los mismos snapshots ──
    displacement_threshold = _settings.behavior_displacement_threshold / 1000.0  # normalize pixels to [0,1]-ish

    proximity_count = 0
    displacement_count = 0
    chase_count = 0
    isolation_time = 0.0

    for snap in snapshots:
        bird_track = None
        other_tracks = []
        for track in snap.get("tracks", []):
            if track.get("bird_id") == bird_id:
                bird_track = track
            else:
                other_tracks.append(track)

        if not bird_track:
            continue

        if not other_tracks:
            isolation_time += interval
            continue

        bc = bird_track["center"]
        min_dist = float("inf")
        for other in other_tracks:
            oc = other["center"]
            d = math.sqrt((bc[0] - oc[0])**2 + (bc[1] - oc[1])**2)
            min_dist = min(min_dist, d)
            if d < displacement_threshold:
                proximity_count += 1

        # Aislamiento: si el ave más cercana está lejos
        if min_dist > displacement_threshold * 3:
            isolation_time += interval

    features.proximity_events_count = proximity_count
    features.isolation_time_sec = round(isolation_time, 1)

    # TODO: displacement_events heurístico — sustituir por detección explícita cuando
    #       bird_tracker.py registre eventos de interacción bird-to-bird
    features.displacement_events_count = _detect_displacement_events(
        bird_id, snapshots, displacement_threshold
    )

    # TODO: chase_like_events usa velocidad de centroide — calibrar umbral con datos reales
    features.chase_like_events_count = _detect_chase_events(
        bird_id, snapshots, _settings.behavior_chase_min_frames
    )

    # ── Cohesión de grupo y centralidad ──
    features.group_cohesion_score, features.centrality_score = _compute_social_metrics(
        bird_id, snapshots
    )

    # ── Clima (snapshot actual de telemetría) ──
    _enrich_climate(features, gallinero_id)

    return features


def _detect_displacement_events(
    bird_id: str,
    snapshots: list[dict],
    threshold: float,
) -> int:
    """Heurística: A se acerca a B, luego B se aleja rápido."""
    count = 0
    # Necesitamos al menos 3 snapshots consecutivos
    for i in range(2, len(snapshots)):
        snap_prev = snapshots[i - 2]
        snap_mid = snapshots[i - 1]
        snap_now = snapshots[i]

        bird_prev = _find_track(bird_id, snap_prev)
        bird_mid = _find_track(bird_id, snap_mid)
        bird_now = _find_track(bird_id, snap_now)
        if not bird_prev or not bird_mid or not bird_now:
            continue

        # Para cada otra ave: ¿bird se acercó y la otra se alejó?
        for other_id in _get_other_ids(bird_id, snap_mid):
            other_prev = _find_track(other_id, snap_prev)
            other_mid = _find_track(other_id, snap_mid)
            other_now = _find_track(other_id, snap_now)
            if not other_prev or not other_mid or not other_now:
                continue

            # Distancia decrece entre prev→mid (bird se acerca)
            d_prev = _dist(bird_prev["center"], other_prev["center"])
            d_mid = _dist(bird_mid["center"], other_mid["center"])
            d_now = _dist(bird_now["center"], other_now["center"])

            if d_prev > d_mid and d_mid < threshold and d_now > d_mid * 1.5:
                count += 1

    return count


def _detect_chase_events(
    bird_id: str,
    snapshots: list[dict],
    min_frames: int,
) -> int:
    """Heurística: bird sigue a otra durante >=min_frames con velocidad > umbral."""
    # Calibrado con datos reales 2026-04-09: P50=0.025, P75=0.161, P90=0.458
    # 0.10 captura solo movimiento deliberado rápido (~P70)
    SPEED_THRESHOLD = 0.10  # normalized units per snapshot
    count = 0

    other_ids = set()
    for snap in snapshots:
        for t in snap.get("tracks", []):
            bid = t.get("bird_id", "")
            if bid and bid != bird_id:
                other_ids.add(bid)

    for other_id in other_ids:
        consecutive = 0
        for i in range(1, len(snapshots)):
            bird_prev = _find_track(bird_id, snapshots[i - 1])
            bird_now = _find_track(bird_id, snapshots[i])
            other_prev = _find_track(other_id, snapshots[i - 1])
            other_now = _find_track(other_id, snapshots[i])

            if not all([bird_prev, bird_now, other_prev, other_now]):
                consecutive = 0
                continue

            # Bird se mueve rápido hacia other
            bird_speed = _dist(bird_prev["center"], bird_now["center"])
            d_prev = _dist(bird_prev["center"], other_prev["center"])
            d_now = _dist(bird_now["center"], other_now["center"])

            if bird_speed > SPEED_THRESHOLD and d_now < d_prev:
                consecutive += 1
                if consecutive >= min_frames:
                    count += 1
                    consecutive = 0
            else:
                consecutive = 0

    return count


def _compute_social_metrics(
    bird_id: str,
    snapshots: list[dict],
) -> tuple[float, float]:
    """Calcula cohesión de grupo y centralidad del ave."""
    if not snapshots:
        return 0.0, 0.0

    centrality_values = []
    cohesion_values = []

    for snap in snapshots:
        tracks = snap.get("tracks", [])
        if len(tracks) < 2:
            continue

        # Centroide del grupo
        all_centers = [t["center"] for t in tracks]
        group_cx = sum(c[0] for c in all_centers) / len(all_centers)
        group_cy = sum(c[1] for c in all_centers) / len(all_centers)

        # Dispersión media (cohesión = inverso de dispersión)
        dispersions = [_dist(c, [group_cx, group_cy]) for c in all_centers]
        avg_disp = sum(dispersions) / len(dispersions) if dispersions else 1.0
        cohesion_values.append(1.0 / (1.0 + avg_disp))

        # Centralidad de esta ave
        bird_track = _find_track(bird_id, snap)
        if bird_track:
            bird_dist = _dist(bird_track["center"], [group_cx, group_cy])
            centrality_values.append(1.0 / (1.0 + bird_dist))

    cohesion = sum(cohesion_values) / len(cohesion_values) if cohesion_values else 0.0
    centrality = sum(centrality_values) / len(centrality_values) if centrality_values else 0.0

    return round(cohesion, 4), round(centrality, 4)


def _enrich_climate(features: BirdBehaviorFeatures, gallinero_id: str):
    """Añade datos climáticos del sensor Zigbee del gallinero."""
    try:
        from services.telemetry import get_last_values, DEVICE_GALLINERO_MAP

        last_vals = get_last_values()
        # Buscar sensor mapeado a este gallinero
        for sensor_name, mapping in DEVICE_GALLINERO_MAP.items():
            if sensor_name == gallinero_id or str(mapping.get("gallinero_id", "")) == gallinero_id.split("_")[-1]:
                sensor_data = last_vals.get(sensor_name, {})
                if sensor_data:
                    temp = sensor_data.get("temperature")
                    hum = sensor_data.get("humidity")
                    if temp is not None:
                        features.ambient_temperature = float(temp)
                        features.climate_data_available = True
                    if hum is not None:
                        features.ambient_humidity = float(hum)
                break
    except Exception as e:
        logger.debug(f"[BehaviorFeatures] Climate enrichment failed: {e}")


def compute_group_features(
    gallinero_id: str,
    window: str = "24h",
    end_time: datetime | None = None,
) -> list[BirdBehaviorFeatures]:
    """Calcula features para todas las aves de un gallinero y rellena ratios vs grupo."""
    store = get_event_store()
    end = end_time or datetime.now(timezone.utc)
    delta = _parse_window(window)
    start = end - delta

    snapshots = store.query(gallinero_id, start, end)

    # Recopilar bird_ids únicos
    bird_ids: set[str] = set()
    for snap in snapshots:
        for track in snap.get("tracks", []):
            bid = track.get("bird_id", "")
            if bid:
                bird_ids.add(bid)

    if not bird_ids:
        return []

    # Calcular features individuales
    all_features = []
    for bid in bird_ids:
        feat = compute_bird_features(bid, gallinero_id, window, end_time)
        all_features.append(feat)

    # Calcular medias de grupo y rellenar ratios
    if len(all_features) > 1:
        avg_feeder = sum(f.feeder_total_time_sec for f in all_features) / len(all_features)
        avg_drinker = sum(f.drinker_total_time_sec for f in all_features) / len(all_features)
        avg_mobility = sum(f.distance_traveled for f in all_features) / len(all_features)

        for feat in all_features:
            feat.feeding_vs_group_ratio = round(
                feat.feeder_total_time_sec / avg_feeder, 3
            ) if avg_feeder > 0 else 1.0
            feat.drinking_vs_group_ratio = round(
                feat.drinker_total_time_sec / avg_drinker, 3
            ) if avg_drinker > 0 else 1.0
            feat.mobility_vs_group_ratio = round(
                feat.distance_traveled / avg_mobility, 3
            ) if avg_mobility > 0 else 1.0

    return all_features


def compute_group_statistics(
    gallinero_id: str,
    window: str = "24h",
) -> dict:
    """Calcula P10/P25/P50/P75/P90 de cada feature para calibración."""
    features = compute_group_features(gallinero_id, window)
    if not features:
        return {}

    def percentiles(values: list[float]) -> dict:
        if not values:
            return {}
        s = sorted(values)
        n = len(s)
        return {
            "p10": s[max(0, int(n * 0.1))],
            "p25": s[max(0, int(n * 0.25))],
            "p50": s[max(0, int(n * 0.5))],
            "p75": s[max(0, int(n * 0.75))],
            "p90": s[max(0, int(n * 0.9))],
            "mean": sum(s) / n,
            "count": n,
        }

    return {
        "gallinero_id": gallinero_id,
        "window": window,
        "n_birds": len(features),
        "feeder_visits": percentiles([f.feeder_visits_count for f in features]),
        "feeder_time_sec": percentiles([f.feeder_total_time_sec for f in features]),
        "drinker_time_sec": percentiles([f.drinker_total_time_sec for f in features]),
        "distance_traveled": percentiles([f.distance_traveled for f in features]),
        "activity_score": percentiles([f.activity_score for f in features]),
        "inactivity_time_sec": percentiles([f.inactivity_time_sec for f in features]),
        "zone_switch_count": percentiles([f.zone_switch_count for f in features]),
        "isolation_time_sec": percentiles([f.isolation_time_sec for f in features]),
        "proximity_events": percentiles([f.proximity_events_count for f in features]),
    }


# ── Helpers ──

def _find_track(bird_id: str, snapshot: dict) -> dict | None:
    for t in snapshot.get("tracks", []):
        if t.get("bird_id") == bird_id:
            return t
    return None


def _get_other_ids(bird_id: str, snapshot: dict) -> list[str]:
    return [
        t["bird_id"] for t in snapshot.get("tracks", [])
        if t.get("bird_id") and t["bird_id"] != bird_id
    ]


def _dist(a: list, b: list) -> float:
    return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
