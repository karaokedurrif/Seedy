#!/usr/bin/env bash
# ────────────────────────────────────────────────────
# Seedy — Backup Qdrant (snapshots vía API)
# Uso: ./scripts/backup_qdrant.sh
# ────────────────────────────────────────────────────
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
BACKUP_DIR="${BACKUP_DIR:-/mnt/nas/seedy-backups/qdrant}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
SNAPSHOT_DIR="${BACKUP_DIR}/${DATE}"

echo "🗂️  Seedy Backup Qdrant — $(date)"
echo "   Qdrant: ${QDRANT_URL}"
echo "   Destino: ${SNAPSHOT_DIR}"

# Verificar que Qdrant responde
if ! curl -sf "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
    echo "❌ ERROR: Qdrant no responde en ${QDRANT_URL}"
    exit 1
fi

mkdir -p "${SNAPSHOT_DIR}"

# Obtener lista de colecciones
COLLECTIONS=$(curl -sf "${QDRANT_URL}/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data['result']['collections']:
    print(c['name'])
")

if [ -z "$COLLECTIONS" ]; then
    echo "⚠️  No se encontraron colecciones en Qdrant"
    exit 0
fi

echo "   Colecciones: $(echo $COLLECTIONS | tr '\n' ', ')"

# Crear snapshot de cada colección
ERRORS=0
for COLLECTION in $COLLECTIONS; do
    echo -n "   📸 Snapshot ${COLLECTION}... "
    
    RESPONSE=$(curl -sf -X POST "${QDRANT_URL}/collections/${COLLECTION}/snapshots" 2>&1) || {
        echo "❌ FALLO"
        ERRORS=$((ERRORS + 1))
        continue
    }
    
    # Extraer nombre del snapshot
    SNAP_NAME=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['result']['name'])
" 2>/dev/null) || {
        echo "❌ No se pudo parsear respuesta"
        ERRORS=$((ERRORS + 1))
        continue
    }
    
    # Descargar snapshot
    curl -sf "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAP_NAME}" \
        -o "${SNAPSHOT_DIR}/${COLLECTION}_${SNAP_NAME}" || {
        echo "❌ Error descargando"
        ERRORS=$((ERRORS + 1))
        continue
    }
    
    SIZE=$(du -h "${SNAPSHOT_DIR}/${COLLECTION}_${SNAP_NAME}" | cut -f1)
    echo "✅ ${SIZE}"
    
    # Limpiar snapshot del servidor
    curl -sf -X DELETE "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAP_NAME}" > /dev/null 2>&1 || true
done

# Limpieza de backups antiguos
echo -n "   🧹 Limpiando backups > ${RETENTION_DAYS} días... "
DELETED=$(find "${BACKUP_DIR}" -maxdepth 1 -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} \; -print 2>/dev/null | wc -l)
echo "${DELETED} eliminados"

# Resumen
TOTAL_SIZE=$(du -sh "${SNAPSHOT_DIR}" 2>/dev/null | cut -f1)
echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✅ Backup Qdrant completo: ${SNAPSHOT_DIR} (${TOTAL_SIZE})"
else
    echo "⚠️  Backup Qdrant con ${ERRORS} errores: ${SNAPSHOT_DIR} (${TOTAL_SIZE})"
    exit 1
fi
