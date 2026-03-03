"""Seedy Backend — Chunker: divide documentos en fragmentos para Qdrant."""

import re


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
