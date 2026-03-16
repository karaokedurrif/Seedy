#!/usr/bin/env python3
"""
build_dataset_cda.py — Genera Q&As desde los 19 CSVs de FIWARE/CDA (Context Data Acquisition)
para ampliar el dataset de Seedy con conocimiento real de IoT agritech.

Datasets CDA:
  - Animal Tracking (vacuno extensivo)
  - Soil sensors (agrovoltaica)
  - Silos (alimentación)
  - Feeders/comederos
  - Vineyard weather (viticultura)
  - Weather agrovoltaic
  - Pest monitoring
  - Parcels (parcelas agrícolas)
  - Soil analysis (NPK, pH, textura)
  - NPK fertilization
  - Irrigation recommendations, pivots, forecasts
  - GPS device locations

Usa qwen2.5:14b local vía Ollama para generar Q&As grounded en estadísticas reales.
"""

import json
import os
import re
import time
import hashlib
import csv
import io
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import httpx

# ─── CONFIG ────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"
BASE_DIR = Path("/home/davidia/Documentos/Seedy")
CDA_DIR = BASE_DIR / "conocimientos" / "Carga de documentos nuevos"
OUT_FILE = BASE_DIR / "seedy_dataset_cda.jsonl"
PROGRESS_FILE = BASE_DIR / ".cda_progress.json"

SYSTEM_PROMPT = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData 7 capas), nutrición animal (NRC 2012), "
    "genética aplicada (EPDs, FarmMatch, heterosis), digital twins, normativa ganadera "
    "(RD 306/2020, EcoGAN), avicultura extensiva (capones, pulardas, razas autóctonas), "
    "vacuno extensivo y GeoTwin GIS.\n"
    "Responde siempre en español técnico, de forma precisa. Si no tienes datos verificados "
    "sobre algo, indícalo claramente en lugar de inventar."
)


