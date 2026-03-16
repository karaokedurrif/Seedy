#!/usr/bin/env python3
"""
Seedy — Pipeline de autoingesta diaria.

Orquesta todo el proceso:
  1. Fetch: descarga RSS y páginas web
  2. Dedup: filtra URLs y contenido ya visto
  3. Parse: extrae texto limpio
  4. Score: puntúa fiabilidad + relevancia
  5. Index: chunkea, embebe e indexa en Qdrant
  6. Brief: genera resumen diario

Uso:
    python -m pipelines.ingest.run_daily
    python -m pipelines.ingest.run_daily --dry-run
    python -m pipelines.ingest.run_daily --sources custom_sources.yaml
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from pipelines.ingest.settings import get_settings
from pipelines.ingest.state_db import StateDB
from pipelines.ingest.fetch import fetch_all_sources, save_raw
from pipelines.ingest.parse import fetch_and_parse_full
from pipelines.ingest.dedup import deduplicate, deduplicate_by_content
from pipelines.ingest.score import classify_and_score
from pipelines.ingest.qdrant_index import ensure_collections, index_item, close as close_qdrant
from pipelines.ingest.daily_brief import generate_brief

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_pipeline(sources_file: str | None = None, dry_run: bool = False):
    """Ejecuta el pipeline completo de autoingesta."""
    settings = get_settings()
    db = StateDB(settings.db_path)
    start_time = datetime.now(timezone.utc)

    logger.info("=" * 60)
    logger.info("🚀 Seedy Autoingesta — Inicio")
    logger.info(f"   Hora: {start_time.isoformat()}")
    logger.info("=" * 60)

    try:
        # ── 1. Fetch ─────────────────────────────────
        logger.info("\n📡 Paso 1: Descargando fuentes...")
        items = fetch_all_sources(sources_file)

        if not items:
            logger.warning("No se obtuvieron items de ninguna fuente")
            return

        # ── 2. Dedup URLs ────────────────────────────
        logger.info("\n🔍 Paso 2: Deduplicando por URL...")
        items = deduplicate(items, db)

        if not items:
            logger.info("Todos los items ya fueron procesados anteriormente")
            generate_brief(db)
            return

        # ── 3. Parse + Dedup contenido ───────────────
        logger.info("\n📄 Paso 3: Parseando contenido...")
        texts: dict[str, str] = {}
        for item in items:
            url = item.get("canonical_url", item.get("url", ""))
            try:
                text = fetch_and_parse_full(item)
                if text and len(text.strip()) >= 50:
                    texts[url] = text
            except Exception as e:
                logger.warning(f"  Error parseando {url}: {e}")

        logger.info(f"  Parseados con contenido: {len(texts)}/{len(items)}")

        items = deduplicate_by_content(items, texts, db)

        if not items:
            logger.info("No hay contenido nuevo tras deduplicación")
            generate_brief(db)
            return

        # ── 4. Score ─────────────────────────────────
        logger.info("\n📊 Paso 4: Scoring relevancia + fiabilidad...")
        items = classify_and_score(items)

        # ── 5. Guardar raw + marcar vistos ───────────
        logger.info("\n💾 Paso 5: Guardando raw y marcando vistos...")
        for item in items:
            url = item.get("canonical_url", item.get("url", ""))
            raw_path = save_raw(item, settings.data_dir)
            item["raw_path"] = raw_path

            # Marcar como visto en DB
            db.mark_url_seen(url, item.get("source_name", ""))
            if "text_hash" in item:
                db.mark_hash_seen(item["text_hash"], url)

        # ── 6. Index en Qdrant ───────────────────────
        to_index = [i for i in items if i.get("status") == "index"]
        to_quarantine = [i for i in items if i.get("status") == "quarantine"]
        rejected = [i for i in items if i.get("status") == "rejected"]

        logger.info(f"\n📥 Paso 6: Indexando {len(to_index)} items...")

        if not dry_run and to_index:
            # Asegurar colecciones
            from pipelines.ingest.embed import get_embedding_dimension
            embed_dim = await get_embedding_dimension()
            await ensure_collections(embed_dim)

            for item in to_index:
                url = item.get("canonical_url", item.get("url", ""))
                title = item.get("title", "")
                try:
                    n_chunks = await index_item(item, embed_dim)
                    doc_id = db.add_doc(
                        url=url,
                        title=title,
                        source_name=item.get("source_name", ""),
                        score=item.get("score", 0),
                        status="indexed",
                        collection=item.get("domain", "estrategia"),
                        raw_path=item.get("raw_path"),
                    )
                    db.update_doc_indexed(doc_id, item.get("domain", "estrategia"), n_chunks)
                    logger.info(f"  ✅ {title[:50]} → {n_chunks} chunks")
                except Exception as e:
                    logger.error(f"  ❌ Error indexando {title[:50]}: {e}")
                    doc_id = db.add_doc(
                        url=url,
                        title=title,
                        source_name=item.get("source_name", ""),
                        score=item.get("score", 0),
                        status="error",
                        raw_path=item.get("raw_path"),
                    )
                    db.update_doc_error(doc_id, str(e))
        elif dry_run:
            logger.info("  [DRY RUN] Saltando indexación")
            for item in to_index:
                logger.info(f"  → Indexaría: [{item['score']:.0f}] {item.get('title', '')[:60]}")

        # Registrar cuarentena
        for item in to_quarantine:
            db.add_doc(
                url=item.get("canonical_url", item.get("url", "")),
                title=item.get("title", ""),
                source_name=item.get("source_name", ""),
                score=item.get("score", 0),
                status="quarantine",
                raw_path=item.get("raw_path"),
            )

        # Registrar rechazados
        for item in rejected:
            db.add_doc(
                url=item.get("canonical_url", item.get("url", "")),
                title=item.get("title", ""),
                source_name=item.get("source_name", ""),
                score=item.get("score", 0),
                status="rejected",
            )

        # ── 7. Daily brief ───────────────────────────
        logger.info("\n📝 Paso 7: Generando daily brief...")
        brief_path = generate_brief(db)

        # ── Resumen final ────────────────────────────
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        stats = db.get_today_stats()
        logger.info("\n" + "=" * 60)
        logger.info("✅ Autoingesta completada")
        logger.info(f"   Duración: {elapsed:.1f}s")
        logger.info(f"   Indexados: {stats.get('indexed', 0)}")
        logger.info(f"   Cuarentena: {stats.get('quarantine', 0)}")
        logger.info(f"   Rechazados: {stats.get('rejected', 0)}")
        logger.info(f"   Errores: {stats.get('error', 0)}")
        logger.info(f"   Brief: {brief_path}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error fatal en pipeline: {e}", exc_info=True)
        raise
    finally:
        close_qdrant()
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Pipeline de autoingesta diaria Seedy")
    parser.add_argument(
        "--sources", type=str, default=None,
        help="Archivo sources.yaml personalizado",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Ejecuta sin indexar (solo fetch, parse, score)",
    )
    args = parser.parse_args()

    asyncio.run(run_pipeline(sources_file=args.sources, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
