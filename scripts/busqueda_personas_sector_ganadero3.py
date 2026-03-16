#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  Seedy — Búsqueda de Personas del Sector Ganadero en España     ║
║  OSINT profesional: nombre, email, teléfono, DNI, documentos    ║
║  oficiales (BOE), webs, RRSS, publicaciones científicas.        ║
╚══════════════════════════════════════════════════════════════════╝

Uso:
    # Por nombre (usar + para separar nombre y apellidos)
    python scripts/busqueda_personas_sector_ganadero.py "Juan+Pérez+García"

    # Por email
    python scripts/busqueda_personas_sector_ganadero.py --email juan.perez@mapa.gob.es

    # Por teléfono
    python scripts/busqueda_personas_sector_ganadero.py --telefono 612345678

    # Por DNI (busca en BOE y documentos oficiales)
    python scripts/busqueda_personas_sector_ganadero.py --dni 12345678A

    # Combinado
    python scripts/busqueda_personas_sector_ganadero.py "María+López+Sánchez" --email mlopez@inia.es

    # Exportar a CSV o JSON
    python scripts/busqueda_personas_sector_ganadero.py "Pedro+Martínez" --export resultados_pedro.csv

    # Solo ciertas fuentes
    python scripts/busqueda_personas_sector_ganadero.py "Ana+Ruiz" --solo-fuentes boe,rrss,scholar

Fuentes:
     1. SearXNG Web general (Google, Bing, DDG, Brave)
     2. BOE — Boletín Oficial del Estado
     3. RRSS — LinkedIn, Twitter/X, Facebook, Instagram, YouTube
     4. ResearchGate, ORCID, Google Scholar
     5. MAPA / INIA / CSIC (webs institucionales ganaderas)
     6. Colegios profesionales (veterinarios, ingenieros agrónomos)
     7. Registros mercantiles y directorios empresariales
     8. Diarios oficiales autonómicos (BOJA, DOCM, DOGC, etc.)
     9. Búsqueda por email (Have I Been Pwned, Gravatar, etc.)
    10. Búsqueda por teléfono (páginas blancas, infobel)
