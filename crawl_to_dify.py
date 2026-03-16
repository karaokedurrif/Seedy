#!/usr/bin/env python3
"""
Seedy — Pipeline: Crawl4AI → Dify KB (automático).

Dado una lista de URLs, las crawlea con Crawl4AI, convierte a markdown
y las sube automáticamente a la KB de Dify "NeoFarm Seedy".

Uso:
    python3 crawl_to_dify.py URL1 URL2 URL3 ...
    python3 crawl_to_dify.py --file urls.txt
    python3 crawl_to_dify.py --file urls.txt --dry-run

Ejemplo:
    python3 crawl_to_dify.py "https://tradicional.dgadr.gov.pt/pt/cat/carne/carne-de-aves/591-capao-de-freamunde-igp"
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

# ── Config ──────────────────────────────────────────
CRAWL4AI_URL = os.getenv("CRAWL4AI_URL", "http://localhost:11235")
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_TOKEN", "seedy_crawl_2026")

DIFY_URL = os.getenv("DIFY_URL", "http://localhost:3002")
DIFY_EMAIL = os.getenv("DIFY_EMAIL", "david@neofarm.io")
DIFY_PASSWD = os.getenv("DIFY_PASSWD", "NeoFarm2026")
DIFY_KB_ID = os.getenv("DIFY_KB_ID", "880d67ee-3bd3-40ce-a457-ef46a3ad6be6")


def sanitize_filename(name: str) -> str:
    """Limpia nombre de archivo para Dify."""
    name = re.sub(r'[—–]', '-', name)
    name = re.sub(r'[:]', '-', name)
    name = re.sub(r'[<>"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:120]


def crawl_url(url: str) -> dict | None:
    """Crawlea una URL con Crawl4AI, devuelve {title, markdown, url}."""
    print(f"  🕷️  Crawleando: {url[:80]}...")
    try:
        r = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CRAWL4AI_TOKEN}",
            },
            json={"urls": [url], "priority": 10},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        result = data["results"][0]

        if not result.get("success"):
            err = result.get("error_message", "unknown error")
            print(f"  ❌ Crawl falló: {err[:100]}")
            return None

        # Extract markdown (v0.5 returns dict, older returns str)
        md = result.get("markdown", "")
        if isinstance(md, dict):
            md = md.get("raw_markdown", "") or md.get("fit_markdown", "")

        if not md or len(md.strip()) < 100:
            print(f"  ⚠️  Contenido muy corto ({len(md)} chars), saltando")
            return None

        # Extract title from metadata or URL
        meta = result.get("metadata", {}) or {}
        title = ""
        if isinstance(meta, dict):
            title = meta.get("title", "") or meta.get("og:title", "")
        if not title:
            parsed = urlparse(url)
            title = parsed.path.split("/")[-1] or parsed.netloc

        print(f"  ✅ Crawled: {len(md)} chars — {title[:60]}")
        return {"title": title, "markdown": md, "url": url}

    except Exception as e:
        print(f"  ❌ Error crawleando {url[:50]}: {e}")
        return None


def dify_login() -> tuple[requests.Session, dict]:
    """Login a Dify, devuelve (session, headers)."""
    session = requests.Session()
    passwd_b64 = base64.b64encode(DIFY_PASSWD.encode()).decode()
    r = session.post(
        f"{DIFY_URL}/console/api/login",
        json={"email": DIFY_EMAIL, "password": passwd_b64},
    )
    r.raise_for_status()
    cookies = dict(session.cookies)
    headers = {
        "Authorization": f"Bearer {cookies['access_token']}",
        "X-CSRF-Token": cookies["csrf_token"],
    }
    return session, headers


def upload_to_dify(session: requests.Session, headers: dict, title: str, markdown: str, source_url: str) -> bool:
    """Sube un documento markdown a la KB de Dify."""
    filename = sanitize_filename(title) + ".md"

    # Prepend source URL as header
    content = f"# {title}\n\n> Fuente: {source_url}\n> Crawleado: {time.strftime('%Y-%m-%d %H:%M')}\n\n{markdown}"

    # Step 1: Upload file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp_path = f.name

    try:
        upload_headers = {k: v for k, v in headers.items()}
        # Don't set Content-Type for multipart
        with open(tmp_path, "rb") as fh:
            r1 = session.post(
                f"{DIFY_URL}/console/api/files/upload",
                headers=upload_headers,
                files={"file": (filename, fh, "text/markdown")},
                data={"source": "datasets"},
            )

        if r1.status_code != 201 and r1.status_code != 200:
            print(f"  ❌ Upload file falló: {r1.status_code} → {r1.text[:200]}")
            return False

        file_id = r1.json().get("id")
        if not file_id:
            print(f"  ❌ No file_id en respuesta: {r1.text[:200]}")
            return False

        # Step 2: Create document in KB
        doc_payload = {
            "data_source": {
                "type": "upload_file",
                "info_list": {
                    "data_source_type": "upload_file",
                    "file_info_list": {
                        "file_ids": [file_id],
                    },
                },
            },
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "automatic",
            },
        }

        create_headers = {k: v for k, v in headers.items()}
        create_headers["Content-Type"] = "application/json"

        r2 = session.post(
            f"{DIFY_URL}/console/api/datasets/{DIFY_KB_ID}/documents",
            headers=create_headers,
            json=doc_payload,
        )

        if r2.status_code in (200, 201):
            print(f"  📄 Subido a Dify KB: {filename}")
            return True
        else:
            print(f"  ❌ Create doc falló: {r2.status_code} → {r2.text[:200]}")
            return False

    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Crawl URLs → Dify KB")
    parser.add_argument("urls", nargs="*", help="URLs a crawlear")
    parser.add_argument("--file", "-f", help="Archivo con URLs (una por línea)")
    parser.add_argument("--dry-run", action="store_true", help="Solo crawlear, no subir")
    args = parser.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file) as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if not urls:
        print("❌ No se proporcionaron URLs")
        print("Uso: python3 crawl_to_dify.py URL1 URL2 ...")
        print("     python3 crawl_to_dify.py --file urls.txt")
        sys.exit(1)

    print(f"🌾 Seedy Crawl→Dify — {len(urls)} URLs")
    print("=" * 60)

    # Crawl all URLs
    crawled = []
    for url in urls:
        result = crawl_url(url)
        if result:
            crawled.append(result)

    print(f"\n📊 Crawleados: {len(crawled)}/{len(urls)}")

    if args.dry_run:
        print("\n[DRY RUN] No se suben a Dify")
        for c in crawled:
            print(f"  → {c['title'][:60]} ({len(c['markdown'])} chars)")
        return

    if not crawled:
        print("No hay contenido para subir")
        return

    # Upload to Dify
    print(f"\n📤 Subiendo a Dify KB...")
    session, headers = dify_login()

    uploaded = 0
    failed = 0
    for item in crawled:
        ok = upload_to_dify(session, headers, item["title"], item["markdown"], item["url"])
        if ok:
            uploaded += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"✅ Completado: {uploaded} subidos, {failed} fallidos de {len(urls)} URLs")


if __name__ == "__main__":
    main()
