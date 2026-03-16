"""Pipeline de autoingesta — Parser: extrae texto limpio de HTML y PDF."""

import logging
import re

logger = logging.getLogger(__name__)


def parse_html(html: str) -> str:
    """
    Extrae texto limpio de HTML usando trafilatura.
    Fallback a regex básico si trafilatura falla.
    """
    if not html or not html.strip():
        return ""

    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
        if text and len(text.strip()) > 50:
            return text.strip()
    except ImportError:
        logger.warning("trafilatura no disponible, usando fallback regex")
    except Exception as e:
        logger.warning(f"trafilatura falló: {e}")

    # Fallback: quitar tags HTML con regex
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_pdf(filepath: str) -> str:
    """Extrae texto de un PDF usando pymupdf (fitz)."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(filepath)
        pages = []
        for page in doc:
            text = page.get_text()
            if text and text.strip():
                pages.append(text.strip())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        logger.error("pymupdf no disponible — pip install pymupdf")
        return ""
    except Exception as e:
        logger.error(f"Error parseando PDF {filepath}: {e}")
        return ""


def parse_item(item: dict) -> str:
    """
    Parsea un item descargado y devuelve texto limpio.
    - Si tiene 'html', lo parsea con trafilatura.
    - Si solo tiene 'summary', limpia HTML del summary.
    - Si tiene 'raw_path' a un PDF, extrae texto del PDF.
    """
    # Caso 1: HTML completo (fuentes tipo 'page')
    html = item.get("html", "")
    if html:
        return parse_html(html)

    # Caso 2: Summary del RSS (puede contener HTML)
    summary = item.get("summary", "")
    if summary:
        # Muchos feeds RSS devuelven HTML en el summary
        if "<" in summary:
            return parse_html(summary)
        return summary.strip()

    # Caso 3: PDF raw
    raw_path = item.get("raw_path", "")
    if raw_path and raw_path.endswith(".pdf"):
        return parse_pdf(raw_path)

    return ""


def fetch_and_parse_full(item: dict) -> str:
    """
    Para items de RSS que solo tienen summary, intenta descargar
    la página completa y extraer el texto.
    Devuelve el texto del artículo completo o el summary si falla.
    """
    url = item.get("url", "")
    summary_text = parse_item(item)

    # Si el summary es suficientemente largo, usar eso
    if len(summary_text) > 300:
        return summary_text

    # Intentar descargar el artículo completo
    if url:
        try:
            import httpx
            from pipelines.ingest.settings import get_settings
            settings = get_settings()
            with httpx.Client(
                timeout=settings.fetch_timeout,
                headers={"User-Agent": settings.user_agent},
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                full_text = parse_html(resp.text)
                if full_text and len(full_text) > len(summary_text):
                    return full_text
        except Exception as e:
            logger.debug(f"No se pudo descargar artículo completo {url}: {e}")

    return summary_text
