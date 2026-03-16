#!/usr/bin/env python3
"""
build_dataset_v10.py — Genera ~964 Q&As nuevos desde TODAS las fuentes de conocimiento
para llegar a 2000 ejemplos totales combinando con v9 (1036).

Fuentes:
  1. Wikipedia articles (157 artículos, 1.8 MB)
  2. Science articles (546 papers, 820 KB)
  3. Conocimientos MD (excluyendo meta-instrucciones)
  4. Data/raw noticias (52 artículos)

Usa qwen2.5:14b local vía Ollama para generar Q&As grounded en el contenido.
"""

import json
import os
import re
import time
import hashlib
import random
import sys
from pathlib import Path
from collections import defaultdict

import httpx

# ─── CONFIG ────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"
BASE_DIR = Path("/home/davidia/Documentos/Seedy")
OUT_FILE = BASE_DIR / "seedy_dataset_sft_v10_new.jsonl"
PROGRESS_FILE = BASE_DIR / ".v10_progress.json"
TARGET_NEW = 964  # para llegar a 2000 con v9 (1036)

SYSTEM_PROMPT = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData 7 capas), nutrición animal (NRC 2012), "
    "genética aplicada (EPDs, FarmMatch, heterosis), digital twins, normativa ganadera "
    "(RD 306/2020, EcoGAN), avicultura extensiva (capones, pulardas, razas autóctonas), "
    "vacuno extensivo y GeoTwin GIS.\n"
    "Responde siempre en español técnico, de forma precisa. Si no tienes datos verificados "
    "sobre algo, indícalo claramente en lugar de inventar."
)

# ─── EXCLUSIONS ────────────────────────────────────────────────
EXCLUDE_FILES = {
    "instruccionespara datasets para SDeedy.md",  # meta-instrucciones, no conocimiento
}


def load_wikipedia() -> list[dict]:
    """Load Wikipedia articles."""
    path = BASE_DIR / "wikipedia_articles" / "wiki_articles_raw.jsonl"
    articles = []
    seen_titles = set()
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            title = d.get("title", "")
            content = d.get("content", d.get("text", ""))
            if title in seen_titles or len(content) < 200:
                continue
            seen_titles.add(title)
            articles.append({
                "source": "wikipedia",
                "title": title,
                "content": content,
            })
    return articles


def load_science() -> list[dict]:
    """Load science articles."""
    path = BASE_DIR / "science_articles" / "science_articles_raw.jsonl"
    articles = []
    seen = set()
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            title = d.get("title", d.get("query", ""))
            content = d.get("content", d.get("text", d.get("abstract", "")))
            key = title[:80]
            if key in seen or len(content) < 200:
                continue
            seen.add(key)
            articles.append({
                "source": "science",
                "title": title,
                "content": content,
            })
    return articles


def load_conocimientos() -> list[dict]:
    """Load markdown knowledge files, excluding meta-instructions."""
    kb_dir = BASE_DIR / "conocimientos"
    articles = []
    for root, _, files in os.walk(kb_dir):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            if fname in EXCLUDE_FILES:
                continue
            path = os.path.join(root, fname)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if len(content) < 200:
                continue
            folder = os.path.relpath(root, kb_dir)
            articles.append({
                "source": "conocimientos",
                "title": f"{folder}/{fname}",
                "content": content,
            })
    return articles


def load_raw_news() -> list[dict]:
    """Load ingested news articles."""
    raw_dir = BASE_DIR / "data" / "raw"
    articles = []
    if not raw_dir.exists():
        return articles
    for root, _, files in os.walk(raw_dir):
        for fname in sorted(files):
            if not fname.endswith(".txt"):
                continue
            path = os.path.join(root, fname)
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if len(content) < 100:
                continue
            articles.append({
                "source": "news",
                "title": fname,
                "content": content,
            })
    return articles


