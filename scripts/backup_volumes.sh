#!/usr/bin/env bash
# ────────────────────────────────────────────────────
# Seedy — Backup Docker Volumes
# Uso: ./scripts/backup_volumes.sh
# ────────────────────────────────────────────────────
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/mnt/nas/seedy-backups/volumes}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)

# Volumes críticos a respaldar
VOLUMES=(
    "ollama_data"
    "open_webui_data"
    "qdrant_data"
    "influxdb_data"
    "grafana_data"
    "nodered_data"
)

echo "💾 Seedy Backup Docker Volumes — $(date)"
echo "   Destino: ${BACKUP_DIR}"

mkdir -p "${BACKUP_DIR}"

ERRORS=0
for VOL in "${VOLUMES[@]}"; do
    echo -n "   📦 ${VOL}... "
    
    # Verificar que el volumen existe
    if ! docker volume inspect "${VOL}" > /dev/null 2>&1; then
        echo "⏭️  No existe, saltando"
        continue
    fi
    
    # Backup usando un contenedor temporal alpine
    docker run --rm \
        -v "${VOL}:/source:ro" \
        -v "${BACKUP_DIR}:/backup" \
        alpine:3.19 \
        tar czf "/backup/${VOL}_${DATE}.tar.gz" -C /source . 2>/dev/null || {
        echo "❌ FALLO"
        ERRORS=$((ERRORS + 1))
        continue
    }
    
    SIZE=$(du -h "${BACKUP_DIR}/${VOL}_${DATE}.tar.gz" | cut -f1)
    echo "✅ ${SIZE}"
done

# Limpieza de backups antiguos
echo -n "   🧹 Limpiando backups > ${RETENTION_DAYS} días... "
DELETED=$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete -print 2>/dev/null | wc -l)
echo "${DELETED} eliminados"

# Resumen
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✅ Backup Volumes completo (${TOTAL_SIZE} total)"
else
    echo "⚠️  Backup Volumes con ${ERRORS} errores (${TOTAL_SIZE} total)"
    exit 1
fi
