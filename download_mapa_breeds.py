#!/usr/bin/env python3
"""
Seedy — Descarga del Catálogo Oficial de Razas de Ganado de España (MAPA/ARCA).

Descarga las fichas detalladas de razas bovina, porcina y aviar del sistema ARCA
y las guarda como Markdown en conocimientos/3.NeoFarm Genetica/

Fuente: https://www.mapa.gob.es/es/ganaderia/temas/zootecnia/razas-ganaderas/razas/catalogo-razas/
RD 45/2019 — Catálogo Oficial de Razas de Ganado de España

Uso:
    python download_mapa_breeds.py              # Descargar todo
    python download_mapa_breeds.py --species bovino  # Solo bovino
    python download_mapa_breeds.py --dry-run    # Solo listar razas
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.mapa.gob.es/es/ganaderia/temas/zootecnia/razas-ganaderas/razas/catalogo-razas"

# Sub-páginas por raza (además de la principal de Datos Generales)
SUBPAGES = [
    ("datos_morfologicos", "Datos Morfológicos"),
    ("usos_sistema", "Usos y Sistema de Explotación"),
    ("datos_productivos", "Datos Productivos"),
    ("datos_reglamentacion", "Programa de Cría y Reglamentación"),
]

# ── Catálogo completo extraído de ARCA ────────────────
# Estructura: { especie: [ (nombre_display, slug_url) ] }
BREED_CATALOG = {
    "aviar": [
        ("Andaluza Azul", "aviar/andaluza-azul"),
        ("Euskal Antzara", "aviar/euskal-antzara"),
        ("Combatiente Español", "aviar/combatiente-espanol"),
        ("Euskal Oiloa", "aviar/euskal-oiloa"),
        ("Galiña de Mos", "aviar/galina-mos"),
        ("Gallina Castellana Negra", "aviar/gallina-castellana-negra"),
        ("Gallina Eivissenca", "aviar/gallina-ibicenca"),
        ("Gallina Empordanesa", "aviar/gallina-empordanesa"),
        ("Gallina Extremeña Azul", "aviar/gallina-extremena-azul"),
        ("Gallina del Prat", "aviar/gallina-prat"),
        ("Gallina Pedresa", "aviar/gallina-pedresa"),
        ("Gallina del Sobrarbe", "aviar/gallina-sobrarbe"),
        ("Indio de León", "aviar/indio-leon"),
        ("Mallorquina (Aviar)", "aviar/mallorquina"),
        ("Menorquina (Aviar)", "aviar/menorquina"),
        ("Murciana (Aviar)", "aviar/murciana"),
        ("Oca Empordanesa", "aviar/oca-empordanesa"),
        ("Pardo de León", "aviar/pardo-leon"),
        ("Penedesenca", "aviar/penedesenca"),
        ("Pita Pinta", "aviar/pita-pinta"),
        ("Utrerana", "aviar/utrerana"),
        ("Valenciana de Chulilla", "aviar/valenciana-chulilla"),
    ],
    "bovino": [
        ("Albera", "bovino/albera"),
        ("Alistana-Sanabresa", "bovino/alistana-sanabresa"),
        ("Asturiana de la Montaña", "bovino/asturiana-montana"),
        ("Asturiana de los Valles", "bovino/asturiana-de-los-valles"),
        ("Avileña-Negra Ibérica", "bovino/avilena-negra-iberica"),
        ("Avileña-Negra Ibérica (var. Bociblanca)", "bovino/avilena-negra-iberica-bociblanca"),
        ("Berrenda en Colorado", "bovino/berrenda-colorado"),
        ("Berrenda en Negro", "bovino/berrenda-negro"),
        ("Betizu", "bovino/betizu"),
        ("Blanca Cacereña", "bovino/blanca-cacerena"),
        ("Blonda de Aquitania", "bovino/blonda-aquitania"),
        ("Bruna de los Pirineos", "bovino/bruna-pirineos"),
        ("Cachena", "bovino/cachena"),
        ("Caldelá", "bovino/caldela"),
        ("Canaria (Bovino)", "bovino/canaria"),
        ("Cárdena Andaluza", "bovino/cardena-andaluza"),
        ("Charolesa", "bovino/charloresa"),
        ("Fleckvieh", "bovino/fleckvieh"),
        ("Frieiresa", "bovino/frieiresa"),
        ("Frisona", "bovino/frisona"),
        ("Lidia", "bovino/lidia"),
        ("Limiá", "bovino/limia"),
        ("Limusina", "bovino/limusina"),
        ("Mallorquina (Bovino)", "bovino/mallorquina"),
        ("Mantequera Leonesa", "bovino/mantequera-leonesa"),
        ("Marismeña (Bovino)", "bovino/marismena"),
        ("Menorquina (Bovino)", "bovino/menorquina"),
        ("Monchina", "bovino/monchina"),
        ("Morucha", "bovino/morucha"),
        ("Morucha (var. Negra)", "bovino/morucha-negra"),
        ("Murciana-Levantina", "bovino/murciana-levantina"),
        ("Negra Andaluza", "bovino/negra-andaluza"),
        ("Pajuna", "bovino/pajuna"),
        ("Pallaresa", "bovino/pallaresa"),
        ("Palmera (Bovino)", "bovino/palmera"),
        ("Parda", "bovino/parda"),
        ("Parda de Montaña", "bovino/parda-montana"),
        ("Pasiega", "bovino/pasiega"),
        ("Pirenaica", "bovino/pirenaica"),
        ("Retinta", "bovino/retinta"),
        ("Rubia Gallega", "bovino/rubia-gallega"),
        ("Sayaguesa", "bovino/sayaguesa"),
        ("Serrana Negra", "bovino/serrana-negra"),
        ("Serrana de Teruel", "bovino/serrana-teruel"),
        ("Terreña", "bovino/terrena"),
        ("Tudanca", "bovino/tudanca"),
        ("Vianesa", "bovino/vianesa"),
    ],
    "porcino": [
        ("Chato Murciano", "porcino/chato-murciano"),
        ("Duroc", "porcino/duroc"),
        ("Euskal Txerria", "porcino/euskal-txerria"),
        ("Gochu Asturcelta", "porcino/gochu-asturcelta"),
        ("Ibérico", "porcino/iberico"),
        ("Ibérico (var. Entrepelado)", "porcino/iberico-entrepelado"),
        ("Ibérico (var. Lampiño)", "porcino/iberico-lampino"),
        ("Ibérico (var. Manchado de Jabugo)", "porcino/iberico-manchado-jabugo"),
        ("Ibérico (var. Retinto)", "porcino/iberico-retinto"),
        ("Ibérico (var. Torbiscal)", "porcino/iberico-torbiscal"),
        ("Landrace", "porcino/landrace"),
        ("Large White", "porcino/large-white"),
        ("Negra Canaria", "porcino/negra-canaria"),
        ("Pietrain", "porcino/pietrain"),
        ("Porco Celta", "porcino/celta"),
        ("Porc Negre Mallorquí", "porcino/negra-mallorquina"),
    ],
}

# Directorio de salida
OUTPUT_DIR = Path(__file__).parent / "conocimientos" / "3.NeoFarm Genetica"
JSONL_OUTPUT = Path(__file__).parent / "data" / "raw" / "mapa_breeds_catalog.jsonl"


def extract_tables_as_markdown(html_chunk: str) -> str:
    """Extrae tablas HTML y las convierte a texto Markdown limpio."""
    result_parts = []

    # Find all panels with tables
    for table_match in re.finditer(r'<table[^>]*>(.*?)</table>', html_chunk, re.DOTALL):
        table_html = table_match.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c for c in cells if c]

            if not cells:
                continue

            # Header row (th)
            if '<th' in row:
                if len(cells) == 1:
                    result_parts.append(f"\n**{cells[0]}**")
                else:
                    result_parts.append(" | ".join(cells))
            else:
                # Data row
                if len(cells) == 1:
                    result_parts.append(cells[0])
                elif len(cells) == 2:
                    result_parts.append(f"- **{cells[0]}** {cells[1]}")
                else:
                    result_parts.append(" | ".join(cells))

    text = "\n".join(result_parts)

    # Clean up entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_breed_section(html: str) -> str:
    """Extrae el contenido de la ficha de raza del HTML de ARCA.
    
    Estructura de la página ARCA:
    - div#main > ... > h3 'Datos Generales' ... h3 '{breed}' ... h3 'Accesos directos'
    - El contenido útil está entre 'Datos Generales' y 'Accesos directos'
    """
    # Buscar las posiciones clave mediante h3 títulos
    datos_gen = re.search(r'<h3[^>]*>\s*Datos Generales\s*</h3>', html, re.IGNORECASE)
    accesos = re.search(r'<h3[^>]*>\s*Accesos directos\s*</h3>', html, re.IGNORECASE)

    if datos_gen and accesos:
        chunk = html[datos_gen.start():accesos.start()]
    elif datos_gen:
        # Fallback: take 12KB after Datos Generales
        chunk = html[datos_gen.start():datos_gen.start() + 12000]
    else:
        # Broader fallback: find id="col-izquierda"
        col_start = html.find('id="col-izquierda"')
        if col_start > 0:
            chunk = html[col_start:col_start + 15000]
        else:
            # Last resort: whole div#main
            main_start = html.find('id="main"')
            if main_start > 0:
                chunk = html[main_start:main_start + 15000]
            else:
                chunk = html

    return extract_tables_as_markdown(chunk)


def download_breed(client: httpx.Client, species: str, breed_name: str, slug: str, delay: float) -> dict | None:
    """Descarga la ficha completa de una raza (página principal + sub-páginas)."""
    base_url = f"{BASE_URL}/{slug}"
    sections = {}

    # 1. Página principal (Datos Generales)
    try:
        resp = client.get(base_url, follow_redirects=True)
        resp.raise_for_status()
        sections["Datos Generales"] = extract_breed_section(resp.text)
    except httpx.HTTPStatusError as e:
        logger.error(f"  HTTP {e.response.status_code} para {breed_name}: {base_url}")
        return None
    except Exception as e:
        logger.error(f"  Error descargando {breed_name}: {e}")
        return None

    # 2. Sub-páginas (morfología, usos, producción, reglamentación)
    for subpage_slug, subpage_title in SUBPAGES:
        sub_url = f"{base_url}/{subpage_slug}"
        try:
            time.sleep(delay * 0.5)  # Medio delay entre sub-páginas
            resp = client.get(sub_url, follow_redirects=True)
            resp.raise_for_status()
            content = extract_breed_section(resp.text)
            if content and len(content) > 20:
                sections[subpage_title] = content
        except Exception:
            pass  # Sub-páginas opcionales

    # Combinar todo el texto
    text_parts = []
    for section_title, section_content in sections.items():
        text_parts.append(f"\n## {section_title}\n\n{section_content}")

    full_text = "\n".join(text_parts).strip()

    if len(full_text) < 100:
        logger.warning(f"  {breed_name}: contenido muy corto ({len(full_text)} chars)")

    return {
        "species": species,
        "breed_name": breed_name,
        "url": base_url,
        "text": full_text,
        "text_length": len(full_text),
        "sections": list(sections.keys()),
    }


def save_as_markdown(breed_data: dict, output_dir: Path):
    """Guarda la ficha como archivo Markdown."""
    species = breed_data["species"]
    name = breed_data["breed_name"]
    
    # Crear subdirectorio por especie
    species_dir = output_dir / f"MAPA_Razas_{species.capitalize()}"
    species_dir.mkdir(parents=True, exist_ok=True)
    
    # Nombre de archivo seguro
    safe_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    filepath = species_dir / f"{safe_name}.md"
    
    # Construir markdown
    md = f"""# {name}

