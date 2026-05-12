#!/bin/bash
# Configuración Dual WiFi para integración DGX → Mini PC → Bebop
# 
# ARQUITECTURA:
# - DGX (192.168.20.57) en Casa_HS_Wifi 5G → detecta gorriones → envía orden
# - Mini PC (192.168.40.128) con 2 WiFi:
#     • D-Link (wlx00265a1686dc) → Casa_HS_Wifi 5G (prioritaria, DGX)
#     • Atheros (wlxc01c30430fbc) → Bebop2-045265 (sin default route)
# - Bebop (192.168.42.1) → recibe órdenes vía Olympe
#
# EJECUTAR EN EL MINI PC:
#   chmod +x configure_dual_wifi_dgx.sh
#   ./configure_dual_wifi_dgx.sh

set -e

echo "════════════════════════════════════════════════════════════════"
echo "🔧 CONFIGURACIÓN DUAL WiFi - DGX + BEBOP"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Arquitectura objetivo:"
echo "  DGX (192.168.20.57) → Mini PC (dual WiFi) → Bebop (192.168.42.1)"
echo ""
echo "Tarjetas WiFi:"
echo "  • D-Link DWA-140 → Casa_HS_Wifi 5G (red DGX, default route)"
echo "  • Atheros AR9271 → Bebop2-045265 (never-default)"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar que estamos en el mini PC
if [ "$USER" != "karaoke" ]; then
    echo "⚠️  Este script debe ejecutarse en el mini PC (user: karaoke)"
    echo "   Conéctate con: ssh karaoke@192.168.40.128"
    exit 1
fi

# Detectar interfaces WiFi
echo "🔍 Detectando interfaces WiFi..."
WIFI_IFACES=$(nmcli device | grep wifi | awk '{print $1}' | grep -v 'p2p-dev' || true)
IFACE_COUNT=$(echo "$WIFI_IFACES" | grep -c '^' || true)

echo "   Interfaces encontradas: $IFACE_COUNT"
for iface in $WIFI_IFACES; do
    MAC=$(ip link show "$iface" | grep "link/ether" | awk '{print $2}')
    echo "     • $iface ($MAC)"
done
echo ""

if [ "$IFACE_COUNT" -lt 2 ]; then
    echo "❌ ERROR: Se necesitan 2 interfaces WiFi, solo hay $IFACE_COUNT"
    echo ""
    echo "Conecta el adaptador USB D-Link DWA-140 y reinicia el mini PC"
    exit 1
fi

# Identificar interfaces por MAC
DLINK_IFACE=$(echo "$WIFI_IFACES" | xargs -I {} sh -c 'ip link show {} | grep -q "00:26:5a:16:86:dc" && echo {}' || true)
ATHEROS_IFACE=$(echo "$WIFI_IFACES" | xargs -I {} sh -c 'ip link show {} | grep -q "c0:1c:30:43:0f:bc" && echo {}' || true)

if [ -z "$DLINK_IFACE" ] || [ -z "$ATHEROS_IFACE" ]; then
    echo "❌ ERROR: No se pudieron identificar las interfaces por MAC"
    echo ""
    echo "Se esperaba:"
    echo "  D-Link: 00:26:5a:16:86:dc"
    echo "  Atheros: c0:1c:30:43:0f:bc"
    echo ""
    echo "MACs encontradas:"
    for iface in $WIFI_IFACES; do
        MAC=$(ip link show "$iface" | grep "link/ether" | awk '{print $2}')
        echo "  $iface: $MAC"
    done
    exit 1
fi

echo "✅ Interfaces identificadas:"
echo "   D-Link:  $DLINK_IFACE (00:26:5a:16:86:dc)"
echo "   Atheros: $ATHEROS_IFACE (c0:1c:30:43:0f:bc)"
echo ""

# Paso 1: Configurar Casa_HS_Wifi 5G en D-Link (red DGX)
echo "════════════════════════════════════════════════════════════════"
echo "📡 PASO 1: Configurar Casa_HS_Wifi 5G → D-Link (red DGX)"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar si la conexión 5G existe
CASA_5G=$(nmcli connection show | grep -i "Casa_HS_Wifi.*5" | head -1 | awk -F'  ' '{print $1}' || true)

if [ -z "$CASA_5G" ]; then
    echo "⚠️  Casa_HS_Wifi 5G no encontrada en conexiones guardadas"
    echo ""
    echo "Conexiones WiFi disponibles:"
    nmcli connection show | grep -i casa || echo "  (ninguna con 'casa' en el nombre)"
    echo ""
    echo "Creando nueva conexión Casa_HS_Wifi 5G..."
    read -p "   Contraseña de Casa_HS_Wifi 5G: " CASA_5G_PASS
    nmcli device wifi connect "Casa_HS_Wifi 5G" password "$CASA_5G_PASS" ifname "$DLINK_IFACE"
    sleep 3
    CASA_5G=$(nmcli connection show | grep -i "Casa_HS_Wifi.*5" | head -1 | awk -F'  ' '{print $1}')
fi

