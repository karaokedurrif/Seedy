#!/usr/bin/env python3
"""
Seedy Backend — Script de ingestión: indexa documentos de conocimientos/ en Qdrant.

Uso:
    python -m ingestion.ingest                        # Indexa todo
    python -m ingestion.ingest --collection nutricion  # Solo una colección
    python -m ingestion.ingest --reset                 # Borra y reindexa
"""

import sys
import os
import argparse
import logging
import asyncio
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

# Añadir backend/ al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from services.embeddings import embed_texts, get_embedding_dimension, close as close_embeddings
from services.rag import (
    get_qdrant, ensure_collections, FOLDER_TO_COLLECTION, ALL_COLLECTIONS,
    close as close_qdrant,
)
from ingestion.chunker import chunk_text, extract_text
from qdrant_client.models import PointStruct

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def discover_files(knowledge_dir: str, target_collection: str | None = None) -> dict[str, list[Path]]:
    """
    Descubre archivos organizados por colección.
    Devuelve {collection_name: [file_paths]}.
    """
    knowledge_path = Path(knowledge_dir)
    collection_files: dict[str, list[Path]] = {}

    for folder_name, collection_name in FOLDER_TO_COLLECTION.items():
        if target_collection and collection_name != target_collection:
            continue

        folder_path = knowledge_path / folder_name
        if not folder_path.exists():
            logger.warning(f"Carpeta no encontrada: {folder_path}")
            continue

        files = []
        for f in folder_path.iterdir():
            if f.is_file() and f.suffix.lower() in {".md", ".pdf", ".docx", ".csv", ".txt"}:
                files.append(f)

        if files:
            collection_files[collection_name] = sorted(files)
            logger.info(f"  {collection_name}: {len(files)} archivos")

    return collection_files


async def ingest_collection(
    collection_name: str,
    files: list[Path],
    chunk_size: int,
    chunk_overlap: int,
    batch_size: int = 10,
):
    """Indexa todos los archivos de una colección en Qdrant."""
    client = get_qdrant()
    total_chunks = 0

    for filepath in files:
        logger.info(f"  Procesando: {filepath.name}")

        try:
            text = extract_text(str(filepath))
        except Exception as e:
            logger.error(f"  Error extrayendo texto de {filepath.name}: {e}")
            continue

        if not text.strip():
            logger.warning(f"  {filepath.name} está vacío, saltando")
            continue

        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        logger.info(f"  → {len(chunks)} chunks")

        # Procesar en batches para embeddings
        for batch_start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_start:batch_start + batch_size]

            try:
                embeddings = await embed_texts(batch_chunks)
            except Exception as e:
                logger.error(f"  Error generando embeddings: {e}")
                continue

            points = []
            for i, (chunk, emb) in enumerate(zip(batch_chunks, embeddings)):
                chunk_idx = batch_start + i
                # ID determinístico basado en archivo + chunk index
                point_id = str(uuid5(NAMESPACE_URL, f"{filepath.name}:{chunk_idx}"))

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=emb,
                        payload={
                            "text": chunk,
                            "source_file": filepath.name,
                            "chunk_index": chunk_idx,
                            "collection": collection_name,
                            "document_type": filepath.suffix.lower().lstrip("."),
                        },
                    )
                )

            try:
                client.upsert(collection_name=collection_name, points=points)
                total_chunks += len(points)
            except Exception as e:
                logger.error(f"  Error insertando en Qdrant: {e}")

    logger.info(f"  ✅ {collection_name}: {total_chunks} chunks indexados")
    return total_chunks


async def main():
    parser = argparse.ArgumentParser(description="Ingestión de conocimientos en Qdrant")
    parser.add_argument("--collection", type=str, default=None, help="Indexar solo esta colección")
    parser.add_argument("--reset", action="store_true", help="Borrar colecciones antes de indexar")
    parser.add_argument("--knowledge-dir", type=str, default=None, help="Directorio de conocimientos")
    args = parser.parse_args()

    settings = get_settings()
    knowledge_dir = args.knowledge_dir or settings.knowledge_dir

    logger.info(f"📚 Ingestión de conocimientos desde: {knowledge_dir}")

    # Inicializar
    embed_dim = await get_embedding_dimension()
    logger.info(f"Dimensión de embeddings: {embed_dim}")

    # Reset si se pide
    if args.reset:
        client = get_qdrant()
        collections_to_reset = [args.collection] if args.collection else ALL_COLLECTIONS
        for cname in collections_to_reset:
            try:
                client.delete_collection(cname)
                logger.info(f"🗑️  Colección '{cname}' eliminada")
            except Exception:
                pass

    # Crear colecciones
    await ensure_collections(embed_dim=embed_dim)

    # Descubrir archivos
    collection_files = discover_files(knowledge_dir, args.collection)

    if not collection_files:
        logger.error("No se encontraron archivos para indexar")
        return

    # Indexar
    grand_total = 0
    for cname, files in collection_files.items():
        logger.info(f"\n📂 Indexando colección: {cname}")
        count = await ingest_collection(
            cname, files,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )
        grand_total += count

    logger.info(f"\n🎉 Ingestión completa: {grand_total} chunks totales en {len(collection_files)} colecciones")

    # Cleanup
    await close_embeddings()
    close_qdrant()


if __name__ == "__main__":
    asyncio.run(main())
