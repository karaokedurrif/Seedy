#!/usr/bin/env python3
"""
Descarga contenido técnico de sitios agropecuarios españoles sobre porcino, vacuno y aviar.
Usa Crawl4AI (local) para renderizar JS y extraer markdown limpio.

Sitios:  3tres3, Archivo Anaporc, ANEMBE, UCO Archivos Zootecnia,
         MAPA manual razas, AgroTerra, AgroInformación, AgroDigital,
         ASAJA, ACNV, COAG.

Salida:  data/raw/agro_sites/ → ficheros .md por artículo
         data/raw/agro_sites_index.jsonl → índice con metadatos
"""

import json, os, re, time, hashlib, sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

# ── Config ─────────────────────────────────────────────
CRAWL4AI_URL = "http://localhost:11235/crawl"
OUTPUT_DIR = Path("/home/davidia/Documentos/Seedy/data/raw/agro_sites")
INDEX_FILE = Path("/home/davidia/Documentos/Seedy/data/raw/agro_sites_index.jsonl")
MIN_CONTENT_LEN = 300  # chars mínimo para guardar
DELAY_BETWEEN = 1.5    # segundos entre requests
TIMEOUT = 60           # timeout por página

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Sitios y sus rutas de interés ──────────────────────
SITES = [
    # ── 3tres3 (porcino) ──
    {
        "name": "3tres3",
        "species": "porcino",
        "seed_urls": [
            "https://www.3tres3.com/articulos/razas-porcinas_1446/",
            "https://www.3tres3.com/articulos/nutricion-porcina_44/",
            "https://www.3tres3.com/articulos/manejo-general-del-cerdo_46/",
            "https://www.3tres3.com/articulos/reproduccion_47/",
            "https://www.3tres3.com/articulos/sanidad_48/",
            "https://www.3tres3.com/articulos/genetica_49/",
            "https://www.3tres3.com/articulos/instalaciones-en-porcino_51/",
            "https://www.3tres3.com/articulos/bienestar_174/",
            "https://www.3tres3.com/articulos/mercados-y-economia_53/",
        ],
        "link_pattern": r"3tres3\.com/articulos/[a-z].*_\d{4,}",
        "max_articles": 60,
    },
    # ── Archivo Anaporc (porcino científico) ──
    {
        "name": "archivo_anaporc",
        "species": "porcino",
        "seed_urls": [
            "https://www.archivo-anaporc.com/sanidad/",
            "https://www.archivo-anaporc.com/nutricion/",
            "https://www.archivo-anaporc.com/genetica/",
            "https://www.archivo-anaporc.com/manejo/",
            "https://www.archivo-anaporc.com/reproduccion/",
            "https://www.archivo-anaporc.com/bienestar-animal/",
        ],
        "link_pattern": r"archivo-anaporc\.com/\d{4}/\d{2}/\d{2}/",
        "max_articles": 50,
    },
    # ── ANEMBE (vacuno) ──
    {
        "name": "anembe",
        "species": "vacuno",
        "seed_urls": [
            "https://www.anembe.com/agenda/eventos",
            "https://www.anembe.com/anembe-english",
            "https://www.anembe.com/publicaciones",
        ],
        "link_pattern": r"anembe\.com/(publicaciones|blog|agenda/evento)/",
        "max_articles": 30,
    },
    # ── UCO Archivos de Zootecnia (científico multiespecie) ──
    {
        "name": "uco_zootecnia",
        "species": "multiespecie",
        "seed_urls": [
            "https://www.uco.es/ucopress/az/index.php/az/issue/archive",
        ],
        "link_pattern": r"az/(article/view|issue/view)/\d+",
        "max_articles": 40,
    },
    # ── MAPA manual razas ganaderas ──
    {
        "name": "mapa_manual_razas",
        "species": "multiespecie",
        "seed_urls": [
            "https://www.mapa.gob.es/es/ganaderia/temas/zootecnia/razas-ganaderas/manual-usuarios/",
        ],
        "link_pattern": r"razas-ganaderas/(razas|manual)",
        "max_articles": 30,
    },
    # ── AgroTerra (marketplace + artículos) ──
    {
        "name": "agroterra",
        "species": "multiespecie",
        "seed_urls": [
            "https://blog.agroterra.com/descubriendo/razas-de-ganado-bovino/76930",
            "https://blog.agroterra.com/descubriendo/razas-de-ganado-porcino/77008",
            "https://blog.agroterra.com/descubriendo/razas-de-gallinas/77072",
            "https://blog.agroterra.com/",
        ],
        "link_pattern": r"blog\.agroterra\.com/.+/\d+",
        "max_articles": 30,
    },
    # ── AgroInformación ──
    {
        "name": "agroinformacion",
        "species": "multiespecie",
        "seed_urls": [
            "https://agroinformacion.com/category/ganaderia/porcino",
            "https://agroinformacion.com/category/ganaderia/vacuno-de-carne",
            "https://agroinformacion.com/category/ganaderia/avicultura-y-cunicultura",
            "https://agroinformacion.com/category/ganaderia/sanidad-animal",
        ],
        "link_pattern": r"agroinformacion\.com/[a-z][a-z0-9-]{30,}",
        "max_articles": 40,
    },
    # ── AgroDigital ──
    {
        "name": "agrodigital",
        "species": "multiespecie",
        "seed_urls": [
            "https://www.agrodigital.com/category/ganaderia/",
            "https://www.agrodigital.com/category/ganaderia/porcino/",
            "https://www.agrodigital.com/category/ganaderia/vacuno/",
        ],
        "link_pattern": r"agrodigital\.com/\d{4}/\d{2}/\d{2}/",
        "max_articles": 40,
    },
    # ── ASAJA (sindicato agrario — informes) ──
    {
        "name": "asaja",
        "species": "multiespecie",
        "seed_urls": [
            "https://www.asaja.com/publicaciones",
        ],
        "link_pattern": r"asaja\.com/(publicaciones|noticias|sala-de-prensa)",
        "max_articles": 20,
    },
    # ── ACNV (Asociación Nacional Veterinarios) ──
    {
        "name": "acnv",
        "species": "vacuno",
        "seed_urls": [
            "https://www.acnv.es/",
        ],
        "link_pattern": r"acnv\.es/[^/]+",
        "max_articles": 20,
    },
    # ── COAG (organización agraria) ──
    {
        "name": "coag",
        "species": "multiespecie",
        "seed_urls": [
            "https://www.coag.org/ganaderia",
            "https://www.coag.org/noticias",
        ],
        "link_pattern": r"coag\.org/(noticias|ganaderia|contenido)",
        "max_articles": 20,
    },
]