# ─── CDA DATASET DEFINITIONS ──────────────────────────────────
CDA_DATASETS = {
    "cda-export (1).csv": {
        "name": "Animal Tracking IoT",
        "category": "iot",
        "description": "Datos de seguimiento de animales (vacuno extensivo) con sensores IoT: "
                       "actividad, batería, celos, partos, geofencing, temperatura. "
                       "338K registros desde 2024. Entidad FIWARE: Animal.",
        "key_columns": ["activity", "battery", "distance", "hascalvingstatus",
                        "hasheatstatus", "hasgeofencingstatus", "hastemperaturestatus"],
        "entity_type": "Animal",
        "domain": "vacuno extensivo / IoT",
    },
    "cda-export (5).csv": {
        "name": "Silos de Alimentación",
        "category": "iot",
        "description": "Monitorización IoT de silos de pienso: temperatura interna/externa, "
                       "humedad, nivel % y kg. 81K registros. Entidad FIWARE: Silo.",
        "key_columns": ["internaltemperature", "externaltemperature", "internalhumidity",
                        "percentagelevel", "kglevel"],
        "entity_type": "Silo",
        "domain": "alimentación / IoT",
    },
    "cda-export (8).csv": {
        "name": "Sensores de Suelo (Agrovoltaica)",
        "category": "iot",
        "description": "Sensores de suelo en instalaciones agrovoltaicas: humedad a 10-60cm, "
                       "temperatura, potencial hídrico, evapotranspiración. 143K registros. "
                       "Entidad FIWARE: SoilObserved.",
        "key_columns": ["soilmoisture10", "soiltemperature10", "soilmoisture20",
                        "soiltemperature20", "soilmoisture30", "soiltemperature30",
                        "soilmoisture40", "soilmoisture50", "soilmoisture60",
                        "soilwaterpotential", "evapotranspiration"],
        "entity_type": "SoilObserved",
        "domain": "suelo / agrovoltaica",
    },
    "cda-export (10).csv": {
        "name": "Comederos Inteligentes",
        "category": "iot",
        "description": "Monitorización de comederos (feeders): nivel %, visitas de animales, "
                       "vaciado, referencia a silo. 1.5K registros. Entidad FIWARE: Feeder.",
        "key_columns": ["percentagelevel", "feedervisitcount", "isempty", "refsilo"],
        "entity_type": "Feeder",
        "domain": "alimentación / IoT",
    },
    "cda-export (13).csv": {
        "name": "Estación Meteorológica Vitícola",
        "category": "iot",
        "description": "Datos meteorológicos para viticultura: precipitación, humedad, temperatura, "
                       "viento, radiación solar, mojado foliar, integral de Winkler, horas de frío. "
                       "26K registros. Entidad FIWARE: AgroWeatherObserved.",
        "key_columns": ["temperature", "relativehumidity", "precipitation", "windspeed",
                        "solarradiation", "leafwetness", "evapotranspiration",
                        "winklerintegral", "chillinghours", "pressure"],
        "entity_type": "AgroWeatherObserved",
        "domain": "viticultura / meteorología",
    },
    "cda-export (14).csv": {
        "name": "Parcelas Agrícolas",
        "category": "iot",
        "description": "Inventario de parcelas agrícolas: cultivos (Cebolla Rita, Veza-Avena), "
                       "tipo de suelo, sistema de riego, provincia. 295 registros. "
                       "Entidad FIWARE: AgriParcel.",
        "key_columns": ["croptype", "category", "soiltexturetype",
                        "irrigationsystemtype", "area", "province"],
        "entity_type": "AgriParcel",
        "domain": "gestión de parcelas",
    },
    "cda-export (15).csv": {
        "name": "Estación Meteorológica Agrovoltaica",
        "category": "iot",
        "description": "Datos meteorológicos en instalaciones agrovoltaicas: precipitación, "
                       "humedad, temperatura, viento, radiación solar/PAR, evapotranspiración, "
                       "presión. 66K registros. Entidad FIWARE: AgroWeatherObserved.",
        "key_columns": ["temperature", "relativehumidity", "precipitation", "windspeed",
                        "solarradiation", "solarradiationpar", "evapotranspiration",
                        "pressure", "pluviometer"],
        "entity_type": "AgroWeatherObserved",
        "domain": "agrovoltaica / meteorología",
    },
    "cda-export (16).csv": {
        "name": "Monitorización de Plagas",
        "category": "iot",
        "description": "Conteos de insectos capturados en trampas: Aphididae, Araneae, Coleoptera, "
                       "Diptera, Drosophilidae, Hemiptera, Hymenoptera, Lepidoptera, Neuroptera, "
                       "Orthoptera, Thysanoptera. 1K registros con imágenes. "
                       "Entidad FIWARE: AgroPlagueObserved.",
        "key_columns": ["aphididae", "araneae", "coleoptera", "diptera", "drosophilidae",
                        "hemiptera", "hymenoptera", "lepidoptera", "neuroptera",
                        "orthoptera", "thysanoptera"],
        "entity_type": "AgroPlagueObserved",
        "domain": "protección de cultivos / viticultura",
    },
    "cda-export (18).csv": {
        "name": "Análisis Detallado de Suelo",
        "category": "iot",
        "description": "Análisis completo de suelo: NPK, conductividad eléctrica, pH, "
                       "materia orgánica, textura (arena/limo/arcilla), densidad. "
                       "81 muestras georreferenciadas. Entidad FIWARE: SoilObserved (lab).",
        "key_columns": ["nitrogen", "phosphorus", "potassium", "electricconductivity",
                        "ph", "organiccontent", "sandcontent", "siltcontent", "claycontent",
                        "density"],
        "entity_type": "SoilObserved",
        "domain": "análisis de suelo / fertilidad",
    },
    "cda-export (19).csv": {
        "name": "Fertilización NPK por Parcela",
        "category": "iot",
        "description": "Recomendaciones y registros de fertilización NPK por parcela: "
                       "nitrógeno, fósforo, potasio. 11K registros vinculados a parcelas agrícolas. "
                       "Entidad FIWARE: SoilObserved (NPK).",
        "key_columns": ["nitrogen", "phosphorus", "potassium", "npk"],
        "entity_type": "SoilObserved",
        "domain": "fertilización / nutrición de cultivos",
    },
    "cda-export (20).csv": {
        "name": "Recomendaciones de Riego",
        "category": "iot",
        "description": "Recomendaciones automatizadas de riego: consumo de agua, riego programado, "
                       "agua disponible, tiempo de riego. 208 registros. "
                       "Entidad FIWARE: IrrigationRecommendation.",
        "key_columns": ["waterconsumption", "irrigation", "availablewater", "irrigationtime"],
        "entity_type": "IrrigationRecommendation",
        "domain": "riego inteligente",
    },
    "cda-export (21).csv": {
        "name": "Pivotes de Riego",
        "category": "iot",
        "description": "Monitorización de pivotes de riego: presión, posición angular, "
                       "tiempo de riego, velocidad. 20 registros. Entidad FIWARE: IrrigationPivot.",
        "key_columns": ["pressure", "position", "irrigationtime", "speed",
                        "theoreticalmaxspeed"],
        "entity_type": "IrrigationPivot",
        "domain": "riego mecanizado",
    },
    "cda-export (22).csv": {
        "name": "Previsión Meteorológica Agrícola",
        "category": "iot",
        "description": "Datos de previsión meteorológica para agricultura: precipitación, "
                       "humedad, temperatura, viento, radiación, evapotranspiración, "
                       "probabilidad de precipitación. 666 registros. "
                       "Entidad FIWARE: AgroWeatherForecast.",
        "key_columns": ["temperature", "relativehumidity", "precipitation", "windspeed",
                        "solarradiation", "evapotranspiration", "precipitationprobability"],
        "entity_type": "AgroWeatherForecast",
        "domain": "meteorología agrícola / predicción",
    },
    "cda-export (23).csv": {
        "name": "Parcelas de Riego (Kc / raíz)",
        "category": "iot",
        "description": "Datos de parcelas con coeficiente de cultivo (Kc), profundidad radicular, "
                       "balance hídrico, eficiencia de riego, índice de estrés. 785 registros. "
                       "Cultivos: Maíz. Entidad FIWARE: AgriParcel.",
        "key_columns": ["cropcoefficient", "rootdepth", "irrigation",
                        "irrigationefficiency", "waterstressindex", "area",
                        "soiltexturetype", "croptype"],
        "entity_type": "AgriParcel",
        "domain": "riego de precisión",
    },
}

