#!/bin/bash
# Seedy → NAS backup (rsync over SSH)
# NAS: OpenMediaVault @ 192.168.30.100
# Cron: cada 6h — 0 */6 * * *

set -euo pipefail

NAS_HOST="192.168.30.100"
NAS_USER="root"
NAS_DEST="/srv/dev-disk-by-uuid-17a070f2-e940-4dca-a886-fb7fd5c78054/datos/Seedy/"
SEEDY_DIR="/home/davidia/Documentos/Seedy/"
LOG="/home/davidia/Documentos/Seedy/data/logs/nas_backup.log"
PASS_FILE="/home/davidia/.nas_pass"

mkdir -p "$(dirname "$LOG")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

# Check NAS reachable
if ! ping -c 1 -W 2 "$NAS_HOST" &>/dev/null; then
  log "SKIP: NAS $NAS_HOST unreachable"
  exit 0
fi

log "START backup to NAS"

rsync -az --delete \
  --exclude='.git' \
  --exclude='models/' \
  --exclude='hf_datasets/' \
  --exclude='yolo_breed_dataset/' \
  --exclude='yolo_breed_models/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='Digital Twin/' \
  --exclude='*.mhtml' \
  -e "sshpass -p '$(cat "$PASS_FILE")' ssh -o StrictHostKeyChecking=no" \
  "$SEEDY_DIR" "$NAS_USER@$NAS_HOST:$NAS_DEST" \
  >> "$LOG" 2>&1

log "DONE backup to NAS (exit $?)"
