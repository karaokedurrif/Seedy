#!/usr/bin/env python3
"""
Seedy — Descarga de documentación de genética de hibridación avícola.

Fuentes:
  - Aviagen (Ross, Arbor Acres, Indian River, Rowan Range)
  - Hubbard Breeders (Efficiency Plus, REDBRO, MINI, JA57, JA57Ki)
  - SASSO / Hendrix Genetics (pollos de color, ponedoras, reproductoras)

Descarga páginas web de productos y PDFs técnicos.
Guarda texto en Markdown en conocimientos/3.NeoFarm Genetica/

Uso:
    python download_hybrid_poultry.py              # Todo
    python download_hybrid_poultry.py --source sasso  # Solo SASSO
    python download_hybrid_poultry.py --dry-run
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

OUTPUT_DIR = Path(__file__).parent / "conocimientos" / "3.NeoFarm Genetica"
PDF_DIR = Path(__file__).parent / "data" / "raw" / "hybrid_poultry_pdfs"
JSONL_OUTPUT = Path(__file__).parent / "data" / "raw" / "hybrid_poultry_catalog.jsonl"

# ── SASSO (Hendrix Genetics) — Pollos tradicionales de color ──
SASSO_BASE = "https://europe.sasso-poultry.com"
SASSO_PAGES = {
    "reproductoras": [
        ("SA31A — Hembra Reproductora", "/es/productos-es/pollos-de-color-es/hembras-reproductoras/sa31a/"),
        ("SA51A — Hembra Reproductora", "/es/productos-es/pollos-de-color-es/hembras-reproductoras/sa51a/"),
        ("SA51N — Hembra Reproductora", "/es/productos-es/pollos-de-color-es/hembras-reproductoras/sa51n/"),
    ],
    "engorde_pesados": [
        ("Ruby C (C44) — Pollo Engorde Pesado", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-pesados/ruby-c-es/"),
        ("Ruby XL (XL44) — Pollo Engorde Pesado", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-pesados/ruby-xl-es/"),
        ("Ruby N (XL44N) — Pollo Engorde Pesado", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-pesados/ruby-n-es/"),
        ("Thunder (X88) — Pollo Engorde Pesado", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-pesados/thunder-es/"),
        ("Marble X (MBX) — Pollo Engorde Pesado", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-pesados/marble-x-es/"),
        ("Rainbow X — Pollo Engorde Pesado", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-pesados/rainbow-x-es/"),
    ],
    "engorde_ligeros": [
        ("Gris Cendré — Pollo Engorde Ligero", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-ligeros/gris-cendre-es/"),
        ("T44NI — Pollo Engorde Ligero", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-ligeros/t44ni-es/"),
        ("Mamba N (T77N) — Pollo Engorde Ligero", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-ligeros/mamba-n-es/"),
        ("T55NPB — Pollo Engorde Ligero", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-ligeros/t55npb-es/"),
        ("Ruby T (T44) — Pollo Engorde Ligero", "/es/productos-es/pollos-de-color-es/pollos-de-engorde-ligeros/ruby-t-es/"),
    ],
    "ponedoras": [
        ("Ciara — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/ciara-es/"),
        ("Irona — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/irona-es/"),
        ("Scarlet — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/scarlet-es/"),
        ("Ivory — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/ivory-es/"),
        ("Silver — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/silver-es/"),
        ("Carminy — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/carminy-es/"),
        ("Amazone — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/amazone-es/"),
        ("Jade — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/jade-es/"),
        ("Powdy — Ponedora de Color", "/es/productos-es/ponedoras-de-color-es/powdy-es/"),
    ],
    "recursos": [
        ("SASSO — Programa de Cría", "/es/programa-de-cr%C3%ADa-es/"),
        ("SASSO — Concepto Label Rouge", "/es/Concept-es/label-rouge/"),
        ("SASSO — Sobre Nosotros", "/es/about-us-europe-es/"),
    ],
}

SASSO_PDFS = [
    # Fichas técnicas
    ("SASSO_Ficha_Tecnica_Cria_ES", "https://europe.sasso-poultry.com/documents/704/SASSO_Technical_Memo_Rearing_ES.pdf"),
    ("SASSO_Ficha_Tecnica_Produccion_ES", "https://europe.sasso-poultry.com/documents/705/SASSO_Technical_Memo_Production_ES.pdf"),
    ("SASSO_Ficha_Tecnica_Label_Rouge_EN", "https://europe.sasso-poultry.com/documents/706/SASSO_Technical_Memo_Label_Rouge_EN.pdf"),
    ("SASSO_Ficha_Tecnica_Ponedoras_Cria_ES", "https://europe.sasso-poultry.com/documents/1727/SASSO_Technical_Memo_Layers_Rearing_ES.pdf"),
    ("SASSO_Ficha_Tecnica_Ponedoras_Produccion_ES", "https://europe.sasso-poultry.com/documents/1730/SASSO_Technical_Memo_Layers_Production_ES.pdf"),
    # Folletos de reproductoras
    ("SASSO_Reproductora_SA31A", "https://europe.sasso-poultry.com/documents/2353/SASSO_Traditional_Poultry_Breeders_SA31A_FR_EN_ES.pdf"),
    ("SASSO_Reproductora_SA51A", "https://europe.sasso-poultry.com/documents/2322/1224_HG_SASSO_Female_factsheet_SA51A_A4_FR_UK_ES_WEB_AaKgkoh.pdf"),
    ("SASSO_Reproductora_SA51N", "https://europe.sasso-poultry.com/documents/1765/SASSO_Traditional_Poultry_Breeders_SA51N.pdf"),
    # Portfolio
    ("SASSO_Portfolio_Europa_ES_2024", "https://www.hendrix-genetics.com/documents/1127/Europe_ES_SASSO_Product_portfolio_Clicable_2024.pdf"),
    # Guía manejo rural
    ("SASSO_Guia_Manejo_Rural_ES", "https://www.hendrix-genetics.com/documents/1672/SASSO_Management_Guide_Rural_Poultry_2022_ES.pdf"),
    # Ponedoras product sheets
    ("SASSO_Ponedora_Ciara", "https://europe.sasso-poultry.com/documents/2327/SASSO_Ciara_Product_sheet.pdf"),
    ("SASSO_Ponedora_Irona", "https://europe.sasso-poultry.com/documents/2326/SASSO_Irona_Product_sheet.pdf"),
    ("SASSO_Ponedora_Scarlet", "https://europe.sasso-poultry.com/documents/2328/SASSO_Scarlet_Product_sheet.pdf"),
    ("SASSO_Ponedora_Ivory", "https://europe.sasso-poultry.com/documents/2329/SASSO_Ivory_Product_sheet.pdf"),
    ("SASSO_Ponedora_Silver", "https://europe.sasso-poultry.com/documents/2325/SASSO_Silver_Product_sheet.pdf"),
    ("SASSO_Ponedora_Carminy", "https://europe.sasso-poultry.com/documents/2331/SASSO_Carminy_Product_sheet.pdf"),
    ("SASSO_Ponedora_Amazone", "https://europe.sasso-poultry.com/documents/2330/SASSO_Amazone_Product_sheet.pdf"),
    ("SASSO_Ponedora_Jade", "https://europe.sasso-poultry.com/documents/2332/SASSO_Jade_Product_sheet.pdf"),
    ("SASSO_Ponedora_Powdy", "https://europe.sasso-poultry.com/documents/2333/SASSO_Powdy_Product_sheet.pdf"),
    # Brochure
    ("SASSO_Brochure_Europe_EN", "https://europe.sasso-poultry.com/documents/1371/HG_SASSO_Brochure_Europe_EN_0224_o4BhgaL.pdf"),
]

# ── HUBBARD (Aviagen Group) — Pollos convencionales y premium ──
HUBBARD_BASE = "https://www.hubbardbreeders.com"
HUBBARD_PAGES = {
    "premium": [
        ("Hubbard — Hembras Premium (crecimiento lento)", "/es/premium/hembras-premium/"),
        ("Hubbard — Hembras Recesivas", "/es/premium/hembras-premium/7758-hembras-recesivas.html"),
    ],
    "convencional": [
        ("Hubbard — Gama Convencional", "/es/convencional/"),
    ],
    "empresa": [
        ("Hubbard — Sobre Nosotros", "/es/hubbard/"),
    ],
}

HUBBARD_PDFS = [
    # Guías (ES)
    ("Hubbard_Guia_Efficiency_Plus_ES", "https://www.hubbardbreeders.com/media/ps-guide-hubbard-efficiency-plus-es.pdf"),
    ("Hubbard_Guia_MINI_Premium_ES", "https://www.hubbardbreeders.com/media/ps-guide-mini-premium-es-20220831-ld.pdf"),
    ("Hubbard_Guia_REDBRO_ES", "https://www.hubbardbreeders.com/media/ps-guide-redbro-es-20220901-ld-1.pdf"),
    # Objetivos de resultados
    ("Hubbard_Objetivos_JA57_ENFRES", "https://www.hubbardbreeders.com/media/ps-performance-objectives-ja57-enfres.pdf"),
    ("Hubbard_Objetivos_JA57Ki_ENFRES", "https://www.hubbardbreeders.com/media/ps-performance-objectives-ja57ki-enfres.pdf"),
    ("Hubbard_Objetivos_REDBRO_MINI_ENFRES", "https://www.hubbardbreeders.com/media/ps-performance-objectives-redbro-mini-enfres.pdf"),
    ("Hubbard_Objetivos_HEP_Broiler_ENFRES", "https://www.hubbardbreeders.com/media/broiler-performance-objectives-hep-enfres-1.pdf"),
    # Guía pollo de engorde
    ("Hubbard_Guia_Broiler_Efficiency_Plus_ES", "https://www.hubbardbreeders.com/media/broiler-guide-efficiency-plus-es-20220830-ld.pdf"),
    # Boletines técnicos (ES)
    ("Hubbard_Boletin_Calidad_Agua_ES", "https://www.hubbardbreeders.com/media/ps-bulletin-hubbard-water-quality-global-es.pdf"),
    ("Hubbard_Boletin_Clasificacion_Reproductores_ES", "https://www.hubbardbreeders.com/media/ps-bulletin-hubbard-grading-of-broiler-breeders-global-es.pdf"),
    ("Hubbard_Boletin_Grasa_Pechuga_ES", "https://www.hubbardbreeders.com/media/ps-bulletin-hubbard-fat-pad-and-fleshing-conventional-es.pdf"),
    ("Hubbard_Boletin_Fibra_Dietetica_ES", "https://www.hubbardbreeders.com/media/ps-bulletin-hubbard-dietary-fibre-conventional-es.pdf"),
    ("Hubbard_Boletin_Manejo_Machos_ES", "https://www.hubbardbreeders.com/media/ps-bulletin-hubbard-male-replacement-global-es.pdf"),
    ("Hubbard_Boletin_Huevos_Piso_ES", "https://www.hubbardbreeders.com/media/ps-bulletin-hubbard-floor-egg-management-conventional-es-5.pdf"),
    ("Hubbard_Boletin_Nutricion_Pollos_Premium_ES", "https://www.hubbardbreeders.com/media/broiler-technical-bulletin-nutrition-recommendations-for-premium-chickens-es.pdf"),
]

# ── AVIAGEN — Ross, Arbor Acres, Indian River ──
AVIAGEN_BASE = "https://aviagen.com"
AVIAGEN_PAGES = {
    "corporate": [
        ("Aviagen — Sobre Aviagen (Genética Global)", "/en/about-us/about-aviagen/"),
        ("Aviagen — I+D — Investigación y Desarrollo", "/en/about-us/research-development/"),
        ("Aviagen — Sostenibilidad", "/en/about-us/breeding-sustainability/"),
    ],
}

# ──────────────────────────────────────────────────────


def clean_html_to_markdown(html: str) -> str:
    """Extrae texto legible de una página web y convierte a Markdown."""
    # Eliminar scripts, styles, nav, footer
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Headers
    for level in range(1, 7):
        html = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, l=level: f"\n{'#' * l} {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n",
            html, flags=re.DOTALL | re.IGNORECASE,
        )

    # Tables - convert to markdown tables
    def convert_table(m):
        table_html = m.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        result = []
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c if c else ' ' for c in cells]
            if cells:
                result.append("| " + " | ".join(cells) + " |")
        return "\n".join(result) if result else ""

    html = re.sub(r"<table[^>]*>.*?</table>", convert_table, html, flags=re.DOTALL | re.IGNORECASE)

    # Lists
    html = re.sub(r"<li[^>]*>", "\n- ", html, flags=re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p>", "\n\n", html, flags=re.IGNORECASE)

    # Bold, italic
    html = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<b>(.*?)</b>", r"**\1**", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<em>(.*?)</em>", r"*\1*", html, flags=re.DOTALL | re.IGNORECASE)

    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", "", html)

    # HTML entities
    html = html.replace("&nbsp;", " ")
    html = html.replace("&amp;", "&")
    html = html.replace("&lt;", "<")
    html = html.replace("&gt;", ">")
    html = html.replace("&quot;", '"')
    html = html.replace("&#39;", "'")
    html = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), html)

    # Clean whitespace
    html = re.sub(r" {2,}", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)

    # Remove noise lines
    noise = [
        "Configuración cookies", "Aceptar cookies", "Política de Cookies",
        "utilizamos cookies", "cookies esenciales", "Acepto Configurar",
        "Configuración de Cookies", "Cookie settings", "DENY ALL",
        "ALLOW ALL COOKIES", "Let me choose", "About cookies",
        "Terms of Use", "Privacy Policy", "Conditions of Sale",
        "Hendrix Genetics logo", "Copyright Hendrix Genetics",
        "Suscríbase a nuestro Boletín",
        "Mediapilote", "LinkedIn", "CTA SASSO",
        "Go to LinkedIn", "linkedin-in-brands",
        "SELECCIONE SU REGIÓN", "Norteamérica", "America Latina",
        "Europa & Rusia", "Oriente Medio",
        "© Hubbard Breeders", "Hubbard - Your choice",
        "California Consumer Privacy", "© 1998 - 20",
        "McComm", "Aviagen Group",
    ]
    lines = html.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        if any(n in s for n in noise):
            continue
        if s:
            cleaned.append(line)

    return "\n".join(cleaned).strip()


def extract_main_content(html: str) -> str:
    """Extrae el contenido principal eliminando sidebar, header, footer."""
    # Try different main content selectors
    patterns = [
        # Sasso: main content area
        r'<div[^>]*class="[^"]*block-container[^"]*"[^>]*>(.*?)(?=<footer|<!--\s*footer)',
        # Generic main
        r'<main[^>]*>(.*?)</main>',
        # Hubbard: content after breadcrumbs
        r'<div[^>]*class="[^"]*contenido[^"]*"[^>]*>(.*?)(?=<footer)',
        # Aviagen: content section
        r'<section[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</section>',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return clean_html_to_markdown(match.group(1))

    # Fallback: clean the whole page
    return clean_html_to_markdown(html)


def download_page(client: httpx.Client, name: str, url: str, source: str) -> dict | None:
    """Descarga una página web y extrae texto como Markdown."""
    try:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"  ❌ {name}: {e}")
        return None

    text = extract_main_content(resp.text)

    if len(text) < 50:
        logger.warning(f"  ⚠️ {name}: muy poco contenido ({len(text)} chars)")

    return {
        "source": source,
        "name": name,
        "url": str(resp.url),
        "text": text,
        "text_length": len(text),
    }


def download_pdf(client: httpx.Client, name: str, url: str) -> bool:
    """Descarga un PDF."""
    filepath = PDF_DIR / f"{name}.pdf"
    if filepath.exists():
        logger.info(f"    ⏭️  Ya existe: {filepath.name}")
        return True

    try:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)
        size_kb = len(resp.content) / 1024
        logger.info(f"    📄 {size_kb:.0f} KB → {filepath.name}")
        return True
    except Exception as e:
        logger.error(f"    ❌ PDF {name}: {e}")
        return False


def save_markdown(data: dict, output_dir: Path, subfolder: str) -> Path:
    """Guarda el contenido como archivo Markdown."""
    target_dir = output_dir / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    # Safe filename
    safe_name = re.sub(r'[^\w\s-]', '', data["name"]).strip().replace(' ', '_')
    safe_name = re.sub(r'_+', '_', safe_name)[:80]
    filepath = target_dir / f"{safe_name}.md"

    md = f"""# {data['name']}

