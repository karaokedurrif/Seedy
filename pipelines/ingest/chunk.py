"""Pipeline de autoingesta — Chunker: reutiliza lógica del backend."""

import sys
import os
import re
import hashlib
from collections import Counter

# ── Reimplementación directa para independencia del backend ──
# (Misma lógica que backend/ingestion/chunker.py pero sin dependencia de imports)


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> list[str]:
    """Divide texto en chunks con overlap."""
    if not text or not text.strip():
        return []

    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        cut = text.rfind("\n\n", start + chunk_size // 2, end)
        if cut == -1:
            cut = text.rfind("\n", start + chunk_size // 2, end)
        if cut == -1:
            cut = text.rfind(" ", start + chunk_size // 2, end)
        if cut == -1:
            cut = end

        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)

        start = max(cut - chunk_overlap, start + 1)

    return chunks


def chunk_for_ingest(
    text: str,
    title: str = "",
    source_name: str = "",
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> list[dict]:
    """
    Divide texto de un artículo en chunks con metadata.
    Devuelve lista de dicts con: text, chunk_index, title, source.
    """
    raw_chunks = chunk_text(text, chunk_size, chunk_overlap)

    return [
        {
            "text": c,
            "chunk_index": i,
            "title": title,
            "source": source_name,
        }
        for i, c in enumerate(raw_chunks)
    ]


# ── Sparse vector para BM25 ──────────────────────────

_STOPWORDS = frozenset({
    "de", "la", "el", "en", "y", "a", "los", "las", "que", "del", "un", "una",
    "por", "con", "no", "es", "se", "para", "su", "al", "lo", "como", "más",
    "o", "pero", "me", "ya", "esto", "le", "si", "entre", "cuando", "muy",
    "sin", "sobre", "también", "fue", "ser", "son", "tiene", "este", "esta",
    "the", "and", "is", "in", "to", "of", "for", "on", "it", "this", "that",
    "with", "are", "from", "or", "an", "be", "at", "by", "not", "was", "but",
})


def compute_sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """Genera vector disperso BM25: (indices, values)."""
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    tokens = [t for t in tokens if t not in _STOPWORDS]

    if not tokens:
        return [], []

    tf = Counter(tokens)
    indices: list[int] = []
    values: list[float] = []

    for token, count in sorted(tf.items()):
        idx = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) % (2**31)
        indices.append(idx)
        values.append(float(count))

    return indices, values
