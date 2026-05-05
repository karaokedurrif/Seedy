#!/usr/bin/env bash
# ────────────────────────────────────────────────────
# Seedy — Deploy a NAS (OMV / servidor remoto)
# Uso: ./scripts/deploy_nas.sh [usuario@host] [ruta_destino]
# Ejemplo: ./scripts/deploy_nas.sh david@192.168.30.100 /srv/seedy
# ────────────────────────────────────────────────────
set -euo pipefail

NAS_HOST="${1:-}"
NAS_PATH="${2:-/srv/seedy}"

if [ -z "$NAS_HOST" ]; then
    echo "Uso: $0 usuario@host [ruta_destino]"
    echo "Ejemplo: $0 david@192.168.30.100 /srv/seedy"
    exit 1
fi

SEEDY_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Seedy Deploy to NAS — $(date)"
echo "   Origen:  ${SEEDY_DIR}"
echo "   Destino: ${NAS_HOST}:${NAS_PATH}"
echo ""

# 1. Crear estructura en NAS
echo "📁 Creando estructura en NAS..."
ssh "${NAS_HOST}" "mkdir -p ${NAS_PATH}/{backend,conocimientos,pipelines,scripts,docs,data,briefs,.github}"

# 2. Rsync del proyecto (excluyendo virtualenvs, modelos, caches)
echo "📤 Sincronizando archivos..."
rsync -avz --progress \
    --exclude '.venv/' \
    --exclude '.venv-1/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude 'data/ingest_state.db' \
    --exclude '*.gguf' \
    --exclude '*.tar.zst' \
    --exclude 'node_modules/' \
    "${SEEDY_DIR}/" "${NAS_HOST}:${NAS_PATH}/"

# 3. Crear .env en NAS si no existe
echo "🔧 Verificando .env..."
ssh "${NAS_HOST}" "
    if [ ! -f ${NAS_PATH}/.env ]; then
        cp ${NAS_PATH}/.env.example ${NAS_PATH}/.env
        echo '⚠️  .env creado desde .env.example — EDITA las credenciales'
    else
        echo '✅ .env ya existe'
    fi
"

# 4. Generar docker-compose adaptado para NAS
echo "🐳 Generando docker-compose NAS..."
ssh "${NAS_HOST}" "
cat > ${NAS_PATH}/docker-compose.nas.yml << 'COMPOSE_EOF'
# Docker Compose adaptado para NAS/OMV (sin GPU)
# Para NAS con GPU NVIDIA, usar docker-compose.yml original

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - \"11434:11434\"
    volumes:
      - ollama_data:/root/.ollama
      - ${NAS_PATH}/models:/models
    # Sin GPU — usar CPU (lento pero funcional para 7B Q4)
    # Si el NAS tiene GPU NVIDIA, descomentar:
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
    healthcheck:
      test: [\"CMD\", \"curl\", \"-f\", \"http://localhost:11434/api/tags\"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - ai_default

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - \"3000:8080\"
    volumes:
      - open_webui_data:/app/backend/data
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      ollama:
        condition: service_healthy
    networks:
      - ai_default

  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    restart: unless-stopped
    ports:
      - \"6333:6333\"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: [\"CMD\", \"curl\", \"-f\", \"http://localhost:6333/healthz\"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - ai_default

  seedy-backend:
    build:
      context: ./backend
    container_name: seedy-backend
    restart: unless-stopped
    ports:
      - \"8000:8000\"
    env_file:
      - .env
    volumes:
      - ./backend:/app
      - ./conocimientos:/app/knowledge:ro
    depends_on:
      ollama:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    networks:
      - ai_default

volumes:
  ollama_data:
  open_webui_data:
  qdrant_data:

networks:
  ai_default:
    name: ai_default
    driver: bridge
COMPOSE_EOF
echo '✅ docker-compose.nas.yml creado (sin IoT services para NAS ligero)'
"

# 5. Script de arranque en NAS
ssh "${NAS_HOST}" "
cat > ${NAS_PATH}/start_nas.sh << 'START_EOF'
#!/bin/bash
cd \$(dirname \$0)
echo '🌱 Arrancando Seedy en NAS...'

# Usar compose NAS (sin GPU, sin IoT)
docker compose -f docker-compose.nas.yml up -d

echo 'Esperando servicios...'
sleep 10

# Verificar
echo 'Estado:'
docker compose -f docker-compose.nas.yml ps
echo ''
echo 'Servicios:'
echo '  Open WebUI: http://\$(hostname -I | awk \"{print \\\$1}\"):3000'
echo '  Seedy API:  http://\$(hostname -I | awk \"{print \\\$1}\"):8000/docs'
echo '  Qdrant:     http://\$(hostname -I | awk \"{print \\\$1}\"):6333/dashboard'
START_EOF
chmod +x ${NAS_PATH}/start_nas.sh
echo '✅ start_nas.sh creado'
"

echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ Deploy completado en ${NAS_HOST}:${NAS_PATH}"
echo ""
echo "Próximos pasos en el NAS:"
echo "  1. ssh ${NAS_HOST}"
echo "  2. cd ${NAS_PATH}"
echo "  3. nano .env  (configurar TOGETHER_API_KEY, etc.)"
echo "  4. ./start_nas.sh"
echo "  5. Abrir http://<ip-nas>:3000"
echo ""
echo "Requisitos mínimos del NAS:"
echo "  - RAM: 8 GB (16 GB recomendado)"
echo "  - Disco: 20 GB libres (modelos + datos)"
echo "  - Docker + Docker Compose instalados"
echo "  - Sin GPU: modelo Q4_K_M (4.4 GB, más lento pero funcional)"
echo "  - Con GPU: modelo Q8_0 (7.7 GB, velocidad completa)"
echo "═══════════════════════════════════════════════════"
