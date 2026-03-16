#!/usr/bin/env python3
"""
Seedy — Ingesta de corpus histórico francés y español sobre capones y avicultura.

Procesa:
  - PDFs escaneados de Gallica/BnF (OCR con Tesseract fra/spa)
  - PDFs modernos con texto incrustado
  - DOCX, MD, TXT
  
Pipeline: Extracción → Detección idioma → OCR si necesario → Chunking →
          Embedding (mxbai-embed-large) → BM25 sparse → Upsert Qdrant (avicultura)
"""

import argparse
import hashlib
import os
import re
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF
import requests

# ── Configuración ────────────────────────────────────────────────────────────
QDRANT_URL   = "http://localhost:6333"
OLLAMA_URL   = "http://localhost:11434"
EMBED_MODEL  = "mxbai-embed-large"
COLLECTION   = "avicultura"   # Todos van a avicultura (capones/aves)

CHUNK_SIZE   = 600   # chars — cabe en 512 tokens de mxbai-embed-large
CHUNK_OVERLAP = 100
MAX_EMBED_CHARS = 1200  # truncación para embedding

# Umbral de caracteres/página para decidir si necesita OCR
OCR_THRESHOLD = 80  # Si <80 chars promedio/página → forzar OCR

# ── Documentos a procesar ────────────────────────────────────────────────────
# Cada entrada: (archivo, idioma_preferido, descripción corta, tipo)
DOCUMENTS = [
    # --- MANUALES FRANCESES HISTÓRICOS (clave para el proyecto) ---
    ("Aviculture___par_Charles_Voitellier_[...]Voitellier_Charles_bpt6k3410830q (1).pdf",
     "fra", "Voitellier — Aviculture (manual completo, ~1905)", "manual_fr"),
    ("Traité_pratique_de_l'éducation_des_[...]Espanet_Alexis_bpt6k3062273f.pdf",
     "fra", "Espanet — Traité pratique éducation poules/poulets (2e éd.)", "manual_fr"),
    ("Cours_complet_par_correspondance_Tome_[...]_bpt6k63898725.pdf",
     "fra", "Collège d'aviculture Château-Thierry — Cours complet T.2", "manual_fr"),
    ("La_Bresse_et_sa_volaille_[...]Dubost_Paul-Claude_bpt6k732100.pdf",
     "fra", "Dubost — La Bresse et sa volaille", "manual_fr"),
    ("La_Bresse_agricole___organe_[...]Comice_agricole_bpt6k5514585j.pdf",
     "fra", "La Bresse agricole — Comice agricole de Bourg", "manual_fr"),
    ("La_poule_de_Barbezieux___[...]Guéraud_de_bpt6k311800k.pdf",
     "fra", "Guéraud de Laharpe — La poule de Barbezieux", "manual_fr"),
    ("L'industrie_agricole___F_Convert_Convert_François_bpt6k63926552.pdf",
     "fra", "F. Convert — L'industrie agricole (secciones avícolas)", "manual_fr"),
    ("Le_vétérinaire_populaire_traité_pratique_[...]Gombault_J_bpt6k931864w.pdf",
     "fra", "J. Gombault — Le vétérinaire populaire (enfermedades aves)", "manual_fr"),

    # --- LABEL ROUGE / NORMATIVA MODERNA ---
    ("3cdc_volailles-argoat_2021.pdf",
     "fra", "Label Rouge LA 28/88 — Volailles d'Argoat (2021)", "label_rouge"),
    ("DOCUMENTO DE REFERENCIA: PLIEGOS DE CONDICIONES LABEL ROUGE (AVES DE ARGOAT).md",
     "spa", "Traducción pliegos Label Rouge Aves de Argoat", "label_rouge"),

    # --- CONTEXTO HISTÓRICO LA GRANJA / FELIPE V ---
    ("El-capon-sonado-de-La-Granja.pdf",
     "spa", "El capón soñado de La Granja — historia borbónica", "historia"),
    ("La_Granja_résidence_d'été_des_[...]_btv1b6403459k.pdf",
     "fra", "La Granja — résidence d'été des rois d'Espagne", "historia"),
    ("Mémoires_complets_et_authentiques_du_[...]Saint-Simon_Louis_bpt6k5790878w.pdf",
     "fra", "Saint-Simon — Mémoires (vida cortesana, gastronomía)", "historia"),
    ("Mémoires_complets_et_authentiques_du_[...]Saint-Simon_Louis_bpt6k70541.pdf",
     "fra", "Saint-Simon — Mémoires (vol. 2)", "historia"),
    ("Nouveau_voyage_en_Espagne_Marcillac_Louis_bpt6k57731264.pdf",
     "fra", "Marcillac — Nouveau voyage en Espagne", "historia"),
    ("articulo_prensa_capon_lagranja_romantico.pdf",
     "spa", "Artículo prensa — El capón romántico de La Granja", "historia"),

    # --- CORPUS RAG ESPAÑOL DE CAPONES Y CRUCES ---
    ("corpus_rag_capon_gourmet_hibridacion_gallinas.docx",
     "spa", "Corpus RAG capón gourmet + hibridación gallinas", "corpus_es"),
    ("corpus_rag_capon_gourmet_hibridacion_gallinas.md",
     "spa", "Corpus RAG capón gourmet (md)", "corpus_es"),
    ("estrategias_cruce_aves_gourmet_v2.docx",
     "spa", "Estrategias cruce aves gourmet v2", "corpus_es"),
    ("estrategias_cruce_aves_gourmet_RAG.md",
     "spa", "Estrategias cruce aves gourmet RAG (md)", "corpus_es"),
    ("programa_raza_capon_propia.docx",
     "spa", "Programa raza capón propia", "corpus_es"),
    ("programa_raza_capon_segoviano.docx",
     "spa", "Programa raza capón segoviano", "corpus_es"),
    ("articulo_prensa_capon_lagranja.docx",
     "spa", "Artículo prensa capón La Granja", "corpus_es"),
    ("articulo_prensa_capon_lagranja_romantico.docx",
     "spa", "Artículo prensa capón romántico La Granja", "corpus_es"),
    ("resumen_capón_lagranja_y_prompt_sora.docx",
     "spa", "Resumen capón La Granja", "corpus_es"),
    ("chat-Capones Españoles.txt",
     "spa", "Chat sobre capones españoles", "corpus_es"),
    ("chat-Gallinas Españolas 🐔.txt",
     "spa", "Chat sobre gallinas españolas", "corpus_es"),
]

