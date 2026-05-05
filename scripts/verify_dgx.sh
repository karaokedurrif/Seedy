#!/bin/bash
# FASE 8: Verificación end-to-end de Seedy en DGX Spark
# Ejecutar EN el DGX después de levantar los stacks

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  VERIFICACIÓN END-TO-END SEEDY DGX${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Función de test con contador
test_endpoint() {
    local name="$1"
    local url="$2"
    local expected="$3"
    
    echo -n "Testing $name... "
    
    if response=$(curl -s -m 10 "$url" 2>/dev/null); then
        if echo "$response" | grep -q "$expected"; then
            echo -e "${GREEN}✅${NC}"
            return 0
        else
            echo -e "${RED}❌ (respuesta inesperada)${NC}"
            ERRORS=$((ERRORS+1))
            return 1
        fi
    else
        echo -e "${RED}❌ (no responde)${NC}"
        ERRORS=$((ERRORS+1))
        return 1
    fi
}

# 1. ARQUITECTURA Y GPU
echo "=== 1. Sistema base ==="
ARCH=$(uname -m)
echo "Arquitectura: $ARCH"
if [ "$ARCH" != "aarch64" ]; then
    echo -e "${YELLOW}⚠️  NO es ARM64, esperado aarch64${NC}"
    WARNINGS=$((WARNINGS+1))
fi

if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✅ nvidia-smi disponible${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo -e "${RED}❌ nvidia-smi NO disponible${NC}"
    ERRORS=$((ERRORS+1))
fi

echo ""

# 2. DOCKER Y CONTENEDORES
echo "=== 2. Docker y contenedores ==="
if docker ps &> /dev/null; then
    echo -e "${GREEN}✅ Docker funciona${NC}"
else
    echo -e "${RED}❌ Docker no responde${NC}"
    ERRORS=$((ERRORS+1))
    exit 1
fi

RUNNING=$(docker ps --filter "name=seedy" --filter "name=ollama" --filter "name=qdrant" --format "{{.Names}}" | wc -l)
echo "Contenedores Seedy activos: $RUNNING"

if [ "$RUNNING" -lt 5 ]; then
    echo -e "${YELLOW}⚠️  Esperados al menos 5 contenedores (ollama, qdrant, backend, open-webui, etc.)${NC}"
    WARNINGS=$((WARNINGS+1))
fi

# Listar contenedores
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(seedy|ollama|qdrant|open-webui)" || true

echo ""

# 3. VOLUMENES
echo "=== 3. Volúmenes Docker ==="
VOLS=$(docker volume ls | grep -E "(seedy|ollama|qdrant)" | wc -l)
echo "Volúmenes Seedy: $VOLS"

if [ "$VOLS" -lt 4 ]; then
    echo -e "${YELLOW}⚠️  Esperados al menos: ollama_data, qdrant_data, yolo_models, openwebui_data${NC}"
    WARNINGS=$((WARNINGS+1))
fi

# Tamaños de volúmenes críticos
echo ""
echo "Tamaños de volúmenes críticos:"
docker volume inspect seedy_ollama_data seedy_qdrant_data seedy_yolo_models 2>/dev/null | \
    jq -r '.[] | "\(.Name): \(.Mountpoint)"' 2>/dev/null || echo "Instalar jq para ver detalles: sudo apt install jq"

echo ""

# 4. DISCO EXTERNO
echo "=== 4. Disco externo 2TB ==="
if mountpoint -q /mnt/data; then
    echo -e "${GREEN}✅ /mnt/data montado${NC}"
    df -h /mnt/data | tail -1
    
    # Verificar subdirectorios
    for dir in models knowledge; do
        if [ -d "/mnt/data/$dir" ]; then
            SIZE=$(du -sh /mnt/data/$dir 2>/dev/null | awk '{print $1}')
            echo "  ✓ /mnt/data/$dir ($SIZE)"
        else
            echo -e "  ${YELLOW}⚠️  /mnt/data/$dir no existe${NC}"
            WARNINGS=$((WARNINGS+1))
        fi
    done
else
    echo -e "${RED}❌ /mnt/data NO está montado${NC}"
    ERRORS=$((ERRORS+1))
fi

echo ""

# 5. ENDPOINTS HTTP
echo "=== 5. Endpoints HTTP ==="

test_endpoint "Seedy Backend Health" "http://localhost:8000/health" "status"
test_endpoint "Qdrant Collections" "http://localhost:6333/collections" "collections"
test_endpoint "Ollama Tags" "http://localhost:11434/api/tags" "models"
test_endpoint "Open WebUI" "http://localhost:3000" "Seedy"
test_endpoint "Grafana" "http://localhost:3001" "grafana"

echo ""

# 6. OLLAMA MODELOS
echo "=== 6. Ollama modelos ==="
if docker exec ollama ollama list 2>/dev/null; then
    MODELS=$(docker exec ollama ollama list 2>/dev/null | grep -v NAME | wc -l)
    echo "Modelos cargados: $MODELS"
    
    if [ "$MODELS" -lt 2 ]; then
        echo -e "${YELLOW}⚠️  Esperados al menos: seedy:v16, mxbai-embed-large${NC}"
        WARNINGS=$((WARNINGS+1))
    fi
else
    echo -e "${RED}❌ Ollama no responde${NC}"
    ERRORS=$((ERRORS+1))
fi

echo ""

# 7. QDRANT COLECCIONES
echo "=== 7. Qdrant colecciones ==="
if COLS=$(curl -s http://localhost:6333/collections 2>/dev/null | jq -r '.result.collections[].name' 2>/dev/null); then
    COLCOUNT=$(echo "$COLS" | wc -l)
    echo "Colecciones: $COLCOUNT"
    echo "$COLS" | head -5
    
    if [ "$COLCOUNT" -lt 5 ]; then
        echo -e "${YELLOW}⚠️  Esperadas ~13 colecciones (avicultura, porcino, genetica, etc.)${NC}"
        WARNINGS=$((WARNINGS+1))
    fi
else
    echo -e "${RED}❌ Qdrant no responde o jq no instalado${NC}"
    ERRORS=$((ERRORS+1))
fi

echo ""

# 8. TEST DE CHAT (opcional, si Together.ai key presente)
echo "=== 8. Test de chat RAG ==="
if [ -f ~/seedy/.env ] && grep -q "TOGETHER_API_KEY=" ~/seedy/.env; then
    echo "Ejecutando query de test..."
    
    RESPONSE=$(curl -s -X POST http://localhost:8000/v1/chat/completions \
        -H "Authorization: Bearer sk-seedy-local" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "seedy",
            "messages": [{"role": "user", "content": "¿Cuál es la temperatura óptima en una nave porcina?"}],
            "max_tokens": 100
        }' 2>/dev/null)
    
    if echo "$RESPONSE" | jq -e '.choices[0].message.content' &>/dev/null; then
        CONTENT=$(echo "$RESPONSE" | jq -r '.choices[0].message.content')
        echo -e "${GREEN}✅ Chat RAG funcional${NC}"
        echo "Respuesta: ${CONTENT:0:100}..."
    else
        echo -e "${YELLOW}⚠️  Chat respondió pero formato inesperado${NC}"
        echo "$RESPONSE" | head -3
        WARNINGS=$((WARNINGS+1))
    fi
else
    echo "Saltando (TOGETHER_API_KEY no configurada)"
fi

echo ""

# 9. GPU EN CONTENEDORES
echo "=== 9. Acceso GPU en contenedores ==="
if docker exec ollama nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null; then
    echo -e "${GREEN}✅ Ollama ve la GPU${NC}"
else
    echo -e "${RED}❌ Ollama NO ve la GPU${NC}"
    ERRORS=$((ERRORS+1))
fi

echo ""

# 10. LOGS DE ERRORES
echo "=== 10. Logs recientes (últimos errores) ==="
RECENT_ERRORS=$(docker compose -f ~/seedy/docker-compose.yml logs --since 10m 2>/dev/null | grep -iE "(error|fatal|exception)" | wc -l)

if [ "$RECENT_ERRORS" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  $RECENT_ERRORS errores en logs de últimos 10 min${NC}"
    echo "Ver con: docker compose -f ~/seedy/docker-compose.yml logs --tail=50 | grep -i error"
    WARNINGS=$((WARNINGS+1))
else
    echo -e "${GREEN}✅ Sin errores recientes en logs${NC}"
fi

# RESUMEN FINAL
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  RESUMEN${NC}"
echo -e "${GREEN}================================================${NC}"

if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo -e "${GREEN}✅ TODOS LOS TESTS PASADOS${NC}"
    echo ""
    echo "Seedy está funcionando correctamente en DGX Spark"
    echo ""
    echo "Siguiente paso: Configurar integración con GEEKOM"
    echo "  1. Añadir DGX a Portainer del GEEKOM"
    echo "  2. Actualizar SEEDY_API_URL en stacks de GEEKOM"
    exit 0
elif [ "$ERRORS" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  TESTS PASADOS CON $WARNINGS WARNINGS${NC}"
    echo ""
    echo "El sistema funciona pero revisa las advertencias arriba"
    exit 0
else
    echo -e "${RED}❌ $ERRORS ERRORES CRÍTICOS, $WARNINGS WARNINGS${NC}"
    echo ""
    echo "Revisar logs:"
    echo "  docker compose -f ~/seedy/docker-compose.yml logs"
    exit 1
fi
