#!/usr/bin/env python3
"""
dify_labels.py  –  Script unificado: genera labels.csv + aplica metadata en Dify.

  # Solo generar CSV (dry-run)
  DIFY_API_KEY=dataset-seedyNeoFarm2026kb \
  DIFY_DATASET_ID=880d67ee-3bd3-40ce-a457-ef46a3ad6be6 \
  python3 dify_labels.py

  # Generar CSV  +  aplicar metadata en Dify
  APPLY=1 ... python3 dify_labels.py
"""
from __future__ import annotations

import os
import re
import csv
import time
import unicodedata
from typing import Dict, List, Tuple

import requests

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "http://localhost:3002/v1").rstrip("/")
DIFY_API_KEY  = os.getenv("DIFY_API_KEY", "").strip()
DATASET_ID    = os.getenv("DIFY_DATASET_ID", "").strip()

OUT_CSV = os.getenv("OUT_CSV", "labels.csv")
APPLY   = os.getenv("APPLY", "0").strip() == "1"
CONTENT_PASS = os.getenv("CONTENT_PASS", "1").strip() == "1"   # 2nd pass via segments API
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "25"))
SLEEP_BETWEEN_BATCHES = float(os.getenv("SLEEP_BETWEEN_BATCHES", "0.2"))

if not DIFY_API_KEY or not DATASET_ID:
    raise SystemExit(
        "Faltan variables: DIFY_API_KEY y/o DIFY_DATASET_ID.\n"
        "  export DIFY_API_KEY='dataset-XXXX'\n"
        "  export DIFY_DATASET_ID='UUID'\n"
    )

HEADERS = {
    "Authorization": f"Bearer {DIFY_API_KEY}",
    "Content-Type": "application/json",
}