def chunk_text(text: str, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    """Split text into chunks, preferring section boundaries."""
    # Split by markdown headers first
    sections = re.split(r'\n(?=#{1,4}\s)', text)
    
    chunks = []
    current = ""
    for section in sections:
        if len(current) + len(section) < max_chars:
            current += section
        else:
            if current.strip():
                chunks.append(current.strip())
            # If single section is too long, split by paragraphs
            if len(section) > max_chars:
                paragraphs = section.split("\n\n")
                current = ""
                for para in paragraphs:
                    if len(current) + len(para) < max_chars:
                        current += "\n\n" + para if current else para
                    else:
                        if current.strip():
                            chunks.append(current.strip())
                        current = para
            else:
                current = section
    if current.strip():
        chunks.append(current.strip())
    
    return chunks if chunks else [text[:max_chars]]


def categorize_article(title: str, content: str) -> str:
    """Assign domain category to an article."""
    combined = (title + " " + content[:500]).lower()
    if any(w in combined for w in ["capón", "capones", "gallina", "pollo", "avícola", "avicultura", 
                                     "pularda", "huevo", "pluma", "incubac", "capon", "poulard",
                                     "brahma", "orpington", "cochin", "malines", "plymouth rock",
                                     "castellana negra", "gallina de mos", "pita pinta", "euskal",
                                     "sobrarbe", "utrerana", "extremeña", "penedesenca", "prat"]):
        return "avicultura"
    elif any(w in combined for w in ["cerdo", "porcin", "cerda", "lechón", "jamón", "ibéric",
                                       "sow", "pig", "swine", "engorde", "cebo", "duroc",
                                       "pietrain", "landrace", "large white", "mangalica",
                                       "peste porcina", "matanza", "embutido", "chorizo"]):
        return "porcino"
    elif any(w in combined for w in ["vaca", "vacun", "terner", "bovin", "bos taurus",
                                       "retinta", "morucha", "rubia gallega", "asturiana",
                                       "pirenaica", "charolais", "hereford", "cachena",
                                       "blanca cacereña", "pajuna", "tudanca", "simmental",
                                       "leche", "carne de vacuno"]):
        return "vacuno"
    elif any(w in combined for w in ["sensor", "iot", "mqtt", "lora", "gateway", "mioty",
                                       "rfid", "gps", "dron", "internet de las cosas"]):
        return "iot"
    elif any(w in combined for w in ["digital twin", "gemelo digital", "blender", "unreal",
                                       "gis", "geotwin", "3d"]):
        return "digital_twin"
    elif any(w in combined for w in ["genétic", "mejoramiento", "heterosis", "hibridac",
                                       "heredabilidad", "genómica", "marcador", "snp",
                                       "consanguinidad", "endogamia", "selección artificial",
                                       "cruzamiento"]):
        return "genetica"
    elif any(w in combined for w in ["nutrici", "formulaci", "pienso", "aminoácido", "lisina",
                                       "metionina", "proteína", "calcio", "fósforo", "forraje",
                                       "ensilado", "heno", "probiótic", "prebiótic", "aditivo",
                                       "cebada", "trigo", "soja", "girasol", "colza",
                                       "harina de pescado"]):
        return "nutricion"
    elif any(w in combined for w in ["normativ", "real decreto", "sige", "ecogan",
                                       "bienestar animal", "ley", "política agrícola",
                                       "denominación de origen", "igp", "appcc"]):
        return "normativa"
    elif any(w in combined for w in ["neofarm", "plataforma", "competencia", "startup",
                                       "negocio", "arquitectura", "roadmap"]):
        return "estrategia"
    elif any(w in combined for w in ["enfermedad", "brucelosis", "tuberculosis", "gripe aviaria",
                                       "newcastle", "salmonel", "cocidio", "mastitis",
                                       "fiebre aftosa", "lengua azul", "bioseguridad",
                                       "vacunación"]):
        return "sanidad"
    elif any(w in combined for w in ["ovino", "caprino", "oveja", "cabra", "queso",
                                       "trashumancia", "pastoreo", "merina", "lacha"]):
        return "ovino_caprino"
    elif any(w in combined for w in ["inteligencia artificial", "visión artificial",
                                       "aprendizaje automático", "machine learning"]):
        return "ia_ml"
    else:
        return "general"


def generate_qa_from_chunk(chunk: str, title: str, category: str, n_pairs: int = 3) -> list[dict]:
    """
    Use qwen2.5:14b to generate Q&A pairs grounded in the chunk.
    Returns list of {"user": ..., "assistant": ...} dicts.
    """
    prompt = f"""Eres un generador de datos de entrenamiento para Seedy, un asistente agrotech especializado.

CONTEXTO (fuente: {title}, dominio: {category}):
---
{chunk[:2500]}
---

INSTRUCCIONES:
Genera exactamente {n_pairs} pares pregunta-respuesta en español basados ESTRICTAMENTE en el contexto anterior.

REGLAS CRÍTICAS:
1. Las respuestas deben usar SOLO datos del contexto. NO inventes cifras, fechas, nombres ni datos.
2. Si el contexto menciona razas, animales o términos técnicos, úsalos tal cual aparecen.
3. Las preguntas deben ser variadas: definiciones, comparativas, técnicas, prácticas.
4. Las respuestas deben tener 100-400 palabras, ser técnicas pero claras.
5. Incluye datos numéricos del contexto cuando los haya.
6. Usa formato profesional con estructura cuando sea apropiado.

FORMATO DE SALIDA (JSON array, sin texto adicional):
[
  {{"pregunta": "...", "respuesta": "..."}},
  {{"pregunta": "...", "respuesta": "..."}}
]

Genera SOLO el JSON array, sin explicaciones ni markdown."""

    try:
        resp = httpx.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_predict": 4096,
                    "num_ctx": 8192,
                },
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
        
        # Parse JSON from response
        # Try to find JSON array in the response
        text = text.strip()
        # Remove markdown code blocks if present
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()
        
        # Find JSON array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            pairs = json.loads(match.group())
        else:
            return []
        
        results = []
        for pair in pairs:
            q = pair.get("pregunta", "").strip()
            a = pair.get("respuesta", "").strip()
            if q and a and len(a) > 80:
                results.append({"user": q, "assistant": a})
        
        return results
    
    except Exception as e:
        print(f"    ERROR generando Q&A: {e}")
        return []


