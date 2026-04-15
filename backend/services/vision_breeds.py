"""
Seedy — Vision Breed Helpers

Breed classification, census matching, normalization, and OvoSfera matching
utilities extracted from routers/vision_identify.py.
"""

import logging

logger = logging.getLogger(__name__)

# ── Prompt especializado para identificar aves individuales ──

BIRD_ID_PROMPT = """Analiza esta imagen de un gallinero.

TAREA: Identifica CADA ave visible individualmente.

Para CADA ave que veas, devuelve EXACTAMENTE un bloque JSON con:
{
  "birds": [
    {
      "breed": "nombre de la raza",
      "color": "color principal del plumaje en español",
      "sex": "male" o "female" o "unknown",
      "confidence": 0.0-1.0,
      "bbox": [x1, y1, x2, y2],
      "distinguishing_features": "rasgos distintivos breves"
    }
  ],
  "total_visible": número total de aves visibles,
  "conditions": "breve descripción del gallinero (luz, actividad)"
}

RAZAS POSIBLES EN ESTA CABAÑA (solo estas, no inventes otras):
- Sussex White (armiñada): blanca con RAYAS NEGRAS en cuello (armiñado). NO es igual a Bresse.
- Sussex Light (Silver): plateada con marcas negras. Gallo grande (4.5kg).
- Bresse: completamente blanca, SIN rayas en cuello, más pequeña (2kg), patas GRIS AZULADO.
- Marans: negro cobrizo, reflejos cobrizos en cuello.
- Araucana: trigueña o negra. Sin cola (rumpless). Huevos azules/verdes.
- Ameraucana: trigueña, similar a araucana pero con cola.
- Sulmtaler: trigueño/atigrado (Weizenfarbig). Cresta pequeña, porte elegante.
- Andaluza Azul: gris azulado uniforme, cresta grande simple.
- Pita Pinta Asturiana: blanca con muchos puntos/motas negros distribuidos (pinta).
- Vorwerk: cuerpo leonado/dorado, cuello y cola NEGROS.
- Cruce F1: fenotipo mixto, color variado.

CLAVES PARA NO CONFUNDIR:
- Sussex White vs Bresse: Sussex tiene rayas negras en cuello (armiñada), Bresse es blanca pura con patas azuladas.
- Pita Pinta vs Sussex White: Pita Pinta tiene motas/puntos negros distribuidos por todo el cuerpo (no solo cuello).
- Vorwerk vs Sulmtaler: Vorwerk tiene cuello/cola negro con cuerpo dorado. Sulmtaler es trigueño atigrado sin contraste tan marcado.

REGLAS:
- El campo 'color' es OBLIGATORIO.
- bbox: coordenadas normalizadas [0.0-1.0] [x1_sup_izq, y1_sup_izq, x2_inf_der, y2_inf_der].
- Si el sexo es evidente (cresta grande, cola larga = male; más pequeña = female), indícalo.
- Confianza: 0.9+ si evidente, 0.5-0.8 si razonable, <0.5 si dudosa.
- Si no se distingue la raza, pon "breed": "Desconocida".
- Responde SOLO con el JSON, sin texto adicional."""

# ── Abreviaturas de color para generar ai_vision_id compactos ──

_COLOR_ABBREV = {
    "blanco": "bl", "blanca": "bl", "white": "bl",
    "negro": "ng", "negra": "ng", "black": "ng",
    "silver": "silver", "plateado": "silver", "plateada": "silver",
    "dorado": "gold", "dorada": "gold", "gold": "gold",
    "azul": "az", "blue": "az",
    "rojo": "rj", "roja": "rj", "red": "rj",
    "pardo": "pardo", "parda": "pardo", "brown": "pardo",
    "leonado": "leon", "leonada": "leon", "buff": "leon",
    "barrado": "barr", "barrada": "barr", "barred": "barr",
    "negro cobrizo": "nc", "negra cobriza": "nc",
    "gris": "gris", "grey": "gris", "gray": "gris",
    "perdiz": "perdiz", "partridge": "perdiz",
    "splash": "splash",
    "tricolor": "tri",
}

# ── Abreviaturas de raza ──

_BREED_ABBREV = {
    "sussex": "sussex",
    "bresse": "bresse",
    "marans": "marans",
    "orpington": "orpington",
    "araucana": "araucana",
    "sulmtaler": "sulmtaler",
    "andaluza azul": "andaluza",
    "andaluza": "andaluza",
    "pita pinta": "pitapinta",
    "vorwerk": "vorwerk",
    "castellana negra": "castellana",
    "castellana": "castellana",
    "cruce f1": "cruceF1",
    "cruce": "cruceF1",
    "plymouth rock": "plymouth",
}


