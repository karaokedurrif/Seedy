"""Seedy Backend — Behavior Event Store

Persiste snapshots agregados del tracker en JSONL para que las ventanas
largas (1h-24h) sean posibles. El tracker solo mantiene 120 frames en RAM
(~8 min a 4s/frame). Este store escribe a disco cada 60s.

Formato: data/behavior_events/{gallinero_id}/{YYYY-MM-DD}.jsonl
Cada línea = 1 snapshot JSON con posiciones de todas las aves activas.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from config import get_settings

if TYPE_CHECKING:
    from services.bird_tracker import GallineroTracker

logger = logging.getLogger(__name__)

_settings = get_settings()
_BASE_PATH = Path(_settings.behavior_event_store_path)


class BehaviorEventStore:
    """Almacena snapshots del tracker en JSONL append-only."""

    def __init__(self, base_path: str | None = None):
        self._base = Path(base_path) if base_path else _BASE_PATH
        self._base.mkdir(parents=True, exist_ok=True)
        self._last_snapshot: dict[str, float] = {}  # gallinero → timestamp

    def snapshot(self, gallinero_id: str, tracker: "GallineroTracker") -> None:
        """Serializa estado actual del tracker y lo escribe a JSONL.

        Cada snapshot: {ts, gallinero_id, active_count, tracks: [{track_id, bird_id, center, zone, confidence, area}]}
        ~500 bytes/snapshot → ~720 KB/gallinero/día (1440 snapshots a 60s).
        """
        now = time.time()
        last = self._last_snapshot.get(gallinero_id, 0)
        interval = _settings.behavior_snapshot_interval_sec
        if now - last < interval:
            return

        active_tracks = []
        for t in tracker.tracks.values():
            if not t.active or not t.history:
                continue
            last_pt = t.history[-1]
            # v4.2: solo escribir bird_id si identity_locked
            bird_id = ""
            if getattr(t, "identity_locked", False) and t.ai_vision_id:
                bird_id = t.ai_vision_id
            active_tracks.append({
                "track_id": t.track_id,
                "bird_id": bird_id,
                "breed": t.breed or "",
                "sex": getattr(t, "sex", "") or "",
                "center": list(last_pt.center),
                "zone": last_pt.zone,
                "confidence": round(last_pt.confidence, 3),
                "area": round(last_pt.area_norm, 6),
            })

        if not active_tracks:
            return

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ts_unix": round(now, 2),
            "gallinero_id": gallinero_id,
            "active_count": len(active_tracks),
            "tracks": active_tracks,
        }

        # Escribir a fichero del día
        day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        gall_dir = self._base / gallinero_id
        gall_dir.mkdir(parents=True, exist_ok=True)
        filepath = gall_dir / f"{day_str}.jsonl"

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._last_snapshot[gallinero_id] = now
        except Exception as e:
            logger.warning(f"[BehaviorStore] Error writing snapshot: {e}")

    def query(
        self,
        gallinero_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Lee snapshots JSONL en rango temporal. Lazy-load línea a línea."""
        gall_dir = self._base / gallinero_id
        if not gall_dir.exists():
            return []

        results = []
        start_ts = start.timestamp()
        end_ts = end.timestamp()

        # Iterar ficheros del rango de días
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
                                if start_ts <= ts <= end_ts:
                                    results.append(record)
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    logger.warning(f"[BehaviorStore] Error reading {filepath}: {e}")
            current += timedelta(days=1)

        return results

    def cleanup(self, max_age_days: int | None = None) -> int:
        """Borra ficheros JSONL anteriores a max_age_days. Devuelve nº borrados."""
        if max_age_days is None:
            max_age_days = _settings.behavior_retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        deleted = 0

        if not self._base.exists():
            return 0

        for gall_dir in self._base.iterdir():
            if not gall_dir.is_dir():
                continue
            for filepath in gall_dir.glob("*.jsonl"):
                # Nombre = YYYY-MM-DD.jsonl
                date_str = filepath.stem
                if date_str < cutoff_str:
                    try:
                        filepath.unlink()
                        deleted += 1
                    except Exception as e:
                        logger.warning(f"[BehaviorStore] Error deleting {filepath}: {e}")

        if deleted:
            logger.info(f"[BehaviorStore] Cleanup: {deleted} ficheros antiguos eliminados")
        return deleted

    def get_stats(self, gallinero_id: str | None = None) -> dict:
        """Estadísticas del store: ficheros, tamaño total, snapshots estimados."""
        stats: dict = {"gallineros": {}, "total_files": 0, "total_bytes": 0}

        if not self._base.exists():
            return stats

        dirs = [self._base / gallinero_id] if gallinero_id else list(self._base.iterdir())
        for gall_dir in dirs:
            if not gall_dir.is_dir():
                continue
            files = list(gall_dir.glob("*.jsonl"))
            total_size = sum(f.stat().st_size for f in files)
            stats["gallineros"][gall_dir.name] = {
                "files": len(files),
                "bytes": total_size,
                "oldest": min((f.stem for f in files), default=""),
                "newest": max((f.stem for f in files), default=""),
            }
            stats["total_files"] += len(files)
            stats["total_bytes"] += total_size

        return stats


# ── Singleton ──

_store: BehaviorEventStore | None = None


def get_event_store() -> BehaviorEventStore:
    """Devuelve instancia singleton del event store."""
    global _store
    if _store is None:
        _store = BehaviorEventStore()
        # Cleanup al startup
        cleaned = _store.cleanup()
        if cleaned:
            logger.info(f"[BehaviorStore] Startup cleanup: {cleaned} ficheros eliminados")
    return _store
