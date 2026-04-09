"""Seedy Backend — Quality Gate: filtro de calidad para ingesta de chunks.

Valida contenido antes de indexar en Qdrant. Previene la entrada de:
- Contenido en idioma incorrecto (inglés en colecciones españolas)
- Texto demasiado corto o sin información útil
- CSV/datos tabulares crudos sin procesar
- Contenido irrelevante para la colección destino
- Duplicados semánticos evidentes

Uso:
    from services.quality_gate import validate_chunk, validate_batch

    passed, score, reasons = validate_chunk(text, collection="avicultura")
    if passed:
        # indexar en Qdrant
"""

import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

# ── Detección de idioma por stopwords ──────────────────────────

_ES_STOPWORDS = frozenset([
    "de", "la", "el", "en", "que", "los", "las", "del", "por", "con",
    "una", "para", "se", "su", "al", "es", "lo", "como", "más", "pero",
    "sus", "fue", "son", "entre", "está", "desde", "también", "muy",
    "sobre", "han", "ser", "tiene", "otro", "hay", "todos", "ya", "puede",
    "este", "cada", "donde", "sin", "uno", "estos", "parte", "ni",
])

_EN_STOPWORDS = frozenset([
    "the", "of", "and", "to", "in", "is", "it", "for", "that", "was",
    "on", "are", "with", "as", "at", "by", "from", "or", "an", "be",
    "this", "which", "have", "not", "but", "had", "has", "its", "they",
    "were", "can", "been", "would", "their", "will", "when", "who",
    "there", "all", "also", "than", "other", "into", "some", "could",
])

_FR_STOPWORDS = frozenset([
    "de", "la", "le", "les", "des", "du", "en", "un", "une", "et",
    "est", "que", "pour", "pas", "qui", "sur", "dans", "par", "avec",
    "ce", "il", "sont", "au", "se", "ne", "ou", "mais", "plus", "ont",
])


def detect_language(text: str) -> tuple[str, float]:
    """
    Detecta idioma dominante por frecuencia de stopwords.

    Returns:
        (idioma, confianza) — idioma en {"es", "en", "fr", "unknown"},
        confianza entre 0.0 y 1.0
    """
    words = re.findall(r'\b[a-záéíóúüñàèìòùâêîôûäëïöü]+\b', text.lower())

    if len(words) < 20:
        return "unknown", 0.0

    word_set = Counter(words)
    total = sum(word_set.values())

    scores = {}
    for lang, stopwords in [("es", _ES_STOPWORDS), ("en", _EN_STOPWORDS), ("fr", _FR_STOPWORDS)]:
        count = sum(word_set[w] for w in stopwords if w in word_set)
        scores[lang] = count / total if total > 0 else 0.0

    best_lang = max(scores, key=scores.get)
    best_score = scores[best_lang]
    second_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0

    # Confianza: diferencia entre el mejor y el segundo
    confidence = best_score - second_score

    # Si la diferencia es muy pequeña, no estamos seguros
    if confidence < 0.02:
        return "unknown", confidence

    return best_lang, confidence


# ── Relevancia por colección ──────────────────────────

