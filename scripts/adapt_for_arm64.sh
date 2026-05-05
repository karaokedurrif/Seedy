#!/bin/bash
# Adaptar docker-compose.yml de Seedy para DGX Spark ARM64
# Ejecutar EN el DGX después de la transferencia

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cd ~/seedy

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  ADAPTACIÓN DOCKER-COMPOSE PARA ARM64${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Verificar que estamos en DGX (ARM64)
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    echo -e "${YELLOW}⚠️  Arquitectura detectada: $ARCH (esperado: aarch64)${NC}"
    read -p "¿Continuar de todas formas? (y/N): " continue_arch
    [[ ! "$continue_arch" =~ ^[Yy]$ ]] && exit 1
fi

# Verificar que existe docker-compose.yml
if [ ! -f docker-compose.yml ]; then
    echo -e "${RED}❌ docker-compose.yml no encontrado en $(pwd)${NC}"
    exit 1
fi

echo "=== PASO 1: Backup del docker-compose.yml original ==="
cp docker-compose.yml docker-compose.yml.bak-x86-$(date +%Y%m%d_%H%M%S)
echo -e "${GREEN}✅ Backup creado: docker-compose.yml.bak-x86-$(date +%Y%m%d_%H%M%S)${NC}"

echo ""
echo "=== PASO 2: Adaptar rutas de volúmenes ==="

# Cambiar ruta de modelos Ollama
if grep -q "/home/davidia/models:/models" docker-compose.yml; then
    sed -i 's|/home/davidia/models:/models|/mnt/data/models:/models|g' docker-compose.yml
    echo -e "${GREEN}✅ Ruta de modelos: /home/davidia/models → /mnt/data/models${NC}"
else
    echo "  Ruta de modelos ya adaptada o no encontrada"
fi

# Cambiar ruta de conocimientos (si existe)
if grep -q "./conocimientos:/app/conocimientos" docker-compose.yml; then
    sed -i 's|./conocimientos:/app/conocimientos|/mnt/data/knowledge:/app/conocimientos|g' docker-compose.yml
    echo -e "${GREEN}✅ Ruta de conocimientos: ./conocimientos → /mnt/data/knowledge${NC}"
else
    echo "  Ruta de conocimientos ya adaptada o no encontrada"
fi

# Cambiar ruta de conocimientos variante (backend)
if grep -q "./conocimientos:/app/knowledge" docker-compose.yml; then
    sed -i 's|./conocimientos:/app/knowledge|/mnt/data/knowledge:/app/knowledge|g' docker-compose.yml
    echo -e "${GREEN}✅ Ruta de conocimientos (backend): ./conocimientos → /mnt/data/knowledge${NC}"
fi

echo ""
echo "=== PASO 3: Ajustar go2rtc (sin cámaras por ahora) ==="

# Comentar network_mode: host de go2rtc (cámaras irán a J3011)
if grep -q "network_mode: host" docker-compose.yml; then
    sed -i 's|network_mode: host|# network_mode: host  # Comentado - cámaras migrarán a J3011|g' docker-compose.yml
    
    # Añadir ports a go2rtc si no existe
    if ! grep -A5 "go2rtc:" docker-compose.yml | grep -q "ports:"; then
        # Buscar línea de go2rtc e insertar ports después de image
        sed -i '/go2rtc:/,/image:/ {
            /image:/ a\    ports:\n      - "1984:1984"\n      - "8554:8554"
        }' docker-compose.yml
    fi
    
    echo -e "${GREEN}✅ go2rtc adaptado: host network → bridge con ports${NC}"
else
    echo "  go2rtc ya adaptado o no usa host network"
fi

echo ""
echo "=== PASO 4: Verificar .env ==="

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠️  .env creado desde .env.example - REVISAR MANUALMENTE${NC}"
    else
        touch .env
        echo -e "${YELLOW}⚠️  .env creado vacío - CONFIGURAR MANUALMENTE${NC}"
    fi
fi

# Actualizar GO2RTC_URL en .env
if grep -q "GO2RTC_URL=" .env; then
    sed -i 's|GO2RTC_URL=.*|GO2RTC_URL=http://go2rtc:1984|g' .env
    echo -e "${GREEN}✅ .env: GO2RTC_URL actualizada${NC}"
else
    echo "GO2RTC_URL=http://go2rtc:1984" >> .env
    echo -e "${GREEN}✅ .env: GO2RTC_URL añadida${NC}"
fi

# Verificar MODELS_PATH
if ! grep -q "MODELS_PATH=" .env; then
    echo "MODELS_PATH=/mnt/data/models" >> .env
    echo -e "${GREEN}✅ .env: MODELS_PATH añadida${NC}"
fi

# Verificar KNOWLEDGE_PATH
if ! grep -q "KNOWLEDGE_PATH=" .env; then
    echo "KNOWLEDGE_PATH=/mnt/data/knowledge" >> .env
    echo -e "${GREEN}✅ .env: KNOWLEDGE_PATH añadida${NC}"
fi

echo ""
echo "=== PASO 5: Verificar sintaxis ==="

if docker compose config > /dev/null 2>&1; then
    echo -e "${GREEN}✅ docker-compose.yml es válido${NC}"
else
    echo -e "${RED}❌ Error en docker-compose.yml:${NC}"
    docker compose config
    exit 1
fi

echo ""
echo "=== PASO 6: Verificar imágenes ARM64 ==="

echo "Verificando compatibilidad ARM64 de imágenes..."
echo ""

check_arm64() {
    local image=$1
    echo -n "Verificando $image... "
    
    if docker manifest inspect "$image" 2>/dev/null | grep -q "arm64"; then
        echo -e "${GREEN}✅${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  (no ARM64 nativa, intentará emulación o build)${NC}"
        return 1
    fi
}

# Extraer imágenes del docker-compose.yml
IMAGES=$(docker compose config --images 2>/dev/null | grep -v "^#" | sort -u)

ARM64_OK=0
ARM64_WARN=0

while IFS= read -r img; do
    [ -z "$img" ] && continue
    
    if check_arm64 "$img"; then
        ARM64_OK=$((ARM64_OK+1))
    else
        ARM64_WARN=$((ARM64_WARN+1))
    fi
done <<< "$IMAGES"

echo ""
echo "Imágenes ARM64 nativas: $ARM64_OK"
echo "Imágenes con advertencias: $ARM64_WARN"

if [ "$ARM64_WARN" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Algunas imágenes pueden necesitar build local o no funcionar${NC}"
fi

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  ADAPTACIÓN COMPLETADA${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Cambios realizados:"
echo "  ✓ Rutas de volúmenes → /mnt/data/*"
echo "  ✓ go2rtc sin host network"
echo "  ✓ .env actualizado"
echo "  ✓ Sintaxis verificada"
echo ""
echo "Backup original en:"
ls -lh docker-compose.yml.bak-x86-* | tail -1
echo ""
echo "=== SIGUIENTE PASO ==="
echo ""
echo "1. Revisar manualmente el docker-compose.yml:"
echo "   nano ~/seedy/docker-compose.yml"
echo ""
echo "2. Verificar .env tiene las API keys:"
echo "   nano ~/seedy/.env"
echo ""
echo "3. Pull de imágenes (verificar ARM64):"
echo "   docker compose pull"
echo ""
echo "4. Build del backend:"
echo "   docker compose build seedy-backend"
echo ""
echo "5. Levantar stack:"
echo "   docker compose up -d"
echo ""
echo "6. Ver logs:"
echo "   docker compose logs -f"