def make_example(user_msg: str, assistant_msg: str) -> dict:
    """Format as SFT training example."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def content_hash(text: str) -> str:
    """Hash for deduplication."""
    return hashlib.md5(text[:200].encode()).hexdigest()


def load_progress() -> dict:
    """Load progress from previous runs."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed_chunks": [], "generated_count": 0}


def save_progress(progress: dict):
    """Save progress for resume capability."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


def main():
    print("=" * 70)
    print("BUILD DATASET v10 — Generador de Q&As desde TODAS las fuentes")
    print("=" * 70)
    
    # 1. Load all sources
    print("\n📚 Cargando fuentes de conocimiento...")
    wikipedia = load_wikipedia()
    science = load_science()
    conocimientos = load_conocimientos()
    news = load_raw_news()
    
    print(f"  Wikipedia:     {len(wikipedia):4d} artículos")
    print(f"  Science:       {len(science):4d} artículos")
    print(f"  Conocimientos: {len(conocimientos):4d} archivos MD")
    print(f"  Noticias:      {len(news):4d} artículos")
    
    # 2. Categorize and plan distribution
    all_articles = wikipedia + science + conocimientos + news
    by_category = defaultdict(list)
    for art in all_articles:
        cat = categorize_article(art["title"], art["content"])
        art["category"] = cat
        by_category[cat].append(art)
    
    print(f"\n📊 Distribución por categoría:")
    total_chars = sum(len(a["content"]) for a in all_articles)
    category_targets = {}
    for cat in sorted(by_category.keys()):
        arts = by_category[cat]
        chars = sum(len(a["content"]) for a in arts)
        pct = 100 * chars / total_chars
        # Target: proportional but with minimum 20
        target = max(20, int(TARGET_NEW * chars / total_chars))
        category_targets[cat] = target
        print(f"  {cat:20s}: {len(arts):3d} arts, {chars/1024:6.0f} KB ({pct:4.1f}%) → ~{target} Q&As")
    
    # Normalize targets to sum to TARGET_NEW
    total_target = sum(category_targets.values())
    scale = TARGET_NEW / total_target
    category_targets = {k: max(10, int(v * scale)) for k, v in category_targets.items()}
    
    print(f"\n  Total target ajustado: {sum(category_targets.values())} Q&As")
    
    # 3. Load progress for resume
    progress = load_progress()
    processed = set(progress["processed_chunks"])
    
    # 4. Open output file (append mode for resume)
    mode = "a" if progress["generated_count"] > 0 else "w"
    generated = progress["generated_count"]
    
    print(f"\n🚀 Generando Q&As con {MODEL} (local Ollama)...")
    print(f"   Progreso previo: {generated}/{TARGET_NEW}")
    if generated >= TARGET_NEW:
        print("   ✅ Ya tenemos suficientes Q&As!")
        return
    
    outf = open(OUT_FILE, mode)
    
    try:
        for cat in sorted(by_category.keys()):
            if generated >= TARGET_NEW:
                break
            
            target = category_targets[cat]
            cat_generated = 0
            articles = by_category[cat]
            random.shuffle(articles)
            
            print(f"\n── {cat.upper()} (target: {target}) ──")
            
            for art in articles:
                if generated >= TARGET_NEW or cat_generated >= target:
                    break
                
                chunks = chunk_text(art["content"], max_chars=2000)
                
                for chunk in chunks:
                    if generated >= TARGET_NEW or cat_generated >= target:
                        break
                    
                    chunk_id = content_hash(chunk)
                    if chunk_id in processed:
                        continue
                    
                    # How many Q&As per chunk
                    n_pairs = min(3, target - cat_generated)
                    if n_pairs <= 0:
                        break
                    
                    pairs = generate_qa_from_chunk(
                        chunk, art["title"], cat, n_pairs=n_pairs
                    )
                    
                    for pair in pairs:
                        example = make_example(pair["user"], pair["assistant"])
                        outf.write(json.dumps(example, ensure_ascii=False) + "\n")
                        generated += 1
                        cat_generated += 1
                    
                    processed.add(chunk_id)
                    
                    # Progress update
                    if generated % 10 == 0:
                        print(f"    [{generated}/{TARGET_NEW}] {cat}: +{len(pairs)} "
                              f"(de '{art['title'][:50]}...')")
                        outf.flush()
                        progress["processed_chunks"] = list(processed)
                        progress["generated_count"] = generated
                        save_progress(progress)
                    
                    # Small delay to not overwhelm Ollama
                    time.sleep(0.1)
            
            print(f"  → {cat}: {cat_generated} Q&As generados")
    
    except KeyboardInterrupt:
        print(f"\n⚠️  Interrumpido. Progreso guardado: {generated} Q&As")
    finally:
        outf.close()
        progress["processed_chunks"] = list(processed)
        progress["generated_count"] = generated
        save_progress(progress)
    
    print(f"\n{'='*70}")
    print(f"✅ Generados: {generated} Q&As nuevos → {OUT_FILE.name}")
    print(f"   Siguiente paso: merge con v9 para crear v10 final")


def add_anti_hallucination_examples() -> list[dict]:
    """
    Generate explicit negative examples where Seedy should say
    'no dispongo de esa información' instead of inventing.
    """
    negatives = [
        {
            "user": "¿Cuál es la raza de gallina Negra de Tudela?",
            "assistant": "No existe una raza de gallina denominada 'Negra de Tudela' en el catálogo oficial de razas avícolas españolas. Las razas autóctonas españolas reconocidas con aptitud para producción de capones incluyen: Pardo de León, Pita Pinta Asturiana, Gallina de Mos, Euskal Oiloa, Prat Leonada, Castellana Negra, Penedesenca Negra, Sureña y Andaluza Azul. Te recomiendo consultar el catálogo oficial del MAPA para información actualizada sobre razas autóctonas."
        },
        {
            "user": "Háblame de la gallina Pintia para capones",
            "assistant": "No tengo constancia de una raza de gallina llamada 'Pintia' en ningún catálogo avícola oficial. Es posible que estés confundiendo el nombre con la Pita Pinta Asturiana, que sí es una raza autóctona española con muy buena aptitud para la producción de capones. La Pita Pinta es originaria de Asturias, con plumaje moteado (pinto), y produce capones de excelente calidad cárnica con un peso adulto de 3.5-4.5 kg. Si buscas razas para caponización, puedo darte información sobre las 9 razas autóctonas españolas documentadas con aptitud verificada."
        },
        {
            "user": "¿Qué sabes de la raza Porrano del Bierzo?",
            "assistant": "No existe una raza avícola denominada 'Porrano del Bierzo' en los registros oficiales españoles ni en la literatura científica que manejo. Las razas autóctonas españolas con presencia en el noroeste peninsular son: Gallina de Mos (Galicia), Pita Pinta Asturiana (Asturias) y Pardo de León (León). Todas ellas están bien documentadas y tienen aptitud para producción de capones. Si te interesa la avicultura en la zona del Bierzo (León), la raza más cercana geográficamente sería el Pardo de León, con aptitud excelente para caponización."
        },
        {
            "user": "¿Cuántas granjas de capones hay en Andalucía?",
            "assistant": "No dispongo de datos verificados sobre el número exacto de granjas de capones en Andalucía. Este tipo de estadísticas específicas por comunidad autónoma requeriría consultar fuentes oficiales como el Registro de Explotaciones Ganaderas (REGA) del MAPA o la Consejería de Agricultura de la Junta de Andalucía. Lo que sí puedo indicarte es que la producción de capones en España está más desarrollada en el noroeste (Galicia, Asturias, León) donde las razas autóctonas como Mos, Pita Pinta y Pardo de León tienen tradición caponera. En Andalucía, la raza autóctona con mayor potencial sería la Andaluza Azul."
        },
        {
            "user": "¿Cuál es el precio del capón de Villalba este año?",
            "assistant": "No dispongo de datos actualizados sobre los precios del Capón de Villalba para este año. Los precios de la Feria del Capón de Villalba (Lugo) varían cada temporada y se fijan en la propia feria, que se celebra en diciembre. Históricamente, los capones de Villalba (IGP) han alcanzado precios de 18-35 €/kg dependiendo de la categoría y el año. Para información actualizada, te recomiendo consultar la web de la IGP Capón de Villalba o el Consello Regulador. Lo que sí puedo confirmar es que se elaboran principalmente con la raza Gallina de Mos, con sacrificio mínimo a los 150 días y un peso canal de 2.5-3.5 kg."
        },
        {
            "user": "¿Existe la raza de cerdo Manchego Rojo?",
            "assistant": "No existe una raza porcina denominada 'Manchego Rojo' en el catálogo oficial de razas ganaderas de España. Las razas porcinas autóctonas españolas reconocidas incluyen: Cerdo Ibérico (con sus variedades: Retinto, Entrepelado, Lampiño, Torbiscal, Manchado de Jabugo), Cerdo Negro Canario, Cerdo Celta, Chato Murciano, Gochu Asturcelta y Porc Negre Mallorquí. En la producción intensiva española predominan los cruces de Duroc, Landrace, Large White y Piétrain. Si buscas información sobre alguna raza porcina específica, puedo ayudarte con datos verificados."
        },
    ]
    return [make_example(n["user"], n["assistant"]) for n in negatives]


if __name__ == "__main__":
    # If called with --merge, merge v9 + new into final v10
    if len(sys.argv) > 1 and sys.argv[1] == "--merge":
        print("🔀 Merging v9 + nuevos → v10 final...")
        
        v9_path = BASE_DIR / "seedy_dataset_sft_v9.jsonl"
        new_path = OUT_FILE
        final_path = BASE_DIR / "seedy_dataset_sft_v10.jsonl"
        
        examples = []
        
        # Load v9
        with open(v9_path) as f:
            for line in f:
                examples.append(json.loads(line))
        print(f"  v9: {len(examples)} ejemplos")
        
        # Load new
        if new_path.exists():
            with open(new_path) as f:
                for line in f:
                    examples.append(json.loads(line))
        print(f"  + nuevos: {len(examples)} total antes de anti-hallucination")
        
        # Add anti-hallucination negatives
        negatives = add_anti_hallucination_examples()
        examples.extend(negatives)
        print(f"  + {len(negatives)} anti-hallucination")
        
        # Shuffle (keeping system prompt consistent)
        random.shuffle(examples)
        
        # Write final
        with open(final_path, "w") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        
        print(f"\n✅ Dataset v10 final: {len(examples)} ejemplos → {final_path.name}")
        print(f"   Tamaño: {final_path.stat().st_size / 1024:.0f} KB")
    else:
        main()