_COLLECTION_KEYWORDS = {
    "avicultura": {
        "required_any": [
            "pollo", "gallina", "ave", "avícola", "capón", "ponedora", "gallo",
            "broiler", "huevo", "raza", "plumaje", "cresta", "gallinero", "incubación",
            "capon", "poulet", "volaille", "poule", "chicken", "poultry", "hen",
            "fowl", "breed", "layer", "hatchery", "rooster",
        ],
        "reject_if_only": [
            "saint-simon", "mémoires", "versailles", "louis xiv", "bourbon",
            "cryptocurrency", "blockchain", "javascript", "react", "python tutorial",
        ],
    },
    "genetica": {
        "required_any": [
            "genética", "genómica", "blup", "epd", "consanguinidad", "cruce",
            "heredabilidad", "alelo", "genotipo", "fenotipo", "snp", "qtl",
            "heterosis", "f1", "línea genética", "valoración genética",
            "genetic", "genomic", "breeding", "heritability", "allele",
        ],
        "reject_if_only": [],
    },
    "nutricion": {
        "required_any": [
            "nutrición", "pienso", "alimentación", "ración", "proteína",
            "energía", "fibra", "vitamina", "mineral", "forraje", "ensilado",
            "feed", "nutrition", "diet", "ration", "protein", "energy",
        ],
        "reject_if_only": [],
    },
    "iot_hardware": {
        "required_any": [
            "sensor", "iot", "mqtt", "lorawan", "lora", "esp32", "arduino",
            "gateway", "telemetría", "influx", "grafana", "modbus", "rfid",
            "temperatura", "humedad", "co2", "amoniaco",
        ],
        "reject_if_only": [],
    },
    "digital_twins": {
        "required_any": [
            "gemelo digital", "digital twin", "bim", "3d", "cesium",
            "ndvi", "gis", "ortofoto", "modelado", "simulación",
        ],
        "reject_if_only": [],
    },
    "normativa": {
        "required_any": [
            "normativa", "real decreto", "reglamento", "directiva", "ley",
            "pac", "pepac", "ecogan", "sige", "condicionalidad",
            "bienestar animal", "trazabilidad", "registro ganadero",
        ],
        "reject_if_only": [],
    },
    "estrategia": {
        "required_any": [
            "mercado", "precio", "competencia", "subvención", "financiación",
            "plan negocio", "rentabilidad", "cooperativa", "cadena valor",
            "market", "price", "competition", "subsidy", "business",
        ],
        "reject_if_only": [],
    },
    "geotwin": {
        "required_any": [
            "geotwin", "gis", "sig", "parcela", "catastro", "pnoa",
            "ortofoto", "cesium", "sentinel", "ndvi", "dem",
        ],
        "reject_if_only": [],
    },
}

# ── Detección de CSV/datos tabulares crudos ──────

_CSV_PATTERN = re.compile(
    r'(?:[\d.,]+[;,\t]){3,}',  # 3+ campos numéricos separados por delimitadores
)

_TABLE_HEADER_PATTERN = re.compile(
    r'^[\w\s]+[;,\t|][\w\s]+[;,\t|][\w\s]+',
    re.MULTILINE,
)


def _is_tabular_data(text: str) -> bool:
    """Detecta si un chunk es principalmente datos tabulares/CSV sin procesar."""
    lines = text.strip().split("\n")
    if not lines:
        return False

    csv_lines = sum(1 for line in lines if _CSV_PATTERN.search(line))
    ratio = csv_lines / len(lines)

    return ratio > 0.5 and len(lines) > 3


# ── Calidad mínima de contenido ──────────────────

def _content_quality_score(text: str) -> float:
    """
    Score de calidad de contenido (0.0-1.0).

    Factores positivos: frases completas, vocabulario diverso, estructura.
    Factores negativos: exceso de números, repetición, texto fragmentado.
    """
    if not text.strip():
        return 0.0

    words = text.split()
    if len(words) < 10:
        return 0.1

    # Diversidad léxica (type-token ratio)
    unique_words = set(w.lower() for w in words)
    ttr = len(unique_words) / len(words)

    # Proporción de frases completas (terminan en .)
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 10]
    sentence_ratio = len(sentences) / max(1, len(text.split("\n")))

    # Proporción de dígitos
    digit_ratio = sum(c.isdigit() for c in text) / max(1, len(text))

    # Longitud promedio de palabra (muy corta = fragmentado)
    avg_word_len = sum(len(w) for w in words) / len(words)

    score = 0.0
    score += min(0.3, ttr * 0.5)                    # Diversidad: hasta 0.3
    score += min(0.2, sentence_ratio * 0.3)          # Frases completas: hasta 0.2
    score += max(0.0, 0.2 - digit_ratio * 2)         # Penalizar exceso numérico
    score += min(0.15, (avg_word_len - 2) * 0.05)    # Palabras reales (no fragmentos)
    score += min(0.15, len(words) / 500 * 0.15)      # Longitud razonable

    return max(0.0, min(1.0, score))


# ── API principal ──────────────────────────────────


