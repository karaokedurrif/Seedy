#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# Seedy AI — Instalador de cron jobs
# Ejecutar una vez para configurar backups y healthchecks
# ─────────────────────────────────────────────────────
set -euo pipefail

SEEDY_DIR="${SEEDY_DIR:-/home/davidia/Documentos/Seedy}"
SCRIPTS_DIR="${SEEDY_DIR}/scripts"

echo "╔════════════════════════════════════════╗"
echo "║  Seedy — Configurar Cron Jobs          ║"
echo "╚════════════════════════════════════════╝"

# Verificar que los scripts existen
for script in backup_all.sh healthcheck.sh; do
  if [[ ! -x "${SCRIPTS_DIR}/${script}" ]]; then
    echo "❌ Error: ${SCRIPTS_DIR}/${script} no encontrado o no ejecutable"
    exit 1
  fi
done

# Crear directorio de logs
mkdir -p "${SEEDY_DIR}/logs"

# Líneas de cron a añadir
CRON_BACKUP="0 3 * * * ${SCRIPTS_DIR}/backup_all.sh >> ${SEEDY_DIR}/logs/cron_backup.log 2>&1"
CRON_HEALTH="*/5 * * * * ${SCRIPTS_DIR}/healthcheck.sh >> ${SEEDY_DIR}/logs/cron_health.log 2>&1"

# Obtener crontab actual (sin errores si está vacía)
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

# Verificar si ya están instalados
CHANGES=0

if echo "$CURRENT_CRON" | grep -qF "backup_all.sh"; then
  echo "⏭️  Backup cron ya instalado"
else
  CURRENT_CRON="${CURRENT_CRON}
${CRON_BACKUP}"
  echo "✅ Añadido: backup diario a las 03:00"
  CHANGES=1
fi

if echo "$CURRENT_CRON" | grep -qF "healthcheck.sh"; then
  echo "⏭️  Healthcheck cron ya instalado"
else
  CURRENT_CRON="${CURRENT_CRON}
${CRON_HEALTH}"
  echo "✅ Añadido: healthcheck cada 5 minutos"
  CHANGES=1
fi

if [[ $CHANGES -eq 1 ]]; then
  # Limpiar líneas vacías duplicadas
  echo "$CURRENT_CRON" | sed '/^$/N;/^\n$/d' | crontab -
  echo ""
  echo "📋 Crontab actualizado:"
  crontab -l
else
  echo ""
  echo "No hay cambios — todo ya estaba configurado"
fi

echo ""
echo "────────────────────────────────────────"
echo "  Logs → ${SEEDY_DIR}/logs/"
echo "  Backup: 03:00 diario"
echo "  Health: cada 5 min"
echo "────────────────────────────────────────"
