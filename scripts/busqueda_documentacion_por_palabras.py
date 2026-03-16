#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Seedy — Búsqueda Profunda de Documentación por Palabras    ║
║  Deep-search en web, RRSS, académico, archivos, bases de    ║
║  datos locales (Qdrant) y repositorios gubernamentales.     ║
╚══════════════════════════════════════════════════════════════╝

Uso:
    python scripts/busqueda_documentacion_por_palabras.py "ganadería ovina IoT"
    python scripts/busqueda_documentacion_por_palabras.py "porcino digital twin" --max 50
    python scripts/busqueda_documentacion_por_palabras.py "capón extensivo" --filetypes pdf,docx
    python scripts/busqueda_documentacion_por_palabras.py "RFID livestock" --lang en
    python scripts/busqueda_documentacion_por_palabras.py "vacuno normativa" --export resultados.csv
    python scripts/busqueda_documentacion_por_palabras.py "sensor IoT granja" --solo-fuentes web,academic
    python scripts/busqueda_documentacion_por_palabras.py "ganadería" --pages 3

Fuentes que busca:
    1. SearXNG (Google, Bing, DuckDuckGo, StartPage, Wikipedia)
    2. SearXNG Scholar (Google Scholar, Semantic Scholar, PubMed, arXiv)
    3. SearXNG RRSS & Foros (Reddit, StackOverflow, etc.)
    4. SearXNG ficheros (filetype:pdf, filetype:docx, etc.)
    5. OpenAlex API (250M+ papers académicos, acceso libre)
    6. CORE API (acceso abierto a papers full-text)
    7. Internet Archive / Wayback Machine
    8. EUR-Lex (legislación europea)
    9. Qdrant local (tu base de conocimiento RAG)
   10. Archivos locales en conocimientos/ (búsqueda por nombre)
