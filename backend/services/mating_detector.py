"""Seedy Backend — Detector de Monta (Mating)

Detecta eventos de monta entre aves a partir de las detecciones YOLO.

Heurística de monta:
  1. Dos bboxes con IoU alto (> 0.35) → posible solapamiento
  2. Un bbox encima del otro (centro Y menor = más arriba en imagen)
  3. El bbox superior es más grande (el gallo encima es más voluminoso)
  4. El patrón se mantiene durante N frames consecutivos (min 3 = ~3-4s)

Persiste eventos en JSONL: data/mating_events/{gallinero_id}/{YYYY-MM-DD}.jsonl
Cada evento incluye: timestamp, gallinero, mounter (track/bird_id), mounted,
duración estimada, confianza.
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.bird_tracker import GallineroTracker

logger = logging.getLogger(__name__)

# ── Configuración ──
MATING_IOU_THRESHOLD = 0.35      # IoU mínimo para considerar solapamiento
MATING_Y_OVERLAP_RATIO = 0.15    # centro Y del mounter debe estar al menos esto más arriba
MATING_MIN_FRAMES = 3            # frames consecutivos para confirmar monta
MATING_SIZE_RATIO = 0.8          # mounter area >= mounted area * ratio (gallos ≥ gallinas)
MATING_COOLDOWN_SEC = 120        # no registrar 2 montas del mismo par en <2 min
MATING_MAX_CANDIDATES = 20       # max pares a evaluar por frame (rendimiento)

_BASE_PATH = Path("data/mating_events/")


def _iou(box1: list, box2: list) -> float:
    if len(box1) != 4 or len(box2) != 4:
        return 0.0
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    return inter / (a1 + a2 - inter)


class MatingCandidate:
    """Seguimiento de un posible evento de monta entre dos tracks."""

    __slots__ = ("mounter_tid", "mounted_tid", "start_time", "frame_count",
                 "last_frame_time", "ious", "confirmed")

    def __init__(self, mounter_tid: int, mounted_tid: int):
        self.mounter_tid = mounter_tid
        self.mounted_tid = mounted_tid
        self.start_time = time.time()
        self.last_frame_time = self.start_time
        self.frame_count = 1
        self.ious: list[float] = []
        self.confirmed = False

    def update(self, iou: float):
        self.frame_count += 1
        self.last_frame_time = time.time()
        self.ious.append(iou)
        if self.frame_count >= MATING_MIN_FRAMES and not self.confirmed:
            self.confirmed = True

    @property
    def duration_sec(self) -> float:
        return self.last_frame_time - self.start_time

    @property
    def avg_iou(self) -> float:
        return sum(self.ious) / max(len(self.ious), 1)

    @property
    def stale(self) -> bool:
        """Candidato expirado (no visto en >10s)."""
        return time.time() - self.last_frame_time > 10.0

    @property
    def key(self) -> tuple[int, int]:
        return (self.mounter_tid, self.mounted_tid)


class MatingDetector:
    """Detecta y registra eventos de monta en un gallinero."""

    def __init__(self, gallinero_id: str):
        self.gallinero_id = gallinero_id
        self._candidates: dict[tuple[int, int], MatingCandidate] = {}
        self._last_event: dict[tuple[int, int], float] = {}  # cooldown
        self._total_events = 0

    def process_frame(self, tracker: "GallineroTracker") -> list[dict]:
        """Procesa un frame del tracker buscando patrones de monta.

        Returns: lista de eventos de monta confirmados en este frame.
        """
        now = time.time()
        events: list[dict] = []
        active = [(tid, t) for tid, t in tracker.tracks.items()
                  if t.active and t.history and t.last_bbox_norm]

        if len(active) < 2:
            self._cleanup_stale()
            return events

        # Evaluar pares de tracks activos
        seen_pairs: set[tuple[int, int]] = set()
        candidates_found = 0

        for i in range(len(active)):
            if candidates_found >= MATING_MAX_CANDIDATES:
                break
            tid_a, track_a = active[i]
            for j in range(i + 1, len(active)):
                tid_b, track_b = active[j]

                bbox_a = track_a.last_bbox_norm
                bbox_b = track_b.last_bbox_norm
                iou = _iou(bbox_a, bbox_b)

                if iou < MATING_IOU_THRESHOLD:
                    continue

                # Determinar quién está encima (centro Y menor = más arriba en imagen)
                cy_a = (bbox_a[1] + bbox_a[3]) / 2
                cy_b = (bbox_b[1] + bbox_b[3]) / 2
                area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
                area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])

                y_diff = abs(cy_a - cy_b)
                if y_diff < MATING_Y_OVERLAP_RATIO:
                    continue  # No hay solapamiento vertical claro

                # El que está más arriba (cy menor) es el que monta
                if cy_a < cy_b:
                    mounter_tid, mounted_tid = tid_a, tid_b
                    mounter_track, mounted_track = track_a, track_b
                    mounter_area, mounted_area = area_a, area_b
                else:
                    mounter_tid, mounted_tid = tid_b, tid_a
                    mounter_track, mounted_track = track_b, track_a
                    mounter_area, mounted_area = area_b, area_a

                # El que monta debe ser al menos un cierto tamaño respecto al montado
                if mounter_area < mounted_area * MATING_SIZE_RATIO:
                    continue

                pair_key = (mounter_tid, mounted_tid)
                seen_pairs.add(pair_key)
                candidates_found += 1

                if pair_key in self._candidates:
                    self._candidates[pair_key].update(iou)
                else:
                    candidate = MatingCandidate(mounter_tid, mounted_tid)
                    candidate.ious.append(iou)
                    self._candidates[pair_key] = candidate

                # ¿Se confirma la monta?
                candidate = self._candidates[pair_key]
                if candidate.confirmed:
                    # Cooldown check
                    last = self._last_event.get(pair_key, 0)
                    if now - last < MATING_COOLDOWN_SEC:
                        continue

                    event = self._build_event(candidate, mounter_track, mounted_track)
                    events.append(event)
                    self._persist_event(event)
                    self._last_event[pair_key] = now
                    self._total_events += 1

                    logger.info(
                        f"🐓 Monta detectada en {self.gallinero_id}: "
                        f"track#{mounter_tid}({mounter_track.breed or '?'}) → "
                        f"track#{mounted_tid}({mounted_track.breed or '?'}) "
                        f"dur={candidate.duration_sec:.1f}s iou={candidate.avg_iou:.2f}"
                    )

        # Limpiar candidatos que se separaron
        self._cleanup_stale()
        # También limpiar pares activos que ya no se solapan
        for pair_key in list(self._candidates):
            if pair_key not in seen_pairs:
                cand = self._candidates[pair_key]
                if not cand.stale:
                    cand.last_frame_time -= 2  # acelerar expiración
                else:
                    del self._candidates[pair_key]

        return events

    def _build_event(self, candidate: MatingCandidate,
                     mounter_track, mounted_track) -> dict:
        """Construye el registro del evento de monta.

        v4.2: incluye campo 'attribution' (full/partial/none)
        y siempre incluye breed+sex aunque no haya bird_id.
        """
        # v4.2: attribution basada en identity_lock
        mounter_locked = getattr(mounter_track, "identity_locked", False)
        mounted_locked = getattr(mounted_track, "identity_locked", False)
        mounter_id = mounter_track.ai_vision_id if mounter_locked else ""
        mounted_id = mounted_track.ai_vision_id if mounted_locked else ""

        if mounter_id and mounted_id:
            attribution = "full"
        elif mounter_id or mounted_id:
            attribution = "partial"
        else:
            attribution = "none"

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ts_unix": round(time.time(), 2),
            "gallinero_id": self.gallinero_id,
            "type": "mating",
            "attribution": attribution,
            "mounter": {
                "track_id": candidate.mounter_tid,
                "bird_id": mounter_id,
                "breed": mounter_track.breed or "",
                "sex": mounter_track.sex or "male",
                "color": getattr(mounter_track, "color", "") or "",
            },
            "mounted": {
                "track_id": candidate.mounted_tid,
                "bird_id": mounted_id,
                "breed": mounted_track.breed or "",
                "sex": mounted_track.sex or "female",
                "color": getattr(mounted_track, "color", "") or "",
            },
            "duration_sec": round(candidate.duration_sec, 1),
            "avg_iou": round(candidate.avg_iou, 3),
            "frames": candidate.frame_count,
            "confidence": min(1.0, candidate.avg_iou * (candidate.frame_count / MATING_MIN_FRAMES)),
        }

    def _persist_event(self, event: dict):
        """Escribe evento a JSONL del día."""
        day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        gall_dir = _BASE_PATH / self.gallinero_id
        gall_dir.mkdir(parents=True, exist_ok=True)
        filepath = gall_dir / f"{day_str}.jsonl"
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[MatingDetector] Error persisting event: {e}")

    def _cleanup_stale(self):
        """Elimina candidatos expirados."""
        stale = [k for k, c in self._candidates.items() if c.stale]
        for k in stale:
            del self._candidates[k]

    def is_active(self) -> bool:
        """True si hay candidatos de monta activos (para triggers 4K)."""
        self._cleanup_stale()
        return len(self._candidates) > 0

    def get_stats(self) -> dict:
        return {
            "gallinero_id": self.gallinero_id,
            "total_events": self._total_events,
            "active_candidates": len(self._candidates),
        }


# ── Singleton por gallinero ──
_detectors: dict[str, MatingDetector] = {}


def get_mating_detector(gallinero_id: str) -> MatingDetector:
    if gallinero_id not in _detectors:
        _detectors[gallinero_id] = MatingDetector(gallinero_id)
    return _detectors[gallinero_id]


# ── Consultas históricas ──

def query_mating_events(
    gallinero_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    bird_id: str | None = None,
) -> list[dict]:
    """Lee eventos de monta de JSONL en rango temporal."""
    gall_dir = _BASE_PATH / gallinero_id
    if not gall_dir.exists():
        return []

    if not end:
        end = datetime.now(timezone.utc)
    if not start:
        start = end - timedelta(days=7)

    results = []
    current = start.date()
    end_date = end.date()

    while current <= end_date:
        filepath = gall_dir / f"{current.isoformat()}.jsonl"
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            ts = record.get("ts_unix", 0)
                            if start.timestamp() <= ts <= end.timestamp():
                                if bird_id:
                                    # Filtrar por ave específica (mounter o mounted)
                                    m_id = record.get("mounter", {}).get("bird_id", "")
                                    f_id = record.get("mounted", {}).get("bird_id", "")
                                    if bird_id not in (m_id, f_id):
                                        continue
                                results.append(record)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.warning(f"[MatingDetector] Error reading {filepath}: {e}")
        current += timedelta(days=1)

    return results


def get_mating_summary(
    gallinero_id: str,
    days: int = 7,
) -> dict:
    """Resumen de montas: quién monta a quién, cuántas veces, frecuencia."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    events = query_mating_events(gallinero_id, start, end)

    if not events:
        return {
            "gallinero_id": gallinero_id,
            "period_days": days,
            "total_events": 0,
            "pairs": [],
            "top_mounters": [],
            "daily_counts": {},
        }

    # Pares: mounter_id → mounted_id → count
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_details: dict[tuple[str, str], dict] = {}
    mounter_counts: dict[str, int] = defaultdict(int)
    daily_counts: dict[str, int] = defaultdict(int)

    for ev in events:
        m = ev.get("mounter", {})
        f = ev.get("mounted", {})
        m_id = m.get("bird_id") or f"track#{m.get('track_id', '?')}"
        f_id = f.get("bird_id") or f"track#{f.get('track_id', '?')}"

        pair_key = (m_id, f_id)
        pair_counts[pair_key] += 1
        mounter_counts[m_id] += 1

        if pair_key not in pair_details:
            pair_details[pair_key] = {
                "mounter_id": m_id,
                "mounter_breed": m.get("breed", ""),
                "mounted_id": f_id,
                "mounted_breed": f.get("breed", ""),
            }

        # Contar por día
        ts = ev.get("ts", "")[:10]
        if ts:
            daily_counts[ts] += 1

    # Ordenar pares por frecuencia
    pairs = []
    for (m_id, f_id), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
        detail = pair_details[(m_id, f_id)]
        detail["count"] = count
        pairs.append(detail)

    # Top mounters
    top_mounters = [
        {"bird_id": bid, "count": c}
        for bid, c in sorted(mounter_counts.items(), key=lambda x: -x[1])
    ]

    return {
        "gallinero_id": gallinero_id,
        "period_days": days,
        "total_events": len(events),
        "pairs": pairs,
        "top_mounters": top_mounters,
        "daily_counts": dict(daily_counts),
        "avg_per_day": round(len(events) / max(days, 1), 1),
    }


