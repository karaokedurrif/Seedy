# PROMPT MAESTRO — Seedy Edge **v4.5 "Jetson en el Borde, GB10 en el Cerebro"**

> **Para:** VSCode Copilot (Claude Opus 4.6 como agente) ejecutando comandos por SSH
> **Acceso primario:** `ssh daviddgx@192.168.20.57` (DGX Spark, contraseña ya gestionada)
> **Acceso secundario:** Jetson Orin Nano 8GB conectado por cable USB-C/Ethernet directo al portátil para bring-up inicial. Tras configurar, el Jetson queda en la red de cámaras 10.10.10.x conectado por Ethernet al DGX.
> **Base:** Estado documentado en `ESTADO_SEEDY_DGX_SPARK.md` (4 may 2026, 13 contenedores up, Qwen2.5-72B descargado, GPU GB10 con stats N/A pendiente de fix)
> **Objetivo:** desplegar arquitectura edge+core para vision pipeline, fix de GPU del DGX, e integrar 2 cámaras MVPSECAM PTZ Onvif que llegan en 1-2 días.
> **Versión:** Seedy v4.5
> **Plazo:** 3-4 días (incluyendo recepción física de las PTZ).
> **Aislamiento:** todo lo nuevo en módulos `backend/edge/` y `services/jetson/`. Si algo falla, el pipeline actual en DGX sigue idéntico.

---

## 0. TL;DR — Tres decisiones tomadas, justificadas

### Decisión 1: Arquitectura edge → core con Jetson como Camera Aggregator + Edge Inference

**El Jetson Orin Nano 8GB se queda físicamente en la sala donde están las cámaras**, conectado al switch que ya tienes con las 5 cámaras (3 actuales + 2 PTZ MVPSECAM entrantes). Sale por su Gigabit Ethernet con cable directo al DGX Spark.

```
       SALA DE GALLINEROS                  CASA / RACK
  ┌─────────────────────────┐         ┌──────────────────────┐
  │  Dahua  10.10.10.108    │         │                      │
  │  VIGI   10.10.10.10     │         │   DGX Spark          │
  │  VIGI   10.10.10.11     │         │   GB10, 128 GB       │
  │  PTZ    10.10.10.20 ★   │         │   192.168.20.57      │
  │  PTZ    10.10.10.21 ★   │         │                      │
  │       │                 │         │  - Qwen2.5-72B       │
  │       ▼                 │         │  - Gemini 2.5 Flash  │
  │  ┌─────────┐ Switch     │         │  - Re-ID gallery     │
  │  │ Switch  │ Gigabit    │         │  - RAG Qdrant        │
  │  └────┬────┘            │         │  - Critic Gate       │
  │       │ 10.10.10.0/24   │         │                      │
  │       ▼                 │   Eth   │                      │
  │  ┌──────────────┐       │ direct  │                      │
  │  │ Jetson Orin  │───────┼─────────┤ enP7s7 10.10.10.200  │
  │  │ Nano 8GB     │       │         │                      │
  │  │ 10.10.10.250 │       │         │                      │
  │  └──────────────┘       │         └──────────────────────┘
  │   YOLO + tracking +     │
  │   filtros + cola Redis  │
  └─────────────────────────┘
```

**¿Por qué este reparto y no las otras dos opciones (proxy puro / backup puro)?**

- **Proxy puro** desperdicia los 67 TOPS del Jetson (Super Mode JetPack 6.2). Si solo hace relay RTSP, basta con un Raspberry Pi. Tienes hardware AI, úsalo.
- **Backup puro** desperdicia capacidad continua. Solo activo cuando el DGX cae es ~1 hora al mes en el mejor caso.
- **Edge inference + aggregator** es la combinación que aprovecha las 3 ventajas a la vez:

  1. **Reduce tráfico de red:** sub-streams continuos a 15 fps × 5 cámaras ≈ 75 Mbps que NO viajan al DGX. El DGX recibe solo eventos + crops 4K bajo demanda (~3-5 Mbps).
  2. **Latencia baja para PTZ tracking:** las MVPSECAM tracean por hardware. El Jetson valida con su YOLO local (~30-50 ms) y solo pide captura 4K cuando hay un evento real. Si fuera todo al DGX, latencia subiría a 400-600 ms.
  3. **Failover gratuito:** Redis local en Jetson hace de cola persistente. Si DGX cae 2h, el Jetson sigue capturando + grabando + alertando vía MQTT, y al volver el DGX drena la cola.

### Decisión 2: Fix de GPU GB10 antes de tocar nada más

El estado actual reporta `nvidia-smi` mostrando N/A para memoria y 0% utilización. **Esto es el bloqueante #1 absoluto.** Si Qwen2.5-72B está corriendo en CPU, va a 0.5-1 token/s en lugar de 25-40 tok/s. Behavior ML con 7 dimensiones × 3 cámaras va a colapsar con 5 cámaras.

GB10 es Grace Blackwell de mayo 2025, arquitectura SBSA aarch64 con CUDA 12.8+. La causa más probable: `nvidia-container-toolkit` no actualizado, o el driver instalado es genérico aarch64 en lugar del DGX OS específico. **El prompt incluye §1 dedicado solo a esto, antes de cualquier cambio en la app.**

### Decisión 3: Confirmación de las cámaras nuevas

**MVPSECAM 4K 8MP 12X PTZ POE Onvif** (105€, sensor Sony, AI Human Detection, audio bidireccional, dome 360° con tracking onboard).

Lo que importa técnicamente, no el branding:
- **Onvif Profile S/T** estándar → `python-onvif-zeep` o `wsdiscovery` para autodetección
- **RTSP main + sub stream** habituales en `/stream1` y `/stream2` (a verificar empíricamente, varios chinos usan `/cam/realmonitor?channel=1&subtype=0`)
- **PTZ vía Onvif PTZ service** → `goto_preset`, `continuous_move`, `stop`
- **Onboard human tracking** → expone metadata vía Onvif Events o RTSP metadata stream (depende del firmware, validar)
- **Sin Smart Tracking API documentada** → usaremos polling vía Onvif `GetStatus` para saber dónde está apuntando

**Implicación:** el adapter `MvpsecamPTZAdapter` que crearemos hereda del `OnvifPTZAdapter` genérico. Si en el futuro cambias a Dahua o Hikvision, basta sobrescribir 3-4 métodos.

---

## 1. FIX URGENTE: GPU GB10 EN EL DGX SPARK

> **Bloqueante absoluto. Resolver ANTES de cualquier cambio de app.**

