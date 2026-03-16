#!/usr/bin/env python3
"""
Descarga estudios de precios, costes, indicadores y prospectiva del MAPA.
 - PDFs de Indicadores anuales, IPC alimentario, AgrInfo, ECREA, Comercio Exterior
 - Crawl de páginas de precios ganaderos coyunturales y observatorio

Salida:
  data/raw/mapa_prospectiva/pdfs/  → PDFs descargados
  data/raw/mapa_prospectiva/pages/ → Páginas crawleadas (.md)
  data/raw/mapa_prospectiva_index.jsonl → índice

Uso:
  python download_mapa_prospectiva.py
  python download_mapa_prospectiva.py --skip-pdfs    # Solo crawl de páginas
  python download_mapa_prospectiva.py --skip-crawl   # Solo PDFs
"""

import json, os, re, time, hashlib, sys, argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

# ── Config ─────────────────────────────────────────────
CRAWL4AI_URL = "http://localhost:11235/crawl"
PDF_DIR = Path("/home/davidia/Documentos/Seedy/data/raw/mapa_prospectiva/pdfs")
PAGE_DIR = Path("/home/davidia/Documentos/Seedy/data/raw/mapa_prospectiva/pages")
INDEX_FILE = Path("/home/davidia/Documentos/Seedy/data/raw/mapa_prospectiva_index.jsonl")
TIMEOUT = 90
DELAY_BETWEEN = 2.0

PDF_DIR.mkdir(parents=True, exist_ok=True)
PAGE_DIR.mkdir(parents=True, exist_ok=True)

# ── PDFs valiosos de MAPA (precios, indicadores, costes) ──
PDFS = [
    # Informes Anuales de Indicadores (datos macro sector pecuario)
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/informe-anual/informe-anual_metadatos_final.pdf",
        "name": "Informe_Anual_Indicadores_2024.pdf",
        "topic": "indicadores_anuales",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/informe-anual/indicadores_2023_accesible.pdf",
        "name": "Informe_Anual_Indicadores_2023.pdf",
        "topic": "indicadores_anuales",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/informe-anual/indicadores_2022_roboto_web__baja_resolucion.pdf",
        "name": "Informe_Anual_Indicadores_2022.pdf",
        "topic": "indicadores_anuales",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/informe-anual/iai2021_version_final_web.pdf",
        "name": "Informe_Anual_Indicadores_2021.pdf",
        "topic": "indicadores_anuales",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/informe-anual/informe_anual_indicadores_mapa_2020.pdf",
        "name": "Informe_Anual_Indicadores_2020.pdf",
        "topic": "indicadores_anuales",
    },
    # IPC alimentario (precios al consumidor)
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/serie_ipc/informes_pdf/ayp_serie_ipc_informe_n-9_enero_2026.pdf",
        "name": "IPC_Rubricas_Alimentarias_Enero_2026.pdf",
        "topic": "ipc_alimentario",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp_serie-indicadores/serie_ipc/informes_pdf/ayp_serie_ipc_informe_n-8_diciembre_2025.pdf",
        "name": "IPC_Rubricas_Alimentarias_Diciembre_2025.pdf",
        "topic": "ipc_alimentario",
    },
    # AgrInfo (análisis agroalimentario)
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp-serie-agrinfo/aypagrinfo_n40vab_saa_2022_v1.pdf",
        "name": "AgrInfo_40_Contribucion_Agroalimentario_2022.pdf",
        "topic": "agrinfo",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp-serie-agrinfo/aypagrinfo_n34vab_saa_2020.pdf",
        "name": "AgrInfo_34_Contribucion_Agroalimentario_2020.pdf",
        "topic": "agrinfo",
    },
    # ECREA - Costes y rentas explotaciones
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ecrea/notametodologicaecrea_.pdf",
        "name": "ECREA_Nota_Metodologica.pdf",
        "topic": "ecrea_costes",
    },
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ecrea/imeecrea20.pdf",
        "name": "ECREA_IME_Estudios_Costes_Rentas_2.0.pdf",
        "topic": "ecrea_costes",
    },
    # Índices de precios de exportación / importación
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/comercio-exterior/informes-especiales-comercio-exterior/otros-informes-especiales/graficos_iprix-iprim_marzo2025.pdf",
        "name": "Indices_Precios_Exportacion_Importacion_2024.pdf",
        "topic": "comercio_exterior",
    },
    # Empleo sector agrario (contexto económico)
    {
        "url": "https://www.mapa.gob.es/dam/mapa/contenido/ministerio/servicios/servicios-de-informacion/analisis-y-prospectiva/ayp-serie-empleo/ayp-empleo-165-afiliacion-y-paro-enero_2026-0.pdf",
        "name": "Empleo_Agrario_Afiliacion_Paro_Feb_2026.pdf",
        "topic": "empleo",
    },
]

