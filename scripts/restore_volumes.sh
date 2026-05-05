#!/bin/bash
# FASE 4: Restauración de volúmenes Docker en DGX Spark
# Ejecutar EN el DGX Spark después del bootstrap
# Fecha: 30 abril 2026

set -euo pipefail

MIGRATION_BASE="$HOME/migration_dumps"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  RESTAURACIÓN DE VOLÚMENES DOCKER${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Verificar que estamos en DGX (ARM64)
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    echo -e "${YELLOW}⚠️  Este script está diseñado para DGX (ARM64)${NC}"
    echo "Arquitectura detectada: $ARCH"
    read -p "¿Continuar de todas formas? (y/N): " continue_arch
    [[ ! "$continue_arch" =~ ^[Yy]$ ]] && exit 1
fi

# Verificar que existen los dumps
if [ ! -d "$MIGRATION_BASE" ] || [ ! -f "$MIGRATION_BASE/MD5SUMS" ]; then
    echo -e "${RED}❌ No se encontraron dumps en $MIGRATION_BASE${NC}"
    echo "Ejecuta primero el script de transferencia desde el portátil"
    exit 1
fi

cd "$MIGRATION_BASE"

echo "=== PASO 1: Verificar integridad (MD5) ==="
if md5sum -c MD5SUMS; then
    echo -e "${GREEN}✅ Todos los checksums OK${NC}"
else
    echo -e "${RED}❌ Fallo en verificación de checksums${NC}"
    read -p "¿Continuar de todas formas? (y/N): " continue_md5
    [[ ! "$continue_md5" =~ ^[Yy]$ ]] && exit 1
fi

echo ""
echo "=== PASO 2: Crear volúmenes Docker vacíos ==="

# Lista de volúmenes a restaurar (basado en los .tar.gz presentes)
for tarball in *.tar.gz; do
    [ -f "$tarball" ] || continue
    vol="${tarball%.tar.gz}"
    
    # Saltar dump SQL
    [[ "$vol" == *"_db.sql"* ]] && continue
    
    echo "Creando volumen: $vol"
    docker volume create "$vol" 2>/dev/null || echo "  Volumen $vol ya existe"
done

echo -e "${GREEN}✅ Volúmenes creados${NC}"

echo ""
echo "=== PASO 3: Restaurar datos en volúmenes ==="

restore_volume() {
    local tarball=$1
    local vol="${tarball%.tar.gz}"
    
    # Saltar archivos que no son volúmenes
    [[ "$vol" == *"_db.sql"* ]] && return 0
    
    if [ ! -f "$tarball" ]; then
        echo -e "${YELLOW}⚠️  Tarball no encontrado: $tarball${NC}"
        return 1
    fi
    
    echo ""
    echo -e "${GREEN}Restaurando: $vol${NC}"
    local tarsize=$(du -h "$tarball" | awk '{print $1}')
    echo "  Tamaño: $tarsize"
    
    # Restaurar usando contenedor Alpine ARM64
    if docker run --rm \
        -v "$vol:/dest" \
        -v "$MIGRATION_BASE:/source:ro" \
        alpine \
        sh -c "cd /dest && tar xzf /source/$tarball"; then
        
        echo -e "${GREEN}✅ $vol restaurado${NC}"
        return 0
    else
        echo -e "${RED}❌ Error restaurando $vol${NC}"
        return 1
    fi
}

# Restaurar volúmenes en orden de prioridad
CRITICAL_VOLUMES=(
    "seedy_ollama_data"
    "seedy_qdrant_data"
    "seedy_yolo_models"
    "ai_openwebui_data"
)

IMPORTANT_VOLUMES=(
    "seedy_influxdb_data"
    "seedy_grafana_data"
    "seedy_nodered_data"
    "geotwin-db-data"
    "geotwin-illustrations"
    "seedy_caddy_data"
)

# Críticos primero
echo ""
echo "=== CRÍTICOS (obligatorios) ==="
for vol in "${CRITICAL_VOLUMES[@]}"; do
    if [ -f "${vol}.tar.gz" ]; then
        restore_volume "${vol}.tar.gz" || {
            echo -e "${RED}❌ FALLO CRÍTICO restaurando $vol${NC}"
            exit 1
        }
    else
        echo -e "${YELLOW}⚠️  No encontrado: ${vol}.tar.gz${NC}"
    fi
done

# Importantes
echo ""
echo "=== IMPORTANTES (recomendados) ==="
for vol in "${IMPORTANT_VOLUMES[@]}"; do
    if [ -f "${vol}.tar.gz" ]; then
        restore_volume "${vol}.tar.gz" || {
            echo -e "${YELLOW}⚠️  Error en $vol pero continúo...${NC}"
        }
    fi
done

# Restaurar cualquier otro volumen presente
echo ""
echo "=== OTROS VOLÚMENES ==="
for tarball in *.tar.gz; do
    [ -f "$tarball" ] || continue
    vol="${tarball%.tar.gz}"
    
    # Saltar los ya procesados
    [[ " ${CRITICAL_VOLUMES[@]} ${IMPORTANT_VOLUMES[@]} " =~ " $vol " ]] && continue
    [[ "$vol" == *"_db.sql"* ]] && continue
    
    restore_volume "$tarball" || echo "Error en $vol (no crítico)"
done

echo ""
echo "=== PASO 4: Restaurar base de datos GeoTwin ==="
if [ -f "geotwin_db.sql.gz" ]; then
    echo "Dump de GeoTwin encontrado, se restaurará cuando se levante el contenedor postgres"
    echo "Comando a ejecutar después:"
    echo "  gunzip < ~/migration_dumps/geotwin_db.sql.gz | docker exec -i geotwin-db psql -U postgres"
    echo -e "${GREEN}✅ Dump preparado${NC}"
else
    echo "No se encontró dump de GeoTwin, saltando..."
fi

echo ""
echo "=== PASO 5: Verificar tamaños de volúmenes ==="
echo ""
docker system df -v | grep -E "(seedy|geotwin|openwebui)" | head -20

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  RESTAURACIÓN COMPLETADA${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Volúmenes Docker restaurados y listos"
echo ""
echo "=== SIGUIENTE PASO ==="
echo "Levantar los stacks:"
echo "  cd ~/seedy && docker compose up -d"
echo "  cd ~/geotwin && docker compose up -d"
