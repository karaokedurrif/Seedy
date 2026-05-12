#!/bin/bash

# Script para copiar archivos esenciales al DGX
# Ejecutar cuando el DGX (192.168.20.57) esté accesible

set -e

DGX_USER="davidia"
DGX_IP="192.168.20.57"
DGX_PATH="/home/davidia/Documentos/Seedy"

echo "═══════════════════════════════════════════════════════"
echo "🔄 SINCRONIZANDO ARCHIVOS AL DGX"
echo "═══════════════════════════════════════════════════════"
echo ""

# Verificar conectividad
echo "📡 Verificando conectividad con DGX ($DGX_IP)..."
if ping -c 2 -W 2 "$DGX_IP" >/dev/null 2>&1; then
    echo "✅ DGX accesible"
else
    echo "❌ DGX no accesible en $DGX_IP"
    echo "   Verifica que estés en la misma red"
    exit 1
fi
echo ""

# Archivos a copiar
FILES=(
    "setup_minipc_local.sh"
    "setup_dual_wifi_auto.sh"
    "drone_bridge.py"
    "fly_bebop_10s.sh"
    "INTEGRACION_DGX_DRON.md"
    "README_DUAL_WIFI_DGX.md"
    "RESUMEN_CONFIGURACION.md"
    "PENDIENTE_MINIPC_13MAY2026.md"
)

echo "📦 Copiando ${#FILES[@]} archivos al DGX..."
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  → $file"
        scp "$file" "$DGX_USER@$DGX_IP:$DGX_PATH/" || {
            echo "    ⚠️  Error copiando $file"
        }
    else
        echo "  ⚠️  Archivo no encontrado: $file"
    fi
done
echo ""

echo "✅ Sincronización completada"
echo ""
echo "═══════════════════════════════════════════════════════"
echo "📋 SIGUIENTE PASO EN EL DGX:"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Cuando el mini PC esté configurado con dual WiFi,"
echo "editar el archivo .env del backend en el DGX:"
echo ""
echo "  cd $DGX_PATH/backend"
echo "  nano .env"
echo ""
echo "Agregar o modificar:"
echo "  DRONE_BRIDGE_URL=http://192.168.20.X:9090"
echo ""
echo "Donde X es la IP del mini PC en la red 5G"
echo "(la IP que muestra setup_minipc_local.sh al terminar)"
echo ""
