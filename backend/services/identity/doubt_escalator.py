"""Seedy Backend — DoubtEscalator v4.2

Registra tracks con identidad ambigua para revisión manual.
Persiste en JSONL: data/behavior_events/{gallinero}/doubts/{YYYY-MM-DD}.jsonl
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_BASE_PATH = Path(_settings.behavior_event_store_path)


class DoubtEscalator:
    """Registra tracks con identidad dudosa para revisión."""

    def __init__(self, gallinero_id: str):
        self.gallinero_id = gallinero_id
        self._doubts_dir = _BASE_PATH / gallinero_id / "doubts"
        self._doubts_dir.mkdir(parents=True, exist_ok=True)
        # Cooldown: no logear la misma duda más de 1 vez por 5 min
        self._last_doubt: dict[int, float] = {}  # track_id → ts

    def mark(
        self,
        track_id: int,
        breed: str,
        sex: str,
        color: Optional[str],
        candidates: list[str],
        reason: str,
    ) -> bool:
        """Registra una duda de identidad.

        Args:
            track_id: ID del track ambiguo
            breed: breed detectada en el track
            sex: sex detectado
            color: color detectado (puede ser None)
            candidates: lista de ai_vision_ids candidatos (0, 2+)
            reason: causa de la duda

        Returns: True si se registró, False si estaba en cooldown.
        """
        now = time.time()
        last = self._last_doubt.get(track_id, 0)
        if now - last < 300:  # 5 min cooldown
            return False

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ts_unix": round(now, 2),
            "gallinero_id": self.gallinero_id,
            "track_id": track_id,
            "breed": breed,
            "sex": sex,
            "color": color,
            "candidates": candidates,
            "candidate_count": len(candidates),
            "reason": reason,
        }

        day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = self._doubts_dir / f"{day_str}.jsonl"
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._last_doubt[track_id] = now
            logger.info(
                f"❓ Doubt: track#{track_id} ({breed} {sex} {color or '?'}) "
                f"→ {len(candidates)} candidates, reason={reason}"
            )
            return True
        except Exception as e:
            logger.warning(f"[DoubtEscalator] Error writing: {e}")
            return False

    def query_recent(self, hours: int = 24) -> list[dict]:
        """Lee las dudas recientes."""
        results = []
        cutoff = time.time() - hours * 3600
        # Leer los últimos 2 días de ficheros para cubrir la ventana
        for day_offset in range(2):
            day = datetime.now(timezone.utc)
            if day_offset:
                from datetime import timedelta
                day = day - timedelta(days=day_offset)
            day_str = day.strftime("%Y-%m-%d")
            filepath = self._doubts_dir / f"{day_str}.jsonl"
            if not filepath.exists():
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        if record.get("ts_unix", 0) >= cutoff:
                            results.append(record)
            except Exception as e:
                logger.warning(f"[DoubtEscalator] Error reading {filepath}: {e}")
        return results


# ── Singletons por gallinero ──
_escalators: dict[str, DoubtEscalator] = {}


def get_doubt_escalator(gallinero_id: str) -> DoubtEscalator:
    if gallinero_id not in _escalators:
        _escalators[gallinero_id] = DoubtEscalator(gallinero_id)
    return _escalators[gallinero_id]
