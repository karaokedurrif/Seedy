#!/usr/bin/env python3
"""
Descarga abstracts de artículos científicos relevantes para Seedy desde OpenAlex API.
OpenAlex indexa ScienceDirect, PubMed, etc. — los abstracts son open access.
"""
import json, os, time, re
import urllib.request
import urllib.parse

OUTPUT_DIR = "/home/davidia/Documentos/Seedy/science_articles"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# Queries de búsqueda para OpenAlex (indexa ScienceDirect, PubMed, etc.)
# ============================================================
QUERIES = [
    # ── AVICULTURA / CAPONES ──
    {"q": "capon chicken meat quality castration", "topic": "avicultura_capones"},
    {"q": "broiler chicken growth performance feed", "topic": "avicultura_engorde"},
    {"q": "poultry breeds heavy dual purpose", "topic": "avicultura_razas"},
    {"q": "capon production poultry meat quality sensory", "topic": "avicultura_capones_calidad"},
    {"q": "layer hen egg production genetics", "topic": "avicultura_ponedoras"},
    {"q": "poultry welfare housing enrichment", "topic": "avicultura_bienestar"},
    {"q": "chicken feed formulation amino acid", "topic": "avicultura_nutricion"},

    # ── PORCINO ──
    {"q": "Iberian pig acorn feeding meat quality", "topic": "porcino_iberico"},
    {"q": "pig nutrition amino acid lysine growth", "topic": "porcino_nutricion"},
    {"q": "swine breeding genetic improvement", "topic": "porcino_genetica"},
    {"q": "pig welfare housing stress behavior", "topic": "porcino_bienestar"},
    {"q": "pork quality intramuscular fat marbling", "topic": "porcino_calidad"},
    {"q": "sow reproduction farrowing piglet mortality", "topic": "porcino_reproduccion"},
    {"q": "pig precision farming IoT sensor monitoring", "topic": "porcino_iot"},
    {"q": "African swine fever epidemiology control", "topic": "porcino_sanidad"},
    {"q": "pig gut microbiome probiotics performance", "topic": "porcino_microbioma"},

    # ── VACUNO ──
    {"q": "beef cattle extensive system pasture Spain", "topic": "vacuno_extensivo"},
    {"q": "cattle genetic evaluation breeding value genomic", "topic": "vacuno_genetica"},
    {"q": "beef quality tenderness fatty acid profile", "topic": "vacuno_calidad"},
    {"q": "dairy cow nutrition rumen fermentation", "topic": "vacuno_lechero"},
    {"q": "cattle precision livestock farming wearable sensor", "topic": "vacuno_iot"},
    {"q": "calf rearing health growth performance", "topic": "vacuno_cria"},
    {"q": "cattle methane emission greenhouse gas reduction", "topic": "vacuno_medioambiente"},

    # ── NUTRICIÓN ANIMAL GENERAL ──
    {"q": "animal nutrition feed formulation optimization", "topic": "nutricion_formulacion"},
    {"q": "feed conversion ratio efficiency livestock", "topic": "nutricion_eficiencia"},
    {"q": "mycotoxin feed contamination livestock", "topic": "nutricion_micotoxinas"},
    {"q": "essential amino acids livestock requirement", "topic": "nutricion_aminoacidos"},
    {"q": "vitamin mineral supplementation livestock", "topic": "nutricion_suplementacion"},

    # ── GENÉTICA ──
    {"q": "genomic selection livestock GWAS SNP", "topic": "genetica_genomica"},
    {"q": "crossbreeding heterosis hybrid vigor livestock", "topic": "genetica_cruzamiento"},
    {"q": "inbreeding depression genetic diversity conservation", "topic": "genetica_consanguinidad"},

    # ── IoT / PRECISION FARMING ──
    {"q": "precision livestock farming digital twin simulation", "topic": "iot_digital_twin"},
    {"q": "livestock IoT sensor LPWAN LoRa monitoring", "topic": "iot_sensores"},
    {"q": "computer vision livestock behavior recognition", "topic": "iot_vision"},
    {"q": "smart farming data analytics machine learning livestock", "topic": "iot_analytics"},
    {"q": "RFID livestock tracking identification traceability", "topic": "iot_rfid"},

    # ── BIENESTAR / NORMATIVA ──
    {"q": "animal welfare regulation European Union livestock", "topic": "normativa_bienestar"},
    {"q": "livestock environmental impact sustainability circular", "topic": "normativa_sostenibilidad"},

    # ── AVICULTURA INTENSIVA ──
    {"q": "broiler production efficiency feed conversion ratio", "topic": "avi_intensiva_broiler"},
    {"q": "poultry house ventilation heating cooling system", "topic": "avi_intensiva_naves"},
    {"q": "laying hen cage-free production welfare", "topic": "avi_intensiva_ponedoras"},
    {"q": "poultry biosecurity disease prevention avian influenza", "topic": "avi_intensiva_bioseguridad"},
    {"q": "hatchery incubation technology egg fertility hatching", "topic": "avi_intensiva_incubacion"},
    {"q": "poultry processing plant automation slaughter quality", "topic": "avi_intensiva_procesado"},
    {"q": "broiler genetics growth rate Cobb Ross performance", "topic": "avi_intensiva_genetica"},
    {"q": "poultry litter management ammonia emission welfare", "topic": "avi_intensiva_cama"},
    {"q": "precision poultry farming sensor monitoring behavior", "topic": "avi_intensiva_precision"},
    {"q": "broiler gut health microbiome antibiotic alternative", "topic": "avi_intensiva_salud"},

    # ── BODEGAS / VINO / VITICULTURA ──
    {"q": "wine quality fermentation oenology phenolic compounds", "topic": "vino_enologia"},
    {"q": "vineyard precision viticulture remote sensing NDVI", "topic": "vino_viticultura_precision"},
    {"q": "Tempranillo grape variety wine sensory quality Spain", "topic": "vino_tempranillo"},
    {"q": "wine aging barrel oak volatile compounds", "topic": "vino_crianza"},
    {"q": "grapevine disease powdery mildew downy management", "topic": "vino_sanidad_vid"},
    {"q": "climate change viticulture grape adaptation Mediterranean", "topic": "vino_cambio_climatico"},
    {"q": "organic biodynamic viticulture wine production", "topic": "vino_ecologico"},
    {"q": "winery technology malolactic fermentation yeast", "topic": "vino_tecnologia"},
    {"q": "wine grape variety Garnacha Monastrell Bobal Spain", "topic": "vino_variedades_esp"},
    {"q": "terroir soil vineyard wine quality influence", "topic": "vino_terroir"},
    {"q": "sparkling wine cava production method", "topic": "vino_espumoso"},
    {"q": "wine tourism enotourism rural development", "topic": "vino_enoturismo"},
]

