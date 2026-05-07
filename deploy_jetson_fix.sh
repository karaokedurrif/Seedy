#!/bin/bash
# DESPLIEGUE JETSON — FIX COMPLETO (7 Mayo 2026)
# Envía código corregido y reinicia proceso edge

set -e

echo "╔════════════════════════════════════════════════════╗"
echo "║  DESPLIEGUE JETSON — FIX RTSPReader + GPU          ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

JETSON_IP="192.168.20.68"
JETSON_USER="jetson"
JETSON_PATH="~/seedy-edge"

echo "🎯 Target: $JETSON_USER@$JETSON_IP:$JETSON_PATH"
echo ""

# 1. Verificar conexión
echo "1️⃣ Verificando conexión al Jetson..."
if ! ping -c 2 -W 2 $JETSON_IP > /dev/null 2>&1; then
    echo "❌ Jetson no responde a ping en $JETSON_IP"
    echo "   Verifica que esté encendido y conectado a WiFi (192.168.20.x)"
    exit 1
fi
echo "   ✅ Jetson accesible"
echo ""

# 2. Copiar archivos corregidos
echo "2️⃣ Copiando archivos corregidos..."

FILES=(
    "jetson_edge_config.yaml"
    "jetson_edge_yolo_engine.py"
    "jetson_edge_dgx_relay.py"
    "jetson_edge_rtsp_reader.py"
    "jetson_edge_camera_supervisor.py"
    "jetson_start_all_cameras.py"
)

for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "   ⚠️  Archivo no encontrado: $file (saltando)"
        continue
    fi
    
    echo "   📄 $file..."
    scp -q "$file" "$JETSON_USER@$JETSON_IP:$JETSON_PATH/" || {
        echo "   ❌ Error copiando $file"
        exit 1
    }
done

echo "   ✅ Archivos copiados"
echo ""

# 3. Crear directorio models si no existe
echo "3️⃣ Verificando estructura de directorios..."
ssh "$JETSON_USER@$JETSON_IP" "mkdir -p $JETSON_PATH/{models,logs,events}" || {
    echo "❌ Error creando directorios"
    exit 1
}
echo "   ✅ Directorios verificados"
echo ""

# 4. Matar proceso previo si existe
echo "4️⃣ Deteniendo proceso edge previo (si existe)..."
ssh "$JETSON_USER@$JETSON_IP" "pkill -f jetson_start_all_cameras || true"
sleep 2
echo "   ✅ Proceso detenido"
echo ""

# 5. Verificar que YOLOv8s.pt existe
echo "5️⃣ Verificando modelo YOLO..."
MODEL_CHECK=$(ssh "$JETSON_USER@$JETSON_IP" "[ -f $JETSON_PATH/models/yolov8s.pt ] && echo 'OK' || echo 'MISSING'")

if [ "$MODEL_CHECK" = "MISSING" ]; then
    echo "   ⚠️  yolov8s.pt no encontrado, descargando..."
    ssh "$JETSON_USER@$JETSON_IP" "cd $JETSON_PATH && source .venv/bin/activate && python3 -c 'from ultralytics import YOLO; YOLO(\"yolov8s.pt\")'" || {
        echo "   ❌ Error descargando modelo"
        exit 1
    }
    ssh "$JETSON_USER@$JETSON_IP" "mv yolov8s.pt $JETSON_PATH/models/"
    echo "   ✅ Modelo descargado"
else
    echo "   ✅ Modelo ya existe"
fi
echo ""

# 6. Iniciar proceso en background
echo "6️⃣ Iniciando proceso edge..."
ssh "$JETSON_USER@$JETSON_IP" << 'ENDSSH'
cd ~/seedy-edge
source .venv/bin/activate

# Crear log con timestamp
LOGFILE="logs/edge_$(date +%Y%m%d_%H%M%S).log"

nohup python3 jetson_start_all_cameras.py > "$LOGFILE" 2>&1 &
PID=$!

echo "   ✅ Proceso iniciado (PID: $PID)"
echo "   📋 Log: $LOGFILE"

# Esperar 5s y verificar que sigue corriendo
sleep 5

if ps -p $PID > /dev/null; then
    echo "   ✅ Proceso confirmado activo"
else
    echo "   ❌ Proceso murió tras arranque, ver logs:"
    tail -30 "$LOGFILE"
    exit 1
fi
ENDSSH

echo ""

# 7. Monitorear logs por 10 segundos
echo "7️⃣ Monitoreando logs (10 segundos)..."
echo "────────────────────────────────────────────────────"
ssh "$JETSON_USER@$JETSON_IP" "cd $JETSON_PATH && tail -f logs/edge_*.log" &
TAIL_PID=$!

sleep 10
kill $TAIL_PID 2>/dev/null || true
echo "────────────────────────────────────────────────────"
echo ""

# 8. Verificar estado final
echo "8️⃣ Verificación final..."

echo ""
echo "   🔍 Procesos Python edge activos:"
ssh "$JETSON_USER@$JETSON_IP" "ps aux | grep jetson_start_all_cameras | grep -v grep" || echo "   ⚠️  No se detecta proceso edge"

echo ""
echo "   📊 Últimas líneas del log:"
ssh "$JETSON_USER@$JETSON_IP" "cd $JETSON_PATH && tail -5 logs/edge_*.log | head -20"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║               ✅ DESPLIEGUE COMPLETADO             ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "📋 Próximos pasos:"
echo "   1. Esperar 60 segundos para acumulación de eventos"
echo "   2. Verificar en DGX que edge events tienen tracks > 0:"
echo "      ssh daviddgx@192.168.20.57 'docker logs seedy-backend --tail 20 | grep \"Edge event\"'"
echo ""
echo "   3. Si sigue con 0 tracks, ver logs completos del Jetson:"
echo "      ssh jetson@192.168.20.68 'tail -100 ~/seedy-edge/logs/edge_*.log'"
echo ""
echo "🔧 Comandos útiles:"
echo "   • Detener edge:  ssh jetson@192.168.20.68 'pkill -f jetson_start'"
echo "   • Ver logs:      ssh jetson@192.168.20.68 'tail -f ~/seedy-edge/logs/edge_*.log'"
echo "   • Ver stats GPU: ssh jetson@192.168.20.68 'nvidia-smi'"
echo ""
