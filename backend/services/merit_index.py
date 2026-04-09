"""
Seedy Backend — Servicio de cálculo del Índice de Mérito Genético (IM).

El IM combina 5 caracteres ponderados para puntuar cada ave de 0.00 a 1.00:
  - Peso relativo (vs Gompertz del cruce)
  - Conformación/marmoleo (visual + IA Vision)
  - Conversión alimentaria (invertida: menor = mejor)
  - Viabilidad/salud (antibióticos, cojeras, deformidades)
  - Docilidad (temperamento IA Vision)

Umbrales: ≥0.85 reproductor | 0.60–0.84 producción | <0.60 descarte.
Basado en genética cuantitativa (BLUP) y criterios NeoFarm.
"""

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.merit_index import (
    MeritInput,
    MeritResult,
    MeritWeights,
    SelectionCategory,
)

logger = logging.getLogger(__name__)

# ── Persistencia de historial IM ──────────────────────

_HISTORY_DIR = Path(os.environ.get("MERIT_HISTORY_DIR", "/app/data/merit_history"))
try:
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    _HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "merit_history"
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)


# ── Gompertz — peso objetivo dinámico ─────────────────

# Parámetros por gallinero de selección (Palacio G1-G5)
# W(t) = W_inf * exp(-exp(-k * (t - t_inflection)))
GOMPERTZ_PARAMS = {
    "G1": {"W_inf": 3500, "k": 0.028, "t_inflection": 70},    # Bresse×Sulmtaler
    "G2": {"W_inf": 4200, "k": 0.025, "t_inflection": 75},    # Sussex×Sussex
    "G3": {"W_inf": 4500, "k": 0.024, "t_inflection": 80},    # Orpington×mixed
    "G4": {"W_inf": 3800, "k": 0.026, "t_inflection": 73},    # Sussex×españolas
    "G5": {"W_inf": 2800, "k": 0.032, "t_inflection": 60},    # Vorwerk×Araucana
}

# Fallback por raza (de birds.py Gompertz existente, convertido a W_inf)
GOMPERTZ_BY_BREED = {
    "sussex":    {"W_inf": 4200, "k": 0.025, "t_inflection": 75},
    "bresse":    {"W_inf": 3800, "k": 0.028, "t_inflection": 70},
    "marans":    {"W_inf": 3500, "k": 0.026, "t_inflection": 73},
    "sulmtaler": {"W_inf": 3200, "k": 0.024, "t_inflection": 78},
    "orpington": {"W_inf": 4500, "k": 0.024, "t_inflection": 80},
    "vorwerk":   {"W_inf": 2800, "k": 0.032, "t_inflection": 60},
    "araucana":  {"W_inf": 2500, "k": 0.033, "t_inflection": 58},
    "castellana": {"W_inf": 2600, "k": 0.031, "t_inflection": 60},
    "pita_pinta": {"W_inf": 3400, "k": 0.027, "t_inflection": 72},
}

# Default genérico heritage
_DEFAULT_GOMPERTZ = {"W_inf": 3500, "k": 0.026, "t_inflection": 73}


def gompertz_weight(age_days: int, W_inf: float, k: float, t_inflection: float) -> float:
    """Peso predicho (gramos) por el modelo Gompertz."""
    return W_inf * math.exp(-math.exp(-k * (age_days - t_inflection)))


def get_target_weight(
    age_weeks: int,
    gallinero: Optional[str] = None,
    breed: Optional[str] = None,
) -> float:
    """Obtiene el peso objetivo para un ave según gallinero o raza."""
    age_days = age_weeks * 7
    # Intentar por gallinero primero
    if gallinero:
        params = GOMPERTZ_PARAMS.get(gallinero.upper())
        if params:
            return gompertz_weight(age_days, **params)
    # Luego por raza
    if breed:
        params = GOMPERTZ_BY_BREED.get(breed.lower())
        if params:
            return gompertz_weight(age_days, **params)
    # Fallback genérico
    return gompertz_weight(age_days, **_DEFAULT_GOMPERTZ)


