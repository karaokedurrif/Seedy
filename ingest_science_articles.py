#!/usr/bin/env python3
"""
Seedy — Ingestión de artículos científicos (OpenAlex abstracts) en Qdrant.

Lee science_articles/science_articles_raw.jsonl y los indexa en las colecciones
Qdrant adecuadas según su topic.

Uso:
    python ingest_science_articles.py              # Indexar todos
    python ingest_science_articles.py --only-new   # Solo nuevos topics (vino, avi_intensiva)
"""

import os
import sys
import json
import argparse
import logging
import asyncio
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QDRANT_HOST", "localhost")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from config import get_settings
from services.embeddings import embed_texts, get_embedding_dimension, close as close_embeddings
from services.rag import get_qdrant, ensure_collections, close as close_qdrant
from ingestion.chunker import chunk_text, compute_sparse_vector
from qdrant_client.models import PointStruct, SparseVector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Mapeo topic → colección Qdrant ──
TOPIC_TO_COLLECTION = {
    # Avicultura
    "avicultura_capones": "avicultura",
    "avicultura_engorde": "avicultura",
    "avicultura_razas": "avicultura",
    "avicultura_capones_calidad": "avicultura",
    "avicultura_ponedoras": "avicultura",
    "avicultura_bienestar": "avicultura",
    "avicultura_nutricion": "nutricion",
    # Porcino
    "porcino_iberico": "genetica",
    "porcino_nutricion": "nutricion",
    "porcino_genetica": "genetica",
    "porcino_bienestar": "normativa",
    "porcino_calidad": "estrategia",
    "porcino_reproduccion": "genetica",
    "porcino_iot": "iot_hardware",
    "porcino_sanidad": "normativa",
    "porcino_microbioma": "nutricion",
    # Vacuno
    "vacuno_extensivo": "estrategia",
    "vacuno_genetica": "genetica",
    "vacuno_calidad": "estrategia",
    "vacuno_lechero": "nutricion",
    "vacuno_iot": "iot_hardware",
    "vacuno_cria": "genetica",
    "vacuno_medioambiente": "estrategia",
    # Nutrición
    "nutricion_formulacion": "nutricion",
    "nutricion_eficiencia": "nutricion",
    "nutricion_micotoxinas": "nutricion",
    "nutricion_aminoacidos": "nutricion",
    "nutricion_suplementacion": "nutricion",
    # Genética
    "genetica_genomica": "genetica",
    "genetica_cruzamiento": "genetica",
    "genetica_consanguinidad": "genetica",
    # IoT
    "iot_digital_twin": "digital_twins",
    "iot_sensores": "iot_hardware",
    "iot_vision": "iot_hardware",
    "iot_analytics": "iot_hardware",
    "iot_rfid": "iot_hardware",
    # Normativa
    "normativa_bienestar": "normativa",
    "normativa_sostenibilidad": "normativa",
    # Avicultura intensiva (NUEVO)
    "avi_intensiva_broiler": "avicultura_intensiva",
    "avi_intensiva_naves": "avicultura_intensiva",
    "avi_intensiva_ponedoras": "avicultura_intensiva",
    "avi_intensiva_bioseguridad": "avicultura_intensiva",
    "avi_intensiva_incubacion": "avicultura_intensiva",
    "avi_intensiva_procesado": "avicultura_intensiva",
    "avi_intensiva_genetica": "avicultura_intensiva",
    "avi_intensiva_cama": "avicultura_intensiva",
    "avi_intensiva_precision": "avicultura_intensiva",
    "avi_intensiva_salud": "avicultura_intensiva",
    # Vino (NUEVO)
    "vino_enologia": "bodegas_vino",
    "vino_viticultura_precision": "bodegas_vino",
    "vino_tempranillo": "bodegas_vino",
    "vino_crianza": "bodegas_vino",
    "vino_sanidad_vid": "bodegas_vino",
    "vino_cambio_climatico": "bodegas_vino",
    "vino_ecologico": "bodegas_vino",
    "vino_tecnologia": "bodegas_vino",
    "vino_variedades_esp": "bodegas_vino",
    "vino_terroir": "bodegas_vino",
    "vino_espumoso": "bodegas_vino",
    "vino_enoturismo": "bodegas_vino",
}

NEW_TOPICS = {t for t in TOPIC_TO_COLLECTION if t.startswith(("avi_intensiva_", "vino_"))}

SCIENCE_FILE = Path(__file__).parent / "science_articles" / "science_articles_raw.jsonl"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
EMBED_BATCH = 32


async def ingest(only_new: bool = False):
    if not SCIENCE_FILE.exists():
        logger.error(f"No se encuentra {SCIENCE_FILE}")
        return

    articles = [json.loads(l) for l in SCIENCE_FILE.open()]
    if only_new:
        articles = [a for a in articles if a.get("topic", "") in NEW_TOPICS]
        logger.info(f"Modo --only-new: {len(articles)} artículos de nuevos verticales")
    else:
        logger.info(f"Total artículos: {len(articles)}")

    embed_dim = await get_embedding_dimension()
    await ensure_collections(embed_dim=embed_dim)

    stats: dict[str, int] = {}

    for i, art in enumerate(articles):
        topic = art.get("topic", "")
        collection = TOPIC_TO_COLLECTION.get(topic)
        if not collection:
            continue

        title = art.get("title", "")
        abstract = art.get("abstract", "")
        if len(abstract) < 80:
            continue

        # Build a rich text from the article
        authors_str = ", ".join(art.get("authors", [])[:3])
        journal = art.get("journal", "")
        year = art.get("year", "")
        text = f"{title}\n\n{abstract}"
        if authors_str:
            text += f"\n\nAutores: {authors_str}"
        if journal:
            text += f"\nRevista: {journal} ({year})"

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        if not chunks:
            continue

        # Embed
        try:
            embeddings = await embed_texts(chunks)
        except Exception as e:
            logger.error(f"  Error embeddiendo {title[:50]}: {e}")
            continue

        # Build points
        client = get_qdrant()
        points = []
        url = art.get("openalex_id", f"openalex:{topic}:{i}")
        for ci, (chunk_text_str, emb) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid5(NAMESPACE_URL, f"science:{url}:{ci}"))
            sparse_idx, sparse_val = compute_sparse_vector(chunk_text_str)
            vector_data = {"dense": emb}
            if sparse_idx:
                vector_data["bm25"] = SparseVector(indices=sparse_idx, values=sparse_val)
            points.append(PointStruct(
                id=point_id,
                vector=vector_data,
                payload={
                    "text": chunk_text_str,
                    "source_file": f"science_{topic}",
                    "source_url": url,
                    "title": title,
                    "chunk_index": ci,
                    "section": "",
                    "collection": collection,
                    "document_type": "science_abstract",
                    "domain": topic,
                    "ingested_by": "ingest_science",
                },
            ))

        try:
            client.upsert(collection_name=collection, points=points)
            stats[collection] = stats.get(collection, 0) + len(points)
        except Exception as e:
            logger.error(f"  Error upserting {title[:50]}: {e}")

        if (i + 1) % 50 == 0:
            logger.info(f"  Procesados {i+1}/{len(articles)}...")

    logger.info(f"\n🎉 Science indexado: {sum(stats.values())} chunks en {len(stats)} colecciones")
    for col, n in sorted(stats.items()):
        logger.info(f"  {col}: {n}")

    close_embeddings()
    close_qdrant()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-new", action="store_true",
                        help="Solo ingestar topics de vino y avicultura intensiva")
    args = parser.parse_args()
    asyncio.run(ingest(only_new=args.only_new))


if __name__ == "__main__":
    main()