### 1.1 Diagnóstico (10 min)

```bash
ssh daviddgx@192.168.20.57

# 1. Driver y versión CUDA
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
nvcc --version 2>/dev/null || echo "nvcc no instalado"
cat /proc/driver/nvidia/version 2>/dev/null
dpkg -l | grep -E "nvidia-driver|cuda-toolkit|nvidia-container"

# 2. ¿El runtime nvidia está disponible para Docker?
docker info 2>&1 | grep -i runtime
cat /etc/docker/daemon.json 2>/dev/null

# 3. ¿Qué ve el contenedor de Ollama?
docker exec ollama nvidia-smi 2>&1 | head -20
docker exec ollama bash -c "ls -la /dev/nvidia* 2>&1"

# 4. ¿Qué ve el backend?
docker exec seedy-backend python -c "
import torch
print(f'CUDA disponible: {torch.cuda.is_available()}')
print(f'Devices: {torch.cuda.device_count()}')
if torch.cuda.is_available():
    print(f'Nombre: {torch.cuda.get_device_name(0)}')
    print(f'Compute capability: {torch.cuda.get_device_capability(0)}')
    print(f'VRAM total: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"

# 5. dmesg en busca de errores de GPU
sudo dmesg 2>&1 | grep -i -E "nvidia|nvgpu|tegra" | tail -50

# 6. ¿Es DGX OS o Ubuntu vanilla?
cat /etc/os-release
uname -a
```

**Decision tree después del diagnóstico:**

| Síntoma | Causa probable | Fix |
|---------|----------------|-----|
| `nvidia-smi` da error completo | Driver no cargado | `sudo apt install nvidia-driver-575-server` (la versión válida para GB10 es ≥575) |
| `nvidia-smi` muestra N/A en memoria pero detecta GPU | `nvidia-smi` no soporta GB10 con drivers <570 | Update a drivers ≥575, opcionalmente usar `nvitop` o `nvidia-smi --query` con campos específicos |
| Contenedor Ollama ve la GPU pero `seedy-backend` no | Falta `runtime: nvidia` o `deploy.resources.reservations.devices` en `docker-compose.yml` del backend | Editar compose, ver §1.3 |
| Todo OK pero Ollama corre lento | `OLLAMA_NUM_GPU` o `OLLAMA_KEEP_ALIVE` mal | Variables de entorno en compose |
| `torch.cuda.is_available()` = False | PyTorch instalado para CPU | Reinstalar `torch` con índice CUDA 12.8 |

### 1.2 Fix probable #1 — `nvidia-container-toolkit` y `daemon.json`

```bash
# Verificar que está instalado y al día
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verificar que daemon.json tiene runtime nvidia como default
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "5"
  }
}
EOF

sudo systemctl restart docker

# Test
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

### 1.3 Fix probable #2 — `docker-compose.yml` del backend y ollama

Buscar y verificar que **ambos** servicios tienen acceso a la GPU:

```bash
ssh daviddgx@192.168.20.57
cd ~/seedy
grep -A 20 "ollama:" docker-compose.yml | head -30
grep -A 20 "seedy-backend:" docker-compose.yml | head -30
```

El bloque correcto para cada uno debe contener:

```yaml
  ollama:
    image: ollama/ollama:latest
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=2
      - OLLAMA_MAX_LOADED_MODELS=2
      - OLLAMA_FLASH_ATTENTION=1          # crítico para Qwen2.5-72B
      - OLLAMA_KV_CACHE_TYPE=q8_0         # ahorra VRAM con calidad similar
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    # ...

  seedy-backend:
    build: ./backend
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - CUDA_VISIBLE_DEVICES=0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    # ...
```

### 1.4 Validación post-fix

```bash
ssh daviddgx@192.168.20.57
cd ~/seedy
docker compose down ollama seedy-backend
docker compose up -d ollama seedy-backend

# Espera 30s y valida
sleep 30

# 1. Ollama ve la GPU
docker exec ollama nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv

# 2. Backend ve la GPU
docker exec seedy-backend python -c "
import torch
assert torch.cuda.is_available(), 'CUDA NO disponible en backend'
print(f'OK: {torch.cuda.get_device_name(0)} con {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB')
"

# 3. Test rendimiento real con Qwen2.5-72B
time docker exec ollama ollama run qwen2.5:72b-instruct-q4_K_M "Responde solo 'OK' en una palabra."

# Esperado: <5 segundos (~25-40 tok/s en GB10).
# Si tarda >30 segundos: sigue en CPU. Volver a §1.1 diagnóstico.

# 4. Monitorización persistente
pip install --user nvitop
nvitop -m   # debe mostrar utilización GPU > 0% al hacer queries
```

**Criterio de éxito GPU:** Qwen2.5-72B responde "OK" en menos de 5 segundos. Memoria usada visible. `utilization.gpu` durante inferencia > 30%.

---

## 2. BRING-UP DEL JETSON ORIN NANO 8GB

### 2.1 Hardware: cable USB-C portátil → Jetson para flasheo y bring-up

Estás conectado al Jetson por su puerto USB-C (modo recovery + serial), así que el primer arranque y configuración los hacemos sin red. Después le metemos una IP en la red de cámaras 10.10.10.x.

**Plan de IPs:**
- Jetson: `10.10.10.250/24` (lejos del rango de cámaras 10-21)
- Gateway: `10.10.10.200` (DGX, ya configurado)
- Mantener en `192.168.20.x` también es opcional vía WiFi para acceso de emergencia

### 2.2 Flashear JetPack 6.2 con Super Mode

> Si ya tiene JetPack 6.x instalado, **saltar al §2.3** y solo activar Super Mode.

```bash
# DESDE EL PORTÁTIL (no SSH)
# 1. Descargar SDK Manager
# https://developer.nvidia.com/sdk-manager
# Instalar el .deb si es Ubuntu, AppImage si otra distro

# 2. Conectar Jetson en modo recovery:
#    - Mantener botón FORCE RECOVERY
#    - Pulsar y soltar RESET
#    - Soltar FORCE RECOVERY tras 2s
#    - lsusb debe mostrar "NVIDIA Corp. APX"

# 3. Lanzar SDK Manager
sdkmanager

