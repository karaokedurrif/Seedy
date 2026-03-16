#!/usr/bin/env python3
"""
build_dataset.py -- Generador automatico de datasets SFT para Together.ai
=========================================================================
Usa Seedy (Ollama) para leer documentos de conocimiento y generar pares
pregunta/respuesta de alta calidad en formato JSONL listo para fine-tuning.

USO:
  # Generar desde un documento:
  python3 build_dataset.py conocimientos/2.Nutricion*/RAF*.md

  # Generar desde todos los .md de una carpeta:
  python3 build_dataset.py conocimientos/3.NeoFarm\ Genetica/

  # Generar desde varios archivos:
  python3 build_dataset.py doc1.md doc2.md doc3.csv

  # Revisar y corregir un dataset existente:
  python3 build_dataset.py --review seedy_dataset_sft_v8.jsonl

  # Usar modelo diferente:
  python3 build_dataset.py --model seedy:v7-local doc.md

  # Ajustar número de pares por documento:
  python3 build_dataset.py --pairs 20 doc.md

  # Salida personalizada:
  python3 build_dataset.py -o mi_dataset.jsonl doc.md

Autor: NeoFarm / Seedy AI
Fecha: 2026-03-05
"""

import argparse
import json
import os
import re
import sys
import time
import glob
from pathlib import Path
from textwrap import dedent

import httpx

# ─── Configuración ───────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("SEEDY_MODEL", "seedy:v7-local")
TIMEOUT = 300  # 5 min por generación (docs largos)

SYSTEM_PROMPT = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData), costes por nave, nutrición porcina, "
    "genética aplicada, normativa SIGE y Digital Twins productivos.\n\n"
    "Responde siempre en español, en prosa natural y profesional.\n"
    "No uses secciones tipo Notes, References o Explanation.\n"
    "No repitas la pregunta.\n"
    "No inventes cifras, normativa ni parámetros técnicos.\n"
    "Si falta un dato imprescindible, pide solo el mínimo necesario (máximo 2 preguntas).\n"
    "Si das un número, incluye unidades y aclara si es aproximado.\n"
    "Prioriza precisión técnica sobre tono comercial."
)

# Meta-prompt para generar pares Q&A
META_PROMPT_GENERATE = dedent("""\
Eres un ingeniero de datos experto en crear datasets de entrenamiento SFT (Supervised Fine-Tuning)
para modelos de lenguaje especializados en agrotech y ganadería.

Tu tarea: a partir del DOCUMENTO que te proporciono, genera exactamente {n_pairs} pares
pregunta–respuesta de alta calidad para entrenar a "Seedy", un asistente técnico ganadero.

REGLAS OBLIGATORIAS:
1. Las preguntas deben ser variadas en tipo:
   - Preguntas directas de datos concretos ("¿Cuánto…?", "¿Cuál es…?")
   - Preguntas de comparación ("¿Qué diferencias hay entre…?")
   - Preguntas de explicación/concepto ("Explícame…", "¿Cómo funciona…?")
   - Preguntas de aplicación práctica ("¿Cómo se aplica…?", "¿Qué haría un ganadero si…?")
   - Preguntas de escenario ("Si tengo una nave con 500 cerdas…")
2. Las respuestas deben:
   - Tener entre 150 y 800 caracteres (prosa densa, nada de relleno)
   - Incluir datos numéricos concretos del documento cuando existan
   - Estar en español, prosa natural, sin secciones ni bullets
   - NO repetir la pregunta en la respuesta
   - NO inventar datos que no estén en el documento
   - Incluir unidades en cualquier cifra
3. NO generes pares que se puedan responder con "sí" o "no"
4. NO repitas la misma pregunta reformulada
5. Cada par debe ser autosuficiente (se entiende sin el documento)

FORMATO DE SALIDA (estricto, un par por línea):
Q: [pregunta]
A: [respuesta]

Q: [pregunta]
A: [respuesta]

... (exactamente {n_pairs} pares)

DOCUMENTO:
---
{document}
---

Genera los {n_pairs} pares ahora:""")

