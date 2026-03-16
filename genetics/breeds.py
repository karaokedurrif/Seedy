"""
Seedy Genetics — Base de datos de razas y parámetros genéticos.

Tres especies: avicultura (capones), porcino, vacuno.
Cada raza tiene: rasgos fenotípicos, heredabilidades, compatibilidad.
"""

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────
# Estructuras base
# ─────────────────────────────────────────────────────

@dataclass
class Trait:
    """Rasgo fenotípico de una raza."""
    name: str
    value: float           # Valor medio del rasgo
    unit: str = ""
    heritability: float = 0.3  # h²
    variance: float = 0.0     # Varianza fenotípica


@dataclass
class Breed:
    """Raza animal con perfil genético completo."""
    name: str
    species: str           # chicken, pig, cattle
    category: str          # meat, dual, maternal, terminal, etc.
    origin: str = ""
    traits: dict[str, Trait] = field(default_factory=dict)
    color_genotype: dict[str, str] = field(default_factory=dict)
    notes: str = ""


# ─────────────────────────────────────────────────────
# Heredabilidades comunes (h²)
# ─────────────────────────────────────────────────────

HERITABILITIES = {
    # ── Avicultura ──
    "chicken": {
        "body_weight_kg": 0.50,
        "carcass_yield_pct": 0.50,
        "growth_rate": 0.40,
        "eggs_per_year": 0.30,
        "docility": 0.30,
        "rusticity": 0.25,
        "feed_conversion": 0.35,
        "breast_width_cm": 0.45,
    },
    # ── Porcino ──
    "pig": {
        "daily_gain_g": 0.40,
        "feed_conversion": 0.35,
        "backfat_mm": 0.50,
        "lean_pct": 0.50,
        "litter_size": 0.10,
        "born_alive": 0.10,
        "weaned_per_litter": 0.08,
        "carcass_index": 0.45,
        "respiratory_resistance": 0.15,
        "thermal_adaptation": 0.20,
        "wean_estrus_interval_days": 0.15,
    },
    # ── Vacuno ──
    "cattle": {
        "weaning_weight_kg": 0.30,
        "yearling_weight_kg": 0.40,
        "daily_gain_g": 0.35,
        "calving_ease": 0.15,
        "fertility_pct": 0.10,
        "calving_interval_days": 0.10,
        "docility": 0.25,
        "heat_tolerance": 0.20,
        "parasite_resistance": 0.25,
        "longevity_years": 0.10,
        "calf_survival_pct": 0.05,
    },
}

# ─────────────────────────────────────────────────────
# Factores de heterosis por especie y rasgo
# ─────────────────────────────────────────────────────

HETEROSIS_FACTORS = {
    "chicken": {
        "body_weight_kg": 0.15,
        "carcass_yield_pct": 0.10,
        "growth_rate": 0.15,
        "feed_conversion": 0.12,
        "rusticity": 0.20,
        "docility": 0.10,
        "eggs_per_year": -0.05,  # Reducción típica en híbridos
        "disease_resistance": 0.20,
        "stress_tolerance": 0.18,
        "meat_quality": 0.10,
    },
    "pig": {
        "daily_gain_g": 0.10,
        "feed_conversion": 0.08,
        "litter_size": 0.08,
        "born_alive": 0.10,
        "weaned_per_litter": 0.12,
        "backfat_mm": 0.05,
        "lean_pct": 0.03,
        "respiratory_resistance": 0.15,
        "carcass_index": 0.05,
        "thermal_adaptation": 0.10,
    },
    "cattle": {
        "weaning_weight_kg": 0.08,
        "yearling_weight_kg": 0.05,
        "daily_gain_g": 0.10,
        "fertility_pct": 0.15,
        "calving_ease": 0.05,
        "calf_survival_pct": 0.10,
        "docility": 0.08,
        "heat_tolerance": 0.12,
        "parasite_resistance": 0.15,
        "longevity_years": 0.05,
    },
}


# ─────────────────────────────────────────────────────
# Umbrales de consanguinidad (Wright F)
# ─────────────────────────────────────────────────────

