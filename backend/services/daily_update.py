"""Seedy Backend — Job de actualización diaria de conocimientos.

Circuito B (offline): Busca novedades por temas → filtra → chunkea → indexa en fresh_web.
Diseñado para ejecutarse como cron/APScheduler cada 24h.

Uso:
    python -m services.daily_update          # Ejecutar actualización completa
    python -m services.daily_update --dry    # Solo buscar, no indexar
    python -m services.daily_update --topic avicultura  # Solo un vertical
"""

import asyncio
import hashlib
import logging
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

import httpx

# Añadir backend/ al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from services.embeddings import embed_texts, close as close_embeddings
from services.rag import get_qdrant, ensure_collections, FRESH_WEB_COLLECTION, close as close_qdrant
from ingestion.chunker import chunk_text, compute_sparse_vector
from services.quality_gate import validate_chunk
from qdrant_client.models import PointStruct, SparseVector, Filter, FieldCondition, MatchValue

# Cross-dedup: reutilizar la BD del pipeline modular para evitar duplicados entre ambos sistemas.
# Se accede vía SQLite directamente (pipelines/ no está dentro del contenedor Docker).
_INGEST_STATE_DB = os.environ.get("INGEST_STATE_DB", "/app/data/ingest_state.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Umbral de autoridad para crawl profundo (las mejores fuentes merecen texto completo)
DEEP_CRAWL_MIN_AUTHORITY = 0.7
DEEP_CRAWL_TIMEOUT = 30.0
DEEP_CRAWL_MAX_TEXT = 8000  # chars máximo por artículo crawleado


# ── Source Authority Scores ──────────────────────────
# 1.0 = normativa oficial, organismos públicos, papers revisados
# 0.9 = universidades, centros de investigación, asociaciones oficiales
# 0.7 = medios sectoriales buenos
# 0.5 = blogs técnicos
# 0.3 = marketing comercial
# 0.1 = foros / ruido

SOURCE_AUTHORITY = {
    # 1.0 — Normativa oficial
    "boe.es": 1.0,
    "eur-lex.europa.eu": 1.0,
    "efsa.europa.eu": 1.0,
    "mapa.gob.es": 1.0,
    "fao.org": 1.0,
    "oie.int": 1.0,
    "woah.org": 1.0,

    # 0.9 — Investigación y asociaciones oficiales
    "inia.csic.es": 0.9,
    "irta.cat": 0.9,
    "neiker.eus": 0.9,
    "cita-aragon.es": 0.9,
    "pubmed.ncbi.nlm.nih.gov": 0.9,
    "sciencedirect.com": 0.9,
    "springer.com": 0.9,
    "mdpi.com": 0.9,
    "nature.com": 0.9,
    "poultry.extension.org": 0.9,
    "uco.es": 0.9,
    "upm.es": 0.9,
    "unizar.es": 0.9,

    # 0.7 — Medios sectoriales
    "3tres3.com": 0.7,
    "avicultura.com": 0.7,
    "agroinformacion.com": 0.7,
    "eurocarne.com": 0.7,
    "interempresas.net": 0.7,
    "agronewscastillayleon.com": 0.7,
    "agrodigital.com": 0.7,
    "porcinews.com": 0.7,
    "avicultura.info": 0.7,
    "razanostra.org": 0.7,

    # 0.5 — Blogs técnicos
    "backyardchickens.com": 0.5,
    "seleccionesavicolas.com": 0.5,
    "thepigsite.com": 0.5,
    "thepoultrysite.com": 0.5,

    # 0.3 — Marketing
    "hendrix-genetics.com": 0.3,
    "aviagen.com": 0.3,
    "hypor.com": 0.3,
    "topigs.com": 0.3,
}

DEFAULT_AUTHORITY = 0.4


# ── Watchlist: queries persistentes por vertical ─────
WATCHLIST = {
    "avicultura": {
        "frequency_hours": 48,
        "queries": [
            "slow-growing broiler genetics study 2025 2026",
            "free-range poultry welfare regulation Europe",
            "capon production study quality meat",
            "razas avícolas autóctonas España conservación",
            "Label Rouge poulet qualité France",
            "poultry breeding heritage breeds genetic diversity",
            "avicultura extensiva normativa España",
            "poultry precision farming sensor technology",
        ],
    },
    "porcino": {
        "frequency_hours": 48,
        "queries": [
            "iberian pig genetics genomic selection",
            "outdoor pig production welfare extensivo",
            "swine biosecurity PRRS ASF Europe update",
            "porcino extensivo ibérico España",
            "pig welfare regulation EU update",
            "pork market price Spain Europe",
        ],
    },
    "bovino": {
        "frequency_hours": 72,
        "queries": [
            "beef cattle crossbreeding Spain extensivo",
            "suckler cow extensive production dehesa",
            "razas bovinas autóctonas España conservación",
            "cattle inbreeding local breeds genetic management",
        ],
    },
    "normativa": {
        "frequency_hours": 24,
        "queries": [
            "site:boe.es ganadería bienestar animal",
            "site:mapa.gob.es porcino avicultura extensivo",
            "EU animal welfare regulation poultry pig update 2025 2026",
            "EFSA poultry welfare scientific opinion",
            "nueva normativa bienestar animal España ganadería",
        ],
    },
    "genetica": {
        "frequency_hours": 72,
        "queries": [
            "livestock genomic selection breeding program",
            "genetic diversity local breeds conservation program",
            "animal breeding EPD GEBV new methodology",
        ],
    },
    "iot_sensores": {
        "frequency_hours": 72,
        "queries": [
            "precision livestock farming sensor IoT poultry pig",
            "smart farming automation Europe startup",
            "livestock monitoring AI computer vision",
        ],
    },
    "papers": {
        "frequency_hours": 72,
        "queries": [
            "site:pubmed.ncbi.nlm.nih.gov poultry genetics capon slow-growing",
            "site:sciencedirect.com poultry meat quality free-range",
            "poultry science capon meat quality study",
        ],
    },
}


# ── Utilidades ───────────────────────────────────────

def get_domain(url: str) -> str:
    """Extrae el dominio de una URL."""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else ""


def get_source_authority(url: str) -> float:
    """Retorna el score de autoridad para una URL."""
    domain = get_domain(url)
    # Buscar coincidencia exacta y parcial
    for pattern, score in SOURCE_AUTHORITY.items():
        if pattern in domain:
            return score
    return DEFAULT_AUTHORITY


def content_hash(text: str) -> str:
    """Hash del contenido para deduplicación."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


async def deep_crawl_url(url: str) -> str | None:
    """Crawlea una URL con crawl4ai y devuelve el texto completo del artículo.

    Solo para fuentes con autoridad >= 0.7 (medios sectoriales, investigación, normativa).
    Usa crawl4ai para obtener el artículo real, no solo el snippet de SearXNG.
    """
    settings = get_settings()
    crawl4ai_url = settings.crawl4ai_url

    if not crawl4ai_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=DEEP_CRAWL_TIMEOUT) as client:
            resp = await client.post(
                f"{crawl4ai_url}/crawl",
                json={
                    "urls": [url],
                    "priority": 5,
                    "word_count_threshold": 50,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Extraer resultado del crawl
        result = data.get("result") or data.get("results", [{}])
        if isinstance(result, list):
            result = result[0] if result else {}

        # crawl4ai devuelve markdown y/o texto limpio
        text = (
            result.get("markdown", "")
            or result.get("cleaned_text", "")
            or result.get("text", "")
        )

        if not text or len(text) < 100:
            return None

        # Limpiar y truncar
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > DEEP_CRAWL_MAX_TEXT:
            text = text[:DEEP_CRAWL_MAX_TEXT]

        return text

    except Exception as e:
        logger.debug(f"  Deep crawl falló para {url[:60]}: {e}")
        return None


async def search_searxng(query: str, max_results: int = 8) -> list[dict]:
    """Busca en SearXNG y retorna resultados con metadatos."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.searxng_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general,science",
                    "language": "es",
                    "safesearch": 1,
                    "time_range": "month",  # Último mes — frescura
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", [])[:max_results]:
            url = item.get("url", "")
            results.append({
                "title": item.get("title", ""),
                "url": url,
                "content": item.get("content", ""),
                "published_date": item.get("publishedDate", ""),
                "source_authority": get_source_authority(url),
                "domain": get_domain(url),
            })
        return results

    except Exception as e:
        logger.warning(f"SearXNG falló para '{query[:50]}': {e}")
        return []


def filter_results(results: list[dict], min_authority: float = 0.3) -> list[dict]:
    """Filtra resultados por calidad: autoridad mínima, contenido no vacío, dedup."""
    seen_hashes = set()
    filtered = []

    for r in results:
        # Filtro de autoridad
        if r["source_authority"] < min_authority:
            logger.debug(f"  Filtrado por autoridad ({r['source_authority']}): {r['url']}")
            continue

        # Filtro de contenido vacío
        text = f"{r['title']} {r['content']}".strip()
        if len(text) < 50:
            continue

        # Deduplicación por hash
        h = content_hash(text)
        if h in seen_hashes:
            logger.debug(f"  Duplicado filtrado: {r['url']}")
            continue
        seen_hashes.add(h)

        filtered.append(r)

    return filtered


async def check_existing_hashes(hashes: list[str]) -> set[str]:
    """Verifica qué hashes ya existen en Qdrant O en la BD del pipeline modular."""
    client = get_qdrant()
    existing = set()

    # Cross-dedup: comprobar BD del pipeline modular (pipelines/ingest/)
    if Path(_INGEST_STATE_DB).exists():
        try:
            import sqlite3 as _sqlite3
            conn = _sqlite3.connect(_INGEST_STATE_DB, timeout=3)
            for h in hashes:
                row = conn.execute("SELECT 1 FROM seen_hashes WHERE hash = ?", (h,)).fetchone()
                if row:
                    existing.add(h)
            conn.close()
        except Exception as e:
            logger.debug(f"Cross-dedup con pipeline DB falló: {e}")

    # Dedup contra Qdrant fresh_web
    try:
        for h in hashes:
            if h in existing:
                continue
            results = client.scroll(
                collection_name=FRESH_WEB_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="content_hash", match=MatchValue(value=h))]
                ),
                limit=1,
            )
            if results[0]:  # points list
                existing.add(h)
    except Exception:
        pass

    return existing


