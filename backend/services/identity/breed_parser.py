"""Seedy Backend — Breed class parser v4.2

Parsea las clases YOLO breed (e.g., "sussex_silver_gallo") en
componentes estructurados: breed, color, sex.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Alias de color: normaliza nombres de color a español estándar ──
COLOR_ALIASES: dict[str, str] = {
    "blanc": "blanco", "white": "blanco",
    "silver": "plateado", "light": "plateado",
    "dore": "dorado", "golden": "dorado",
    "negro": "negro", "black": "negro", "noir": "negro",
    "azul": "azul", "blue": "azul", "bleu": "azul",
    "caoba": "caoba", "partridge": "aperdizado",
    "tricolor": "tricolor",
}

# ── Razas conocidas (para saber cuándo termina el breed y empieza el color) ──
KNOWN_BREEDS = {
    "sussex", "bresse", "marans", "vorwerk", "sulmtaler",
    "orpington", "araucana", "ameraucana", "andaluza_azul",
    "andaluza", "pita_pinta", "castellana", "gallina", "gallo",
    "pollito", "pollo_juvenil",
}

# Alias de razas para normalizar a nombre canónico del censo
BREED_ALIASES: dict[str, str] = {
    "ameraucana": "araucana",
}


def parse_breed_class(raw: str) -> dict:
    """Parsea una clase YOLO breed en componentes.

    Entrada: "sussex_silver_gallo"
    Salida:  {"breed": "Sussex", "color": "plateado", "sex": "macho",
              "breed_raw": "sussex", "color_raw": "silver", "raw_class": "sussex_silver_gallo"}

    Entrada: "bresse_gallo"  (sin color)
    Salida:  {"breed": "Bresse", "color": None, "sex": "macho", ...}

    Entrada: "pita_pinta_gallina"
    Salida:  {"breed": "Pita Pinta", "color": None, "sex": "hembra", ...}
    """
    result = {
        "breed": "",
        "color": None,
        "sex": "",
        "breed_raw": "",
        "color_raw": None,
        "raw_class": raw,
    }

    if not raw:
        return result

    raw_lower = raw.lower().strip()

    # 1. Extraer el sufijo de sexo
    sex = ""
    core = raw_lower
    if core.endswith("_gallina"):
        sex = "hembra"
        core = core[:-8]  # strip _gallina
    elif core.endswith("_gallo"):
        sex = "macho"
        core = core[:-6]  # strip _gallo
    result["sex"] = sex

    # 2. Intentar separar breed y color
    # Manejar razas compuestas (pita_pinta, andaluza_azul, pollo_juvenil)
    breed_raw = ""
    color_raw = None

    # Intentar match con razas conocidas de 2 tokens primero
    parts = core.split("_")
    if len(parts) >= 2 and "_".join(parts[:2]) in KNOWN_BREEDS:
        breed_raw = "_".join(parts[:2])
        remaining = parts[2:]
    elif len(parts) >= 1 and parts[0] in KNOWN_BREEDS:
        breed_raw = parts[0]
        remaining = parts[1:]
    else:
        # Fallback: todo es breed
        breed_raw = core
        remaining = []

    # Lo que queda después del breed es color
    if remaining:
        color_raw = "_".join(remaining)

    # 3. Normalizar
    # Breed: aplicar alias
    breed_norm = BREED_ALIASES.get(breed_raw, breed_raw)
    breed_display = breed_norm.replace("_", " ").title()

    # Color: aplicar alias
    color_norm = None
    if color_raw:
        color_norm = COLOR_ALIASES.get(color_raw.lower(), color_raw.lower())

    result["breed"] = breed_display
    result["breed_raw"] = breed_raw
    result["color"] = color_norm
    result["color_raw"] = color_raw

    return result


def normalize_color(color: Optional[str]) -> Optional[str]:
    """Normaliza un color a su forma canónica española."""
    if not color:
        return None
    return COLOR_ALIASES.get(color.lower().strip(), color.lower().strip())


# ── Alias de sexo: normaliza a forma canónica ──
SEX_ALIASES: dict[str, str] = {
    "macho": "male", "male": "male", "m": "male",
    "hembra": "female", "female": "female", "f": "female",
    "gallo": "male", "gallina": "female",
}


def normalize_sex(sex: Optional[str]) -> str:
    """Normaliza un sexo a 'male' o 'female' (formato registro)."""
    if not sex:
        return ""
    return SEX_ALIASES.get(sex.lower().strip(), sex.lower().strip())


def sexes_match(s1: Optional[str], s2: Optional[str]) -> bool:
    """Compara dos sexos con tolerancia a alias. Vacío == wildcard."""
    if not s1 or not s2:
        return True
    return normalize_sex(s1) == normalize_sex(s2)


def colors_match(c1: Optional[str], c2: Optional[str]) -> bool:
    """Compara dos colores con tolerancia a alias. None == wildcard."""
    if c1 is None or c2 is None:
        return True  # wildcard
    return normalize_color(c1) == normalize_color(c2)