def reconstruct_abstract(inverted_index: dict) -> str:
    """OpenAlex returns abstracts as inverted index — reconstruct to text."""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def search_openalex(query: str, per_page: int = 25) -> list:
    """Search OpenAlex for works matching the query."""
    params = {
        "search": query,
        "per_page": str(per_page),
        "select": "id,title,publication_year,abstract_inverted_index,authorships,primary_location,cited_by_count,type",
        "sort": "cited_by_count:desc",
        "filter": "type:article,publication_year:>2014",
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "SeedyBot/1.0 (mailto:david@neofarm.io)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("results", [])
    except Exception as e:
        print(f"  ⚠ Error: {e}")
        return []


def extract_article_info(work: dict) -> dict | None:
    """Extract relevant info from an OpenAlex work."""
    abstract_ii = work.get("abstract_inverted_index")
    if not abstract_ii:
        return None

    abstract = reconstruct_abstract(abstract_ii)
    if len(abstract) < 100:
        return None

    title = work.get("title", "")
    if not title:
        return None

    # Get authors
    authors = []
    for authorship in work.get("authorships", [])[:5]:
        author = authorship.get("author", {})
        name = author.get("display_name", "")
        if name:
            authors.append(name)

    # Get journal
    primary_loc = work.get("primary_location", {}) or {}
    source = primary_loc.get("source", {}) or {}
    journal = source.get("display_name", "")

    return {
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal,
        "year": work.get("publication_year"),
        "cited_by": work.get("cited_by_count", 0),
        "openalex_id": work.get("id", ""),
    }


def main():
    all_articles = []
    by_topic = {}

    for i, search in enumerate(QUERIES):
        q = search["q"]
        topic = search["topic"]
        print(f"\n[{i+1}/{len(QUERIES)}] 🔍 {topic}: \"{q}\"")

        results = search_openalex(q, per_page=25)
        count = 0

        for work in results:
            info = extract_article_info(work)
            if info:
                info["topic"] = topic
                # Avoid duplicates
                if not any(a["title"] == info["title"] for a in all_articles):
                    all_articles.append(info)
                    count += 1

        by_topic.setdefault(topic, 0)
        by_topic[topic] += count
        print(f"   → {count} artículos con abstract (de {len(results)} resultados)")

        time.sleep(0.5)  # Rate limiting (OpenAlex allows ~10 req/s but be polite)

    # Save all
    output_path = os.path.join(OUTPUT_DIR, "science_articles_raw.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for art in all_articles:
            f.write(json.dumps(art, ensure_ascii=False) + "\n")

    # Summary
    summary_path = os.path.join(OUTPUT_DIR, "download_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_articles": len(all_articles),
            "total_abstracts_chars": sum(len(a["abstract"]) for a in all_articles),
            "by_topic": by_topic,
            "avg_citations": sum(a["cited_by"] for a in all_articles) / max(len(all_articles), 1),
            "top_journals": _top_journals(all_articles),
        }, f, ensure_ascii=False, indent=2)

    total_chars = sum(len(a["abstract"]) for a in all_articles)
    print(f"\n{'='*60}")
    print(f"📊 RESUMEN ARTÍCULOS CIENTÍFICOS:")
    print(f"   Total artículos: {len(all_articles)}")
    print(f"   Total chars abstracts: {total_chars:,} (~{total_chars//4:,} tokens)")
    print(f"   Citaciones promedio: {sum(a['cited_by'] for a in all_articles) / max(len(all_articles), 1):.0f}")
    print(f"   Guardado en: {output_path}")
    print(f"\n   Por tema:")
    for topic, count in sorted(by_topic.items()):
        print(f"     {topic}: {count}")
    print(f"{'='*60}")


def _top_journals(articles: list) -> list:
    journals = {}
    for a in articles:
        j = a.get("journal", "")
        if j:
            journals[j] = journals.get(j, 0) + 1
    return sorted(journals.items(), key=lambda x: -x[1])[:20]


if __name__ == "__main__":
    main()
