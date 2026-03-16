#!/usr/bin/env python3
"""
Migra documentos de Dify Knowledge Base → Qdrant (colecciones de Seedy).
- Extrae segmentos de cada documento vía API de Dify
- Clasifica cada documento en la colección Qdrant correcta
- Genera embeddings (mxbai-embed-large) y sparse vectors (BM25)
- Indexa en Qdrant con el mismo formato que el backend de Seedy

Uso:
    python migrate_dify_to_qdrant.py [--dry-run] [--limit N]
"""

import argparse
import hashlib
import json
import re
import sys
import time
import uuid
from typing import Optional

import requests

# ── Config ──────────────────────────────────────────────
DIFY_BASE = "http://localhost:3002/v1"
DIFY_API_KEY = "dataset-seedyNeoFarm2026kb"
DIFY_DATASET_ID = "880d67ee-3bd3-40ce-a457-ef46a3ad6be6"

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "mxbai-embed-large"
EMBED_MAX_CHARS = 800

QDRANT_URL = "http://localhost:6333"
NAMESPACE_URL = uuid.NAMESPACE_URL

# ── Clasificación de documentos → colecciones ──────────
KEYWORDS_TO_COLLECTION = {
    "avicultura": [
        "poultry", "chicken", "broiler", "layer", "hen", "rooster",
        "egg", "hatchab", "incubat", "avicul", "gallina", "pollo",
        "capón", "capon", "fowl", "duck", "quail", "turkey",
        "pavo", "pato", "codorniz", "coccidi", "salmonella",
        "newcastle", "marek", "gumboro", "avian", "plumage",
    ],
    "genetica": [
        "genetic", "genómic", "genome", "gwas", "snp", "qtl",
        "heritab", "breed", "raza", "selección genética",
        "ebv", "gebv", "consanguini", "inbreeding", "crossbre",
        "fleckvieh", "hybri", "haplotyp", "allel", "polymorph",
    ],
    "nutricion": [
        "nutri", "diet", "amino acid", "protein", "lysine",
        "methionine", "calcium", "phosphor", "vitamin",
        "probiotic", "prebiotic", "synbiotic", "feed additive",
        "formulaci", "ración", "pienso", "soybean", "corn",
        "phytase", "enzyme", "supplement",
    ],
    "normativa": [
        "normativ", "regulat", "legisl", "directiva", "boe",
        "reglamento", "real decreto", "bienestar animal",
        "welfare", "pnt-", "sige", "trazabilidad",
    ],
    "iot_hardware": [
        "iot", "sensor", "hardware", "mqtt", "esp32",
        "monitor", "smart farm", "precision livestock",
        "plc", "raspberry", "arduino",
    ],
    "digital_twins": [
        "digital twin", "gemelo digital", "simulat",
        "cfd", "model", "3d", "twin",
    ],
    "estrategia": [
        "estrategi", "mercado", "market", "competit",
        "viabilidad", "inversor", "negocio", "plan",
        "extensiv", "intensiv", "dehesa", "pastoreo",
        "ecológi", "orgánic", "silvo", "holíst",
    ],
    "geotwin": [
        "geotwin", "gis", "catastro", "parcela",
        "dem", "terrain", "ortofoto",
    ],
}

# Fallback collection when no keyword matches
DEFAULT_COLLECTION = "estrategia"


def classify_document(name: str, text_sample: str) -> str:
    """Classify a document into a Qdrant collection based on name + content."""
    combined = (name + " " + text_sample).lower()
    scores: dict[str, int] = {}
    for collection, keywords in KEYWORDS_TO_COLLECTION.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[collection] = score
    if not scores:
        return DEFAULT_COLLECTION
    return max(scores, key=scores.get)


# ── Stopwords & BM25 sparse ────────────────────────────
STOPWORDS = set(
    "de la el en y a los las del un una por con para al es que se lo su"
    " no le da más o son fue ha ser está como pero sus ya entre cuando"
    " the a an and is it of to in for on with as by at from or be was"
    " this that are were has have had been will would can could may"
    " their its not but all also into than other".split()
)
_TOKEN_RE = re.compile(r"\b\w{2,}\b")


def _sparse_vector(text: str) -> tuple[list[int], list[float]]:
    tokens = _TOKEN_RE.findall(text.lower())
    tf: dict[int, int] = {}
    for t in tokens:
        if t in STOPWORDS:
            continue
        idx = int(hashlib.md5(t.encode()).hexdigest()[:8], 16) % (2**31)
        tf[idx] = tf.get(idx, 0) + 1
    indices = sorted(tf.keys())
    values = [float(tf[i]) for i in indices]
    return indices, values


# ── Embedding ──────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
    truncated = text[:EMBED_MAX_CHARS]
    resp = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": truncated},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    embeddings = data.get("embeddings") or [data.get("embedding", [])]
    return embeddings[0]


# ── Dify API helpers ───────────────────────────────────
def dify_headers():
    return {"Authorization": f"Bearer {DIFY_API_KEY}"}


