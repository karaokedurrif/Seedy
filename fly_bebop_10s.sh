#!/bin/bash
# VUELO BEBOP 2 - 10 segundos, 2m altura, descenso lento
# EJECUTAR EN EL MINI PC DIRECTAMENTE

set -e

echo "═══════════════════════════════════════════════════════"
echo "🚁 VUELO VERTICAL BEBOP 2"
echo "   • Altura: 2 metros"
echo "   • Hover: 10 segundos"
echo "   • Descenso: Lento y controlado"
echo "═══════════════════════════════════════════════════════"
echo ""

# 1. Verificar/Conectar al Bebop
BEBOP_CONNECTED=$(nmcli connection show --active | grep -c "Bebop2-045265" || true)

if [ "$BEBOP_CONNECTED" -eq 0 ]; then
    echo "📡 Conectando al Bebop WiFi..."
    echo "1234" | sudo -S nmcli connection up Bebop2-045265
    sleep 5
    echo "✅ Conectado"
else
    echo "✅ Ya conectado al Bebop"
fi

echo ""
echo "🔍 Verificando conectividad con el dron (192.168.42.1)..."
if timeout 5 ping -c 2 192.168.42.1 >/dev/null 2>&1; then
    echo "✅ Dron accesible"
else
    echo "❌ DRON NO RESPONDE"
    echo ""
    echo "Verifica que:"
    echo "  • El Bebop esté encendido"
    echo "  • Los LEDs estén en verde"
    echo "  • Estás en la WiFi Bebop2-045265"
    exit 1
fi

echo ""
echo "📋 Verificando drone_bridge.py..."
if pgrep -f "drone_bridge.py" >/dev/null; then
    echo "⚠️  Bridge ya está ejecutándose, reiniciando..."
    pkill -f "drone_bridge.py"
    sleep 2
fi

echo "🚀 Iniciando drone bridge actualizado..."
cd /home/karaoke
nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &
BRIDGE_PID=$!
echo "   PID: $BRIDGE_PID"
sleep 3

echo ""
echo "🔌 Conectando al dron via Olympe..."
CONNECT_RESULT=$(curl -s -X POST http://localhost:9090/connect 2>&1)
echo "$CONNECT_RESULT"

if echo "$CONNECT_RESULT" | grep -q '"status"'; then
    echo "✅ Conexión Olympe establecida"
else
    echo "⚠️  Respuesta inesperada del bridge"
fi
sleep 2

echo ""
echo "═══════════════════════════════════════════════════════"
echo "🚀 LANZANDO VUELO"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Parámetros:"
echo "  • Altura: 2 metros"
echo "  • Hover: 10 segundos"
echo "  • Descenso: Gradual en 2 pasos"
echo ""
echo "Enviando comando..."
sleep 1

FLIGHT_RESULT=$(curl -s -X POST http://localhost:9090/fly 2>&1)
echo ""
echo "$FLIGHT_RESULT"
echo ""

if echo "$FLIGHT_RESULT" | grep -q '"status".*"completed"'; then
    echo "═══════════════════════════════════════════════════════"
    echo "✅ ¡VUELO COMPLETADO EXITOSAMENTE!"
    echo "═══════════════════════════════════════════════════════"
    
    # Extraer duración
    DURATION=$(echo "$FLIGHT_RESULT" | grep -o '"duration_s":[0-9.]*' | cut -d':' -f2)
    if [ -n "$DURATION" ]; then
        echo "⏱️  Duración total: ${DURATION}s"
    fi
elif echo "$FLIGHT_RESULT" | grep -q '"status"'; then
    echo "📊 Vuelo en progreso o estado intermedio"
    echo "$FLIGHT_RESULT" | python3 -m json.tool 2>/dev/null || echo "$FLIGHT_RESULT"
else
    echo "⚠️  Respuesta inesperada"
    echo "$FLIGHT_RESULT"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ Script finalizado"
echo "═══════════════════════════════════════════════════════"
echo ""