# Selecciones:
# - Target: Jetson Orin Nano 8GB Developer Kit
# - JetPack: 6.2 (con Super Mode)
# - Storage: NVMe (NO microSD - esencial para rendimiento)
# - Components: CUDA, TensorRT, DeepStream, OpenCV con CUDA
# - User: durrif / password: <elige>
```

Tarda ~45 minutos. Mientras tanto, sigue al §1 y §3 en paralelo en otra terminal.

### 2.3 Configuración inicial (vía SSH ya por red)

Una vez flasheado, se conecta a tu red WiFi por defecto para setup inicial:

```bash
# Identifica IP del Jetson (mira en tu router o usa nmap)
nmap -sn 192.168.20.0/24 | grep -B 2 -i nvidia

# SSH (la IP variará, asume 192.168.20.X temporalmente)
ssh durrif@192.168.20.X

# 1. Activar Super Mode (clave para 67 TOPS)
sudo nvpmodel -m 2          # MAXN_SUPER mode
sudo jetson_clocks          # locks clocks al máximo

# Verificar
sudo nvpmodel -q
# Debe decir: MODE_25W_SUPER o similar

# 2. Instalar jetson-stats para monitorización
sudo apt update
sudo apt install -y python3-pip
sudo pip3 install -U jetson-stats
sudo reboot

# Tras reboot
ssh durrif@192.168.20.X
jtop    # dashboard interactivo, debe mostrar GPU 0% idle, 67 TOPS disponibles

# 3. Optimizaciones de RAM (el OS gasta ~1.5 GB de los 8 GB)
sudo systemctl disable nvargus-daemon.service        # no usamos cámaras CSI
sudo systemctl mask snapd.service apt-daily.service  # libera ~200 MB
sudo apt remove --purge libreoffice-* thunderbird firefox -y   # headless

# Aumentar swap (CRÍTICO para no morir si pico de RAM)
sudo systemctl disable nvzramconfig.service
sudo fallocate -l 16G /mnt/16GB.swap
sudo chmod 600 /mnt/16GB.swap
sudo mkswap /mnt/16GB.swap
sudo swapon /mnt/16GB.swap
echo '/mnt/16GB.swap none swap sw,pri=10 0 0' | sudo tee -a /etc/fstab

# 4. Asignar IP estática en la red de cámaras
sudo nmcli con add type ethernet con-name "cameras-edge" ifname eth0 \
  ipv4.method manual \
  ipv4.addresses 10.10.10.250/24 \
  ipv4.gateway 10.10.10.200 \
  ipv4.dns "1.1.1.1,8.8.8.8" \
  connection.autoconnect yes
sudo nmcli con up cameras-edge

# 5. Permitir SSH desde el DGX sin password (para que el DGX orqueste el Jetson)
# Desde el DGX:
ssh daviddgx@192.168.20.57
ssh-keygen -t ed25519 -f ~/.ssh/jetson_edge -N ""
ssh-copy-id -i ~/.ssh/jetson_edge.pub durrif@10.10.10.250
echo "Host jetson-edge
    HostName 10.10.10.250
    User durrif
    IdentityFile ~/.ssh/jetson_edge
    StrictHostKeyChecking accept-new" >> ~/.ssh/config

# Desde DGX, debe funcionar:
ssh jetson-edge "uptime && jtop --no-warnings | head -5"
```

### 2.4 Escritorio remoto (sustituto de monitor)

> Recomendación: **xRDP en lugar de VNC** porque ya tienes Windows/Linux con clientes RDP nativos y la latencia es menor.

```bash
ssh durrif@10.10.10.250

sudo apt install -y xrdp xfce4 xfce4-goodies dbus-x11
sudo systemctl enable --now xrdp

# xfce más liviano que el GNOME por defecto
echo "xfce4-session" > ~/.xsession

# Permitir RDP en la subred 10.10.10.x
sudo ufw allow from 10.10.10.0/24 to any port 3389

# Desde tu portátil:
# Windows: Escritorio Remoto → 10.10.10.250 (vía la ruta de cámaras del DGX, o directo si conectas el portátil al switch de cámaras)
# Linux: remmina → RDP → 10.10.10.250
```

**Alternativa más liviana sin RDP** si prefieres trabajar siempre por SSH+VSCode Remote-SSH: salta este paso y usa Cursor/VSCode con Remote-SSH apuntando a `jetson-edge`.

---

## 3. PIPELINE EDGE EN EL JETSON

### 3.1 Stack mínimo en el Jetson (no Docker, nativo)

> **Decisión:** sin Docker en el Jetson. Razón: Docker añade ~600 MB de overhead y los containers en aarch64 con TensorRT son frágiles. El Jetson corre 4 procesos systemd nativos.

```bash
ssh jetson-edge

# Dependencias
sudo apt install -y \
    python3.10-venv \
    redis-server \
    mosquitto-clients \
    ffmpeg \
    libgstreamer1.0-dev \
    libgstrtspserver-1.0-dev

# Redis local (cola persistente para failover DGX)
sudo systemctl enable --now redis-server
sudo sed -i 's/^# maxmemory <bytes>/maxmemory 1gb/' /etc/redis/redis.conf
sudo sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
sudo systemctl restart redis-server

# Workspace
mkdir -p ~/seedy-edge/{models,events,logs}
cd ~/seedy-edge
python3 -m venv .venv --system-site-packages   # crítico: hereda pycuda/torch del JetPack
source .venv/bin/activate

pip install --upgrade pip
pip install \
    ultralytics==8.3.0 \
    onvif-zeep==0.2.12 \
    wsdiscovery==2.0.0 \
    paho-mqtt==2.1.0 \
    redis==5.0.4 \
    aiohttp==3.9.5 \
    pyyaml==6.0.1 \
    structlog==24.1.0 \
    fastapi==0.111.0 \
    uvicorn==0.30.0 \
    httpx==0.27.0
