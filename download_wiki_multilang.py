#!/usr/bin/env python3
"""
Descarga artículos de Wikipedia en FR, EN, IT, DE sobre ganadería, avicultura y razas.
Complementa download_wiki_articles.py (que cubre ES + algunos EN).
Foco: cubrir razas que ES-wiki no tiene y artículos técnicos mejores en otros idiomas.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

OUTPUT_DIR = "/home/davidia/Documentos/Seedy/wikipedia_articles"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# Artículos por idioma — priorizando lo que falta en ES
# ============================================================
ARTICLES = {
    # ── FRANCÉS (FR) — razas avícolas francesas, capones, razas bovinas ──
    "fr": [
        # Avicultura / Capones
        "Chapon (animal)", "Poularde", "Poulet de Bresse", "Volaille de Bresse",
        "Gauloise dorée", "Faverolles (race de poule)", "Poule de La Flèche",
        "Poule de Barbezieux", "Poule de Houdan", "Poule de Crèvecœur",
        "Géline de Touraine", "Poule de Gournay", "Poule gâtinaise",
        "Poule de Caussade", "Poule cou nu du Forez", "Poule de Marans",
        "Noire du Berry", "Poule de Bresse-Gauloise",
        "Brahma (race de poule)", "Cochin (race de poule)",
        # Razas bovinas
        "Cachena (race bovine)", "Barrosã", "Race bovine",
        "Blonde d'Aquitaine", "Limousine (race bovine)", "Charolaise",
        "Salers (race bovine)", "Aubrac (race bovine)", "Parthenaise",
        "Bazadaise", "Gasconne (race bovine)", "Béarnaise (race bovine)",
        # Porcino
        "Porc ibérique", "Porc basque", "Porc noir de Bigorre",
        "Porc de Bayeux", "Porc cul noir", "Porc nustrale",
        # Razas ovinas
        "Lacaune (race ovine)", "Manech",
        # Ganadería general
        "Race rustique", "Élevage extensif", "Appellation d'origine contrôlée",
        "Insémination artificielle (élevage)",
    ],

    # ── INGLÉS (EN) — razas que faltan del primer descargador ──
    "en": [
        # Avicultura / Capones
        "Capon", "Poularde", "Bresse chicken", "Faverolles chicken",
        "La Flèche chicken", "Barbezieux chicken", "Houdan chicken",
        "Crèvecœur chicken", "Malines chicken", "Campine chicken",
        "Braekel", "Brahma chicken", "Cochin chicken",
        "Jersey Giant", "Cornish chicken", "Plymouth Rock chicken",
        "Sussex chicken", "Wyandotte chicken", "Orpington chicken",
        "Dorking chicken", "Ixworth chicken",
        # Italianas
        "Padovana chicken", "Robusta Maculata", "Bionda Piemontese",
        # Bovino — razas que faltaron
        "Cachena cattle", "Barrosã cattle", "Avileña-Black Iberian cattle",
        "Morucha cattle", "Tudanca cattle", "Sayaguesa cattle",
        "Alistana-Sanabresa cattle", "Pajuna cattle",
        "Blonde d'Aquitaine", "Piedmontese cattle", "Marchigiana cattle",
        "Angus cattle", "Hereford cattle", "Simmental cattle",
        "Holstein Friesian cattle", "Fleckvieh",
        # Porcino
        "Iberian pig", "Gascon pig", "Berkshire pig", "Hampshire pig",
        "Mangalica", "Celtic pig", "Pietrain",
        # Técnicos
        "Precision livestock farming", "Digital twin",
        "Animal nutrition", "Feed conversion ratio",
        "Estimated breeding value", "Heterosis",
        "Animal welfare", "Livestock",
    ],

    # ── ITALIANO (IT) — razas italianas para capones ──
    "it": [
        # Avicultura
        "Cappone", "Padovana (razza avicola)", "Polverara (razza avicola)",
        "Robusta Maculata", "Robusta Lionata",
        "Bionda Piemontese (razza avicola)", "Bianca di Saluzzo",
        "Cappone di Morozzo", "Livorno (razza avicola)",
        "Valdarno (razza avicola)", "Ancona (razza avicola)",
        "Siciliana (razza avicola)", "Ermellinata di Rovigo",
        "Avicultura",
        # Bovino
        "Chianina", "Marchigiana", "Piemontese (razza bovina)",
        "Romagnola (razza bovina)", "Maremmana (razza bovina)",
        "Podolica (razza bovina)",
        # Porcino
        "Cinta senese", "Nero dei Nebrodi", "Suino nero di Calabria",
        "Mora romagnola",
        # General
        "Allevamento estensivo", "Razza autoctona",
    ],

    # ── ALEMÁN (DE) — razas centroeuropeas y técnico ──
    "de": [
        # Avicultura
        "Kapaun", "Mechelner Huhn", "Brahma (Huhn)",
        "Cochin (Huhn)", "Faverolles (Huhn)", "Orpington (Huhn)",
        "Sundheimer Huhn", "Deutsches Lachshuhn",
        "Bielefelder Kennhuhn", "Marans (Huhn)",
        # Bovino
        "Fleckvieh", "Gelbvieh", "Pinzgauer Rind",
        "Braunvieh", "Hinterwälder", "Vorderwälder",
        "Murnau-Werdenfelser", "Rotes Höhenvieh",
        "Charolais (Rind)", "Limousin (Rind)", "Angus (Rind)",
        # Porcino
        "Schwäbisch-Hällisches Schwein", "Bunte Bentheimer Schwein",
        "Angler Sattelschwein", "Mangalica",
        # Técnico
        "Precision Livestock Farming", "Tierzucht",
        "Künstliche Besamung", "Tierhaltung",
    ],
}


def fetch_wiki_article(title: str, lang: str) -> dict | None:
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
            text = page.get("extract", "")
            if len(text) < 200:
                return None
            return {
                "title": page.get("title", title),
                "pageid": int(page_id),
                "text": text,
                "lang": lang,
            }
    except Exception as e:
        print(f"  ⚠ Error fetching {title} ({lang}): {e}")
        return None


def clean_text(text: str) -> str:
    """Limpia texto de Wikipedia."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    for section in [
        "== Ver también ==", "== Véase también ==", "== Referencias ==",
        "== Enlaces externos ==", "== Bibliografía ==", "== Notas ==",
        "== See also ==", "== References ==", "== External links ==",
        "== Voir aussi ==", "== Notes et références ==", "== Liens externes ==",
        "== Voci correlate ==", "== Note ==", "== Altri progetti ==",
        "== Siehe auch ==", "== Einzelnachweise ==", "== Weblinks ==",
        "== Literatur ==",
    ]:
        idx = text.find(section)
        if idx > 0:
            text = text[:idx].rstrip()
    return text.strip()