def get_all_documents() -> list[dict]:
    docs = []
    page = 1
    while True:
        r = requests.get(
            f"{DIFY_BASE}/datasets/{DIFY_DATASET_ID}/documents",
            params={"limit": 100, "page": page},
            headers=dify_headers(),
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("data", [])
        if not batch:
            break
        docs.extend(batch)
        if not data.get("has_more"):
            break
        page += 1
    return docs


def get_document_segments(doc_id: str) -> list[dict]:
    segments = []
    page = 1  # Dify doesn't support pagination well for segments, get all
    while True:
        r = requests.get(
            f"{DIFY_BASE}/datasets/{DIFY_DATASET_ID}/documents/{doc_id}/segments",
            params={"limit": 500},
            headers=dify_headers(),
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("data", [])
        segments.extend(batch)
        if not data.get("has_more"):
            break
        page += 1
    return segments


# ── Qdrant upserting ───────────────────────────────────
def get_existing_sources(collection: str) -> set[str]:
    sources = set()
    offset = None
    while True:
        body: dict = {"limit": 10000, "with_payload": ["source_file"]}
        if offset:
            body["offset"] = offset
        r = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        result = r.json().get("result", {})
        for p in result.get("points", []):
            sf = p.get("payload", {}).get("source_file", "")
            if sf:
                sources.add(sf)
        offset = result.get("next_page_offset")
        if not offset:
            break
    return sources


def upsert_points(collection: str, points: list[dict]):
    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        r = requests.put(
            f"{QDRANT_URL}/collections/{collection}/points",
            json={"points": batch},
            timeout=120,
        )
        r.raise_for_status()


def make_point_id(source: str, chunk_idx: int) -> str:
    raw = f"dify:{source}:{chunk_idx}"
    return str(uuid.uuid5(NAMESPACE_URL, raw))


# ── Rechunking ─────────────────────────────────────────
def rechunk(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to cut at paragraph, newline, or space
            for sep in ["\n\n", "\n", ". ", " "]:
                idx = text.rfind(sep, start + chunk_size // 2, end)
                if idx > start:
                    end = idx + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]


# ── Main ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Migrate Dify KB → Qdrant")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max docs to process")
    args = parser.parse_args()

    print("Fetching Dify documents...")
    all_docs = get_all_documents()
    print(f"  Total in Dify: {len(all_docs)}")

    # Get existing Qdrant sources
    print("Loading existing Qdrant sources...")
    all_qdrant_sources: set[str] = set()
    collections = [
        "avicultura", "estrategia", "genetica", "normativa",
        "iot_hardware", "nutricion", "fresh_web", "digital_twins", "geotwin",
    ]
    for c in collections:
        sources = get_existing_sources(c)
        all_qdrant_sources.update(sources)
    print(f"  Qdrant unique sources: {len(all_qdrant_sources)}")

    # Filter docs to migrate
    to_migrate = []
    for d in all_docs:
        name = d["name"]
        if d["indexing_status"] != "completed":
            continue
        if name.endswith(".csv"):
            continue
        if d["word_count"] > 500000:
            continue
        # Check if already in Qdrant
        if name in all_qdrant_sources:
            continue
        base = name.rsplit(".", 1)[0] if "." in name else name
        if any(base in s for s in all_qdrant_sources):
            continue
        to_migrate.append(d)

    # Remove docx duplicates where md exists
    md_bases = set(
        d["name"].rsplit(".", 1)[0]
        for d in to_migrate
        if d["name"].endswith(".md")
    )
    to_migrate = [
        d
        for d in to_migrate
        if not (d["name"].endswith(".docx") and d["name"].rsplit(".", 1)[0] in md_bases)
    ]

    if args.limit:
        to_migrate = to_migrate[: args.limit]

    print(f"  Documents to migrate: {len(to_migrate)}")
    if args.dry_run:
        for d in to_migrate:
            print(f"    {d['word_count']:>8d}w  {d['name']}")
        return

    # Process each document
    stats = {"docs": 0, "chunks": 0, "errors": 0}
    for i, doc in enumerate(to_migrate, 1):
        doc_name = doc["name"]
        doc_id = doc["id"]
        ext = doc_name.rsplit(".", 1)[-1] if "." in doc_name else "txt"

        print(f"\n[{i}/{len(to_migrate)}] {doc_name} ({doc['word_count']}w)...")

        try:
            # Get all segments from Dify
            segments = get_document_segments(doc_id)
            if not segments:
                print(f"  ⚠ No segments, skipping")
                continue

            # Concatenate all segment texts
            full_text = "\n\n".join(
                s.get("content", "") for s in segments if s.get("content")
            )
            if not full_text.strip():
                print(f"  ⚠ Empty content, skipping")
                continue

            # Classify document
            sample = full_text[:2000]
            collection = classify_document(doc_name, sample)
            print(f"  → collection: {collection}")

            # Rechunk with Seedy's settings
            chunks = rechunk(full_text, chunk_size=800, overlap=150)
            print(f"  → {len(chunks)} chunks")

            # Build Qdrant points
            points = []
            for idx, chunk_text in enumerate(chunks):
                if not chunk_text.strip():
                    continue
                point_id = make_point_id(doc_name, idx)
                embedding = get_embedding(chunk_text)
                sp_indices, sp_values = _sparse_vector(chunk_text)

                point = {
                    "id": point_id,
                    "vector": {
                        "dense": embedding,
                        "bm25": {"indices": sp_indices, "values": sp_values},
                    },
                    "payload": {
                        "text": chunk_text,
                        "source_file": doc_name,
                        "chunk_index": idx,
                        "section": "",
                        "collection": collection,
                        "document_type": ext,
                        "source_origin": "dify_migration",
                    },
                }
                points.append(point)

            # Upsert to Qdrant
            upsert_points(collection, points)
            stats["docs"] += 1
            stats["chunks"] += len(points)
            print(f"  ✓ {len(points)} chunks → {collection}")

            # Rate limit Ollama embedding calls
            time.sleep(0.1)

        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats["errors"] += 1
            continue

    print(f"\n{'='*50}")
    print(f"Migration complete!")
    print(f"  Documents: {stats['docs']}")
    print(f"  Chunks indexed: {stats['chunks']}")
    print(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
