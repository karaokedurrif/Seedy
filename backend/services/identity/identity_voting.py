"""Seedy Backend — Identity Voting Buffer v4.2

Acumula votos de clasificación por track antes de asignar identidad.
Requiere N votos consistentes en una ventana temporal para confirmar.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Config ──
VOTE_WINDOW_SEC = 60        # Ventana temporal para acumular votos
MIN_CONSISTENT_VOTES = 3    # Mínimo de votos coincidentes (breed+sex)
MAX_VOTES = 5               # Máximo de votos en buffer
MIN_MEAN_CONFIDENCE = 0.70  # Confianza media mínima para confirmar


@dataclass
class Vote:
    """Un voto de clasificación para un track."""
    ts: float
    breed: str
    color: str | None
    sex: str
    confidence: float


@dataclass
class VoteResult:
    """Resultado del análisis de votos."""
    confirmed: bool
    breed: str = ""
    color: str | None = None
    sex: str = ""
    mean_confidence: float = 0.0
    vote_count: int = 0
    reason: str = ""


class IdentityVotingBuffer:
    """Buffer de votos por track_id.

    Cada vez que classify_breed_crop identifica algo para un track,
    se añade un voto. Cuando el buffer tiene suficientes votos
    consistentes, emite una confirmación.
    """

    def __init__(
        self,
        window_sec: float = VOTE_WINDOW_SEC,
        min_votes: int = MIN_CONSISTENT_VOTES,
        max_votes: int = MAX_VOTES,
        min_confidence: float = MIN_MEAN_CONFIDENCE,
    ):
        self._window = window_sec
        self._min_votes = min_votes
        self._max_votes = max_votes
        self._min_conf = min_confidence
        # track_id → list[Vote]
        self._buffers: dict[int, list[Vote]] = defaultdict(list)

    def add_vote(
        self,
        track_id: int,
        breed: str,
        color: str | None,
        sex: str,
        confidence: float,
    ) -> VoteResult:
        """Añade un voto y evalúa si hay consenso.

        Returns:
            VoteResult con confirmed=True si se alcanza consenso.
        """
        now = time.time()
        vote = Vote(ts=now, breed=breed, color=color, sex=sex, confidence=confidence)

        buf = self._buffers[track_id]
        buf.append(vote)

        # Purgar votos fuera de ventana
        cutoff = now - self._window
        buf[:] = [v for v in buf if v.ts >= cutoff]

        # Limitar tamaño (FIFO)
        if len(buf) > self._max_votes:
            buf[:] = buf[-self._max_votes:]

        # Evaluar consenso
        return self._evaluate(track_id)

    def _evaluate(self, track_id: int) -> VoteResult:
        """Evalúa si los votos del track alcanzan consenso."""
        buf = self._buffers.get(track_id, [])
        if len(buf) < self._min_votes:
            return VoteResult(
                confirmed=False,
                reason=f"insufficient_votes ({len(buf)}/{self._min_votes})",
            )

        # Agrupar por (breed, sex) — color puede variar
        groups: dict[tuple[str, str], list[Vote]] = defaultdict(list)
        for v in buf:
            key = (v.breed.lower(), v.sex.lower())
            groups[key].append(v)

        # Buscar el grupo mayoritario
        best_key = max(groups, key=lambda k: len(groups[k]))
        best_votes = groups[best_key]

        if len(best_votes) < self._min_votes:
            return VoteResult(
                confirmed=False,
                reason=f"no_majority ({len(best_votes)}/{self._min_votes} for {best_key})",
            )

        mean_conf = sum(v.confidence for v in best_votes) / len(best_votes)
        if mean_conf < self._min_conf:
            return VoteResult(
                confirmed=False,
                breed=best_key[0],
                sex=best_key[1],
                mean_confidence=round(mean_conf, 3),
                vote_count=len(best_votes),
                reason=f"low_confidence ({mean_conf:.2f} < {self._min_conf})",
            )

        # Consenso alcanzado — extraer el color más frecuente (no-None)
        color_votes = [v.color for v in best_votes if v.color]
        best_color = None
        if color_votes:
            from collections import Counter
            best_color = Counter(color_votes).most_common(1)[0][0]

        return VoteResult(
            confirmed=True,
            breed=best_key[0],
            color=best_color,
            sex=best_key[1],
            mean_confidence=round(mean_conf, 3),
            vote_count=len(best_votes),
            reason="consensus",
        )

    def get_votes(self, track_id: int) -> list[Vote]:
        """Devuelve los votos actuales de un track."""
        return list(self._buffers.get(track_id, []))

    def clear(self, track_id: int) -> None:
        """Limpia los votos de un track."""
        self._buffers.pop(track_id, None)

    def clear_all(self) -> None:
        """Limpia todos los buffers."""
        self._buffers.clear()
