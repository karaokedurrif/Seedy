"""Seedy Backend — IdentityLock + AssignmentRegistry v4.2

IdentityLock: bloqueo de identidad confirmada en un BirdTrack.
AssignmentRegistry: singleton que garantiza que un ai_vision_id
solo puede estar asignado a un track activo a la vez.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ──
CONFIDENCE_DECAY_INTERVAL = 600   # 10 min
CONFIDENCE_DECAY_FACTOR = 0.95    # ×0.95 cada intervalo
CONFIDENCE_UNLOCK_THRESHOLD = 0.50  # debajo de esto, se desbloquea
CONFIDENCE_STEAL_MARGIN = 0.10    # para robar un ID: conf > current + margin


@dataclass
class IdentityLock:
    """Bloqueo de identidad para un BirdTrack."""
    ai_vision_id: str
    breed: str
    color: Optional[str]
    sex: Optional[str]
    confidence: float
    locked_at: float
    last_confirmed: float  # último classify coincidente
    vote_count: int
    reason: str  # "breed+sex+color unique" | "voting_consensus" | "manual_enroll"

    def should_decay(self, now: float | None = None) -> bool:
        """True si ha pasado suficiente tiempo sin confirmación."""
        now = now or time.time()
        return (now - self.last_confirmed) >= CONFIDENCE_DECAY_INTERVAL

    def apply_decay(self, now: float | None = None) -> bool:
        """Aplica decay. Devuelve True si el lock sigue activo, False si debe desbloquearse."""
        now = now or time.time()
        elapsed = now - self.last_confirmed
        intervals = int(elapsed / CONFIDENCE_DECAY_INTERVAL)
        if intervals > 0:
            self.confidence *= CONFIDENCE_DECAY_FACTOR ** intervals
            self.confidence = round(self.confidence, 4)
        return self.confidence >= CONFIDENCE_UNLOCK_THRESHOLD

    def refresh(self, confidence: float) -> None:
        """Refresca el lock con una nueva confirmación."""
        self.confidence = max(self.confidence, confidence)
        self.last_confirmed = time.time()


class AssignmentRegistry:
    """Registro centralizado de asignaciones ai_vision_id → track_id.

    Garantiza que un ai_vision_id no esté asignado a dos tracks simultáneamente.
    Singleton por gallinero.
    """

    def __init__(self):
        # ai_vision_id → (track_id, confidence)
        self._assignments: dict[str, tuple[int, float]] = {}
        # track_id → ai_vision_id (inverso)
        self._track_to_id: dict[int, str] = {}

    def claim(self, track_id: int, ai_vision_id: str, confidence: float) -> bool:
        """Intenta asignar ai_vision_id a track_id.

        Éxito si:
        - El ID no está tomado, o
        - El reclamante tiene confidence > current + STEAL_MARGIN

        Returns: True si la asignación se concedió.
        """
        current = self._assignments.get(ai_vision_id)

        if current is not None:
            current_tid, current_conf = current
            if current_tid == track_id:
                # Ya lo tiene — refrescar confidence
                self._assignments[ai_vision_id] = (track_id, max(current_conf, confidence))
                return True
            if confidence <= current_conf + CONFIDENCE_STEAL_MARGIN:
                logger.info(
                    f"⚔️ Claim rechazado: track#{track_id} quiere {ai_vision_id} "
                    f"(conf={confidence:.2f}) pero track#{current_tid} lo tiene "
                    f"(conf={current_conf:.2f})"
                )
                return False
            # Robar
            logger.warning(
                f"⚔️ Claim robado: track#{track_id} (conf={confidence:.2f}) "
                f"roba {ai_vision_id} de track#{current_tid} (conf={current_conf:.2f})"
            )
            self._track_to_id.pop(current_tid, None)

        # Liberar cualquier ID previo del track
        old_id = self._track_to_id.get(track_id)
        if old_id and old_id != ai_vision_id:
            self._assignments.pop(old_id, None)

        self._assignments[ai_vision_id] = (track_id, confidence)
        self._track_to_id[track_id] = ai_vision_id
        logger.info(
            f"🔒 Claim exitoso: track#{track_id} → {ai_vision_id} (conf={confidence:.2f})"
        )
        return True

    def release(self, track_id: int) -> Optional[str]:
        """Libera la asignación de un track (timeout/lost).

        Returns: ai_vision_id liberado, o None.
        """
        vid = self._track_to_id.pop(track_id, None)
        if vid:
            current = self._assignments.get(vid)
            if current and current[0] == track_id:
                del self._assignments[vid]
            logger.info(f"🔓 Released: track#{track_id} liberó {vid}")
        return vid

    def is_taken(self, ai_vision_id: str) -> bool:
        """¿Está este ai_vision_id asignado a algún track activo?"""
        return ai_vision_id in self._assignments

    def get_taken_ids(self) -> set[str]:
        """Devuelve los ai_vision_ids actualmente asignados."""
        return set(self._assignments.keys())

    def get_assignment(self, ai_vision_id: str) -> Optional[tuple[int, float]]:
        """Devuelve (track_id, confidence) o None."""
        return self._assignments.get(ai_vision_id)

    def get_track_id(self, track_id: int) -> Optional[str]:
        """Devuelve el ai_vision_id asignado a un track."""
        return self._track_to_id.get(track_id)

    def clear(self) -> None:
        """Reset completo."""
        self._assignments.clear()
        self._track_to_id.clear()

    def get_summary(self) -> dict:
        """Resumen para diagnóstico."""
        return {
            "total_assignments": len(self._assignments),
            "assignments": {
                vid: {"track_id": tid, "confidence": round(conf, 3)}
                for vid, (tid, conf) in self._assignments.items()
            },
        }


# ── Singletons por gallinero ──
_registries: dict[str, AssignmentRegistry] = {}


def get_registry(gallinero_id: str) -> AssignmentRegistry:
    if gallinero_id not in _registries:
        _registries[gallinero_id] = AssignmentRegistry()
    return _registries[gallinero_id]
