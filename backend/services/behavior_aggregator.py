"""Seedy Backend — Agregador de Comportamiento

Calcula scores por dimensión a partir de:
- behavior_events/{gallinero}/snapshots/{date}.jsonl  (tracks por frame)
- mating_events/{gallinero}/{date}.jsonl              (montas con bird_id)

Ventana por defecto: 24h.
Output: dict por ave con score [0-1] y completeness [0-1] por dimensión.
Persiste en: data/twin_metrics/{bird_id}/{date}.json

OBJ5: Implementar las 7 dimensiones para el digital twin individual.
"""

from __future__ import annotations
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
import logging

logger = logging.getLogger(__name__)

DIMENSIONS = (
    "agresividad", "dominancia", "subordinacion",
    "alimentacion", "estres", "sociabilidad", "patron_nido",
)

# Umbrales mínimos de muestras para considerar "datos suficientes"
MIN_FRAMES_FOR_DIMENSION = {
    "agresividad":   80,   # ~13 min de presencia
    "dominancia":    80,
    "subordinacion": 80,
    "alimentacion":  40,   # ~7 min cerca del comedero
    "estres":       100,
    "sociabilidad":  60,
    "patron_nido":   20,   # eventos de nido (raros pero significativos)
}


@dataclass
class DimensionScore:
    score: float = 0.0          # [0, 1]
    completeness: float = 0.0   # [0, 1] — fracción de min_frames disponibles
    sample_size: int = 0
    notes: list[str] = field(default_factory=list)


def _iter_snapshots(gallinero_id: str, since: datetime) -> Iterable[dict]:
    """Lee JSONLs de behavior_events desde una fecha."""
    base = Path(f"data/behavior_events/{gallinero_id}/snapshots")
    if not base.exists():
        return
    cutoff_ts = since.timestamp()
    # Solo ficheros de últimas 2 fechas para no leer todo
    for jf in sorted(base.glob("*.jsonl"))[-2:]:
        with jf.open() as fh:
            for line in fh:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("ts_unix", 0) >= cutoff_ts:
                    yield event


def _iter_mating(gallinero_id: str, since: datetime) -> Iterable[dict]:
    """Lee JSONLs de mating_events desde una fecha."""
    base = Path(f"data/mating_events/{gallinero_id}")
    if not base.exists():
        return
    cutoff_ts = since.timestamp()
    for jf in sorted(base.glob("*.jsonl"))[-2:]:
        with jf.open() as fh:
            for line in fh:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = datetime.fromisoformat(event["ts"]).timestamp()
                if ts >= cutoff_ts:
                    yield event


