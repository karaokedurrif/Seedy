#!/bin/bash
# Diagnóstico Zigbee — 13 mayo 2026
# Ejecutar en DGX Spark (192.168.20.57)

echo "═══════════════════════════════════════════════════"
echo "   DIAGNÓSTICO COMPLETO ZIGBEE → OVOSFERA"
echo "═══════════════════════════════════════════════════"
echo ""

cd /home/davidia/Documentos/Seedy || { echo "❌ No se encuentra el directorio Seedy"; exit 1; }

echo "1️⃣  MINI PC ZIGBEE (192.168.40.128)"
echo "──────────────────────────────────────────────────"
ping -c 2 -W 2 192.168.40.128 >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Mini PC responde al ping"
    echo "   → Intentando conectar por SSH (user: karaoke)..."
    timeout 5 ssh -o ConnectTimeout=3 karaoke@192.168.40.128 "hostname && docker ps --format 'table {{.Names}}\t{{.Status}}' | grep zigbee" 2>/dev/null
else
    echo "❌ MINI PC NO RESPONDE"
    echo "   Causa: Apagado, sin red, o problema de firewall"
    echo "   Acción: Verificar físicamente el Mini PC en 192.168.40.128"
fi
echo ""

echo "2️⃣  BROKER MQTT (Mosquitto en DGX)"
echo "──────────────────────────────────────────────────"
docker compose ps mosquitto
if [ $? -eq 0 ]; then
    echo "✅ Mosquitto running"
    echo "   → Esperando mensajes Zigbee2MQTT (3 segundos)..."
    timeout 3 docker compose exec -T mosquitto mosquitto_sub -h localhost -t 'zigbee2mqtt/#' -C 3 2>/dev/null
    if [ $? -eq 124 ]; then
        echo "⚠️  Timeout - Sin mensajes en topic zigbee2mqtt/# (Mini PC caído o Z2M sin publicar)"
    else
        echo "✅ Recibiendo mensajes Zigbee2MQTT"
    fi
else
    echo "❌ Mosquitto NO está corriendo"
fi
echo ""

echo "3️⃣  BACKEND SEEDY (paho-mqtt instalado?)"
echo "──────────────────────────────────────────────────"
docker compose exec -T seedy-backend python -c "import paho.mqtt.client; print('✅ paho-mqtt', paho.mqtt.client.__version__)" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ paho-mqtt NO instalado"
    echo "   Acción: docker compose exec seedy-backend pip install paho-mqtt>=2.0"
fi
echo ""

echo "4️⃣  LOGS TELEMETRY EN BACKEND"
echo "──────────────────────────────────────────────────"
TELEMETRY_LOGS=$(docker compose logs --tail=500 seedy-backend 2>&1 | grep -i 'telemetry\|mqtt' | tail -10)
if [ -z "$TELEMETRY_LOGS" ]; then
    echo "⚠️  Sin logs de Telemetry/MQTT"
    echo "   Causa probable: paho-mqtt no instalado o conexión MQTT fallando"
else
    echo "$TELEMETRY_LOGS"
fi
echo ""

echo "5️⃣  ÚLTIMA TELEMETRÍA EN /ovosfera/devices/status"
echo "──────────────────────────────────────────────────"
curl -s 'http://localhost:8000/ovosfera/devices/status' | python3 -c "
import sys, json
d = json.load(sys.stdin)
galls = d.get('gallineros', {})
for gid, gdata in galls.items():
    print(f\"Gallinero {gdata.get('gallinero_name', gid)}:\")
    sensors = gdata.get('sensors', [])
    for s in sensors:
        name = s.get('sensor', 'unknown')
        online = s.get('online', False)
        temp = s.get('temperature')
        last_seen = s.get('last_seen', 'never')
        status = '✅ ONLINE' if online else '❌ OFFLINE'
        print(f\"  {status} {name} — temp={temp}°C, last_seen={last_seen}\")
" 2>/dev/null || echo "❌ Backend no responde en :8000"
echo ""

echo "═══════════════════════════════════════════════════"
echo "   RESUMEN Y ACCIONES"
echo "═══════════════════════════════════════════════════"
echo ""
echo "PROBLEMA IDENTIFICADO:"
echo "  • Mini PC Zigbee (192.168.40.128) NO RESPONDE"
echo "  • Zigbee2MQTT no publica → Mosquitto sin datos → Backend sin telemetría"
echo ""
echo "ACCIONES REQUERIDAS:"
echo "  1. Verificar físicamente el Mini PC (encendido? WiFi conectado?)"
echo "  2. Si el Mini PC está apagado, encenderlo"
echo "  3. Verificar conectividad: ping 192.168.40.128"
echo "  4. Verificar Zigbee2MQTT: ssh karaoke@192.168.40.128 'docker ps | grep zigbee'"
echo "  5. Verificar WiFi watchdog: ssh karaoke@192.168.40.128 'systemctl status wifi-watchdog'"
echo "  6. Reiniciar Zigbee2MQTT si está UP pero sin publicar:"
echo "     ssh karaoke@192.168.40.128 'docker restart zigbee2mqtt'"
echo ""
echo "VERIFICACIÓN FINAL:"
echo "  • Después de encender Mini PC, esperar 2 min"
echo "  • Volver a ejecutar este script"
echo "  • Los sensores deberían aparecer ONLINE en hub.ovosfera.com/farm/palacio/devices"
echo ""