# ── Páginas web a crawlear (precios ganaderos, observatorio) ──
CRAWL_PAGES = [
    {
        "url": "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/economia/precios-coyunturales-productos-ganaderos",
        "name": "precios_coyunturales_ganaderos",
        "topic": "precios_ganaderos",
        "follow_links": True,  # seguir sub-páginas
        "link_pattern": r"precios-coyunturales.*ganaderos",
    },
    {
        "url": "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/economia/precios-medios-nacionales",
        "name": "precios_medios_nacionales",
        "topic": "precios_medios",
        "follow_links": True,
        "link_pattern": r"precios-medios-nacionales",
    },
    {
        "url": "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/economia/precios-percibidos-pagados",
        "name": "indices_precios_percibidos_pagados",
        "topic": "precios_percibidos",
        "follow_links": True,
        "link_pattern": r"precios-percibidos-pagados",
    },
    {
        "url": "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-alimentacion/observatorio-precios",
        "name": "observatorio_precios_origen_destino",
        "topic": "observatorio_precios",
        "follow_links": True,
        "link_pattern": r"observatorio-precios",
    },
    {
        "url": "https://www.mapa.gob.es/es/ganaderia/temas/produccion-y-mercados-ganaderos/sectores-ganaderos",
        "name": "sectores_ganaderos",
        "topic": "sectores_ganaderos",
        "follow_links": True,
        "link_pattern": r"sectores-ganaderos/(porcino|bovino|ovino|caprino|aviar)",
    },
    {
        "url": "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/economia/cuentas-economicas-agricultura",
        "name": "cuentas_economicas_agricultura",
        "topic": "cuentas_economicas",
        "follow_links": False,
        "link_pattern": "",
    },
    {
        "url": "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/economia/red-contable-recan",
        "name": "red_contable_recan",
        "topic": "red_contable",
        "follow_links": False,
        "link_pattern": "",
    },
]


# ── Funciones ──────────────────────────────────────────

def download_pdf(url: str, dest: Path) -> bool:
    """Descarga un PDF de MAPA."""
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  ⏭️  Ya existe: {dest.name} ({dest.stat().st_size // 1024} KB)")
        return True
    try:
        print(f"  ⬇️  Descargando {dest.name}...")
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "Mozilla/5.0 Seedy-Bot"})
            r.raise_for_status()
            dest.write_bytes(r.content)
            size_kb = len(r.content) // 1024
            print(f"  ✅ {dest.name} ({size_kb} KB)")
            return True
    except Exception as e:
        print(f"  ❌ Error descargando {dest.name}: {e}")
        return False


def crawl_page(url: str) -> dict | None:
    """Crawlea una página con Crawl4AI."""
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
        print(f"  ❌ Error crawleando {url}: {e}")
    return None


def extract_markdown(result: dict) -> str:
    """Extrae markdown limpio de resultado Crawl4AI."""
    md = result.get("markdown", "")
    if isinstance(md, dict):
        text = md.get("fit_markdown") or md.get("raw_markdown") or ""
    else:
        text = str(md)

    lines = text.split("\n")
    cleaned = []
    skip_patterns = [
        "cookie", "newsletter", "suscri", "registro", "iniciar sesión",
        "política de privacidad", "términos y condiciones", "todos los derechos",
        "copyright ©", "menú principal", "navegación", "configuración cookies",
        "aceptar cookies", "mapa web", "guía de navegación", "aviso legal",
        "canal del informante", "flickr", "instagram", "telegram",
    ]
    for line in lines:
        low = line.lower().strip()
        if any(p in low for p in skip_patterns) and len(line) < 200:
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def extract_links(result: dict, base_url: str) -> list[str]:
    """Extrae links internos."""
    links_data = result.get("links", {})
    if not isinstance(links_data, dict):
        return []
    urls = set()
    for link_type in ["internal", "external"]:
        for link in links_data.get(link_type, []):
            href = link.get("href", "") if isinstance(link, dict) else str(link)
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                full = urljoin(base_url, href)
                urls.add(full.split("#")[0])
    return list(urls)


def extract_pdf_links(result: dict, base_url: str) -> list[str]:
    """Extrae links a PDFs de una página crawleada."""
    links = extract_links(result, base_url)
    return [l for l in links if l.lower().endswith(".pdf")]


def safe_filename(name: str) -> str:
    """Genera un nombre de fichero seguro."""
    return re.sub(r'[^\w\-.]', '_', name)


def save_page(content: str, name: str, url: str, topic: str) -> Path | None:
    """Guarda una página crawleada como .md."""
    if len(content) < 200:
        return None
    fname = safe_filename(name) + ".md"
    path = PAGE_DIR / fname
    header = f"---\nsource: {url}\ntopic: {topic}\ndate: {time.strftime('%Y-%m-%d')}\n---\n\n"
    path.write_text(header + content, encoding="utf-8")
    return path


