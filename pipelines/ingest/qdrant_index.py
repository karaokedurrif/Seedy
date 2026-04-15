"""Pipeline de autoingesta — Indexación en Qdrant."""

import logging
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, SparseVector, Distance,
    VectorParams, SparseVectorParams, SparseIndexParams,
)

from pipelines.ingest.settings import get_settings
from pipelines.ingest.chunk import chunk_for_ingest, compute_sparse_vector
from pipelines.ingest.embed import embed_texts

logger = logging.getLogger(__name__)

# Mapeo dominio → colección Qdrant (las mismas que el backend)
DOMAIN_TO_COLLECTION = {
    "porcino": "porcino",
    "vacuno": "bovino",
    "avicultura": "avicultura",
    "avicultura_intensiva": "avicultura_intensiva",
    "bodegas_vino": "bodegas_vino",
    "nutricion": "nutricion",
    "genetica": "genetica",
    "normativa": "normativa",
    "iot": "iot_hardware",
    "estrategia": "estrategia",
}

ALL_COLLECTIONS = list(set(DOMAIN_TO_COLLECTION.values()))

_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    """Singleton del cliente Qdrant."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = QdrantClient(url=settings.qdrant_url)
    return _client


async def ensure_collections(embed_dim: int = 1024):
    """Crea colecciones si no existen (misma estructura que backend)."""
    client = get_qdrant()
    existing = {c.name for c in client.get_collections().collections}

    for cname in ALL_COLLECTIONS:
        if cname not in existing:
            client.create_collection(
                collection_name=cname,
                vectors_config={
                    "dense": VectorParams(size=embed_dim, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    "bm25": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
                },
            )
            logger.info(f"Colección '{cname}' creada")


async def index_item(
    item: dict,
    embed_dim: int = 1024,
) -> int:
    """
    Chunkea, embebe e indexa un item en su colección Qdrant.
    Devuelve el número de chunks indexados.
    """
    settings = get_settings()
    client = get_qdrant()

    text = item.get("parsed_text", "")
    if not text or len(text.strip()) < 50:
        return 0

    domain = item.get("domain", "estrategia")
    collection = DOMAIN_TO_COLLECTION.get(domain, "estrategia")

    # Chunkear
    chunks = chunk_for_ingest(
        text=text,
        title=item.get("title", ""),
        source_name=item.get("source_name", ""),
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        return 0

    total_indexed = 0

    # Procesar en batches
    for batch_start in range(0, len(chunks), settings.embed_batch_size):
        batch = chunks[batch_start : batch_start + settings.embed_batch_size]
        batch_texts = [c["text"] for c in batch]

        try:
            embeddings = await embed_texts(batch_texts)
        except Exception as e:
            logger.error(f"Error embeddiendo: {e}")
            continue

        points = []
        for i, (chunk, emb) in enumerate(zip(batch, embeddings)):
            chunk_idx = batch_start + i
            url = item.get("canonical_url", item.get("url", ""))
            point_id = str(uuid5(NAMESPACE_URL, f"ingest:{url}:{chunk_idx}"))

            # Vector denso + sparse
            vector_data: dict = {"dense": emb}
            sparse_idx, sparse_val = compute_sparse_vector(chunk["text"])
            if sparse_idx:
                vector_data["bm25"] = SparseVector(indices=sparse_idx, values=sparse_val)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector_data,
                    payload={
                        "text": chunk["text"],
                        "source_file": f"ingest_{item.get('source_name', 'unknown')}",
                        "source_url": url,
                        "title": item.get("title", ""),
                        "chunk_index": chunk_idx,
                        "section": "",
                        "collection": collection,
                        "document_type": "web_article",
                        "domain": domain,
                        "score": item.get("score", 0),
                        "ingested_by": "autoingesta",
                    },
                )
            )

        try:
            client.upsert(collection_name=collection, points=points)
            total_indexed += len(points)
        except Exception as e:
            logger.error(f"Error upserting en '{collection}': {e}")

    logger.info(f"  → {total_indexed} chunks indexados en '{collection}'")
    return total_indexed


def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None
