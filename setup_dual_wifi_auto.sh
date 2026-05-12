#!/bin/bash
# Configuración Dual WiFi AUTOMATIZADA para DGX → Mini PC → Bebop
# Contraseña WiFi 5G incluida (ErizoDespenado22)
#
# ARQUITECTURA:
# - DGX (192.168.20.57) en Casa_HS_Wifi 5G → detecta gorriones → envía orden
# - Mini PC con 2 WiFi simultáneas:
#     • D-Link → Casa_HS_Wifi 5G (default route, acceso DGX)
#     • Atheros → Bebop2-045265 (never-default, control dron)
# - Bebop (192.168.42.1) → recibe órdenes vía Olympe
#
# EJECUTAR EN EL MINI PC:
#   chmod +x setup_dual_wifi_auto.sh
#   ./setup_dual_wifi_auto.sh

set -e

WIFI_5G_SSID="Casa_HS_Wifi 5G"
WIFI_5G_PASS="ErizoDespenado22"
BEBOP_SSID="Bebop2-045265"

echo "════════════════════════════════════════════════════════════════"
echo "🔧 CONFIGURACIÓN DUAL WiFi AUTOMATIZADA - DGX + BEBOP"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Arquitectura:"
echo "  DGX (192.168.20.57) → Mini PC (dual WiFi) → Bebop (192.168.42.1)"
echo ""
echo "Tarjetas:"
echo "  • D-Link DWA-140 → Casa_HS_Wifi 5G (red DGX 192.168.20.x)"
echo "  • Atheros AR9271 → Bebop2-045265 (red dron 192.168.42.x)"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Detectar interfaces WiFi
echo "🔍 Detectando interfaces WiFi..."
WIFI_IFACES=$(nmcli device | grep wifi | awk '{print $1}' | grep -v 'p2p-dev' || true)
IFACE_COUNT=$(echo "$WIFI_IFACES" | grep -c '^' || true)

if [ "$IFACE_COUNT" -lt 2 ]; then
    echo "❌ ERROR: Se necesitan 2 interfaces WiFi, solo hay $IFACE_COUNT"
    echo ""
    echo "Conecta el adaptador D-Link DWA-140 y reinicia el mini PC"
    exit 1
fi

# Identificar por MAC
DLINK_IFACE=$(echo "$WIFI_IFACES" | xargs -I {} sh -c 'ip link show {} | grep -q "00:26:5a:16:86:dc" && echo {}' || true)
ATHEROS_IFACE=$(echo "$WIFI_IFACES" | xargs -I {} sh -c 'ip link show {} | grep -q "c0:1c:30:43:0f:bc" && echo {}' || true)

if [ -z "$DLINK_IFACE" ] || [ -z "$ATHEROS_IFACE" ]; then
    echo "❌ ERROR: No se pudieron identificar las interfaces por MAC"
    echo ""
    echo "MACs esperadas:"
    echo "  D-Link:  00:26:5a:16:86:dc"
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
echo "   D-Link:  $DLINK_IFACE"
echo "   Atheros: $ATHEROS_IFACE"
echo ""

# PASO 1: Desconectar todo
echo "════════════════════════════════════════════════════════════════"
echo "🔄 PASO 1: Limpiando conexiones existentes"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Desconectar todas las WiFi
for conn in $(nmcli -t -f NAME connection show | grep -i "casa\|bebop"); do
    echo "Desconectando: $conn"
    echo "1234" | sudo -S nmcli connection down "$conn" 2>/dev/null || true
done
sleep 2

echo "✅ Conexiones limpiadas"
echo ""

# PASO 2: Conectar Casa_HS_Wifi 5G en D-Link
echo "════════════════════════════════════════════════════════════════"
echo "📡 PASO 2: Conectar Casa_HS_Wifi 5G → D-Link (red DGX)"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Eliminar conexión 5G anterior si existe
CASA_5G_OLD=$(nmcli connection show | grep -i "Casa_HS.*5\|5G" | awk -F'  ' '{print $1}' || true)
if [ -n "$CASA_5G_OLD" ]; then
    echo "Eliminando conexión 5G anterior: $CASA_5G_OLD"
    echo "1234" | sudo -S nmcli connection delete "$CASA_5G_OLD" 2>/dev/null || true
fi

# Crear conexión 5G nueva con configuración correcta
echo "Creando conexión Casa_HS_Wifi 5G en $DLINK_IFACE..."
echo "1234" | sudo -S nmcli device wifi connect "$WIFI_5G_SSID" password "$WIFI_5G_PASS" ifname "$DLINK_IFACE"
sleep 4

# Obtener nombre de la conexión creada
CASA_5G=$(nmcli connection show | grep -i "Casa_HS.*5\|5G" | head -1 | awk -F'  ' '{print $1}')

if [ -z "$CASA_5G" ]; then
    echo "❌ ERROR: No se pudo conectar a Casa_HS_Wifi 5G"
    echo ""
    echo "Redes 5GHz disponibles:"
    nmcli device wifi list | grep "5 GHz" | head -5
    exit 1
fi

echo "Configurando $CASA_5G..."
echo "1234" | sudo -S nmcli connection modify "$CASA_5G" connection.interface-name "$DLINK_IFACE"
echo "1234" | sudo -S nmcli connection modify "$CASA_5G" ipv4.route-metric 100
echo "1234" | sudo -S nmcli connection modify "$CASA_5G" ipv6.method disabled
echo "1234" | sudo -S nmcli connection modify "$CASA_5G" connection.autoconnect yes
echo "1234" | sudo -S nmcli connection modify "$CASA_5G" connection.autoconnect-priority 100

