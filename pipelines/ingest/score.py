"""Pipeline de autoingesta — Scoring: fiabilidad + relevancia."""

import logging
import re

from pipelines.ingest.settings import get_settings

logger = logging.getLogger(__name__)

# Keywords por dominio para cálculo de relevancia (0-40)
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "porcino": [
        "porcino", "cerdo", "cerda", "lechón", "ibérico", "cebo",
        "engorde", "maternidad", "destete", "sige", "ecogan",
        "pienso", "granja", "nave", "purín", "bienestar animal",
        "jamón", "bellota", "montanera", "dehesa", "porcine",
        "swine", "pig", "sow", "piglet", "boar",
    ],
    "vacuno": [
        "vacuno", "bovino", "vaca", "ternero", "novilla", "toro",
        "carne", "leche", "extensivo", "pastos", "dehesa",
        "cruzamiento", "destete", "cebadero", "matadero",
        "cattle", "beef", "dairy", "cow", "bull", "calf",
        "feedlot", "heifer", "steer",
    ],
    "avicultura": [
        "avícola", "avicultura", "pollo", "gallina", "capón",
        "cruce", "raza", "plumaje", "huevo", "corral",
        "campero", "label rouge", "caponización",
        "broiler", "layer", "poultry", "chicken", "hen",
        "salmonella", "influenza aviar",
    ],
    "nutricion": [
        "nutrición", "alimentación", "pienso", "ración", "dieta",
        "proteína", "lisina", "aminoácido", "energía", "fibra",
        "formulación", "materia prima", "soja", "cebada", "maíz",
        "lonja", "cotización", "precio", "mercado",
        "feed", "nutrition", "additive", "supplement",
    ],
    "genetica": [
        "genética", "raza", "cruce", "híbrido", "selección",
        "heredabilidad", "blup", "ebv", "gebv", "consanguinidad",
        "fenotipo", "genotipo", "line", "duroc", "pietrain",
        "large white", "landrace", "retinta", "avileña",
        "breed", "crossbreed", "genetics", "genomics",
    ],
    "normativa": [
        "real decreto", "normativa", "ley", "reglamento", "boe",
        "directiva", "orden", "resolución", "sige", "ecogan",
        "bienestar", "sanidad", "trazabilidad", "registro",
        "pac", "ayuda", "subvención", "convocatoria",
        "diario oficial", "doue", "regulation",
    ],
    "iot": [
        "sensor", "iot", "mqtt", "temperatura", "humedad",
        "monitorización", "digital twin", "gateway", "lorawan",
        "mioty", "influxdb", "grafana", "dashboard",
    ],
    # Catch-all ganadero: artículos genéricos de ganadería sin dominio claro
    "estrategia": [
        "ganadería", "ganadero", "explotación", "livestock",
        "animal", "producción animal", "cadena alimentaria",
        "antimicrobiano", "antibiótico", "resistencia",
        "emisiones", "cambio climático", "sostenibilidad",
        "relevo generacional", "pac", "ayuda", "subvención",
        "reposición", "rentabilidad", "arrendamiento",
        "finca", "parcela", "superficie agraria",
        "veterinario", "sanidad animal", "vacunación",
        "dermatosis", "enfermedad", "foco", "brote",
        "mapa", "ministerio", "denominación de origen",
    ],
}


def score_item(item: dict) -> tuple[float, str]:
    """
    Calcula puntuación total (0-100) = fiabilidad + relevancia.

    - Fiabilidad (0-60): viene del sources.yaml (reliability del medio).
    - Relevancia (0-40): coincidencia de keywords ganaderas en título + texto.

    Returns: (score, best_domain)
    """
    reliability = item.get("reliability", 30)

    # Texto a evaluar: título + summary/texto parseado
    title = item.get("title", "").lower()
    text = item.get("parsed_text", item.get("summary", "")).lower()
    full = f"{title} {text}"

    # Calcular relevancia por dominio
    best_relevance = 0.0
    best_domain = "estrategia"  # default

    for domain, keywords in _DOMAIN_KEYWORDS.items():
        hits = 0
        for kw in keywords:
            # Buscar keyword en el texto
            if re.search(r"\b" + re.escape(kw) + r"\b", full):
                hits += 1

        if not keywords:
            continue

        # Relevancia = ratio de keywords encontradas * 40
        relevance = min((hits / len(keywords)) * 40 * 3, 40.0)  # *3 boost porque basta con ~1/3

        if relevance > best_relevance:
            best_relevance = relevance
            best_domain = domain

    total = reliability + best_relevance
    return round(total, 1), best_domain


def classify_and_score(items: list[dict]) -> list[dict]:
    """
    Añade score y dominio a cada item.
    Clasifica en: 'index', 'quarantine', 'rejected'.
    """
    settings = get_settings()
    scored = []

    for item in items:
        score, domain = score_item(item)
        item["score"] = score
        item["domain"] = domain

        if score >= settings.score_threshold:
            item["status"] = "index"
        elif score >= settings.quarantine_threshold:
            item["status"] = "quarantine"
        else:
            item["status"] = "rejected"

        scored.append(item)
        level = "✅" if item["status"] == "index" else ("⏸️" if item["status"] == "quarantine" else "❌")
        logger.info(
            f"  {level} [{score:.0f}] {domain}: {item.get('title', '')[:60]}"
        )

    indexed = sum(1 for i in scored if i["status"] == "index")
    quarantined = sum(1 for i in scored if i["status"] == "quarantine")
    rejected = sum(1 for i in scored if i["status"] == "rejected")
    logger.info(f"  Scoring: {indexed} indexar, {quarantined} cuarentena, {rejected} rechazados")

    return scored
