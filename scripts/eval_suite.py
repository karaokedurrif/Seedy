#!/usr/bin/env python3
"""
Seedy Eval Suite — Evaluación automatizada de calidad del pipeline.

Ejecuta N preguntas gold contra el pipeline completo y evalúa:
- Responde o falla (timeout/error)
- Factualidad: ¿menciona los hechos clave esperados?
- No-confusión: ¿no menciona elementos prohibidos?
- Formato: ¿texto plano sin markdown?
- Latencia

Uso:
    python3 scripts/eval_suite.py                    # Todas las preguntas
    python3 scripts/eval_suite.py --domain AVICULTURA  # Solo un dominio
    python3 scripts/eval_suite.py --json              # Salida JSON
"""

import argparse
import json
import re
import sys
import time
import httpx

# ── Configuración ──
BACKEND_URL = "http://localhost:8000"
TIMEOUT = 180  # segundos

# ── Preguntas gold: (dominio, pregunta, hechos_esperados, prohibidos) ──
# hechos_esperados: al menos 2 de estos deben aparecer en la respuesta
# prohibidos: si alguno aparece, se marca como fallo de confusión

GOLD_QUESTIONS = [
    # ── AVICULTURA (10) ──
    {
        "domain": "AVICULTURA",
        "question": "¿Qué razas avícolas son mejores para producir capones gourmet en España?",
        "expected_facts": ["Bresse", "Sulmtaler", "Malines", "Faverolles", "Sussex", "Dorking", "Orpington"],
        "min_expected": 3,
        "prohibited": ["Retinta", "Avileña", "Ibérico", "Duroc", "Landrace"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Cuál es el proceso de caponización quirúrgica y a qué edad se realiza?",
        "expected_facts": ["6", "8", "semanas", "quirúrgica", "testículo", "castración"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué es el Capon Score y qué parámetros incluye?",
        "expected_facts": ["canal", "peso", "docilidad", "crecimiento", "rusticidad", "35", "25", "15"],
        "min_expected": 3,
        "prohibited": [],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué cruce F1 recomiendas para un capón gourmet con crecimiento lento?",
        "expected_facts": ["F1", "cruce", "heterosis", "crecimiento lento", "capón"],
        "min_expected": 2,
        "prohibited": ["Duroc", "Landrace", "Large White", "vaca", "ternera"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué es la normativa Label Rouge para aves?",
        "expected_facts": ["Label Rouge", "Francia", "extensivo", "libre", "calidad"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué características tiene la raza Pita Pinta Asturiana?",
        "expected_facts": ["Pita Pinta", "Asturias", "autóctona"],
        "min_expected": 2,
        "prohibited": ["cerdo", "porcino", "bovino"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué diferencia hay entre un capón y una pularda?",
        "expected_facts": ["capón", "pularda", "macho", "hembra", "castr"],
        "min_expected": 3,
        "prohibited": [],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué razas de gallinas autóctonas españolas existen según el catálogo MAPA?",
        "expected_facts": ["Pita Pinta", "Castellana", "Prat", "Euskal", "Mos", "Empordanesa",
                           "Penedesenca", "Utrerana", "Sobrarbe", "Menorquina", "autóctona"],
        "min_expected": 2,
        "prohibited": ["Duroc", "Ibérico", "Retinta"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué es la alimentación con pâtée en épinettes para capones?",
        "expected_facts": ["pâtée", "épinette", "engorde", "láctea", "capón"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Cuánto pesa un capón de raza Malines adulto y cuánto tarda en crecer?",
        "expected_facts": ["Malines", "kg", "peso", "meses"],
        "min_expected": 2,
        "prohibited": ["cerdo", "ternera"],
    },

    # ── GENETICA (8) ──
    {
        "domain": "GENETICS",
        "question": "¿Qué es la consanguinidad de Wright y cómo se calcula?",
        "expected_facts": ["consanguinidad", "Wright", "coeficiente", "F", "pedigree", "ancestro"],
        "min_expected": 3,
        "prohibited": [],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué son los EPDs en genética animal?",
        "expected_facts": ["EPD", "esperada", "progenie", "diferencia", "BLUP", "valor"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué razas porcinas autóctonas hay en España?",
        "expected_facts": ["Ibérico", "Celta", "Chato Murciano", "Porc Negre"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "Bresse", "Malines"],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué es la heterosis y cómo se aprovecha en ganadería?",
        "expected_facts": ["heterosis", "vigor", "híbrido", "cruce", "complementar"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué diferencia hay entre línea paterna y línea materna en porcino?",
        "expected_facts": ["paterna", "materna", "crecimiento", "conformación", "prolificidad"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "aviar"],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué razas bovinas autóctonas españolas conoces?",
        "expected_facts": ["Retinta", "Avileña", "Rubia Gallega", "Morucha", "Sayaguesa"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "Bresse", "cerdo"],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué es la selección genómica y qué ventajas tiene sobre BLUP?",
        "expected_facts": ["genómica", "SNP", "marcador", "precisión", "generación"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué paneles genómicos se usan en porcino (Neogen, Zoetis)?",
        "expected_facts": ["panel", "genóm", "SNP", "Neogen", "Zoetis", "GGP"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo"],
    },

    # ── NORMATIVA (7) ──
    {
        "domain": "NORMATIVA",
        "question": "¿Cuáles son los 11 planes del SIGE según el RD 306/2020?",
        "expected_facts": ["SIGE", "306/2020", "sanitario", "bioseguridad", "limpieza", "purines", "bienestar"],
        "min_expected": 3,
        "prohibited": [],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué superficies mínimas establece el RD 1135/2002 para cerdos de engorde?",
        "expected_facts": ["1135/2002", "m²", "superficie", "cerdo", "engorde", "bienestar"],
        "min_expected": 3,
        "prohibited": [],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué es ECOGAN y para qué sirve?",
        "expected_facts": ["ECOGAN", "emisiones", "ambiental", "ganadería"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué requisitos tiene una granja AAI (Autorización Ambiental Integrada)?",
        "expected_facts": ["AAI", "ambiental", "IPPC", "MTD", "emisiones"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué normativa regula la trazabilidad en ganadería española?",
        "expected_facts": ["trazabilidad", "identificación", "registro", "REGA", "explotación"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué es el plan de gestión de purines obligatorio?",
        "expected_facts": ["purines", "gestión", "plan", "nitrógeno", "aplicación"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué normativa europea aplica al bienestar de las gallinas ponedoras?",
        "expected_facts": ["Directiva", "gallina", "ponedora", "jaula", "bienestar"],
        "min_expected": 2,
        "prohibited": [],  # NORMATIVA corpus es mayormente porcino; no penalizar por mencionar contexto real
    },

    # ── IOT (7) ──
    {
        "domain": "IOT",
        "question": "¿Qué capas de sensores tiene el sistema PorciData?",
        "expected_facts": ["capa", "sensor", "PorciData", "temperatura", "humedad"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "IOT",
        "question": "¿Qué sensores recomiendas para medir amoniaco en una nave porcina?",
        "expected_facts": ["amoniaco", "NH3", "sensor", "ppm", "concentración"],
        "min_expected": 2,
        "prohibited": ["gallina", "avícola"],
    },
    {
        "domain": "IOT",
        "question": "¿Qué protocolo usa PorciData para comunicar sensores?",
        "expected_facts": ["MQTT", "LoRa", "ESP32", "neofarm"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "IOT",
        "question": "¿Cuánto cuesta aproximadamente instalar PorciData en una nave?",
        "expected_facts": ["EUR", "€", "coste", "nave", "1420", "1.420"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "IOT",
        "question": "¿Qué es InfluxDB y cómo se usa en ganadería de precisión?",
        "expected_facts": ["InfluxDB", "series temporales", "datos", "sensor", "telemetría"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "IOT",
        "question": "¿Qué ventajas tiene LoRa frente a WiFi para sensores en granja?",
        "expected_facts": ["LoRa", "alcance", "consumo", "batería", "cobertura"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "IOT",
        "question": "¿Qué sensores Dragino y Renke se usan en PorciData?",
        "expected_facts": ["Dragino", "Renke", "sensor", "LoRa"],
        "min_expected": 2,
        "prohibited": [],
    },

    # ── NUTRITION (5) ──
    {
        "domain": "NUTRITION",
        "question": "¿Qué es el butirato sódico y para qué se usa en nutrición porcina?",
        "expected_facts": ["butirato", "intestinal", "salud", "aditivo", "ácido"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo"],
    },
    {
        "domain": "NUTRITION",
        "question": "¿Qué son las enzimas NSP en alimentación porcina?",
        "expected_facts": ["NSP", "enzima", "polisacárido", "digestibilidad", "fibra"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NUTRITION",
        "question": "¿Cómo funciona la formulación de piensos por programación lineal?",
        "expected_facts": ["lineal", "coste", "requerimiento", "ingrediente", "optimización"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NUTRITION",
        "question": "¿Qué lonjas de referencia se usan para precios del cerdo en España?",
        "expected_facts": ["Mercolleida", "Segovia", "Ebro", "lonja", "precio"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "NUTRITION",
        "question": "¿Qué requerimientos proteicos tiene un cerdo de engorde según NRC?",
        "expected_facts": ["proteína", "NRC", "lisina", "aminoácido", "engorde", "%"],
        "min_expected": 2,
        "prohibited": [],
    },

    # ── DIGITAL TWINS (5) ──
    {
        "domain": "TWIN",
        "question": "¿Qué es un Digital Twin en ganadería y cómo funciona?",
        "expected_facts": ["gemelo", "digital", "modelo", "sensor", "simulación", "real"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "TWIN",
        "question": "¿Qué es GeoTwin y cómo usa Cesium 3D?",
        "expected_facts": ["GeoTwin", "Cesium", "3D", "geoespacial", "PNOA"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "TWIN",
        "question": "¿Qué capas tiene el Twin Porcino de NeoFarm?",
        "expected_facts": ["capa", "IoT", "World Model", "nave", "lote"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "TWIN",
        "question": "¿Qué es NDVI y cómo se aplica a vacuno extensivo?",
        "expected_facts": ["NDVI", "vegetación", "pasto", "satélite", "extensivo"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "TWIN",
        "question": "¿Qué sistema de coordenadas usa NeoFarm para España?",
        "expected_facts": ["EPSG", "25830", "UTM", "30", "coordenadas"],
        "min_expected": 2,
        "prohibited": [],
    },

    # ── CONFUSIÓN DE ESPECIE (tests negativos) (8) ──
    {
        "domain": "GENETICS",
        "question": "¿Qué razas de cerdo ibérico existen?",
        "expected_facts": ["Ibérico", "Retinto", "Entrepelado", "Torbiscal", "Lampiño", "cerdo"],
        "min_expected": 2,
        "prohibited": ["Bresse", "Malines", "Sussex", "gallina", "pollo", "capón"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué raza de gallina es la Mos?",
        "expected_facts": ["Mos", "Galicia", "gallina", "autóctona", "aviar"],
        "min_expected": 2,
        "prohibited": ["cerdo", "vaca", "bovino", "porcino"],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué es la raza bovina Sayaguesa?",
        "expected_facts": ["Sayaguesa", "bovino", "Zamora", "autóctona"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "cerdo", "porcino"],
    },
    {
        "domain": "IOT",
        "question": "¿Qué sensores IoT necesito para una nave de cerdos?",
        "expected_facts": ["sensor", "temperatura", "humedad", "cerdo", "nave", "porcin"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "avícola"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Cuánto pesa un gallo Brahma adulto?",
        "expected_facts": ["Brahma", "kg", "peso", "gallo"],
        "min_expected": 2,
        "prohibited": ["cerdo", "vaca", "toro"],
    },
    {
        "domain": "GENETICS",
        "question": "¿Para qué tipo de explotación se usa la raza Retinta?",
        "expected_facts": ["Retinta", "bovino", "extensivo", "carne", "dehesa"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "cerdo", "avícola"],
    },
    {
        "domain": "NORMATIVA",
        "question": "¿Qué normativa aplica a granjas de gallinas ponedoras en jaula?",
        "expected_facts": ["jaula", "gallina", "ponedora", "Directiva", "bienestar"],
        "min_expected": 2,
        "prohibited": [],  # NORMATIVA corpus es mayormente porcino; no penalizar por contexto real
    },
    {
        "domain": "NUTRITION",
        "question": "¿Qué pienso necesita un lechón de 10 kg?",
        "expected_facts": ["lechón", "proteína", "kg", "pienso", "starter"],
        "min_expected": 2,
        "prohibited": ["gallina", "pollo", "pollito"],
    },

    # ── IDENTIDAD NEOFARM (4) ──
    {
        "domain": "IDENTITY",
        "question": "¿Qué es NeoFarm?",
        "expected_facts": ["agrotech", "ganadería", "PorciData", "VacasData", "IoT", "neofarm"],
        "min_expected": 3,
        "prohibited": ["cannabis", "CBD", "marihuana", "semillas recreativas", "blockchain", "Afrotech"],
    },
    {
        "domain": "IDENTITY",
        "question": "¿Quién eres tú?",
        "expected_facts": ["Seedy", "NeoFarm", "asistente", "ganadería", "agrotech"],
        "min_expected": 2,
        "prohibited": ["cannabis", "CBD", "Afrotech", "blockchain"],
    },
    {
        "domain": "IDENTITY",
        "question": "¿NeoFarm vende cannabis?",
        "expected_facts": ["no", "ganadería", "agrotech", "PorciData"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "IDENTITY",
        "question": "¿Qué tiene que ver hub.ovosfera.com con NeoFarm?",
        "expected_facts": ["Ovosfera", "NeoFarm", "ganadería", "datos", "plataforma"],
        "min_expected": 2,
        "prohibited": ["cannabis", "CBD"],
    },

    # ── CACHENA / VACUNO EXTENSIVO (5) ──
    {
        "domain": "VACUNO",
        "question": "¿De dónde es originaria la raza Cachena?",
        "expected_facts": ["Portugal", "Tras-os-Montes", "bovina", "bovino", "portuguesa"],
        "min_expected": 2,
        "prohibited": ["española", "España como origen", "Castilla"],
    },
    {
        "domain": "VACUNO",
        "question": "¿La raza Cachena es ovina o bovina?",
        "expected_facts": ["bovina", "bovino", "vacuno", "vaca"],
        "min_expected": 1,
        "prohibited": ["ovina", "oveja", "cabra"],
    },
    {
        "domain": "VACUNO",
        "question": "¿Qué razas de vacuno recomiendas para la Sierra de Guadarrama?",
        "expected_facts": ["Avileña", "extensivo", "montaña", "rústic"],
        "min_expected": 2,
        "prohibited": ["Holstein", "Jersey", "Frisona"],
    },
    {
        "domain": "VACUNO",
        "question": "¿La Holstein es buena para extensivo de montaña?",
        "expected_facts": ["no", "lecher", "intensiv", "suplementa"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "VACUNO",
        "question": "¿Qué diferencia hay entre Limusín y Charolés?",
        "expected_facts": ["Limusín", "Charolés", "parto", "conformación", "cruce"],
        "min_expected": 3,
        "prohibited": ["gallina", "pollo", "cerdo"],
    },

    # ── GRASS-FED (2) ──
    {
        "domain": "VACUNO",
        "question": "¿Qué es el grass-fed?",
        "expected_facts": ["pasto", "grass", "fed", "extensivo", "hierba"],
        "min_expected": 2,
        "prohibited": ["cannabis", "cerdo", "gallina"],
    },
    {
        "domain": "VACUNO",
        "question": "¿Qué diferencia hay entre grass-fed y grass-finished?",
        "expected_facts": ["grass-fed", "grass-finished", "grano", "pasto", "sacrificio"],
        "min_expected": 3,
        "prohibited": [],
    },

    # ── IBÉRICO TERMINOLOGÍA (3) ──
    {
        "domain": "IBERICO",
        "question": "¿Cómo es el ciclo de vida del cerdo ibérico de bellota?",
        "expected_facts": ["cría", "recría", "montanera", "bellota", "dehesa", "sacrificio"],
        "min_expected": 3,
        "prohibited": ["ningot", "lechazo", "gallina", "pollo"],
    },
    {
        "domain": "IBERICO",
        "question": "¿El cerdo ibérico vive suelto o estabulado?",
        "expected_facts": ["suelto", "dehesa", "montanera", "extensivo", "bellota"],
        "min_expected": 2,
        "prohibited": ["ningot", "lechazo"],
    },
    {
        "domain": "IBERICO",
        "question": "¿Qué razas de cerdo ibérico existen?",
        "expected_facts": ["Retinto", "Entrepelado", "Lampiño", "Torbiscal", "ibérico"],
        "min_expected": 3,
        "prohibited": ["Cremona", "Blangy", "gallina"],
    },

    # ── CONFUSIÓN BIOLÓGICA (3) ──
    {
        "domain": "CONFUSION",
        "question": "¿Se pueden cruzar patos con gallinas?",
        "expected_facts": ["no", "imposible", "especie", "diferente", "Anatidae", "Phasianidae"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "CONFUSION",
        "question": "¿Qué es la Selle de protection para gallinas?",
        "expected_facts": ["accesorio", "protección", "dorso", "gallo", "monta"],
        "min_expected": 2,
        "prohibited": [],
    },
    {
        "domain": "CONFUSION",
        "question": "¿Cuántos huevos pone una gallina Cremona?",
        "expected_facts": ["no conozco", "no existe", "confusión"],
        "min_expected": 1,
        "prohibited": [],
    },

    # ── IOT EXTENSIVO (3) ──
    {
        "domain": "IOT_EXT",
        "question": "¿Qué es Digitanimal?",
        "expected_facts": ["Digitanimal", "España", "GPS", "ganadería", "extensivo"],
        "min_expected": 3,
        "prohibited": ["gallina", "pollo"],
    },
    {
        "domain": "IOT_EXT",
        "question": "¿Qué es Nofence?",
        "expected_facts": ["Nofence", "Noruega", "cerca virtual", "collar", "GPS"],
        "min_expected": 3,
        "prohibited": [],
    },
    {
        "domain": "IOT_EXT",
        "question": "¿Qué es mioty y cómo se usa en ganadería?",
        "expected_facts": ["mioty", "LPWAN", "Fraunhofer", "sensor", "telegram"],
        "min_expected": 2,
        "prohibited": [],
    },

    # ── DUROC vs PIETRAIN (2) ──
    {
        "domain": "GENETICS",
        "question": "Compara Duroc y Pietrain como línea padre en porcino",
        "expected_facts": ["Duroc", "Pietrain", "magro", "grasa", "halotano", "HAL", "IMF"],
        "min_expected": 3,
        "prohibited": ["gallina", "pollo", "bovino"],
    },
    {
        "domain": "GENETICS",
        "question": "¿Qué es el gen del halotano en porcino?",
        "expected_facts": ["halotano", "HAL", "RYR1", "estrés", "PSE", "Pietrain"],
        "min_expected": 3,
        "prohibited": ["gallina", "bovino"],
    },

    # ── AVICULTURA FRANCESA (2) ──
    {
        "domain": "AVICULTURA",
        "question": "¿Qué razas de gallina francesa son ideales para capones?",
        "expected_facts": ["Bresse", "La Flèche", "Faverolles", "Barbezieux", "Houdan", "Coucou"],
        "min_expected": 3,
        "prohibited": ["Cremona", "Blangy", "Duroc", "cerdo"],
    },
    {
        "domain": "AVICULTURA",
        "question": "¿Qué raza de animal es la Bresse?",
        "expected_facts": ["avícola", "gallina", "ave", "AOP", "Francia"],
        "min_expected": 2,
        "prohibited": ["cerdo", "vaca", "bovino", "porcino"],
    },
]


# ── Evaluadores ──────────────────────────────────────

def check_expected_facts(answer: str, expected: list[str], min_count: int) -> tuple[bool, int, list[str]]:
    """Verifica que al menos min_count hechos esperados aparecen en la respuesta."""
    answer_lower = answer.lower()
    found = [f for f in expected if f.lower() in answer_lower]
    return len(found) >= min_count, len(found), found


def check_prohibited(answer: str, prohibited: list[str]) -> tuple[bool, list[str]]:
    """Verifica que ningún elemento prohibido aparece (confusión de especie)."""
    answer_lower = answer.lower()
    found = [p for p in prohibited if p.lower() in answer_lower]
    return len(found) == 0, found


def check_no_markdown(answer: str) -> tuple[bool, list[str]]:
    """Verifica que la respuesta no contiene markdown."""
    issues = []
    if re.search(r"^#{1,6}\s", answer, re.MULTILINE):
        issues.append("headers (#)")
    if "**" in answer:
        issues.append("negritas (**)")
    if re.search(r"^\s*\*\s", answer, re.MULTILINE):
        issues.append("bullets (*)")
    if "```" in answer:
        issues.append("code blocks (```)")
    return len(issues) == 0, issues


def check_not_blocked(answer: str) -> bool:
    """Verifica que no es la respuesta fallback del critic."""
    return "No puedo darte una respuesta fiable" not in answer


# ── Ejecución ────────────────────────────────────────

def run_question(q: dict) -> dict:
    """Ejecuta una pregunta gold y evalúa la respuesta."""
    t0 = time.time()
    result = {
        "domain": q["domain"],
        "question": q["question"][:80],
        "passed": False,
        "latency_s": 0,
        "issues": [],
    }

    try:
        resp = httpx.post(
            f"{BACKEND_URL}/v1/chat/completions",
            json={
                "model": "seedy",
                "messages": [{"role": "user", "content": q["question"]}],
                "stream": False,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
    except Exception as e:
        result["issues"].append(f"ERROR: {e}")
        result["latency_s"] = time.time() - t0
        return result

    result["latency_s"] = round(time.time() - t0, 1)
    result["answer_preview"] = answer[:200]

    # Check 1: No es fallback del critic
    if not check_not_blocked(answer):
        result["issues"].append("BLOCKED por critic")
        return result

    # Check 2: Hechos esperados
    facts_ok, facts_count, facts_found = check_expected_facts(
        answer, q["expected_facts"], q.get("min_expected", 2)
    )
    if not facts_ok:
        result["issues"].append(
            f"FACTS: solo {facts_count}/{q.get('min_expected', 2)} "
            f"(encontrados: {facts_found})"
        )

    # Check 3: Sin confusión de especie
    no_confuse, confuse_found = check_prohibited(answer, q.get("prohibited", []))
    if not no_confuse:
        result["issues"].append(f"CONFUSION: {confuse_found}")

    # Check 4: Sin markdown
    no_md, md_issues = check_no_markdown(answer)
    if not no_md:
        result["issues"].append(f"MARKDOWN: {md_issues}")

    result["passed"] = len(result["issues"]) == 0
    return result


def main():
    parser = argparse.ArgumentParser(description="Seedy Eval Suite")
    parser.add_argument("--domain", type=str, default=None, help="Filtrar por dominio")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N preguntas")
    args = parser.parse_args()

    questions = GOLD_QUESTIONS
    if args.domain:
        questions = [q for q in questions if q["domain"].upper() == args.domain.upper()]

    if args.limit > 0:
        questions = questions[:args.limit]

    print(f"\n{'='*70}")
    print(f"  SEEDY EVAL SUITE — {len(questions)} preguntas gold")
    print(f"  Backend: {BACKEND_URL}")
    print(f"{'='*70}\n")

    results = []
    passed = 0
    total = len(questions)

    for i, q in enumerate(questions, 1):
        domain_short = q["domain"][:8]
        print(f"[{i:02d}/{total}] {domain_short:8s} | {q['question'][:55]}...", end=" ", flush=True)

        r = run_question(q)
        results.append(r)

        if r["passed"]:
            passed += 1
            print(f"PASS ({r['latency_s']}s)")
        else:
            issues_str = " | ".join(r["issues"])
            print(f"FAIL ({r['latency_s']}s) — {issues_str}")

    # Resumen
    accuracy = passed / total * 100 if total else 0
    avg_latency = sum(r["latency_s"] for r in results) / total if total else 0

    # Por dominio
    domain_stats = {}
    for r in results:
        d = r["domain"]
        if d not in domain_stats:
            domain_stats[d] = {"total": 0, "passed": 0}
        domain_stats[d]["total"] += 1
        if r["passed"]:
            domain_stats[d]["passed"] += 1

    print(f"\n{'='*70}")
    print(f"  RESULTADO: {passed}/{total} ({accuracy:.0f}%)")
    print(f"  Latencia media: {avg_latency:.1f}s")
    print(f"{'='*70}")

    for d, s in sorted(domain_stats.items()):
        pct = s["passed"] / s["total"] * 100
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"  {d:12s}  {bar}  {s['passed']}/{s['total']} ({pct:.0f}%)")

    # Fallos detallados
    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\n  FALLOS DETALLADOS:")
        for r in failures:
            print(f"  - [{r['domain']}] {r['question']}")
            for issue in r["issues"]:
                print(f"    ! {issue}")

    if args.json:
        output = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": total,
            "passed": passed,
            "accuracy_pct": round(accuracy, 1),
            "avg_latency_s": round(avg_latency, 1),
            "domain_stats": domain_stats,
            "results": results,
        }
        json_path = f"/tmp/seedy_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n  JSON guardado: {json_path}")

    print()
    return 0 if accuracy >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