# Meta-prompt para revisar/corregir datasets
META_PROMPT_REVIEW = dedent("""\
Eres un ingeniero de QA de datos especializado en datasets SFT para LLMs.
Revisa el siguiente par pregunta–respuesta y devuelve una versión corregida.

CRITERIOS DE CALIDAD:
1. Ortografía y gramática perfectas en español
2. La respuesta debe tener entre 150 y 800 caracteres
3. Si la respuesta es demasiado corta, amplíala con contexto técnico relevante
4. Si es demasiado larga, condénsala manteniendo los datos clave
5. Elimina muletillas: "Claro", "Por supuesto", "Buena pregunta"
6. La respuesta NO debe empezar repitiendo la pregunta
7. Incluye unidades en todas las cifras
8. No inventes datos, solo mejora la redacción
9. Si la pregunta es ambigua, mejórala para que sea precisa

Devuelve EXACTAMENTE este formato (nada más):
Q: [pregunta corregida]
A: [respuesta corregida]

PAR A REVISAR:
Q: {question}
A: {answer}

Tu corrección:""")


# ─── Funciones auxiliares ────────────────────────────────────────────────
def read_document(path: str) -> str:
    """Lee un documento (.md, .txt, .csv, .pdf) y devuelve su texto."""
    p = Path(path)
    if not p.exists():
        print(f"  ⚠ No existe: {path}")
        return ""

    # PDFs: extraer texto con PyMuPDF
    if p.suffix.lower() == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(p))
            pages = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages.append(text)
            doc.close()
            full = "\n\n".join(pages)
            print(f"  📑 PDF: {len(pages)} páginas, {len(full)} chars")
            return full
        except Exception as e:
            print(f"  ⚠ Error leyendo PDF: {e}")
            return ""

    text = p.read_text(encoding="utf-8", errors="replace")
    # Para CSV, incluir las primeras 200 líneas
    if p.suffix.lower() == ".csv":
        lines = text.split("\n")
        if len(lines) > 200:
            text = "\n".join(lines[:200]) + f"\n\n[... {len(lines)-200} líneas más ...]"
    return text


def truncate_document(text: str, max_chars: int = 12000) -> list[str]:
    """Divide documentos largos en chunks manejables."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            if current.strip():
                chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def call_ollama(prompt: str, model: str, temperature: float = 0.7) -> str:
    """Llama a Ollama y devuelve la respuesta."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": 4096,
        },
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json().get("response", "")
    except Exception as e:
        print(f"  ❌ Error Ollama: {e}")
        return ""


def parse_qa_pairs(text: str) -> list[tuple[str, str]]:
    """Parsea la salida del modelo en pares (pregunta, respuesta)."""
    pairs = []
    # Buscar patrones Q: ... A: ...
    pattern = r"Q:\s*(.+?)(?:\n+)A:\s*(.+?)(?=\nQ:|\n*$)"
    matches = re.findall(pattern, text, re.DOTALL)
    for q, a in matches:
        q = q.strip().strip('"').strip("«»")
        a = a.strip().strip('"').strip("«»")
        if q and a:
            pairs.append((q, a))
    return pairs


def make_jsonl_entry(question: str, answer: str) -> dict:
    """Crea una entrada JSONL en formato Together.ai SFT."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


def validate_pair(q: str, a: str) -> tuple[bool, str]:
    """Valida un par Q&A. Devuelve (ok, motivo)."""
    if len(a) < 80:
        return False, f"Respuesta muy corta ({len(a)} chars)"
    if len(a) > 3000:
        return False, f"Respuesta excesiva ({len(a)} chars)"
    if len(q) < 10:
        return False, f"Pregunta muy corta ({len(q)} chars)"
    if a.lower().startswith(q.lower()[:30]):
        return False, "Respuesta repite la pregunta"
    if a.strip() in ("Sí", "No", "Sí.", "No.", "Correcto.", "Correcto"):
        return False, "Respuesta sí/no"
    # Detectar muletillas
    for bad in ["Claro,", "Por supuesto,", "Buena pregunta", "Gran pregunta"]:
        if a.startswith(bad):
            return False, f"Empieza con muletilla: {bad}"
    return True, "OK"


def deduplicate(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Elimina pares con preguntas muy similares."""
    seen = set()
    unique = []
    for q, a in pairs:
        # Normalizar para comparar
        key = re.sub(r"[¿?¡!.,;:\s]+", " ", q.lower()).strip()
        if key not in seen:
            seen.add(key)
            unique.append((q, a))
        else:
            print(f"  ⚠ Duplicado eliminado: {q[:60]}...")
    return unique