```

### 3.2 Estructura de código edge

```
~/seedy-edge/
├── .venv/
├── seedy_edge/
│   ├── __init__.py
│   ├── main.py                    ← Punto de entrada, supervisión de subprocesos
│   ├── config.yaml                ← Cámaras, umbrales, MQTT, DGX URL
│   │
│   ├── capture/                   ← CAPA 1 (modularidad v4.3)
│   │   ├── rtsp_reader.py         ← Lector RTSP + reconexión exponencial
│   │   ├── onvif_discovery.py     ← Auto-descubre cámaras Onvif en 10.10.10.0/24
│   │   └── onvif_ptz.py           ← Wrapper PTZ (goto_preset, continuous_move, status)
│   │
│   ├── inference/                 ← CAPA 2
│   │   ├── yolo_engine.py         ← YOLOv8s TensorRT FP16, batch up to 4
│   │   ├── tracker.py             ← BYTETrack o IoU tracker simple
│   │   └── triggers.py            ← Reglas: new_bird, quality_bird, pest_alert
│   │
│   ├── publish/                   ← CAPA 3
│   │   ├── dgx_relay.py           ← POST /vision/edge_event al DGX, con retry
│   │   ├── redis_queue.py         ← Cola si DGX no responde
│   │   ├── mqtt_alerts.py         ← Alertas críticas directo a Mosquitto del DGX
│   │   └── snapshot_4k.py         ← Captura 4K main-stream bajo demanda
│   │
│   ├── orchestrator/              ← CAPA 4
│   │   ├── camera_supervisor.py   ← Un proceso por cámara (5 procesos paralelos)
│   │   ├── ptz_controller.py      ← Lee triggers + comanda PTZ tracking
│   │   └── health.py              ← FastAPI /health, /metrics, /cameras
│   │
│   └── models/                    ← Pesos y engines TensorRT
│       ├── yolov8s.pt             ← Original Ultralytics (descargar)
│       ├── yolov8s.onnx           ← Export intermedio
│       └── yolov8s_fp16.engine    ← TensorRT engine optimizado
│
└── deploy/
    ├── seedy-edge.service         ← systemd unit
    └── camera-network.service     ← persistencia red 10.10.10.250
```

### 3.3 Conversión YOLOv8s a TensorRT (una vez, en el Jetson)

> CRÍTICO hacer la conversión EN EL JETSON, no en otra máquina. El engine TensorRT es específico de la GPU y la versión de TRT instalada.

```bash
ssh jetson-edge
cd ~/seedy-edge
source .venv/bin/activate

# Descargar pesos originales
mkdir -p seedy_edge/models
cd seedy_edge/models
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt

# Conversión .pt → ONNX → TRT engine
python -c "
from ultralytics import YOLO
model = YOLO('yolov8s.pt')
# Export con FP16, dynamic batch, workspace 4GB
model.export(
    format='engine',
    half=True,
    dynamic=True,
    batch=4,
    workspace=4,
    device=0,
    imgsz=640,
)
"

# Validación
python -c "
import time
from ultralytics import YOLO
import torch
model = YOLO('yolov8s.engine')
# Warmup
dummy = torch.zeros((1, 3, 640, 640))
for _ in range(3):
    model.predict(dummy, verbose=False)
# Benchmark
t0 = time.time()
for _ in range(100):
    model.predict(dummy, verbose=False)
elapsed = time.time() - t0
print(f'FPS: {100/elapsed:.1f}')
"
# Esperado en Jetson Orin Nano 8GB Super Mode: 50-70 FPS con batch=1, ~120 FPS efectivos con batch=4
```

### 3.4 Algoritmo del CameraSupervisor (uno por cámara)

```python
# seedy_edge/orchestrator/camera_supervisor.py
"""
Un proceso por cámara. Lee sub-stream, infiere, dispara triggers.
NUNCA bloquea por errores de una sola cámara.
"""
import asyncio
import structlog
from seedy_edge.capture.rtsp_reader import RTSPReader
from seedy_edge.inference.yolo_engine import YOLOEngine
from seedy_edge.inference.tracker import IOUTracker
from seedy_edge.inference.triggers import TriggerEngine
from seedy_edge.publish.dgx_relay import DGXRelay

log = structlog.get_logger()

class CameraSupervisor:
    def __init__(self, camera_cfg: dict, yolo: YOLOEngine, dgx: DGXRelay):
        self.cam = camera_cfg
        self.yolo = yolo
        self.tracker = IOUTracker(max_age=120, iou_threshold=0.3)
        self.triggers = TriggerEngine(camera_id=self.cam['id'])
        self.dgx = dgx
        self.reader = RTSPReader(self.cam['substream_url'], timeout=15)
        self.frame_count = 0
        self.last_log = 0

    async def run(self):
        log.info("camera_supervisor.start", camera=self.cam['id'])
        async for frame, ts in self.reader.frames():
            try:
                # 1. Inferencia YOLO (single frame, ~15-20 ms)
                detections = self.yolo.predict(frame)

                # 2. Solo birds y dogs (ignoramos COCO classes irrelevantes)
                detections = [d for d in detections if d.cls in (14, 15, 16)]  # bird, cat, dog

                # 3. Filtro de artefactos (bbox > 45% del tile = falso positivo)
                detections = [d for d in detections if d.area_ratio < 0.45]

                # 4. Tracker: asigna track_ids
                tracks = self.tracker.update(detections, ts)

                # 5. Triggers
                events = self.triggers.evaluate(tracks, frame, ts)

                # 6. Para cada evento: enviar al DGX (asíncrono, no bloquea)
                for ev in events:
                    asyncio.create_task(self.dgx.send_event(ev))

                self.frame_count += 1
                if ts - self.last_log > 60:
                    log.info("camera.heartbeat", camera=self.cam['id'],
                             fps=self.frame_count/60, tracks=len(tracks))
                    self.frame_count = 0
                    self.last_log = ts

            except Exception:
                log.exception("camera.frame_error", camera=self.cam['id'])
                # NO romper el loop. Sigue con el siguiente frame.
                continue
```

### 3.5 Contrato de eventos hacia el DGX

```python
# seedy_edge/publish/dgx_relay.py
"""
Envía eventos al DGX vía POST. Si falla, encola en Redis local.
Drainer en background re-envía cuando DGX vuelve.
"""

EVENT_SCHEMA = {
    "schema_version": "edge.v1",
    "edge_id": "jetson-orin-nano-01",      # identifica el origen
    "camera_id": "vigi_durrif_1",          # cuál cámara
    "ts": 1714826400.123,                  # epoch
    "event_type": "new_bird",              # | quality_bird | pest_alert | scheduled | mating_candidate | ptz_target
    "tracks": [{
        "track_id": "vigi_durrif_1_t847",
        "bbox": [x1, y1, x2, y2],
        "cls": 14,                          # COCO class
        "conf": 0.87,
        "size_pixels": 12450,
    }],
    "frame_jpeg_b64": "...",                # solo si event_type requiere snapshot
    "wants_4k_capture": True,               # si True, DGX dispara captura main-stream
    "ptz_state": None,                      # solo cuando es PTZ con tracking activo
}
```

Endpoint nuevo en el DGX que consume esto: `POST /vision/edge_event` (ver §4.1).

### 3.6 Adapter para las 2 PTZ MVPSECAM (entrantes)

```python
# seedy_edge/capture/onvif_ptz.py
"""
Adapter Onvif para las 2 PTZ MVPSECAM. Si en el futuro cambian a Dahua/Hikvision,
sobrescribir solo lo específico.
"""
from onvif import ONVIFCamera

