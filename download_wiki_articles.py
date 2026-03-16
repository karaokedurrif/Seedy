#!/usr/bin/env python3
"""
Descarga artículos de Wikipedia ES relevantes para Seedy (ganadería, avicultura, porcino, vacuno, nutrición)
Usa la API de Wikipedia — rápido y preciso.
"""
import json, os, time, re
import urllib.request
import urllib.parse

OUTPUT_DIR = "/home/davidia/Documentos/Seedy/wikipedia_articles"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# Lista completa de artículos a descargar
# ============================================================
ARTICLES = {
    # ── AVICULTURA / CAPONES ──
    "avicultura": [
        "Avicultura", "Capón", "Pularda", "Pollo de engorde", "Gallina ponedora",
        "Gallus gallus domesticus", "Cría de pollos",
        # Razas de gallinas pesadas para capones
        "Gallina de Malinas", "Brahma (gallina)", "Cochinchina (gallina)",
        "Plymouth Rock (gallina)", "Orpington (gallina)", "Sussex (gallina)",
        "Wyandotte (gallina)", "Jersey Giant", "Cornish (gallina)",
        "Castellana negra", "Prat leonada", "Empordanesa",
        "Gallina del Sobrarbe", "Gallina vasca", "Gallina murciana",
        "Gallina de Mos", "Gallina extremeña azul", "Gallina utrerana",
        # Productos
        "Huevo (alimento)", "Carne de pollo", "Foie gras",
        "Incubación artificial", "Incubadora (avicultura)",
    ],

    # ── PORCINO ──
    "porcino": [
        "Cerdo", "Porcicultura", "Cerdo ibérico", "Jamón ibérico",
        "Jamón serrano", "Dehesa", "Montanera",
        # Razas porcinas
        "Duroc", "Pietrain", "Landrace (cerdo)", "Large White",
        "Hampshire (cerdo)", "Berkshire (cerdo)", "Cerdo celta",
        "Cerdo negro canario", "Cerdo chato murciano",
        "Mangalica", "Cerdo vietnamita",
        # Productos y manejo
        "Embutido", "Chorizo", "Salchichón", "Lomo embuchado",
        "Matanza del cerdo", "Castración", "Inseminación artificial porcina",
        "Destete", "Cebo (ganadería)",
    ],

    # ── VACUNO ──
    "vacuno": [
        "Ganado vacuno", "Ganadería bovina", "Bos taurus",
        "Carne de vacuno", "Leche",
        # Razas españolas
        "Retinta", "Avileña-Negra Ibérica", "Morucha",
        "Rubia gallega", "Asturiana de los valles", "Asturiana de la montaña",
        "Pirenaica (raza bovina)", "Lidia (raza bovina)", "Tudanca",
        "Alistana-Sanabresa", "Sayaguesa", "Cachena", "Berrenda",
        "Blanca cacereña", "Negra andaluza (bovina)", "Pajuna (raza bovina)",
        "Limusina (raza bovina)",
        # Razas europeas comunes en España
        "Charolais", "Hereford", "Angus (bovino)", "Simmental",
        "Frisona (bovina)", "Parda alpina", "Fleckvieh",
        "Blonde d'Aquitaine", "Piamontesa (raza bovina)", "Marchigiana",
        # Manejo
        "Ganadería extensiva", "Ganadería intensiva",
        "Cebadero", "Feed lot",
        "Inseminación artificial", "Transferencia de embriones",
    ],

    # ── OVINO/CAPRINO ──
    "ovino_caprino": [
        "Ganado ovino", "Ganado caprino", "Oveja", "Cabra",
        "Merina", "Rasa aragonesa", "Latxa", "Churra (oveja)",
        "Manchega (oveja)", "Segureña",
        "Cabra murciano-granadina", "Cabra malagueña", "Cabra majorera",
        "Queso manchego", "Queso de cabra",
        "Trashumancia", "Pastoreo",
    ],

    # ── NUTRICIÓN ANIMAL ──
    "nutricion": [
        "Nutrición animal", "Pienso", "Alimentación animal",
        "Silo (almacén)", "Ensilaje", "Heno", "Paja",
        "Proteína (nutriente)", "Aminoácido esencial", "Lisina", "Metionina",
        "Vitamina", "Mineral (nutriente)", "Calcio", "Fósforo",
        "Maíz", "Cebada", "Trigo", "Soja", "Girasol", "Colza",
        "Harina de pescado", "Torta de soja",
        "Ración (alimentación)", "Conversión alimenticia",
        "Aditivo alimentario", "Probiótico", "Prebiótico", "Antibiótico",
    ],

    # ── GENÉTICA ──
    "genetica": [
        "Genética", "Mejora genética", "Selección artificial",
        "Hibridación", "Heterosis", "Cruzamiento",
        "Heredabilidad", "Valor genético", "BLUP",
        "Genómica", "Marcador genético", "SNP",
        "Consanguinidad", "Endogamia",
    ],

    # ── SANIDAD ANIMAL ──
    "sanidad": [
        "Peste porcina africana", "Peste porcina clásica",
        "Fiebre aftosa", "Brucelosis", "Tuberculosis bovina",
        "Lengua azul", "Gripe aviar", "Enfermedad de Newcastle",
        "Salmonelosis", "Coccidiosis", "Mastitis",
        "Vacunación", "Bioseguridad",
        "Bienestar animal", "Estrés térmico",
    ],

    # ── TECNOLOGÍA / IoT / PRECISION ──
    "tecnologia": [
        "Ganadería de precisión", "Internet de las cosas",
        "Sensor", "RFID", "GPS", "Dron",
        "Gemelo digital", "Inteligencia artificial",
        "Visión artificial", "Aprendizaje automático",
        "LPWAN", "LoRa", "Sigfox", "NB-IoT",
    ],

    # ── NORMATIVA ──
    "normativa": [
        "Política agrícola común", "PAC (Unión Europea)",
        "Denominación de origen", "Indicación geográfica protegida",
        "Trazabilidad alimentaria", "APPCC",
        "Bienestar animal en la Unión Europea",
        "Reglamento (CE) n.º 1099/2009",
    ],

    # ── RAZAS en inglés (Wikipedia EN tiene más info técnica) ──
    "en_breeds": [
        "Capon", "Poularde", "Broiler", "Layer chicken",
        "Malines chicken", "Brahma chicken", "Cochin chicken",
        "Jersey Giant chicken", "Cornish chicken", "Plymouth Rock chicken",
        "Iberian pig", "Duroc pig", "Pietrain", "Landrace pig", "Large White pig",
        "Retinta cattle", "Avileña-Black Iberian cattle", "Rubia Gallega",
        "Charolais cattle", "Hereford cattle", "Angus cattle",
        "Precision livestock farming", "Digital twin",
        "Animal nutrition", "Feed conversion ratio",
        "Heterosis", "Estimated breeding value",
    ],
}

