"""Seedy Backend — Chunker: divide documentos en fragmentos para Qdrant."""

import hashlib
import re
from collections import Counter


def chunk_text(
    text: str,
    chunk_size: int = 1500,
    chunk_overlap: int = 300,
) -> list[str]:
    """
    Divide texto en chunks con overlap.
    Intenta cortar en fronteras de párrafo para mantener coherencia.
    """
    if not text or not text.strip():
        return []

    # Limpiar whitespace excesivo
    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Intentar cortar en un párrafo (doble salto de línea)
        cut = text.rfind("\n\n", start + chunk_size // 2, end)
        if cut == -1:
            # Intentar cortar en un salto de línea simple
            cut = text.rfind("\n", start + chunk_size // 2, end)
        if cut == -1:
            # Intentar cortar en un espacio
            cut = text.rfind(" ", start + chunk_size // 2, end)
        if cut == -1:
            cut = end

        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)

        # Siguiente chunk con overlap
        start = max(cut - chunk_overlap, start + 1)

    return chunks


def extract_text_from_md(filepath: str) -> str:
    """Lee un archivo Markdown."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def extract_text_from_pdf(filepath: str) -> str:
    """Extrae texto de un PDF."""
    from PyPDF2 import PdfReader

    reader = PdfReader(filepath)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def extract_text_from_docx(filepath: str) -> str:
    """Extrae texto de un .docx."""
    from docx import Document

    doc = Document(filepath)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_text_from_csv(filepath: str) -> str:
    """Lee un CSV como texto."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def extract_text(filepath: str) -> str:
    """Extrae texto de un archivo según su extensión."""
    ext = filepath.lower().rsplit(".", 1)[-1]

    extractors = {
        "md": extract_text_from_md,
        "pdf": extract_text_from_pdf,
        "docx": extract_text_from_docx,
        "csv": extract_text_from_csv,
        "txt": extract_text_from_md,
    }

    extractor = extractors.get(ext)
    if extractor is None:
        raise ValueError(f"Formato no soportado: .{ext}")

    return extractor(filepath)


# ── Chunking markdown por secciones ──────────────────

def chunk_markdown(
    text: str,
    max_chunk_size: int = 1500,
    chunk_overlap: int = 200,
) -> list[dict]:
    """
    Divide un documento Markdown respetando secciones (## headers).
    Devuelve lista de dicts con: text, section, sub_chunk.
    Las subsecciones (###) se mantienen dentro de su sección padre.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    chunks: list[dict] = []

    # Split on ## headers (level 2), keeping the delimiter
    parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract section title from ## header
        header_match = re.match(r"^##\s+(.+?)(?:\n|$)", part)
        section = header_match.group(1).strip() if header_match else "Introducción"

        if len(part) <= max_chunk_size:
            chunks.append({"text": part, "section": section, "sub_chunk": 0})
        else:
            # Sub-chunk large sections preserving overlap
            sub_chunks = chunk_text(part, max_chunk_size, chunk_overlap)
            for j, sc in enumerate(sub_chunks):
                chunks.append({"text": sc, "section": section, "sub_chunk": j})

    return chunks


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
    """
    Genera un vector disperso (sparse) para búsqueda BM25-like.
    Devuelve (indices, values) para qdrant SparseVector.
    Los índices son hashes determinísticos de cada token único;
    los valores son frecuencias de término (TF).
    Qdrant aplica IDF automáticamente si la colección usa Modifier.IDF.
    """
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

    return extractor(filepath)
