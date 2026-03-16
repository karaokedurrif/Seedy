#!/usr/bin/env python3
"""
Ingest new content files into Qdrant collections.
Uses small batches and delays to avoid VRAM saturation.
"""
import hashlib
import json
import time
import uuid
import sys
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434"
QDRANT_URL = "http://localhost:6333"
EMBED_MODEL = "mxbai-embed-large"

CHUNK_SIZE = 200
CHUNK_OVERLAP = 40

# File → collection mapping
FILE_COLLECTIONS = {
    "ganaderia_holistica_pastoreo.md": "estrategia",
    "raza_sussex_completa.md": "avicultura",
}

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + size])
        chunks.append(chunk)
        i += size - overlap
    return chunks


def embed(text: str) -> list[float]:
    """Get embedding from Ollama."""
    r = requests.post(f"{OLLAMA_URL}/api/embeddings", json={
        "model": EMBED_MODEL,
        "prompt": text,
    }, timeout=120)
    r.raise_for_status()
    return r.json()["embedding"]


def simple_bm25_sparse(text: str) -> dict:
    """Build a simple sparse vector for BM25-like matching."""
    from collections import Counter
    import math
    words = text.lower().split()
    counts = Counter(words)
    total = len(words)
    idx_map = {}
    for word, count in counts.items():
        h = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 100_000
        tf = count / total
        val = tf * (1 + math.log(1 + count))
        idx_map[h] = idx_map.get(h, 0) + round(val, 6)
    return {"indices": list(idx_map.keys()), "values": list(idx_map.values())}


def ensure_collection(name: str):
    """Verify collection exists."""
    r = requests.get(f"{QDRANT_URL}/collections/{name}")
    if r.status_code != 200:
        print(f"  ERROR: Collection '{name}' not found!")
        sys.exit(1)


def upsert_points(collection: str, points: list):
    """Upsert points into Qdrant."""
    r = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        json={"points": points},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def ingest_file(filepath: Path, collection: str, batch_size: int = 5):
    """Ingest a single file into a Qdrant collection."""
    print(f"\n{'='*60}")
    print(f"Ingesting: {filepath.name} → {collection}")

    ensure_collection(collection)

    text = filepath.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    print(f"  {len(chunks)} chunks ({len(text)} chars)")

    total = len(chunks)
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_chunks = chunks[batch_start:batch_end]
        points = []

        for idx, chunk in enumerate(batch_chunks, start=batch_start):
            vec = embed(chunk)
            sparse = simple_bm25_sparse(chunk)
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{filepath.name}:{idx}"))
            points.append({
                "id": point_id,
                "vector": {
                    "dense": vec,
                    "bm25": sparse,
                },
                "payload": {
                    "text": chunk,
                    "source": filepath.name,
                    "chunk_index": idx,
                    "total_chunks": total,
                },
            })

        upsert_points(collection, points)
        print(f"  [{batch_end}/{total}] indexed", flush=True)

        # Small delay between batches to let VRAM breathe
        if batch_end < total:
            time.sleep(1)

    print(f"  Done: {total} chunks indexed into '{collection}'")


def main():
    content_dir = Path(__file__).parent / "content"

    if not content_dir.exists():
        print(f"ERROR: {content_dir} not found")
        sys.exit(1)

    files = list(content_dir.glob("*.md"))
    if not files:
        print("No .md files found in content/")
        sys.exit(1)

    print(f"Found {len(files)} content files")

    for f in files:
        collection = FILE_COLLECTIONS.get(f.name)
        if not collection:
            # Auto-classify based on keywords
            text_lower = f.read_text()[:2000].lower()
            if any(k in text_lower for k in ["gallina", "pollo", "avicul", "sussex", "raza"]):
                collection = "avicultura"
            elif any(k in text_lower for k in ["nutri", "pienso", "alimenta", "dieta"]):
                collection = "nutricion"
            elif any(k in text_lower for k in ["iot", "sensor", "hardware"]):
                collection = "iot_hardware"
            elif any(k in text_lower for k in ["norma", "ley", "regla", "boe"]):
                collection = "normativa"
            elif any(k in text_lower for k in ["digital twin", "gemelo"]):
                collection = "digital_twins"
            else:
                collection = "estrategia"
            print(f"  Auto-classified {f.name} → {collection}")

        ingest_file(f, collection)

    print(f"\nAll done!")


if __name__ == "__main__":
    main()