def main():
    total = 0
    downloaded = 0
    failed = []
    all_articles = []

    for lang, titles in ARTICLES.items():
        print(f"\n{'=' * 60}")
        print(f"📂 {lang}.wikipedia.org — {len(titles)} artículos")
        print(f"{'=' * 60}")

        for title in titles:
            total += 1
            article = fetch_wiki_article(title, lang=lang)

            if article:
                article["text"] = clean_text(article["text"])
                article["category"] = f"{lang}_breeds"
                all_articles.append(article)
                downloaded += 1
                chars = len(article["text"])
                print(f"  ✅ {article['title']} ({lang}) — {chars:,} chars")
            else:
                failed.append(f"{title} ({lang})")
                print(f"  ❌ {title} ({lang}) — no encontrado o vacío")

            time.sleep(0.3)

    # Save as JSONL
    output_path = os.path.join(OUTPUT_DIR, "wiki_articles_multilang.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for art in all_articles:
            f.write(json.dumps(art, ensure_ascii=False) + "\n")

    # Summary
    summary_path = os.path.join(OUTPUT_DIR, "download_multilang_summary.json")
    cats_summary = {}
    for art in all_articles:
        lang = art["lang"]
        cats_summary.setdefault(lang, {"count": 0, "total_chars": 0})
        cats_summary[lang]["count"] += 1
        cats_summary[lang]["total_chars"] += len(art["text"])

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_requested": total,
            "downloaded": downloaded,
            "failed_count": len(failed),
            "failed": failed,
            "total_chars": sum(len(a["text"]) for a in all_articles),
            "by_lang": cats_summary,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"📊 RESUMEN MULTIIDIOMA:")
    print(f"   Solicitados: {total}")
    print(f"   Descargados: {downloaded}")
    print(f"   Fallidos:    {len(failed)}")
    total_chars = sum(len(a["text"]) for a in all_articles)
    print(f"   Total chars: {total_chars:,} (~{total_chars // 4:,} tokens)")
    for lang, info in cats_summary.items():
        print(f"   {lang}: {info['count']} arts, {info['total_chars']:,} chars")
    print(f"   Guardado en: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