# ─── Modo: Generar dataset desde documentos ─────────────────────────────
def generate_from_docs(
    paths: list[str],
    model: str,
    n_pairs: int,
    output: str,
):
    """Genera un dataset SFT a partir de documentos."""
    all_pairs = []

    for path in paths:
        p = Path(path)
        if p.is_dir():
            files = sorted(glob.glob(str(p / "**/*"), recursive=True))
            files = [f for f in files if Path(f).suffix.lower() in (".md", ".txt", ".csv", ".pdf")]
        else:
            files = [str(p)]

        for filepath in files:
            print(f"\n📄 Procesando: {filepath}")
            text = read_document(filepath)
            if not text or len(text) < 100:
                print("  ⚠ Documento vacío o muy corto, saltando")
                continue

            chunks = truncate_document(text)
            pairs_per_chunk = max(3, n_pairs // len(chunks))

            for i, chunk in enumerate(chunks):
                label = f"  chunk {i+1}/{len(chunks)}" if len(chunks) > 1 else ""
                print(f"  🤖 Generando {pairs_per_chunk} pares{label}...")

                prompt = META_PROMPT_GENERATE.format(
                    n_pairs=pairs_per_chunk,
                    document=chunk,
                )
                response = call_ollama(prompt, model, temperature=0.7)
                if not response:
                    continue

                pairs = parse_qa_pairs(response)
                print(f"  ✅ Parseados: {len(pairs)} pares")

                # Validar cada par
                valid = []
                for q, a in pairs:
                    ok, reason = validate_pair(q, a)
                    if ok:
                        valid.append((q, a))
                    else:
                        print(f"  ⚠ Descartado ({reason}): {q[:50]}...")

                all_pairs.extend(valid)
                # Pequeña pausa para no saturar Ollama
                time.sleep(1)

    # Deduplicar
    print(f"\n🔍 Deduplicando {len(all_pairs)} pares...")
    all_pairs = deduplicate(all_pairs)
    print(f"  → {len(all_pairs)} pares únicos")

    # Escribir JSONL
    with open(output, "w", encoding="utf-8") as f:
        for q, a in all_pairs:
            entry = make_jsonl_entry(q, a)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n✅ Dataset generado: {output}")
    print(f"   {len(all_pairs)} ejemplos, listo para Together.ai")

    # Estadísticas
    if all_pairs:
        lengths = [len(a) for _, a in all_pairs]
        print(f"   Resp. min: {min(lengths)} chars | max: {max(lengths)} chars | avg: {sum(lengths)//len(lengths)} chars")


# ─── Modo: Revisar y corregir dataset existente ─────────────────────────
def review_dataset(
    input_path: str,
    model: str,
    output: str,
):
    """Revisa y corrige un dataset JSONL existente."""
    print(f"\n📋 Revisando: {input_path}")
    with open(input_path, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    print(f"   {len(entries)} ejemplos a revisar")

    corrected = []
    stats = {"ok": 0, "corregido": 0, "descartado": 0, "error": 0}

    for i, entry in enumerate(entries):
        msgs = entry.get("messages", [])
        q = next((m["content"] for m in msgs if m["role"] == "user"), "")
        a = next((m["content"] for m in msgs if m["role"] == "assistant"), "")

        if not q or not a:
            stats["descartado"] += 1
            continue

        # Validación rápida
        ok, reason = validate_pair(q, a)

        if ok and 150 <= len(a) <= 800:
            # Par aceptable, solo corrección ortográfica ligera
            corrected.append(entry)
            stats["ok"] += 1
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(entries)}] {stats}")
            continue

        # Necesita corrección → enviar a Ollama
        print(f"  🔧 [{i+1}] Corrigiendo ({reason}): {q[:60]}...")
        prompt = META_PROMPT_REVIEW.format(question=q, answer=a)
        response = call_ollama(prompt, model, temperature=0.3)

        if response:
            pairs = parse_qa_pairs(response)
            if pairs:
                new_q, new_a = pairs[0]
                ok2, reason2 = validate_pair(new_q, new_a)
                if ok2:
                    corrected.append(make_jsonl_entry(new_q, new_a))
                    stats["corregido"] += 1
                else:
                    # Si la corrección tampoco pasa, mantener original si no es terrible
                    if len(a) >= 80:
                        corrected.append(entry)
                        stats["ok"] += 1
                    else:
                        stats["descartado"] += 1
            else:
                corrected.append(entry)
                stats["error"] += 1
        else:
            corrected.append(entry)
            stats["error"] += 1

        # Pausa entre correcciones
        time.sleep(0.5)

    # Deduplicar
    seen = set()
    unique = []
    for entry in corrected:
        q = next((m["content"] for m in entry["messages"] if m["role"] == "user"), "")
        key = re.sub(r"[¿?¡!.,;:\s]+", " ", q.lower()).strip()
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    # Escribir salida
    with open(output, "w", encoding="utf-8") as f:
        for entry in unique:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n✅ Dataset revisado: {output}")
    print(f"   {len(unique)} ejemplos finales")
    print(f"   Stats: {stats}")