SRC_DIR = Path("/home/davidia/Descargas")

# ── Utilidades ───────────────────────────────────────────────────────────────

_STOPWORDS = set(
    "the a an is are was were be been have has had do does did will would "
    "de del la el en y los las un una que es por con le les des du au aux "
    "et ou ne pas dans pour sur ce cette ces sont été avoir".split()
)


def compute_sparse(text: str) -> dict:
    """BM25-like sparse vector."""
    tokens = [t for t in re.findall(r"\b\w{2,}\b", text.lower()) if t not in _STOPWORDS]
    if not tokens:
        return {}
    tf = Counter(tokens)
    return {
        "indices": [int(hashlib.md5(t.encode()).hexdigest()[:8], 16) % (2**31) for t in sorted(tf)],
        "values":  [float(tf[t]) for t in sorted(tf)],
    }


def embed_text(text: str, retries: int = 3) -> list[float]:
    """Embed with truncation and retry."""
    clean = re.sub(r"\s{2,}", " ", text).strip()[:MAX_EMBED_CHARS]
    for attempt in range(retries):
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": clean},
                timeout=120,
            )
            r.raise_for_status()
            return r.json()["embedding"]
        except Exception as e:
            if attempt < retries - 1:
                if "500" in str(e):
                    clean = clean[: len(clean) // 2]
                time.sleep(3 * (attempt + 1))
            else:
                raise


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks, s = [], 0
    while s < len(text):
        c = text[s : s + size].strip()
        if c:
            chunks.append(c)
        s += size - overlap
    return chunks


# Keywords de relevancia avícola/capones (FR + ES) para filtrar libros generalistas
_RELEVANCE_KW = re.compile(
    r"capon|capón|chapon|poule|poulet|gallina|pollo|volaille|oiseau|aves|avicul|"
    r"coq|gallo|poussin|pollito|épinette|engraiss|engord|plum|œuf|huevo|"
    r"bresse|barbezieux|houdan|crèvecœur|faverol|dorking|coucou|malines|"
    r"sussex|orpington|cochinchin|brahma|leghorn|raza|race|crois|cruce|"
    r"castrat|castrad|chaponnage|caponiz|abat|sacrific|carcass|canal|"
    r"aliment|nourri|pienso|grain|pâtée|fourrage|son|maïs|trigo|"
    r"élevage|cría|élev|ganadería|ferme|granja|basse.cour|corral",
    re.IGNORECASE,
)


def filter_relevant_chunks(chunks: list[str], min_keywords: int = 2) -> list[str]:
    """Keep only chunks with enough domain-relevant keywords (for large generalise books)."""
    return [c for c in chunks if len(_RELEVANCE_KW.findall(c)) >= min_keywords]


def upsert_batch(collection: str, points: list[dict]) -> bool:
    """Upsert a batch of points to Qdrant."""
    r = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        json={"points": points},
        timeout=60,
    )
    return r.status_code in (200, 201)