# ── Cálculo de viabilidad ─────────────────────────────

def calculate_viability(inp: MeritInput) -> float:
    """
    Score de viabilidad/salud [0, 1].

    Regla de locomoción refinada (consensuada con el criador):
    - Antibióticos alguna vez = 0.0 (descarte programa reproductor)
    - Deformidad estructural = 0.0
    - Cojera crónica (>72h + asimétrica + progresiva) = 0.2
    - Cojera transitoria (resuelta <48h) = 0.7 (pollitos torpones = normal)
    - Sin problemas = 1.0
    """
    if inp.has_antibiotics or inp.has_deformity:
        return 0.0
    if inp.has_chronic_lameness:
        return 0.2
    if inp.has_transient_lameness:
        return 0.7
    return 1.0


# ── Cálculo principal del IM ──────────────────────────

def calculate_merit_index(
    inp: MeritInput,
    weights: Optional[MeritWeights] = None,
) -> MeritResult:
    """
    Calcula el Índice de Mérito Genético (IM) para un ave.
    Score compuesto 0.00–1.00, 5 caracteres ponderados.
    """
    w = weights or MeritWeights()

    # Peso objetivo: del input o calculado por Gompertz
    target = inp.target_weight_grams
    if target is None or target <= 0:
        target = get_target_weight(inp.age_weeks, inp.gallinero)
    if target <= 0:
        target = 1.0  # safety

    # Normalizar cada componente a [0, 1]
    p_norm = min(inp.weight_grams / target, 1.0)

    # Conformación con bonus por cata de hermano capón
    conf_raw = min(inp.conformacion_score + inp.sibling_tasting_bonus, 5.0)
    m_norm = conf_raw / 5.0

    if inp.conversion_ratio is not None and inp.max_conversion > 0:
        c_norm = 1.0 - min(inp.conversion_ratio / inp.max_conversion, 1.0)
    else:
        c_norm = 0.5  # Default neutral si no hay datos

    v_norm = calculate_viability(inp)
    d_norm = inp.docilidad_score / 5.0

    components = {
        "peso": round(p_norm, 3),
        "conformacion": round(m_norm, 3),
        "conversion": round(c_norm, 3),
        "viabilidad": round(v_norm, 3),
        "docilidad": round(d_norm, 3),
    }

    weighted = {
        "peso": round(p_norm * w.peso, 4),
        "conformacion": round(m_norm * w.conformacion, 4),
        "conversion": round(c_norm * w.conversion, 4),
        "viabilidad": round(v_norm * w.viabilidad, 4),
        "docilidad": round(d_norm * w.docilidad, 4),
    }

    im_score = round(sum(weighted.values()), 3)
    im_score = min(im_score, 1.0)  # clamp

    # Categorización
    sex_label = ""
    if inp.sex == "male":
        sex_label = " (macho)"
    elif inp.sex == "female":
        sex_label = " (hembra)"

    if im_score >= 0.85:
        category = SelectionCategory.REPRODUCTOR
        recommendation = (
            f"Ave {inp.bird_id}{sex_label}: IM={im_score:.2f} → REPRODUCTOR. "
            "Candidato a padre/madre de siguiente generación. Reservar para clanes de cría."
        )
    elif im_score >= 0.60:
        category = SelectionCategory.PRODUCCION
        if inp.sex == "male":
            destino = "capón"
        elif inp.sex == "female":
            destino = "pularda o ponedora"
        else:
            destino = "capón (macho) o pularda/ponedora (hembra)"
        recommendation = (
            f"Ave {inp.bird_id}{sex_label}: IM={im_score:.2f} → PRODUCCIÓN. "
            f"Destinar a {destino}. "
            "Buen individuo pero no top para reproducción."
        )
    else:
        category = SelectionCategory.DESCARTE
        recommendation = (
            f"Ave {inp.bird_id}{sex_label}: IM={im_score:.2f} → DESCARTE. "
            "Vender como pollo campero o engorde. No aporta al programa genético."
        )

    result = MeritResult(
        bird_id=inp.bird_id,
        im_score=im_score,
        category=category,
        components=components,
        weighted_components=weighted,
        weights_used=w,
        calculated_at=datetime.utcnow(),
        age_weeks=inp.age_weeks,
        recommendation=recommendation,
    )

    # Persistir en historial
    _save_history(result)

    return result