def fetch_wiki_article(title: str, lang: str = "es") -> dict | None:
    """Fetch article text from Wikipedia API."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
        "redirects": "1",
    }
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SeedyBot/1.0 (NeoFarm research)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1" or "missing" in page:
                return None
            return {
                "title": page.get("title", title),
                "pageid": int(page_id),
                "text": page.get("extract", ""),
                "lang": lang,
            }
    except Exception as e:
        print(f"  ⚠ Error fetching {title} ({lang}): {e}")
        return None

def clean_text(text: str) -> str:
    """Limpia texto de Wikipedia."""
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove "== Ver también ==" and everything after (references, external links)
    for section in ["== Ver también ==", "== Véase también ==", "== Referencias ==",
                     "== Enlaces externos ==", "== Bibliografía ==", "== Notas ==",
                     "== See also ==", "== References ==", "== External links =="]:
        idx = text.find(section)
        if idx > 0:
            text = text[:idx].rstrip()
    return text.strip()


def main():
    total = 0
    downloaded = 0
    failed = []
    all_articles = []

    for category, titles in ARTICLES.items():
        lang = "en" if category == "en_breeds" else "es"
        print(f"\n{'='*60}")
        print(f"📂 Categoría: {category} ({lang}.wikipedia.org) — {len(titles)} artículos")
        print(f"{'='*60}")

        for title in titles:
            total += 1
            article = fetch_wiki_article(title, lang=lang)

            if article and len(article["text"]) > 200:
                article["text"] = clean_text(article["text"])
                article["category"] = category
                all_articles.append(article)
                downloaded += 1
                chars = len(article["text"])
                print(f"  ✅ {article['title']} — {chars:,} chars")
            else:
                failed.append(f"{title} ({lang})")
                print(f"  ❌ {title} — no encontrado o vacío")

            time.sleep(0.3)  # Rate limiting

    # Save all articles as JSONL
    output_path = os.path.join(OUTPUT_DIR, "wiki_articles_raw.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for art in all_articles:
            f.write(json.dumps(art, ensure_ascii=False) + "\n")

    # Also save a summary
    summary_path = os.path.join(OUTPUT_DIR, "download_summary.json")
    cats_summary = {}
    for art in all_articles:
        cat = art["category"]
        cats_summary.setdefault(cat, {"count": 0, "total_chars": 0})
        cats_summary[cat]["count"] += 1
        cats_summary[cat]["total_chars"] += len(art["text"])

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_requested": total,
            "downloaded": downloaded,
            "failed_count": len(failed),
            "failed": failed,
            "total_chars": sum(len(a["text"]) for a in all_articles),
            "categories": cats_summary,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"📊 RESUMEN:")
    print(f"   Solicitados: {total}")
    print(f"   Descargados: {downloaded}")
    print(f"   Fallidos:    {len(failed)}")
    total_chars = sum(len(a["text"]) for a in all_articles)
    print(f"   Total chars: {total_chars:,} (~{total_chars//4:,} tokens)")
    print(f"   Guardado en: {output_path}")
    if failed:
        print(f"\n   ❌ Fallidos: {', '.join(failed[:20])}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
