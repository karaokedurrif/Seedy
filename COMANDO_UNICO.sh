#!/bin/bash
# COMANDO ÚNICO - EJECUTAR EN LA LAPTOP
# Copia archivos y da instrucciones para ejecutar en el mini PC

cat << 'EOF'
════════════════════════════════════════════════════════════════
🚁 CONFIGURACIÓN DUAL WiFi + BEBOP - COMANDO ÚNICO
════════════════════════════════════════════════════════════════

PASO 1: Copiar archivos al mini PC
═══════════════════════════════════════════════════════════════

Ejecuta esto AHORA en tu laptop:

cd /home/davidia/Documentos/Seedy && \
scp setup_dual_wifi_auto.sh drone_bridge.py fly_bebop_10s.sh \
    README_DUAL_WIFI_DGX.md INTEGRACION_DGX_DRON.md \
    karaoke@192.168.40.128:~ && \
echo "✅ Archivos copiados"

════════════════════════════════════════════════════════════════

PASO 2: Ejecutar en el mini PC
═══════════════════════════════════════════════════════════════

Conéctate al mini PC:

ssh karaoke@192.168.40.128

Ejecuta ESTO en el mini PC (copia todo el bloque):

chmod +x setup_dual_wifi_auto.sh && \
./setup_dual_wifi_auto.sh && \
echo "" && \
echo "✅ Dual WiFi configurado" && \
echo "" && \
echo "Iniciando drone_bridge..." && \
cd /home/karaoke && \
nohup python3 drone_bridge.py > drone_bridge.log 2>&1 & \
sleep 2 && \
echo "✅ Bridge iniciado (PID: $!)" && \
echo "" && \
IP_5G=$(ip addr show | grep "inet " | grep "192.168.20" | awk '{print $2}' | cut -d'/' -f1) && \
echo "════════════════════════════════════════════════════════════════" && \
echo "✅ ¡TODO LISTO!" && \
echo "════════════════════════════════════════════════════════════════" && \
echo "" && \
echo "IP en red DGX (5G): $IP_5G" && \
echo "" && \
echo "Configura esto en el DGX (.env del backend):" && \
echo "  DRONE_BRIDGE_URL=http://$IP_5G:9090" && \
echo "" && \
echo "Prueba de vuelo:" && \
echo "  ./fly_bebop_10s.sh" && \
echo "" && \
echo "Desde el DGX:" && \
echo "  curl -X POST http://localhost:8000/api/dron/sparrow-deterrent" && \
echo ""

════════════════════════════════════════════════════════════════
📋 RESUMEN DE LO QUE HACE
════════════════════════════════════════════════════════════════

1. Copia 5 archivos al mini PC
2. Configura dual WiFi automáticamente:
   • D-Link → Casa_HS_Wifi 5G (red DGX, 192.168.20.x)
   • Atheros → Bebop2-045265 (dron, 192.168.42.x)
3. Inicia drone_bridge.py
4. Muestra la IP para configurar en el DGX

Duración total: ~45 segundos

════════════════════════════════════════════════════════════════

EOF