# ── Utilidades ─────────────────────────────────────────

def slug(url: str) -> str:
    """Genera un identificador seguro para el fichero basado en la URL."""
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    path = urlparse(url).path.strip("/").replace("/", "_")[:80]
    return f"{path}_{h}" if path else h


def crawl_page(url: str) -> dict | None:
    """Crawlea una página con Crawl4AI y devuelve markdown + links."""
    try:
        resp = httpx.post(
            CRAWL4AI_URL,
            json={
                "urls": [url],
                "word_count_threshold": 30,
                "bypass_cache": True,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("results"):
            return data["results"][0]
    except Exception as e:
        print(f"  ⚠ Error crawling {url}: {e}")
    return None


def extract_markdown(result: dict) -> str:
    """Extrae el markdown limpio de un resultado Crawl4AI."""
    md = result.get("markdown", "")
    if isinstance(md, dict):
        # fit_markdown tiene el contenido principal sin nav/footer
        text = md.get("fit_markdown") or md.get("raw_markdown") or ""
    else:
        text = str(md)

    # Limpiar: quitar menús de navegación, cookies notices, etc.
    lines = text.split("\n")
    cleaned = []
    skip_patterns = [
        "cookie", "newsletter", "suscri", "registro", "iniciar sesión",
        "política de privacidad", "términos y condiciones", "todos los derechos",
        "copyright ©", "menú principal", "navegación",
    ]
    for line in lines:
        low = line.lower().strip()
        if any(p in low for p in skip_patterns) and len(line) < 200:
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def extract_links(result: dict, base_url: str) -> list[str]:
    """Extrae links internos de un resultado Crawl4AI."""
    links_data = result.get("links", {})
    if not isinstance(links_data, dict):
        return []

    urls = set()
    for link_type in ["internal", "external"]:
        for link in links_data.get(link_type, []):
            href = link.get("href", "") if isinstance(link, dict) else str(link)
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                full = urljoin(base_url, href)
                urls.add(full.split("#")[0].split("?")[0])  # quitar fragments/params
    return list(urls)


def filter_article_links(links: list[str], pattern: str, base_domain: str) -> list[str]:
    """Filtra links que coinciden con el patrón de artículos del sitio."""
    regex = re.compile(pattern)
    filtered = []
    seen = set()
    for url in links:
        # Aceptar dominio base o subdominio (blog.agroterra vs www.agroterra)
        domain_root = base_domain.replace("www.", "")
        if domain_root not in url:
            continue
        # Excluir seeds, categorías genéricas, locales alternativos
        if "/latam/" in url or "/es-ar/" in url or "/es-mx/" in url:
            continue
        if regex.search(url) and url not in seen:
            seen.add(url)
            filtered.append(url)
    return filtered


def already_downloaded(url: str) -> bool:
    """Verifica si ya se descargó explorando el fichero de índice."""
    s = slug(url)
    return (OUTPUT_DIR / f"{s}.md").exists()


# ── Descarga principal ─────────────────────────────────

def download_site(site: dict, stats: dict):
    """Descarga artículos de un sitio siguiendo seed URLs → artículo links."""
    name = site["name"]
    species = site["species"]
    pattern = site["link_pattern"]
    max_articles = site["max_articles"]

    print(f"\n{'='*60}")
    print(f"📥 {name.upper()} ({species}) — max {max_articles} artículos")
    print(f"{'='*60}")

    # Fase 1: Crawlear seeds para descubrir artículos
    article_urls = set()
    base_domain = urlparse(site["seed_urls"][0]).netloc

    for seed_url in site["seed_urls"]:
        print(f"\n  🔍 Crawleando seed: {seed_url}")
        result = crawl_page(seed_url)
        if not result:
            print(f"  ⚠ No se pudo crawlear seed: {seed_url}")
            continue

        links = extract_links(result, seed_url)
        matched = filter_article_links(links, pattern, base_domain)
        print(f"  → {len(links)} links totales, {len(matched)} coinciden con patrón")

        article_urls.update(matched)

        # También intentar guardar la seed si tiene contenido
        md = extract_markdown(result)
        if len(md) > MIN_CONTENT_LEN:
            save_article(seed_url, md, name, species, "seed_page", stats)

        time.sleep(DELAY_BETWEEN)

        if len(article_urls) >= max_articles:
            break

    # Fase 2: Crawlear artículos encontrados
    article_list = sorted(article_urls)[:max_articles]
    print(f"\n  📄 {len(article_list)} artículos a descargar")

    for i, url in enumerate(article_list, 1):
        if already_downloaded(url):
            print(f"  [{i}/{len(article_list)}] ⏭ Ya descargado: {url[-60:]}")
            stats["skipped"] += 1
            continue

        print(f"  [{i}/{len(article_list)}] ⬇ {url[-70:]}")
        result = crawl_page(url)
        if not result:
            stats["errors"] += 1
            continue

        md = extract_markdown(result)
        if len(md) < MIN_CONTENT_LEN:
            print(f"    ⚠ Contenido muy corto ({len(md)} chars), saltando")
            stats["too_short"] += 1
            continue

        save_article(url, md, name, species, "article", stats)
        time.sleep(DELAY_BETWEEN)


def save_article(url: str, markdown: str, source: str, species: str, doc_type: str, stats: dict):
    """Guarda un artículo en disco y añade al índice."""
    s = slug(url)
    filepath = OUTPUT_DIR / f"{s}.md"

    # Extraer título del markdown (primer heading)
    title = ""
    for line in markdown.split("\n"):
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break
    if not title:
        title = urlparse(url).path.strip("/").split("/")[-1].replace("-", " ").title()

    # Añadir header con metadatos al markdown
    header = (
        f"---\n"
        f"source: {source}\n"
        f"species: {species}\n"
        f"url: {url}\n"
        f"title: {title}\n"
        f"type: {doc_type}\n"
        f"downloaded: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"---\n\n"
    )
    filepath.write_text(header + markdown, encoding="utf-8")

    # Añadir al índice JSONL
    record = {
        "source": source,
        "species": species,
        "url": url,
        "title": title,
        "file": str(filepath),
        "text_length": len(markdown),
        "type": doc_type,
    }
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    stats["downloaded"] += 1
    print(f"    ✅ {len(markdown):,} chars → {filepath.name}")


# ── Punto de entrada ───────────────────────────────────

def main():
    # Filtrar sites si se pasan como argumento
    site_filter = sys.argv[1:] if len(sys.argv) > 1 else None

    stats = {"downloaded": 0, "skipped": 0, "errors": 0, "too_short": 0}

    sites_to_process = SITES
    if site_filter:
        sites_to_process = [s for s in SITES if s["name"] in site_filter]
        if not sites_to_process:
            print(f"Sitios válidos: {[s['name'] for s in SITES]}")
            return

    print(f"🌐 Descargando de {len(sites_to_process)} sitios agropecuarios")
    print(f"   Destino: {OUTPUT_DIR}")

    for site in sites_to_process:
        try:
            download_site(site, stats)
        except Exception as e:
            print(f"\n❌ Error procesando {site['name']}: {e}")
            stats["errors"] += 1

    print(f"\n{'='*60}")
    print(f"📊 RESUMEN FINAL")
    print(f"{'='*60}")
    print(f"  ✅ Descargados:  {stats['downloaded']}")
    print(f"  ⏭ Ya existían:  {stats['skipped']}")
    print(f"  ⚠ Muy cortos:   {stats['too_short']}")
    print(f"  ❌ Errores:      {stats['errors']}")

    if INDEX_FILE.exists():
        with open(INDEX_FILE) as f:
            total_records = sum(1 for _ in f)
        print(f"  📑 Total en índice: {total_records}")


if __name__ == "__main__":
    main()
