"""Seedy Backend — Knowledge Agent: agente autónomo de adquisición de conocimiento.

Complementa al daily_update.py con capacidades más inteligentes:

1. **Gap Detection**: Analiza cada colección para identificar temas débiles
   (pocas fuentes, baja diversidad, falta de datos concretos).

2. **Targeted Search**: Genera queries específicas para cubrir los gaps
   detectados, buscando en SearXNG con prioridad en fuentes de alta autoridad.

3. **Promote from Fresh**: Analiza chunks en fresh_web con score alto y los
   promueve a la colección temática que corresponda (esto es lo que daily_update
   NO hace — solo mete todo en fresh_web y ahí se queda).

4. **Quality Audit**: Revisa chunks existentes en colecciones principales
   y marca los de baja calidad para limpieza.

Ciclo de ejecución: cada 12h (configurable), como asyncio task.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from collections import Counter

logger = logging.getLogger(__name__)

# ── Configuración ──

AGENT_INTERVAL = int(os.environ.get("KNOWLEDGE_AGENT_INTERVAL", 12 * 3600))  # 12h
MAX_QUERIES_PER_RUN = int(os.environ.get("KNOWLEDGE_AGENT_MAX_QUERIES", 15))
PROMOTE_MIN_AUTHORITY = 0.6
PROMOTE_MIN_TEXT_LEN = 200

DATA_DIR = Path("/app/data") if Path("/app/data").exists() else Path("data")
REPORT_DIR = DATA_DIR / "knowledge_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Mapa de topics → colecciones ──

TOPIC_COLLECTION_MAP = {
    "avicultura": "avicultura",
    "porcino": "estrategia",           # porcino va a estrategia (no tiene colección propia)
    "bovino": "estrategia",
    "normativa": "normativa",
    "genetica": "genetica",
    "iot_sensores": "iot_hardware",
    "nutricion": "nutricion",
    "digital_twins": "digital_twins",
    "geotwin": "geotwin",
}

# ── Gaps conocidos por vertical (se actualiza en cada run) ──

_KNOWN_GAPS = {
    "avicultura": [
        "razas autóctonas españolas datos concretos peso producción",
        "capones producción extensiva calidad carne estudios",
        "Malines características productivas peso engorde",
        "Bresse Gauloise estándar peso producción extensiva",
        "Sulmtaler raza austriaca características cría extensiva",
        "manejo gallineros extensivos densidad ventilación",
        "incubación natural razas pesadas protocolo",
    ],
    "genetica": [
        "BLUP avícola evaluación genética aves reproductores",
        "consanguinidad razas autóctonas gestión genética",
        "heterosis cruces F1 aves carne tabla datos",
        "selección genómica avicultura extensiva marcadores",
        "programa mejora genética capones líneas paternas maternas",
    ],
    "nutricion": [
        "formulación pienso capones engorde fases",
        "necesidades nutricionales aves extensivas pastoreo",
        "cereales locales alimentación avícola extensiva España",
        "coste alimentación avicultura extensiva rentabilidad",
    ],
    "iot_hardware": [
        "sensores temperatura humedad gallinero LoRa ESP32",
        "monitorización avícola IoT cámaras peso automático",
        "MQTT broker ganadería arquitectura sistema",
        "alertas automáticas amoniaco CO2 gallinero",
    ],
    "normativa": [
        "Real Decreto 306/2020 bienestar animal avicultura",
        "ECOGAN registro bienestar animal España",
        "normativa europea bienestar aves corral 2024 2025",
        "densidad máxima aves extensivas normativa España",
    ],
    "digital_twins": [
        "gemelo digital explotación ganadera arquitectura",
        "BIM ganadería modelado 3D granja",
        "NDVI Sentinel-2 pastos ganadería extensiva",
    ],
}


# ═══════════════════════════════════════════════════════
# 1. Gap Detection — analiza Qdrant para detectar debilidades
# ═══════════════════════════════════════════════════════


async def detect_gaps(collection: str, sample_size: int = 100) -> list[dict]:
    """
    Analiza una colección de Qdrant y detecta gaps temáticos.

    Returns:
        Lista de gaps: [{"topic": str, "score": float, "reason": str}]
    """
    from services.rag import get_qdrant

    client = get_qdrant()
    gaps = []

    try:
        info = client.get_collection(collection)
        total_points = info.points_count

        if total_points == 0:
            gaps.append({
                "topic": collection,
                "score": 0.0,
                "reason": "Colección vacía",
            })
            return gaps

        # Muestra aleatoria de chunks para análisis
        sample = client.scroll(
            collection_name=collection,
            limit=sample_size,
            with_payload=True,
            with_vectors=False,
        )

        texts = [p.payload.get("text", "") for p in sample[0]]
        sources = [p.payload.get("source_file", "") for p in sample[0]]

        # Análisis de diversidad de fuentes
        unique_sources = set(sources)
        source_diversity = len(unique_sources) / max(1, len(sources))

        if source_diversity < 0.3:
            gaps.append({
                "topic": f"{collection}/diversidad_fuentes",
                "score": source_diversity,
                "reason": f"Baja diversidad: {len(unique_sources)} fuentes únicas en {len(sources)} chunks",
            })

        # Análisis de idioma dominante
        from services.quality_gate import detect_language
        lang_counts: dict[str, int] = Counter()
        for text in texts:
            lang, conf = detect_language(text)
            if conf > 0.03:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

        en_ratio = lang_counts.get("en", 0) / max(1, sum(lang_counts.values()))
        if en_ratio > 0.4 and collection not in ("fresh_web",):
            gaps.append({
                "topic": f"{collection}/exceso_ingles",
                "score": en_ratio,
                "reason": f"{en_ratio:.0%} del contenido en inglés (debería ser <40%)",
            })

        # Longitud promedio de chunks (muy cortos = baja información)
        avg_len = sum(len(t) for t in texts) / max(1, len(texts))
        if avg_len < 200:
            gaps.append({
                "topic": f"{collection}/chunks_cortos",
                "score": avg_len / 500,
                "reason": f"Longitud media: {avg_len:.0f} chars (recomendado: >500)",
            })

    except Exception as e:
        logger.error(f"[KnowledgeAgent] Error analizando {collection}: {e}")

    return gaps


# ═══════════════════════════════════════════════════════
# 2. Targeted Search — busca contenido para cubrir gaps
# ═══════════════════════════════════════════════════════


async def search_for_gap(gap_query: str, topic: str) -> list[dict]:
    """
    Busca contenido para cubrir un gap específico vía SearXNG.
    Devuelve resultados filtrados por autoridad y relevancia.
    """
    from services.daily_update import (
        search_searxng, filter_results, get_source_authority, get_domain,
    )

    try:
        raw_results = await search_searxng(gap_query, max_results=10)

        if not raw_results:
            return []

        # Enriquecer con autoridad
        for r in raw_results:
            r["source_authority"] = get_source_authority(r.get("url", ""))
            r["domain"] = get_domain(r.get("url", ""))

        # Filtrar y deduplicar (min_authority=0.3 por defecto)
        filtered = filter_results(raw_results)

        # Priorizar por autoridad
        filtered.sort(key=lambda x: x.get("source_authority", 0), reverse=True)

        logger.info(
            f"[KnowledgeAgent] Búsqueda '{gap_query[:50]}': "
            f"{len(filtered)}/{len(raw_results)} resultados válidos"
        )
        return filtered[:5]  # Top 5 por query

    except Exception as e:
        logger.error(f"[KnowledgeAgent] Error buscando '{gap_query[:40]}': {e}")
        return []


# ═══════════════════════════════════════════════════════
# 3. Promote from Fresh — promueve chunks buenos a colecciones principales
# ═══════════════════════════════════════════════════════


async def promote_from_fresh_web(
    min_authority: float = PROMOTE_MIN_AUTHORITY,
    max_promote: int = 50,
) -> dict:
    """
    Revisa fresh_web y promueve chunks de alta calidad a sus colecciones temáticas.

    Criterios:
    - source_authority >= 0.6
    - text length >= 200
    - topic mapeado a una colección principal
    - Pasa quality_gate para la colección destino

    Returns:
        {"promoted": int, "by_collection": dict, "skipped": int}
    """
    from services.rag import get_qdrant, FRESH_WEB_COLLECTION
    from services.embeddings import embed_texts
    from services.quality_gate import validate_chunk
    from ingestion.chunker import compute_sparse_vector
    from qdrant_client.models import PointStruct, SparseVector, Filter, FieldCondition, Range

    client = get_qdrant()
    promoted = 0
    skipped = 0
    by_collection: dict[str, int] = {}

    try:
        # Buscar chunks de alta autoridad en fresh_web
        results = client.scroll(
            collection_name=FRESH_WEB_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_authority",
                        range=Range(gte=min_authority),
                    ),
                ],
            ),
            limit=max_promote * 2,  # Margen para rechazos por quality gate
            with_payload=True,
            with_vectors=True,
        )

        candidates = results[0]
        if not candidates:
            logger.info("[KnowledgeAgent] No hay candidatos para promoción en fresh_web")
            return {"promoted": 0, "by_collection": {}, "skipped": 0}

        logger.info(f"[KnowledgeAgent] {len(candidates)} candidatos para promoción")

        for point in candidates:
            if promoted >= max_promote:
                break

            payload = point.payload or {}
            text = payload.get("text", "")
            topic = payload.get("topic", "")
            authority = payload.get("source_authority", 0)

            # Determinar colección destino
            target_col = TOPIC_COLLECTION_MAP.get(topic)
            if not target_col:
                skipped += 1
                continue

            # Longitud mínima
            if len(text.strip()) < PROMOTE_MIN_TEXT_LEN:
                skipped += 1
                continue

            # Quality gate para la colección destino
            passed, score, reasons = validate_chunk(text, target_col)
            if not passed:
                skipped += 1
                continue

            # Crear punto en la colección destino
            # Reutilizar el vector existente (ya está embeddido)
            vector_data = point.vector
            if isinstance(vector_data, dict) and "dense" in vector_data:
                new_vector = vector_data
            elif isinstance(vector_data, list):
                new_vector = {"dense": vector_data}
            else:
                # Necesita re-embed
                try:
                    embs = await embed_texts([text])
                    new_vector = {"dense": embs[0]}
                    sparse_idx, sparse_val = compute_sparse_vector(text)
                    if sparse_idx:
                        new_vector["bm25"] = SparseVector(
                            indices=sparse_idx, values=sparse_val
                        )
                except Exception:
                    skipped += 1
                    continue

            point_id = str(uuid5(NAMESPACE_URL, f"promoted:{payload.get('content_hash', text[:100])}"))

            new_payload = {
                **payload,
                "collection": target_col,
                "promoted_from": "fresh_web",
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "quality_score": score,
            }

            try:
                client.upsert(
                    collection_name=target_col,
                    points=[PointStruct(id=point_id, vector=new_vector, payload=new_payload)],
                )
                promoted += 1
                by_collection[target_col] = by_collection.get(target_col, 0) + 1
            except Exception as e:
                logger.error(f"[KnowledgeAgent] Error promoviendo a {target_col}: {e}")
                skipped += 1

    except Exception as e:
        logger.error(f"[KnowledgeAgent] Error en promote_from_fresh_web: {e}", exc_info=True)

    logger.info(
        f"[KnowledgeAgent] Promoción: {promoted} chunks promovidos, "
        f"{skipped} saltados. Por colección: {by_collection}"
    )
    return {"promoted": promoted, "by_collection": by_collection, "skipped": skipped}


# ═══════════════════════════════════════════════════════
# 4. Index Gap Results — indexa resultados de búsqueda de gaps
# ═══════════════════════════════════════════════════════


async def index_gap_results(
    results: list[dict],
    target_collection: str,
    topic: str,
) -> int:
    """
    Indexa resultados de búsqueda en la colección destino (no en fresh_web).
    Solo contenido que pasa el quality gate.
    """
    from services.rag import get_qdrant
    from services.embeddings import embed_texts
    from services.quality_gate import validate_chunk
    from services.daily_update import deep_crawl_url, content_hash, DEEP_CRAWL_MIN_AUTHORITY
    from ingestion.chunker import chunk_text, compute_sparse_vector
    from qdrant_client.models import PointStruct, SparseVector

    client = get_qdrant()
    indexed = 0

    for result in results:
        # Deep crawl si autoridad alta
        text = result.get("content", "")
        if result.get("source_authority", 0) >= DEEP_CRAWL_MIN_AUTHORITY:
            full_text = await deep_crawl_url(result["url"])
            if full_text and len(full_text) > len(text):
                text = full_text

        if not text or len(text.strip()) < 100:
            continue

        full_text = f"{result.get('title', '')}\n{text}"

        # Chunkear si es largo
        if len(full_text) > 1200:
            chunks = chunk_text(full_text, chunk_size=1000, overlap=200)
        else:
            chunks = [full_text]

        for i, chunk in enumerate(chunks):
            # Quality gate
            passed, score, reasons = validate_chunk(chunk, target_collection)
            if not passed:
                continue

            try:
                embs = await embed_texts([chunk])
                c_hash = content_hash(chunk)
                point_id = str(uuid5(NAMESPACE_URL, f"gap:{c_hash}"))

                vector_data: dict = {"dense": embs[0]}
                sparse_idx, sparse_val = compute_sparse_vector(chunk)
                if sparse_idx:
                    vector_data["bm25"] = SparseVector(
                        indices=sparse_idx, values=sparse_val
                    )

                now = datetime.now(timezone.utc).isoformat()
                client.upsert(
                    collection_name=target_collection,
                    points=[PointStruct(
                        id=point_id,
                        vector=vector_data,
                        payload={
                            "text": chunk,
                            "source_file": result.get("domain", "unknown"),
                            "chunk_index": i,
                            "section": result.get("title", ""),
                            "collection": target_collection,
                            "document_type": "web",
                            "discovered_at": now,
                            "source_authority": result.get("source_authority", 0),
                            "topic": topic,
                            "domain": result.get("domain", ""),
                            "url": result.get("url", ""),
                            "content_hash": c_hash,
                            "quality_score": score,
                            "acquisition": "knowledge_agent",
                        },
                    )],
                )
                indexed += 1
            except Exception as e:
                logger.error(f"[KnowledgeAgent] Error indexando chunk: {e}")

    return indexed


# ═══════════════════════════════════════════════════════
# 5. Orchestrator — ejecuta el ciclo completo
# ═══════════════════════════════════════════════════════


async def run_knowledge_agent() -> dict:
    """
    Ejecuta un ciclo completo del agente de conocimiento:
    1. Detecta gaps en todas las colecciones
    2. Busca contenido para los gaps más críticos
    3. Indexa resultados con quality gate
    4. Promueve contenido bueno de fresh_web a colecciones principales
    5. Genera reporte

    Returns:
        Reporte con estadísticas del ciclo.
    """
    from services.rag import ALL_COLLECTIONS

    t0 = datetime.now(timezone.utc)
    logger.info("[KnowledgeAgent] ═══ Iniciando ciclo de adquisición de conocimiento ═══")

    report = {
        "started_at": t0.isoformat(),
        "gaps_detected": [],
        "searches_performed": 0,
        "chunks_indexed": 0,
        "chunks_promoted": 0,
        "errors": [],
    }

    # ── Paso 1: Detectar gaps ──
    all_gaps = []
    for col in ALL_COLLECTIONS:
        try:
            gaps = await detect_gaps(col)
            all_gaps.extend(gaps)
        except Exception as e:
            report["errors"].append(f"Gap detection {col}: {e}")

    report["gaps_detected"] = all_gaps
    logger.info(f"[KnowledgeAgent] {len(all_gaps)} gaps detectados")

    # ── Paso 2: Buscar contenido para gaps conocidos ──
    searches_done = 0
    total_indexed = 0

    for topic, gap_queries in _KNOWN_GAPS.items():
        if searches_done >= MAX_QUERIES_PER_RUN:
            break

        target_col = TOPIC_COLLECTION_MAP.get(topic, topic)

        for gap_query in gap_queries:
            if searches_done >= MAX_QUERIES_PER_RUN:
                break

            try:
                results = await search_for_gap(gap_query, topic)
                if results:
                    count = await index_gap_results(results, target_col, topic)
                    total_indexed += count
                    searches_done += 1
                    logger.info(
                        f"[KnowledgeAgent] Gap '{gap_query[:40]}' → "
                        f"{count} chunks indexados en {target_col}"
                    )
            except Exception as e:
                report["errors"].append(f"Search '{gap_query[:30]}': {e}")

            # Rate limiting
            await asyncio.sleep(2)

    report["searches_performed"] = searches_done
    report["chunks_indexed"] = total_indexed

    # ── Paso 3: Promover de fresh_web a colecciones principales ──
    try:
        promote_result = await promote_from_fresh_web()
        report["chunks_promoted"] = promote_result["promoted"]
        report["promote_by_collection"] = promote_result["by_collection"]
    except Exception as e:
        report["errors"].append(f"Promote: {e}")

    # ── Paso 4: Guardar reporte ──
    t1 = datetime.now(timezone.utc)
    report["finished_at"] = t1.isoformat()
    report["duration_seconds"] = (t1 - t0).total_seconds()

    report_path = REPORT_DIR / f"knowledge_agent_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        logger.info(f"[KnowledgeAgent] Reporte guardado: {report_path.name}")
    except Exception as e:
        logger.error(f"[KnowledgeAgent] Error guardando reporte: {e}")

    logger.info(
        f"[KnowledgeAgent] ═══ Ciclo completado en {report['duration_seconds']:.0f}s: "
        f"{total_indexed} indexados, {report.get('chunks_promoted', 0)} promovidos, "
        f"{len(report['errors'])} errores ═══"
    )

    return report


# ═══════════════════════════════════════════════════════
# 6. Loop asyncio — para auto_learn.py
# ═══════════════════════════════════════════════════════


async def knowledge_agent_loop():
    """Loop periódico del agente de conocimiento. Lanzar desde auto_learn.py."""
    # Esperar 30 min tras arranque (dejar que otros servicios se estabilicen)
    await asyncio.sleep(1800)
    logger.info(
        f"[KnowledgeAgent] Loop iniciado — intervalo={AGENT_INTERVAL // 3600}h"
    )

    while True:
        try:
            await run_knowledge_agent()
        except Exception as e:
            logger.error(f"[KnowledgeAgent] Error en ciclo: {e}", exc_info=True)

        await asyncio.sleep(AGENT_INTERVAL)
