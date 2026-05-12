#!/bin/bash
# CONFIGURACIÓN DUAL WiFi - EJECUTAR DIRECTAMENTE EN EL MINI PC
# (con monitor y teclado físico, ya que no está accesible remotamente)

cd /home/karaoke

echo "════════════════════════════════════════════════════════════════"
echo "🔧 CONFIGURACIÓN DUAL WiFi AUTOMÁTICA - EJECUCIÓN LOCAL"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Detectar interfaces WiFi
echo "Detectando interfaces WiFi..."
WIFI_IFACES=$(nmcli device | grep wifi | awk '{print $1}' | grep -v 'p2p-dev')
DLINK_IFACE=$(echo "$WIFI_IFACES" | xargs -I {} sh -c 'ip link show {} | grep -q "00:26:5a:16:86:dc" && echo {}')
ATHEROS_IFACE=$(echo "$WIFI_IFACES" | xargs -I {} sh -c 'ip link show {} | grep -q "c0:1c:30:43:0f:bc" && echo {}')

if [ -z "$DLINK_IFACE" ] || [ -z "$ATHEROS_IFACE" ]; then
    echo "❌ ERROR: No se detectaron ambas interfaces WiFi"
    echo "   D-Link:  $DLINK_IFACE"
    echo "   Atheros: $ATHEROS_IFACE"
    echo ""
    echo "Verifica que el D-Link DWA-140 esté conectado por USB"
    exit 1
fi

echo "  ✓ D-Link:  $DLINK_IFACE"
echo "  ✓ Atheros: $ATHEROS_IFACE"
echo ""

# Desconectar todo
echo "Limpiando conexiones anteriores..."
for conn in $(nmcli -t -f NAME connection show | grep -i "casa\|bebop"); do
    nmcli connection down "$conn" 2>/dev/null || true
done
sleep 2
echo "✓ Desconectado"
echo ""

# Conectar Casa_HS_Wifi 5G en D-Link
echo "Conectando D-Link → Casa_HS_Wifi 5G (red DGX)..."
nmcli device wifi connect "Casa_HS_Wifi 5G" password "ErizoDespenado22" ifname "$DLINK_IFACE"
sleep 4

# Configurar conexión 5G
CASA_5G=$(nmcli connection show | grep -i "Casa_HS.*5\|5G" | head -1 | awk -F'  ' '{print $1}')
if [ -z "$CASA_5G" ]; then
    echo "❌ ERROR: No se pudo conectar a Casa_HS_Wifi 5G"
    exit 1
fi

nmcli connection modify "$CASA_5G" connection.interface-name "$DLINK_IFACE"
nmcli connection modify "$CASA_5G" ipv4.route-metric 100
nmcli connection modify "$CASA_5G" ipv6.method disabled
nmcli connection modify "$CASA_5G" connection.autoconnect yes
nmcli connection modify "$CASA_5G" connection.autoconnect-priority 100

IP_5G=$(ip addr show "$DLINK_IFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
echo "✓ Casa_HS_Wifi 5G configurada"
echo "  IP en red DGX: $IP_5G"
echo ""

# Configurar Bebop en Atheros
echo "Configurando Atheros → Bebop2-045265..."
BEBOP_CONN=$(nmcli connection show | grep "Bebop2-045265" | awk -F'  ' '{print $1}')

if [ -z "$BEBOP_CONN" ]; then
    echo "  Creando nueva conexión Bebop..."
    nmcli device wifi connect "Bebop2-045265" ifname "$ATHEROS_IFACE" 2>/dev/null || true
    sleep 3
    BEBOP_CONN="Bebop2-045265"
fi

nmcli connection modify "$BEBOP_CONN" connection.interface-name "$ATHEROS_IFACE"
nmcli connection modify "$BEBOP_CONN" ipv4.never-default yes
nmcli connection modify "$BEBOP_CONN" ipv4.route-metric 200
nmcli connection modify "$BEBOP_CONN" ipv6.method disabled
nmcli connection modify "$BEBOP_CONN" connection.autoconnect no

echo "✓ Bebop2-045265 configurado"
echo ""

# Conectar al Bebop (si está encendido)
echo "Conectando al Bebop (si está encendido)..."
if nmcli connection up "$BEBOP_CONN" 2>/dev/null; then
    sleep 4
    IP_BEBOP=$(ip addr show "$ATHEROS_IFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
    echo "✓ Bebop conectado: $IP_BEBOP"
    
    # Test ping
    if timeout 3 ping -c 1 192.168.42.1 >/dev/null 2>&1; then
        echo "✓ Bebop accesible en 192.168.42.1"
    else
        echo "⚠ Bebop no responde (verifica que esté encendido)"
    fi
else
    echo "⚠ No se pudo conectar al Bebop (puede estar apagado)"
fi
echo ""

# Iniciar drone_bridge.py
echo "Iniciando drone_bridge.py..."
cd /home/karaoke

# Matar proceso anterior si existe
pkill -f drone_bridge.py 2>/dev/null || true
sleep 1

nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &
BRIDGE_PID=$!
sleep 2

if ps -p $BRIDGE_PID > /dev/null; then
    echo "✓ Bridge iniciado (PID: $BRIDGE_PID)"
else
    echo "⚠ Bridge no se inició correctamente, revisa drone_bridge.log"
fi
echo ""

# Resumen final
echo "════════════════════════════════════════════════════════════════"
echo "✅ CONFIGURACIÓN COMPLETADA"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Estado:"
echo "  • D-Link ($DLINK_IFACE):  $IP_5G → Red DGX (Casa_HS_Wifi 5G)"
echo "  • Atheros ($ATHEROS_IFACE): ${IP_BEBOP:-N/A} → Bebop"
echo "  • drone_bridge.py: puerto 9090 (PID: $BRIDGE_PID)"
echo ""
echo "Conexiones activas:"
nmcli connection show --active | grep -E "NAME|$CASA_5G|$BEBOP_CONN" | head -4
echo ""
echo "Tabla de rutas:"
ip route show | grep -E "default|192.168" | sed 's/^/  /'
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📋 CONFIGURAR EN EL DGX"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "1. Editar /backend/.env en el DGX:"
echo "   DRONE_BRIDGE_URL=http://$IP_5G:9090"
echo ""
echo "2. Reiniciar backend:"
echo "   docker compose restart seedy-backend"
echo ""
echo "3. Prueba de vuelo desde el DGX:"
echo "   curl -X POST http://localhost:8000/api/dron/sparrow-deterrent"
echo ""
echo "4. O prueba local desde aquí:"
echo "   ./fly_bebop_10s.sh"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
