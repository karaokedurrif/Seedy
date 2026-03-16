#!/usr/bin/env python3
"""
Seedy — Ingesta masiva de documentos en /conocimientos/Carga de documentos nuevos/

Soporta: PDF, MD, DOCX, CSV, EPUB
Clasifica automáticamente cada documento en la colección Qdrant adecuada
según keywords del título y contenido.
"""

import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

import fitz  # PyMuPDF
import requests

# ── Config ──
OLLAMA_URL = "http://localhost:11434"
QDRANT_URL = "http://localhost:6333"
EMBED_MODEL = "mxbai-embed-large"
CHUNK_SIZE = 600
EMBED_MAX_CHARS = 800

DOCS_DIR = Path("/home/davidia/Documentos/Seedy/conocimientos/Carga de documentos nuevos")

# ── Clasificación por colección basada en keywords ──
COLLECTION_KEYWORDS = {
    "digital_twins": [
        "digital twin", "gemelo digital", "smart farm", "precision farm",
        "iot", "lora", "lorawan", "sensor", "monitoriz", "smart agri",
        "precision livestock", "ganadería de precisión", "ganadería precisión",
        "telemetr", "wearable", "rfid",
    ],
    "geotwin": [
        "gis", "sigpac", "teledetec", "remote sens", "geoesp", "cartograf",
        "spatial", "lidar", "dron", "uav", "satélit", "ndvi",
        "modelado 3d", "3d model",
    ],
    "avicultura": [
        "avícol", "avicul", "poultry", "chicken", "pollo", "gallina", "hen",
        "huevo", "egg", "laying", "puesta", "broiler", "capón", "capon",
        "incubaci", "hatch", "coccidio", "salmonella poultry", "campero",
        "aves de corral", "rapaz", "pluma",
    ],
    "nutricion": [
        "nutri", "pienso", "feed", "formulaci", "amino", "proteín", "protein",
        "vitamin", "mineral", "metabol", "digest", "fiber", "fibra",
        "probiot", "prebiot", "aditiv", "additive", "antibiot", "coccidio",
        "ensilad", "silage", "ración", "dieta animal", "engorde",
    ],
    "genetica": [
        "genét", "genetic", "genom", "gwas", "qtl", "allel", "alelo",
        "raza", "breed", "cruce", "cross", "hibrid", "consanguin",
        "selección", "selection", "mejora genética", "polimorf", "snp",
        "biodiversi", "autócton", "heritage",
    ],
    "normativa": [
        "normativ", "regulaci", "legisl", "real decreto", "boe", "ley ",
        "directiv", "bienestar animal", "animal welfare", "pac ",
        "ecogan", "trazab", "traceab", "mtd", "bref", "sanidad",
        "convenio", "programa nacional", "inventario", "censo ganadero",
    ],
    "estrategia": [
        "estrateg", "plan nacional", "política", "policy", "competitiv",
        "mercado", "market", "export", "rentabil", "viabil", "financ",
        "economía", "economi", "cadena de valor", "supply chain",
        "prospectiv", "sostenibil", "sustainab", "extensiv", "intensiv",
        "dehesa", "pastoral", "impact", "cambio climátic",
    ],
}

# Fallback collection for unclassified docs
DEFAULT_COLLECTION = "estrategia"

_STOPWORDS = frozenset(
    "de la el en los las un una del al con por para es que se su no lo más"
    " como pero ya o si le este esta ese esa estos estas esos esas"
    " ser estar haber tener ir poder decir hacer ver dar saber querer"
    " a ante bajo cabe contra desde durante entre hacia hasta mediante"
    " otro otra otros otras muy también así donde cuando todo toda todos todas"
    " me te nos os les mi tu mis tus nuestro nuestra nuestros nuestras"
    " the a an in of to and is for on with that this from by at or be"
    " was were are been has have had do does not its can will may it"
    .split()
)


def classify_document(title: str, text_sample: str) -> str:
    """Classify a document into the best Qdrant collection."""
    combined = f"{title} {text_sample[:3000]}".lower()
    scores = {}
    for collection, keywords in COLLECTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        # Boost exact title matches
        title_lower = title.lower()
        score += sum(2 for kw in keywords if kw in title_lower)
        scores[collection] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return DEFAULT_COLLECTION
    return best


def extract_pdf(path: Path) -> tuple[str, str]:
    """Extract title and text from PDF."""
    doc = fitz.open(str(path))
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    full_text = "\n".join(text_parts)

    # Title: try first meaningful line or filename
    lines = [l.strip() for l in full_text.split("\n") if l.strip() and len(l.strip()) > 5]
    title = lines[0][:150] if lines else path.stem
    # If title is too generic, use filename
    if len(title) < 10 or title.lower().startswith(("http", "doi:", "©")):
        title = path.stem

    return title, full_text


def extract_md(path: Path) -> tuple[str, str]:
    """Extract title and text from Markdown."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Title from first heading or filename
    m = re.search(r'^#\s+(.+)', text, re.MULTILINE)
    title = m.group(1).strip() if m else path.stem
    return title, text


def extract_docx(path: Path) -> tuple[str, str]:
    """Extract text from DOCX using python-docx or fallback to zipfile."""
    try:
        from docx import Document
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        title = paragraphs[0][:150] if paragraphs else path.stem
        return title, "\n\n".join(paragraphs)
    except ImportError:
        # Fallback: extract from zip
        import zipfile
        from xml.etree import ElementTree
        with zipfile.ZipFile(str(path)) as z:
            with z.open("word/document.xml") as f:
                tree = ElementTree.parse(f)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for p in tree.findall(".//w:p", ns):
            texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
            if texts:
                paragraphs.append("".join(texts))
        title = paragraphs[0][:150] if paragraphs else path.stem
        return title, "\n\n".join(paragraphs)


def extract_csv(path: Path) -> tuple[str, str]:
    """Extract text from CSV (CDA exports, etc.)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    title = f"Datos CDA: {path.stem}"
    return title, text


