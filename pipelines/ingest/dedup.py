"""Pipeline de autoingesta — Deduplicación por URL canónica y hash de texto."""

import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from pipelines.ingest.state_db import StateDB

logger = logging.getLogger(__name__)


def canonical_url(url: str) -> str:
    """
    Normaliza una URL para comparación:
    - Elimina fragmentos (#)
    - Elimina parámetros de tracking (utm_*, fbclid, etc.)
    - Lowercase del host
    - Elimina trailing slash
    """
    parsed = urlparse(url.strip())

    # Parámetros de tracking a eliminar
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "source",
    }

    # Filtrar parámetros
    qs = parse_qs(parsed.query, keep_blank_values=False)
    clean_qs = {k: v for k, v in qs.items() if k.lower() not in tracking_params}
    clean_query = urlencode(clean_qs, doseq=True)

    # Reconstruir
    clean = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        parsed.params,
        clean_query,
        "",  # sin fragment
    ))
    return clean


def deduplicate(items: list[dict], db: StateDB) -> list[dict]:
    """
    Filtra items ya vistos por URL canónica.
    Devuelve solo los nuevos.
    """
    new_items = []
    skipped = 0

    for item in items:
        url = canonical_url(item.get("url", ""))
        if not url:
            continue

        if db.is_url_seen(url):
            skipped += 1
            continue

        item["canonical_url"] = url
        new_items.append(item)

    logger.info(f"  Dedup URLs: {len(new_items)} nuevos, {skipped} ya vistos")
    return new_items


def deduplicate_by_content(items: list[dict], texts: dict[str, str], db: StateDB) -> list[dict]:
    """
    Filtra items cuyo texto ya fue indexado (hash SHA-256).
    texts: {url: texto_parseado}
    """
    new_items = []
    skipped = 0

    for item in items:
        url = item.get("canonical_url", item.get("url", ""))
        text = texts.get(url, "")

        if not text or len(text.strip()) < 50:
            continue

        text_hash = StateDB.text_hash(text)
        if db.is_hash_seen(text_hash):
            skipped += 1
            logger.debug(f"  Texto duplicado: {item.get('title', url)}")
            continue

        item["text_hash"] = text_hash
        item["parsed_text"] = text
        new_items.append(item)

    logger.info(f"  Dedup contenido: {len(new_items)} únicos, {skipped} duplicados")
    return new_items
