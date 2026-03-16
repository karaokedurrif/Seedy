#!/usr/bin/env python3
"""
promote_quarantine.py  –  Re-evalúa artículos en cuarentena con los nuevos umbrales/keywords
y promueve a indexados los que pasan el nuevo score_threshold.

  # Dry-run (solo muestra qué se haría)
  python3 promote_quarantine.py

  # Ejecutar la promoción
  python3 promote_quarantine.py --apply
"""

import asyncio
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# Asegurar que los módulos del pipeline se encuentren
sys.path.insert(0, str(Path(__file__).parent))

from pipelines.ingest.settings import get_settings
from pipelines.ingest.score import score_item
from pipelines.ingest.qdrant_index import (
    get_qdrant, ensure_collections, index_item, close as close_qdrant,
    DOMAIN_TO_COLLECTION,
)
from pipelines.ingest.embed import get_embedding_dimension

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def get_embed_dim() -> int:
    """Obtener dimensión del modelo de embedding."""
    try:
        return await get_embedding_dimension()
    except Exception:
        return 1024  # fallback


async def main():
    parser = argparse.ArgumentParser(description="Promover artículos de cuarentena")
    parser.add_argument("--apply", action="store_true", help="Ejecutar la promoción (sin esto = dry run)")
    args = parser.parse_args()

    settings = get_settings()
    db_path = settings.db_path

    logger.info(f"📋 DB: {db_path}")
    logger.info(f"📊 Nuevo umbral: score >= {settings.score_threshold}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Buscar artículos en cuarentena con score >= nuevo umbral
    rows = conn.execute(
        "SELECT id, url, title, source_name, score, raw_path, status "
        "FROM docs WHERE status = 'quarantine' AND score >= ? "
        "ORDER BY score DESC",
        (settings.score_threshold,),
    ).fetchall()

    logger.info(f"📦 Artículos en cuarentena con score >= {settings.score_threshold}: {len(rows)}")

    if not rows:
        logger.info("✅ Nada que promover")
        conn.close()
        return

    # Mostrar candidatos
    for row in rows:
        logger.info(f"  ({row['score']:.0f}pts) {row['source_name']:20s} | {row['title'][:70]}")

    if not args.apply:
        logger.info(f"\n⚠️  Dry run. Usa --apply para promover {len(rows)} artículos a Qdrant.")
        conn.close()
        return

    # ── Promover: indexar en Qdrant ──
    logger.info(f"\n🚀 Promoviendo {len(rows)} artículos...")

    # Adaptar URLs de Qdrant a localhost
    settings.qdrant_url = settings.qdrant_url.replace("qdrant:6333", "localhost:6333")
    settings.ollama_url = settings.ollama_url.replace("ollama:11434", "localhost:11434")

    embed_dim = await get_embed_dim()
    await ensure_collections(embed_dim)

    promoted = 0
    errors = 0

    for row in rows:
        doc_id = row["id"]
        raw_path = row["raw_path"]
        title = row["title"]

        # Leer texto raw
        if not raw_path or not Path(raw_path).exists():
            logger.warning(f"  ⚠ Archivo no encontrado: {raw_path} — saltando {title[:50]}")
            errors += 1
            continue

        text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
        if len(text.strip()) < 50:
            logger.warning(f"  ⚠ Texto muy corto ({len(text)} chars) — saltando {title[:50]}")
            errors += 1
            continue

        # Re-evaluar con nuevos keywords
        item = {
            "title": title,
            "parsed_text": text,
            "reliability": row["score"] - 0,  # original reliability desconocida, usar score total
            "source_name": row["source_name"],
            "url": row["url"],
            "canonical_url": row["url"],
            "score": row["score"],
        }

        # Re-scoring con nuevos keywords
        new_score, domain = score_item(item)
        item["score"] = new_score
        item["domain"] = domain

        if new_score < settings.score_threshold:
            logger.info(f"  ⏸ Re-scored {new_score:.0f} < {settings.score_threshold} — sigue en cuarentena: {title[:50]}")
            continue

        collection = DOMAIN_TO_COLLECTION.get(domain, "estrategia")

        try:
            n_chunks = await index_item(item, embed_dim)
            # Actualizar DB
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE docs SET status = 'indexed', collection = ?, chunks = ?, indexed_at = ?, score = ? WHERE id = ?",
                (collection, n_chunks, now, new_score, doc_id),
            )
            conn.commit()
            promoted += 1
            logger.info(f"  ✅ [{new_score:.0f}pts] {domain:12s} → {collection:15s} ({n_chunks} chunks) | {title[:50]}")
        except Exception as e:
            logger.error(f"  ❌ Error indexando {title[:50]}: {e}")
            errors += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Promoción completada")
    logger.info(f"   Promovidos: {promoted}")
    logger.info(f"   Errores: {errors}")
    logger.info(f"   Siguen cuarentena: {len(rows) - promoted - errors}")
    logger.info(f"{'='*60}")

    conn.close()
    close_qdrant()


if __name__ == "__main__":
    asyncio.run(main())