**Especie:** {species.capitalize()}
**Fuente:** [Catálogo Oficial de Razas — MAPA/ARCA]({breed_data['url']})
**Base legal:** RD 45/2019 — Catálogo Oficial de Razas de Ganado de España

---

{breed_data['text']}
"""
    
    filepath.write_text(md, encoding="utf-8")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Descarga catálogo MAPA de razas ganaderas")
    parser.add_argument("--species", choices=["bovino", "porcino", "aviar", "all"], default="all",
                        help="Especie a descargar")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar razas, no descargar")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay entre requests (segs)")
    args = parser.parse_args()
    
    # Especies a procesar
    species_list = list(BREED_CATALOG.keys()) if args.species == "all" else [args.species]
    
    total_breeds = sum(len(BREED_CATALOG[s]) for s in species_list)
    logger.info(f"📋 Catálogo MAPA — {total_breeds} razas en {len(species_list)} especies")
    
    for species in species_list:
        breeds = BREED_CATALOG[species]
        logger.info(f"\n{'='*60}")
        logger.info(f"  {species.upper()}: {len(breeds)} razas")
        logger.info(f"{'='*60}")
        for name, slug in breeds:
            logger.info(f"  - {name}")
    
    if args.dry_run:
        logger.info(f"\n(dry-run) {total_breeds} razas identificadas")
        return
    
    # Preparar directorio de salida
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSONL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    
    # Descargar
    results = []
    errors = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    
    with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
        for species in species_list:
            breeds = BREED_CATALOG[species]
            logger.info(f"\n📂 Descargando {species.upper()} ({len(breeds)} razas)...")
            
            for i, (name, slug) in enumerate(breeds, 1):
                logger.info(f"  [{i}/{len(breeds)}] {name}...")
                
                data = download_breed(client, species, name, slug, args.delay)
                
                if data:
                    # Guardar Markdown
                    filepath = save_as_markdown(data, OUTPUT_DIR)
                    results.append(data)
                    logger.info(f"    ✅ {data['text_length']} chars, secciones: {', '.join(data['sections'])} → {filepath.name}")
                else:
                    errors.append((species, name, slug))
                    logger.error(f"    ❌ Error")
                
                # Rate limiting
                if i < len(breeds):
                    time.sleep(args.delay)
    
    # Guardar JSONL consolidado
    with open(JSONL_OUTPUT, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    # Resumen
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 RESUMEN")
    logger.info(f"{'='*60}")
    logger.info(f"  Descargadas: {len(results)}/{total_breeds}")
    logger.info(f"  Errores: {len(errors)}")
    
    if errors:
        logger.info(f"\n  Razas con error:")
        for sp, name, slug in errors:
            logger.info(f"    - [{sp}] {name}")
    
    by_species = {}
    total_chars = 0
    for r in results:
        sp = r["species"]
        by_species.setdefault(sp, {"count": 0, "chars": 0})
        by_species[sp]["count"] += 1
        by_species[sp]["chars"] += r["text_length"]
        total_chars += r["text_length"]
    
    logger.info(f"\n  Por especie:")
    for sp, stats in sorted(by_species.items()):
        logger.info(f"    {sp}: {stats['count']} razas, {stats['chars']:,} chars")
    
    logger.info(f"\n  Total: {len(results)} fichas, {total_chars:,} chars")
    logger.info(f"  JSONL: {JSONL_OUTPUT}")
    logger.info(f"  Markdown: {OUTPUT_DIR}/MAPA_Razas_*/")


if __name__ == "__main__":
    main()