"""

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx

# ── Config ──────────────────────────────────────────────────────────────
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")
TIMEOUT = 25  # seconds per HTTP request
# Google/DDG/Bing/Brave rotos o devuelven ruido CJK — solo estos funcionan
WORKING_ENGINES = "qwant,yahoo,yandex,mojeek"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("person_search")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ── Data model ──────────────────────────────────────────────────────────
@dataclass
class PersonResult:
    title: str
    url: str
    source: str        # e.g. "boe", "linkedin", "google_scholar"
    category: str      # "documento_oficial", "rrss", "academico", "web", "directorio"
    snippet: str = ""
    date: str = ""
    relevance: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        u = re.sub(r"https?://(www\.)?", "", self.url.lower().rstrip("/"))
        return hashlib.md5(u.encode()).hexdigest()


# ── Helpers ─────────────────────────────────────────────────────────────
def _trim(text: str, maxlen: int = 250) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:maxlen] + "…" if len(text) > maxlen else text


# Domains that consistently return irrelevant results for Spanish person search
_BLOCKED_DOMAINS = {
    "baidu.com", "zhidao.baidu.com", "zhihu.com", "tieba.baidu.com",
    "bilibili.com", "douyin.com", "weibo.com", "weixin.qq.com",
    "bankier.pl", "onet.pl", "wp.pl",  # Polish noise
}


def _is_noise_result(url: str, title: str, snippet: str) -> bool:
    """Filter out results clearly unrelated (CJK noise, blocked domains)."""
    # Block known noise domains
    for bd in _BLOCKED_DOMAINS:
        if bd in url.lower():
            return True
    # Block results whose title + snippet is predominantly CJK/non-Latin
    text = f"{title} {snippet}"
    if not text.strip():
        return False
    latin_chars = sum(1 for c in text if c.isascii() or unicodedata.category(c).startswith("L"))
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" or "\uac00" <= c <= "\ud7af")
    if cjk > len(text) * 0.15:
        return True
    return False


def _name_from_plus(name_plus: str) -> dict:
    """Parse 'Juan+Pérez+García' → parts and search-ready forms."""
    parts = [p.strip() for p in name_plus.replace("+", " ").split() if p.strip()]
    full = " ".join(parts)
    quoted = f'"{full}"'
    return {
        "parts": parts,
        "full": full,
        "quoted": quoted,
        "first": parts[0] if parts else "",
        "last": " ".join(parts[1:]) if len(parts) > 1 else "",
        "slug": "-".join(p.lower() for p in parts),
        "dotted": ".".join(p.lower() for p in parts),
    }


async def _searxng(
    client: httpx.AsyncClient,
    query: str,
    pages: int = 10,
    max_results: int = 30,
    lang: str = "es",
    category: str = "general",
    engines: str = "",
) -> list[dict]:
    """Generic SearXNG search, returns raw results."""
    results = []
    for page in range(1, pages + 1):
        try:
            params = {
                "q": query, "format": "json", "pageno": page,
                "language": lang, "categories": category,
                "engines": engines or WORKING_ENGINES,
            }
            r = await client.get(
                f"{SEARXNG_URL}/search",
                params=params,
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            results.extend(data.get("results", []))
            if len(results) >= max_results:
                break
        except Exception as e:
            log.debug(f"  ⚠ SearXNG error: {e}")
            break
    # Pre-filter noise (CJK, blocked domains)
    results = [
        r for r in results
        if not _is_noise_result(r.get("url", ""), r.get("title", ""), r.get("content", ""))
    ]
    return results[:max_results]


# ══════════════════════════════════════════════════════════════════════
#  SEARCH PROVIDERS
# ══════════════════════════════════════════════════════════════════════

# ── 1. Web general ──────────────────────────────────────────────────
async def search_web_general(
    client: httpx.AsyncClient, name: dict, pages: int, max_r: int,
) -> list[PersonResult]:
    """Búsqueda web general del nombre."""
    sector_query = f'{name["quoted"]} ganadería OR veterinario OR agropecuario OR MAPA OR INIA'
    raw = await _searxng(client, sector_query, pages, max_r)
    return [
        PersonResult(
            title=_trim(r.get("title", ""), 120),
            url=r.get("url", ""),
            source=r.get("engine", "web"),
            category="web",
            snippet=_trim(r.get("content", "")),
            date=r.get("publishedDate", ""),
        )
        for r in raw
    ]


# ── 2. BOE & Diarios oficiales ─────────────────────────────────────
async def search_boe(
    client: httpx.AsyncClient, name: dict, dni: str,
    pages: int, max_r: int,
) -> list[PersonResult]:
    """Busca en BOE y diarios oficiales autonómicos."""
    results: list[PersonResult] = []

    # 2a. BOE API directa (boe.es tiene buscador con JSON)
    boe_queries = []
    if dni:
        boe_queries.append(f'"{dni}" site:boe.es')
    boe_queries.append(f'{name["quoted"]} site:boe.es')

    for q in boe_queries:
        raw = await _searxng(client, q, pages, max_r)
        for r in raw:
            results.append(PersonResult(
                title=_trim(r.get("title", ""), 150),
                url=r.get("url", ""),
                source="boe",
                category="documento_oficial",
                snippet=_trim(r.get("content", "")),
                date=r.get("publishedDate", ""),
            ))

    # 2b. Diarios autonómicos
    autonomic_sites = [
        ("BOJA", "juntadeandalucia.es/eboja"),
        ("DOCM", "docm.jccm.es"),
        ("DOG", "xunta.gal/dog"),
        ("DOGC", "dogc.gencat.cat"),
        ("DOGV", "dogv.gva.es"),
        ("BOPV", "euskadi.eus/bopv"),
        ("BOA", "boa.aragon.es"),
        ("BOCM", "bocm.es"),
        ("BORM", "borm.es"),
        ("BON", "bon.navarra.es"),
        ("BOR", "larioja.org/bor"),
        ("BOCYL", "bocyl.jcyl.es"),
        ("DOE", "doe.juntaex.es"),
        ("BOIB", "caib.es/boib"),
        ("BOC", "boc.cantabria.es"),
        ("BOPA", "asturias.es/bopa"),
    ]
    for diario_name, site in autonomic_sites[:10]:  # Top 10 to avoid too many queries
        q = f'{name["quoted"]} site:{site}'
        raw = await _searxng(client, q, 1, 5)
        for r in raw:
            results.append(PersonResult(
                title=_trim(r.get("title", ""), 150),
                url=r.get("url", ""),
                source=diario_name.lower(),
                category="documento_oficial",
                snippet=_trim(r.get("content", "")),
                date=r.get("publishedDate", ""),
            ))

    return results[:max_r]


# ── 3. RRSS ─────────────────────────────────────────────────────────
async def search_rrss(
    client: httpx.AsyncClient, name: dict, email: str,
    pages: int, max_r: int,
) -> list[PersonResult]:
    """Busca perfiles en redes sociales."""
    results: list[PersonResult] = []

    social_sites = {
        "linkedin": ("LinkedIn", "linkedin.com/in/"),
        "twitter": ("Twitter/X", "twitter.com OR x.com"),
        "facebook": ("Facebook", "facebook.com"),
        "instagram": ("Instagram", "instagram.com"),
        "youtube": ("YouTube", "youtube.com"),
        "tiktok": ("TikTok", "tiktok.com"),
    }

    for platform, (label, site_filter) in social_sites.items():
        q = f'{name["quoted"]} site:{site_filter}'
        raw = await _searxng(client, q, 1, 5)
        for r in raw:
            url = r.get("url", "")
            # Verify it's actually a profile link
            results.append(PersonResult(
                title=f"[{label}] {_trim(r.get('title', ''), 100)}",
                url=url,
                source=platform,
                category="rrss",
                snippet=_trim(r.get("content", "")),
            ))

    # Note: SearXNG "social media" category returns noisy Mastodon results,
    # so we rely on site-specific searches above instead.

    # Search by email on social if provided
    if email:
        q_email = f'"{email}" site:linkedin.com OR site:twitter.com OR site:researchgate.net OR site:facebook.com OR site:instagram.com'
        raw_email = await _searxng(client, q_email, 1, 5)
        for r in raw_email:
            results.append(PersonResult(
                title=_trim(r.get("title", ""), 120),
                url=r.get("url", ""),
                source="email_social",
                category="rrss",
                snippet=_trim(r.get("content", "")),
            ))

    return results[:max_r]


# ── 4. Académico / Investigador ─────────────────────────────────────
async def search_academico(
    client: httpx.AsyncClient, name: dict, email: str,
    pages: int, max_r: int,
) -> list[PersonResult]:
    """Google Scholar, ResearchGate, ORCID, Dialnet, CSIC."""
    results: list[PersonResult] = []

    # 4a. Google Scholar via SearXNG (author-specific query)
    scholar_queries = [
        f'author:{name["quoted"]}',
        f'{name["quoted"]} site:scholar.google.com',
        f'{name["quoted"]} site:dialnet.unirioja.es OR site:researchgate.net',
    ]
    for sq in scholar_queries:
        raw = await _searxng(client, sq, 1, max_r // 3 + 1, category="science")
        for r in raw:
            results.append(PersonResult(
                title=_trim(r.get("title", ""), 150),
                url=r.get("url", ""),
                source=r.get("engine", "scholar"),
                category="academico",
                snippet=_trim(r.get("content", "")),
                date=r.get("publishedDate", ""),
            ))

    # 4b. ResearchGate profile
    q_rg = f'{name["quoted"]} site:researchgate.net'
    raw_rg = await _searxng(client, q_rg, 1, 5)
    for r in raw_rg:
        results.append(PersonResult(
            title=f"[ResearchGate] {_trim(r.get('title', ''), 100)}",
            url=r.get("url", ""),
            source="researchgate",
            category="academico",
            snippet=_trim(r.get("content", "")),
        ))

    # 4c. ORCID API (free, no key required)
    try:
        orcid_params = {"q": name["full"], "rows": 5}
        r = await client.get(
            "https://pub.orcid.org/v3.0/search/",
            params=orcid_params,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            for entry in data.get("result", []):
                orcid_id = entry.get("orcid-identifier", {}).get("path", "")
                if orcid_id:
                    results.append(PersonResult(
                        title=f"[ORCID] {orcid_id}",
                        url=f"https://orcid.org/{orcid_id}",
                        source="orcid",
                        category="academico",
                        snippet=f"Perfil ORCID encontrado para búsqueda: {name['full']}",
                        extra={"orcid_id": orcid_id},
                    ))
    except Exception as e:
        log.debug(f"  ⚠ ORCID: {e}")

    # 4d. Dialnet (repositorio académico español)
    q_dialnet = f'{name["quoted"]} site:dialnet.unirioja.es'
    raw_dial = await _searxng(client, q_dialnet, 1, 5)
    for r in raw_dial:
        results.append(PersonResult(
            title=f"[Dialnet] {_trim(r.get('title', ''), 100)}",
            url=r.get("url", ""),
            source="dialnet",
            category="academico",
            snippet=_trim(r.get("content", "")),
        ))

    # 4e. CSIC Digital
    q_csic = f'{name["quoted"]} site:digital.csic.es'
    raw_csic = await _searxng(client, q_csic, 1, 5)
    for r in raw_csic:
        results.append(PersonResult(
            title=f"[CSIC] {_trim(r.get('title', ''), 100)}",
            url=r.get("url", ""),
            source="csic",
            category="academico",
            snippet=_trim(r.get("content", "")),
        ))

    # 4f. OpenAlex author search
    try:
        r = await client.get(
            "https://api.openalex.org/authors",
            params={
                "search": name["full"],
                "per_page": 5,
                "mailto": "mkddg@hotmail.com",
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            for author in data.get("results", []):
                display = author.get("display_name", "")
                oa_id = author.get("id", "").split("/")[-1]
                works = author.get("works_count", 0)
                cited = author.get("cited_by_count", 0)
                topics = ", ".join(
                    t.get("display_name", "")
                    for t in (author.get("topics", []) or [])[:5]
                )
                results.append(PersonResult(
                    title=f"[OpenAlex] {display}",
                    url=f"https://openalex.org/authors/{oa_id}",
                    source="openalex",
                    category="academico",
                    snippet=f"{works} publicaciones, {cited} citas. Temas: {topics[:150]}",
                    extra={
                        "works_count": works,
                        "cited_by_count": cited,
                        "topics": topics,
                    },
                ))
    except Exception as e:
        log.debug(f"  ⚠ OpenAlex authors: {e}")

    return results[:max_r]


# ── 5. Institucional ganadero ───────────────────────────────────────
async def search_institucional(
    client: httpx.AsyncClient, name: dict,
    pages: int, max_r: int,
) -> list[PersonResult]:
    """MAPA, INIA, Colegios Veterinarios, asociaciones ganaderas."""
    results: list[PersonResult] = []

    sites = {
        "MAPA": "mapa.gob.es",
        "INIA/CSIC": "inia.csic.es",
        "COAG": "coag.org",
        "ASAJA": "asaja.com",
        "UPA": "upa.es",
        "Interovic": "interovic.es",
        "ANPROGAPOR": "anprogapor.es",
        "ASEPRHU": "aseprhu.es",
        "INTERPORC": "interporc.com",
        "Col.Veterinarios": "colvet.es OR consejogeneralcolegiosveterinarios.es",
        "FEAGAS": "feagas.com",
        "InfoCarne": "infocarne.com",
    }

    for label, site in sites.items():
        q = f'{name["quoted"]} site:{site}'
        raw = await _searxng(client, q, 1, 3)
        for r in raw:
            results.append(PersonResult(
                title=f"[{label}] {_trim(r.get('title', ''), 100)}",
                url=r.get("url", ""),
                source=label.lower().replace(" ", "_"),
                category="institucional",
                snippet=_trim(r.get("content", "")),
            ))

    return results[:max_r]


# ── 6. Registros / Directorios empresariales ────────────────────────
async def search_directorios(
    client: httpx.AsyncClient, name: dict, dni: str,
    pages: int, max_r: int,
) -> list[PersonResult]:
    """Registro Mercantil, Infoempresa, eInforma, Axesor."""
    results: list[PersonResult] = []

    dir_sites = {
        "Infoempresa": "infoempresa.com",
        "eInforma": "einforma.com",
        "Axesor": "axesor.es",
        "Empresia": "empresia.es",
        "LibreBOR": "librebor.me",
    }

    for label, site in dir_sites.items():
        q = f'{name["quoted"]} site:{site}'
        raw = await _searxng(client, q, 1, 3)
        for r in raw:
            results.append(PersonResult(
                title=f"[{label}] {_trim(r.get('title', ''), 100)}",
                url=r.get("url", ""),
                source=label.lower(),
                category="directorio",
                snippet=_trim(r.get("content", "")),
            ))

    # DNI search in official registries
    if dni:
        q_dni = f'"{dni}" registro mercantil OR administrador OR apoderado'
        raw_dni = await _searxng(client, q_dni, 1, 5)
        for r in raw_dni:
            results.append(PersonResult(
                title=_trim(r.get("title", ""), 120),
                url=r.get("url", ""),
                source="registro_dni",
                category="directorio",
                snippet=_trim(r.get("content", "")),
            ))

    return results[:max_r]


# ── 7. Búsqueda por email ──────────────────────────────────────────
async def search_by_email(
    client: httpx.AsyncClient, email: str, max_r: int,
) -> list[PersonResult]:
    """Busca presencia online de un email."""
    if not email:
        return []
    results: list[PersonResult] = []

    # 7a. Búsqueda directa del email
    q = f'"{email}"'
    raw = await _searxng(client, q, 2, max_r)
    for r in raw:
        results.append(PersonResult(
            title=_trim(r.get("title", ""), 120),
            url=r.get("url", ""),
            source="email_web",
            category="email",
            snippet=_trim(r.get("content", "")),
        ))

    # 7b. Gravatar (avatar público asociado al email)
    try:
        email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
        grav_url = f"https://www.gravatar.com/{email_hash}.json"
        r = await client.get(grav_url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for entry in data.get("entry", []):
                display = entry.get("displayName", "")
                about = entry.get("aboutMe", "")
                urls = [u.get("value", "") for u in entry.get("urls", [])]
                results.append(PersonResult(
                    title=f"[Gravatar] {display}",
                    url=f"https://gravatar.com/{email_hash}",
                    source="gravatar",
                    category="email",
                    snippet=f"{about}. Links: {', '.join(urls[:3])}",
                    extra={"gravatar_urls": urls},
                ))
    except Exception:
        pass

    # 7c. ORCID by email (if institutional)
    if any(email.endswith(d) for d in [".es", ".edu", ".org", ".gob.es", ".csic.es"]):
        try:
            r = await client.get(
                "https://pub.orcid.org/v3.0/search/",
                params={"q": f"email:{email}", "rows": 3},
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                data = r.json()
                for entry in data.get("result", []):
                    orcid_id = entry.get("orcid-identifier", {}).get("path", "")
                    if orcid_id:
                        results.append(PersonResult(
                            title=f"[ORCID via email] {orcid_id}",
                            url=f"https://orcid.org/{orcid_id}",
                            source="orcid_email",
                            category="academico",
                            snippet=f"ORCID vinculado al email {email}",
                        ))
        except Exception:
            pass

    return results[:max_r]


# ── 8. Búsqueda por teléfono ───────────────────────────────────────
async def search_by_phone(
    client: httpx.AsyncClient, phone: str, max_r: int,
) -> list[PersonResult]:
    """Busca referencias a un número de teléfono."""
    if not phone:
        return []
    results: list[PersonResult] = []

    # Normalizar teléfono
    phone_clean = re.sub(r"[^\d+]", "", phone)
    if not phone_clean.startswith("+"):
        phone_clean_intl = f"+34{phone_clean}" if not phone_clean.startswith("34") else f"+{phone_clean}"
    else:
        phone_clean_intl = phone_clean

    # Formatos de búsqueda
    phone_variants = set()
    digits = phone_clean.lstrip("+")
    if digits.startswith("34"):
        digits = digits[2:]
    phone_variants.add(digits)
    phone_variants.add(f"+34{digits}")
    phone_variants.add(f"+34 {digits[:3]} {digits[3:6]} {digits[6:]}")
    phone_variants.add(f"{digits[:3]} {digits[3:6]} {digits[6:]}")
    phone_variants.add(f"{digits[:3]}-{digits[3:6]}-{digits[6:]}")

    for variant in list(phone_variants)[:3]:
        q = f'"{variant}"'
        raw = await _searxng(client, q, 1, 5)
        for r in raw:
            results.append(PersonResult(
                title=_trim(r.get("title", ""), 120),
                url=r.get("url", ""),
                source="telefono_web",
                category="telefono",
                snippet=_trim(r.get("content", "")),
            ))

    # Páginas Blancas / directorios telefónicos
    phone_sites = {
        "PáginasBlancas": "paginasblancas.es",
        "Infobel": "infobel.com/es",
        "11888": "11888.es",
    }
    for label, site in phone_sites.items():
        q = f'"{digits}" site:{site}'
        raw = await _searxng(client, q, 1, 3)
        for r in raw:
            results.append(PersonResult(
                title=f"[{label}] {_trim(r.get('title', ''), 100)}",
                url=r.get("url", ""),
                source=label.lower().replace("á", "a"),
                category="telefono",
                snippet=_trim(r.get("content", "")),
            ))

    return results[:max_r]


# ── 9. Búsqueda por DNI ────────────────────────────────────────────
async def search_by_dni(
    client: httpx.AsyncClient, dni: str, max_r: int,
) -> list[PersonResult]:
    """Busca apariciones de un DNI en documentos públicos."""
    if not dni:
        return []
    results: list[PersonResult] = []
    dni_upper = dni.upper().strip()

    # BOE y diarios oficiales publican DNIs
    q_boe = f'"{dni_upper}" site:boe.es'
    raw = await _searxng(client, q_boe, 2, max_r)
    for r in raw:
        results.append(PersonResult(
            title=_trim(r.get("title", ""), 150),
            url=r.get("url", ""),
            source="boe_dni",
            category="documento_oficial",
            snippet=_trim(r.get("content", "")),
        ))

    # Búsqueda general del DNI
    q_gen = f'"{dni_upper}" subvención OR ayuda OR resolución OR nombramiento'
    raw_gen = await _searxng(client, q_gen, 1, max_r)
    for r in raw_gen:
        results.append(PersonResult(
            title=_trim(r.get("title", ""), 150),
            url=r.get("url", ""),
            source="dni_general",
            category="documento_oficial",
            snippet=_trim(r.get("content", "")),
        ))

    # Registros mercantiles con DNI
    q_merc = f'"{dni_upper}" site:librebor.me OR site:einforma.com OR site:axesor.es'
    raw_merc = await _searxng(client, q_merc, 1, 5)
    for r in raw_merc:
        results.append(PersonResult(
            title=_trim(r.get("title", ""), 120),
            url=r.get("url", ""),
            source="registro_mercantil",
            category="directorio",
            snippet=_trim(r.get("content", "")),
        ))

    return results[:max_r]


# ── Keywords cross-search ──────────────────────────────────────────
async def search_keywords(
    client: httpx.AsyncClient,
    name: dict,
    keywords: list[str],
    pages: int = 2,
    max_r: int = 30,
) -> list[PersonResult]:
    """Cross-search: for each keyword, search 'surname keyword' to find
    results that mention the person in a business/sectoral context."""
    results: list[PersonResult] = []
    # Build surname forms to combine with keywords
    surname = name.get("last", "") or name["full"]
    # Also try just the last surname for people with many names
    last_parts = name["parts"][1:] if len(name["parts"]) > 1 else name["parts"]
    surname_short = " ".join(last_parts[-2:]) if len(last_parts) >= 2 else surname

    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        queries = [
            f'"{surname}" {kw}',
        ]
        # If short surname differs, also search that
        if surname_short != surname:
            queries.append(f'"{surname_short}" {kw}')
        # Also search keyword alone (for company/property names)
        queries.append(f'"{kw}"')

        for q in queries:
            raw = await _searxng(client, q, pages=min(pages, 2), max_results=10)
            for r in raw:
                results.append(PersonResult(
                    title=_trim(r.get("title", ""), 120),
                    url=r.get("url", ""),
                    source="keyword_cross",
                    category="web",
                    snippet=_trim(r.get("content", "")),
                    date=r.get("publishedDate", ""),
                    extra={"keyword": kw, "query": q},
                ))

    return results[:max_r]


# ══════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════

SOURCES_ALL = {
    "web", "boe", "rrss", "scholar", "institucional", "directorios",
    "email", "telefono", "dni", "keywords",
}


async def buscar_persona(
    name_plus: str = "",
    email: str = "",
    phone: str = "",
    dni: str = "",
    keywords: list[str] | None = None,
    pages: int = 5,
    max_per_source: int = 50,
    sources: set[str] | None = None,
) -> tuple[list[PersonResult], dict[str, int]]:
    """Orquesta todas las búsquedas para una persona."""
    if sources is None:
        sources = SOURCES_ALL

    name = _name_from_plus(name_plus) if name_plus else None
    all_results: list[PersonResult] = []
    source_counts: dict[str, int] = {}

    if not name and not email and not phone and not dni:
        log.error("❌ Debes proporcionar al menos: nombre, email, teléfono o DNI")
        return [], {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks: dict[str, asyncio.Task] = {}

        if name:
            if "web" in sources:
                tasks["🌐 Web general"] = asyncio.create_task(
                    search_web_general(client, name, pages, max_per_source)
                )
            if "boe" in sources:
                tasks["📜 BOE & Diarios oficiales"] = asyncio.create_task(
                    search_boe(client, name, dni, pages, max_per_source)
                )
            if "rrss" in sources:
                tasks["📱 RRSS"] = asyncio.create_task(
                    search_rrss(client, name, email, pages, max_per_source)
                )
            if "scholar" in sources:
                tasks["🎓 Académico & Investigación"] = asyncio.create_task(
                    search_academico(client, name, email, pages, max_per_source)
                )
            if "institucional" in sources:
                tasks["🏛️ Institucional ganadero"] = asyncio.create_task(
                    search_institucional(client, name, pages, max_per_source)
                )
            if "directorios" in sources:
                tasks["🏢 Directorios empresariales"] = asyncio.create_task(
                    search_directorios(client, name, dni, pages, max_per_source)
                )
            if keywords and "keywords" in sources:
                tasks["🔑 Keywords cruzadas"] = asyncio.create_task(
                    search_keywords(client, name, keywords, pages, max_per_source)
                )

        if email and "email" in sources:
            tasks["📧 Email"] = asyncio.create_task(
                search_by_email(client, email, max_per_source)
            )
        if phone and "telefono" in sources:
            tasks["📞 Teléfono"] = asyncio.create_task(
                search_by_phone(client, phone, max_per_source)
            )
        if dni and "dni" in sources:
            tasks["🆔 DNI"] = asyncio.create_task(
                search_by_dni(client, dni, max_per_source)
            )

        for label, task in tasks.items():
            try:
                results = await task
                log.info(f"  {label:<35s} →  {len(results):>3} resultados")
                source_counts[label] = len(results)
                all_results.extend(results)
            except Exception as e:
                log.warning(f"  {label:<35s} →  ❌ Error: {e}")
                source_counts[label] = 0

    return all_results, source_counts


# ── Deduplication & relevance ───────────────────────────────────────
def _strip_accents(s: str) -> str:
    """Remove accents/diacritics for fuzzy name matching."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _result_mentions_person(
    r: PersonResult, name: dict | None, email: str, dni: str, phone: str,
) -> bool:
    """Return True if the result plausibly references the target person."""
    # If no name given, we can't filter by name
    if not name:
        return True
    text = _strip_accents(f"{r.title} {r.snippet} {r.url}").lower()
    parts = [_strip_accents(p).lower() for p in name["parts"]]
    # Exact email/DNI/phone match always passes
    if email and email.lower() in text:
        return True
    if dni and _strip_accents(dni).upper() in text.upper():
        return True
    if phone:
        digits = re.sub(r"\D", "", phone)
        if digits in re.sub(r"\D", "", text):
            return True
    # ── Trusted sources always pass ──
    _TRUSTED = {"boe_directo", "orcid", "openalex", "gravatar", "hibp",
                "infobel", "paginasamarillas", "keyword_cross"}
    if r.source.lower() in _TRUSTED:
        return True
    # documento_oficial always passes (BOE, BORME, diarios autonómicos)
    if r.category == "documento_oficial":
        return True
    # keyword cross-search results always pass
    if r.source == "keyword_cross":
        return True
    # Permissive name filter: require only 1 of N name parts to match
    matches = sum(1 for p in parts if p in text)
    return matches >= 1


