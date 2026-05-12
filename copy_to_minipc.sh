#!/bin/bash
# Script para copiar todos los archivos necesarios al mini PC
# EJECUTAR DESDE LA LAPTOP cuando el mini PC esté accesible

set -e

MINI_PC_IP="192.168.40.128"
MINI_PC_USER="karaoke"
MINI_PC_PASS="1234"

echo "════════════════════════════════════════════════════════════════"
echo "📦 COPIAR ARCHIVOS AL MINI PC - CONFIGURACIÓN DUAL WiFi + DRON"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar conectividad
echo "🔍 Verificando conectividad con el mini PC ($MINI_PC_IP)..."
if ! timeout 3 ping -c 1 $MINI_PC_IP >/dev/null 2>&1; then
    echo "❌ ERROR: Mini PC no accesible"
    echo ""
    echo "El mini PC podría estar:"
    echo "  • Apagado"
    echo "  • Conectado solo al Bebop (sin acceso a red principal)"
    echo "  • En otra IP"
    echo ""
    echo "Soluciones:"
    echo "  1. Verifica que el mini PC esté en la red Casa_HS_Wifi (NO Bebop)"
    echo "  2. Encuentra su IP: nmap -sn 192.168.40.0/24"
    echo "  3. O conéctate directamente al mini PC con monitor+teclado"
    exit 1
fi

echo "✅ Mini PC accesible"
echo ""

# Listar archivos a copiar
echo "📋 Archivos a copiar:"
FILES=(
    "setup_dual_wifi_auto.sh"
    "configure_dual_wifi_dgx.sh"
    "drone_bridge.py"
    "fly_bebop_10s.sh"
    "README_DUAL_WIFI_DGX.md"
    "INTEGRACION_DGX_DRON.md"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        size=$(ls -lh "$file" | awk '{print $5}')
        echo "  ✓ $file ($size)"
    else
        echo "  ✗ $file (NO ENCONTRADO)"
    fi
done
echo ""

# Copiar con scp
echo "📤 Copiando archivos..."
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  Copiando $file..."
        if command -v sshpass >/dev/null 2>&1; then
            sshpass -p "$MINI_PC_PASS" scp -o StrictHostKeyChecking=no "$file" $MINI_PC_USER@$MINI_PC_IP:~ 2>&1
        else
            scp "$file" $MINI_PC_USER@$MINI_PC_IP:~
        fi
    fi
done
echo ""

# Verificar en el mini PC
echo "✅ Archivos copiados"
echo ""
echo "🔍 Verificando en el mini PC..."
if command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$MINI_PC_PASS" ssh -o StrictHostKeyChecking=no $MINI_PC_USER@$MINI_PC_IP "ls -lh ${FILES[@]} 2>/dev/null | tail -n +2" || echo "  (no se pudo verificar)"
else
    ssh $MINI_PC_USER@$MINI_PC_IP "ls -lh ${FILES[@]} 2>/dev/null | tail -n +2" || echo "  (no se pudo verificar)"
fi
echo ""

# Instrucciones finales
echo "════════════════════════════════════════════════════════════════"
echo "✅ ARCHIVOS COPIADOS EXITOSAMENTE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📋 Siguiente paso: EJECUTAR EN EL MINI PC"
echo ""
echo "Conéctate al mini PC:"
echo "  ssh $MINI_PC_USER@$MINI_PC_IP"
echo ""
echo "Ejecuta el script de configuración:"
echo "  chmod +x setup_dual_wifi_auto.sh"
echo "  ./setup_dual_wifi_auto.sh"
echo ""
echo "Eso configurará:"
echo "  • D-Link → Casa_HS_Wifi 5G (red DGX)"
echo "  • Atheros → Bebop2-045265 (dron)"
echo ""
echo "Duración: ~30 segundos"
echo ""
echo "Después, inicia el drone bridge:"
echo "  nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
