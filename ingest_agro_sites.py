#!/usr/bin/env python3
"""
Ingesta contenido descargado de sitios agropecuarios en Qdrant.

Lee los ficheros .md de data/raw/agro_sites/ y los indexa en la colección
apropiada según la especie del documento (porcino→genetica, vacuno→genetica,
multiespecie→avicultura, etc.).

Uso:
    python ingest_agro_sites.py              # Indexar todo
    python ingest_agro_sites.py --reset      # Borrar y reindexar
    python ingest_agro_sites.py --dry-run    # Solo ver qué se indexaría
"""

import os, sys, json, logging, asyncio, argparse, re
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

# Apuntar a servicios Docker en localhost
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QDRANT_HOST", "localhost")

# Añadir backend/ al path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from services.embeddings import embed_texts, get_embedding_dimension, close as close_embeddings
from services.rag import get_qdrant, ensure_collections, close as close_qdrant
from ingestion.chunker import chunk_markdown, compute_sparse_vector
from qdrant_client.models import PointStruct, SparseVector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

AGRO_DIR = Path(__file__).parent / "data" / "raw" / "agro_sites"
INDEX_FILE = Path(__file__).parent / "data" / "raw" / "agro_sites_index.jsonl"

# Mapeo especie → colección Qdrant
SPECIES_TO_COLLECTION = {
    "porcino": "genetica",
    "vacuno": "genetica",
    "multiespecie": "avicultura",  # catch-all de conocimiento general → avicultura (la más grande)
}

# Chunk config — smaller chunks to stay within Ollama token limit
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
BATCH_SIZE = 10

# Regex para limpiar enlaces markdown: [text](url) → text
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")
# Regex para limpiar URLs sueltas
_URL_RE = re.compile(r"https?://\S+")
# Regex para limpiar bloques de navegación (* [texto](url))
_NAV_LINE_RE = re.compile(r"^\s*\*\s*\[.*\]\(.*\)\s*$")


def clean_markdown_for_embedding(text: str) -> str:
    """Limpia el markdown para que no tenga URLs que excedan el context length."""
    lines = text.split("\n")
    cleaned = []
    nav_block_count = 0

    for line in lines:
        # Detectar bloques de navegación (muchas líneas seguidas de * [text](url))
        if _NAV_LINE_RE.match(line):
            nav_block_count += 1
            if nav_block_count > 3:  # Skip navigation blocks (>3 consecutive nav items)
                continue
        else:
            nav_block_count = 0

        # Reemplazar [text](url) → text
        line = _MD_LINK_RE.sub(r"\1", line)
        # Quitar URLs sueltas
        line = _URL_RE.sub("", line)
        # Limpiar espacios extra
        line = re.sub(r"  +", " ", line).rstrip()

        if line.strip():
            cleaned.append(line)

    return "\n".join(cleaned)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extrae YAML frontmatter del markdown."""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip()
            body = parts[2].strip()
    return meta, body


def discover_files() -> dict[str, list[tuple[Path, dict]]]:
    """Agrupa ficheros por colección Qdrant según metadatos."""
    collection_files: dict[str, list[tuple[Path, dict]]] = {}

    for md_file in sorted(AGRO_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        species = meta.get("species", "multiespecie")
        collection = SPECIES_TO_COLLECTION.get(species, "avicultura")

        if collection not in collection_files:
            collection_files[collection] = []
        collection_files[collection].append((md_file, meta))

    return collection_files


async def ingest_collection(
    collection_name: str,
    files: list[tuple[Path, dict]],
    dry_run: bool = False,
):
    """Indexa ficheros en una colección Qdrant."""
    client = get_qdrant()
    total_chunks = 0

    for filepath, meta in files:
        logger.info(f"  📄 {filepath.name} ({meta.get('source', '?')})")

        text = filepath.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)

        if len(body) < 200:
            logger.warning(f"    ⚠ Contenido muy corto ({len(body)} chars), saltando")
            continue

        # Limpiar URLs/navegación que explotan el tokenizer de Ollama
        body = clean_markdown_for_embedding(body)

        # Chunk markdown
        chunk_dicts = chunk_markdown(
            body, max_chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        logger.info(f"    → {len(chunk_dicts)} chunks")

        if dry_run:
            total_chunks += len(chunk_dicts)
            continue

        # Embed + upsert en batches
        for batch_start in range(0, len(chunk_dicts), BATCH_SIZE):
            batch = chunk_dicts[batch_start:batch_start + BATCH_SIZE]
            batch_texts = [c["text"] for c in batch]

            try:
                embeddings = await embed_texts(batch_texts)
            except Exception as e:
                logger.error(f"    Error embeddings: {e}")
                continue

            points = []
            for i, (chunk_dict, emb) in enumerate(zip(batch, embeddings)):
                chunk_idx = batch_start + i
                point_id = str(uuid5(NAMESPACE_URL, f"agro:{filepath.name}:{chunk_idx}"))

                vector_data: dict = {"dense": emb}
                sparse_idx, sparse_val = compute_sparse_vector(chunk_dict["text"])
                if sparse_idx:
                    vector_data["bm25"] = SparseVector(indices=sparse_idx, values=sparse_val)

                points.append(PointStruct(
                    id=point_id,
                    vector=vector_data,
                    payload={
                        "text": chunk_dict["text"],
                        "source_file": filepath.name,
                        "source_site": meta.get("source", "unknown"),
                        "species": meta.get("species", "unknown"),
                        "url": meta.get("url", ""),
                        "title": meta.get("title", ""),
                        "chunk_index": chunk_idx,
                        "section": chunk_dict.get("section", ""),
                        "collection": collection_name,
                        "document_type": "agro_site_article",
                    },
                ))

            try:
                client.upsert(collection_name=collection_name, points=points)
                total_chunks += len(points)
            except Exception as e:
                logger.error(f"    Error Qdrant upsert: {e}")

    logger.info(f"  ✅ {collection_name}: {total_chunks} chunks indexados")
    return total_chunks


async def main():
    parser = argparse.ArgumentParser(description="Ingesta agro_sites en Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="Solo contar chunks")
    args = parser.parse_args()

    logger.info(f"📚 Ingesta de sitios agropecuarios → Qdrant")
    logger.info(f"   Directorio: {AGRO_DIR}")

    embed_dim = await get_embedding_dimension()
    logger.info(f"   Dimensión embeddings: {embed_dim}")

    await ensure_collections(embed_dim=embed_dim)

    collection_files = discover_files()
    if not collection_files:
        logger.error("No se encontraron archivos para indexar")
        return

    for cname, files in collection_files.items():
        logger.info(f"\n📂 Colección: {cname} ({len(files)} archivos)")

    grand_total = 0
    for cname, files in collection_files.items():
        logger.info(f"\n🔄 Indexando {cname} ({len(files)} archivos)...")
        count = await ingest_collection(cname, files, dry_run=args.dry_run)
        grand_total += count

    action = "contados (dry-run)" if args.dry_run else "indexados"
    logger.info(f"\n🎉 Completado: {grand_total} chunks {action}")

    await close_embeddings()
    close_qdrant()


if __name__ == "__main__":
    asyncio.run(main())