def build_vision_id(breed: str, color: str, seq: int) -> str:
    """Genera ai_vision_id compacto: sussexbl1, maransnc2, etc."""
    breed_low = breed.strip().lower()
    color_low = color.strip().lower()
    breed_slug = _BREED_ABBREV.get(breed_low, breed_low.replace(" ", ""))
    color_slug = _COLOR_ABBREV.get(color_low, color_low.split()[0][:4] if color_low else "x")
    return f"{breed_slug}{color_slug}{seq}"


# ── OvoSfera breed/color matching ──

_BREED_OVOSFERA_ALIASES = {
    "f1 (cruce)": ["cruce f1", "cruce", "f1"],
    "cruce f1": ["f1 (cruce)", "cruce", "f1"],
    "cruce": ["cruce f1", "f1 (cruce)"],
    "pita pinta": ["pita pinta asturiana"],
    "pita pinta asturiana": ["pita pinta"],
}

_COLOR_OVOSFERA_ALIASES = {
    "silver": ["light (silver)", "plateado", "plateada"],
    "dorado": ["gold-black", "gold", "dorada"],
    "blanco": ["white", "blanca"],
    "negro cobrizo": ["black copper", "negra cobriza"],
    "trigueño": ["wheaten (weizenfarbig)", "wheaten", "trigueña"],
    "variado": ["varied", "variada"],
    "azul": ["blue"],
    "negro": ["negra", "black"],
    "pinta": ["mottled"],
    # reverse mappings (OvoSfera → census)
    "light (silver)": ["silver", "plateado"],
    "gold-black": ["dorado", "gold"],
    "white": ["blanco", "blanca"],
    "black copper": ["negro cobrizo"],
    "wheaten (weizenfarbig)": ["trigueño", "wheaten"],
}


def match_breed_ovosfera(seedy_breed: str, ovo_breed: str) -> bool:
    """Check if Seedy breed matches OvoSfera breed (handles aliases)."""
    a = seedy_breed.lower().strip()
    b = ovo_breed.lower().strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    return b in _BREED_OVOSFERA_ALIASES.get(a, [])


def match_color_ovosfera(seedy_color: str, ovo_color: str) -> bool:
    """Check if Seedy color matches OvoSfera color (handles aliases)."""
    a = seedy_color.lower().strip()
    b = ovo_color.lower().strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    return b in _COLOR_OVOSFERA_ALIASES.get(a, [])


# ── Breed YOLO → Census mapping ──

BREED_YOLO_TO_CENSUS = {
    "vorwerk_gallina":         ("Vorwerk",        "dorado",        "female"),
    "vorwerk_gallo":           ("Vorwerk",        "dorado",        "male"),
    "sussex_silver_gallina":   ("Sussex",         "silver",        "female"),
    "sussex_silver_gallo":     ("Sussex",         "silver",        "male"),
    "sussex_white_gallina":    ("Sussex",         "white",         "female"),
    "sulmtaler_gallina":       ("Sulmtaler",      "trigueño",      "female"),
    "sulmtaler_gallo":         ("Sulmtaler",      "trigueño",      "male"),
    "marans_gallina":          ("Marans",         "negro cobrizo", "female"),
    "bresse_gallina":          ("Bresse",         "blanco",        "female"),
    "bresse_gallo":            ("Bresse",         "blanco",        "male"),
    "andaluza_azul_gallina":   ("Andaluza Azul",  "azul",          "female"),
    "pita_pinta_gallina":      ("Pita Pinta",     "pinta",         "female"),
    "araucana_gallina":        ("Araucana",       "trigueño",      "female"),
    "ameraucana_gallina":      ("Ameraucana",     "trigueño",      "female"),
}

# Razas que NO están en YOLO → se detectan por descarte del censo
FALLBACK_BREEDS = {
    "F1 (cruce)":       {"color": "variado",   "sexo": "female"},
    "Araucana (negra)": {"color": "negra",     "sexo": "female"},
}


def map_sex(sex_str: str) -> str:
    """Normaliza sex string de Together (gallina/gallo) → male/female/unknown."""
    s = sex_str.lower().strip()
    if s in ("gallina", "female", "hembra"):
        return "female"
    if s in ("gallo", "male", "macho"):
        return "male"
    return "unknown"


# ── Breed classification functions ──

