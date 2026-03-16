#!/usr/bin/env bash
# Seedy — Cron de autoingesta diaria
# Instalar con: crontab -e
#   0 6 * * * /home/davidia/Documentos/Seedy/scripts/cron_ingest.sh >> /home/davidia/Documentos/Seedy/data/cron.log 2>&1

set -euo pipefail

SEEDY_DIR="/home/davidia/Documentos/Seedy"
COMPOSE="docker compose -f ${SEEDY_DIR}/docker-compose.yml"

echo "========================================"
echo "Seedy Autoingesta — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================"

# Ejecutar el servicio de ingestión
${COMPOSE} run --rm seedy-ingest

echo "Autoingesta completada: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