def compute_dimensions(
    bird_id: str,
    gallinero_id: str,
    window_hours: int = 24,
) -> dict[str, DimensionScore]:
    """Calcula las 7 dimensiones para un ave en una ventana de tiempo."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    scores = {d: DimensionScore() for d in DIMENSIONS}

    # Acumuladores
    frames_by_zone: dict[str, int] = defaultdict(int)
    total_frames = 0
    interactions = 0  # frames con >1 ave cerca
    nido_frames = 0
    comedero_frames = 0

    # 1. Recorrer snapshots y filtrar tracks de este bird_id
    for snap in _iter_snapshots(gallinero_id, since):
        tracks_in_frame = snap.get("tracks", [])
        bird_track = None
        for tr in tracks_in_frame:
            if tr.get("bird_id") == bird_id or tr.get("ai_vision_id") == bird_id:
                bird_track = tr
                break
        
        if not bird_track:
            continue
        
        total_frames += 1
        zone = bird_track.get("zone", "unknown")
        frames_by_zone[zone] += 1
        
        if zone == "nido":
            nido_frames += 1
        if zone == "comedero":
            comedero_frames += 1
        
        # Más de 1 ave en el frame → interacción social
        if snap.get("active_count", 1) > 1:
            interactions += 1

    # 2. Montas como mounter / mounted
    mounter_count = 0
    mounted_count = 0
    for ev in _iter_mating(gallinero_id, since):
        mounter_id = ev.get("mounter", {}).get("bird_id") or ev.get("mounter_id", "")
        mounted_id = ev.get("mounted", {}).get("bird_id") or ev.get("mounted_id", "")
        
        if mounter_id == bird_id:
            mounter_count += 1
        if mounted_id == bird_id:
            mounted_count += 1

    # 3. Cálculo de scores (heurísticas simples y honestas)
    if total_frames > 0:
        # DOMINANCIA: ser mounter + tiempo en zonas centrales
        scores["dominancia"].score = min(1.0, mounter_count / 20.0)
        scores["dominancia"].sample_size = mounter_count
        scores["dominancia"].completeness = min(
            1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["dominancia"]
        )

        # SUBORDINACION: ser mounted
        scores["subordinacion"].score = min(1.0, mounted_count / 20.0)
        scores["subordinacion"].sample_size = mounted_count
        scores["subordinacion"].completeness = min(
            1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["subordinacion"]
        )

        # ALIMENTACION: fracción de tiempo en comedero
        if total_frames > 0:
            scores["alimentacion"].score = comedero_frames / total_frames
            scores["alimentacion"].sample_size = comedero_frames
            scores["alimentacion"].completeness = min(
                1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["alimentacion"]
            )

        # PATRON_NIDO: fracción de tiempo en nido
        if total_frames > 0:
            scores["patron_nido"].score = nido_frames / total_frames
            scores["patron_nido"].sample_size = nido_frames
            scores["patron_nido"].completeness = min(
                1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["patron_nido"]
            )

        # SOCIABILIDAD: fracción de frames con otra ave cerca
        if total_frames > 0:
            scores["sociabilidad"].score = interactions / total_frames
            scores["sociabilidad"].sample_size = interactions
            scores["sociabilidad"].completeness = min(
                1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["sociabilidad"]
            )

        # ESTRES: alta varianza de zonas + bajo tiempo en aseladero
        # heurística inicial — refinar con datos reales
        zone_entropy = _entropy(list(frames_by_zone.values()))
        aseladero_ratio = frames_by_zone.get("aseladero", 0) / total_frames if total_frames > 0 else 0
        scores["estres"].score = min(1.0, zone_entropy * (1 - aseladero_ratio))
        scores["estres"].sample_size = total_frames
        scores["estres"].completeness = min(
            1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["estres"]
        )

        # AGRESIVIDAD: por ahora proxy = mounter_count alto sin reciprocidad
        # (mejora futura: detectar picoteo)
        agg_proxy = mounter_count - mounted_count
        scores["agresividad"].score = max(0.0, min(1.0, agg_proxy / 15.0))
        scores["agresividad"].sample_size = max(0, agg_proxy)
        scores["agresividad"].completeness = min(
            1.0, total_frames / MIN_FRAMES_FOR_DIMENSION["agresividad"]
        )

    return scores


def _entropy(counts: list[int]) -> float:
    """Entropía de Shannon normalizada [0, 1]."""
    total = sum(counts)
    if total == 0 or len(counts) <= 1:
        return 0.0
    probs = [c / total for c in counts if c > 0]
    h = -sum(p * math.log2(p) for p in probs)
    max_h = math.log2(len(probs))
    return h / max_h if max_h > 0 else 0.0


def persist_metrics(bird_id: str, scores: dict[str, DimensionScore]) -> Path:
    """Guarda el snapshot diario en data/twin_metrics/{bird_id}/{date}.json."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(f"data/twin_metrics/{bird_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{today}.json"

    payload = {
        "bird_id": bird_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "window_hours": 24,
        "dimensions": {
            name: {
                "score": s.score,
                "completeness": s.completeness,
                "sample_size": s.sample_size,
                "notes": s.notes,
            }
            for name, s in scores.items()
        },
    }
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info(f"[BehaviorAggregator] Métricas guardadas: {out_file}")
    return out_file


def run_for_all_birds(gallinero_id: str, registered_birds: list[dict]) -> int:
    """Ejecutar para todas las aves del gallinero. Devuelve nº procesadas."""
    n = 0
    for bird in registered_birds:
        bird_id = bird.get("ai_vision_id")
        if not bird_id:
            continue
        scores = compute_dimensions(bird_id, gallinero_id)
        persist_metrics(bird_id, scores)
        n += 1
    logger.info(f"[BehaviorAggregator] Procesadas {n} aves de {gallinero_id}")
    return n