def cleanup_old_events(max_age_days: int = 30) -> int:
    """Borra JSONL de mating anteriores a max_age_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    deleted = 0

    if not _BASE_PATH.exists():
        return 0

    for gall_dir in _BASE_PATH.iterdir():
        if not gall_dir.is_dir():
            continue
        for filepath in gall_dir.glob("*.jsonl"):
            if filepath.stem < cutoff_str:
                try:
                    filepath.unlink()
                    deleted += 1
                except Exception as e:
                    logger.warning(f"[MatingDetector] Error deleting {filepath}: {e}")
    return deleted


# ── Detección retrospectiva de montas desde behavior snapshots ──

# Umbrales para detección retrospectiva (sin bbox usa distancia centros)
_RETRO_DIST_THRESHOLD = 0.06     # dist normalizada entre centros para considerar monta
_RETRO_DIST_BBOX_THRESHOLD = 0.04  # más estricto si no hay bbox
_RETRO_MIN_CONSECUTIVE = 2       # snapshots consecutivos (a 60s) con proximidad
_RETRO_Y_OFFSET_MIN = 0.02      # mounter debe estar al menos esto más arriba
_RETRO_COOLDOWN_SEC = 300        # 5 min entre eventos del mismo par (retrospectivo)


def scan_mating_retrospective(
    gallinero_id: str,
    hours: int = 24,
    persist: bool = True,
) -> list[dict]:
    """Escanea behavior snapshots buscando patrones de monta retrospectivamente.

    Detecta secuencias donde dos tracks están superpuestos (IoU si hay bbox,
    distancia de centros si no) durante ≥2 snapshots consecutivos (~120s).

    Los eventos se persisten en el JSONL de mating con source='retrospective'.
    Solo genera eventos nuevos que no solapen con eventos ya registrados.

    Returns: lista de eventos de monta encontrados.
    """
    from services.behavior_event_store import get_event_store

    store = get_event_store()
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    snapshots = store.query(gallinero_id, start, end)

    if len(snapshots) < 2:
        return []

    # Cargar eventos ya registrados para evitar duplicados
    existing_events = query_mating_events(gallinero_id, start, end)
    existing_times = set()
    for ev in existing_events:
        # Ventana de 5 min alrededor de cada evento ya registrado
        ts = ev.get("ts_unix", 0)
        existing_times.add(int(ts // _RETRO_COOLDOWN_SEC))

    # Estado: pares activos con su cuenta de snapshots consecutivos
    active_pairs: dict[tuple, dict] = {}  # (tid_a, tid_b) → {count, first_ts, last_snap, ...}
    events: list[dict] = []
    detector = get_mating_detector(gallinero_id)

    for snap_idx, snap in enumerate(snapshots):
        ts_unix = snap.get("ts_unix", 0)
        tracks = snap.get("tracks", [])
        if len(tracks) < 2:
            # Limpiar pares activos que no se ven
            active_pairs.clear()
            continue

        seen_pairs: set[tuple] = set()

        for i in range(len(tracks)):
            t1 = tracks[i]
            for j in range(i + 1, len(tracks)):
                t2 = tracks[j]

                # Calcular proximidad
                c1 = t1.get("center", [0, 0])
                c2 = t2.get("center", [0, 0])

                bbox1 = t1.get("bbox", [])
                bbox2 = t2.get("bbox", [])
                has_bbox = len(bbox1) == 4 and len(bbox2) == 4

                is_close = False
                overlap_iou = 0.0

                if has_bbox:
                    overlap_iou = _iou(bbox1, bbox2)
                    is_close = overlap_iou >= MATING_IOU_THRESHOLD
                else:
                    # Fallback: distancia entre centros
                    import math
                    dist = math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)
                    is_close = dist < _RETRO_DIST_THRESHOLD

                if not is_close:
                    continue

                # Y-offset: el mounter está más arriba (cy menor)
                cy1, cy2 = c1[1], c2[1]
                y_diff = abs(cy1 - cy2)
                if y_diff < _RETRO_Y_OFFSET_MIN:
                    continue  # Sin solapamiento vertical claro

                # Determinar mounter/mounted
                if cy1 < cy2:
                    mounter_t, mounted_t = t1, t2
                else:
                    mounter_t, mounted_t = t2, t1

                tid_a = mounter_t.get("track_id", 0)
                tid_b = mounted_t.get("track_id", 0)
                # Pair key: usar track_id si disponible, sino breed+posición como proxy
                if tid_a and tid_b and tid_a != tid_b:
                    pair_key = (tid_a, tid_b)
                else:
                    # Sin track_ids válidos, usar hash de breed+posición (menos fiable)
                    pk_a = f"{mounter_t.get('breed','')}{mounter_t.get('bird_id','')}{i}"
                    pk_b = f"{mounted_t.get('breed','')}{mounted_t.get('bird_id','')}{j}"
                    pair_key = (pk_a, pk_b)
                seen_pairs.add(pair_key)

                if pair_key in active_pairs:
                    active_pairs[pair_key]["count"] += 1
                    active_pairs[pair_key]["last_ts"] = ts_unix
                    active_pairs[pair_key]["last_iou"] = overlap_iou
                else:
                    active_pairs[pair_key] = {
                        "count": 1,
                        "first_ts": ts_unix,
                        "last_ts": ts_unix,
                        "mounter": mounter_t,
                        "mounted": mounted_t,
                        "last_iou": overlap_iou,
                    }

                # ¿Confirmar monta?
                info = active_pairs[pair_key]
                if info["count"] >= _RETRO_MIN_CONSECUTIVE:
                    # Cooldown check
                    time_bucket = int(ts_unix // _RETRO_COOLDOWN_SEC)
                    if time_bucket in existing_times:
                        continue

                    event = _build_retro_event(
                        gallinero_id, info, has_bbox
                    )
                    events.append(event)
                    existing_times.add(time_bucket)

                    if persist:
                        detector._persist_event(event)

                    # Reset pair counter para no duplicar
                    active_pairs[pair_key]["count"] = 0

        # Limpiar pares no vistos en este snapshot
        stale = [k for k in active_pairs if k not in seen_pairs]
        for k in stale:
            del active_pairs[k]

    logger.info(
        f"[MatingRetro] Scan {gallinero_id} {hours}h: "
        f"{len(snapshots)} snapshots, {len(events)} montas detectadas"
    )
    return events


def _build_retro_event(gallinero_id: str, info: dict, has_bbox: bool) -> dict:
    """Construye evento de monta retrospectivo."""
    mounter = info["mounter"]
    mounted = info["mounted"]
    duration = info["last_ts"] - info["first_ts"]

    return {
        "ts": datetime.fromtimestamp(info["first_ts"], tz=timezone.utc).isoformat(),
        "ts_unix": round(info["first_ts"], 2),
        "gallinero_id": gallinero_id,
        "type": "mating",
        "source": "retrospective",
        "attribution": _retro_attribution(mounter, mounted),
        "mounter": {
            "track_id": mounter.get("track_id", 0),
            "bird_id": mounter.get("bird_id", ""),
            "breed": mounter.get("breed", ""),
            "sex": mounter.get("sex", "male"),
            "color": mounter.get("color", ""),
        },
        "mounted": {
            "track_id": mounted.get("track_id", 0),
            "bird_id": mounted.get("bird_id", ""),
            "breed": mounted.get("breed", ""),
            "sex": mounted.get("sex", "female"),
            "color": mounted.get("color", ""),
        },
        "duration_sec": round(max(duration, 60), 1),  # mín 60s (1 snapshot interval)
        "avg_iou": round(info["last_iou"], 3),
        "frames": info["count"],
        "confidence": min(0.8, 0.3 + 0.15 * info["count"]) if has_bbox else min(0.6, 0.2 + 0.1 * info["count"]),
        "detection_method": "retrospective_iou" if has_bbox else "retrospective_proximity",
    }


def _retro_attribution(mounter: dict, mounted: dict) -> str:
    if mounter.get("bird_id") and mounted.get("bird_id"):
        return "full"
    if mounter.get("bird_id") or mounted.get("bird_id"):
        return "partial"
    return "none"
