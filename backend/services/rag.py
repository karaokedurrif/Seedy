"""Seedy Backend — Servicio RAG con Qdrant (búsqueda híbrida dense + sparse)."""

import logging
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, SparseVectorParams, SparseIndexParams

from config import get_settings
from services.embeddings import embed_query
from ingestion.chunker import compute_sparse_vector

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
    "7.Avicultura Extensiva & Capones": "avicultura",
    "7.Fuentes_Externas": "iot_hardware",
    "7.GeoTwin & GIS 3D": "geotwin",
    "8.Avicultura Intensiva": "avicultura_intensiva",
    "9.Bodegas & Vino": "bodegas_vino",
    "CDA_Resumenes": "digital_twins",
    "Carga de documentos nuevos": "avicultura",
}

# Colección especial para contenido web fresco (no mapeada a carpeta)
FRESH_WEB_COLLECTION = "fresh_web"

ALL_COLLECTIONS = list(set(FOLDER_TO_COLLECTION.values())) + [FRESH_WEB_COLLECTION, "porcino", "bovino"]


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
                vectors_config={
                    "dense": VectorParams(
                        size=embed_dim,
                        distance=Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    "bm25": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    )
                },
            )
            logger.info(f"Colección '{collection_name}' creada (dim={embed_dim}, hybrid)")
        else:
            logger.info(f"Colección '{collection_name}' ya existe")


async def search(
    query: str,
    collections: list[str],
    top_k: int | None = None,
    alt_query: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """
    Búsqueda híbrida (dense + sparse BM25) con fusión RRF.
    Si alt_query se proporciona, se hace dual-query: se generan embeddings
    de ambas queries, se busca dense con cada una, y se fusionan los
    resultados con RRF. Esto mejora recall cuando el rewriter sesga la query.
    BM25 se hace solo con la query principal (la reescrita tiene más tokens útiles).

    Phase 2: Aplica metadata filters (especie, document_type) para reducir ruido.
    Devuelve lista de resultados ordenados por score fusionado.
    """
    from services.metadata_filter import build_qdrant_filter

    settings = get_settings()
    client = get_qdrant()
    k = top_k or settings.rag_top_k

    # Generar vectores de query
    query_vector = await embed_query(query)
    sparse_indices, sparse_values = compute_sparse_vector(query)

    # Vector alternativo para dual-query (si se proporciona)
    alt_vector = None
    if alt_query and alt_query != query:
        alt_vector = await embed_query(alt_query)

    rrf_k = 60  # constante estándar RRF
    fused: dict[str, dict] = {}  # key → resultado con score RRF

    # Colecciones existentes (una sola llamada)
    existing = {c.name for c in client.get_collections().collections}

    for collection_name in collections:
        if collection_name not in existing:
            logger.warning(f"Colección '{collection_name}' no existe, saltando")
            continue

        # Phase 2: Metadata filter por colección
        q_filter = build_qdrant_filter(query, collection_name, category)

        try:
            # Búsqueda densa (query principal)
            try:
                dense_hits = client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    using="dense",
                    limit=k * 2,
                    with_payload=True,
                    query_filter=q_filter,
                ).points
            except Exception:
                dense_hits = []

            # Búsqueda densa alternativa (query original, dual-query)
            alt_dense_hits = []
            if alt_vector:
                try:
                    alt_dense_hits = client.query_points(
                        collection_name=collection_name,
                        query=alt_vector,
                        using="dense",
                        limit=k * 2,
                        with_payload=True,
                        query_filter=q_filter,
                    ).points
                except Exception:
                    alt_dense_hits = []

            # Búsqueda sparse BM25 (solo con query principal)
            sparse_hits = []
            if sparse_indices:
                try:
                    sparse_hits = client.query_points(
                        collection_name=collection_name,
                        query=models.SparseVector(
                            indices=sparse_indices, values=sparse_values
                        ),
                        using="bm25",
                        limit=k * 2,
                        with_payload=True,
                        query_filter=q_filter,
                    ).points
                except Exception:
                    sparse_hits = []

            # Fusión RRF (Reciprocal Rank Fusion)
            # Dense principal
            for rank, hit in enumerate(dense_hits):
                key = f"{collection_name}:{hit.id}"
                if key not in fused:
                    payload = hit.payload or {}
                    fused[key] = {
                        "text": payload.get("text", ""),
                        "file": payload.get("source_file") or payload.get("source", ""),
                        "collection": collection_name,
                        "chunk_index": payload.get("chunk_index", 0),
                        "section": payload.get("section", ""),
                        "score": 0.0,
                    }
                fused[key]["score"] += 1.0 / (rrf_k + rank + 1)

            # Dense alternativa (misma contribución RRF)
            for rank, hit in enumerate(alt_dense_hits):
                key = f"{collection_name}:{hit.id}"
                if key not in fused:
                    payload = hit.payload or {}
                    fused[key] = {
                        "text": payload.get("text", ""),
                        "file": payload.get("source_file") or payload.get("source", ""),
                        "collection": collection_name,
                        "chunk_index": payload.get("chunk_index", 0),
                        "section": payload.get("section", ""),
                        "score": 0.0,
                    }
                fused[key]["score"] += 1.0 / (rrf_k + rank + 1)

            # BM25
            bm25_w = settings.rag_bm25_weight
            for rank, hit in enumerate(sparse_hits):
                key = f"{collection_name}:{hit.id}"
                if key not in fused:
                    payload = hit.payload or {}
                    fused[key] = {
                        "text": payload.get("text", ""),
                        "file": payload.get("source_file") or payload.get("source", ""),
                        "collection": collection_name,
                        "chunk_index": payload.get("chunk_index", 0),
                        "section": payload.get("section", ""),
                        "score": 0.0,
                    }
                fused[key]["score"] += bm25_w / (rrf_k + rank + 1)

        except Exception as e:
            logger.error(f"Error buscando en '{collection_name}': {e}")

    results = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
    return results[:k]


def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None