INBREEDING_THRESHOLDS = {
    "chicken": {"green": 0.10, "yellow": 0.20, "red": 0.30},
    "pig_white": {"green": 0.0625, "yellow": 0.125, "red": 0.25},
    "pig_iberico": {"green": 0.10, "yellow": 0.20, "red": 0.30},
    "cattle": {"green": 0.0625, "yellow": 0.125, "red": 0.25},
}


# ─────────────────────────────────────────────────────
# Base de datos de razas — AVICULTURA (capones)
# ─────────────────────────────────────────────────────

CHICKEN_BREEDS: dict[str, Breed] = {
    "bresse": Breed(
        name="Bresse", species="chicken", category="meat_premium",
        origin="Francia (AOP)", notes="Patas azules, carne fina, referencia capones",
        traits={
            "body_weight_kg": Trait("Peso corporal", 4.0, "kg", 0.50, 0.3),
            "carcass_yield_pct": Trait("Rendimiento canal", 70.0, "%", 0.50, 3.0),
            "growth_rate": Trait("Velocidad crecimiento", 75, "score", 0.40, 8.0),
            "docility": Trait("Docilidad", 80, "score", 0.30, 10.0),
            "rusticity": Trait("Rusticidad", 70, "score", 0.25, 12.0),
            "eggs_per_year": Trait("Huevos/año", 250, "uds", 0.30, 20.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.2, "ratio", 0.35, 0.3),
            "breast_width_cm": Trait("Ancho quilla", 9.5, "cm", 0.45, 0.8),
        },
        color_genotype={"E": "I/I", "Co": "co/co", "S": "S/S", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "orpington": Breed(
        name="Orpington", species="chicken", category="meat_dual",
        origin="Inglaterra", notes="Masa corporal alta, docilidad excepcional",
        traits={
            "body_weight_kg": Trait("Peso corporal", 4.5, "kg", 0.50, 0.4),
            "carcass_yield_pct": Trait("Rendimiento canal", 65.0, "%", 0.50, 3.5),
            "growth_rate": Trait("Velocidad crecimiento", 80, "score", 0.40, 8.0),
            "docility": Trait("Docilidad", 95, "score", 0.30, 5.0),
            "rusticity": Trait("Rusticidad", 85, "score", 0.25, 8.0),
            "eggs_per_year": Trait("Huevos/año", 180, "uds", 0.30, 15.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.5, "ratio", 0.35, 0.3),
            "breast_width_cm": Trait("Ancho quilla", 10.0, "cm", 0.45, 0.9),
        },
        color_genotype={"E": "E+/E+", "Co": "co/co", "S": "s+/s+", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "sussex": Breed(
        name="Sussex", species="chicken", category="meat_dual",
        origin="Inglaterra", notes="Canal equilibrada, patrón columbia",
        traits={
            "body_weight_kg": Trait("Peso corporal", 4.2, "kg", 0.50, 0.3),
            "carcass_yield_pct": Trait("Rendimiento canal", 68.0, "%", 0.50, 3.0),
            "growth_rate": Trait("Velocidad crecimiento", 78, "score", 0.40, 7.0),
            "docility": Trait("Docilidad", 85, "score", 0.30, 8.0),
            "rusticity": Trait("Rusticidad", 80, "score", 0.25, 10.0),
            "eggs_per_year": Trait("Huevos/año", 220, "uds", 0.30, 18.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.3, "ratio", 0.35, 0.25),
            "breast_width_cm": Trait("Ancho quilla", 9.8, "cm", 0.45, 0.7),
        },
        color_genotype={"E": "E+/E+", "Co": "Co/Co", "S": "S/S", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "brahma": Breed(
        name="Brahma", species="chicken", category="meat_heavy",
        origin="Asia (India/China)", notes="Peso extremo, patas emplumadas, genéticamente distante",
        traits={
            "body_weight_kg": Trait("Peso corporal", 5.5, "kg", 0.50, 0.5),
            "carcass_yield_pct": Trait("Rendimiento canal", 62.0, "%", 0.50, 4.0),
            "growth_rate": Trait("Velocidad crecimiento", 60, "score", 0.40, 10.0),
            "docility": Trait("Docilidad", 90, "score", 0.30, 6.0),
            "rusticity": Trait("Rusticidad", 95, "score", 0.25, 5.0),
            "eggs_per_year": Trait("Huevos/año", 140, "uds", 0.30, 12.0),
            "feed_conversion": Trait("Conversión alimenticia", 4.0, "ratio", 0.35, 0.4),
            "breast_width_cm": Trait("Ancho quilla", 10.5, "cm", 0.45, 1.0),
        },
        color_genotype={"E": "eWh/eWh", "Co": "Co/Co", "S": "s+/s+", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "cornish": Breed(
        name="Cornish", species="chicken", category="meat_terminal",
        origin="Inglaterra", notes="Musculatura extrema, base broiler industrial",
        traits={
            "body_weight_kg": Trait("Peso corporal", 4.8, "kg", 0.50, 0.4),
            "carcass_yield_pct": Trait("Rendimiento canal", 75.0, "%", 0.50, 2.5),
            "growth_rate": Trait("Velocidad crecimiento", 90, "score", 0.40, 6.0),
            "docility": Trait("Docilidad", 60, "score", 0.30, 12.0),
            "rusticity": Trait("Rusticidad", 55, "score", 0.25, 15.0),
            "eggs_per_year": Trait("Huevos/año", 120, "uds", 0.30, 10.0),
            "feed_conversion": Trait("Conversión alimenticia", 2.8, "ratio", 0.35, 0.2),
            "breast_width_cm": Trait("Ancho quilla", 11.0, "cm", 0.45, 0.8),
        },
        color_genotype={"E": "I/I", "Co": "co/co", "S": "S/S", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "cochin": Breed(
        name="Cochin", species="chicken", category="meat_heavy",
        origin="China", notes="Muy pesada, plumaje abundante, patas emplumadas",
        traits={
            "body_weight_kg": Trait("Peso corporal", 5.0, "kg", 0.50, 0.5),
            "carcass_yield_pct": Trait("Rendimiento canal", 60.0, "%", 0.50, 4.0),
            "growth_rate": Trait("Velocidad crecimiento", 55, "score", 0.40, 10.0),
            "docility": Trait("Docilidad", 92, "score", 0.30, 5.0),
            "rusticity": Trait("Rusticidad", 88, "score", 0.25, 7.0),
            "eggs_per_year": Trait("Huevos/año", 160, "uds", 0.30, 13.0),
            "feed_conversion": Trait("Conversión alimenticia", 4.2, "ratio", 0.35, 0.4),
            "breast_width_cm": Trait("Ancho quilla", 10.0, "cm", 0.45, 0.9),
        },
        color_genotype={"E": "E+/E+", "Co": "co/co", "S": "s+/s+", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "plymouth_rock": Breed(
        name="Plymouth Rock Barrada", species="chicken", category="meat_dual",
        origin="EEUU", notes="Barrado ligado al sexo, buena ponedora + carne",
        traits={
            "body_weight_kg": Trait("Peso corporal", 4.0, "kg", 0.50, 0.3),
            "carcass_yield_pct": Trait("Rendimiento canal", 66.0, "%", 0.50, 3.0),
            "growth_rate": Trait("Velocidad crecimiento", 75, "score", 0.40, 8.0),
            "docility": Trait("Docilidad", 82, "score", 0.30, 8.0),
            "rusticity": Trait("Rusticidad", 85, "score", 0.25, 8.0),
            "eggs_per_year": Trait("Huevos/año", 200, "uds", 0.30, 16.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.4, "ratio", 0.35, 0.3),
            "breast_width_cm": Trait("Ancho quilla", 9.5, "cm", 0.45, 0.7),
        },
        color_genotype={"E": "E+/E+", "Co": "co/co", "S": "B/B", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "sulmtaler": Breed(
        name="Sulmtaler", species="chicken", category="meat_premium",
        origin="Austria", notes="Cresta nuez, carne premium para capón centroeuropeo",
        traits={
            "body_weight_kg": Trait("Peso corporal", 3.8, "kg", 0.50, 0.3),
            "carcass_yield_pct": Trait("Rendimiento canal", 68.0, "%", 0.50, 3.0),
            "growth_rate": Trait("Velocidad crecimiento", 70, "score", 0.40, 8.0),
            "docility": Trait("Docilidad", 78, "score", 0.30, 9.0),
            "rusticity": Trait("Rusticidad", 82, "score", 0.25, 9.0),
            "eggs_per_year": Trait("Huevos/año", 180, "uds", 0.30, 15.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.5, "ratio", 0.35, 0.3),
            "breast_width_cm": Trait("Ancho quilla", 9.2, "cm", 0.45, 0.7),
        },
        color_genotype={"E": "eWh/eWh", "Co": "co/co", "S": "s+/s+", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "vorwerk": Breed(
        name="Vorwerk", species="chicken", category="dual",
        origin="Alemania", notes="Patrón columbia dorado, rara y elegante",
        traits={
            "body_weight_kg": Trait("Peso corporal", 3.2, "kg", 0.50, 0.3),
            "carcass_yield_pct": Trait("Rendimiento canal", 65.0, "%", 0.50, 3.0),
            "growth_rate": Trait("Velocidad crecimiento", 72, "score", 0.40, 8.0),
            "docility": Trait("Docilidad", 75, "score", 0.30, 10.0),
            "rusticity": Trait("Rusticidad", 85, "score", 0.25, 8.0),
            "eggs_per_year": Trait("Huevos/año", 170, "uds", 0.30, 15.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.6, "ratio", 0.35, 0.3),
            "breast_width_cm": Trait("Ancho quilla", 8.5, "cm", 0.45, 0.6),
        },
        color_genotype={"E": "E+/E+", "Co": "Co/Co", "S": "s+/s+", "Ml": "ml+/ml+", "Bl": "bl+/bl+"},
    ),
    "andaluza": Breed(
        name="Andaluza Azul", species="chicken", category="dual",
        origin="España (Andalucía)", notes="Dominancia incompleta Blue → 25% splash, 50% azul, 25% negro",
        traits={
            "body_weight_kg": Trait("Peso corporal", 3.5, "kg", 0.50, 0.3),
            "carcass_yield_pct": Trait("Rendimiento canal", 64.0, "%", 0.50, 3.5),
            "growth_rate": Trait("Velocidad crecimiento", 68, "score", 0.40, 9.0),
            "docility": Trait("Docilidad", 70, "score", 0.30, 10.0),
            "rusticity": Trait("Rusticidad", 90, "score", 0.25, 6.0),
            "eggs_per_year": Trait("Huevos/año", 160, "uds", 0.30, 14.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.7, "ratio", 0.35, 0.35),
            "breast_width_cm": Trait("Ancho quilla", 8.8, "cm", 0.45, 0.7),
        },
        color_genotype={"E": "E+/E+", "Co": "co/co", "S": "s+/s+", "Ml": "Ml/Ml", "Bl": "Bl/bl+"},
    ),
    "castellana": Breed(
        name="Castellana Negra", species="chicken", category="dual",
        origin="España (Castilla)", notes="Puro negro, cara blanca, rusticidad extrema",
        traits={
            "body_weight_kg": Trait("Peso corporal", 3.0, "kg", 0.50, 0.25),
            "carcass_yield_pct": Trait("Rendimiento canal", 62.0, "%", 0.50, 3.5),
            "growth_rate": Trait("Velocidad crecimiento", 60, "score", 0.40, 9.0),
            "docility": Trait("Docilidad", 65, "score", 0.30, 12.0),
            "rusticity": Trait("Rusticidad", 95, "score", 0.25, 4.0),
            "eggs_per_year": Trait("Huevos/año", 200, "uds", 0.30, 17.0),
            "feed_conversion": Trait("Conversión alimenticia", 3.8, "ratio", 0.35, 0.35),
            "breast_width_cm": Trait("Ancho quilla", 8.5, "cm", 0.45, 0.6),
        },
        color_genotype={"E": "E+/E+", "Co": "co/co", "S": "s+/s+", "Ml": "Ml/Ml", "Bl": "bl+/bl+"},
    ),
}


# ─────────────────────────────────────────────────────
# Base de datos de razas — PORCINO
# ─────────────────────────────────────────────────────

PIG_BREEDS: dict[str, Breed] = {
    "large_white": Breed(
        name="Large White", species="pig", category="maternal",
        origin="Inglaterra",
        traits={
            "daily_gain_g": Trait("GMD", 850, "g/d", 0.40, 60),
            "feed_conversion": Trait("FCR", 2.5, "ratio", 0.35, 0.15),
            "backfat_mm": Trait("Grasa dorsal", 12.0, "mm", 0.50, 2.0),
            "lean_pct": Trait("% magro", 60.0, "%", 0.50, 2.5),
            "litter_size": Trait("Tamaño camada", 13.5, "lechones", 0.10, 2.0),
            "born_alive": Trait("Nacidos vivos", 12.5, "lechones", 0.10, 2.0),
            "weaned_per_litter": Trait("Destetados/cam", 11.0, "lechones", 0.08, 1.5),
            "carcass_index": Trait("Índice canal", 78, "score", 0.45, 5.0),
            "respiratory_resistance": Trait("Resist. resp.", 70, "score", 0.15, 12.0),
        },
    ),
    "landrace": Breed(
        name="Landrace", species="pig", category="maternal",
        origin="Dinamarca",
        traits={
            "daily_gain_g": Trait("GMD", 820, "g/d", 0.40, 55),
            "feed_conversion": Trait("FCR", 2.6, "ratio", 0.35, 0.15),
            "backfat_mm": Trait("Grasa dorsal", 13.0, "mm", 0.50, 2.0),
            "lean_pct": Trait("% magro", 58.0, "%", 0.50, 2.5),
            "litter_size": Trait("Tamaño camada", 14.0, "lechones", 0.10, 2.2),
            "born_alive": Trait("Nacidos vivos", 13.0, "lechones", 0.10, 2.2),
            "weaned_per_litter": Trait("Destetados/cam", 11.5, "lechones", 0.08, 1.6),
            "carcass_index": Trait("Índice canal", 76, "score", 0.45, 5.0),
            "respiratory_resistance": Trait("Resist. resp.", 65, "score", 0.15, 13.0),
        },
    ),
    "duroc": Breed(
        name="Duroc", species="pig", category="terminal",
        origin="EEUU",
        traits={
            "daily_gain_g": Trait("GMD", 900, "g/d", 0.40, 65),
            "feed_conversion": Trait("FCR", 2.4, "ratio", 0.35, 0.12),
            "backfat_mm": Trait("Grasa dorsal", 15.0, "mm", 0.50, 2.5),
            "lean_pct": Trait("% magro", 55.0, "%", 0.50, 3.0),
            "litter_size": Trait("Tamaño camada", 10.5, "lechones", 0.10, 1.8),
            "born_alive": Trait("Nacidos vivos", 9.5, "lechones", 0.10, 1.8),
            "weaned_per_litter": Trait("Destetados/cam", 8.5, "lechones", 0.08, 1.4),
            "carcass_index": Trait("Índice canal", 82, "score", 0.45, 4.0),
            "respiratory_resistance": Trait("Resist. resp.", 80, "score", 0.15, 10.0),
        },
    ),
    "pietrain": Breed(
        name="Pietrain", species="pig", category="terminal",
        origin="Bélgica", notes="Máximo magro, sensible al estrés (gen halotano)",
        traits={
            "daily_gain_g": Trait("GMD", 780, "g/d", 0.40, 50),
            "feed_conversion": Trait("FCR", 2.3, "ratio", 0.35, 0.10),
            "backfat_mm": Trait("Grasa dorsal", 8.0, "mm", 0.50, 1.5),
            "lean_pct": Trait("% magro", 66.0, "%", 0.50, 2.0),
            "litter_size": Trait("Tamaño camada", 10.0, "lechones", 0.10, 1.5),
            "born_alive": Trait("Nacidos vivos", 9.0, "lechones", 0.10, 1.5),
            "weaned_per_litter": Trait("Destetados/cam", 8.0, "lechones", 0.08, 1.3),
            "carcass_index": Trait("Índice canal", 88, "score", 0.45, 3.0),
            "respiratory_resistance": Trait("Resist. resp.", 55, "score", 0.15, 15.0),
        },
    ),
    "iberico": Breed(
        name="Ibérico", species="pig", category="quality",
        origin="España", notes="Infiltración grasa, bellota, jamón premium",
        traits={
            "daily_gain_g": Trait("GMD", 550, "g/d", 0.40, 50),
            "feed_conversion": Trait("FCR", 3.8, "ratio", 0.35, 0.30),
            "backfat_mm": Trait("Grasa dorsal", 35.0, "mm", 0.50, 5.0),
            "lean_pct": Trait("% magro", 38.0, "%", 0.50, 4.0),
            "litter_size": Trait("Tamaño camada", 8.0, "lechones", 0.10, 1.5),
            "born_alive": Trait("Nacidos vivos", 7.0, "lechones", 0.10, 1.5),
            "weaned_per_litter": Trait("Destetados/cam", 6.5, "lechones", 0.08, 1.2),
            "carcass_index": Trait("Índice canal", 65, "score", 0.45, 5.0),
            "respiratory_resistance": Trait("Resist. resp.", 85, "score", 0.15, 8.0),
        },
    ),
}


# ─────────────────────────────────────────────────────
# Base de datos de razas — VACUNO
# ─────────────────────────────────────────────────────

CATTLE_BREEDS: dict[str, Breed] = {
    "avilena": Breed(
        name="Avileña-Negra Ibérica", species="cattle", category="autochthonous",
        origin="España (Ávila/Extremadura)", notes="Extrema rusticidad, dehesa",
        traits={
            "weaning_weight_kg": Trait("Peso destete", 200, "kg", 0.30, 20),
            "yearling_weight_kg": Trait("Peso al año", 340, "kg", 0.40, 30),
            "daily_gain_g": Trait("GMD", 850, "g/d", 0.35, 100),
            "calving_ease": Trait("Facilidad parto", 85, "score", 0.15, 10),
            "fertility_pct": Trait("Fertilidad", 90, "%", 0.10, 8),
            "calving_interval_days": Trait("Intervalo partos", 395, "días", 0.10, 30),
            "docility": Trait("Docilidad", 70, "score", 0.25, 12),
            "heat_tolerance": Trait("Tolerancia calor", 90, "score", 0.20, 6),
            "parasite_resistance": Trait("Resist. parásitos", 85, "score", 0.25, 8),
        },
    ),
    "retinta": Breed(
        name="Retinta", species="cattle", category="autochthonous",
        origin="España (Extremadura/Andalucía)", notes="Adaptada a dehesa, capa retinta",
        traits={
            "weaning_weight_kg": Trait("Peso destete", 210, "kg", 0.30, 22),
            "yearling_weight_kg": Trait("Peso al año", 360, "kg", 0.40, 32),
            "daily_gain_g": Trait("GMD", 900, "g/d", 0.35, 110),
            "calving_ease": Trait("Facilidad parto", 82, "score", 0.15, 10),
            "fertility_pct": Trait("Fertilidad", 88, "%", 0.10, 8),
            "calving_interval_days": Trait("Intervalo partos", 400, "días", 0.10, 32),
            "docility": Trait("Docilidad", 68, "score", 0.25, 13),
            "heat_tolerance": Trait("Tolerancia calor", 92, "score", 0.20, 5),
            "parasite_resistance": Trait("Resist. parásitos", 88, "score", 0.25, 7),
        },
    ),
    "rubia_gallega": Breed(
        name="Rubia Gallega", species="cattle", category="autochthonous",
        origin="España (Galicia)", notes="Máxima calidad de carne, veteado excepcional",
        traits={
            "weaning_weight_kg": Trait("Peso destete", 240, "kg", 0.30, 25),
            "yearling_weight_kg": Trait("Peso al año", 420, "kg", 0.40, 35),
            "daily_gain_g": Trait("GMD", 1050, "g/d", 0.35, 120),
            "calving_ease": Trait("Facilidad parto", 75, "score", 0.15, 12),
            "fertility_pct": Trait("Fertilidad", 82, "%", 0.10, 9),
            "calving_interval_days": Trait("Intervalo partos", 410, "días", 0.10, 35),
            "docility": Trait("Docilidad", 80, "score", 0.25, 10),
            "heat_tolerance": Trait("Tolerancia calor", 65, "score", 0.20, 10),
            "parasite_resistance": Trait("Resist. parásitos", 70, "score", 0.25, 10),
        },
    ),
    "charolais": Breed(
        name="Charolais", species="cattle", category="terminal",
        origin="Francia", notes="Masa muscular, cruce terminal clásico",
        traits={
            "weaning_weight_kg": Trait("Peso destete", 280, "kg", 0.30, 28),
            "yearling_weight_kg": Trait("Peso al año", 500, "kg", 0.40, 40),
            "daily_gain_g": Trait("GMD", 1200, "g/d", 0.35, 130),
            "calving_ease": Trait("Facilidad parto", 60, "score", 0.15, 14),
            "fertility_pct": Trait("Fertilidad", 78, "%", 0.10, 10),
            "calving_interval_days": Trait("Intervalo partos", 420, "días", 0.10, 35),
            "docility": Trait("Docilidad", 65, "score", 0.25, 14),
            "heat_tolerance": Trait("Tolerancia calor", 55, "score", 0.20, 12),
            "parasite_resistance": Trait("Resist. parásitos", 60, "score", 0.25, 12),
        },
    ),
    "angus": Breed(
        name="Angus", species="cattle", category="terminal",
        origin="Escocia", notes="Facilidad parto, calidad canal, sin cuernos",
        traits={
            "weaning_weight_kg": Trait("Peso destete", 250, "kg", 0.30, 25),
            "yearling_weight_kg": Trait("Peso al año", 440, "kg", 0.40, 35),
            "daily_gain_g": Trait("GMD", 1100, "g/d", 0.35, 120),
            "calving_ease": Trait("Facilidad parto", 88, "score", 0.15, 8),
            "fertility_pct": Trait("Fertilidad", 85, "%", 0.10, 8),
            "calving_interval_days": Trait("Intervalo partos", 380, "días", 0.10, 28),
            "docility": Trait("Docilidad", 78, "score", 0.25, 10),
            "heat_tolerance": Trait("Tolerancia calor", 65, "score", 0.20, 10),
            "parasite_resistance": Trait("Resist. parásitos", 65, "score", 0.25, 10),
        },
    ),
    "limousin": Breed(
        name="Limousin", species="cattle", category="terminal",
        origin="Francia", notes="Rendimiento canal excepcional, magro",
        traits={
            "weaning_weight_kg": Trait("Peso destete", 265, "kg", 0.30, 26),
            "yearling_weight_kg": Trait("Peso al año", 470, "kg", 0.40, 38),
            "daily_gain_g": Trait("GMD", 1150, "g/d", 0.35, 125),
            "calving_ease": Trait("Facilidad parto", 72, "score", 0.15, 12),
            "fertility_pct": Trait("Fertilidad", 80, "%", 0.10, 9),
            "calving_interval_days": Trait("Intervalo partos", 400, "días", 0.10, 32),
            "docility": Trait("Docilidad", 72, "score", 0.25, 12),
            "heat_tolerance": Trait("Tolerancia calor", 60, "score", 0.20, 11),
            "parasite_resistance": Trait("Resist. parásitos", 62, "score", 0.25, 11),
        },
    ),
}


# ─────────────────────────────────────────────────────
# Acceso unificado
# ─────────────────────────────────────────────────────

ALL_BREEDS: dict[str, dict[str, Breed]] = {
    "chicken": CHICKEN_BREEDS,
    "pig": PIG_BREEDS,
    "cattle": CATTLE_BREEDS,
}


def get_breed(species: str, breed_id: str) -> Breed | None:
    """Obtiene una raza por especie e ID."""
    return ALL_BREEDS.get(species, {}).get(breed_id)


def list_breeds(species: str | None = None) -> list[dict]:
    """Lista razas disponibles; opcionalmente filtradas por especie."""
    result = []
    for sp, breeds in ALL_BREEDS.items():
        if species and sp != species:
            continue
        for bid, breed in breeds.items():
            result.append({
                "id": bid,
                "name": breed.name,
                "species": breed.species,
                "category": breed.category,
                "origin": breed.origin,
                "n_traits": len(breed.traits),
            })
    return result
