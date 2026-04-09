"""Limpieza quirúrgica de contenido en inglés de colecciones Qdrant.

Estrategia:
- AGRESIVA (avicultura, iot_hardware, avicultura_intensiva): eliminar TODO chunk EN puro
- MODERADA (digital_twins, geotwin, bodegas_vino, nutricion): eliminar EN con quality_score < 0.6
- LEVE (genetica, estrategia): solo eliminar EN sin keywords del dominio
- PROTEGER: normativa (ya 93% ES), fresh_web (temporal por diseño)

Ejecutar: python3 scripts/cleanup_english.py [--dry-run]
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Añadir el directorio padre al path para importar servicios
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient
from services.quality_gate import detect_language

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

QDRANT_HOST = "qdrant"
QDRANT_PORT = 6333
BATCH_SIZE = 100  # Scroll batch

# ── Estrategias por colección ──

AGGRESSIVE = {
    "avicultura", "iot_hardware", "avicultura_intensiva",
}

MODERATE = {
    "digital_twins", "geotwin", "bodegas_vino", "nutricion",
}

LIGHT = {
    "genetica", "estrategia",
}

# Keywords de alto valor que evitan borrado incluso en modo agresivo
# (papers directamente relevantes para Seedy)
_KEEP_EN_IF_CONTAINS = {
    "avicultura": [
        "capon", "capons", "caponiz", "free-range", "free range",
        "heritage breed", "slow-growing", "pastured poultry",
        "bresse", "malines", "mechelen", "sulmtaler", "sussex",
        "castellana negra", "pita pinta", "araucana", "vorwerk",
    ],
    "iot_hardware": [
        "mqtt", "lora", "lorawan", "esp32", "zigbee",
        "precision livestock", "poultry monitoring", "smart farm",
        "influxdb", "grafana", "node-red",
    ],
    "avicultura_intensiva": [
        "capon", "capons", "free-range", "heritage",
    ],
    "digital_twins": [
        "digital twin", "cesium", "3d tiles", "bim",
        "ndvi", "sentinel", "precision agriculture",
    ],
    "geotwin": [
        "cesium", "3d tiles", "terrain", "pnoa", "ortho",
        "digital twin", "gis",
    ],
    "bodegas_vino": [
        "terroir", "viticulture", "enology", "winery",
        "denominación", "ribera", "rioja", "priorat",
    ],
    "nutricion": [
        "poultry nutrition", "feed formulation", "amino acid",
        "broiler diet", "layer nutrition", "metabolizable energy",
    ],
    "genetica": [
        "blup", "genomic selection", "heritability", "qtl",
        "snp", "breeding value", "heterosis", "inbreeding",
        "poultry genetic", "avian genom",
    ],
    "estrategia": [
        "precision livestock", "smart farming", "agritech",
        "pepac", "pac ", "rural development",
    ],
}


def should_delete(text: str, collection: str, lang: str, confidence: float) -> tuple[bool, str]:
    """
    Decide si un chunk debe eliminarse.

    Returns:
        (delete, reason)
    """
    # Solo eliminar chunks detectados como inglés
    if lang != "en":
        return False, "not-english"

    # Confianza muy baja → no borrar (podría ser mixed/bilingüe)
    if confidence < 0.05:
        return False, "low-confidence"

    text_lower = text.lower()

    # Comprobar keywords protegidas
    keep_keywords = _KEEP_EN_IF_CONTAINS.get(collection, [])
    for kw in keep_keywords:
        if kw in text_lower:
            return False, f"protected-keyword:{kw}"

    # Decisión según estrategia
    if collection in AGGRESSIVE:
        return True, "aggressive-en-removal"

    if collection in MODERATE:
        # En moderado, borrar solo si no aporta keywords del dominio
        # (los keywords protegidos ya los filtró arriba)
        if len(text.strip()) < 300:
            return True, "moderate-short-en"
        return True, "moderate-en-removal"

    if collection in LIGHT:
        # En leve, solo borrar chunks cortos o sin relevancia
        if len(text.strip()) < 200:
            return True, "light-short-en"
        return False, "light-keep"

    return False, "unknown-collection"


def cleanup_collection(client: QdrantClient, collection: str, dry_run: bool = True) -> dict:
    """Limpia una colección de chunks en inglés."""
    stats = {"total": 0, "scanned": 0, "to_delete": 0, "kept_by_keyword": 0, "deleted": 0}

    info = client.get_collection(collection)
    stats["total"] = info.points_count
    logger.info(f"[{collection}] Total: {stats['total']:,} chunks")

    ids_to_delete = []
    offset = None

    while True:
        scroll_result = client.scroll(
            collection_name=collection,
            limit=BATCH_SIZE,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )

        points, next_offset = scroll_result
        if not points:
            break

        for point in points:
            stats["scanned"] += 1
            text = point.payload.get("text", "")
            lang, conf = detect_language(text)

            delete, reason = should_delete(text, collection, lang, conf)

            if delete:
                ids_to_delete.append(point.id)
                stats["to_delete"] += 1
            elif "protected-keyword" in reason:
                stats["kept_by_keyword"] += 1

        offset = next_offset
        if offset is None:
            break

        # Log progreso cada 1000
        if stats["scanned"] % 1000 == 0:
            logger.info(
                f"  [{collection}] Escaneados: {stats['scanned']:,}, "
                f"a eliminar: {stats['to_delete']:,}"
            )

    logger.info(
        f"[{collection}] Scan completo: {stats['scanned']:,} escaneados, "
        f"{stats['to_delete']:,} a eliminar, "
        f"{stats['kept_by_keyword']:,} protegidos por keyword"
    )

    if not dry_run and ids_to_delete:
        # Borrar en lotes de 500
        for i in range(0, len(ids_to_delete), 500):
            batch = ids_to_delete[i:i+500]
            client.delete(
                collection_name=collection,
                points_selector=batch,
            )
            stats["deleted"] += len(batch)
            logger.info(
                f"  [{collection}] Eliminados {stats['deleted']:,}/{stats['to_delete']:,}"
            )
    elif dry_run:
        logger.info(f"  [{collection}] DRY RUN — no se eliminaron chunks")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Limpieza de chunks en inglés de Qdrant")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Solo mostrar qué se borraría (default: True)")
    parser.add_argument("--execute", action="store_true",
                        help="Ejecutar borrado real (override dry-run)")
    parser.add_argument("--collections", nargs="+", default=None,
                        help="Colecciones específicas (default: todas)")
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        logger.info("=" * 60)
        logger.info("  MODO DRY RUN — no se eliminará nada")
        logger.info("  Usa --execute para borrado real")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("  ⚠️  MODO EJECUCIÓN — se eliminarán chunks")
        logger.info("=" * 60)

    client = QdrantClient(QDRANT_HOST, port=QDRANT_PORT)

    all_collections = list(AGGRESSIVE | MODERATE | LIGHT)
    targets = args.collections or sorted(all_collections)

    total_stats = {"total": 0, "scanned": 0, "to_delete": 0, "kept_by_keyword": 0, "deleted": 0}

    for col in targets:
        if col not in all_collections:
            logger.warning(f"Colección '{col}' no está en la lista de limpieza, saltando")
            continue

        stats = cleanup_collection(client, col, dry_run=dry_run)

        for k in total_stats:
            total_stats[k] += stats[k]

        print()

    logger.info("=" * 60)
    logger.info(f"  RESUMEN:")
    logger.info(f"    Escaneados: {total_stats['scanned']:,}")
    logger.info(f"    A eliminar: {total_stats['to_delete']:,}")
    logger.info(f"    Protegidos por keyword: {total_stats['kept_by_keyword']:,}")
    if not dry_run:
        logger.info(f"    Eliminados: {total_stats['deleted']:,}")
    else:
        logger.info(f"    (dry run — sin borrado)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