def classify_breeds_yolo(frame_bytes: bytes, yolo_result: dict) -> list[dict] | None:
    """Clasifica la raza de cada ave detectada por COCO YOLO usando el modelo de razas."""
    try:
        from services.yolo_detector import classify_breed_crop, crop_detections, get_breed_model
    except ImportError:
        return None

    if get_breed_model() is None:
        return None

    poultry = [d for d in yolo_result.get("detections", []) if d.get("category") == "poultry"]
    if not poultry:
        return None

    crops = crop_detections(frame_bytes, poultry)
    if not crops:
        return None

    birds = []
    for det, crop_bytes in zip(poultry, crops):
        breed_pred = classify_breed_crop(crop_bytes)

        if breed_pred and breed_pred["confidence"] >= 0.35:
            breed_class = breed_pred["breed_class"]
            census_info = BREED_YOLO_TO_CENSUS.get(breed_class)
            if census_info:
                breed, color, sex = census_info
                birds.append({
                    "breed": breed,
                    "color": color,
                    "sex": sex,
                    "confidence": breed_pred["confidence"],
                    "bbox": det["bbox_norm"],
                    "distinguishing_features": f"Breed YOLO: {breed_class} ({breed_pred['confidence']:.0%})",
                    "engine": "yolo_breed",
                })
                continue

        birds.append({
            "breed": "Desconocida",
            "color": "",
            "sex": "unknown",
            "confidence": det["confidence"],
            "bbox": det["bbox_norm"],
            "distinguishing_features": "Breed YOLO: sin match suficiente",
            "engine": "yolo_breed_unknown",
        })

    return birds if birds else None


def resolve_unknown_by_census(gallinero_id: str, birds: list[dict]) -> list[dict]:
    """Resuelve aves 'Desconocida' cruzando con el censo de la cabaña."""
    try:
        from services.flock_census import get_expected_breeds
    except ImportError:
        return birds

    census = get_expected_breeds(gallinero_id)
    if not census:
        return birds

    from collections import Counter
    identified_counts: Counter = Counter()
    for b in birds:
        if b["breed"] != "Desconocida":
            key = (b["breed"].lower(), b["sex"])
            identified_counts[key] += 1

    unmatched_census = []
    for entry in census:
        raza = entry["raza"]
        if raza == "Por determinar":
            continue
        color = entry["color"]
        sexo = entry["sexo"]
        cantidad = entry.get("cantidad", 0)

        key = (raza.lower(), sexo)
        already = identified_counts.get(key, 0)
        remaining = max(0, cantidad - already)

        if remaining > 0 and raza in FALLBACK_BREEDS:
            for _ in range(remaining):
                unmatched_census.append((raza, color, sexo))

    unknown_indices = [i for i, b in enumerate(birds) if b["breed"] == "Desconocida"]

    for idx, unk_i in enumerate(unknown_indices):
        if idx < len(unmatched_census):
            raza, color, sexo = unmatched_census[idx]
            birds[unk_i]["breed"] = raza
            birds[unk_i]["color"] = color
            birds[unk_i]["sex"] = sexo
            birds[unk_i]["distinguishing_features"] = (
                f"Asignada por descarte del censo ({raza} {color})"
            )
            birds[unk_i]["engine"] = "census_fallback"

    return birds


def merge_breed_yolo_into_gemini(breed_birds: list[dict], gemini_result: dict):
    """Si breed YOLO tiene alta confianza para un ave, sobrescribe la predicción de Gemini."""
    gemini_birds = gemini_result.get("birds", [])
    if not gemini_birds or not breed_birds:
        return

    for bb in breed_birds:
        if bb.get("engine") != "yolo_breed" or bb["confidence"] < 0.6:
            continue
        bb_bbox = bb.get("bbox", [])
        if len(bb_bbox) != 4:
            continue

        best_iou = 0
        best_gb = None
        for gb in gemini_birds:
            gb_bbox = gb.get("bbox", [])
            if len(gb_bbox) != 4:
                continue
            iou = bbox_iou(bb_bbox, gb_bbox)
            if iou > best_iou:
                best_iou = iou
                best_gb = gb

        if best_gb and best_iou > 0.3:
            if bb["confidence"] > best_gb.get("confidence", 0):
                best_gb["breed"] = bb["breed"]
                best_gb["color"] = bb["color"]
                best_gb["sex"] = bb["sex"]
                best_gb["confidence"] = bb["confidence"]
                best_gb["engine"] = "yolo_breed+gemini"