# ── Historial de IM ───────────────────────────────────

def _save_history(result: MeritResult) -> None:
    """Guarda resultado en JSONL por ave (para evolución temporal)."""
    try:
        path = _HISTORY_DIR / f"{result.bird_id}.jsonl"
        record = {
            "bird_id": result.bird_id,
            "im_score": result.im_score,
            "category": result.category.value,
            "components": result.components,
            "age_weeks": result.age_weeks,
            "calculated_at": result.calculated_at.isoformat(),
        }
        with open(path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[MeritIndex] No se pudo guardar historial para {result.bird_id}: {e}")


def get_history(bird_id: str) -> list[dict]:
    """Devuelve el historial de IM de un ave."""
    path = _HISTORY_DIR / f"{bird_id}.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text().strip().split("\n"):
        if line:
            records.append(json.loads(line))
    return records


# ── Guard IM × COI ────────────────────────────────────

COI_BLOCK_THRESHOLD = 0.25  # F esperado de la cría > esto → bloquear apareamiento


def evaluate_pairing(
    sire: MeritInput,
    dam: MeritInput,
    expected_coi: float,
    weights: Optional[MeritWeights] = None,
) -> dict:
    """
    Evalúa un apareamiento propuesto: calcula IM de ambos y comprueba COI.

    El COI esperado de la descendencia se pasa como parámetro porque depende
    del pedigrí completo (calculado externamente con BLUPEngine.build_relationship_matrix).
    Fórmula: COI_offspring = A[sire, dam] / 2

    Returns:
        dict con IM de ambos, COI, decisión (APPROVED/BLOCKED) y motivos.
    """
    w = weights or MeritWeights()
    sire_result = calculate_merit_index(sire, w)
    dam_result = calculate_merit_index(dam, w)

    blocked = False
    warnings: list[str] = []

    # Guard 1: COI de descendencia
    if expected_coi > COI_BLOCK_THRESHOLD:
        blocked = True
        warnings.append(
            f"COI esperado de la cría = {expected_coi:.3f} (> {COI_BLOCK_THRESHOLD}). "
            "Riesgo de depresión endogámica. Apareamiento BLOQUEADO."
        )
    elif expected_coi > 0.125:
        warnings.append(
            f"COI esperado = {expected_coi:.3f} (equivalente a primos hermanos). "
            "Precaución: vigilar vigor de la descendencia."
        )

    # Guard 2: ambos deben ser REPRODUCTOR
    if sire_result.category != SelectionCategory.REPRODUCTOR:
        warnings.append(
            f"Padre {sire.bird_id}: IM={sire_result.im_score:.2f} → "
            f"{sire_result.category.value}. No es reproductor."
        )
    if dam_result.category != SelectionCategory.REPRODUCTOR:
        warnings.append(
            f"Madre {dam.bird_id}: IM={dam_result.im_score:.2f} → "
            f"{dam_result.category.value}. No es reproductora."
        )

    decision = "BLOCKED" if blocked else "APPROVED"

    return {
        "decision": decision,
        "sire": sire_result.model_dump(),
        "dam": dam_result.model_dump(),
        "expected_coi": round(expected_coi, 4),
        "coi_threshold": COI_BLOCK_THRESHOLD,
        "warnings": warnings,
    }