"""

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx

# ── Config ──────────────────────────────────────────────────────────────
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")
CONOCIMIENTOS_DIR = Path(os.getenv(
    "CONOCIMIENTOS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conocimientos"),
))

OPENALEX_MAILTO = "seedy@neofarm.es"  # Polite pool — faster responses
CORE_API_KEY = os.getenv("CORE_API_KEY", "")  # Optional — works without key

DEFAULT_MAX_PER_SOURCE = 20
DEFAULT_FILETYPES = ["pdf", "docx", "xlsx", "pptx", "odt"]
QDRANT_COLLECTIONS = [
    "avicultura", "digital_twins", "estrategia", "fresh_web",
    "genetica", "geotwin", "iot_hardware", "normativa", "nutricion",
]

TIMEOUT = 20  # seconds per HTTP request

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger("deep_search")

# Suppress noisy httpx/httpcore logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ── Data model ──────────────────────────────────────────────────────────
@dataclass
class SearchResult:
    title: str
    url: str
    source: str  # e.g. "web:google", "academic:openalex", "local:qdrant"
    snippet: str = ""
    filetype: str = ""
    score: float = 0.0
    engine: str = ""
    date: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        """Normalised URL for deduplication."""
        u = re.sub(r"https?://(www\.)?", "", self.url.lower().rstrip("/"))
        return hashlib.md5(u.encode()).hexdigest()


# ── Helpers ─────────────────────────────────────────────────────────────
def _ft(url: str) -> str:
    """Guess file type from URL."""
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower().lstrip(".")
    return ext if ext in ("pdf", "docx", "xlsx", "pptx", "odt", "csv", "md", "txt", "zip") else ""


def _trim(text: str, maxlen: int = 200) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:maxlen] + "…" if len(text) > maxlen else text


async def _get(client: httpx.AsyncClient, url: str, **kw) -> Optional[dict]:
    try:
        r = await client.get(url, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug(f"  ⚠ GET {url[:80]}: {e}")
        return None


async def _post(client: httpx.AsyncClient, url: str, **kw) -> Optional[dict]:
    try:
        r = await client.post(url, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug(f"  ⚠ POST {url[:80]}: {e}")
        return None


# ── Search providers ────────────────────────────────────────────────────

async def search_searxng(
    client: httpx.AsyncClient,
    query: str,
    category: str = "general",
    pages: int = 2,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
    lang: str = "es",
    engines: str = "",
) -> list[SearchResult]:
    """Search via local SearXNG instance (aggregates many search engines)."""
    results: list[SearchResult] = []
    for page in range(1, pages + 1):
        params = {
            "q": query,
            "format": "json",
            "pageno": page,
            "language": lang,
            "categories": category,
        }
        if engines:
            params["engines"] = engines
        data = await _get(client, f"{SEARXNG_URL}/search", params=params)
        if not data:
            break
        for r in data.get("results", []):
            results.append(SearchResult(
                title=_trim(r.get("title", ""), 120),
                url=r.get("url", ""),
                source=f"web:{category}",
                snippet=_trim(r.get("content", "")),
                engine=r.get("engine", ""),
                date=r.get("publishedDate", ""),
                filetype=_ft(r.get("url", "")),
                score=r.get("score", 0),
            ))
        if len(results) >= max_results:
            break
    return results[:max_results]


async def search_searxng_files(
    client: httpx.AsyncClient,
    query: str,
    filetypes: list[str],
    pages: int = 2,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
    lang: str = "es",
) -> list[SearchResult]:
    """Search for specific file types via SearXNG."""
    results: list[SearchResult] = []
    for ft in filetypes:
        file_query = f"{query} filetype:{ft}"
        batch = await search_searxng(client, file_query, "general", pages, max_results // len(filetypes), lang)
        for r in batch:
            r.source = f"files:{ft}"
            r.filetype = ft
        results.extend(batch)
    return results[:max_results]


async def search_openalex(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
) -> list[SearchResult]:
    """Search OpenAlex (250M+ academic works, free API)."""
    results: list[SearchResult] = []
    params = {
        "search": query,
        "per_page": min(max_results, 50),
        "mailto": OPENALEX_MAILTO,
        "sort": "relevance_score:desc",
    }
    data = await _get(client, "https://api.openalex.org/works", params=params)
    if not data:
        return results
    # If no results, retry with simplified English terms
    if not data.get("results") and any(ord(c) > 127 for c in query):
        import unicodedata
        ascii_q = unicodedata.normalize('NFKD', query).encode('ascii', 'ignore').decode()
        params["search"] = ascii_q
        data = await _get(client, "https://api.openalex.org/works", params=params)
        if not data:
            return results
    for w in data.get("results", []):
        doi = w.get("doi", "") or ""
        url = doi if doi.startswith("http") else w.get("primary_location", {}).get("landing_page_url", "") or ""
        if not url:
            url = f"https://openalex.org/works/{w.get('id', '').split('/')[-1]}"
        # Get PDF link if available
        pdf_url = ""
        for loc in w.get("locations", []):
            if loc.get("pdf_url"):
                pdf_url = loc["pdf_url"]
                break
        abstract = ""
        ab_inv = w.get("abstract_inverted_index")
        if ab_inv and isinstance(ab_inv, dict):
            # Reconstruct abstract from inverted index
            word_pos = []
            for word, positions in ab_inv.items():
                for pos in positions:
                    word_pos.append((pos, word))
            word_pos.sort()
            abstract = " ".join(w for _, w in word_pos[:60])

        results.append(SearchResult(
            title=_trim(w.get("title", ""), 150),
            url=url,
            source="academic:openalex",
            snippet=_trim(abstract, 250),
            date=str(w.get("publication_year", "")),
            score=w.get("relevance_score", 0) or 0,
            filetype="pdf" if pdf_url else "",
            extra={
                "cited_by": w.get("cited_by_count", 0),
                "type": w.get("type", ""),
                "pdf_url": pdf_url,
                "open_access": w.get("open_access", {}).get("is_oa", False),
            },
        ))
    return results[:max_results]


async def search_core(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
) -> list[SearchResult]:
    """Search CORE (open-access academic papers with full text)."""
    results: list[SearchResult] = []
    headers = {}
    if CORE_API_KEY:
        headers["Authorization"] = f"Bearer {CORE_API_KEY}"
    params = {
        "q": query,
        "limit": min(max_results, 50),
    }
    data = await _get(
        client,
        "https://api.core.ac.uk/v3/search/works",
        params=params,
        headers=headers,
    )
    if not data:
        return results
    for w in data.get("results", []):
        url = ""
        for link in w.get("links", []):
            if link.get("type") == "download":
                url = link.get("url", "")
                break
        if not url:
            for link in w.get("links", []):
                url = link.get("url", "")
                if url:
                    break
        if not url:
            url = f"https://core.ac.uk/works/{w.get('id', '')}"
        results.append(SearchResult(
            title=_trim(w.get("title", ""), 150),
            url=url,
            source="academic:core",
            snippet=_trim(w.get("abstract", ""), 250),
            date=str(w.get("yearPublished", "")),
            filetype="pdf" if w.get("downloadUrl") else "",
            extra={
                "doi": w.get("doi", ""),
                "download_url": w.get("downloadUrl", ""),
            },
        ))
    return results[:max_results]


async def search_archive_org(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
) -> list[SearchResult]:
    """Search Internet Archive (books, papers, archived web pages)."""
    results: list[SearchResult] = []
    params = {
        "q": query,
        "output": "json",
        "rows": min(max_results, 50),
        "fl[]": "identifier,title,description,date,mediatype",
    }
    data = await _get(client, "https://archive.org/advancedsearch.php", params=params)
    if not data:
        return results
    for doc in data.get("response", {}).get("docs", []):
        ident = doc.get("identifier", "")
        results.append(SearchResult(
            title=_trim(doc.get("title", ""), 150),
            url=f"https://archive.org/details/{ident}",
            source="archive:internet_archive",
            snippet=_trim(doc.get("description", "") if isinstance(doc.get("description"), str) else " ".join(doc.get("description", [])), 250),
            date=doc.get("date", ""),
            filetype=doc.get("mediatype", ""),
        ))
    return results[:max_results]


async def search_eurlex(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = 10,
) -> list[SearchResult]:
    """Search EUR-Lex via SearXNG (European legislation)."""
    # EUR-Lex doesn't have a simple free API; use SearXNG with site filter
    site_query = f"{query} site:eur-lex.europa.eu"
    batch = await search_searxng(client, site_query, "general", 1, max_results)
    for r in batch:
        r.source = "legal:eurlex"
    return batch


async def search_qdrant(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
) -> list[SearchResult]:
    """Semantic search in local Qdrant vector database."""
    results: list[SearchResult] = []
    # Get embedding
    emb_resp = await _post(
        client,
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": query},
    )
    if not emb_resp or "embeddings" not in emb_resp:
        log.warning("  ⚠ No se pudo obtener embedding de Ollama")
        return results

    embedding = emb_resp["embeddings"][0]
    per_collection = max(3, max_results // len(QDRANT_COLLECTIONS))

    for col in QDRANT_COLLECTIONS:
        search_body = {
            "vector": {"name": "dense", "vector": embedding},
            "limit": per_collection,
            "with_payload": True,
            "with_vector": False,
        }
        data = await _post(
            client,
            f"{QDRANT_URL}/collections/{col}/points/search",
            json=search_body,
        )
        if not data or "result" not in data:
            continue
        for pt in data["result"]:
            payload = pt.get("payload", {})
            score = pt.get("score", 0)
            source_file = payload.get("source_file", "")
            text = payload.get("text", "")
            results.append(SearchResult(
                title=f"[{col}] {source_file}",
                url=f"qdrant://{col}/{pt.get('id', '')}",
                source=f"local:qdrant:{col}",
                snippet=_trim(text, 300),
                score=score,
                filetype=Path(source_file).suffix.lstrip(".") if source_file else "",
                extra={"collection": col, "chunk_index": payload.get("chunk_index", 0)},
            ))

    # Sort by score and deduplicate by source_file
    results.sort(key=lambda r: r.score, reverse=True)
    seen_files: set[str] = set()
    deduped: list[SearchResult] = []
    for r in results:
        sf = r.title
        if sf not in seen_files:
            seen_files.add(sf)
            deduped.append(r)
    return deduped[:max_results]


def search_local_files(
    query: str,
    max_results: int = DEFAULT_MAX_PER_SOURCE,
) -> list[SearchResult]:
    """Search local conocimientos/ folder by filename keyword match."""
    results: list[SearchResult] = []
    if not CONOCIMIENTOS_DIR.exists():
        return results

    keywords = [kw.lower() for kw in query.split() if len(kw) > 2]
    for root, _dirs, files in os.walk(CONOCIMIENTOS_DIR):
        for fname in files:
            name_lower = fname.lower()
            matched = sum(1 for kw in keywords if kw in name_lower)
            if matched > 0:
                fpath = Path(root) / fname
                rel = fpath.relative_to(CONOCIMIENTOS_DIR)
                results.append(SearchResult(
                    title=fname,
                    url=f"file://{fpath}",
                    source=f"local:files:{rel.parts[0] if len(rel.parts) > 1 else 'root'}",
                    snippet=f"📁 {rel.parent}",
                    score=matched / len(keywords) if keywords else 0,
                    filetype=fpath.suffix.lstrip("."),
                    extra={"size_kb": fpath.stat().st_size // 1024},
                ))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:max_results]


# ── Orchestrator ────────────────────────────────────────────────────────

SOURCES_ALL = {
    "web", "scholar", "social", "files", "openalex", "core",
    "archive", "eurlex", "qdrant", "local",
}


async def deep_search(
    query: str,
    max_per_source: int = DEFAULT_MAX_PER_SOURCE,
    filetypes: list[str] | None = None,
    lang: str = "es",
    sources: set[str] | None = None,
    pages: int = 2,
) -> list[SearchResult]:
    """Run deep search across all configured sources."""
    if filetypes is None:
        filetypes = DEFAULT_FILETYPES
    if sources is None:
        sources = SOURCES_ALL

    all_results: list[SearchResult] = []
    source_counts: dict[str, int] = {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks: dict[str, asyncio.Task] = {}

        if "web" in sources:
            tasks["🌐 Web (Google/Bing/DDG)"] = asyncio.create_task(
                search_searxng(client, query, "general", pages, max_per_source, lang)
            )
        if "scholar" in sources:
            tasks["🎓 Scholar (GScholar/PubMed/arXiv)"] = asyncio.create_task(
                search_searxng(client, query, "science", pages, max_per_source, lang)
            )
        if "social" in sources:
            tasks["💬 RRSS & Foros"] = asyncio.create_task(
                search_searxng(client, query, "social media", pages, max_per_source, lang)
            )
        if "files" in sources:
            tasks["📄 Ficheros online"] = asyncio.create_task(
                search_searxng_files(client, query, filetypes, pages, max_per_source, lang)
            )
        if "openalex" in sources:
            tasks["📚 OpenAlex (250M papers)"] = asyncio.create_task(
                search_openalex(client, query, max_per_source)
            )
        if "core" in sources:
            tasks["🔓 CORE (open access)"] = asyncio.create_task(
                search_core(client, query, max_per_source)
            )
        if "archive" in sources:
            tasks["🏛️ Internet Archive"] = asyncio.create_task(
                search_archive_org(client, query, max_per_source)
            )
        if "eurlex" in sources:
            tasks["⚖️ EUR-Lex (legislación UE)"] = asyncio.create_task(
                search_eurlex(client, query, max_per_source)
            )
        if "qdrant" in sources:
            tasks["🧠 Qdrant (RAG local)"] = asyncio.create_task(
                search_qdrant(client, query, max_per_source)
            )

        # Local files (sync, fast)
        if "local" in sources:
            local_results = search_local_files(query, max_per_source)
            log.info(f"  📁 Archivos locales             →  {len(local_results):>3} resultados")
            source_counts["📁 Archivos locales"] = len(local_results)
            all_results.extend(local_results)

        # Await all async tasks
        for label, task in tasks.items():
            try:
                results = await task
                log.info(f"  {label:<35s} →  {len(results):>3} resultados")
                source_counts[label] = len(results)
                all_results.extend(results)
            except Exception as e:
                log.warning(f"  {label:<35s} →  ❌ Error: {e}")
                source_counts[label] = 0

    return all_results, source_counts


# ── Deduplication & ranking ─────────────────────────────────────────────

def deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    """Remove duplicate URLs, keeping highest-scored version."""
    seen: dict[str, SearchResult] = {}
    for r in results:
        key = r.dedup_key
        if key not in seen or r.score > seen[key].score:
            seen[key] = r
    return list(seen.values())


def rank_results(results: list[SearchResult], query: str) -> list[SearchResult]:
    """Simple relevance ranking: boost by keyword matches + source priority."""
    keywords = [kw.lower() for kw in query.split() if len(kw) > 2]
    source_boost = {
        "local:qdrant": 2.0,
        "local:files": 1.8,
        "academic:openalex": 1.5,
        "academic:core": 1.4,
        "web:science": 1.3,
        "legal:eurlex": 1.2,
        "web:general": 1.0,
        "web:social media": 0.9,
        "archive:internet_archive": 0.8,
    }

    for r in results:
        text = f"{r.title} {r.snippet}".lower()
        kw_score = sum(1 for kw in keywords if kw in text) / max(len(keywords), 1)

        # Source type boost
        boost = 1.0
        for prefix, b in source_boost.items():
            if r.source.startswith(prefix):
                boost = b
                break

        # PDF/doc boost
        if r.filetype in ("pdf", "docx"):
            boost *= 1.1

        # Open access boost
        if r.extra.get("open_access"):
            boost *= 1.1

        # Citations boost (academic)
        cited = r.extra.get("cited_by", 0)
        if cited and cited > 0:
            import math
            boost *= 1 + math.log10(max(cited, 1)) * 0.1

        r.score = (r.score + kw_score) * boost

    results.sort(key=lambda r: r.score, reverse=True)
    return results


# ── Output formatters ───────────────────────────────────────────────────

def format_terminal(results: list[SearchResult], query: str, source_counts: dict) -> str:
    """Pretty terminal output."""
    lines = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append(f"║  🔍 DEEP SEARCH: {query[:44]:<44s} ║")
    lines.append("╠══════════════════════════════════════════════════════════════╣")

    # Source summary
    for src, count in source_counts.items():
        status = f"{count:>3} resultados" if count > 0 else "  ❌ sin resultado"
        lines.append(f"║  {src:<32s} {status:>26s} ║")
    lines.append(f"║{'─' * 60}║")
    lines.append(f"║  📊 TOTAL (deduplicado): {len(results):<35} ║")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    lines.append("")

    # Group by source type
    groups: dict[str, list[SearchResult]] = {}
    for r in results:
        # Simplify source to group
        if "qdrant" in r.source:
            group = "🧠 RAG Local (Qdrant)"
        elif "local:files" in r.source:
            group = "📁 Archivos Locales"
        elif "openalex" in r.source:
            group = "📚 OpenAlex"
        elif "core" in r.source:
            group = "🔓 CORE Open Access"
        elif "science" in r.source or "scholar" in r.source:
            group = "🎓 Académico"
        elif "eurlex" in r.source:
            group = "⚖️ Legislación UE"
        elif "archive" in r.source:
            group = "🏛️ Internet Archive"
        elif "social" in r.source:
            group = "💬 RRSS & Foros"
        elif "files:" in r.source:
            group = "📄 Ficheros Online"
        else:
            group = "🌐 Web General"
        groups.setdefault(group, []).append(r)

    for group_name, group_results in groups.items():
        lines.append(f"\n{'━' * 62}")
        lines.append(f"  {group_name} ({len(group_results)} resultados)")
        lines.append(f"{'━' * 62}")
        for i, r in enumerate(group_results, 1):
            ft_badge = f" [{r.filetype.upper()}]" if r.filetype else ""
            oa_badge = " 🔓OA" if r.extra.get("open_access") else ""
            cited = r.extra.get("cited_by", 0)
            cite_badge = f" 📖{cited}citas" if cited else ""
            pdf_note = ""
            if r.extra.get("pdf_url"):
                pdf_note = f"\n       📥 PDF: {r.extra['pdf_url'][:80]}"
            date_str = f" ({r.date})" if r.date else ""

            lines.append(f"\n  {i:>3}. {r.title[:75]}{ft_badge}{oa_badge}{cite_badge}{date_str}")
            if r.engine:
                lines.append(f"       🔎 {r.engine}")
            lines.append(f"       🔗 {r.url[:90]}")
            if r.snippet:
                lines.append(f"       📝 {r.snippet[:150]}")
            if pdf_note:
                lines.append(pdf_note)

    lines.append(f"\n{'═' * 62}")
    lines.append(f"  Búsqueda completada: {len(results)} resultados únicos")
    lines.append(f"{'═' * 62}\n")

    return "\n".join(lines)


def export_csv(results: list[SearchResult], filepath: str):
    """Export results to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "title", "url", "source", "engine", "filetype",
            "snippet", "score", "date", "cited_by", "open_access", "pdf_url",
        ])
        for i, r in enumerate(results, 1):
            writer.writerow([
                i, r.title, r.url, r.source, r.engine, r.filetype,
                r.snippet, f"{r.score:.3f}", r.date,
                r.extra.get("cited_by", ""),
                r.extra.get("open_access", ""),
                r.extra.get("pdf_url", ""),
            ])
    log.info(f"  📁 Exportado a {filepath} ({len(results)} filas)")


