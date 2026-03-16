#!/usr/bin/env python3
"""
Seedy — Ingesta de corpus externo (PDFs chunkeados).

Lee chunks pre-procesados desde seedy_open_qdrant_ingest.zip e inyecta
en Qdrant usando nuestro pipeline de embeddings (mxbai-embed-large 1024d)
y vectores sparse BM25.

Uso:
    python ingest_new_corpus.py                 # Ingestar todo
    python ingest_new_corpus.py --dry-run       # Solo ver qué se haría
    python ingest_new_corpus.py --skip-existing # No insertar si ya hay chunks del doc

Fuente:
    /tmp/seedy_open_qdrant_ingest/chunks_new_uploads.jsonl  (903 chunks, 10 PDFs)
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

# ── Apuntar a servicios Docker en localhost ──
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QDRANT_HOST", "localhost")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_corpus")

# ── Fichero de chunks ──
CHUNKS_FILE = "/tmp/seedy_open_qdrant_ingest/chunks_new_uploads.jsonl"
# Si no está extraído todavía:
ZIP_FILE = "/home/davidia/Descargas/seedy_open_qdrant_ingest.zip"

# ── Mapping de títulos a colecciones Qdrant ──
# Casi todo es avicultura; solo el módulo de cerdos va aparte
TITLE_TO_COLLECTION = {
    "Modulo multimodal de deteccion de tos y cerdos con tos": "iot_hardware",
}
DEFAULT_COLLECTION = "avicultura"

# ── Filtro: chunks basura ──
SKIP_CHUNKS = {
    ("c9cdfbc86907e9dc", 0),  # puro texto legal: ISBN, editorial, derechos
    ("316bffa553684b44", 111),  # formulario de trazos (———) que rompe tokenizer
}

# ── Longitud máxima de texto para embedding ──
# mxbai-embed-large tiene context_length=512 tokens.
# Texto en español ≈ 2.5-3.5 chars/token. Con 800 chars ≈ 320 tokens → seguro.
# El texto completo se guarda en payload; solo se trunca para generar el vector.
# (BM25 sparse vector usa el texto completo)
EMBED_MAX_CHARS = 800


def clean_for_embedding(text: str) -> str:
    """Limpia texto antes de enviarlo al modelo de embeddings.
    Elimina puntuación repetitiva (índices, formularios) que consume tokens
    sin aportar semántica. Luego trunca a EMBED_MAX_CHARS."""
    # Colapsar secuencias de puntos, guiones, puntos suspensivos
    cleaned = re.sub(r'[\.…]{3,}', '... ', text)
    cleaned = re.sub(r'[\u2014\u2013\-_]{3,}', ' ', cleaned)
    # Colapsar espacios múltiples
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip()[:EMBED_MAX_CHARS]

# ── Stopwords para BM25 sparse ──
_STOPWORDS = frozenset(
    "de la el en los las un una del al con por para es que se su no lo más"
    " como pero ya o si le este esta ese esa estos estas esos esas"
    " ser estar haber tener ir poder decir hacer ver dar saber querer"
    " a ante bajo cabe contra desde durante entre hacia hasta mediante"
    " otro otra otros otras muy también así donde cuando todo toda todos todas"
    " me te nos os les mi tu mis tus nuestro nuestra nuestros nuestras"
    .split()
)


def compute_sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """Vector disperso BM25-like para Qdrant."""
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    tokens = [t for t in tokens if t not in _STOPWORDS]
    if not tokens:
        return [], []
    tf = Counter(tokens)
    indices, values = [], []
    for token, count in sorted(tf.items()):
        idx = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) % (2**31)
        indices.append(idx)
        values.append(float(count))
    return indices, values


def map_collection(title: str) -> str:
    """Decide en qué colección Qdrant meter un documento."""
    return TITLE_TO_COLLECTION.get(title, DEFAULT_COLLECTION)


def is_garbage(text: str) -> bool:
    """Detecta chunks basura (formularios con trazos, tablas vacías, etc.)."""
    dash_count = text.count('\u2014') + text.count('\u2013') + text.count('_')
    if dash_count > len(text) * 0.4:
        return True
    # Texto sin contenido real (solo espacios/trazos)
    clean = re.sub(r'[\s\u2014\u2013_\-—–]+', '', text)
    if len(clean) < 50:
        return True
    return False


def load_chunks(path: str) -> list[dict]:
    """Lee el JSONL y devuelve lista de chunks."""
    chunks = []
    skipped_garbage = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            # Filtrar chunks por ID explícito
            key = (obj.get("doc_id", ""), obj.get("chunk_index", -1))
            if key in SKIP_CHUNKS:
                logger.info(f"  Saltando chunk basura (ID): {obj.get('title','')} idx={key[1]}")
                continue
            # Filtrar chunks basura por contenido
            if is_garbage(obj.get("text", "")):
                skipped_garbage += 1
                logger.debug(f"  Saltando chunk basura (contenido): {obj.get('title','')} idx={key[1]}")
                continue
            chunks.append(obj)
    if skipped_garbage:
        logger.info(f"  Filtrados {skipped_garbage} chunks basura por contenido")
    return chunks


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Ingestión de corpus externo en Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se haría")
    parser.add_argument("--skip-existing", action="store_true",
                        help="No insertar si ya hay chunks del mismo source_file")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Chunks por batch de embedding (default: 10)")
    args = parser.parse_args()

    # ── Extraer si no existe ──
    if not os.path.exists(CHUNKS_FILE):
        if os.path.exists(ZIP_FILE):
            import zipfile
            logger.info(f"Extrayendo {ZIP_FILE}...")
            with zipfile.ZipFile(ZIP_FILE) as zf:
                zf.extractall("/tmp")
        else:
            logger.error(f"No se encuentra ni {CHUNKS_FILE} ni {ZIP_FILE}")
            sys.exit(1)

    # ── Cargar chunks ──
    chunks = load_chunks(CHUNKS_FILE)
    logger.info(f"Cargados {len(chunks)} chunks")

    # ── Agrupar por colección ──
    by_collection: dict[str, list[dict]] = {}
    for chunk in chunks:
        col = map_collection(chunk.get("title", ""))
        by_collection.setdefault(col, []).append(chunk)

    logger.info("Distribución por colección:")
    for col, col_chunks in sorted(by_collection.items()):
        titles = set(c.get("title", "") for c in col_chunks)
        logger.info(f"  {col}: {len(col_chunks)} chunks ({len(titles)} docs)")
        for t in sorted(titles):
            logger.info(f"    - {t}")

    if args.dry_run:
        logger.info("🏁 Dry-run finalizado. No se insertó nada.")
        return

    # ── Imports pesados solo si vamos a insertar ──
    from services.embeddings import embed_texts, get_embedding_dimension, close as close_embeddings
    from services.rag import get_qdrant, ensure_collections
    from qdrant_client.models import PointStruct, SparseVector

    embed_dim = await get_embedding_dimension()
    logger.info(f"Dimensión de embeddings: {embed_dim}")
    await ensure_collections(embed_dim=embed_dim)

    client = get_qdrant()
    grand_total = 0

    for col_name, col_chunks in sorted(by_collection.items()):
        logger.info(f"\n── Colección: {col_name} ({len(col_chunks)} chunks) ──")

        # ── Verificar existencia si se pide ──
        if args.skip_existing:
            existing_sources = set()
            try:
                # Buscar por source_file
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                for chunk in col_chunks[:1]:
                    sf = chunk.get("title", "unknown") + ".pdf"
                    result = client.scroll(
                        collection_name=col_name,
                        scroll_filter=Filter(must=[
                            FieldCondition(key="source_file", match=MatchValue(value=sf))
                        ]),
                        limit=1,
                    )
                    if result[0]:
                        existing_sources.add(sf)
            except Exception:
                pass

            if existing_sources:
                logger.info(f"  ⏭ Ya existen chunks de {existing_sources}, saltando")
                continue

        # ── Procesar en batches ──
        col_total = 0
        for batch_start in range(0, len(col_chunks), args.batch_size):
            batch = col_chunks[batch_start : batch_start + args.batch_size]
            # Limpiar y truncar texto para embedding (payload guarda completo)
            batch_texts = [clean_for_embedding(c["text"]) for c in batch]

            try:
                embeddings = await embed_texts(batch_texts)
            except Exception as e:
                logger.error(f"  Error embeddings batch {batch_start}: {e}")
                continue

            points = []
            for i, (chunk, emb) in enumerate(zip(batch, embeddings)):
                chunk_idx = chunk.get("chunk_index", batch_start + i)
                source_file = chunk.get("title", "unknown") + ".pdf"
                doc_id = chunk.get("doc_id", "")

                # ID determinístico
                point_id = str(uuid5(NAMESPACE_URL, f"corpus:{doc_id}:{chunk_idx}"))

                # Vectores denso + sparse
                vector_data: dict = {"dense": emb}
                sparse_idx, sparse_val = compute_sparse_vector(chunk["text"])
                if sparse_idx:
                    vector_data["bm25"] = SparseVector(
                        indices=sparse_idx, values=sparse_val
                    )

                # Payload compatible con nuestro formato
                payload = {
                    "text": chunk["text"],
                    "source_file": source_file,
                    "chunk_index": chunk_idx,
                    "section": "",
                    "collection": col_name,
                    "document_type": "pdf",
                    # Metadatos extra del corpus
                    "doc_id": doc_id,
                    "title": chunk.get("title", ""),
                    "language": chunk.get("language", "es"),
                    "topics": chunk.get("topics", []),
                    "species": chunk.get("species", []),
                    "source_origin": "corpus_externo",
                }

                points.append(PointStruct(
                    id=point_id,
                    vector=vector_data,
                    payload=payload,
                ))

            try:
                client.upsert(collection_name=col_name, points=points)
                col_total += len(points)
            except Exception as e:
                logger.error(f"  Error upsert batch {batch_start}: {e}")

            if (batch_start + args.batch_size) % 50 == 0 or batch_start == 0:
                logger.info(f"  Progreso: {col_total}/{len(col_chunks)} chunks")

        grand_total += col_total
        logger.info(f"  ✅ {col_name}: {col_total} chunks insertados")

    logger.info(f"\n🎉 Ingestión completa: {grand_total} chunks nuevos en Qdrant")
    await close_embeddings()


if __name__ == "__main__":
    asyncio.run(main())
