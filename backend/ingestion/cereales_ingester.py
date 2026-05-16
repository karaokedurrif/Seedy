"""Seedy — Ingesta de precios de cereales desde Mercolleida, Lonja Segovia, MAPA."""

import logging
import re
import httpx
from datetime import datetime, timezone
from typing import Optional
from bs4 import BeautifulSoup

from services.rag import get_qdrant
from services.embeddings import embed_query
from ingestion.chunker import compute_sparse_vector

logger = logging.getLogger(__name__)

COLLECTION_NAME = "cereales_mercados"


async def ingest_mercolleida() -> int:
    """Ingesta precios de Mercolleida (Lleida).
    
    URL: https://www.mercolleida.cat/es/precios-cereales
    Parsea tabla HTML con precios actuales de trigo, maíz, cebada, etc.
    
    Returns:
        Número de registros ingestados.
    """
    url = "https://www.mercolleida.cat/es/precios-cereales"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error(f"[Mercolleida] Error descargando: {e}")
        return 0

    try:
        soup = BeautifulSoup(html, "html.parser")
        # Buscar tabla con precios (ajustar selector según estructura real)
        tables = soup.find_all("table")
        if not tables:
            logger.warning("[Mercolleida] No se encontró tabla de precios")
            return 0

        # Parsear filas (cereal | precio €/t | fecha)
        rows = []
        for table in tables:
            for row in table.find_all("tr")[1:]:  # Skip header
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    rows.append(cells)

        if not rows:
            logger.warning("[Mercolleida] No se parsearon filas de precios")
            return 0

        # Crear chunks de texto para ingestar
        chunks = []
        for cells in rows:
            cereal = cells[0] if len(cells) > 0 else "desconocido"
            precio = cells[1] if len(cells) > 1 else "N/A"
            # Normalizar texto
            text = f"Mercolleida: {cereal} a {precio} €/t"
            chunks.append({
                "text": text,
                "metadata": {
                    "source": "mercolleida",
                    "url": url,
                    "cereal": cereal,
                    "precio": precio,
                    "fecha_ingesta": datetime.now(timezone.utc).isoformat(),
                }
            })

        # Ingestar a Qdrant
        client = get_qdrant()
        points = []
        for i, chunk in enumerate(chunks):
            text = chunk["text"]
            dense_vec = embed_query(text)
            sparse_vec = compute_sparse_vector(text)
            point_id = hash(f"mercolleida_{i}_{datetime.now().isoformat()}") % (2**63)
            points.append({
                "id": point_id,
                "vector": {
                    "dense": dense_vec,
                    "bm25": sparse_vec,
                },
                "payload": {
                    "text": text,
                    **chunk["metadata"],
                },
            })

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"[Mercolleida] {len(chunks)} precios ingestados")
        return len(chunks)

    except Exception as e:
        logger.error(f"[Mercolleida] Error parseando: {e}", exc_info=True)
        return 0


async def ingest_lonja_segovia() -> int:
    """Ingesta precios de Lonja de Segovia.
    
    URL: https://www.lonjasegovia.es/precios
    Parsea tabla con precios semanales de cereales.
    
    Returns:
        Número de registros ingestados.
    """
    url = "https://www.lonjasegovia.es/precios"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error(f"[Lonja Segovia] Error descargando: {e}")
        return 0

    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            logger.warning("[Lonja Segovia] No se encontró tabla de precios")
            return 0

        rows = []
        for table in tables:
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    rows.append(cells)

        if not rows:
            logger.warning("[Lonja Segovia] No se parsearon filas")
            return 0

        chunks = []
        for cells in rows:
            cereal = cells[0] if len(cells) > 0 else "desconocido"
            precio = cells[1] if len(cells) > 1 else "N/A"
            text = f"Lonja Segovia: {cereal} a {precio} €/t"
            chunks.append({
                "text": text,
                "metadata": {
                    "source": "lonja_segovia",
                    "url": url,
                    "cereal": cereal,
                    "precio": precio,
                    "fecha_ingesta": datetime.now(timezone.utc).isoformat(),
                }
            })

        client = get_qdrant()
        points = []
        for i, chunk in enumerate(chunks):
            text = chunk["text"]
            dense_vec = embed_query(text)
            sparse_vec = compute_sparse_vector(text)
            point_id = hash(f"lonja_segovia_{i}_{datetime.now().isoformat()}") % (2**63)
            points.append({
                "id": point_id,
                "vector": {
                    "dense": dense_vec,
                    "bm25": sparse_vec,
                },
                "payload": {
                    "text": text,
                    **chunk["metadata"],
                },
            })

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"[Lonja Segovia] {len(chunks)} precios ingestados")
        return len(chunks)

    except Exception as e:
        logger.error(f"[Lonja Segovia] Error parseando: {e}", exc_info=True)
        return 0


async def ingest_mapa() -> int:
    """Ingesta datos de mercados de cereales del MAPA (Ministerio de Agricultura).
    
    URL: https://www.mapa.gob.es/es/agricultura/temas/comercio-exterior-y-mercados-agricolas/
    Típicamente archivos PDF semanales. Esta implementación es un placeholder.
    
    Returns:
        Número de registros ingestados.
    """
    # NOTA: MAPA publica PDFs semanales. Requiere parser PDF específico.
    # Por ahora, placeholder que retorna 0.
    logger.info("[MAPA] Ingesta no implementada (requiere parser PDF)")
    return 0


async def ingest_all_cereales() -> dict[str, int]:
    """Ingesta precios de todas las fuentes de cereales.
    
    Returns:
        {"mercolleida": N, "lonja_segovia": M, "mapa": K}
    """
    results = {}
    results["mercolleida"] = await ingest_mercolleida()
    results["lonja_segovia"] = await ingest_lonja_segovia()
    results["mapa"] = await ingest_mapa()
    total = sum(results.values())
    logger.info(f"[Cereales] Ingesta total: {total} registros ({results})")
    return results
