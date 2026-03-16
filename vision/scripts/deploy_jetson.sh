#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# Seedy Vision — Deploy to Jetson Orin Nano
# Empaqueta modelos + código y despliega al Jetson
# ─────────────────────────────────────────────────────
set -euo pipefail

VISION_DIR="$(cd "$(dirname "$0")/.." && pwd)"
JETSON_USER="${JETSON_USER:-seedy}"
JETSON_HOST="${JETSON_HOST:-jetson-seedy.local}"
JETSON_DIR="${JETSON_DIR:-/home/seedy/seedy-vision}"
MODELS_DIR="${VISION_DIR}/models"

echo "╔══════════════════════════════════════════╗"
echo "║  Seedy Vision — Deploy to Jetson         ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Host:  ${JETSON_USER}@${JETSON_HOST}"
echo "  Dir:   ${JETSON_DIR}"
echo ""

# ── 1. Verificar modelos exportados a TensorRT ──────
echo "── 1. Verificando modelos exportados ──"

EXPORT_MODELS=()
for engine in "${MODELS_DIR}"/*/weights/best.engine 2>/dev/null; do
  if [[ -f "$engine" ]]; then
    task=$(basename "$(dirname "$(dirname "$engine")")")
    size=$(du -h "$engine" | cut -f1)
    echo "  ✅ $task → $engine ($size)"
    EXPORT_MODELS+=("$engine")
  fi
done

# Fallback: buscar ONNX si no hay engine
if [[ ${#EXPORT_MODELS[@]} -eq 0 ]]; then
  echo "  ⚠  No se encontraron modelos .engine"
  echo "  Buscando .onnx..."
  for onnx in "${MODELS_DIR}"/*/weights/best.onnx 2>/dev/null; do
    if [[ -f "$onnx" ]]; then
      echo "  ✅ $onnx"
      EXPORT_MODELS+=("$onnx")
    fi
  done
fi

