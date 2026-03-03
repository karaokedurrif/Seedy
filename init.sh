#!/bin/bash
# ────────────────────────────────────────────────────
# Seedy — Init script post docker-compose up
# ────────────────────────────────────────────────────
set -e

echo "🌱 Seedy Init — $(date)"

# 1. Esperar a que Ollama esté listo
echo "⏳ Esperando Ollama..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "✅ Ollama listo"

# 2. Verificar/crear modelo seedy:q8
if curl -sf http://localhost:11434/api/tags | grep -q "seedy:q8"; then
    echo "✅ Modelo seedy:q8 ya existe"
else
    echo "📦 Creando modelo seedy:q8 desde GGUF..."
    if [ -f /home/davidia/models/gguf/seedy-q8_0.gguf ]; then
        cat <<EOF | curl -sf http://localhost:11434/api/create -d @-
{
    "model": "seedy:q8",
    "modelfile": "FROM /models/gguf/seedy-q8_0.gguf\nPARAMETER temperature 0.3\nPARAMETER top_p 0.9\nPARAMETER repeat_penalty 1.1\nPARAMETER num_ctx 8192"
}
EOF
        echo "✅ Modelo seedy:q8 creado"
    else
        echo "⚠️  GGUF no encontrado en /home/davidia/models/gguf/seedy-q8_0.gguf"
    fi
fi

# 3. Verificar modelo de embeddings
if curl -sf http://localhost:11434/api/tags | grep -q "mxbai-embed-large"; then
    echo "✅ Modelo mxbai-embed-large ya existe"
else
    echo "📥 Descargando mxbai-embed-large..."
    curl -sf http://localhost:11434/api/pull -d '{"model": "mxbai-embed-large"}' | tail -1
    echo "✅ mxbai-embed-large descargado"
fi

# 4. Esperar Qdrant
echo "⏳ Esperando Qdrant..."
until curl -sf http://localhost:6333/healthz > /dev/null 2>&1; do
    sleep 2
done
echo "✅ Qdrant listo"

# 5. Esperar Backend
echo "⏳ Esperando Seedy Backend..."
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    sleep 3
done
echo "✅ Backend listo"

# 6. Indexar conocimientos en Qdrant
echo "📚 Indexando conocimientos en Qdrant..."
docker exec seedy-backend python -m ingestion.ingest --knowledge-dir /app/knowledge
echo "✅ Indexación completa"

# 7. Tests de diagnóstico
echo ""
echo "🧪 Ejecutando tests..."
docker exec seedy-backend python -m tests.test_rag || true
docker exec seedy-backend python -m tests.test_classifier || true

echo ""
echo "🎉 Seedy Init completo — $(date)"
echo ""
echo "Servicios disponibles:"
echo "  Open WebUI:     http://localhost:3000"
echo "  Seedy API:      http://localhost:8000 (docs: http://localhost:8000/docs)"
echo "  Qdrant:         http://localhost:6333/dashboard"
echo "  Grafana:        http://localhost:3001"
echo "  Node-RED:       http://localhost:1880"
echo "  InfluxDB:       http://localhost:8086"