def validate_chunk(
    text: str,
    collection: str,
    source_file: str = "",
    min_length: int = 50,
    min_quality: float = 0.25,
    require_spanish: bool | None = None,
) -> tuple[bool, float, list[str]]:
    """
    Valida un chunk antes de indexarlo en Qdrant.

    Args:
        text: contenido del chunk
        collection: colección destino
        source_file: nombre del archivo fuente (para logging)
        min_length: longitud mínima (chars)
        min_quality: score mínimo de calidad
        require_spanish: si True, rechaza chunks en inglés.
            None (default) = auto-detecta por colección (ES-primarias rechazan EN).

    Returns:
        (passed, score, reasons)
        - passed: True si el chunk pasa todos los filtros
        - score: score de calidad (0.0-1.0)
        - reasons: lista de razones de rechazo (vacía si passed)
    """
    reasons = []

    # 1. Longitud mínima
    if len(text.strip()) < min_length:
        reasons.append(f"demasiado_corto ({len(text.strip())} < {min_length})")
        return False, 0.0, reasons

    # 2. Detección de datos tabulares crudos
    if _is_tabular_data(text):
        reasons.append("datos_tabulares_crudos")
        return False, 0.1, reasons

    # 3. Calidad de contenido
    quality = _content_quality_score(text)
    if quality < min_quality:
        reasons.append(f"calidad_baja ({quality:.2f} < {min_quality})")
        return False, quality, reasons

    # 4. Idioma
    lang, confidence = detect_language(text)

    # Colecciones que deben ser principalmente en español
    _ES_PRIMARY = {
        "avicultura", "nutricion", "normativa", "avicultura_intensiva",
        "bodegas_vino", "iot_hardware",
    }
    # Si require_spanish=None (default), auto-detectar por colección
    effective_require_es = require_spanish if require_spanish is not None else (collection in _ES_PRIMARY)

    if effective_require_es and lang == "en" and confidence > 0.05:
        reasons.append(f"idioma_ingles (conf={confidence:.2f})")
        return False, quality, reasons

    # Para colecciones con contenido mixto: no rechazar, pero penalizar score
    if lang == "en" and confidence > 0.08:
        quality *= 0.7  # Penalización de 30% para inglés

    # 5. Relevancia por colección
    col_config = _COLLECTION_KEYWORDS.get(collection)
    if col_config:
        text_lower = text.lower()

        # Rechazar contenido claramente fuera de dominio
        reject_keywords = col_config.get("reject_if_only", [])
        if reject_keywords:
            has_reject = any(kw in text_lower for kw in reject_keywords)
            has_domain = any(kw in text_lower for kw in col_config["required_any"])
            if has_reject and not has_domain:
                reasons.append(f"contenido_fuera_de_dominio ({collection})")
                return False, quality, reasons

        # Verificar presencia de al menos 1 keyword de dominio
        required = col_config.get("required_any", [])
        if required:
            has_any = any(kw in text_lower for kw in required)
            if not has_any:
                # No rechazar directamente, pero penalizar fuerte
                quality *= 0.5
                if quality < min_quality:
                    reasons.append(
                        f"sin_keywords_dominio ({collection}, score={quality:.2f})"
                    )
                    return False, quality, reasons

    return True, quality, reasons


def validate_batch(
    chunks: list[dict],
    collection: str,
    **kwargs,
) -> tuple[list[dict], list[dict], dict]:
    """
    Valida un batch de chunks, devolviendo los que pasan y los rechazados.

    Args:
        chunks: lista de dicts con al menos {"text": str}
        collection: colección destino
        **kwargs: parámetros adicionales para validate_chunk

    Returns:
        (passed_chunks, rejected_chunks, stats)
    """
    passed = []
    rejected = []
    reason_counts: dict[str, int] = {}

    for chunk in chunks:
        text = chunk.get("text", "")
        source = chunk.get("source_file", "")

        ok, score, reasons = validate_chunk(
            text, collection, source_file=source, **kwargs
        )

        if ok:
            chunk["quality_score"] = score
            passed.append(chunk)
        else:
            chunk["rejection_reasons"] = reasons
            chunk["quality_score"] = score
            rejected.append(chunk)
            for r in reasons:
                # Extraer razón base (sin detalles entre paréntesis)
                base_reason = r.split("(")[0].strip()
                reason_counts[base_reason] = reason_counts.get(base_reason, 0) + 1

    stats = {
        "total": len(chunks),
        "passed": len(passed),
        "rejected": len(rejected),
        "pass_rate": len(passed) / max(1, len(chunks)),
        "rejection_reasons": reason_counts,
    }

    if rejected:
        logger.info(
            f"[QualityGate] {collection}: {len(passed)}/{len(chunks)} pasaron "
            f"({stats['pass_rate']:.0%}). Rechazados: {reason_counts}"
        )

    return passed, rejected, stats
