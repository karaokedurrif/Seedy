"""
Seedy — Flock Census Service

Carga el censo real de la cabaña (flock_census.json) y genera:
1. Contexto para el prompt de Gemini (qué razas buscar)
2. Cuotas para el registro (limitar a N aves por raza+color+sexo)
3. Estado de asignación (cuántas ya identificadas vs esperadas)
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CENSUS_PATH = Path(__file__).parent.parent / "config" / "flock_census.json"
_census: dict = {}


def _load():
    global _census
    if _census:
        return
    try:
        _census = json.loads(_CENSUS_PATH.read_text(encoding="utf-8"))
        total = sum(
            sum(e["cantidad"] for e in g["aves"])
            for k, g in _census.items() if k.startswith("gallinero_")
        )
        logger.info(f"🐔 Flock census loaded: {total} aves from {_CENSUS_PATH.name}")
    except Exception as e:
        logger.warning(f"Could not load flock census: {e}")
        _census = {}


def reload():
    """Fuerza recarga del censo (tras editar el JSON)."""
    global _census
    _census = {}
    _load()


def get_census(gallinero_id: str) -> list[dict]:
    """Devuelve la lista de aves esperadas en un gallinero."""
    _load()
    gal = _census.get(gallinero_id, {})
    return gal.get("aves", [])


def get_all_gallineros() -> dict:
    """Devuelve todo el censo."""
    _load()
    return {
        k: v for k, v in _census.items()
        if k.startswith("gallinero_")
    }


def _get_sin_asignar() -> list[dict]:
    """Devuelve aves sin_asignar (pueden estar en cualquier gallinero)."""
    _load()
    sa = _census.get("sin_asignar", {})
    return sa.get("aves", []) if isinstance(sa, dict) else []


def _get_visitor_gallinero(gallinero_id: str) -> str | None:
    """Devuelve el ID del gallinero de visitantes permitidos, si existe."""
    _load()
    gal = _census.get(gallinero_id, {})
    return gal.get("permite_visitantes_de") if isinstance(gal, dict) else None


def get_expected_breeds(gallinero_id: str, include_roaming: bool = True) -> list[dict]:
    """Lista de (raza, color, sexo, cantidad) con cantidad > 0.

    Si include_roaming=True, incluye sin_asignar y visitantes permitidos.
    """
    own = [
        e for e in get_census(gallinero_id)
        if e.get("cantidad", 0) > 0
    ]
    if not include_roaming:
        return own

    # Añadir sin_asignar (aves libres entre gallineros)
    for e in _get_sin_asignar():
        if e.get("cantidad", 0) > 0:
            own.append(e)

    # Añadir visitantes del gallinero permitido
    visitor_gal = _get_visitor_gallinero(gallinero_id)
    if visitor_gal:
        for e in get_census(visitor_gal):
            if e.get("cantidad", 0) > 0:
                own.append(e)

    return own


def get_all_breeds() -> set[str]:
    """Devuelve un set con todas las razas (lowercase) de toda la cabaña,
    incluyendo sin_asignar."""
    _load()
    breeds: set[str] = set()
    for key, val in _census.items():
        if isinstance(val, dict) and "aves" in val:
            for e in val["aves"]:
                if e.get("raza"):
                    breeds.add(e["raza"].lower())
    return breeds


def get_canonical_breed_name(breed_lower: str) -> str:
    """Devuelve el nombre canónico (con mayúsculas originales) de una raza."""
    _load()
    for val in _census.values():
        if isinstance(val, dict):
            for e in val.get("aves", []):
                if e.get("raza", "").lower() == breed_lower:
                    return e["raza"]
    return breed_lower.title()


def get_quota(gallinero_id: str, breed: str, color: str, sex: str) -> int:
    """Cuántas aves de esta raza+color+sexo se esperan para REGISTRO.

    Busca en: 1) censo propio, 2) sin_asignar.
    NO incluye visitantes de otro gallinero — esas aves se reconocen
    pero se registran en su gallinero de origen.
    """
    def _match(entries: list[dict]) -> int:
        for e in entries:
            if (e["raza"].lower() == breed.lower()
                    and e["color"].lower() == color.lower()
                    and e["sexo"] == sex
                    and e.get("cantidad", 0) > 0):
                return e["cantidad"]
        return 0

    # 1) Censo propio del gallinero
    q = _match(get_census(gallinero_id))
    if q > 0:
        return q

    # 2) Sin asignar (aves libres entre gallineros)
    q = _match(_get_sin_asignar())
    if q > 0:
        return q

    return 0


def build_gemini_context(gallinero_id: str, registered: list[dict] | None = None) -> str:
    """Genera contexto textual del censo para inyectar en el prompt de Gemini.

    Args:
        gallinero_id: ID del gallinero
        registered: lista de aves ya registradas [{breed, color, sex, ai_vision_id}]

    Returns:
        Texto para anteponer al prompt de identificación
    """
    _load()
    entries = get_expected_breeds(gallinero_id)
    if not entries:
        return ""

    gal_name = _census.get(gallinero_id, {}).get("name", gallinero_id)
    registered = registered or []

    # Contar cuántas ya tenemos por (raza, color, sexo)
    from collections import Counter
    have: Counter = Counter()
    for r in registered:
        key = (r.get("breed", "").lower(), r.get("color", "").lower(), r.get("sex", "unknown"))
        have[key] += 1

    lines = [
        f"CONTEXTO: Este es el {gal_name}.",
        "La cabaña real contiene EXACTAMENTE estas aves (no inventes razas que no estén en la lista):",
        "",
    ]

    pending_any = False
    for e in entries:
        key = (e["raza"].lower(), e["color"].lower(), e["sexo"])
        n_have = have[key]
        n_total = e["cantidad"]
        n_pending = max(0, n_total - n_have)
        status = f"✅ todas identificadas" if n_pending == 0 else f"⏳ {n_pending} pendiente(s)"
        if n_pending > 0:
            pending_any = True
        sexo_txt = "♂" if e["sexo"] == "male" else "♀"
        lines.append(
            f"  • {e['raza']} {e['color']} {sexo_txt} — {n_total} total, {n_have} identificadas ({status})"
        )
        if e.get("notas"):
            lines.append(f"    Rasgos: {e['notas']}")

    lines.append("")
    if pending_any:
        lines.append(
            "PRIORIDAD: Identifica aves de las razas PENDIENTES (⏳). "
            "Usa los rasgos indicados para distinguirlas. "
            "Si un ave no coincide con ninguna raza de la lista, pon breed='Desconocida'."
        )
    else:
        lines.append(
            "Todas las aves están identificadas. "
            "Solo confirma presencia/ausencia de las ya registradas."
        )

    return "\n".join(lines)


def get_assignment_status(gallinero_id: str, registered: list[dict]) -> dict:
    """Estado de asignación por raza para dashboard/API.

    Returns:
        {"entries": [{raza, color, sexo, expected, assigned, pending, vision_ids}], "total_expected", "total_assigned"}
    """
    entries = get_expected_breeds(gallinero_id)
    from collections import defaultdict

    # Agrupar registradas por (raza, color, sexo)
    grouped: dict[tuple, list] = defaultdict(list)
    for r in registered:
        key = (r.get("breed", "").lower(), r.get("color", "").lower(), r.get("sex", "unknown"))
        grouped[key].append(r.get("ai_vision_id", ""))

    result = []
    total_exp = 0
    total_ass = 0
    for e in entries:
        key = (e["raza"].lower(), e["color"].lower(), e["sexo"])
        ids = grouped.get(key, [])
        n = e["cantidad"]
        total_exp += n
        total_ass += min(len(ids), n)
        result.append({
            "raza": e["raza"],
            "color": e["color"],
            "sexo": e["sexo"],
            "expected": n,
            "assigned": len(ids),
            "pending": max(0, n - len(ids)),
            "vision_ids": ids[:n],  # cap at quota
        })

    return {
        "entries": result,
        "total_expected": total_exp,
        "total_assigned": total_ass,
        "completion_pct": round(total_ass / total_exp * 100, 1) if total_exp else 0,
    }