def deduplicate(results: list[PersonResult]) -> list[PersonResult]:
    seen: dict[str, PersonResult] = {}
    for r in results:
        key = r.dedup_key
        if key not in seen or r.relevance > seen[key].relevance:
            seen[key] = r
    return list(seen.values())


def rank_person_results(
    results: list[PersonResult], name: dict | None, email: str, dni: str,
) -> list[PersonResult]:
    """Rank by relevance to the person."""
    cat_boost = {
        "documento_oficial": 2.0,
        "academico": 1.8,
        "institucional": 1.5,
        "rrss": 1.3,
        "directorio": 1.2,
        "email": 1.4,
        "telefono": 1.0,
        "web": 0.9,
    }
    for r in results:
        score = 1.0
        boost = cat_boost.get(r.category, 1.0)

        # Name match in title/snippet
        if name:
            text = f"{r.title} {r.snippet}".lower()
            parts_match = sum(1 for p in name["parts"] if p.lower() in text)
            score += parts_match / max(len(name["parts"]), 1) * 2

        # Email match
        if email and email.lower() in f"{r.title} {r.snippet} {r.url}".lower():
            score += 2

        # DNI match
        if dni and dni.upper() in f"{r.title} {r.snippet}".upper():
            score += 3

        # BOE/official document extra boost
        if "boe" in r.source or r.category == "documento_oficial":
            boost *= 1.3

        # Academic citations boost
        cited = r.extra.get("cited_by_count", 0)
        if cited:
            import math
            boost *= 1 + math.log10(max(cited, 1)) * 0.1

        r.relevance = score * boost

    results.sort(key=lambda r: r.relevance, reverse=True)
    return results


