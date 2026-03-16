#!/usr/bin/env python3
"""
Seedy — Script de ingestión local.

Ejecuta la indexación de documentos de conocimientos/ en Qdrant.
Apunta a los servicios Docker expuestos en localhost.

Uso:
    python run_ingest.py                          # Indexar todo
    python run_ingest.py --collection avicultura  # Solo avicultura
    python run_ingest.py --reset                  # Borrar y reindexar todo
    python run_ingest.py --reset --collection nutricion  # Reset + reindex una
    python run_ingest.py --dry-run                # Solo ver qué se indexaría

Requisitos:
    - Docker Compose corriendo (ollama + qdrant mínimo)
    - pip install qdrant-client httpx pydantic-settings
"""

import os
import sys

# Apuntar a servicios Docker en localhost
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("KNOWLEDGE_DIR", os.path.join(os.path.dirname(__file__), "conocimientos"))

# Añadir backend/ al path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

import asyncio


async def main():
    # Import here after path setup
    from ingestion.ingest import main as ingest_main
    await ingest_main()


if __name__ == "__main__":
    asyncio.run(main())
