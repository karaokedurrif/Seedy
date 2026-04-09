"""Seedy Backend — Búsqueda web vía SearXNG (fallback cuando RAG local es insuficiente)."""

import logging
import re
import httpx
from config import get_settings

logger = logging.getLogger(__name__)

# Umbral de score RAG por debajo del cual se complementa con búsqueda web
WEB_SEARCH_THRESHOLD = 0.012  # score RRF; resultados por debajo → búsqueda web
MAX_WEB_RESULTS = 5

# ── Detección de intención comercial / producto ──────
# Queries sobre productos, precios, tiendas, recomendaciones de compra
# necesitan búsqueda web obligatoria (RAG no tiene catálogos de productos).
_PRODUCT_INTENT_RE = re.compile(
    r"(?:"
    r"compr[ae]r?\b"                          # comprar, compra, compre
    r"|precio[s]?\b"                          # precio, precios
    r"|tienda[s]?\b"                          # tienda, tiendas
    r"|d[óo]nde\s+(?:comprar|conseg|encontr|vend)"  # dónde comprar/conseguir/encontrar
    r"|cu[áa]nto\s+(?:cuesta|vale|cuestan|valen)"   # cuánto cuesta/vale
    r"|presupuesto"                           # presupuesto
    r"|comparativ[ao]"                        # comparativa, comparativo
    r"|proveedor[es]*\b"                      # proveedor, proveedores
    r"|distribuidor[es]*\b"                   # distribuidor, distribuidores
    r"|cat[áa]logo"                           # catálogo
    r"|oferta[s]?\b"                          # oferta, ofertas
    r"|descuento"                             # descuento
    r"|recom[ié]nd\w*\s+\d+"                  # "recomiéndame 4 ..." (recomendar + número)
    r"|mejor(?:es)?\s+\d*\s*(?:incubadora|nacedora|equipo|sensor|maquin|software|herramienta|producto|dispositivo)"
    r"|incubadora[s]?\s+(?:para|de|casera|autom[áa]tica|digital|eléctrica|industrial)"
    r"|nacedora[s]?\s+(?:para|de|autom[áa]tica)"
    r"|marca[s]?\s+(?:de|para)\b"             # marca/s de/para ...
    r"|modelo[s]?\s+(?:de|para)\b"            # modelo/s de/para ...
    r"|\bBOM\b"                               # Bill of Materials
    r"|\bqu[ée]\s+(?:sensor|dispositivo|c[aá]mara|equipo)"  # qué sensor/dispositivo poner
    r"|dispositivo[s]?\s+(?:iot|para|de)\b"   # dispositivos IoT/para/de
    r"|sensor[es]*\s+(?:de|para|iot|zigbee|lora)\b"  # sensores de/para/IoT
    r"|c[aá]mara[s]?\s+(?:de|para|ip|t[ée]rmica|vigilancia)"
    r"|panel[es]*\s+solar[es]*\b"             # paneles solares
    r"|gateway[s]?\b"                         # gateways
    r"|\bestaci[oó]n\s+meteorol[oó]gica"      # estación meteorológica
    r"|collar[es]*\s+(?:gps|iot|ganado)"      # collares GPS
    r"|equipamiento\b"                        # equipamiento
    r")",
    re.IGNORECASE,
)


def needs_product_search(query: str) -> bool:
    """Detecta queries con intención comercial/producto que necesitan búsqueda web."""
    return bool(_PRODUCT_INTENT_RE.search(query))


async def search_web(query: str, max_results: int = MAX_WEB_RESULTS, product_mode: bool = False) -> list[dict]:
    """
    Busca en SearXNG y devuelve resultados estructurados.
    
    Args:
        query: Consulta de búsqueda
        max_results: Número máximo de resultados
        product_mode: Si True, adapta la búsqueda para productos/precios
    
    Returns:
        Lista de dicts con keys: title, url, content (snippet)
    """
    settings = get_settings()
    searxng_url = settings.searxng_url

    if not searxng_url:
        return []

    # En modo producto, enriquecer query y aumentar resultados
    search_query = query
    if product_mode:
        max_results = max(max_results, 8)
        # Añadir términos comerciales si no los tiene ya
        has_commercial = re.search(r"precio|comprar|tienda|€|EUR", query, re.IGNORECASE)
        if not has_commercial:
            search_query = f"{query} precio comprar"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{searxng_url}/search",
                params={
                    "q": search_query,
                    "format": "json",
                    "categories": "general",
                    "language": "es",
                    "safesearch": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            })

        logger.info(f"SearXNG: {len(results)} resultados para '{search_query[:60]}...'"
                     f"{' (producto)' if product_mode else ''}")
        return results

    except Exception as e:
        logger.warning(f"SearXNG búsqueda fallida: {e}")
        return []


def format_web_results(results: list[dict]) -> str:
    """Formatea resultados web como contexto textual para el LLM."""
    if not results:
        return ""

    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"[Web {i}: {r['title']}]\n"
            f"URL: {r['url']}\n"
            f"{r['content']}"
        )

    return "\n\n".join(parts)


def should_search_web(rag_results: list[dict], threshold: float = WEB_SEARCH_THRESHOLD) -> bool:
    """
    Decide si es necesario complementar con búsqueda web.
    True si:
    - No hay resultados RAG
    - El mejor score RAG está por debajo del umbral
    """
    if not rag_results:
        return True

    best_score = max(r.get("score", 0.0) for r in rag_results)
    return best_score < threshold
