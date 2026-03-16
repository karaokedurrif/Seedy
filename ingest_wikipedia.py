#!/usr/bin/env python3
"""
Seedy — Ingestión de artículos Wikipedia (ES + FR/EN/IT/DE) en Qdrant.

Lee los JSONL de wikipedia_articles/ y los indexa en las colecciones
Qdrant adecuadas según su categoría.

Uso:
    python ingest_wikipedia.py              # Indexar todos los artículos
    python ingest_wikipedia.py --reset      # Borrar colecciones Wikipedia y reindexar
    python ingest_wikipedia.py --dry-run    # Solo contar, no indexar
"""

import os
import sys
import json
import argparse
import logging
import asyncio
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

# Apuntar a servicios Docker en localhost
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QDRANT_HOST", "localhost")

# Añadir backend/ al path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from config import get_settings
from services.embeddings import embed_texts, get_embedding_dimension, close as close_embeddings
from services.rag import get_qdrant, ensure_collections, close as close_qdrant
from ingestion.chunker import chunk_text, compute_sparse_vector
from qdrant_client.models import PointStruct, SparseVector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Mapeo categoría Wikipedia → colección Qdrant ──────────────────────
CATEGORY_TO_COLLECTION = {
    # ES categories
    "avicultura":    "avicultura",
    "genetica":      "genetica",
    "normativa":     "normativa",
    "nutricion":     "nutricion",
    "ovino_caprino": "genetica",
    "porcino":       "genetica",
    "sanidad":       "nutricion",
    "tecnologia":    "iot_hardware",
    "vacuno":        "genetica",
    "en_breeds":     "genetica",
    # Multilang categories
    "fr_breeds":     "genetica",
    "it_breeds":     "genetica",
    "de_breeds":     "genetica",
}

WIKI_DIR = Path(__file__).parent / "wikipedia_articles"
WIKI_FILES = [
    WIKI_DIR / "wiki_articles_raw.jsonl",
    WIKI_DIR / "wiki_articles_multilang.jsonl",
]


def load_articles() -> list[dict]:
    """Carga todos los artículos de los JSONL de Wikipedia."""
    articles = []
    for fpath in WIKI_FILES:
        if not fpath.exists():
            logger.warning(f"Archivo no encontrado: {fpath}")
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                art = json.loads(line)
                # Filtrar artículos vacíos
                if art.get("text", "").strip():
                    articles.append(art)
    return articles


async def ingest_articles(
    articles: list[dict],
    chunk_size: int = 1500,
    chunk_overlap: int = 300,
    batch_size: int = 10,
    dry_run: bool = False,
) -> dict[str, int]:
    """Indexa los artículos en Qdrant según su categoría."""
    client = get_qdrant()
    stats: dict[str, int] = {}

    # Agrupar por colección
    by_collection: dict[str, list[dict]] = {}
    skipped = 0
    for art in articles:
        cat = art.get("category", "")
        collection = CATEGORY_TO_COLLECTION.get(cat)
        if not collection:
            logger.warning(f"Categoría desconocida '{cat}' para: {art.get('title','?')}")
            skipped += 1
            continue
        by_collection.setdefault(collection, []).append(art)

    logger.info(f"\n📊 Distribución por colección:")
    for cname, arts in sorted(by_collection.items()):
        logger.info(f"  {cname}: {len(arts)} artículos")
    if skipped:
        logger.info(f"  (saltados: {skipped})")

    if dry_run:
        return {cname: len(arts) for cname, arts in by_collection.items()}

    for collection_name, arts in by_collection.items():
        total_chunks = 0
        logger.info(f"\n📂 Indexando en '{collection_name}': {len(arts)} artículos")

        for art in arts:
            title = art.get("title", "sin título")
            lang = art.get("lang", "es")
            text = art["text"]

            # Prepend título y idioma para contexto
            full_text = f"# {title} [{lang.upper()}]\n\n{text}"

            chunks = chunk_text(full_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if not chunks:
                continue

            logger.info(f"  {title} ({lang}) → {len(chunks)} chunks")

            # Batches de embeddings
            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start : batch_start + batch_size]

                try:
                    embeddings = await embed_texts(batch)
                except Exception as e:
                    logger.error(f"  Error generando embeddings para {title}: {e}")
                    continue

                points = []
                for i, (chunk_text_str, emb) in enumerate(zip(batch, embeddings)):
                    chunk_idx = batch_start + i
                    point_id = str(uuid5(NAMESPACE_URL, f"wiki:{lang}:{title}:{chunk_idx}"))

                    vector_data: dict = {"dense": emb}
                    sparse_idx, sparse_val = compute_sparse_vector(chunk_text_str)
                    if sparse_idx:
                        vector_data["bm25"] = SparseVector(
                            indices=sparse_idx, values=sparse_val
                        )

                    points.append(
                        PointStruct(
                            id=point_id,
                            vector=vector_data,
                            payload={
                                "text": chunk_text_str,
                                "source_file": f"wikipedia_{lang}_{title}.md",
                                "chunk_index": chunk_idx,
                                "section": title,
                                "collection": collection_name,
                                "document_type": "wikipedia",
                                "lang": lang,
                                "wiki_title": title,
                                "wiki_category": art.get("category", ""),
                            },
                        )
                    )

                try:
                    client.upsert(collection_name=collection_name, points=points)
                    total_chunks += len(points)
                except Exception as e:
                    logger.error(f"  Error insertando en Qdrant: {e}")

        stats[collection_name] = total_chunks
        logger.info(f"  ✅ {collection_name}: +{total_chunks} chunks de Wikipedia")

    return stats


async def main():
    parser = argparse.ArgumentParser(description="Ingestión de Wikipedia en Qdrant")
    parser.add_argument("--reset", action="store_true", help="Borra artículos Wikipedia antes de reindexar")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar plan, no indexar")
    args = parser.parse_args()

    logger.info("📚 Ingestión de artículos Wikipedia en Qdrant")

    # Cargar artículos
    articles = load_articles()
    logger.info(f"Artículos cargados: {len(articles)}")

    if not articles:
        logger.error("No se encontraron artículos Wikipedia")
        return

    # Inicializar embeddings
    embed_dim = await get_embedding_dimension()
    logger.info(f"Dimensión de embeddings: {embed_dim}")

    # Crear colecciones si no existen
    await ensure_collections(embed_dim=embed_dim)

    if args.reset:
        # Borrar solo los puntos de Wikipedia (no toda la colección)
        client = get_qdrant()
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        target_collections = set(CATEGORY_TO_COLLECTION.values())
        for cname in target_collections:
            try:
                client.delete(
                    collection_name=cname,
                    points_selector=Filter(
                        must=[FieldCondition(key="document_type", match=MatchValue(value="wikipedia"))]
                    ),
                )
                logger.info(f"🗑️  Puntos Wikipedia eliminados de '{cname}'")
            except Exception as e:
                logger.warning(f"No se pudieron eliminar puntos de {cname}: {e}")

    # Indexar
    stats = await ingest_articles(articles, dry_run=args.dry_run)

    grand_total = sum(stats.values())
    logger.info(f"\n🎉 Wikipedia indexado: {grand_total} chunks en {len(stats)} colecciones")
    for cname, count in sorted(stats.items()):
        logger.info(f"  {cname}: {count}")

    # Cleanup
    await close_embeddings()
    close_qdrant()


if __name__ == "__main__":
    asyncio.run(main())