# ── Output formatters ───────────────────────────────────────────────

CATEGORY_EMOJI = {
    "documento_oficial": "📜",
    "rrss": "📱",
    "academico": "🎓",
    "institucional": "🏛️",
    "directorio": "🏢",
    "email": "📧",
    "telefono": "📞",
    "web": "🌐",
}

CATEGORY_LABEL = {
    "documento_oficial": "Documentos Oficiales (BOE, diarios autonómicos)",
    "rrss": "Redes Sociales",
    "academico": "Publicaciones & Perfiles Académicos",
    "institucional": "Webs Institucionales Ganaderas",
    "directorio": "Directorios Empresariales & Registros",
    "email": "Resultados por Email",
    "telefono": "Resultados por Teléfono",
    "web": "Web General",
}


def format_terminal(
    results: list[PersonResult],
    source_counts: dict[str, int],
    name_plus: str, email: str, phone: str, dni: str,
) -> str:
    lines = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════╗")

    target = name_plus.replace("+", " ") if name_plus else email or phone or dni
    lines.append(f"║  🔍 PERSONA: {target[:50]:<50s} ║")

    extras = []
    if email:
        extras.append(f"📧 {email}")
    if phone:
        extras.append(f"📞 {phone}")
    if dni:
        extras.append(f"🆔 {dni}")
    if extras:
        extra_str = " | ".join(extras)
        lines.append(f"║  {extra_str:<64s} ║")

    lines.append("╠══════════════════════════════════════════════════════════════════╣")

    for src, count in source_counts.items():
        status = f"{count:>3} resultados" if count > 0 else "  ❌ sin resultado"
        lines.append(f"║  {src:<34s} {status:>28s} ║")
    lines.append(f"║{'─' * 64}║")
    lines.append(f"║  📊 TOTAL (deduplicado): {len(results):<39} ║")
    lines.append("╚══════════════════════════════════════════════════════════════════╝")

    # Group by category
    groups: dict[str, list[PersonResult]] = {}
    for r in results:
        groups.setdefault(r.category, []).append(r)

    # Ordered categories
    cat_order = [
        "documento_oficial", "academico", "institucional",
        "rrss", "directorio", "email", "telefono", "web",
    ]
    for cat in cat_order:
        group = groups.get(cat, [])
        if not group:
            continue
        emoji = CATEGORY_EMOJI.get(cat, "📄")
        label = CATEGORY_LABEL.get(cat, cat)
        lines.append(f"\n{'━' * 66}")
        lines.append(f"  {emoji} {label} ({len(group)} resultados)")
        lines.append(f"{'━' * 66}")

        for i, r in enumerate(group, 1):
            date_str = f" ({r.date})" if r.date else ""
            lines.append(f"\n  {i:>3}. {r.title[:80]}{date_str}")
            lines.append(f"       🔗 {r.url[:95]}")
            if r.snippet:
                lines.append(f"       📝 {r.snippet[:160]}")
            if r.source not in r.title.lower():
                lines.append(f"       📌 Fuente: {r.source}")
            # Extra info
            if r.extra.get("works_count"):
                lines.append(f"       📊 {r.extra['works_count']} publicaciones, {r.extra.get('cited_by_count',0)} citas")
            if r.extra.get("gravatar_urls"):
                for gu in r.extra["gravatar_urls"][:3]:
                    lines.append(f"       🔗 {gu[:90]}")

    lines.append(f"\n{'═' * 66}")
    lines.append(f"  Búsqueda completada: {len(results)} resultados únicos")
    lines.append(f"{'═' * 66}\n")

    return "\n".join(lines)