**Fuente:** [{data['source']}]({data['url']})
**Tipo:** Genética de hibridación avícola

---

{data['text']}
"""

    filepath.write_text(md, encoding="utf-8")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Descarga documentación de genética avícola")
    parser.add_argument("--source", choices=["sasso", "hubbard", "aviagen", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-pdfs", action="store_true", help="No descargar PDFs")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    sources = ["sasso", "hubbard", "aviagen"] if args.source == "all" else [args.source]

    # Count total pages
    total_pages = 0
    total_pdfs = 0
    if "sasso" in sources:
        total_pages += sum(len(v) for v in SASSO_PAGES.values())
        total_pdfs += len(SASSO_PDFS)
    if "hubbard" in sources:
        total_pages += sum(len(v) for v in HUBBARD_PAGES.values())
        total_pdfs += len(HUBBARD_PDFS)
    if "aviagen" in sources:
        total_pages += sum(len(v) for v in AVIAGEN_PAGES.values())

    logger.info(f"🐔 Genética Avícola — {total_pages} páginas + {total_pdfs} PDFs")

    if args.dry_run:
        for src in sources:
            if src == "sasso":
                logger.info(f"\n{'='*50}\n  SASSO (Hendrix Genetics)")
                for cat, pages in SASSO_PAGES.items():
                    logger.info(f"  [{cat}]")
                    for name, _ in pages:
                        logger.info(f"    - {name}")
                logger.info(f"  PDFs: {len(SASSO_PDFS)}")
            elif src == "hubbard":
                logger.info(f"\n{'='*50}\n  HUBBARD Breeders")
                for cat, pages in HUBBARD_PAGES.items():
                    for name, _ in pages:
                        logger.info(f"    - {name}")
                logger.info(f"  PDFs: {len(HUBBARD_PDFS)}")
            elif src == "aviagen":
                logger.info(f"\n{'='*50}\n  AVIAGEN (Ross / Arbor Acres)")
                for cat, pages in AVIAGEN_PAGES.items():
                    for name, _ in pages:
                        logger.info(f"    - {name}")
        return

    # Prepare dirs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    JSONL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []
    pdf_ok = 0
    pdf_fail = 0

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }

    with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:

        # ── SASSO ──
        if "sasso" in sources:
            logger.info(f"\n{'='*60}")
            logger.info(f"  🐓 SASSO / Hendrix Genetics — Pollos Tradicionales")
            logger.info(f"{'='*60}")

            for cat, pages in SASSO_PAGES.items():
                logger.info(f"\n  📂 {cat} ({len(pages)} páginas)")
                for i, (name, path) in enumerate(pages, 1):
                    url = f"{SASSO_BASE}{path}"
                    logger.info(f"  [{i}/{len(pages)}] {name}...")
                    data = download_page(client, name, url, "SASSO / Hendrix Genetics")
                    if data:
                        fp = save_markdown(data, OUTPUT_DIR, "Hibridos_SASSO")
                        results.append(data)
                        logger.info(f"    ✅ {data['text_length']} chars → {fp.name}")
                    else:
                        errors.append(("sasso", name))
                    time.sleep(args.delay)

            if not args.skip_pdfs:
                logger.info(f"\n  📄 Descargando {len(SASSO_PDFS)} PDFs de SASSO...")
                for name, url in SASSO_PDFS:
                    if download_pdf(client, name, url):
                        pdf_ok += 1
                    else:
                        pdf_fail += 1
                    time.sleep(args.delay * 0.5)

        # ── HUBBARD ──
        if "hubbard" in sources:
            logger.info(f"\n{'='*60}")
            logger.info(f"  🐓 HUBBARD Breeders — Pollos Convencionales y Premium")
            logger.info(f"{'='*60}")

            for cat, pages in HUBBARD_PAGES.items():
                logger.info(f"\n  📂 {cat} ({len(pages)} páginas)")
                for i, (name, path) in enumerate(pages, 1):
                    url = f"{HUBBARD_BASE}{path}"
                    logger.info(f"  [{i}/{len(pages)}] {name}...")
                    data = download_page(client, name, url, "Hubbard Breeders")
                    if data:
                        fp = save_markdown(data, OUTPUT_DIR, "Hibridos_Hubbard")
                        results.append(data)
                        logger.info(f"    ✅ {data['text_length']} chars → {fp.name}")
                    else:
                        errors.append(("hubbard", name))
                    time.sleep(args.delay)

            if not args.skip_pdfs:
                logger.info(f"\n  📄 Descargando {len(HUBBARD_PDFS)} PDFs de Hubbard...")
                for name, url in HUBBARD_PDFS:
                    if download_pdf(client, name, url):
                        pdf_ok += 1
                    else:
                        pdf_fail += 1
                    time.sleep(args.delay * 0.5)

        # ── AVIAGEN ──
        if "aviagen" in sources:
            logger.info(f"\n{'='*60}")
            logger.info(f"  🐓 AVIAGEN — Ross / Arbor Acres / Indian River")
            logger.info(f"{'='*60}")

            for cat, pages in AVIAGEN_PAGES.items():
                logger.info(f"\n  📂 {cat} ({len(pages)} páginas)")
                for i, (name, path) in enumerate(pages, 1):
                    url = f"{AVIAGEN_BASE}{path}"
                    logger.info(f"  [{i}/{len(pages)}] {name}...")
                    data = download_page(client, name, url, "Aviagen")
                    if data:
                        fp = save_markdown(data, OUTPUT_DIR, "Hibridos_Aviagen")
                        results.append(data)
                        logger.info(f"    ✅ {data['text_length']} chars → {fp.name}")
                    else:
                        errors.append(("aviagen", name))
                    time.sleep(args.delay)

    # Save JSONL
    with open(JSONL_OUTPUT, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 RESUMEN — Genética de Hibridación Avícola")
    logger.info(f"{'='*60}")
    logger.info(f"  Páginas descargadas: {len(results)}/{total_pages}")
    logger.info(f"  PDFs descargados: {pdf_ok}/{pdf_ok + pdf_fail}")
    logger.info(f"  Errores: {len(errors)}")

    if errors:
        for src, name in errors:
            logger.info(f"    ❌ [{src}] {name}")

    by_source = {}
    for r in results:
        src = r["source"]
        by_source.setdefault(src, {"count": 0, "chars": 0})
        by_source[src]["count"] += 1
        by_source[src]["chars"] += r["text_length"]

    total_chars = sum(s["chars"] for s in by_source.values())
    logger.info(f"\n  Por fuente:")
    for src, stats in sorted(by_source.items()):
        logger.info(f"    {src}: {stats['count']} páginas, {stats['chars']:,} chars")

    logger.info(f"\n  Total: {len(results)} páginas, {total_chars:,} chars")
    logger.info(f"  JSONL: {JSONL_OUTPUT}")
    logger.info(f"  Markdown: {OUTPUT_DIR}/Hibridos_*/")
    logger.info(f"  PDFs: {PDF_DIR}/")


if __name__ == "__main__":
    main()
