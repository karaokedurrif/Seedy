"""Seedy Backend — Servicio RAG con Qdrant (búsqueda híbrida dense + sparse)."""

import logging
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, SparseVectorParams, SparseIndexParams

from config import get_settings
from services.embeddings import embed_query

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None

# Mapeo de carpetas de conocimientos → colección Qdrant
FOLDER_TO_COLLECTION = {
    "1.PorciData — IoT & Hardware": "iot_hardware",
    "2.Nutricion & Formulacion": "nutricion",
    "3.NeoFarm Genetica": "genetica",
    "4.Estrategia & Competencia": "estrategia",
    "5.Digital Twins & IoT": "digital_twins",
    "6.Normativa & SIGE  ": "normativa",
}

ALL_COLLECTIONS = list(FOLDER_TO_COLLECTION.values())


def get_qdrant() -> QdrantClient:
    """Singleton del cliente Qdrant."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


async def ensure_collections(embed_dim: int = 1024):
    """Crea las colecciones en Qdrant si no existen."""
    client = get_qdrant()
    existing = {c.name for c in client.get_collections().collections}

    for collection_name in ALL_COLLECTIONS:
        if collection_name not in existing:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embed_dim,
                    distance=Distance.COSINE,
                ),
                sparse_vectors_config={
                    "bm25": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    )
                },
            )
            logger.info(f"Colección '{collection_name}' creada (dim={embed_dim})")
        else:
            logger.info(f"Colección '{collection_name}' ya existe")


async def search(
    query: str,
    collections: list[str],
    top_k: int | None = None,
) -> list[dict]:
    """
    Búsqueda híbrida (dense + awareness de BM25 weight) en las colecciones indicadas.
    Devuelve lista de resultados ordenados por score.
    """
    settings = get_settings()
    client = get_qdrant()
    k = top_k or settings.rag_top_k

    # Generar embedding de la query
    query_vector = await embed_query(query)

    all_results = []

    for collection_name in collections:
        try:
            # Verificar que la colección existe
            existing = {c.name for c in client.get_collections().collections}
            if collection_name not in existing:
                logger.warning(f"Colección '{collection_name}' no existe, saltando")
                continue

            # Búsqueda por vector denso
            hits = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=k,
                score_threshold=settings.rag_relevance_threshold,
                with_payload=True,
            ).points

            for hit in hits:
                payload = hit.payload or {}
                all_results.append({
                    "text": payload.get("text", ""),
                    "file": payload.get("source_file", ""),
                    "collection": collection_name,
                    "chunk_index": payload.get("chunk_index", 0),
                    "score": hit.score,
                })

        except Exception as e:
            logger.error(f"Error buscando en '{collection_name}': {e}")

    # Ordenar por score descendente y limitar
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:k]


def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None