# ─── Modo: Merge de datasets ────────────────────────────────────────────
def merge_datasets(files: list[str], output: str):
    """Fusiona varios JSONL eliminando duplicados."""
    all_entries = []
    for f_path in files:
        print(f"  📥 Cargando: {f_path}")
        with open(f_path, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
            all_entries.extend(entries)
            print(f"     {len(entries)} ejemplos")

    # Deduplicar por pregunta
    seen = set()
    unique = []
    dupes = 0
    for entry in all_entries:
        q = next((m["content"] for m in entry["messages"] if m["role"] == "user"), "")
        key = re.sub(r"[¿?¡!.,;:\s]+", " ", q.lower()).strip()
        if key not in seen:
            seen.add(key)
            unique.append(entry)
        else:
            dupes += 1

    with open(output, "w", encoding="utf-8") as f:
        for entry in unique:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n✅ Merge completado: {output}")
    print(f"   {len(unique)} ejemplos únicos ({dupes} duplicados eliminados)")


# ─── CLI ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generador de datasets SFT para Together.ai usando Seedy/Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
        Ejemplos:
          %(prog)s conocimientos/3.NeoFarm\\ Genetica/
          %(prog)s --pairs 20 doc.md
          %(prog)s --review seedy_dataset_sft_v8.jsonl
          %(prog)s --merge v4.jsonl v8.jsonl -o merged.jsonl
        """),
    )
    parser.add_argument("inputs", nargs="*", help="Documentos (.md/.txt/.csv) o carpetas")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help=f"Modelo Ollama (default: {DEFAULT_MODEL})")
    parser.add_argument("--pairs", "-p", type=int, default=10, help="Pares Q&A por documento (default: 10)")
    parser.add_argument("--output", "-o", default=None, help="Archivo de salida JSONL")
    parser.add_argument("--review", action="store_true", help="Modo revisión: corrige un JSONL existente")
    parser.add_argument("--merge", action="store_true", help="Modo merge: fusiona varios JSONL")

    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    # Determinar nombre de salida
    if args.output:
        output = args.output
    elif args.review:
        base = Path(args.inputs[0]).stem
        output = f"{base}_reviewed.jsonl"
    elif args.merge:
        output = "seedy_dataset_merged.jsonl"
    else:
        timestamp = time.strftime("%Y%m%d_%H%M")
        output = f"seedy_dataset_new_{timestamp}.jsonl"

    print("=" * 60)
    print("  Seedy Dataset Builder — NeoFarm")
    print("=" * 60)
    print(f"  Modelo:  {args.model}")
    print(f"  Ollama:  {OLLAMA_URL}")
    print(f"  Salida:  {output}")

    if args.merge:
        print(f"  Modo:    MERGE ({len(args.inputs)} archivos)")
        print("=" * 60)
        merge_datasets(args.inputs, output)
    elif args.review:
        print(f"  Modo:    REVIEW & CORRECT")
        print("=" * 60)
        review_dataset(args.inputs[0], args.model, output)
    else:
        print(f"  Modo:    GENERATE ({args.pairs} pares/doc)")
        print(f"  Inputs:  {len(args.inputs)} fuentes")
        print("=" * 60)
        generate_from_docs(args.inputs, args.model, args.pairs, output)


if __name__ == "__main__":
    main()