class OnvifPTZAdapter:
    def __init__(self, host: str, port: int = 80, user: str = "admin", password: str = ""):
        self.cam = ONVIFCamera(host, port, user, password)
        self.media = self.cam.create_media_service()
        self.ptz = self.cam.create_ptz_service()
        self.profile = self.media.GetProfiles()[0]
        self.token = self.profile.token

    def get_status(self) -> dict:
        s = self.ptz.GetStatus({'ProfileToken': self.token})
        return {
            "pan": float(s.Position.PanTilt.x),
            "tilt": float(s.Position.PanTilt.y),
            "zoom": float(s.Position.Zoom.x),
            "moving": s.MoveStatus.PanTilt != 'IDLE',
        }

    def goto_preset(self, preset_token: str):
        self.ptz.GotoPreset({
            'ProfileToken': self.token,
            'PresetToken': preset_token,
            'Speed': {'PanTilt': {'x': 0.5, 'y': 0.5}, 'Zoom': {'x': 0.5}}
        })

    def continuous_move(self, pan: float, tilt: float, zoom: float = 0.0, duration: float = 1.0):
        """pan/tilt/zoom en rango [-1.0, 1.0]"""
        self.ptz.ContinuousMove({
            'ProfileToken': self.token,
            'Velocity': {
                'PanTilt': {'x': pan, 'y': tilt},
                'Zoom': {'x': zoom}
            }
        })
        # MVPSECAM no respeta timeout, hay que parar manualmente
        import time; time.sleep(duration)
        self.stop()

    def stop(self):
        self.ptz.Stop({'ProfileToken': self.token, 'PanTilt': True, 'Zoom': True})

    def get_substream_url(self) -> str:
        """RTSP sub-stream URL — varía por marca, MVPSECAM usa el path Dahua-style"""
        # Empíricamente: probar primero el estándar Onvif
        uri = self.media.GetStreamUri({
            'StreamSetup': {
                'Stream': 'RTP-Unicast',
                'Transport': {'Protocol': 'RTSP'}
            },
            'ProfileToken': self.token,
        })
        return uri.Uri


class MvpsecamPTZAdapter(OnvifPTZAdapter):
    """
    Sobrescribe particularidades observadas:
    - El stop a veces tarda 200ms en aplicar
    - El sub-stream tiene metadata de tracking en MJPEG embebido (por verificar)
    """
    def stop(self):
        super().stop()
        import time; time.sleep(0.2)
```

### 3.7 Auto-descubrimiento de cámaras Onvif

```python
# seedy_edge/capture/onvif_discovery.py
"""
Cuando llegan las 2 PTZ, ejecutar este script desde el Jetson.
Devuelve la lista de cámaras Onvif visibles en la subred 10.10.10.0/24.
"""
from wsdiscovery import WSDiscovery
from urllib.parse import urlparse

def discover_onvif_cameras() -> list[dict]:
    wsd = WSDiscovery()
    wsd.start()
    services = wsd.searchServices(timeout=5)
    cameras = []
    for s in services:
        for url in s.getXAddrs():
            host = urlparse(url).hostname
            cameras.append({
                "host": host,
                "xaddr": url,
                "scopes": [str(sc) for sc in s.getScopes()],
            })
    wsd.stop()
    return cameras

if __name__ == "__main__":
    import json
    print(json.dumps(discover_onvif_cameras(), indent=2))
```

CLI de uso cuando lleguen las cámaras:

```bash
ssh jetson-edge
cd ~/seedy-edge && source .venv/bin/activate
python -m seedy_edge.capture.onvif_discovery
# Output: lista con host, xaddr (endpoint Onvif), scopes
# Las dos PTZ deberían aparecer con scopes que mencionan "MVPSECAM" o el sensor
```

### 3.8 systemd unit para arranque automático

```bash
sudo tee /etc/systemd/system/seedy-edge.service > /dev/null <<'EOF'
[Unit]
Description=Seedy Edge - YOLO + Tracking + Camera Aggregator
After=network-online.target redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=durrif
WorkingDirectory=/home/durrif/seedy-edge
Environment="PATH=/home/durrif/seedy-edge/.venv/bin:/usr/local/cuda/bin:/usr/bin"
Environment="LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:/usr/local/cuda/lib64"
ExecStart=/home/durrif/seedy-edge/.venv/bin/python -m seedy_edge.main
Restart=always
RestartSec=10

# Límites
MemoryLimit=6G               # deja 2 GB para OS y Redis
CPUQuota=400%                # 4 cores de los 6 disponibles
Nice=-5                      # prioridad ligeramente alta

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now seedy-edge
sudo journalctl -u seedy-edge -f --output=cat
```

---

## 4. RECONFIGURACIÓN DEL DGX PARA RECIBIR DEL JETSON

### 4.1 Endpoint nuevo en el backend

```python
# backend/edge/routes.py — NUEVO módulo, no toca el resto
from fastapi import APIRouter, BackgroundTasks
from .schemas import EdgeEvent
from backend.services.vision_pipeline import process_edge_event
from backend.services.snapshot_4k import capture_main_stream

router = APIRouter(prefix="/vision/edge", tags=["edge"])

@router.post("/event")
async def receive_edge_event(event: EdgeEvent, bg: BackgroundTasks):
    """
    Recibe eventos del Jetson. Disparados desde el sub-stream que el Jetson
    procesa localmente. Si el evento pide captura 4K, se dispara aquí en el DGX
    (donde está el clasificador breed + Gemini + Re-ID).
    """
    # 1. Persistir el evento (rápido, no bloquea)
    bg.add_task(process_edge_event, event)

    # 2. Si el evento merece captura 4K, dispararla
    if event.wants_4k_capture:
        bg.add_task(
            capture_main_stream,
            camera_id=event.camera_id,
            track_hint=event.tracks[0] if event.tracks else None,
        )

    return {"accepted": True, "event_id": event.event_id}
```

```python
# backend/edge/schemas.py
from pydantic import BaseModel
from typing import Optional

class TrackInfo(BaseModel):
    track_id: str
    bbox: list[float]   # [x1, y1, x2, y2]
    cls: int
    conf: float
    size_pixels: int

