"""
Seedy Backend — URL Fetcher via crawl4ai.

Detecta URLs en queries del usuario, las crawlea con crawl4ai
y devuelve contenido textual limpio para inyectar como contexto.
"""

import logging
import re
from html import unescape

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

# Regex para detectar URLs en texto del usuario
_URL_RE = re.compile(r"https?://[^\s)\]>,\"']+", re.IGNORECASE)

# Límite de texto extraído por URL (chars)
_MAX_TEXT_LEN = 6000

# Timeout para petición a crawl4ai
_CRAWL_TIMEOUT = 45.0


def extract_urls(text: str) -> list[str]:
    """Extrae URLs http/https del texto del usuario."""
    return _URL_RE.findall(text)


def _strip_query_urls(text: str) -> str:
    """Elimina las URLs del texto para obtener la pregunta limpia."""
    return _URL_RE.sub("", text).strip()


def _html_to_text(html: str) -> str:
    """Convierte HTML a texto plano eliminando scripts, estilos y tags."""
    # Eliminar scripts, styles, SVGs, noscript
    cleaned = re.sub(
        r"<(script|style|svg|noscript)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Reemplazar tags con espacios
    text = re.sub(r"<[^>]+>", " ", cleaned)
    # Decodificar entidades HTML
    text = unescape(text)
    # Colapsar whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def fetch_url_content(url: str) -> str | None:
    """
    Crawlea una URL con crawl4ai y devuelve texto limpio.

    Returns:
        Texto extraído (truncado a _MAX_TEXT_LEN) o None si falla.
    """
    try:
        settings = get_settings()
        crawl_url = f"{settings.crawl4ai_url}/crawl"

        async with httpx.AsyncClient(timeout=_CRAWL_TIMEOUT) as client:
            resp = await client.post(
                crawl_url,
                json={"urls": [url], "priority": 10},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success") or not data.get("results"):
            logger.warning(f"[URLFetcher] crawl4ai devolvió sin resultados: {url}")
            return None

        result = data["results"][0]

        if not result.get("success", True):
            logger.warning(f"[URLFetcher] crawl falló para {url}")
            return None

        # Extraer texto limpio del HTML (más fiable que el markdown de crawl4ai
        # que a veces incluye basura de iconos/SVG)
        text = ""
        html = result.get("html", "")
        if html:
            text = _html_to_text(html)

        # Si HTML está vacío, intentar markdown como fallback
        if len(text) < 50:
            md = result.get("markdown", "")
            if isinstance(md, dict):
                raw = md.get("raw_markdown", "")
                if isinstance(raw, str) and len(raw.strip()) > 50:
                    text = raw.strip()
            elif isinstance(md, str) and len(md.strip()) > 50:
                text = md.strip()

        if not text:
            logger.warning(f"[URLFetcher] No se pudo extraer texto de {url}")
            return None

        # Truncar
        if len(text) > _MAX_TEXT_LEN:
            text = text[:_MAX_TEXT_LEN] + "…"

        logger.info(f"[URLFetcher] {url} → {len(text)} chars")
        return text

    except httpx.TimeoutException:
        logger.warning(f"[URLFetcher] Timeout crawleando {url}")
        return None
    except Exception as e:
        logger.error(f"[URLFetcher] Error crawleando {url}: {e}")
        return None


async def fetch_urls_from_query(query: str) -> list[dict]:
    """
    Detecta URLs en la query, las crawlea y devuelve chunks de contexto.

    Returns:
        Lista de chunks-dict con keys: text, file, collection, chunk_index, rerank_score
    """
    urls = extract_urls(query)
    if not urls:
        return []

    logger.info(f"[URLFetcher] {len(urls)} URL(s) detectada(s) en query: {urls}")

    chunks = []
    for i, url in enumerate(urls[:3]):  # Máximo 3 URLs
        content = await fetch_url_content(url)
        if content:
            chunks.append({
                "text": f"[Contenido de la web {url}]\n{content}",
                "file": url,
                "collection": "url_crawl",
                "chunk_index": i,
                "rerank_score": 0.9,  # Prioridad alta: el usuario pidió explícitamente esta URL
            })

    return chunks