def log_index(entry: dict):
    """Añade una entrada al índice."""
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Main ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Descarga estudios MAPA prospectiva")
    parser.add_argument("--skip-pdfs", action="store_true", help="No descargar PDFs")
    parser.add_argument("--skip-crawl", action="store_true", help="No crawlear páginas")
    args = parser.parse_args()

    stats = {"pdfs_ok": 0, "pdfs_err": 0, "pages_ok": 0, "pages_err": 0, "extra_pdfs": 0}

    # ── 1. Descargar PDFs ──
    if not args.skip_pdfs:
        print("\n📄 DESCARGANDO PDFs DE MAPA PROSPECTIVA")
        print("=" * 60)
        for pdf_info in PDFS:
            dest = PDF_DIR / pdf_info["name"]
            ok = download_pdf(pdf_info["url"], dest)
            if ok:
                stats["pdfs_ok"] += 1
                log_index({
                    "type": "pdf",
                    "name": pdf_info["name"],
                    "url": pdf_info["url"],
                    "topic": pdf_info["topic"],
                    "path": str(dest),
                    "size_kb": dest.stat().st_size // 1024 if dest.exists() else 0,
                })
            else:
                stats["pdfs_err"] += 1
            time.sleep(0.5)

    # ── 2. Crawl de páginas ──
    if not args.skip_crawl:
        print("\n🌐 CRAWLEANDO PÁGINAS DE PRECIOS Y MERCADOS")
        print("=" * 60)

        visited = set()

        for page_info in CRAWL_PAGES:
            url = page_info["url"]
            name = page_info["name"]
            topic = page_info["topic"]
            print(f"\n📌 {name}: {url}")

            # Crawlear página principal
            result = crawl_page(url)
            if not result:
                stats["pages_err"] += 1
                continue

            content = extract_markdown(result)
            saved = save_page(content, name, url, topic)
            if saved:
                print(f"  ✅ Guardado: {saved.name} ({len(content)} chars)")
                stats["pages_ok"] += 1
                log_index({
                    "type": "page",
                    "name": name,
                    "url": url,
                    "topic": topic,
                    "path": str(saved),
                    "chars": len(content),
                })
            else:
                print(f"  ⚠️ Contenido demasiado corto, saltando")
                stats["pages_err"] += 1

            # Buscar PDFs enlazados en la página
            pdf_links = extract_pdf_links(result, url)
            for pdf_url in pdf_links[:10]:  # max 10 PDFs por página
                pdf_name = pdf_url.split("/")[-1]
                if len(pdf_name) < 5:
                    continue
                pdf_dest = PDF_DIR / safe_filename(pdf_name)
                if pdf_dest.exists():
                    continue
                if download_pdf(pdf_url, pdf_dest):
                    stats["extra_pdfs"] += 1
                    log_index({
                        "type": "pdf_from_crawl",
                        "name": pdf_name,
                        "url": pdf_url,
                        "topic": topic,
                        "path": str(pdf_dest),
                        "source_page": url,
                    })
                time.sleep(0.5)

            visited.add(url)

            # Seguir sub-enlaces si está configurado
            if page_info.get("follow_links") and page_info.get("link_pattern"):
                pattern = re.compile(page_info["link_pattern"])
                sub_links = extract_links(result, url)
                sub_links = [l for l in sub_links if pattern.search(l) and l not in visited]
                sub_links = sub_links[:8]  # max 8 sub-páginas

                for sub_url in sub_links:
                    if sub_url in visited:
                        continue
                    visited.add(sub_url)
                    sub_name = f"{name}__{urlparse(sub_url).path.split('/')[-1]}"
                    print(f"  🔗 Sub-página: {sub_url}")

                    time.sleep(DELAY_BETWEEN)
                    sub_result = crawl_page(sub_url)
                    if not sub_result:
                        continue

                    sub_content = extract_markdown(sub_result)
                    sub_saved = save_page(sub_content, sub_name, sub_url, topic)
                    if sub_saved:
                        print(f"    ✅ {sub_saved.name} ({len(sub_content)} chars)")
                        stats["pages_ok"] += 1
                        log_index({
                            "type": "sub_page",
                            "name": sub_name,
                            "url": sub_url,
                            "topic": topic,
                            "path": str(sub_saved),
                            "chars": len(sub_content),
                        })

                    # PDFs en sub-páginas
                    sub_pdfs = extract_pdf_links(sub_result, sub_url)
                    for pdf_url in sub_pdfs[:5]:
                        pdf_name = pdf_url.split("/")[-1]
                        if len(pdf_name) < 5:
                            continue
                        pdf_dest = PDF_DIR / safe_filename(pdf_name)
                        if pdf_dest.exists():
                            continue
                        if download_pdf(pdf_url, pdf_dest):
                            stats["extra_pdfs"] += 1
                        time.sleep(0.5)

            time.sleep(DELAY_BETWEEN)

    # ── Resumen ──
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print(f"  PDFs descargados:      {stats['pdfs_ok']}")
    print(f"  PDFs con error:        {stats['pdfs_err']}")
    print(f"  Páginas crawleadas:    {stats['pages_ok']}")
    print(f"  Páginas con error:     {stats['pages_err']}")
    print(f"  PDFs extra (de crawl): {stats['extra_pdfs']}")
    print(f"\n  📁 PDFs en: {PDF_DIR}")
    print(f"  📁 Páginas en: {PAGE_DIR}")
    print(f"  📋 Índice: {INDEX_FILE}")


if __name__ == "__main__":
    main()