class EdgeEvent(BaseModel):
    schema_version: str = "edge.v1"
    edge_id: str
    camera_id: str
    ts: float
    event_type: str
    tracks: list[TrackInfo]
    frame_jpeg_b64: Optional[str] = None
    wants_4k_capture: bool = False
    ptz_state: Optional[dict] = None
    event_id: Optional[str] = None  # generado en server si no viene
```

Registro en `backend/main.py` con UNA línea:

```python
from backend.edge.routes import router as edge_router
app.include_router(edge_router)
```

### 4.2 Desactivar la inferencia YOLO en sub-stream del DGX (parcial)

El backend del DGX seguirá procesando main-stream 4K (donde brilla con Qwen 72B + Gemini), pero deja de hacer YOLO en sub-stream para las cámaras que ahora gestiona el Jetson.

```yaml
# config/cameras.yaml en el DGX
cameras:
  dahua_sauna:
    id: dahua_sauna
    main_stream: rtsp://admin:xxx@10.10.10.108:554/cam/realmonitor?channel=1&subtype=0
    sub_stream: rtsp://admin:xxx@10.10.10.108:554/cam/realmonitor?channel=1&subtype=1
    edge_managed: true        # ← NUEVO. El sub-stream lo procesa el Jetson.
    main_stream_processor: dgx # main-stream 4K sigue en DGX

  vigi_durrif_1:
    id: vigi_durrif_1
    main_stream: rtsp://admin:xxx@10.10.10.11:554/stream1
    sub_stream: rtsp://admin:xxx@10.10.10.11:554/stream2
    edge_managed: true

  vigi_durrif_2:
    id: vigi_durrif_2
    main_stream: rtsp://admin:xxx@10.10.10.10:554/stream1
    sub_stream: rtsp://admin:xxx@10.10.10.10:554/stream2
    edge_managed: true

  ptz_mvpsecam_1:               # ← NUEVA, IP a confirmar tras llegada
    id: ptz_mvpsecam_1
    onvif_host: 10.10.10.20
    onvif_user: admin
    onvif_password: xxx
    main_stream: auto           # se obtiene vía Onvif GetStreamUri
    edge_managed: true
    has_ptz: true

  ptz_mvpsecam_2:
    id: ptz_mvpsecam_2
    onvif_host: 10.10.10.21
    onvif_user: admin
    onvif_password: xxx
    main_stream: auto
    edge_managed: true
    has_ptz: true
```

En el código del backend, donde se inicia el `vision_pipeline` para cada cámara, añadir el guard:

```python
# backend/services/vision_pipeline.py
def start_camera_workers(cameras_config):
    for cam in cameras_config:
        if cam.get("edge_managed", False):
            log.info("camera.skipped_substream", camera=cam["id"],
                     reason="managed by edge")
            # Solo registramos para receive main-stream snapshots a demanda
            register_main_stream_consumer(cam)
        else:
            # Pipeline antiguo completo
            start_full_pipeline(cam)
```

### 4.3 Aprovechamiento de Qwen2.5-72B para behavior y mating analysis

Ahora que la GPU GB10 funciona (post §1) y el DGX no gasta ciclos en YOLO de sub-stream (delegado al Jetson), Qwen2.5-72B tiene VRAM y compute para análisis serios.

**Cambio clave:** el módulo `BehaviorMLEngine` (las 7 dimensiones que reportan "Sin datos suficientes" en el digital twin) pasa de ser un clasificador estadístico simple a usar Qwen 72B para analizar **secuencias de eventos** del Jetson.

```python
# backend/services/behavior_qwen.py — NUEVO
"""
Cuando se acumulan N eventos del mismo bird_id en una ventana de tiempo,
se manda a Qwen 72B un resumen estructurado y se pide análisis de las 7
dimensiones (agresividad, dominancia, sociabilidad, etc.).
"""

ANALYSIS_PROMPT = """Eres un etólogo aviar especializado en gallinas de raza heredada.
Analiza esta secuencia de eventos de comportamiento del ave {bird_id} ({breed}, {sex})
en las últimas {window_hours} horas:

EVENTOS:
{events_summary}

CONTEXTO DEL CORRAL:
- Pen: {pen_id}
- Compañeros visibles: {peer_birds}
- Eventos de monta detectados (track-level): {mating_count}

Para cada una de estas 7 dimensiones, devuelve JSON con:
- score (0.0 a 1.0)
- confidence (0.0 a 1.0)
- evidence (cita 1-3 eventos por número)

Dimensiones:
1. agresividad     — interacciones agresivas iniciadas
2. dominancia      — desplazamiento de otros, acceso prioritario a recursos
3. subordinación   — evitación, retirada
4. alimentación    — frecuencia y duración en zonas de comida
5. estrés          — comportamientos repetitivos, alarma
6. sociabilidad    — proximidad voluntaria a otros
7. patrón de nido  — visitas a nidales

Responde SOLO con el JSON. Si la evidencia es insuficiente para una dimensión,
score=null y explica en evidence.
"""

async def analyze_bird_behavior(bird_id: str, window_hours: int = 24):
    events = await fetch_events_from_influx(bird_id, window_hours)
    if len(events) < 10:
        return {"completeness": len(events) / 10, "reason": "insufficient_data"}

    # Resumen estructurado para no saturar el contexto
    summary = summarize_events_compact(events)

    prompt = ANALYSIS_PROMPT.format(
        bird_id=bird_id,
        breed=await get_breed(bird_id),
        sex=await get_sex(bird_id),
        window_hours=window_hours,
        events_summary=summary,
        pen_id=await get_pen(bird_id),
        peer_birds=await get_peers(bird_id),
        mating_count=sum(1 for e in events if e.type == "mating_candidate"),
    )

    # Llamada a Ollama Qwen2.5-72B
    response = await ollama_chat(
        model="qwen2.5:72b-instruct-q4_K_M",
        messages=[{"role": "user", "content": prompt}],
        format="json",
        temperature=0.2,
    )

    return parse_dimensions(response)
