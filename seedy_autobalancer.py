#!/usr/bin/env python3
"""
Seedy — Auto-Balancer: busca, descarga e ingesta conocimiento automáticamente.

Cada 24h:
1. Analiza el balance de colecciones en Qdrant
2. Identifica las colecciones con menos información
3. Busca artículos relevantes en fuentes académicas y agritech
4. Descarga, convierte y organiza el contenido
5. Ingesta en Qdrant con embeddings + BM25

Fuentes:
- Google Scholar (artículos académicos)
- PubMed (nutrición animal, genética)
- MAPA/REGA portales abiertos
- Portales agritech (Agroptima, iAgri, INIA, IRTA, etc.)
- Wikipedia ES/EN para temas genéricos

Uso:
    python seedy_autobalancer.py                 # Ejecutar una vez
    python seedy_autobalancer.py --daemon        # Ejecutar cada 24h
    python seedy_autobalancer.py --dry-run       # Solo mostrar plan
    python seedy_autobalancer.py --report        # Solo informe de balance
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

import requests
from bs4 import BeautifulSoup

# ── Config ──
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")
EMBED_MODEL = "mxbai-embed-large"
EMBED_MAX_CHARS = 800
CHUNK_SIZE = 600
DATA_DIR = Path("/home/davidia/Documentos/Seedy/autobalancer_data")
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "autobalancer.log"
NAS_PATH = Path("/run/user/1000/gvfs/smb-share:server=192.168.30.100,share=datos/Seedy_AutoIngest")

# Artículos máximos por colección por ciclo
MAX_ARTICLES_PER_CYCLE = 10
# Mínimo de puntos target por colección (para equilibrar)
MIN_POINTS_TARGET = 5000

# ── Colecciones y sus topics de búsqueda ──
COLLECTION_TOPICS = {
    "geotwin": {
        "description": "Digital twins geoespaciales, GIS, modelado 3D ganadero",
        "queries_es": [
            "gemelo digital ganadería",
            "GIS explotación ganadera",
            "modelado 3D granja precisión",
            "digital twin livestock farm",
            "teledetección pastos ganadería",
            "SIGPAC ganadería",
        ],
        "queries_en": [
            "digital twin livestock farm precision",
            "GIS precision livestock farming",
            "3D modeling poultry house",
            "remote sensing grazing pasture",
            "geospatial analytics animal farming",
        ],
    },
    "digital_twins": {
        "description": "Gemelos digitales, simulación, modelado de procesos ganaderos",
        "queries_es": [
            "gemelo digital porcino simulación",
            "modelado computacional producción avícola",
            "simulación biológica crecimiento animal",
            "digital twin cerdo engorde",
            "modelo predictivo producción ganadera",
        ],
        "queries_en": [
            "digital twin pig growth simulation",
            "computational modeling poultry production",
            "agent-based model livestock farm",
            "predictive analytics animal production",
            "simulation swine production system",
        ],
    },
    "fresh_web": {
        "description": "Noticias y tendencias recientes en ganadería de precisión",
        "queries_es": [
            "ganadería precisión España 2025 2026",
            "innovación avícola tecnología",
            "IoT ganadería inteligente noticias",
            "startups agritech ganadería España",
            "inteligencia artificial producción animal",
        ],
        "queries_en": [
            "precision livestock farming trends 2025 2026",
            "agritech poultry innovation",
            "smart farming IoT cattle pigs",
            "AI animal production latest research",
            "livestock technology startups Europe",
        ],
    },
    "iot_hardware": {
        "description": "Sensores IoT, hardware, PLF (Precision Livestock Farming)",
        "queries_es": [
            "sensores IoT ganadería porcina",
            "monitorización ambiental granja avícola",
            "RFID identificación animal electrónica",
            "sensores temperatura humedad granja",
            "cámara termográfica bienestar animal",
        ],
        "queries_en": [
            "IoT sensors pig farming monitoring",
            "precision livestock farming hardware",
            "RFID animal identification systems",
            "environmental sensors poultry house",
            "wearable sensors cattle health monitoring",
            "thermal imaging animal welfare",
        ],
    },
    "nutricion": {
        "description": "Nutrición animal, formulación piensos, metabolismo",
        "queries_es": [
            "formulación piensos avícolas optimización",
            "nutrición porcina aminoácidos digestibles",
            "aditivos alimentarios ganadería alternativas antibióticos",
            "metabolismo energético rumiantes",
            "nutrición capón gallo alimentación",
        ],
        "queries_en": [
            "poultry feed formulation optimization",
            "swine nutrition digestible amino acids",
            "feed additives livestock antibiotic alternatives",
            "capon feeding program nutrition",
            "precision feeding dairy cattle",
        ],
    },
    "normativa": {
        "description": "Normativa ganadera española y europea",
        "queries_es": [
            "normativa bienestar animal España 2025",
            "ECOGAN requisitos explotación ganadera",
            "Real Decreto ganadería avícola",
            "PAC 2024 2025 ganadería condicionalidad",
            "SIGE sistema información ganadero",
            "trazabilidad ganadera normativa europea",
        ],
        "queries_en": [
            "EU animal welfare legislation livestock 2025",
            "European Commission farm animal regulation",
            "poultry welfare directive EU",
        ],
    },
    "genetica": {
        "description": "Genética animal, selección, razas, genómica",
        "queries_es": [
            "selección genómica porcino España",
            "razas autóctonas avícolas España conservación",
            "mejora genética avicultura",
            "cruzamientos capón razas pesadas",
            "genómica ganado vacuno autóctono",
        ],
        "queries_en": [
            "genomic selection livestock poultry",
            "heritage chicken breeds genetic diversity",
            "GWAS poultry growth traits",
            "capon breed genetics Bresse Sulmtaler",
            "swine genomics breeding programs",
        ],
    },
}

# ── Fuentes académicas / institucionales ──
ACADEMIC_SOURCES = [
    # Google Scholar proxy via SearXNG
    {"engine": "searxng", "category": "science"},
    # PubMed
    {"engine": "pubmed", "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"},
    # INIA/IRTA (via web)
    {"engine": "web", "domains": [
        "inia.es", "irta.cat", "mapa.gob.es",
        "sciencedirect.com", "mdpi.com", "frontiersin.org",
    ]},
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8") if LOG_FILE.parent.exists() else logging.StreamHandler(),
    ]
)
logger = logging.getLogger("autobalancer")

_STOPWORDS = frozenset(
    "de la el en los las un una del al con por para es que se su no lo más"
    " como pero ya o si le este esta ese esa estos estas esos esas the a an"
    " and or but in on at to for of is it that this with from by as be was"
    " are have has had been will would could should may can do did not"
    " otro otra otros otras muy también así donde cuando todo toda todos todas"
    .split()
)


# ──────── UTILIDADES ────────

def get_collection_stats() -> dict[str, int]:
    """Retorna {collection_name: points_count}."""
    resp = requests.get(f"{QDRANT_URL}/collections", timeout=10)
    resp.raise_for_status()
    stats = {}
    for c in resp.json()["result"]["collections"]:
        name = c["name"]
        info = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=10).json()
        stats[name] = info["result"]["points_count"]
    return stats


def compute_priority(stats: dict[str, int]) -> list[tuple[str, float, int]]:
    """Calcula prioridad de cada colección. Mayor prioridad = más necesita datos."""
    total = sum(stats.values())
    avg = total / len(stats) if stats else 1
    priorities = []
    for name, pts in stats.items():
        if name not in COLLECTION_TOPICS:
            continue
        # Prioridad inversamente proporcional al tamaño
        deficit = max(0, MIN_POINTS_TARGET - pts)
        ratio = avg / max(pts, 1)
        priority = deficit * 0.001 + ratio
        priorities.append((name, priority, pts))
    return sorted(priorities, key=lambda x: -x[1])


# Keywords que deben aparecer en título o snippet para considerar relevante
DOMAIN_KEYWORDS = {
    "ganad", "pecuar", "avícol", "avicul", "porcin", "poult", "swine", "pig", "cattle",
    "livestock", "farm", "granja", "animal", "breed", "raza", "genét", "genom",
    "nutri", "pienso", "feed", "aliment", "iot", "sensor", "smart farm",
    "precis", "digital twin", "gemelo digital", "gis", "remote sens", "teledet",
    "normativ", "regulat", "welfare", "bienestar", "sanidad", "veterinar",
    "agri", "agro", "rumiante", "ruminant", "dairy", "leche", "carne", "meat",
    "capón", "capon", "pollo", "chicken", "hen", "gallina", "huevo", "egg",
    "cerdo", "ovino", "sheep", "cabra", "goat", "vacuno", "bovine",
    "pastur", "pasto", "forag", "forraje", "silage", "ensilado",
    "antibiot", "probiot", "aditiv", "additive", "amino", "protein",
    "fertili", "crop", "cultivo", "plaga", "pest", "herbicid", "insecticid",
    "sigpac", "pac ", "mapa.gob", "ecogan", "rega ", "trace", "trazab",
}


def is_relevant(title: str, snippet: str, collection: str) -> bool:
    """Check if a search result is relevant to the agricultural domain."""
    text_lower = f"{title} {snippet}".lower()
    # Must match at least one domain keyword
    return any(kw in text_lower for kw in DOMAIN_KEYWORDS)


def search_searxng(query: str, max_results: int = 5) -> list[dict]:
    """Busca artículos via SearXNG."""
    try:
        params = {
            "q": query,
            "format": "json",
            "categories": "science,general",
            "language": "es" if any(c in query for c in "áéíóúñ") else "en",
            "pageno": 1,
            "engines": "pubmed,semantic scholar,openalex,google scholar,wikipedia,brave,duckduckgo,google",
        }
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "content": r.get("content", "")} for r in results[:max_results]]
    except Exception as e:
        logger.warning(f"SearXNG search failed for '{query}': {e}")
        return []


# ── Wikipedia via MediaWiki API ──
WIKIPEDIA_TOPICS = {
    "geotwin": ["Precision agriculture", "Geographic information system",
                "Remote sensing in agriculture", "Digital twin"],
    "digital_twins": ["Digital twin", "Precision livestock farming",
                      "Livestock monitoring", "Computational biology"],
    "fresh_web": ["Smart farming", "Agricultural technology",
                  "Internet of things in agriculture"],
    "iot_hardware": ["Precision livestock farming", "RFID",
                     "Wireless sensor network", "Environmental monitoring"],
    "nutricion": ["Animal nutrition", "Feed conversion ratio",
                  "Poultry feed", "Swine nutrition"],
    "normativa": ["Animal welfare", "Common Agricultural Policy",
                  "European Union agricultural policy"],
    "genetica": ["Animal breeding", "Quantitative genetics",
                 "Genomic selection", "Poultry genetics"],
}


def search_wikipedia(query: str, lang: str = "en", max_results: int = 3) -> list[dict]:
    """Search Wikipedia via MediaWiki API and return article text excerpts."""
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    headers = {"User-Agent": "SeedyBot/1.0 (agricultural research bot)"}
    results = []
    try:
        # Search for pages
        resp = requests.get(api_url, params={
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": max_results, "format": "json",
        }, headers=headers, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])

        for hit in hits:
            page_id = hit["pageid"]
            title = hit["title"]
            # Get full text extract
            resp2 = requests.get(api_url, params={
                "action": "query", "pageids": page_id,
                "prop": "extracts", "explaintext": True,
                "exsectionformat": "plain", "format": "json",
            }, headers=headers, timeout=15)
            resp2.raise_for_status()
            pages = resp2.json().get("query", {}).get("pages", {})
            text = pages.get(str(page_id), {}).get("extract", "")
            if text and len(text) > 300:
                url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                results.append({"title": title, "url": url, "text": text})
    except Exception as e:
        logger.warning(f"Wikipedia API error for '{query}' ({lang}): {e}")
    return results


def fetch_article(url: str, session: requests.Session | None = None) -> tuple[str, str]:
    """Descarga y extrae texto de una URL. Returns (title, text)."""
    s = session or requests.Session()
    s.headers.setdefault("User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) SeedyBot/1.0 (agricultural research)")
    try:
        resp = s.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return "", ""

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove script, style, nav, footer
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = ""
    if soup.title:
        title = ' '.join(soup.title.get_text(strip=True).split())

    # Try common article selectors
    article_text = ""
    for selector in ["article", ".entry-content", ".the-content",
                     ".article-body", "main", "#content", ".post-content"]:
        elem = soup.select_one(selector)
        if elem and len(elem.get_text(strip=True)) > 200:
            article_text = elem.get_text(separator="\n", strip=True)
            break

    if not article_text:
        # Fallback: largest text block
        divs = soup.find_all("div")
        best = max(divs, key=lambda d: len(d.get_text(strip=True)),
                   default=None)
        if best:
            article_text = best.get_text(separator="\n", strip=True)

    return title, article_text


def chunk_text(text: str, title: str) -> list[dict]:
    """Split text into semantic chunks."""
    sections = re.split(r'\n(?=#{1,4}\s)', text)
    chunks = []
    for section in sections:
        paragraphs = re.split(r'\n\n+', section.strip())
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) < CHUNK_SIZE:
                current = (current + "\n\n" + para).strip()
            else:
                if current and len(current) > 50:
                    chunks.append(current)
                if len(para) > CHUNK_SIZE * 2:
                    words = para.split()
                    sub = ""
                    for w in words:
                        if len(sub) + len(w) > CHUNK_SIZE:
                            if sub:
                                chunks.append(sub.strip())
                            sub = w
                        else:
                            sub = sub + " " + w if sub else w
                    if sub and len(sub) > 50:
                        chunks.append(sub.strip())
                    current = ""
                else:
                    current = para
        if current and len(current) > 50:
            chunks.append(current)

    return [{"text": c, "title": title, "chunk_index": i}
            for i, c in enumerate(chunks)]


def embed_text(text: str) -> list[float]:
    """Get embedding from Ollama."""
    clean = re.sub(r'\s{2,}', ' ', text).strip()[:EMBED_MAX_CHARS]
    resp = requests.post(f"{OLLAMA_URL}/api/embeddings",
                         json={"model": EMBED_MODEL, "prompt": clean}, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]


def compute_sparse(text: str) -> dict:
    """BM25-like sparse vector."""
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    tokens = [t for t in tokens if t not in _STOPWORDS]
    if not tokens:
        return {}
    tf = Counter(tokens)
    indices, values = [], []
    for token, count in sorted(tf.items()):
        idx = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) % (2**31)
        indices.append(idx)
        values.append(float(count))
    return {"indices": indices, "values": values}


def ingest_article(collection: str, title: str, text: str, url: str,
                   lang: str = "es") -> int:
    """Chunk, embed, and upsert an article. Returns number of points inserted."""
    chunks = chunk_text(text, title)
    if not chunks:
        return 0

    points = []
    for chunk in chunks:
        try:
            emb = embed_text(chunk["text"])
        except Exception as e:
            logger.warning(f"  Embed error chunk {chunk['chunk_index']}: {e}")
            continue

        safe_title = re.sub(r'[^\w\s-]', '', title)[:80]
        point_id = str(uuid5(NAMESPACE_URL,
                             f"auto:{collection}:{safe_title}:{chunk['chunk_index']}"))
        vector_data = {"dense": emb}
        sparse = compute_sparse(chunk["text"])
        if sparse:
            vector_data["bm25"] = sparse

        points.append({
            "id": point_id,
            "vector": vector_data,
            "payload": {
                "text": chunk["text"],
                "source_file": f"auto_{safe_title}.md",
                "chunk_index": chunk["chunk_index"],
                "section": "",
                "collection": collection,
                "document_type": "web_article",
                "title": title,
                "language": lang,
                "source_origin": "autobalancer",
                "source_url": url,
                "ingested_at": datetime.utcnow().isoformat(),
            },
        })

    # Upsert in batches
    total = 0
    for b in range(0, len(points), 20):
        batch = points[b:b+20]
        try:
            resp = requests.put(
                f"{QDRANT_URL}/collections/{collection}/points",
                json={"points": batch}, timeout=30
            )
            if resp.status_code in (200, 201):
                total += len(batch)
            else:
                logger.warning(f"  Upsert failed: {resp.status_code}")
        except Exception as e:
            logger.warning(f"  Upsert error: {e}")

    return total


def save_state(state: dict):
    """Persist state to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_state() -> dict:
    """Load persistent state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_run": None, "seen_urls": [], "history": []}


def save_article_md(collection: str, title: str, text: str, url: str):
    """Save article as markdown to NAS for backup."""
    try:
        col_dir = NAS_PATH / collection
        col_dir.mkdir(parents=True, exist_ok=True)
        clean_title = ' '.join(title.split())  # collapse \n \t whitespace
        safe = re.sub(r'[^\w\s\-áéíóúñÁÉÍÓÚÑ]', '', clean_title)[:80].strip()
        md_path = col_dir / f"{safe}.md"
        content = f"# {title}\n\nFuente: {url}\nFecha: {datetime.now().isoformat()}\n\n---\n\n{text}"
        md_path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.warning(f"  Could not save to NAS: {e}")


# ──────── MAIN ────────

def run_cycle(dry_run: bool = False):
    """Execute one balance+ingest cycle."""
    logger.info("=" * 60)
    logger.info(f"🔄 Ciclo AutoBalancer — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Analyze balance
    stats = get_collection_stats()
    priorities = compute_priority(stats)
    total = sum(stats.values())

    logger.info(f"\n📊 Estado actual ({total} puntos totales):")
    for name, prio, pts in priorities:
        bar = "█" * max(1, int(pts / total * 40)) if total else ""
        logger.info(f"  {name:20s} {pts:>6d} pts  prio={prio:.2f}  {bar}")

    state = load_state()
    seen_urls = set(state.get("seen_urls", []))

    if dry_run:
        logger.info("\n🏁 Dry-run — solo se muestra el plan:")
        for name, prio, pts in priorities[:4]:
            topics = COLLECTION_TOPICS[name]
            logger.info(f"\n  Colección: {name} (prio={prio:.2f}, {pts} pts)")
            logger.info(f"    Queries: {topics['queries_es'][:3]}")
        return

    # 2. Process top-priority collections
    cycle_total = 0
    cycle_articles = 0
    collections_processed = []

    for name, prio, pts in priorities:
        if prio < 0.3:
            logger.info(f"\n  ⏭ {name}: ya equilibrada (prio={prio:.2f})")
            continue

        topics = COLLECTION_TOPICS[name]
        all_queries = topics["queries_es"] + topics["queries_en"]
        logger.info(f"\n── Colección: {name} (prio={prio:.2f}, {pts} pts) ──")

        col_articles = 0
        col_points = 0

        for query in all_queries:
            if col_articles >= MAX_ARTICLES_PER_CYCLE:
                break

            logger.info(f"  🔍 Buscando: {query}")
            results = search_searxng(query, max_results=5)

            for result in results:
                if col_articles >= MAX_ARTICLES_PER_CYCLE:
                    break

                url = result.get("url", "")
                if not url or url in seen_urls:
                    continue

                # Skip non-article URLs
                if any(x in url for x in [".pdf", "youtube.com", "twitter.com",
                                          "facebook.com", "instagram.com"]):
                    continue

                # Relevance filter — skip results unrelated to agritech/livestock
                if not is_relevant(result.get("title", ""), result.get("content", ""), name):
                    logger.info(f"    ⏭ Irrelevante: {result['title'][:60]}")
                    seen_urls.add(url)
                    continue

                logger.info(f"    📥 {result['title'][:70]}...")
                title, text = fetch_article(url)

                if not text or len(text) < 300:
                    logger.info(f"    ⏭ Sin contenido útil")
                    seen_urls.add(url)
                    continue

                # Detect language
                lang = "es" if sum(1 for c in text if c in "áéíóúñ") > len(text) * 0.005 else "en"

                # Ingest
                n_pts = ingest_article(name, title or result["title"], text, url, lang)
                if n_pts > 0:
                    col_articles += 1
                    col_points += n_pts
                    cycle_total += n_pts
                    cycle_articles += 1
                    logger.info(f"    ✅ {n_pts} chunks insertados")

                    # Save backup to NAS
                    save_article_md(name, title or result["title"], text, url)

                seen_urls.add(url)

                # Rate limit
                time.sleep(2)

        if col_points:
            collections_processed.append(f"{name}: +{col_points} pts ({col_articles} arts)")

        # ── Wikipedia supplement for this collection ──
        wiki_topics = WIKIPEDIA_TOPICS.get(name, [])
        for topic in wiki_topics:
            if col_articles >= MAX_ARTICLES_PER_CYCLE:
                break
            for lang in ["en", "es"]:
                wiki_results = search_wikipedia(topic, lang=lang, max_results=1)
                for wr in wiki_results:
                    if wr["url"] in seen_urls:
                        continue
                    if not is_relevant(wr["title"], wr["text"][:500], name):
                        seen_urls.add(wr["url"])
                        continue
                    lang_tag = "es" if lang == "es" else "en"
                    n_pts = ingest_article(name, wr["title"], wr["text"], wr["url"], lang_tag)
                    if n_pts > 0:
                        col_articles += 1
                        col_points += n_pts
                        cycle_total += n_pts
                        cycle_articles += 1
                        logger.info(f"    📚 Wikipedia ({lang}): {wr['title'][:50]} → {n_pts} chunks")
                        save_article_md(name, wr["title"], wr["text"], wr["url"])
                    seen_urls.add(wr["url"])

    # 3. Save state
    state["last_run"] = datetime.utcnow().isoformat()
    state["seen_urls"] = list(seen_urls)[-5000:]  # Keep last 5000
    state["history"].append({
        "date": datetime.utcnow().isoformat(),
        "articles": cycle_articles,
        "points": cycle_total,
        "collections": collections_processed,
    })
    state["history"] = state["history"][-100:]  # Keep last 100 cycles
    save_state(state)

    # 4. Report
    new_stats = get_collection_stats()
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Ciclo completado")
    logger.info(f"   Artículos descargados: {cycle_articles}")
    logger.info(f"   Puntos insertados: {cycle_total}")
    logger.info(f"   Colecciones actualizadas:")
    for name, prio, old_pts in priorities:
        new_pts = new_stats.get(name, old_pts)
        diff = new_pts - old_pts
        if diff > 0:
            logger.info(f"     {name}: {old_pts} → {new_pts} (+{diff})")


def report_only():
    """Just print balance report."""
    stats = get_collection_stats()
    priorities = compute_priority(stats)
    total = sum(stats.values())

    print(f"\n📊 Balance de conocimiento Seedy ({total} puntos)")
    print(f"{'Colección':25s} {'Puntos':>8s} {'%':>6s} {'Prioridad':>10s} {'Estado':>15s}")
    print("-" * 70)
    for name, prio, pts in priorities:
        pct = pts / total * 100 if total else 0
        if prio > 2:
            estado = "⚠️  CRÍTICO"
        elif prio > 1:
            estado = "📉 BAJO"
        elif prio > 0.5:
            estado = "✅ OK"
        else:
            estado = "📊 ALTO"
        print(f"{name:25s} {pts:>8d} {pct:>5.1f}% {prio:>10.2f} {estado:>15s}")
    print("-" * 70)
    print(f"{'TOTAL':25s} {total:>8d}")

    state = load_state()
    if state.get("last_run"):
        print(f"\n⏰ Última ejecución: {state['last_run']}")
        if state.get("history"):
            last = state["history"][-1]
            print(f"   Resultado: {last.get('articles', 0)} artículos, "
                  f"{last.get('points', 0)} puntos")


def main():
    parser = argparse.ArgumentParser(description="Seedy AutoBalancer")
    parser.add_argument("--daemon", action="store_true",
                        help="Ejecutar en bucle cada 24h")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría")
    parser.add_argument("--report", action="store_true",
                        help="Solo informe de balance")
    parser.add_argument("--interval", type=int, default=24,
                        help="Horas entre ciclos (default: 24)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.report:
        report_only()
        return

    if args.daemon:
        logger.info(f"🤖 AutoBalancer daemon started (interval={args.interval}h)")
        while True:
            try:
                run_cycle(dry_run=args.dry_run)
            except Exception as e:
                logger.error(f"Cycle error: {e}", exc_info=True)
            logger.info(f"💤 Durmiendo {args.interval}h hasta el próximo ciclo...")
            time.sleep(args.interval * 3600)
    else:
        run_cycle(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