# Verificar IP
IP_5G=$(ip addr show "$DLINK_IFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)

echo "✅ Casa_HS_Wifi 5G conectada:"
echo "   Interface: $DLINK_IFACE"
echo "   IP: $IP_5G"
echo "   Metric: 100 (default route)"
echo ""

# Verificar acceso al DGX
echo "🔍 Verificando acceso al DGX (192.168.20.57)..."
if timeout 3 ping -c 2 192.168.20.57 >/dev/null 2>&1; then
    echo "✅ DGX accesible"
else
    echo "⚠️  DGX no responde"
    echo "   Verifica que esté encendido y en la red 5G"
fi
echo ""

# PASO 3: Configurar Bebop en Atheros (never-default)
echo "════════════════════════════════════════════════════════════════"
echo "🚁 PASO 3: Configurar Bebop2-045265 → Atheros"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar si conexión Bebop existe
BEBOP_CONN=$(nmcli connection show | grep "$BEBOP_SSID" | awk -F'  ' '{print $1}' || true)

if [ -z "$BEBOP_CONN" ]; then
    echo "Creando conexión Bebop..."
    # Bebop suele no tener contraseña
    echo "1234" | sudo -S nmcli device wifi connect "$BEBOP_SSID" ifname "$ATHEROS_IFACE" 2>/dev/null || true
    sleep 3
    BEBOP_CONN="$BEBOP_SSID"
fi

echo "Configurando $BEBOP_CONN en $ATHEROS_IFACE..."
echo "1234" | sudo -S nmcli connection modify "$BEBOP_CONN" connection.interface-name "$ATHEROS_IFACE"
echo "1234" | sudo -S nmcli connection modify "$BEBOP_CONN" ipv4.never-default yes
echo "1234" | sudo -S nmcli connection modify "$BEBOP_CONN" ipv4.route-metric 200
echo "1234" | sudo -S nmcli connection modify "$BEBOP_CONN" ipv6.method disabled
echo "1234" | sudo -S nmcli connection modify "$BEBOP_CONN" connection.autoconnect no

echo "✅ Bebop2-045265 configurado:"
echo "   Interface: $ATHEROS_IFACE"
echo "   Never-default: sí"
echo "   Metric: 200"
echo "   Autoconnect: no (manual)"
echo ""

# PASO 4: Conectar Bebop y verificar dual WiFi
echo "════════════════════════════════════════════════════════════════"
echo "🔗 PASO 4: Activar Bebop (dual WiFi simultáneo)"
echo "════════════════════════════════════════════════════════════════"
echo ""

echo "Conectando al Bebop..."
echo "1234" | sudo -S nmcli connection up "$BEBOP_CONN"
sleep 4

# Verificar conexiones activas
echo "✅ Conexiones activas:"
nmcli connection show --active | grep -E "NAME|$CASA_5G|$BEBOP_CONN" | sed 's/^/   /'
echo ""

# Verificar IPs
echo "📊 Direcciones IP:"
IP_5G=$(ip addr show "$DLINK_IFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1 || echo "N/A")
IP_BEBOP=$(ip addr show "$ATHEROS_IFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1 || echo "N/A")
echo "   D-Link ($DLINK_IFACE):  $IP_5G (red DGX)"
echo "   Atheros ($ATHEROS_IFACE): $IP_BEBOP (red Bebop)"
echo ""

# Verificar rutas
echo "🛣️  Tabla de rutas:"
ip route show | grep -E 'default|192.168' | sed 's/^/   /'
echo ""

# Test de conectividad
echo "════════════════════════════════════════════════════════════════"
echo "🧪 TESTS DE CONECTIVIDAD"
echo "════════════════════════════════════════════════════════════════"
echo ""

echo "Test 1: DGX (192.168.20.57)..."
if timeout 3 ping -c 2 192.168.20.57 >/dev/null 2>&1; then
    echo "   ✅ DGX accesible vía D-Link"
else
    echo "   ❌ DGX no responde"
fi

echo "Test 2: Bebop (192.168.42.1)..."
if timeout 3 ping -c 2 192.168.42.1 >/dev/null 2>&1; then
    echo "   ✅ Bebop accesible vía Atheros"
else
    echo "   ❌ Bebop no responde (verifica que esté encendido)"
fi

echo "Test 3: Internet (8.8.8.8)..."
if timeout 3 ping -c 2 8.8.8.8 >/dev/null 2>&1; then
    echo "   ✅ Internet accesible vía D-Link"
else
    echo "   ⚠️  Sin acceso a internet"
fi
echo ""

# RESULTADO FINAL
echo "════════════════════════════════════════════════════════════════"
echo "✅ CONFIGURACIÓN DUAL WiFi COMPLETADA"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Estado final:"
echo "  • D-Link ($DLINK_IFACE): $IP_5G → DGX + Internet"
echo "  • Atheros ($ATHEROS_IFACE): $IP_BEBOP → Bebop"
echo ""
echo "El mini PC ahora tiene acceso simultáneo a:"
echo "  1. DGX en 192.168.20.57 (vía D-Link)"
echo "  2. Bebop en 192.168.42.1 (vía Atheros)"
echo "  3. Internet (vía D-Link, default route)"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📋 SIGUIENTES PASOS"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "1. Iniciar drone_bridge.py:"
echo "   cd /home/karaoke"
echo "   nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &"
echo ""
echo "2. Test de vuelo:"
echo "   ./fly_bebop_10s.sh"
echo ""
echo "3. El DGX puede enviar comandos a:"
echo "   http://$IP_5G:9090/fly"
echo ""
echo "4. Para reconectar Bebop en el futuro:"
echo "   sudo nmcli connection up Bebop2-045265"
echo ""