# Skip duplicates: (2)=(7), (3)=(6), (4)=(10)
SKIP_FILES = {"cda-export (2).csv", "cda-export (3).csv",
              "cda-export (4).csv", "cda-export (6).csv", "cda-export (7).csv"}


def read_csv_stats(filepath: Path, info: dict) -> dict:
    """Read a CDA CSV and compute statistics for key columns."""
    stats = {
        "filename": filepath.name,
        "name": info["name"],
        "entity_type": info["entity_type"],
        "domain": info["domain"],
        "total_rows": 0,
        "date_range": {"min": None, "max": None},
        "columns": {},
        "sample_entities": set(),
        "sample_rows": [],
    }

    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter=";")
            headers = reader.fieldnames or []
            stats["all_columns"] = headers

            numeric_data = defaultdict(list)
            categorical_data = defaultdict(lambda: defaultdict(int))
            row_count = 0
            dates = []

            for row in reader:
                row_count += 1

                # Sample first 5 rows
                if row_count <= 5:
                    stats["sample_rows"].append(dict(row))

                # Timestamps
                ts = row.get("timeinstant", "")
                if ts and len(ts) >= 10:
                    try:
                        dates.append(ts[:19])
                    except:
                        pass

                # Entity IDs (sample)
                eid = row.get("entityid", row.get('"entityid"', ""))
                if eid and len(stats["sample_entities"]) < 20:
                    stats["sample_entities"].add(eid.strip('"'))

                # Key columns
                for col in info.get("key_columns", []):
                    val = row.get(col, "")
                    if val is None or val == "":
                        continue
                    try:
                        numeric_data[col].append(float(val))
                    except (ValueError, TypeError):
                        categorical_data[col][str(val)[:50]] += 1

            stats["total_rows"] = row_count

            # Date range
            if dates:
                dates_sorted = sorted(dates)
                stats["date_range"] = {"min": dates_sorted[0], "max": dates_sorted[-1]}

            # Numeric stats
            for col, values in numeric_data.items():
                if not values:
                    continue
                values_sorted = sorted(values)
                n = len(values)
                stats["columns"][col] = {
                    "type": "numeric",
                    "count": n,
                    "min": round(values_sorted[0], 2),
                    "max": round(values_sorted[-1], 2),
                    "mean": round(sum(values) / n, 2),
                    "median": round(values_sorted[n // 2], 2),
                    "p5": round(values_sorted[int(n * 0.05)], 2),
                    "p95": round(values_sorted[int(n * 0.95)], 2),
                }

            # Categorical stats
            for col, counts in categorical_data.items():
                top_5 = sorted(counts.items(), key=lambda x: -x[1])[:5]
                stats["columns"][col] = {
                    "type": "categorical",
                    "unique_values": len(counts),
                    "top_5": dict(top_5),
                    "total_counted": sum(counts.values()),
                }

            stats["sample_entities"] = list(stats["sample_entities"])

    except Exception as e:
        print(f"  ERROR leyendo {filepath.name}: {e}")
        stats["error"] = str(e)

    return stats


def format_stats_for_prompt(stats: dict, info: dict) -> str:
    """Format dataset statistics into a readable context for QA generation."""
    parts = []
    parts.append(f"## Dataset: {info['name']}")
    parts.append(f"- **Descripción**: {info['description']}")
    parts.append(f"- **Entidad FIWARE**: {stats['entity_type']}")
    parts.append(f"- **Dominio**: {stats['domain']}")
    parts.append(f"- **Total registros**: {stats['total_rows']:,}")

    if stats["date_range"]["min"]:
        parts.append(f"- **Período**: {stats['date_range']['min'][:10]} a {stats['date_range']['max'][:10]}")

    if stats["sample_entities"]:
        parts.append(f"- **Entidades de ejemplo**: {', '.join(stats['sample_entities'][:10])}")

    if stats["columns"]:
        parts.append("\n### Estadísticas de Variables Clave:")
        for col, cstats in stats["columns"].items():
            if cstats["type"] == "numeric":
                parts.append(
                    f"  - **{col}**: min={cstats['min']}, max={cstats['max']}, "
                    f"media={cstats['mean']}, mediana={cstats['median']}, "
                    f"P5={cstats['p5']}, P95={cstats['p95']} "
                    f"({cstats['count']:,} valores válidos)"
                )
            else:
                top_str = ", ".join(
                    f"{k}: {v}" for k, v in list(cstats["top_5"].items())[:5]
                )
                parts.append(
                    f"  - **{col}**: {cstats['unique_values']} valores únicos. "
                    f"Top: {top_str}"
                )

    # Sample rows
    if stats["sample_rows"]:
        parts.append("\n### Registros de ejemplo:")
        for i, row in enumerate(stats["sample_rows"][:3]):
            # Keep only non-empty fields
            clean = {k: v for k, v in row.items() if v and v.strip()}
            parts.append(f"  Registro {i+1}: {json.dumps(clean, ensure_ascii=False)[:300]}")

    return "\n".join(parts)


def generate_qa_from_cda(context: str, dataset_name: str, domain: str,
                         entity_type: str, n_pairs: int = 5) -> list[dict]:
    """Generate Q&A pairs from CDA dataset statistics using Ollama."""
    prompt = f"""Eres un generador de datos de entrenamiento para Seedy, un asistente agrotech de NeoFarm que trabaja con plataformas FIWARE e IoT agrícola.

CONTEXTO — Datos reales CDA (Context Data Acquisition):
---
{context[:4000]}
---

INSTRUCCIONES:
Genera exactamente {n_pairs} pares pregunta-respuesta en español basados ESTRICTAMENTE en los datos anteriores.

TIPOS DE PREGUNTAS A GENERAR:
1. **Interpretación de datos**: "¿Qué significan los valores de [variable] en [rango]?"
2. **Umbrales y alertas**: "¿Cuándo debería activarse una alerta en [variable]?"
3. **Patrones temporales**: "¿Qué patrones se observan en los datos de [dataset]?"
4. **FIWARE/IoT**: "¿Cómo funciona la entidad {entity_type} en una plataforma FIWARE?"
5. **Recomendaciones prácticas**: "¿Qué acciones recomiendas cuando [condición]?"
6. **Comparativas**: "¿Cómo se comparan los valores de [variable] con rangos normales?"
7. **Integración de datos**: "¿Cómo se relacionan los datos de [dataset] con otros sensores?"

REGLAS CRÍTICAS:
1. Usa SOLO los datos estadísticos proporcionados. NO inventes valores.
2. Menciona rangos reales (min, max, media, percentiles) del contexto.
3. Incluye el tipo de entidad FIWARE ({entity_type}) cuando sea relevante.
4. Las respuestas deben tener 100-400 palabras, con datos técnicos concretos.
5. Explica la relevancia agrotécnica de los datos.
6. Referencia la plataforma NeoFarm/CDA cuando sea natural.

FORMATO DE SALIDA (JSON array, sin texto adicional):
[
  {{"pregunta": "...", "respuesta": "..."}},
  {{"pregunta": "...", "respuesta": "..."}}
]

Genera SOLO el JSON array, sin explicaciones ni markdown."""

    try:
        resp = httpx.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_predict": 6000,
                    "num_ctx": 8192,
                },
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")

        # Parse JSON
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            pairs = json.loads(match.group())
        else:
            return []

        results = []
        for pair in pairs:
            q = pair.get("pregunta", "").strip()
            a = pair.get("respuesta", "").strip()
            if q and a and len(a) > 80:
                results.append({"user": q, "assistant": a})

        return results

    except Exception as e:
        print(f"    ERROR generando Q&A: {e}")
        return []


def generate_cross_dataset_qa(all_stats: dict) -> list[dict]:
    """Generate Q&As that connect multiple datasets (integración)."""
    # Build a summary of all datasets
    summary_parts = []
    for fname, stats in all_stats.items():
        info = CDA_DATASETS.get(fname, {})
        name = info.get("name", fname)
        summary_parts.append(
            f"- **{name}** ({stats.get('entity_type', '?')}): "
            f"{stats['total_rows']:,} registros, dominio {stats.get('domain', '?')}"
        )
        # Key stats
        for col, cs in list(stats.get("columns", {}).items())[:3]:
            if cs["type"] == "numeric":
                summary_parts.append(
                    f"  - {col}: media={cs['mean']}, rango [{cs['min']}, {cs['max']}]"
                )

    context = f"""## Plataforma CDA NeoFarm — Resumen de todas las fuentes de datos IoT

La plataforma CDA (Context Data Acquisition) de NeoFarm integra múltiples fuentes
de datos en tiempo real usando el estándar FIWARE NGSI-v2. Los datasets disponibles son:

{chr(10).join(summary_parts)}

### Entidades FIWARE en la plataforma:
- Animal: tracking de vacuno extensivo (actividad, celos, partos, geofencing)
- Silo: silos de pienso (nivel, temperatura, humedad)
- Feeder: comederos inteligentes (visitas, nivel, vaciado)
- SoilObserved: sensores de suelo (humedad por capas, temperatura, potencial hídrico)
- AgriParcel: parcelas agrícolas (cultivo, Kc, riego, suelo)
- AgroWeatherObserved: estaciones meteorológicas (precipitación, viento, radiación)
- AgroWeatherForecast: previsión meteorológica
- AgroPlagueObserved: monitorización de plagas (conteos por familia entomológica)
- IrrigationRecommendation: recomendaciones automáticas de riego
- IrrigationPivot: pivotes de riego mecanizado
"""

    prompt = f"""Eres un generador de datos de entrenamiento para Seedy, asistente agrotech de NeoFarm.

{context}

INSTRUCCIONES:
Genera exactamente 10 pares pregunta-respuesta en español que INTEGREN múltiples datasets.

EJEMPLOS DE TEMAS:
1. ¿Cómo se relacionan los datos de suelo con las recomendaciones de riego?
2. ¿Cómo afecta la meteorología a la planificación de fertilización NPK?
3. ¿Qué visión general ofrece la plataforma CDA de NeoFarm?
4. ¿Cómo se usa FIWARE NGSI-v2 para integrar sensores heterogéneos?
5. ¿Qué alertas cruzadas se pueden configurar combinando datos de animales y meteorología?
6. ¿Cómo funciona un Digital Twin agrícola con estos datos CDA?
7. ¿Qué KPIs de sostenibilidad se pueden calcular con los datos disponibles?
8. ¿Cómo se integra la monitorización de plagas con la previsión meteorológica?

REGLAS:
1. Respuestas de 150-400 palabras, técnicas y con datos reales del contexto.
2. Menciona entidades FIWARE, tipos de sensores y rangos estadísticos reales.
3. Referencia NeoFarm y la arquitectura CDA/FIWARE.

FORMATO (JSON array):
[{{"pregunta": "...", "respuesta": "..."}}]

Genera SOLO el JSON array."""

    return generate_qa_from_cda(
        context + "\n" + prompt.split("INSTRUCCIONES:")[1],
        "Cross-Dataset CDA", "integración", "Multi-Entity",
        n_pairs=10
    )


def make_example(user_msg: str, assistant_msg: str) -> dict:
    """Format as SFT training example."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed_datasets": [], "generated_count": 0}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


def main():
    print("=" * 70)
    print("BUILD DATASET CDA — Q&As desde datos IoT FIWARE reales")
    print("=" * 70)

    progress = load_progress()
    all_stats = {}
    total_qa = 0

    # Open output file in append mode
    mode = "a" if progress["generated_count"] > 0 else "w"
    outf = open(OUT_FILE, mode, encoding="utf-8")

    print(f"\n📊 Analizando {len(CDA_DATASETS)} datasets CDA...")
    start_time = time.time()

    for fname, info in sorted(CDA_DATASETS.items()):
        filepath = CDA_DIR / fname
        if not filepath.exists():
            print(f"  ⚠️  {fname} no encontrado, saltando...")
            continue

        if fname in progress["processed_datasets"]:
            print(f"  ⏭️  {fname} ya procesado, saltando...")
            continue

        print(f"\n{'─' * 50}")
        print(f"📂 {info['name']} ({fname})")
        print(f"   Dominio: {info['domain']}")

        # 1. Read and compute statistics
        print("   Leyendo CSV y calculando estadísticas...")
        stats = read_csv_stats(filepath, info)
        all_stats[fname] = stats

        if "error" in stats:
            print(f"   ❌ Error: {stats['error']}")
            continue

        print(f"   📊 {stats['total_rows']:,} registros, "
              f"{len(stats['columns'])} variables analizadas")
        if stats["date_range"]["min"]:
            print(f"   📅 Período: {stats['date_range']['min'][:10]} → "
                  f"{stats['date_range']['max'][:10]}")

        # 2. Generate Q&As
        context = format_stats_for_prompt(stats, info)

        # Determine number of Q&As based on dataset size/importance
        if stats["total_rows"] > 50000:
            n_pairs = 8
        elif stats["total_rows"] > 5000:
            n_pairs = 6
        elif stats["total_rows"] > 500:
            n_pairs = 5
        else:
            n_pairs = 4

        print(f"   🤖 Generando {n_pairs} Q&As con {MODEL}...")
        qa_pairs = generate_qa_from_cda(
            context, info["name"], info["domain"],
            info["entity_type"], n_pairs=n_pairs
        )

        print(f"   ✅ {len(qa_pairs)} Q&As generados")

        # Write immediately
        for pair in qa_pairs:
            example = make_example(pair["user"], pair["assistant"])
            outf.write(json.dumps(example, ensure_ascii=False) + "\n")
            total_qa += 1

        # Update progress
        progress["processed_datasets"].append(fname)
        progress["generated_count"] += len(qa_pairs)
        save_progress(progress)

        # Brief pause between API calls
        time.sleep(2)

    # 3. Generate cross-dataset integration Q&As
    if "cross_dataset" not in progress["processed_datasets"] and all_stats:
        print(f"\n{'─' * 50}")
        print(f"🔗 Generando Q&As de integración cross-dataset...")

        # Rebuild all_stats for any previously processed datasets
        for fname, info in CDA_DATASETS.items():
            if fname not in all_stats:
                filepath = CDA_DIR / fname
                if filepath.exists():
                    stats = read_csv_stats(filepath, info)
                    all_stats[fname] = stats

        cross_qa = generate_cross_dataset_qa(all_stats)
        print(f"   ✅ {len(cross_qa)} Q&As de integración generados")

        for pair in cross_qa:
            example = make_example(pair["user"], pair["assistant"])
            outf.write(json.dumps(example, ensure_ascii=False) + "\n")
            total_qa += 1

        progress["processed_datasets"].append("cross_dataset")
        progress["generated_count"] += len(cross_qa)
        save_progress(progress)

    outf.close()

    elapsed = time.time() - start_time
    total_in_file = sum(1 for _ in open(OUT_FILE))
    print(f"\n{'=' * 70}")
    print(f"✅ COMPLETADO en {elapsed/60:.1f} min")
    print(f"   Total Q&As generados esta sesión: {total_qa}")
    print(f"   Total Q&As en archivo: {total_in_file}")
    print(f"   Archivo: {OUT_FILE}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
