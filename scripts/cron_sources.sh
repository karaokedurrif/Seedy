#!/usr/bin/env bash
# Seedy — Cron para scraping periódico de fuentes externas
# 
# Descarga artículos científicos y webs agro, luego dispara ingestión vía API.
#
# Instalar:
#   crontab -e
#   # Artículos científicos: lunes a las 03:00
#   0 3 * * 1 /home/davidia/Documentos/Seedy/scripts/cron_sources.sh science >> /home/davidia/Documentos/Seedy/data/logs/cron_sources.log 2>&1
#   # Webs agro: miércoles y sábados a las 04:00
#   0 4 * * 3,6 /home/davidia/Documentos/Seedy/scripts/cron_sources.sh agro >> /home/davidia/Documentos/Seedy/data/logs/cron_sources.log 2>&1
#   # Trigger ingestión diaria: todos los días a las 06:00
#   0 6 * * * /home/davidia/Documentos/Seedy/scripts/cron_sources.sh ingest >> /home/davidia/Documentos/Seedy/data/logs/cron_sources.log 2>&1

set -euo pipefail

SEEDY_DIR="/home/davidia/Documentos/Seedy"
VENV="${SEEDY_DIR}/.venv/bin/python3"
BACKEND_URL="http://localhost:8000"
LOG_DIR="${SEEDY_DIR}/data/logs"

mkdir -p "${LOG_DIR}"

echo "========================================"
echo "Seedy Sources — $(date -u '+%Y-%m-%d %H:%M:%S UTC') — modo: ${1:-help}"
echo "========================================"

case "${1:-help}" in
    science)
        echo "Descargando artículos científicos (OpenAlex)..."
        cd "${SEEDY_DIR}"
        ${VENV} download_science_articles.py
        echo "Artículos descargados."
        ;;
    agro)
        echo "Descargando webs agro españolas..."
        cd "${SEEDY_DIR}"
        ${VENV} download_agro_sites.py
        echo "Webs agro descargadas."
        ;;
    ingest)
        echo "Disparando ingestión diaria vía API..."
        curl -s -X POST "${BACKEND_URL}/ingest/trigger" \
            -H "Content-Type: application/json" \
            -d '{"topic": null, "dry_run": false}' || echo "WARN: Backend no accesible"
        echo "Ingestión disparada."
        ;;
    *)
        echo "Uso: $0 {science|agro|ingest}"
        echo "  science  — Descarga artículos científicos de OpenAlex"
        echo "  agro     — Descarga webs agro españolas (3tres3, MAPA...)"
        echo "  ingest   — Dispara actualización diaria vía API backend"
        exit 1
        ;;
esac

echo "Completado: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