def export_csv(results: list[PersonResult], filepath: str):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "category", "title", "url", "source",
            "snippet", "relevance", "date",
        ])
        for i, r in enumerate(results, 1):
            writer.writerow([
                i, r.category, r.title, r.url, r.source,
                r.snippet, f"{r.relevance:.2f}", r.date,
            ])
    log.info(f"  📁 Exportado a {filepath} ({len(results)} filas)")


def export_json(results: list[PersonResult], filepath: str):
    data = [asdict(r) for r in results]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"  📁 Exportado a {filepath} ({len(results)} entradas)")


# ── CLI ─────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="🔍 Seedy — Búsqueda de Personas del Sector Ganadero",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s "Juan+Pérez+García"
  %(prog)s "María+López" --email mlopez@inia.es
  %(prog)s --email contacto@granja.es
  %(prog)s --dni 12345678A
  %(prog)s --telefono 612345678
  %(prog)s "Pedro+Martínez" --export resultados.csv
  %(prog)s "Ana+Ruiz" --solo-fuentes boe,rrss,scholar
  %(prog)s "Hugo+Rodriguez+Sauras" --keywords "capilarium,finca los furriles,caza extremadura"
        """,
    )
    parser.add_argument(
        "nombre",
        nargs="?",
        default="",
        help="Nombre con + como separador: 'Juan+Pérez+García'",
    )
    parser.add_argument("--email", default="", help="Email de la persona")
    parser.add_argument("--telefono", default="", help="Teléfono (ej: 612345678)")
    parser.add_argument("--dni", default="", help="DNI/NIF (ej: 12345678A)")
    parser.add_argument(
        "--keywords", "-k", default="",
        help="Palabras clave del contexto: empresa, finca, sector (separadas por coma)",
    )
    parser.add_argument(
        "--max", "-m", type=int, default=50, dest="max_per_source",
        help="Máximo resultados por fuente (default: 50)",
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=2,
        help="Páginas SearXNG por consulta (default: 10)",
    )
    parser.add_argument(
        "--export", "-e", default="",
        help="Exportar resultados (.csv o .json)",
    )
    parser.add_argument(
        "--solo-fuentes", "-s", default="",
        help=f"Solo estas fuentes (separadas por coma): {','.join(sorted(SOURCES_ALL))}",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Mostrar detalles de depuración",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.nombre and not args.email and not args.telefono and not args.dni:
        log.error("❌ Proporciona al menos un dato: nombre, --email, --telefono o --dni")
        sys.exit(1)

    sources = None
    if args.solo_fuentes:
        alias = {
            "web": "web", "boe": "boe", "oficial": "boe",
            "rrss": "rrss", "social": "rrss", "redes": "rrss",
            "scholar": "scholar", "academico": "scholar", "ciencia": "scholar",
            "institucional": "institucional", "inst": "institucional",
            "directorios": "directorios", "empresas": "directorios",
            "email": "email", "telefono": "telefono", "dni": "dni",
            "keywords": "keywords", "kw": "keywords",
        }
        sources = {alias.get(s.strip().lower(), s.strip().lower()) for s in args.solo_fuentes.split(",")}

    # Parse keywords
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []

    name = _name_from_plus(args.nombre) if args.nombre else None
    target = args.nombre.replace("+", " ") if args.nombre else args.email or args.telefono or args.dni

    log.info(f"\n🔍 Buscando persona: \"{target}\"")
    if args.email:
        log.info(f"   📧 Email: {args.email}")
    if args.telefono:
        log.info(f"   📞 Teléfono: {args.telefono}")
    if args.dni:
        log.info(f"   🆔 DNI: {args.dni}")
    if keywords:
        log.info(f"   🔑 Keywords: {', '.join(keywords)}")
    log.info(f"   Max/fuente: {args.max_per_source} | Páginas: {args.pages}")
    if sources:
        log.info(f"   Fuentes: {', '.join(sorted(sources))}")
    log.info("")

    t0 = time.time()
    all_results, source_counts = await buscar_persona(
        name_plus=args.nombre,
        email=args.email,
        phone=args.telefono,
        dni=args.dni,
        keywords=keywords or None,
        pages=args.pages,
        max_per_source=args.max_per_source,
        sources=sources,
    )

    unique = deduplicate(all_results)
    # Post-filter: keep only results that actually mention the person
    filtered = [
        r for r in unique
        if _result_mentions_person(r, name, args.email, args.dni, args.telefono)
    ]
    dropped = len(unique) - len(filtered)
    if dropped:
        log.info(f"  ✂️ Filtrados {dropped} resultados no relevantes")
    ranked = rank_person_results(filtered, name, args.email, args.dni)
    elapsed = time.time() - t0

    output = format_terminal(
        ranked, source_counts,
        args.nombre, args.email, args.telefono, args.dni,
    )
    print(output)
    log.info(f"  ⏱️ Tiempo total: {elapsed:.1f}s")

    if args.export:
        if args.export.endswith(".json"):
            export_json(ranked, args.export)
        else:
            export_csv(ranked, args.export)


if __name__ == "__main__":
    asyncio.run(main())