def export_json(results: list[SearchResult], filepath: str):
    """Export results to JSON."""
    data = [asdict(r) for r in results]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"  📁 Exportado a {filepath} ({len(results)} entradas)")


# ── CLI ─────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="🔍 Seedy — Búsqueda Profunda de Documentación por Palabras",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s "ganadería ovina IoT"
  %(prog)s "porcino digital twin" --max 50
  %(prog)s "capón extensivo" --filetypes pdf,docx
  %(prog)s "RFID livestock" --lang en
  %(prog)s "vacuno normativa" --export resultados.csv
  %(prog)s "sensor IoT granja" --solo-fuentes web,academic,qdrant
  %(prog)s "ganadería" --pages 3
        """,
    )
    parser.add_argument(
        "query",
        help="Palabras clave de búsqueda (entre comillas si son varias)",
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=DEFAULT_MAX_PER_SOURCE,
        dest="max_per_source",
        help=f"Máximo resultados por fuente (default: {DEFAULT_MAX_PER_SOURCE})",
    )
    parser.add_argument(
        "--filetypes", "-f",
        default=",".join(DEFAULT_FILETYPES),
        help=f"Tipos de archivo a buscar, separados por coma (default: {','.join(DEFAULT_FILETYPES)})",
    )
    parser.add_argument(
        "--lang", "-l",
        default="es",
        help="Idioma de búsqueda: es, en, fr, all (default: es)",
    )
    parser.add_argument(
        "--export", "-e",
        default="",
        help="Ruta para exportar resultados (.csv o .json)",
    )
    parser.add_argument(
        "--solo-fuentes", "-s",
        default="",
        help=f"Solo buscar en estas fuentes (separadas por coma). Disponibles: {','.join(sorted(SOURCES_ALL))}",
    )
    parser.add_argument(
        "--pages", "-p",
        type=int,
        default=2,
        help="Páginas a recorrer en SearXNG (default: 2)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar detalles de depuración",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    query = args.query
    filetypes = [ft.strip() for ft in args.filetypes.split(",") if ft.strip()]
    sources = set(args.solo_fuentes.split(",")) if args.solo_fuentes else None
    if sources:
        # Map friendly names
        source_aliases = {
            "web": "web", "academic": "scholar", "scholar": "scholar",
            "social": "social", "rrss": "social", "foros": "social",
            "files": "files", "ficheros": "files",
            "openalex": "openalex", "core": "core",
            "archive": "archive", "wayback": "archive",
            "eurlex": "eurlex", "legal": "eurlex",
            "qdrant": "qdrant", "rag": "qdrant",
            "local": "local",
        }
        sources = {source_aliases.get(s.strip().lower(), s.strip().lower()) for s in sources}

    log.info(f"\n🔍 Buscando: \"{query}\"")
    log.info(f"   Idioma: {args.lang} | Max/fuente: {args.max_per_source} | Páginas: {args.pages}")
    if sources:
        log.info(f"   Fuentes: {', '.join(sorted(sources))}")
    log.info("")

    t0 = time.time()
    all_results, source_counts = await deep_search(
        query=query,
        max_per_source=args.max_per_source,
        filetypes=filetypes,
        lang=args.lang,
        sources=sources,
        pages=args.pages,
    )

    # Deduplicate and rank
    unique = deduplicate(all_results)
    ranked = rank_results(unique, query)
    elapsed = time.time() - t0

    # Display
    output = format_terminal(ranked, query, source_counts)
    print(output)
    log.info(f"  ⏱️ Tiempo total: {elapsed:.1f}s")

    # Export
    if args.export:
        if args.export.endswith(".json"):
            export_json(ranked, args.export)
        else:
            export_csv(ranked, args.export)


if __name__ == "__main__":
    asyncio.run(main())
