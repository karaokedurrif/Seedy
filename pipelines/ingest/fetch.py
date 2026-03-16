"""Pipeline de autoingesta — Fetcher: descarga RSS y páginas web."""

import logging
import yaml
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pipelines.ingest.settings import get_settings

logger = logging.getLogger(__name__)


def load_sources(sources_file: str | None = None) -> list[dict]:
    """Carga las fuentes desde sources.yaml."""
    path = sources_file or get_settings().sources_file
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def _http_get(url: str, timeout: int = 30) -> httpx.Response:
    """GET con reintentos (tenacity)."""
    settings = get_settings()
    with httpx.Client(
        timeout=timeout,
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
        },
        follow_redirects=True,
        verify=False,  # Algunos sites ganaderos tienen certs caducados
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp


def fetch_rss(source: dict) -> list[dict]:
    """
    Descarga y parsea un feed RSS.
    Devuelve lista de items con: url, title, published, summary, source_name, reliability, tags.
    """
    url = source["url"]
    name = source["name"]
    logger.info(f"  Fetching RSS: {name} ({url})")

    try:
        resp = _http_get(url, timeout=get_settings().fetch_timeout)
        feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.error(f"  Error descargando RSS {name}: {e}")
        return []

    items = []
    for entry in feed.entries:
        link = getattr(entry, "link", "")
        if not link:
            continue

        items.append({
            "url": link.strip(),
            "title": getattr(entry, "title", "Sin título").strip(),
            "published": getattr(entry, "published", ""),
            "summary": getattr(entry, "summary", ""),
            "source_name": name,
            "reliability": source.get("reliability", 30),
            "tags": source.get("tags", []),
        })

    logger.info(f"  → {len(items)} items de {name}")
    return items


def fetch_page(source: dict) -> list[dict]:
    """
    Descarga una página web completa (para fuentes tipo 'page').
    Devuelve un solo item con el HTML raw para parsear después.
    """
    url = source["url"]
    name = source["name"]
    logger.info(f"  Fetching page: {name} ({url})")

    try:
        resp = _http_get(url, timeout=get_settings().fetch_timeout)
        return [{
            "url": url,
            "title": name,
            "published": "",
            "summary": "",
            "html": resp.text,
            "source_name": name,
            "reliability": source.get("reliability", 30),
            "tags": source.get("tags", []),
        }]
    except Exception as e:
        logger.error(f"  Error descargando página {name}: {e}")
        return []


def save_raw(item: dict, data_dir: str) -> str | None:
    """Guarda contenido raw en data/raw/YYYY/MM/DD/."""
    now = datetime.now(timezone.utc)
    day_dir = Path(data_dir) / "raw" / now.strftime("%Y/%m/%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    # Nombre basado en hash de URL
    import hashlib
    url_hash = hashlib.md5(item["url"].encode()).hexdigest()[:12]
    filename = f"{url_hash}.txt"
    filepath = day_dir / filename

    content = item.get("html") or item.get("summary", "")
    if content:
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)
    return None


def fetch_all_sources(sources_file: str | None = None) -> list[dict]:
    """
    Recorre todas las fuentes y devuelve items consolidados.
    """
    sources = load_sources(sources_file)
    all_items: list[dict] = []

    for source in sources:
        src_type = source.get("type", "rss")
        try:
            if src_type == "rss":
                items = fetch_rss(source)
            elif src_type in ("page", "url"):
                items = fetch_page(source)
            else:
                logger.warning(f"  Tipo desconocido: {src_type} para {source['name']}")
                continue
            all_items.extend(items)
        except Exception as e:
            logger.error(f"  Error procesando fuente {source['name']}: {e}")

    logger.info(f"Total items descargados: {len(all_items)}")
    return all_items
