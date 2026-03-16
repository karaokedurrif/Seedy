#!/usr/bin/env bash
# ────────────────────────────────────────────────────
# Seedy — Backup Knowledge Base + Datasets
# Uso: ./scripts/backup_knowledge.sh
# ────────────────────────────────────────────────────
set -euo pipefail

SEEDY_DIR="${SEEDY_DIR:-/home/davidia/Documentos/Seedy}"
BACKUP_DIR="${BACKUP_DIR:-/mnt/nas/seedy-backups/knowledge}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)

echo "📚 Seedy Backup Knowledge — $(date)"
echo "   Origen: ${SEEDY_DIR}"
echo "   Destino: ${BACKUP_DIR}"

mkdir -p "${BACKUP_DIR}"

# 1. Backup de conocimientos/ (RAG docs)
echo -n "   📁 conocimientos/... "
tar czf "${BACKUP_DIR}/conocimientos_${DATE}.tar.gz" \
    -C "${SEEDY_DIR}" conocimientos/ 2>/dev/null
SIZE=$(du -h "${BACKUP_DIR}/conocimientos_${DATE}.tar.gz" | cut -f1)
echo "✅ ${SIZE}"

# 2. Backup de datasets SFT
echo -n "   📊 Datasets SFT... "
tar czf "${BACKUP_DIR}/datasets_${DATE}.tar.gz" \
    -C "${SEEDY_DIR}" \
    --include='*.jsonl' \
    --include='build_v*.py' \
    . 2>/dev/null || \
tar czf "${BACKUP_DIR}/datasets_${DATE}.tar.gz" \
    -C "${SEEDY_DIR}" \
    $(cd "${SEEDY_DIR}" && ls *.jsonl build_v*.py 2>/dev/null) 2>/dev/null
SIZE=$(du -h "${BACKUP_DIR}/datasets_${DATE}.tar.gz" | cut -f1)
echo "✅ ${SIZE}"

# 3. Backup de pipelines/ (autoingesta)
echo -n "   🔄 pipelines/... "
tar czf "${BACKUP_DIR}/pipelines_${DATE}.tar.gz" \
    -C "${SEEDY_DIR}" pipelines/ 2>/dev/null
SIZE=$(du -h "${BACKUP_DIR}/pipelines_${DATE}.tar.gz" | cut -f1)
echo "✅ ${SIZE}"

# 4. Backup de backend/ (code)
echo -n "   ⚙️  backend/... "
tar czf "${BACKUP_DIR}/backend_${DATE}.tar.gz" \
    -C "${SEEDY_DIR}" backend/ \
    --exclude='__pycache__' --exclude='.pyc' 2>/dev/null
SIZE=$(du -h "${BACKUP_DIR}/backend_${DATE}.tar.gz" | cut -f1)
echo "✅ ${SIZE}"

# 5. Backup de configs (docker-compose, .env, Modelfile, etc.)
echo -n "   🔧 Configs... "
tar czf "${BACKUP_DIR}/configs_${DATE}.tar.gz" \
    -C "${SEEDY_DIR}" \
    docker-compose.yml .env.example init.sh Modelfile.seedy-q8 \
    .github/ README.md 2>/dev/null
SIZE=$(du -h "${BACKUP_DIR}/configs_${DATE}.tar.gz" | cut -f1)
echo "✅ ${SIZE}"

# 6. Backup de briefs diarios (si existen)
if [ -d "${SEEDY_DIR}/briefs" ] && [ "$(ls -A ${SEEDY_DIR}/briefs 2>/dev/null)" ]; then
    echo -n "   📰 briefs/... "
    tar czf "${BACKUP_DIR}/briefs_${DATE}.tar.gz" \
        -C "${SEEDY_DIR}" briefs/ 2>/dev/null
    SIZE=$(du -h "${BACKUP_DIR}/briefs_${DATE}.tar.gz" | cut -f1)
    echo "✅ ${SIZE}"
fi

# Limpieza de backups antiguos
echo -n "   🧹 Limpiando backups > ${RETENTION_DAYS} días... "
DELETED=$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete -print 2>/dev/null | wc -l)
echo "${DELETED} eliminados"

# Resumen
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
echo ""
echo "✅ Backup Knowledge completo (${TOTAL_SIZE} total en ${BACKUP_DIR})"