echo "   Conexión 5G: $CASA_5G"
echo "   Configurando en interfaz: $DLINK_IFACE"
echo ""

# Configurar Casa_HS 5G en D-Link con default route
sudo nmcli connection modify "$CASA_5G" connection.interface-name "$DLINK_IFACE"
sudo nmcli connection modify "$CASA_5G" ipv4.route-metric 100
sudo nmcli connection modify "$CASA_5G" ipv6.method disabled
sudo nmcli connection modify "$CASA_5G" connection.autoconnect yes
sudo nmcli connection modify "$CASA_5G" connection.autoconnect-priority 100

echo "✅ Casa_HS_Wifi 5G configurada:"
echo "   • Interface: $DLINK_IFACE"
echo "   • Route metric: 100 (default route, prioritaria)"
echo "   • Autoconnect: sí (priority 100)"
echo ""

# Paso 2: Configurar Bebop en Atheros (never-default)
echo "════════════════════════════════════════════════════════════════"
echo "🚁 PASO 2: Configurar Bebop2-045265 → Atheros (never-default)"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar si la conexión Bebop existe
BEBOP_CONN=$(nmcli connection show | grep "Bebop2-045265" | awk -F'  ' '{print $1}' || true)

if [ -z "$BEBOP_CONN" ]; then
    echo "⚠️  Bebop2-045265 no encontrada, creando..."
    read -p "   Contraseña del Bebop (dejar vacío si no tiene): " BEBOP_PASS
    if [ -z "$BEBOP_PASS" ]; then
        nmcli device wifi connect "Bebop2-045265" ifname "$ATHEROS_IFACE"
    else
        nmcli device wifi connect "Bebop2-045265" password "$BEBOP_PASS" ifname "$ATHEROS_IFACE"
    fi
    sleep 3
    BEBOP_CONN="Bebop2-045265"
fi

echo "   Conexión Bebop: $BEBOP_CONN"
echo "   Configurando en interfaz: $ATHEROS_IFACE"
echo ""

# Configurar Bebop en Atheros sin default route
sudo nmcli connection modify "$BEBOP_CONN" connection.interface-name "$ATHEROS_IFACE"
sudo nmcli connection modify "$BEBOP_CONN" ipv4.never-default yes
sudo nmcli connection modify "$BEBOP_CONN" ipv4.route-metric 200
sudo nmcli connection modify "$BEBOP_CONN" ipv6.method disabled
sudo nmcli connection modify "$BEBOP_CONN" connection.autoconnect no

echo "✅ Bebop2-045265 configurado:"
echo "   • Interface: $ATHEROS_IFACE"
echo "   • Never-default: sí (no toca default route)"
echo "   • Route metric: 200 (secundaria)"
echo "   • Autoconnect: no (conectar solo cuando se use)"
echo ""

# Paso 3: Desconectar todo y conectar en orden
echo "════════════════════════════════════════════════════════════════"
echo "🔄 PASO 3: Aplicar configuración"
echo "════════════════════════════════════════════════════════════════"
echo ""

echo "Desconectando todas las WiFi..."
nmcli connection down "$CASA_5G" 2>/dev/null || true
nmcli connection down "$BEBOP_CONN" 2>/dev/null || true
sleep 2

echo "Conectando Casa_HS_Wifi 5G (D-Link, red DGX)..."
sudo nmcli connection up "$CASA_5G"
sleep 3

# Verificar IP en la red DGX
IP_5G=$(ip addr show "$DLINK_IFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
echo "✅ Conectado a Casa_HS_Wifi 5G"
echo "   IP: $IP_5G"
echo ""

# Verificar acceso al DGX
echo "🔍 Verificando acceso al DGX (192.168.20.57)..."
if timeout 3 ping -c 2 192.168.20.57 >/dev/null 2>&1; then
    echo "✅ DGX accesible"
else
    echo "⚠️  DGX no responde al ping"
    echo "   Verifica que el DGX esté encendido y en la red 5G"
fi
echo ""

# Paso 4: Test de conectividad dual (NO conectar Bebop aún)
echo "════════════════════════════════════════════════════════════════"
echo "✅ CONFIGURACIÓN COMPLETADA"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Estado actual:"
echo "  • D-Link ($DLINK_IFACE): Casa_HS_Wifi 5G → Red DGX (192.168.20.x)"
echo "  • Atheros ($ATHEROS_IFACE): Listo para Bebop (192.168.42.x)"
echo ""
echo "Rutas actuales:"
ip route show | grep -E 'default|192.168' | sed 's/^/  /'
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📋 SIGUIENTE PASO: Conectar al Bebop"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Cuando quieras conectar al Bebop (para vuelos):"
echo "  sudo nmcli connection up Bebop2-045265"
echo ""
echo "Esto mantendrá:"
echo "  • Default route por D-Link (acceso DGX + remoto)"
echo "  • Ruta específica 192.168.42.0/24 por Atheros (dron)"
echo ""
echo "Para volar:"
echo "  ./fly_bebop_10s.sh"
echo ""
echo "El DGX podrá enviar comandos a:"
echo "  http://$IP_5G:9090/fly"
echo ""