def bbox_iou(a: list[float], b: list[float]) -> float:
    """IoU entre dos bboxes normalizados [x1,y1,x2,y2]."""
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def validate_breeds_against_census(gallinero_id: str, gemini_result: dict):
    """Valida las razas identificadas por Gemini contra el censo de la cabaña."""
    try:
        from services.flock_census import get_all_breeds, get_canonical_breed_name
    except ImportError:
        return

    valid_breeds = get_all_breeds()
    if not valid_breeds:
        return

    for bird in gemini_result.get("birds", []):
        breed = bird.get("breed", "")
        if not breed or breed == "Desconocida":
            continue

        breed_low = breed.strip().lower()

        if breed_low in valid_breeds:
            continue

        partial = None
        for vb in valid_breeds:
            if vb in breed_low or breed_low in vb:
                partial = vb
                break

        if partial:
            continue

        match = None
        for vb in valid_breeds:
            if fuzzy_match(breed_low, vb):
                match = vb
                break

        if match:
            corrected = get_canonical_breed_name(match)
            logger.debug(f"Census correction: '{breed}' → '{corrected}'")
            bird["breed"] = corrected
        else:
            logger.info(f"[Census] Raza '{breed}' no existe en la cabaña — marcada como Desconocida")
            bird["breed"] = "Desconocida"
            bird["confidence"] = min(bird.get("confidence", 0.5), 0.3)
            bird["distinguishing_features"] = (
                bird.get("distinguishing_features", "") +
                f" (Gemini dijo: {breed}, no en censo)"
            )


# ── Normalization map: Gemini variants → (breed, color) census ──

_BREED_NORM_MAP: dict[str, tuple[str, str | None]] = {
    "vorwerk": ("Vorwerk", "dorado"),
    "vorwerk dorado": ("Vorwerk", "dorado"),
    "sussex": ("Sussex", None),
    "sussex silver": ("Sussex", "silver"),
    "sussex white": ("Sussex", "white"),
    "sussex armiñada": ("Sussex", "white"),
    "bresse": ("Bresse", "blanco"),
    "bresse blanco": ("Bresse", "blanco"),
    "marans": ("Marans", "negro cobrizo"),
    "marans negro cobrizo": ("Marans", "negro cobrizo"),
    "sulmtaler": ("Sulmtaler", "trigueño"),
    "sulmtaler trigueño": ("Sulmtaler", "trigueño"),
    "f1 (cruce)": ("F1 (cruce)", "variado"),
    "f1 (cruce) variado": ("F1 (cruce)", "variado"),
    "andaluza azul": ("Andaluza Azul", "azul"),
    "andaluza azul azul": ("Andaluza Azul", "azul"),
    "pita pinta": ("Pita Pinta", "pinta"),
    "pita pinta pinta": ("Pita Pinta", "pinta"),
    "araucana": ("Araucana", "trigueña"),
    "araucana trigueña": ("Araucana", "trigueña"),
    "araucana negra": ("Araucana", "negra"),
    "ameraucana": ("Ameraucana", "trigueño"),
}


def normalize_to_census(gallinero_id: str, breed: str, color: str, sex: str) -> tuple[str, str, str]:
    """Normaliza breed/color/sex al censo de la cabaña."""
    breed_key = breed.lower().strip()

    norm = _BREED_NORM_MAP.get(breed_key)
    if norm:
        canon_breed, canon_color = norm
        if canon_color is None:
            cl = color.lower()
            if "silver" in cl or "plat" in cl:
                canon_color = "silver"
            elif "white" in cl or "blanc" in cl or "armiñ" in cl:
                canon_color = "white"
            elif "negra" in cl or "negr" in cl:
                canon_color = "negra"
            else:
                canon_color = "silver"
        return canon_breed, canon_color, sex

    try:
        from services.flock_census import get_expected_breeds
    except ImportError:
        return breed, color, sex

    entries = get_expected_breeds(gallinero_id)
    if not entries:
        return breed, color, sex

    breed_low = breed.lower().strip()
    color_low = color.lower().strip()

    for e in entries:
        if e["raza"].lower() == breed_low and e["color"].lower() == color_low:
            return e["raza"], e["color"], sex

    for e in entries:
        if e["raza"].lower() == breed_low:
            ec = e["color"].lower()
            if ec in color_low or color_low in ec:
                return e["raza"], e["color"], sex

    for e in entries:
        census_breed = e["raza"].lower()
        if fuzzy_match(breed_low, census_breed):
            ec = e["color"].lower()
            if ec in color_low or color_low in ec or not color_low:
                return e["raza"], e["color"], sex

    return breed, color, sex


def fuzzy_match(a: str, b: str) -> bool:
    """Simple fuzzy match: True if strings differ by at most 2 chars."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 2:
        return False
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    diffs = sum(1 for i, c in enumerate(short) if i < len(long) and c != long[i])
    diffs += len(long) - len(short)
    return diffs <= 2