async def index_fresh_results(results: list[dict], topic: str, batch_size: int = 5):
    """Indexa resultados filtrados en la colección fresh_web con metadatos de frescura.

    Para fuentes con autoridad >= 0.7, intenta un deep crawl con crawl4ai para
    obtener el artículo completo en vez del snippet de SearXNG (~200 chars).
    El texto completo se chunkea para mejor retrieval.
    """
    client = get_qdrant()
    now = datetime.now(timezone.utc).isoformat()
    total = 0

    # Fase 1: Deep crawl para fuentes de alta autoridad
    deep_crawled = 0
    for result in results:
        if result["source_authority"] >= DEEP_CRAWL_MIN_AUTHORITY:
            full_text = await deep_crawl_url(result["url"])
            if full_text and len(full_text) > len(result.get("content", "")):
                result["content"] = full_text
                result["_deep_crawled"] = True
                deep_crawled += 1
    if deep_crawled:
        logger.info(f"  🕷️  Deep crawl exitoso: {deep_crawled}/{len(results)} artículos completos")

    # Fase 2: Indexar (chunkeando textos largos de deep crawl)
    all_items = []  # (text, result) pairs ready to index
    quality_rejected = 0
    for result in results:
        text = f"{result['title']}\n{result['content']}"
        if result.get("_deep_crawled") and len(text) > 1200:
            # Chunkear artículos largos
            chunks = chunk_text(text, chunk_size=800, overlap=150)
            for i, chunk in enumerate(chunks):
                # Quality gate: validar cada chunk antes de indexar
                passed, score, reasons = validate_chunk(
                    chunk, collection="fresh_web", min_quality=0.20
                )
                if passed:
                    all_items.append((chunk, result, i))
                else:
                    quality_rejected += 1
        else:
            passed, score, reasons = validate_chunk(
                text, collection="fresh_web", min_quality=0.20
            )
            if passed:
                all_items.append((text, result, 0))
            else:
                quality_rejected += 1

    if quality_rejected:
        logger.info(f"  ⚠ Quality Gate: {quality_rejected} chunks rechazados de {len(results)} results")

    for batch_start in range(0, len(all_items), batch_size):
        batch = all_items[batch_start:batch_start + batch_size]

        texts = [item[0] for item in batch]

        try:
            embeddings = await embed_texts(texts)
        except Exception as e:
            logger.error(f"Error generando embeddings: {e}")
            continue

        points = []
        for i, ((text, result, chunk_idx), emb) in enumerate(zip(batch, embeddings)):
            c_hash = content_hash(text)
            point_id = str(uuid5(NAMESPACE_URL, f"fresh:{c_hash}"))

            vector_data: dict = {"dense": emb}
            sparse_idx, sparse_val = compute_sparse_vector(text)
            if sparse_idx:
                vector_data["bm25"] = SparseVector(indices=sparse_idx, values=sparse_val)

            pub_date = result.get("published_date", "")
            if not pub_date:
                pub_date = now

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector_data,
                    payload={
                        "text": text,
                        "source_file": result["domain"],
                        "chunk_index": chunk_idx,
                        "section": result["title"],
                        "collection": FRESH_WEB_COLLECTION,
                        "document_type": "web",
                        "published_at": pub_date,
                        "discovered_at": now,
                        "source_authority": result["source_authority"],
                        "topic": topic,
                        "domain": result["domain"],
                        "url": result["url"],
                        "content_hash": c_hash,
                        "freshness_tier": "fresh_web",
                        "is_regulatory": result["source_authority"] >= 1.0,
                        "is_scientific": result["source_authority"] >= 0.9,
                        "deep_crawled": result.get("_deep_crawled", False),
                    },
                )
            )

        try:
            client.upsert(collection_name=FRESH_WEB_COLLECTION, points=points)
            total += len(points)
        except Exception as e:
            logger.error(f"Error indexando en Qdrant: {e}")

    return total


