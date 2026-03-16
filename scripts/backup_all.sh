#!/usr/bin/env bash
# ────────────────────────────────────────────────────
# Seedy — Backup completo (orquestador)
# Uso: ./scripts/backup_all.sh
# Cron: 0 3 * * * /home/davidia/Documentos/Seedy/scripts/backup_all.sh >> /var/log/seedy-backup.log 2>&1
# ────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export BACKUP_DIR="${BACKUP_DIR:-/mnt/nas/seedy-backups}"
export RETENTION_DAYS="${RETENTION_DAYS:-7}"
export SEEDY_DIR="${SEEDY_DIR:-/home/davidia/Documentos/Seedy}"
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

LOG_FILE="/var/log/seedy-backup.log"

echo ""
echo "═══════════════════════════════════════════════════"
echo "🌱 SEEDY — Backup Completo — $(date)"
echo "═══════════════════════════════════════════════════"

ERRORS=0

# 1. Qdrant snapshots
echo ""
export BACKUP_DIR="${BACKUP_DIR}/qdrant"
"${SCRIPT_DIR}/backup_qdrant.sh" || ERRORS=$((ERRORS + 1))

# 2. Knowledge + datasets + code
echo ""
export BACKUP_DIR="${BACKUP_DIR%/qdrant}/knowledge"
"${SCRIPT_DIR}/backup_knowledge.sh" || ERRORS=$((ERRORS + 1))

# 3. Docker volumes
echo ""
export BACKUP_DIR="${BACKUP_DIR%/knowledge}/volumes"
"${SCRIPT_DIR}/backup_volumes.sh" || ERRORS=$((ERRORS + 1))

# 4. Modelos GGUF (solo si hay espacio)
MODELS_DIR="/home/davidia/models"
MODELS_BACKUP="${BACKUP_DIR%/volumes}/models"
if [ -d "$MODELS_DIR" ]; then
    echo ""
    echo -n "🤖 Backup modelos GGUF... "
    mkdir -p "$MODELS_BACKUP"
    # Solo copiar los .gguf si han cambiado (rsync)
    rsync -a --include='*.gguf' --exclude='*' "$MODELS_DIR/" "$MODELS_BACKUP/" 2>/dev/null || true
    SIZE=$(du -sh "$MODELS_BACKUP" 2>/dev/null | cut -f1)
    echo "✅ ${SIZE}"
fi

echo ""
echo "═══════════════════════════════════════════════════"
TOTAL=$(du -sh "${BACKUP_DIR%/volumes}" 2>/dev/null | cut -f1)
if [ $ERRORS -eq 0 ]; then
    echo "✅ BACKUP COMPLETO OK — ${TOTAL} total"
else
    echo "⚠️  BACKUP con ${ERRORS} errores — ${TOTAL} total"
fi
echo "═══════════════════════════════════════════════════"

# Enviar alerta si hubo errores (descomentar cuando configures Telegram)
# if [ $ERRORS -gt 0 ]; then
#     TELEGRAM_BOT_TOKEN="your-bot-token"
#     TELEGRAM_CHAT_ID="your-chat-id"
#     curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
#         -d "chat_id=${TELEGRAM_CHAT_ID}" \
#         -d "text=⚠️ Seedy Backup falló con ${ERRORS} errores — $(date)" > /dev/null
# fi

exit $ERRORS