if [[ ${#EXPORT_MODELS[@]} -eq 0 ]]; then
  echo "  ❌ No hay modelos exportados. Ejecuta primero:"
  echo "     python train_yolo.py export --task detection"
  exit 1
fi

# ── 2. Preparar paquete de deploy ───────────────────
echo ""
echo "── 2. Preparando paquete de deploy ──"

DEPLOY_DIR=$(mktemp -d)/seedy-vision
mkdir -p "${DEPLOY_DIR}"/{models,scripts,configs,events}

# Código Python
cp "${VISION_DIR}/jetson_inference.py" "${DEPLOY_DIR}/"
cp "${VISION_DIR}/config.py" "${DEPLOY_DIR}/"
cp -r "${VISION_DIR}/utils" "${DEPLOY_DIR}/"

# Configs
cp "${VISION_DIR}/configs/"*.yaml "${DEPLOY_DIR}/configs/" 2>/dev/null || true

# Modelos
for model in "${EXPORT_MODELS[@]}"; do
  cp "$model" "${DEPLOY_DIR}/models/"
done

# Requirements para Jetson (sin CUDA packages — ya incluidos en JetPack)
cat > "${DEPLOY_DIR}/requirements_jetson.txt" << 'EOF'
ultralytics>=8.3.0
opencv-python-headless>=4.9.0
paho-mqtt>=2.0.0
httpx>=0.27.0
rich>=13.7.0
pyyaml>=6.0
numpy>=1.24.0
EOF

# Script de inicio
cat > "${DEPLOY_DIR}/start.sh" << 'STARTEOF'
#!/usr/bin/env bash
# Seedy Vision — Start inference on Jetson
set -euo pipefail

cd "$(dirname "$0")"

# Activar venv si existe
if [[ -d ".venv" ]]; then
  source .venv/bin/activate
fi

# Defaults (editar según cámara)
MODEL="${MODEL:-models/best.engine}"
SOURCE="${SOURCE:-0}"
CAMERA_ID="${CAMERA_ID:-cam0}"
MQTT_TOPIC="${MQTT_TOPIC:-seedy/vision/${CAMERA_ID}}"
CONF="${CONF:-0.4}"
IMGSZ="${IMGSZ:-640}"

echo "🚀 Seedy Vision — Starting inference"
echo "  Model:  $MODEL"
echo "  Source: $SOURCE"
echo "  MQTT:   $MQTT_TOPIC"
echo ""

python3 jetson_inference.py \
  --model "$MODEL" \
  --source "$SOURCE" \
  --camera-id "$CAMERA_ID" \
  --mqtt-topic "$MQTT_TOPIC" \
  --conf "$CONF" \
  --imgsz "$IMGSZ" \
  --events-dir events
STARTEOF
chmod +x "${DEPLOY_DIR}/start.sh"

# Systemd service para auto-start
cat > "${DEPLOY_DIR}/seedy-vision.service" << 'SVCEOF'
[Unit]
Description=Seedy Vision Edge Inference
After=network.target docker.service
Wants=network.target

[Service]
Type=simple
User=seedy
WorkingDirectory=/home/seedy/seedy-vision
ExecStart=/home/seedy/seedy-vision/start.sh
Restart=always
RestartSec=10
Environment=MODEL=models/best.engine
Environment=SOURCE=0
Environment=CAMERA_ID=cam0
Environment=MQTT_TOPIC=seedy/vision/cam0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

echo "  ✅ Paquete preparado: ${DEPLOY_DIR}"
du -sh "${DEPLOY_DIR}"

# ── 3. Sync al Jetson ──────────────────────────────
echo ""
echo "── 3. Sincronizando con Jetson ──"
echo "  Destino: ${JETSON_USER}@${JETSON_HOST}:${JETSON_DIR}"
echo ""

# Verificar conectividad
if ! ssh -o ConnectTimeout=5 "${JETSON_USER}@${JETSON_HOST}" "echo ok" &>/dev/null; then
  echo "  ⚠  No se puede conectar al Jetson (${JETSON_HOST})"
  echo "  El paquete está listo en: ${DEPLOY_DIR}"
  echo ""
  echo "  Para copiar manualmente:"
  echo "  scp -r ${DEPLOY_DIR} ${JETSON_USER}@${JETSON_HOST}:${JETSON_DIR}"
  echo ""
  echo "  En el Jetson:"
  echo "  cd ${JETSON_DIR}"
  echo "  python3 -m venv .venv && source .venv/bin/activate"
  echo "  pip install -r requirements_jetson.txt"
  echo "  sudo cp seedy-vision.service /etc/systemd/system/"
  echo "  sudo systemctl enable --now seedy-vision"
  exit 0
fi

rsync -avz --progress \
  "${DEPLOY_DIR}/" \
  "${JETSON_USER}@${JETSON_HOST}:${JETSON_DIR}/"

echo ""
echo "  ✅ Sincronizado"

# ── 4. Setup en Jetson ──────────────────────────────
echo ""
echo "── 4. Configurando en Jetson ──"

ssh "${JETSON_USER}@${JETSON_HOST}" << REMOTEEOF
cd ${JETSON_DIR}

# Crear venv si no existe
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

# Instalar dependencias
pip install -q -r requirements_jetson.txt

# Instalar servicio systemd
sudo cp seedy-vision.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable seedy-vision

echo ""
echo "✅ Jetson configurado"
echo ""
echo "Para arrancar:"
echo "  sudo systemctl start seedy-vision"
echo "  journalctl -u seedy-vision -f"
REMOTEEOF

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ Deploy completado                    ║"
echo "║                                          ║"
echo "║  Arrancar:                               ║"
echo "║  ssh ${JETSON_USER}@${JETSON_HOST}       ║"
echo "║  sudo systemctl start seedy-vision       ║"
echo "║                                          ║"
echo "║  Logs:                                   ║"
echo "║  journalctl -u seedy-vision -f           ║"
echo "╚══════════════════════════════════════════╝"