```

**Llamado por un cron interno cada 6h por bird_id activo**, o bajo demanda desde el digital twin.

### 4.4 Mating detector revisado con contexto edge

El Jetson detecta `mating_candidate` (dos tracks de aves diferentes superpuestos durante >2s con uno encima). El DGX recibe el evento + crops, y aquí Qwen 72B confirma:

```python
# backend/services/mating_qwen.py
async def confirm_mating(event: EdgeEvent) -> dict:
    """
    Recibe candidato del Jetson. Pide captura 4K. Pasa crops a Qwen 72B
    para validación + identificación de gallo y gallina implicados.
    """
    # 1. Captura 4K ya disparada por receive_edge_event
    snap_4k = await wait_for_4k_capture(event.camera_id, event.ts, timeout=3.0)
    if snap_4k is None:
        return {"confirmed": False, "reason": "no_4k_capture"}

    # 2. Crops de cada bird del evento
    crops = [crop_bbox(snap_4k, t.bbox) for t in event.tracks]

    # 3. Re-ID en cada crop (sistema v4.2)
    identities = [reid_match(c) for c in crops]

    # 4. Si ambos identificados → registro directo
    if all(i.locked for i in identities):
        return record_mating(identities[0], identities[1], event.ts, snap_4k)

    # 5. Si parcial → Qwen vision (vía VLM o describiendo crops para Qwen 72B text)
    description = await describe_with_seedy_vision(snap_4k, event.tracks)
    decision = await ollama_chat(
        model="qwen2.5:72b-instruct-q4_K_M",
        messages=[{"role": "user", "content": MATING_VALIDATION_PROMPT.format(
            description=description,
            partial_identities=identities,
        )}],
        format="json",
    )
    return parse_mating_decision(decision)
```

---

## 5. CABLE DIRECTO JETSON ↔ DGX

Una vez que el Jetson está en `10.10.10.250` y el DGX en `10.10.10.200` (con `enP7s7` ya configurado pero NO persistente, según el doc de estado), hacer persistente la red en el DGX:

```bash
ssh daviddgx@192.168.20.57

# Crear systemd unit para que la red 10.10.10.200 sobreviva reboots
sudo tee /etc/systemd/system/config-camera-network.service > /dev/null <<'EOF'
[Unit]
Description=Configure camera network 10.10.10.x on enP7s7
After=network.target
Before=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'ip addr add 10.10.10.200/24 dev enP7s7 2>/dev/null; ip link set enP7s7 up'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now config-camera-network

# Verificar
ip addr show enP7s7
ping -c 2 10.10.10.250
```

**Test de conectividad bidireccional:**

```bash
# Desde DGX
ping -c 2 10.10.10.250 && echo "DGX → Jetson OK"
ssh jetson-edge "ping -c 2 10.10.10.200" && echo "Jetson → DGX OK"

# Test del endpoint
curl -s http://10.10.10.250:8001/health   # Jetson health endpoint
curl -s http://10.10.10.200:8000/health   # DGX backend
```

---

## 6. PARAR EL SEEDY DEL MSI VECTOR (limpieza)

Pendiente del doc de estado. Hacerlo ahora que el DGX está validado:

```bash
ssh davidia@192.168.20.131  # MSI Vector
cd ~/Documentos/Seedy
docker compose down
docker system prune -a -f --volumes  # libera ~50 GB
echo "MSI Seedy detenido. Verificar que DGX sigue operativo."

# Verificar desde el portátil que las URLs Cloudflare siguen vivas
curl -s -o /dev/null -w "%{http_code}\n" https://seedy-api.neofarm.io/health
# Esperado: 200
```

---

## 7. VALIDACIÓN END-TO-END

### 7.1 Smoke test (5 minutos tras todo el deploy)

```bash
# 1. GPU del DGX en uso real
ssh daviddgx@192.168.20.57 "nvitop --once"
# Debe mostrar GPU activa, modelo qwen2.5:72b cargado en VRAM

# 2. Jetson alive y procesando
ssh jetson-edge "systemctl is-active seedy-edge && jtop --no-warnings | head -10"
# Debe mostrar GPU del Jetson 30-60% utilización con 5 cámaras activas

# 3. Eventos llegando al DGX desde el Jetson
ssh daviddgx@192.168.20.57 "docker logs seedy-backend --tail 50 | grep edge_event"
# Debe mostrar eventos recibidos en los últimos minutos

# 4. Tasa de tráfico Jetson → DGX
ssh daviddgx@192.168.20.57 "sudo iftop -i enP7s7 -t -s 10"
# Esperado: ~3-5 Mbps en sustained, picos cuando hay capturas 4K
# (Vs ~75 Mbps si no estuviera el Jetson filtrando)

# 5. Cámaras MVPSECAM (post-llegada)
ssh jetson-edge "cd ~/seedy-edge && source .venv/bin/activate && python -m seedy_edge.capture.onvif_discovery"
# Debe listar las 5 cámaras (3 actuales + 2 nuevas)
```

### 7.2 Test funcional behavior con Qwen 72B

```bash
# Curl al backend para forzar análisis de un ave conocida
curl -X POST https://seedy-api.neofarm.io/birds/PAL-2026-0001/behavior/analyze \
  -H "Authorization: Bearer $SEEDY_API_KEY" \
  -d '{"window_hours": 24, "force_qwen": true}'

# Esperado en respuesta: 7 dimensiones con score, confidence, evidence
# Anteriormente todas decían "Sin datos suficientes (completeness < 0.4)".
# Ahora con la mejora del pipeline + Qwen 72B, esperar al menos 5/7 con score válido.
```

### 7.3 Test PTZ mating workflow (cuando lleguen las PTZ)

1. Apuntar manualmente una PTZ a un par de aves activas vía interfaz web de la cámara.
2. Observar logs del Jetson: debe detectar `mating_candidate`.
3. Observar backend DGX: debe registrar el evento, disparar captura 4K, pasar a Qwen 72B para validación.
4. Si confirma: aparece en `/birds/{id}/mating_events` con timestamp y crop URL.

---

## 8. ORDEN DE EJECUCIÓN — 4 DÍAS

```
DÍA 1 (mañana): FIX GPU DGX
  ├─ §1 completo: diagnóstico + fix + validación
  └─ Criterio: Qwen2.5-72B responde "OK" en <5s vía Ollama

DÍA 1 (tarde): JETSON BRING-UP
  ├─ §2.2-2.3: flasheo (si necesario) + super mode + IP estática
  ├─ §2.4: xrdp opcional (o saltar a SSH-only)
  └─ Criterio: ssh jetson-edge funciona desde el DGX

DÍA 2 (mañana): EDGE STACK
  ├─ §3.1-3.3: instalación deps + conversión TensorRT
  └─ Criterio: yolov8s.engine corre a >50 FPS en jetson-edge

DÍA 2 (tarde): EDGE PIPELINE
  ├─ §3.4-3.5, 3.8: CameraSupervisor para las 3 cámaras existentes + systemd
  └─ Criterio: 3 cámaras activas en jtop, eventos en /tmp/seedy-edge/events