async def expire_old_content(max_age_days: int = 30):
    """Elimina contenido de fresh_web más antiguo que max_age_days (default 30d)."""
    client = get_qdrant()
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()

    try:
        # Scroll all points and check discovered_at
        deleted = 0
        offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=FRESH_WEB_COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
            )
            if not points:
                break

            to_delete = []
            for p in points:
                discovered = p.payload.get("discovered_at", "")
                if discovered and discovered < cutoff_iso:
                    to_delete.append(p.id)

            if to_delete:
                client.delete(
                    collection_name=FRESH_WEB_COLLECTION,
                    points_selector=to_delete,
                )
                deleted += len(to_delete)

            if next_offset is None:
                break
            offset = next_offset

        if deleted:
            logger.info(f"🗑️  Expirados {deleted} documentos antiguos (>{max_age_days} días)")

    except Exception as e:
        logger.error(f"Error expirando contenido: {e}")


# ── Ejecución principal ──────────────────────────────

async def run_daily_update(target_topic: str | None = None, dry_run: bool = False):
    """
    Ejecuta la actualización diaria completa.
    
    1. Para cada vertical en la watchlist:
       - Lanza queries persistentes a SearXNG
       - Filtra por autoridad, calidad y deduplicación
       - Indexa novedades en fresh_web con metadata de frescura
    2. Expira contenido viejo (>60 días)
    """
    logger.info("🔄 Iniciando actualización diaria de conocimientos...")

    # Asegurar colección fresh_web existe
    embed_dim = 1024
    try:
        from services.embeddings import get_embedding_dimension
        embed_dim = await get_embedding_dimension()
    except Exception:
        pass
    await ensure_collections(embed_dim=embed_dim)

    grand_total = 0
    grand_filtered = 0
    grand_indexed = 0

    topics = [target_topic] if target_topic else list(WATCHLIST.keys())

    for topic in topics:
        if topic not in WATCHLIST:
            logger.warning(f"Vertical '{topic}' no existe en la watchlist")
            continue

        config = WATCHLIST[topic]
        queries = config["queries"]
        logger.info(f"\n📡 Vertical: {topic} ({len(queries)} queries)")

        topic_results = []

        for q in queries:
            results = await search_searxng(q, max_results=6)
            logger.info(f"  🔍 '{q[:50]}...' → {len(results)} resultados")
            topic_results.extend(results)

        grand_total += len(topic_results)

        # Filtrar
        filtered = filter_results(topic_results, min_authority=0.3)
        logger.info(f"  📋 Filtrados: {len(filtered)}/{len(topic_results)} pasan calidad")
        grand_filtered += len(filtered)

        if dry_run:
            for r in filtered[:5]:
                logger.info(f"    [DRY] {r['source_authority']:.1f} | {r['domain']} | {r['title'][:60]}")
            continue

        if not filtered:
            continue

        # Dedup contra existentes
        hashes = [content_hash(f"{r['title']} {r['content']}") for r in filtered]
        existing = await check_existing_hashes(hashes)
        new_results = [r for r, h in zip(filtered, hashes) if h not in existing]
        logger.info(f"  🆕 Nuevos: {len(new_results)} (ya existían: {len(filtered) - len(new_results)})")

        if new_results:
            count = await index_fresh_results(new_results, topic)
            grand_indexed += count
            logger.info(f"  ✅ Indexados: {count} chunks en fresh_web")

            # Cross-dedup: registrar URLs y hashes en BD del pipeline modular
            if Path(_INGEST_STATE_DB).exists():
                try:
                    import sqlite3 as _sqlite3
                    conn = _sqlite3.connect(_INGEST_STATE_DB, timeout=3)
                    now_iso = datetime.now(timezone.utc).isoformat()
                    for r in new_results:
                        url = r["url"]
                        h = content_hash(f"{r['title']} {r['content']}")
                        conn.execute(
                            "INSERT OR IGNORE INTO seen_urls (url, source_name, first_seen, last_seen) VALUES (?, ?, ?, ?)",
                            (url, f"daily_update/{topic}", now_iso, now_iso),
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO seen_hashes (hash, url, first_seen) VALUES (?, ?, ?)",
                            (h, url, now_iso),
                        )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.debug(f"Cross-dedup sync falló: {e}")

    if not dry_run:
        # Expirar contenido viejo (>30 días)
        await expire_old_content(max_age_days=30)

    logger.info(f"\n🎉 Actualización completa:")
    logger.info(f"   Total resultados: {grand_total}")
    logger.info(f"   Filtrados (calidad): {grand_filtered}")
    logger.info(f"   Indexados (nuevos): {grand_indexed}")

    return grand_indexed


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Actualización diaria de conocimientos")
    parser.add_argument("--dry", action="store_true", help="Solo buscar, no indexar")
    parser.add_argument("--topic", type=str, default=None, help="Solo un vertical")
    args = parser.parse_args()

    count = await run_daily_update(target_topic=args.topic, dry_run=args.dry)

    await close_embeddings()
    close_qdrant()


if __name__ == "__main__":
    asyncio.run(main())