# ── Extractores de texto ─────────────────────────────────────────────────────

def extract_pdf_text(path: str) -> str:
    """Extract text from PDF using PyMuPDF. Returns raw text."""
    doc = fitz.open(path)
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    doc.close()
    return "\n\n".join(pages_text)


def extract_pdf_ocr(path: str, lang: str = "fra") -> str:
    """Extract text from scanned PDF using Tesseract OCR via PyMuPDF + pytesseract."""
    import pytesseract
    from PIL import Image
    import io

    doc = fitz.open(path)
    pages_text = []
    total = len(doc)

    for i, page in enumerate(doc):
        # Render page to image at 300 DPI
        mat = fitz.Matrix(2, 2)  # 2x zoom ≈ 144 DPI (good balance speed/quality)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))

        # OCR
        text = pytesseract.image_to_string(img, lang=lang)
        pages_text.append(text)

        if (i + 1) % 20 == 0:
            print(f"    OCR: {i+1}/{total} páginas...")

    doc.close()
    return "\n\n".join(pages_text)


def extract_docx(path: str) -> str:
    """Extract text from DOCX."""
    import zipfile
    import xml.etree.ElementTree as ET

    text_parts = []
    with zipfile.ZipFile(path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for para in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        texts = [t.text for t in para.findall(".//w:t", ns) if t.text]
        if texts:
            text_parts.append(" ".join(texts))
    return "\n".join(text_parts)


def extract_text_file(path: str) -> str:
    """Extract text from .md or .txt."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def needs_ocr(path: str) -> bool:
    """Check if a PDF needs OCR by sampling pages from beginning, middle and end.
    Uses majority rule: if fewer than half of sampled pages have meaningful text, needs OCR."""
    doc = fitz.open(path)
    total = len(doc)
    if total == 0:
        doc.close()
        return True
    # Sample: first 5, middle 5, last 5 pages
    indices = set()
    for i in range(min(5, total)):
        indices.add(i)
    mid = total // 2
    for i in range(max(0, mid - 2), min(total, mid + 3)):
        indices.add(i)
    for i in range(max(0, total - 5), total):
        indices.add(i)
    pages_with_text = sum(1 for i in indices if len(doc[i].get_text().strip()) >= OCR_THRESHOLD)
    doc.close()
    return pages_with_text < len(indices) * 0.5


# ── Pipeline principal ───────────────────────────────────────────────────────

def process_document(filename: str, lang: str, description: str, doc_type: str,
                     dry_run: bool = False) -> dict:
    """Process a single document: extract → chunk → embed → upsert."""
    path = SRC_DIR / filename
    if not path.exists():
        print(f"  ⚠ No existe: {filename}")
        return {"status": "missing", "chunks": 0}

    ext = path.suffix.lower()
    print(f"\n{'='*60}")
    print(f"📄 {filename}")
    print(f"   {description}")
    print(f"   Idioma: {lang} | Tipo: {doc_type} | Tamaño: {path.stat().st_size // 1024}KB")

    # 1. Extraer texto
    t0 = time.time()
    try:
        if ext == ".pdf":
            if needs_ocr(str(path)):
                print(f"   🔍 Necesita OCR ({lang})...")
                text = extract_pdf_ocr(str(path), lang=lang)
            else:
                print("   📖 Texto incrustado detectado")
                text = extract_pdf_text(str(path))
        elif ext == ".docx":
            text = extract_docx(str(path))
        elif ext in (".md", ".txt"):
            text = extract_text_file(str(path))
        else:
            print(f"  ⚠ Formato no soportado: {ext}")
            return {"status": "unsupported", "chunks": 0}
    except Exception as e:
        print(f"  ❌ Error extracción: {e}")
        return {"status": "error", "chunks": 0, "error": str(e)}

    extract_time = time.time() - t0

    # Limpiar texto
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    if len(text) < 100:
        print(f"  ⚠ Texto demasiado corto ({len(text)} chars)")
        return {"status": "too_short", "chunks": 0}

    print(f"   Extraído: {len(text):,} chars en {extract_time:.1f}s")

    # 2. Chunking
    chunks = chunk_text(text)

    # For large generalise books (historia, manual_fr with huge page counts), filter relevant chunks
    min_kw = 3 if doc_type == "historia" else 2
    if doc_type == "historia" or (doc_type == "manual_fr" and len(chunks) > 500):
        original = len(chunks)
        chunks = filter_relevant_chunks(chunks, min_keywords=min_kw)
        if chunks:
            print(f"   Filtrado relevancia: {original} → {len(chunks)} chunks (avícola/capones)")
        else:
            print(f"   ⚠ Filtrado demasiado agresivo ({original} → 0), usando top 200 por densidad")
            # Fallback: score all chunks and keep top 200 by keyword density
            all_chunks = chunk_text(text)
            scored = [(c, len(_RELEVANCE_KW.findall(c))) for c in all_chunks]
            scored.sort(key=lambda x: x[1], reverse=True)
            chunks = [c for c, s in scored[:200] if s >= 1]

    print(f"   Chunks: {len(chunks)}")

    if dry_run:
        return {"status": "dry_run", "chunks": len(chunks), "chars": len(text)}

    # 3. Embed + Upsert
    t1 = time.time()
    points = []
    total_upserted = 0

    for i, ch in enumerate(chunks):
        try:
            vec = embed_text(ch)
        except Exception as e:
            print(f"  ❌ Embed falló en chunk {i}: {e}")
            break

        sparse = compute_sparse(ch)
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"capones-corpus:{filename}:{i}"))
        pt = {
            "id": pid,
            "vector": {"dense": vec},
            "payload": {
                "text": ch,
                "source": filename,
                "source_file": filename,
                "title": description,
                "source_type": f"capones_corpus_{doc_type}",
                "language": lang,
                "doc_type": doc_type,
                "collection": COLLECTION,
                "chunk_index": i,
            },
        }
        if sparse:
            pt["vector"]["bm25"] = sparse
        points.append(pt)

        if len(points) >= 20:
            upsert_batch(COLLECTION, points)
            total_upserted += len(points)
            points = []

        if (i + 1) % 50 == 0:
            print(f"   ... {i+1}/{len(chunks)} chunks embebidos")

    if points:
        upsert_batch(COLLECTION, points)
        total_upserted += len(points)

    embed_time = time.time() - t1
    print(f"   ✅ {total_upserted} chunks → Qdrant/{COLLECTION} ({embed_time:.1f}s)")

    return {"status": "ok", "chunks": total_upserted, "chars": len(text), "text": text}


def main():
    parser = argparse.ArgumentParser(description="Ingesta corpus capones FR/ES → Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="Solo extraer y contar, no indexar")
    parser.add_argument("--only-type", type=str, help="Solo procesar un tipo: manual_fr, label_rouge, historia, corpus_es")
    parser.add_argument("--summary", action="store_true", help="Generar resumen de manuales franceses al terminar")
    args = parser.parse_args()

    # Verificar servicios
    try:
        requests.get(f"{QDRANT_URL}/collections", timeout=5)
    except Exception:
        print("❌ Qdrant no disponible en localhost:6333")
        sys.exit(1)

    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    except Exception:
        print("❌ Ollama no disponible en localhost:11434")
        sys.exit(1)

    print("🌱 Seedy — Ingesta corpus capones (francés + español)")
    print(f"   Documentos: {len(DOCUMENTS)}")
    print(f"   Destino: Qdrant/{COLLECTION}")
    print(f"   {'DRY RUN' if args.dry_run else 'PRODUCCIÓN'}")
    print()

    results = {}
    all_texts = {}  # filename → full text (for summary)

    for filename, lang, desc, doc_type in DOCUMENTS:
        if args.only_type and doc_type != args.only_type:
            continue

        result = process_document(filename, lang, desc, doc_type, dry_run=args.dry_run)
        results[filename] = result

        # Guardar texto para resumen
        if result.get("text") and doc_type == "manual_fr":
            all_texts[filename] = result["text"]

    # Resumen final
    print(f"\n{'='*60}")
    print("📊 RESUMEN DE INGESTA")
    print(f"{'='*60}")

    total_chunks = 0
    total_chars = 0
    ok_count = 0

    for filename, r in results.items():
        status = r["status"]
        chunks = r.get("chunks", 0)
        chars = r.get("chars", 0)
        icon = {"ok": "✅", "dry_run": "📋", "missing": "⚠", "error": "❌",
                "too_short": "⚠", "unsupported": "⚠"}.get(status, "?")
        print(f"  {icon} {filename[:60]}: {status} ({chunks} chunks, {chars:,} chars)")
        if status in ("ok", "dry_run"):
            total_chunks += chunks
            total_chars += chars
            ok_count += 1

    print(f"\n  Total: {ok_count} docs procesados, {total_chunks:,} chunks, {total_chars:,} chars")

    # Generar resumen si se pide
    if args.summary and all_texts:
        print(f"\n{'='*60}")
        print("📝 GENERANDO RESUMEN DE MANUALES FRANCESES...")
        print(f"{'='*60}")
        generate_french_summary(all_texts)


def generate_french_summary(texts: dict[str, str]):
    """Genera un resumen estructura de los manuales franceses usando Ollama."""
    # Preparar extractos clave de cada manual (primeros 3000 chars)
    excerpts = []
    for filename, text in texts.items():
        desc = next(d for f, _, d, _ in DOCUMENTS if f == filename)
        excerpts.append(f"--- {desc} ---\n{text[:3000]}\n")

    context = "\n\n".join(excerpts)

    prompt = (
        "Eres un experto en avicultura histórica francesa y caponización. "
        "A continuación tienes extractos de manuales franceses del siglo XIX y principios del XX "
        "sobre avicultura, capones y producción avícola.\n\n"
        "Genera un RESUMEN ESTRUCTURADO en español que cubra:\n"
        "1. TECNICAS DE CAPONIZACION documentadas (métodos, edades, razas preferidas)\n"
        "2. RAZAS FRANCESAS descritas y sus aptitudes para capón\n"
        "3. ALIMENTACION Y ENGORDE (épinettes, pâtée láctea, regímenes)\n"
        "4. CRUCES E HIBRIDACIONES mencionados\n"
        "5. DATOS HISTORICOS sobre La Bresse, Barbezieux y otras regiones\n"
        "6. LECCIONES APLICABLES hoy para un proyecto de capón premium en España\n\n"
        "Sé exhaustivo, cita datos concretos (pesos, edades, periodos) cuando aparezcan.\n\n"
        f"--- TEXTOS ---\n{context[:12000]}\n--- FIN ---"
    )

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": "seedy:v16",
                "messages": [
                    {"role": "system", "content": "Eres un experto en historia de avicultura francesa."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 2048, "temperature": 0.3},
            },
            timeout=300,
        )
        r.raise_for_status()
        summary = r.json()["message"]["content"]

        # Guardar resumen
        out_path = "/home/davidia/Documentos/Seedy/resumen_manuales_franceses_capones.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Resumen de manuales franceses históricos sobre capones y avicultura\n\n")
            f.write(f"Generado por Seedy el {time.strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(f"Fuentes analizadas: {len(texts)} manuales\n\n")
            f.write("---\n\n")
            f.write(summary)

        print(f"\n✅ Resumen guardado en: {out_path}")
        print(f"\n{summary[:1500]}...")

    except Exception as e:
        print(f"❌ Error generando resumen: {e}")


if __name__ == "__main__":
    main()