# ──────────────────────────────────────────────
# Util
# ──────────────────────────────────────────────
def norm(s: str) -> str:
    """lower + quita acentos + separadores → espacios.
    capón→capon, capão→capao, Modulo_Genetica→modulo genetica
    """
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # quitar extensión de archivo
    s = re.sub(r"\.(pdf|md|txt|csv|jsonl)$", "", s)
    # separadores comunes en nombres de archivo → espacio
    s = re.sub(r"[_\-\./]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def add(tags: List[str], *new_tags: str) -> None:
    for t in new_tags:
        if t and t not in tags:
            tags.append(t)


def any_prefix(tags: List[str], prefix: str) -> bool:
    return any(t.startswith(prefix) for t in tags)


def http_get(path: str, params=None) -> dict:
    r = requests.get(f"{DIFY_BASE_URL}{path}", headers=HEADERS, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def http_post(path: str, payload: dict) -> dict:
    r = requests.post(f"{DIFY_BASE_URL}{path}", headers=HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def list_all_documents(dataset_id: str) -> List[dict]:
    docs: List[dict] = []
    page, limit = 1, 100
    while True:
        data = http_get(f"/datasets/{dataset_id}/documents", params={"page": page, "limit": limit})
        docs.extend(data.get("data", []))
        if not data.get("has_more", False):
            break
        page += 1
    return docs


def fetch_first_segment(dataset_id: str, doc_id: str, max_chars: int = 4000) -> str:
    """Descarga los primeros segmentos de un documento vía API de Dify."""
    try:
        data = http_get(f"/datasets/{dataset_id}/documents/{doc_id}/segments")
        segments = data.get("data", [])
        text = ""
        for seg in segments:
            text += seg.get("content", "") + " "
            if len(text) >= max_chars:
                break
        return text[:max_chars]
    except Exception as e:
        print(f"    ⚠ segments error ({doc_id[:12]}…): {e}")
        return ""


# ──────────────────────────────────────────────
# Reglas de clasificación (sobre nombre normalizado)
# ──────────────────────────────────────────────

# ESPECIE
SPECIES_PATTERNS: List[Tuple[str, str]] = [
    ("ESPECIE:BOVINO",
     r"\b(vacuno|bovino|vacasdata|novilla|ternera|toro|vaca|cattle|bovine|cow|bull|bos taurus|calf|calves|heifer|steer|feedlot)s?\b"),
    ("ESPECIE:PORCINO",
     r"\b(porcino|porcidata|cerdo|lechon|cebo|engorde|pig|swine|porcine|hog|sow|piglet|boar|gilt|barrow|sus scrofa)s?\b"),
    ("ESPECIE:AVICULTURA",
     r"\b(avicultura|poultry|chicken|hen|rooster|broiler|layer|gallina|gallo|pollo|fowl|chick|pullet|cockerel|gallus|laying hen)s?\b"),
]

# SUBTIPOS
SUBTYPE_PATTERNS: List[Tuple[str, str]] = [
    ("SUB:INTENSIVO",  r"\b(intensivo|intensive)\b"),
    ("SUB:EXTENSIVO",  r"\b(extensivo|extensive|pasture|pastoreo|free range|campero)\b"),
    ("SUB:CAPONES",    r"\b(capon|capones|capao|caponiz\w*|castrat\w*|capone?)\b"),
    ("SUB:ECOLOGICO",  r"\b(ecologico|organic|bio |agroecolog\w*)\b"),
]

# TEMAS
TOPIC_PATTERNS: List[Tuple[str, str]] = [
    ("TEMA:GENETICA",
     r"\b(genetica|genetic|genomic|gwas|qtldb|ensembl|qtl|snp|ebv|gebv|genotype|phenotype|heritability|heterosis|crossbreed|inbreeding|selection|chromosome|allele|polymorphism|marker assisted|genome wide|transcriptom\w*|gene expression|sequencing|resequenc|spliced gene)s?\b"),
    ("TEMA:RAZAS",
     r"\b(raza|razas|breed|breeds|dad\s?is|landrace|duroc|pietrain|large white|iberic\w*|angus|hereford|charolais|limousi\w*|ross|cobb|hubbard)\b"),
    ("TEMA:NORMATIVA",
     r"\b(normativa|reglamento|directive|regulation|eur lex|woah|oie|sige|ecogan|rd\s?\d{3,4}|legislacion|ley|decreto|orden ministerial)s?\b"),
    ("TEMA:MANEJO",
     r"\b(manejo|management|husbandry|rearing|crianza|handling|alojamiento|housing|ventilacion|ventilation|densidad|stocking density|cage free|aviary|floor type)s?\b"),
    ("TEMA:BIOSEGURIDAD",
     r"\b(bioseguridad|biosecurity|cuarentena|quarantine|desinfeccion|disinfect\w*|sanitation|sanitiz\w*|chlorine|hydrogen peroxide)\b"),
    ("TEMA:BIENESTAR",
     r"\b(bienestar|welfare|enriquecimiento|enrichment|stress|cortisol|comportamiento|behaviour|behavior|cage free|free range|space use)\b"),
    ("TEMA:NUTRICION",
     r"\b(nutricion|nutrition|nutritive|feed|diet\w*|pienso|racion|formulation|lonja|amino\s?acid|protein|soybean|soja|fatty acid|omega|insect meal|larva|tenebrio|hermetia|lysine|methionine|energy|metabolizable|digestib\w*|additive|probiotic|prebiotic|enzyme|phytase|phytate|supplement\w*|intake|conversion|fcr|corn|canola|oat hull|vitamin|mineral|antioxidant|ferment\w*|bioavailab\w*)s?\b"),
    ("TEMA:SANIDAD",
     r"\b(sanidad|health|disease|veterinar\w*|pathogen|antimicrobial|amr|zoonotic|infection|mortality|immune|immun\w*|vaccin\w*|salmonella|campylobacter|parasit\w*|bacteri\w*|virus|coccid\w*|marek|newcastle|influenza|antibiot\w*|resistance|morbidity|diarr\w*|necrotic|enteritis|mycotoxin|moldy|eimeria|mucosal barrier|protective effect|iga|intestinal|ileal|pathogen\w*)s?\b"),
    ("TEMA:CALIDAD_CARNE",
     r"\b(meat quality|calidad de carne|carcass|canal|intramuscular fat|grasa intramuscular|tenderness|terneza|juiciness|jugosidad|sensory|organolep\w*|ph\s?postmortem|color de carne|marbling|marmole\w*|textura|firmness|drip loss|collagen)\b"),
    ("TEMA:PRODUCCION",
     r"\b(produccion|production|productivity|yield|rendimiento|crecimiento|growth|ganancia|average daily gain|peso vivo|live weight|slaughter|sacrificio|matadero|faena|indice de conversion|performance|egg quality|egg production)\b"),
    ("TEMA:REPRODUCCION",
     r"\b(reproduccion|reproduction|fertility|fertilidad|incubacion|incubation|hatchability|eclosion|inseminacion|insemination|ovulacion|ovulation|prolificidad|prolificacy|litter size|camada|in ovo|embryo\w*|laying hen|hatch)\b"),
    # Proyecto / tech
    ("TEMA:IOT",           r"\b(iot|monitoring|sensor|sensing|livestock monitoring|mioty|telemetria|telemetry|wearable|accelerometer|rfid)\b"),
    ("TEMA:DIGITAL_TWINS", r"\bdigital\s?twins?\b"),
    ("TEMA:RAG",           r"\brag\b"),
    ("TEMA:ARQUITECTURA",  r"\barquitectura\b"),
    ("TEMA:PIPELINE",      r"\bpipeline\b"),
    ("TEMA:ROADMAP",       r"\broadmap\b"),
    ("TEMA:DATASETS",      r"\bdatasets?\b"),
]

# FUENTE
SOURCE_PATTERNS: List[Tuple[str, str]] = [
    ("FUENTE:FAO",        r"\b(fao|dad\s?is)\b"),
    ("FUENTE:HARVARD",    r"\bharvard\b"),
    ("FUENTE:CIENTIFICO", r"(1 s2 0 |\bmdpi\b|\banimals \d|\bmanuscript\b|\bdoi\b|\bjournal\b|\barticle\b|\bspringer\b|\belsevier\b|\bwiley\b|\bfrontiers\b|\bplos\b|\babstract\b|\bpubmed\b|\bpeer.review\w*\b|\bpoultry science\b|\bcitations?\b|\bpoult\b|\bphd.thesis\b|\bajol\b)"),
    ("FUENTE:GUIA_TECNICA", r"\b(manual|guide|handbook|guia|protocol|protocolo|ficha tecnica)\b"),
    ("FUENTE:INTERNO",    r"\b(neofarm|seedy|porcidata|vacasdata|modulo |resumen |master roadmap|arquitectura|propuesta)\b"),
    ("FUENTE:MAPA",       r"\b(mapa raza|arca|ministerio.{0,20}ganaderia|mapa.{0,10}bovino|mapa.{0,10}porcino|mapa.{0,10}aviar)\b"),
]

# IDIOMA
LANG_PATTERNS: List[Tuple[str, str]] = [
    ("IDIOMA:PT", r"\b(portugues\w*|produtos|freamunde|capao|igp|lisboa|alentejo|transmontano)\b"),
    ("IDIOMA:ES", r"\b(espanol|castellano|normativa|avicultura|porcino|vacuno|ganaderia|proyecto|modulo|nutricion|genetica|presentacion|jornadas|produccion animal|espana|ministerio)\b"),
    ("IDIOMA:EN", r"\b(english|genome|study|effects|evaluation|analysis|review|production|breeding|livestock|poultry science|abstract|results|introduction|materials and methods|discussion|conclusion)\b"),
]

# Pistas internas por nombre → inyectan tags extra
INTERNAL_HINTS: List[Tuple[str, List[str]]] = [
    (r"\bneofarm\b",    ["FUENTE:INTERNO"]),
    (r"\bseedy\b",      ["FUENTE:INTERNO"]),
    (r"\bmodulo\b",     ["FUENTE:INTERNO"]),
    (r"\bresumen\b",    ["FUENTE:INTERNO"]),
    (r"\bporcidata\b",  ["FUENTE:INTERNO", "ESPECIE:PORCINO"]),
    (r"\bvacasdata\b",  ["FUENTE:INTERNO", "ESPECIE:BOVINO"]),
    (r"\becogan\b",     ["FUENTE:INTERNO", "TEMA:NORMATIVA", "ESPECIE:PORCINO"]),
    (r"\brd\s?\d{3,4}\b", ["FUENTE:INTERNO", "TEMA:NORMATIVA"]),
    (r"\bsige\b",       ["FUENTE:INTERNO", "TEMA:NORMATIVA", "ESPECIE:PORCINO"]),
    (r"\braf\b",        ["FUENTE:INTERNO"]),
    # Artículos de Poultry Science → avicultura + científico
    (r"poult\w*$|_poult\w*\b|\bpoultry sci",   ["FUENTE:CIENTIFICO", "ESPECIE:AVICULTURA"]),
    # CDA exports → interno + digital twins
    (r"\bcda.export",    ["FUENTE:INTERNO", "TEMA:DIGITAL_TWINS"]),
    # ScienceDirect 1-s2.0 → científico
    (r"^1 s2 0 ",        ["FUENTE:CIENTIFICO"]),
    # Tesis doctoral
    (r"\bphd.thesis|\btesis\b", ["FUENTE:CIENTIFICO"]),
    # MAPA razas
    (r"\bmapa.*raza|\barca\b",  ["FUENTE:MAPA", "TEMA:RAZAS"]),
]


def match_patterns(text: str, patterns: List[Tuple[str, str]]) -> List[str]:
    t = norm(text)
    return [tag for tag, pat in patterns if re.search(pat, t, flags=re.I)]


def infer_tags(doc_name: str, content: str = "") -> List[str]:
    tags: List[str] = []
    t = norm(doc_name)
    # Texto combinado: nombre + contenido (para 2nd pass)
    combined = t + " " + norm(content) if content else t

    # 1) Fuente (por nombre; si hay contenido, también buscar ahí)
    src = match_patterns(doc_name, SOURCE_PATTERNS)
    if content:
        src += [s for s in match_patterns(content, SOURCE_PATTERNS) if s not in src]
    if src:
        for s in src:
            add(tags, s)
    else:
        add(tags, "FUENTE:WEB")

    # 2) Especie / tema / subtipo — sobre nombre + contenido
    target = combined if content else doc_name
    for tag in match_patterns(target, SPECIES_PATTERNS):
        add(tags, tag)
    for tag in match_patterns(target, TOPIC_PATTERNS):
        add(tags, tag)
    for tag in match_patterns(target, SUBTYPE_PATTERNS):
        add(tags, tag)

    # 3) Pistas internas (solo por nombre)
    for pat, extra_tags in INTERNAL_HINTS:
        if re.search(pat, t, flags=re.I):
            for et in extra_tags:
                add(tags, et)

    # 4) Si capón detectado pero sin especie → avicultura
    if any(t == "SUB:CAPONES" for t in tags) and not any_prefix(tags, "ESPECIE:"):
        add(tags, "ESPECIE:AVICULTURA")

    # 4b) Si es de Poultry Science y no tiene especie → avicultura
    if "FUENTE:CIENTIFICO" in tags and not any_prefix(tags, "ESPECIE:"):
        if re.search(r"poult|poultry", norm(doc_name), re.I):
            add(tags, "ESPECIE:AVICULTURA")

    # 5) Idioma — sobre nombre + contenido
    for tag in match_patterns(target, LANG_PATTERNS):
        add(tags, tag)
    if not any_prefix(tags, "IDIOMA:"):
        # Detectar idioma por heurística de contenido
        if content and re.search(r"\b(the|and|of|in|for|with|from|this|was|were|that)\b", norm(content)[:500]):
            add(tags, "IDIOMA:EN")
        else:
            add(tags, "IDIOMA:ES")  # default ES para NeoFarm

    return tags


def is_poorly_tagged(tags: List[str]) -> bool:
    """Retorna True si el doc solo tiene FUENTE + IDIOMA (sin ESPECIE/TEMA/SUB)."""
    for t in tags:
        prefix = t.split(":")[0]
        if prefix in ("ESPECIE", "TEMA", "SUB"):
            return False
    return True


# ──────────────────────────────────────────────
# Aplicar metadata en Dify (APPLY=1)
# ──────────────────────────────────────────────
PREFIX_TO_FIELD = {
    "ESPECIE": "especie",
    "TEMA": "tema",
    "SUB": "subtipo",
    "FUENTE": "fuente",
    "IDIOMA": "idioma",
}
DEFAULT_FIELD = "etiquetas_libres"


def parse_tags_to_fields(tags: List[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for p in tags:
        if ":" in p:
            prefix, value = p.split(":", 1)
            field = PREFIX_TO_FIELD.get(prefix.strip().upper(), DEFAULT_FIELD)
            out.setdefault(field, []).append(value.strip())
        else:
            out.setdefault(DEFAULT_FIELD, []).append(p.strip())
    for k in list(out.keys()):
        out[k] = sorted(set(out[k]))
    return out


def get_metadata_fields(dataset_id: str) -> Dict[str, str]:
    data = http_get(f"/datasets/{dataset_id}/metadata")
    fields: Dict[str, str] = {}
    for m in data.get("doc_metadata", []):
        if m.get("name") and m.get("id"):
            fields[m["name"]] = m["id"]
    return fields


def ensure_metadata_field(dataset_id: str, fields: Dict[str, str], field_name: str) -> str:
    if field_name in fields:
        return fields[field_name]
    created = http_post(f"/datasets/{dataset_id}/metadata", {"type": "string", "name": field_name})
    mid = created.get("id")
    if not mid:
        raise RuntimeError(f"No pude crear metadata field '{field_name}': {created}")
    fields[field_name] = mid
    print(f"  [+] campo creado: {field_name} → {mid}")
    return mid


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def apply_metadata(dataset_id: str, docs: List[dict], doc_name_to_tags: Dict[str, List[str]]):
    name_to_id = {d["name"]: d["id"] for d in docs if d.get("name") and d.get("id")}

    fields = get_metadata_fields(dataset_id)
    needed = set()
    for tags in doc_name_to_tags.values():
        for field in parse_tags_to_fields(tags).keys():
            needed.add(field)
    for field in sorted(needed):
        ensure_metadata_field(dataset_id, fields, field)

    ops = []
    missing = 0
    for name, tags in doc_name_to_tags.items():
        doc_id = name_to_id.get(name)
        if not doc_id:
            missing += 1
            continue
        parsed = parse_tags_to_fields(tags)
        metadata_list = [
            {"id": fields[fn], "name": fn, "value": "|".join(vals)}
            for fn, vals in parsed.items()
        ]
        ops.append({"document_id": doc_id, "metadata_list": metadata_list})

    print(f"  ops={len(ops)}  missing_names={missing}")

    applied = 0
    for batch in chunked(ops, BATCH_SIZE):
        http_post(f"/datasets/{dataset_id}/documents/metadata", {"operation_data": batch})
        applied += len(batch)
        print(f"  batch aplicado → total {applied}")
        time.sleep(SLEEP_BETWEEN_BATCHES)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    docs = list_all_documents(DATASET_ID)
    print(f"📋 docs: {len(docs)}")

    # Mapa nombre → id para buscar contenido después
    name_to_doc = {d["name"]: d for d in docs if d.get("name")}

    # ── PASS 1: por nombre de archivo ──
    doc_name_to_tags: Dict[str, List[str]] = {}
    for d in docs:
        name = d.get("name", "")
        if name:
            doc_name_to_tags[name] = infer_tags(name)

    poor_count = sum(1 for tags in doc_name_to_tags.values() if is_poorly_tagged(tags))
    print(f"  Pass 1 → {len(doc_name_to_tags) - poor_count} bien, {poor_count} sin ESPECIE/TEMA/SUB")

    # ── PASS 2: por contenido (segmentos API) ──
    if CONTENT_PASS and poor_count > 0:
        print(f"\n🔍 Pass 2: leyendo contenido de {poor_count} docs mal etiquetados...")
        improved = 0
        for name, tags in list(doc_name_to_tags.items()):
            if not is_poorly_tagged(tags):
                continue
            doc_info = name_to_doc.get(name)
            if not doc_info:
                continue
            doc_id = doc_info.get("id", "")
            content = fetch_first_segment(DATASET_ID, doc_id)
            if not content or len(content.strip()) < 20:
                continue
            new_tags = infer_tags(name, content)
            if not is_poorly_tagged(new_tags):
                improved += 1
            doc_name_to_tags[name] = new_tags
            time.sleep(0.05)  # gentle with API

        still_poor = sum(1 for tags in doc_name_to_tags.values() if is_poorly_tagged(tags))
        print(f"  Pass 2 → mejorados: {improved}, aún sin tags: {still_poor}")

    # Escribir CSV
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_name", "tags"])
        for name, tags in doc_name_to_tags.items():
            w.writerow([name, ";".join(tags)])
    print(f"\n💾 {OUT_CSV}")

    # Resumen
    from collections import Counter
    all_tags = Counter()
    for tags in doc_name_to_tags.values():
        for t in tags:
            all_tags[t] += 1

    print("── cobertura ──")
    for tag, count in all_tags.most_common():
        print(f"  {count:4d}  {tag}")

    # Aplicar
    if APPLY:
        print("\n🚀 Aplicando metadata en Dify...")
        apply_metadata(DATASET_ID, docs, doc_name_to_tags)
        print("✅ Metadata aplicada")
    else:
        print("\nℹ️  Solo CSV (usa APPLY=1 para aplicar en Dify)")


if __name__ == "__main__":
    main()
