#!/usr/bin/env python3
"""
Seedy — Ingesta de artículos CarlosStro (Markdown → Qdrant).

Lee los .md descargados del NAS y los ingesta en la colección 'nutricion'
de Qdrant con embeddings mxbai-embed-large (1024d) + BM25 sparse.
"""

import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

import requests

OLLAMA_URL = "http://localhost:11434"
QDRANT_URL = "http://localhost:6333"
NAS_PATH = "/run/user/1000/gvfs/smb-share:server=192.168.30.100,share=datos/Fran"
COLLECTION = "nutricion"
EMBED_MODEL = "mxbai-embed-large"
CHUNK_SIZE = 600  # chars target per chunk
CHUNK_OVERLAP = 80
EMBED_MAX_CHARS = 800

# Páginas meta que NO son artículos
SKIP_FILES = {
    "Descargas.md", "Gestión de suscripción y compras.md",
    "miembros_irene-masullo.md", "miembros_pablogallego.md",
    "register.md", "Webinarios.md", "Sistema de rangos y puntos.md",
    "soporte.md", "reflexiones.md", "Quiénes somos.md",
}

_STOPWORDS = frozenset(
    "de la el en los las un una del al con por para es que se su no lo más"
    " como pero ya o si le este esta ese esa estos estas esos esas"
    " ser estar haber tener ir poder decir hacer ver dar saber querer"
    " a ante bajo cabe contra desde durante entre hacia hasta mediante"
    " otro otra otros otras muy también así donde cuando todo toda todos todas"
    " me te nos os les mi tu mis tus nuestro nuestra nuestros nuestras"
    .split()
)


def chunk_text(text: str, title: str) -> list[dict]:
    """Split markdown text into semantic chunks around paragraph boundaries."""
    # Split by double newline (paragraphs) or headings
    sections = re.split(r'\n(?=#{1,4}\s)', text)
    chunks = []

    for section in sections:
        paragraphs = re.split(r'\n\n+', section.strip())
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) < CHUNK_SIZE:
                current = (current + "\n\n" + para).strip()
            else:
                if current and len(current) > 50:
                    chunks.append(current)
                if len(para) > CHUNK_SIZE * 2:
                    # Split very long paragraphs
                    words = para.split()
                    sub = ""
                    for w in words:
                        if len(sub) + len(w) > CHUNK_SIZE:
                            if sub:
                                chunks.append(sub.strip())
                            sub = w
                        else:
                            sub = sub + " " + w if sub else w
                    if sub and len(sub) > 50:
                        chunks.append(sub.strip())
                    current = ""
                else:
                    current = para
        if current and len(current) > 50:
            chunks.append(current)

    return [{"text": c, "title": title, "chunk_index": i}
            for i, c in enumerate(chunks)]


def embed_text(text: str) -> list[float]:
    """Get embedding from Ollama."""
    clean = re.sub(r'[\.…]{3,}', '... ', text)
    clean = re.sub(r'[\u2014\u2013\-_]{3,}', ' ', clean)
    clean = re.sub(r'\s{2,}', ' ', clean).strip()[:EMBED_MAX_CHARS]

    resp = requests.post(f"{OLLAMA_URL}/api/embeddings",
                         json={"model": EMBED_MODEL, "prompt": clean}, timeout=30)
    resp.raise_for_status()
    return resp.json()["embedding"]


def compute_sparse(text: str) -> dict:
    """BM25-like sparse vector."""
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    tokens = [t for t in tokens if t not in _STOPWORDS]
    if not tokens:
        return {}
    tf = Counter(tokens)
    indices, values = [], []
    for token, count in sorted(tf.items()):
        idx = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) % (2**31)
        indices.append(idx)
        values.append(float(count))
    return {"indices": indices, "values": values}


def upsert_points(points: list[dict]):
    """Upsert batch to Qdrant."""
    resp = requests.put(
        f"{QDRANT_URL}/collections/{COLLECTION}/points",
        json={"points": points}, timeout=30
    )
    if resp.status_code not in (200, 201):
        print(f"  ❌ Qdrant upsert failed: {resp.status_code} {resp.text[:200]}")
        return False
    return True


def main():
    nas = Path(NAS_PATH)
    if not nas.exists():
        print(f"❌ NAS no accesible: {NAS_PATH}")
        sys.exit(1)

    # Verify Qdrant collection exists
    resp = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}")
    if resp.status_code != 200:
        print(f"❌ Colección '{COLLECTION}' no existe en Qdrant")
        sys.exit(1)
    before_count = resp.json()["result"]["points_count"]

    md_files = sorted(nas.glob("*.md"))
    articles = [f for f in md_files if f.name not in SKIP_FILES]
    print(f"📄 {len(articles)} artículos a ingestar en '{COLLECTION}'")
    print(f"   Puntos antes: {before_count}")
    print()

    total_chunks = 0
    total_points = 0

    for i, md_path in enumerate(articles, 1):
        title = md_path.stem
        text = md_path.read_text(encoding="utf-8")

        if len(text.strip()) < 100:
            print(f"  [{i}/{len(articles)}] ⏭ Demasiado corto: {title}")
            continue

        chunks = chunk_text(text, title)
        if not chunks:
            print(f"  [{i}/{len(articles)}] ⏭ Sin chunks: {title}")
            continue

        points = []
        for chunk in chunks:
            try:
                emb = embed_text(chunk["text"])
            except Exception as e:
                print(f"    ⚠ Error embedding chunk {chunk['chunk_index']}: {e}")
                continue

            point_id = str(uuid5(NAMESPACE_URL,
                                 f"stro:{title}:{chunk['chunk_index']}"))
            vector_data = {"dense": emb}
            sparse = compute_sparse(chunk["text"])
            if sparse:
                vector_data["bm25"] = sparse

            points.append({
                "id": point_id,
                "vector": vector_data,
                "payload": {
                    "text": chunk["text"],
                    "source_file": f"CarlosStro - {title}.md",
                    "chunk_index": chunk["chunk_index"],
                    "section": "",
                    "collection": COLLECTION,
                    "document_type": "web_article",
                    "title": title,
                    "language": "es",
                    "topics": ["nutricion", "salud", "biohacking", "luz_solar",
                               "circadian", "leptina"],
                    "source_origin": "carlosstro.com",
                },
            })

        # Upsert in batches of 20
        batch_ok = 0
        for b in range(0, len(points), 20):
            batch = points[b:b+20]
            if upsert_points(batch):
                batch_ok += len(batch)

        total_chunks += len(chunks)
        total_points += batch_ok
        size_kb = len(text) / 1024
        print(f"  [{i}/{len(articles)}] ✅ {title} ({len(chunks)} chunks, "
              f"{size_kb:.0f}KB → {batch_ok} pts)")

    # Verify
    resp = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}")
    after_count = resp.json()["result"]["points_count"]

    print()
    print("=" * 60)
    print(f"✅ Ingesta completada")
    print(f"   Artículos procesados: {len(articles)}")
    print(f"   Chunks generados: {total_chunks}")
    print(f"   Puntos insertados: {total_points}")
    print(f"   Qdrant '{COLLECTION}': {before_count} → {after_count} puntos")


if __name__ == "__main__":
    main()