DÍA 3 (mañana): INTEGRACIÓN DGX
  ├─ §4.1-4.2: endpoint /vision/edge_event + edge_managed flag
  ├─ §5: persistencia red 10.10.10.200
  ├─ §6: parar Seedy MSI
  └─ Criterio: eventos del Jetson llegan al DGX, latencia < 200ms

DÍA 3 (tarde): MEJORA BEHAVIOR/MATING CON QWEN 72B
  ├─ §4.3-4.4: behavior_qwen.py + mating_qwen.py
  ├─ §7.2: validación funcional
  └─ Criterio: 5/7 dimensiones con score válido en bird de prueba

DÍA 4 (cuando lleguen PTZ): ONBOARDING MVPSECAM
  ├─ §3.6-3.7: discovery + adapter + IPs
  ├─ Conexión física al switch de cámaras + asignación 10.10.10.20 / 10.10.10.21
  ├─ Añadir a config/cameras.yaml
  ├─ Reiniciar seedy-edge en Jetson
  └─ Criterio: 5/5 cámaras up, eventos de las PTZ llegando
```

---

## 9. RIESGOS Y MITIGACIONES

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| GB10 sigue sin reportar stats incluso tras drivers nuevos | Media | Alto | Usar `nvitop` que parsea diferente; lo importante es el rendimiento real (Qwen 72B en <5s "OK") |
| Jetson Orin Nano 8GB se queda corto con 5 cámaras | Baja | Medio | Bajar sub-streams a 5-7 fps (suficiente para tracking); offload del 5° stream al DGX si necesario |
| MVPSECAM no implementa Onvif PTZ correctamente | Media | Medio | Adapter heredable; fallback a HTTP CGI estilo Dahua si Onvif falla |
| El cable Ethernet directo Jetson-DGX da problemas (sin switch entre medio) | Baja | Bajo | Funciona con cable straight + autoMDIX (todos los GbE modernos lo soportan). Si falla, meter un switch barato 10.10.10.x |
| TensorRT engine generado en Jetson rompe tras `apt upgrade` | Alta | Bajo | Re-generar engine es 2 min; añadirlo al systemd como pre-start script si versión TRT cambia |
| Qwen 72B se queda sin VRAM cuando coexisten múltiples modelos | Media | Alto | `OLLAMA_MAX_LOADED_MODELS=2`, descargar `seedy:v16` cuando se use 72B; KV cache q8_0 |
| Las 2 PTZ no usan password "admin/admin" por defecto | Alta | Bajo | Login web previo para resetear/configurar credenciales antes de añadir al config |
| El watcher de Continue v4.4 (si está activo) reindexa con cada cambio del backend edge | Media | Bajo | Excluir `backend/edge/` temporalmente del index hasta que el código se estabilice |

---

## 10. DELIVERABLES

Al cierre del Día 4:

1. **GPU GB10 funcionando** confirmable con `nvitop` y benchmark Qwen 72B <5s.
2. **Jetson Orin Nano** corriendo `seedy-edge` como systemd, conectado a DGX por cable directo `10.10.10.200 ↔ 10.10.10.250`.
3. **5 cámaras** procesándose: 3 actuales + 2 PTZ MVPSECAM. Sub-stream YOLO en Jetson, main-stream 4K en DGX.
4. **Reducción de tráfico de red** medida y documentada (~75 Mbps → ~3-5 Mbps continuos).
5. **Qwen2.5-72B** atendiendo análisis de behavior y validación de mating, no solo Q&A vía OpenWebUI.
6. **MSI Vector** con Seedy detenido, ~50 GB liberados.
7. **Red 10.10.10.x persistente** vía systemd unit en el DGX.
8. **Documentación** `docs/edge-architecture.md` con el diagrama final y el contrato de eventos.
9. **Changelog**:
   ```
   ## [v4.5] — 2026-05-XX — "Jetson en el Borde, GB10 en el Cerebro"
   - Fix: GPU GB10 reconocida correctamente (nvidia-container-toolkit + daemon.json)
   - Añadido: Jetson Orin Nano 8GB como Edge Inference + Camera Aggregator
   - Añadido: backend/edge/ con endpoint /vision/edge_event
   - Añadido: backend/services/behavior_qwen.py — análisis 7D con Qwen2.5-72B
   - Añadido: backend/services/mating_qwen.py — confirmación de monta con vision context
   - Añadido: 2 cámaras MVPSECAM PTZ Onvif via OnvifPTZAdapter
   - Cambiado: cámaras existentes pasan a edge_managed=true (sub-stream en Jetson)
   - Cambiado: red 10.10.10.x persistente en DGX vía systemd
   - Eliminado: Seedy redundante en MSI Vector (parado, espacio liberado)
   - No tocado: pipeline RAG /v1/chat/completions, v4.3 coder router, v4.4 repo context
   ```

---

## 11. CIERRE

Esta v4.5 cierra el reparto natural de la arquitectura física que ahora tienes:

- **Jetson Orin Nano 8GB** → "ojos" del sistema. Filtra ruido, identifica candidatos, comanda PTZ. Localizado físicamente con las cámaras.
- **DGX Spark GB10 + 128 GB** → "cerebro". Qwen2.5-72B + Re-ID + RAG + Critic. Solo recibe lo que merece la pena pensar.
- **Red de cámaras 10.10.10.x** aislada del WiFi de casa. Cero impacto en tu red doméstica.
- **MSI Vector** liberado para lo que quieras (laptop de coding, fine-tuning con el Modelfile de v4.3).

El pipeline anterior reportaba "Sin datos suficientes" en behavior porque (a) la GPU no estaba activa y (b) el sub-stream del DGX a 15 fps × 3 cámaras saturaba sin dar tiempo a análisis serio. Con el reparto edge/core, el DGX procesa **menos frames pero mucho mejores** y Qwen 72B tiene VRAM y tiempo para razonar de verdad sobre el comportamiento de cada ave.

Las 3 hermanas Seedy v4.x ahora están en su sitio:
- **v4.2** — Identidad robusta de aves (Vision)
- **v4.3** — Router de modelos coding tras endpoint OpenAI-compatible
- **v4.4** — Memoria del repo (chunking AST + embedding local)
- **v4.5** — Edge inference + GPU del cerebro funcionando

---

*Prompt v4.5 — Seedy Edge "Jetson en el Borde, GB10 en el Cerebro" — mayo 2026*
*Para ejecutar mayoritariamente vía SSH a daviddgx@192.168.20.57 y a jetson-edge.*