def extract_text(path: Path) -> tuple[str, str]:
    """Route extraction by file type."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    elif ext == ".md":
        return extract_md(path)
    elif ext == ".docx":
        return extract_docx(path)
    elif ext == ".csv":
        return extract_csv(path)
    else:
        return path.stem, ""


def chunk_text(text: str, title: str) -> list[dict]:
    """Split text into semantic chunks."""
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


def upsert_points(collection: str, points: list[dict]):
    """Upsert batch to Qdrant."""
    resp = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        json={"points": points}, timeout=60
    )
    if resp.status_code not in (200, 201):
        print(f"  ❌ Qdrant upsert failed: {resp.status_code} {resp.text[:200]}")
        return 0
    return len(points)


def ingest_document(path: Path, collection: str, title: str, text: str) -> int:
    """Chunk, embed and ingest a document into Qdrant. Returns points inserted."""
    chunks = chunk_text(text, title)
    if not chunks:
        return 0

    points = []
    for ch in chunks:
        point_id = str(uuid5(NAMESPACE_URL, f"{path.name}:{ch['chunk_index']}"))
        vec = embed_text(ch["text"])
        sparse = compute_sparse(ch["text"])

        point = {
            "id": point_id,
            "vector": {
                "dense": vec,
                "bm25": sparse,
            },
            "payload": {
                "text": ch["text"],
                "title": ch["title"],
                "chunk_index": ch["chunk_index"],
                "source": path.name,
                "source_type": path.suffix.lower(),
                "collection": collection,
            }
        }
        points.append(point)

        # Batch upsert every 20 points
        if len(points) >= 20:
            upsert_points(collection, points)
            points = []

    if points:
        upsert_points(collection, points)

    return len(chunks)


def collect_files(base: Path) -> list[Path]:
    """Recursively collect processable files."""
    exts = {".pdf", ".md", ".docx", ".csv"}
    files = []
    for f in sorted(base.rglob("*")):
        if f.is_file() and f.suffix.lower() in exts:
            # Skip images and tiny files
            if f.stat().st_size < 500:
                continue
            files.append(f)
    return files


def main():
    if not DOCS_DIR.exists():
        print(f"❌ Directorio no encontrado: {DOCS_DIR}")
        sys.exit(1)

    # Verify Qdrant is up
    try:
        requests.get(f"{QDRANT_URL}/collections", timeout=5).raise_for_status()
    except Exception:
        print("❌ Qdrant no accesible")
        sys.exit(1)

    # Get initial point counts
    resp = requests.get(f"{QDRANT_URL}/collections", timeout=10).json()
    before = {}
    for c in resp["result"]["collections"]:
        info = requests.get(f"{QDRANT_URL}/collections/{c['name']}", timeout=10).json()
        before[c["name"]] = info["result"]["points_count"]

    files = collect_files(DOCS_DIR)
    print(f"📄 {len(files)} documentos encontrados")
    print(f"   Tipos: {Counter(f.suffix.lower() for f in files)}")
    print()

    # Classify all documents first
    classified = {}  # collection -> list of (path, title, text)
    skipped = 0

    for i, path in enumerate(files, 1):
        try:
            title, text = extract_text(path)
        except Exception as e:
            print(f"  [{i}/{len(files)}] ⚠️  Error extrayendo {path.name}: {e}")
            skipped += 1
            continue

        if not text or len(text.strip()) < 100:
            skipped += 1
            continue

        collection = classify_document(title, text)
        classified.setdefault(collection, []).append((path, title, text))

    print("📊 Clasificación:")
    for col, docs in sorted(classified.items(), key=lambda x: -len(x[1])):
        print(f"   {col:20s}: {len(docs):3d} documentos")
    print(f"   {'(descartados)':20s}: {skipped:3d}")
    print()

    # Process each collection
    total_chunks = 0
    total_docs = 0

    for collection, docs in sorted(classified.items()):
        print(f"\n{'='*60}")
        print(f"📦 Colección: {collection} ({len(docs)} docs)")
        print(f"{'='*60}")

        for j, (path, title, text) in enumerate(docs, 1):
            n = ingest_document(path, collection, title, text)
            total_chunks += n
            total_docs += 1
            print(f"  [{j}/{len(docs)}] ✅ {n:4d} chunks ← {path.name[:60]}")

    # Final report
    print(f"\n{'='*60}")
    print(f"✅ INGESTA COMPLETADA")
    print(f"   Documentos procesados: {total_docs}")
    print(f"   Chunks totales: {total_chunks}")
    print(f"   Descartados: {skipped}")
    print(f"\n   Evolución por colección:")

    resp = requests.get(f"{QDRANT_URL}/collections", timeout=10).json()
    for c in sorted(resp["result"]["collections"], key=lambda x: x["name"]):
        name = c["name"]
        info = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=10).json()
        after = info["result"]["points_count"]
        diff = after - before.get(name, 0)
        if diff > 0:
            print(f"   {name:20s}: {before.get(name,0):>8,d} → {after:>8,d} (+{diff:,d})")
        else:
            print(f"   {name:20s}: {after:>8,d} (sin cambios)")


if __name__ == "__main__":
    main()
