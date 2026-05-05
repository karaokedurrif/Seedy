# 🚀 Guía de Setup Jetson Orin Nano 8GB para Seedy Edge

**Fecha:** 4 mayo 2026  
**Estado:** Jetson **seminuevo**, encendido, conectado USB-C, **en proceso de flasheo JetPack 6.2**

---

## 📊 DIAGNÓSTICO INICIAL

- ✅ Jetson Orin Nano 8GB **seminuevo** (tiene JetPack previo, necesita reflash limpio)
- ✅ Jetson **encendido** (alimentación conectada, LEDs visibles)
- ✅ USB-C conectado: Portátil MSI → USB 3.0 del Jetson
- ⏳ **EN PROGRESO:** Poner Jetson en modo recovery (botón REC+RST)
- 🎯 **Acción requerida:** Flashear JetPack 6.2 con Super Mode (67 TOPS)

---

## 🔌 REQUISITOS PREVIOS

### Hardware necesario:
1. **Alimentación DC:** Adaptador 5V 4A con conector barrel jack O USB-C PD ≥15W
2. **Cable USB-C:** Para conectar Jetson → Portátil MSI (modo recovery)
3. **Cable Ethernet:** Ya conectado (para red de cámaras 10.10.10.x después del flasheo)
4. **Monitor HDMI (opcional):** Para ver la pantalla del Jetson durante la configuración inicial

### Software necesario:
- **NVIDIA SDK Manager 2.1+** (se instalará en el portátil MSI)
- **Ubuntu 20.04/22.04/24.04** en host (✅ tienes Ubuntu 24.04)
- **JetPack 6.2** (incluye JetOS 36.4, CUDA 12.6, TensorRT 10.3)

---

## 📋 FASE 1: FLASHEAR JETPACK 6.2 CON SUPER MODE

### Paso 1.1: Instalar NVIDIA SDK Manager en el portátil MSI

```bash
# Descargar SDK Manager desde NVIDIA (requiere cuenta de desarrollador)
# https://developer.nvidia.com/sdk-manager

# Instalar dependencias
sudo apt update
sudo apt install -y libgconf-2-4 libcanberra-gtk-module

# Instalar SDK Manager .deb
cd ~/Descargas
sudo dpkg -i sdkmanager_*.deb
sudo apt install -f  # Resolver dependencias si faltan
```

### Paso 1.2: Poner el Jetson en modo Recovery

**Secuencia física (IMPORTANTE):**

1. **Desconecta la alimentación** del Jetson (si estaba conectada)
2. **Conecta el cable USB-C** del Jetson al portátil MSI
3. **Localiza el botón "REC" o "Force Recovery"** en el Jetson (botón pequeño cerca de los pines GPIO)
4. **Mantén presionado el botón REC**
5. **Conecta la alimentación DC** al Jetson (mientras mantienes REC presionado)
6. **Suelta el botón REC** tras 2 segundos
7. **Verifica que aparezca un LED verde** en el Jetson

**Verificar que el Jetson está en modo recovery:**

```bash
lsusb | grep -i nvidia
# Debería mostrar algo como: "Bus 001 Device 005: ID 0955:7323 NVIDIA Corp. APX"
```

### Paso 1.3: Ejecutar SDK Manager

```bash
# Lanzar SDK Manager
sdkmanager

# En la interfaz gráfica:
# 1. Seleccionar "Jetson Orin Nano 8GB Developer Kit"
# 2. Target OS: "JetPack 6.2" (más reciente disponible)
# 3. Marcar "I accept the terms and conditions"
# 4. Click "Continue"
# 5. En "Select Target Components":
#    - ✅ Jetson OS
#    - ✅ Jetson SDK Components
#    - ✅ CUDA Toolkit
#    - ✅ TensorRT
#    - ✅ cuDNN
#    - ✅ VPI (Vision Programming Interface)
# 6. Click "Continue" y esperar ~45 minutos
```

**Durante el flasheo:**
- SDK Manager descargará ~8GB de archivos
- Flasheará la eMMC del Jetson automáticamente
- Pedirá configurar usuario/contraseña para el Jetson
- **Usuario sugerido:** `jetson`
- **Contraseña sugerida:** `4431Durr` (misma que DGX para consistencia)

### Paso 1.4: Activar Super Mode (67 TOPS)

Una vez que el Jetson arranque por primera vez, conectarse por SSH o en el monitor y ejecutar:

```bash
# Verificar modos disponibles
sudo /usr/sbin/nvpmodel -q

# Activar Super Mode (modo 2)
sudo /usr/sbin/nvpmodel -m 2

# Maximizar clocks (15W, 67 TOPS)
sudo /usr/sbin/jetson_clocks

# Verificar que esté activo
sudo /usr/sbin/nvpmodel -q
# Debería mostrar: "NV Power Mode: MAXN"
```

**Hacer Super Mode persistente al reinicio:**

```bash
# Agregar a /etc/rc.local (se ejecuta al boot)
sudo bash -c 'cat > /etc/rc.local << EOF
#!/bin/bash
/usr/sbin/nvpmodel -m 2
/usr/sbin/jetson_clocks
exit 0
EOF'

sudo chmod +x /etc/rc.local

# Habilitar servicio rc-local
sudo systemctl enable rc-local
```

---

## 📋 FASE 2: CONFIGURAR RED Y SSH

### Paso 2.1: Configurar IP estática 10.10.10.250

**Opción A: Por SSH (si el Jetson está en la red WiFi 192.168.20.x)**

```bash
# Desde el portátil MSI, escanear para encontrar la IP del Jetson en WiFi
sudo nmap -sn 192.168.20.0/24 | grep -B 2 -i nvidia

# SSH al Jetson (IP encontrada, ej: 192.168.20.xxx)
ssh jetson@192.168.20.xxx

# Configurar IP estática en eth0 para la red de cámaras
sudo nmcli con add type ethernet con-name camera-net ifname eth0 \
  ip4 10.10.10.250/24

# Activar la conexión
sudo nmcli con up camera-net

# Verificar
ip addr show eth0 | grep "inet "
# Debería mostrar: inet 10.10.10.250/24
```

**Opción B: Por monitor HDMI (si tienes un monitor conectado al Jetson)**

```bash
# En la terminal del Jetson (conectado por HDMI):
sudo nmcli con add type ethernet con-name camera-net ifname eth0 \
  ip4 10.10.10.250/24

sudo nmcli con up camera-net
```

### Paso 2.2: Configurar SSH keys desde DGX

```bash
# En el DGX Spark (192.168.20.57), generar claves SSH si no existen
ssh daviddgx@192.168.20.57
ssh-keygen -t ed25519 -C "daviddgx@dgx-spark" -f ~/.ssh/id_ed25519 -N ""

# Copiar la clave pública al Jetson
ssh-copy-id -i ~/.ssh/id_ed25519.pub jetson@10.10.10.250

# Probar conexión sin contraseña
ssh jetson@10.10.10.250 "hostname && uname -a"
# Debería conectar automáticamente
```

---

## 📋 FASE 3: INSTALAR DEPENDENCIAS EN EL JETSON

### Paso 3.1: Actualizar sistema y paquetes base

```bash
# SSH al Jetson desde el DGX
ssh jetson@10.10.10.250

# Actualizar sistema
sudo apt update
sudo apt upgrade -y

# Instalar dependencias de sistema
sudo apt install -y \
  python3-pip python3-venv \
  redis-server mosquitto mosquitto-clients \
  ffmpeg gstreamer1.0-tools gstreamer1.0-plugins-good \
  libopencv-dev python3-opencv \
  git curl wget htop iotop \
  v4l-utils onvif-tools

# Habilitar servicios
sudo systemctl enable redis-server mosquitto
sudo systemctl start redis-server mosquitto
```

### Paso 3.2: Crear estructura de directorios

```bash
# Crear workspace para Seedy Edge
mkdir -p ~/seedy-edge/{models,events,logs,scripts}

# Crear directorios para datos
sudo mkdir -p /data/edge/{frames,crops,events}
sudo chown -R jetson:jetson /data/edge
```

### Paso 3.3: Instalar Python packages

```bash
# Crear entorno virtual
cd ~/seedy-edge
python3 -m venv .venv
source .venv/bin/activate

# Instalar PyTorch para Jetson (ARM64, CUDA 12.6)
pip3 install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu126 \
  torch torchvision torchaudio

# Instalar Ultralytics (YOLOv8)
pip3 install ultralytics==8.3.0

# Instalar librerías de red y comunicación
pip3 install \
  redis==5.2.0 \
  paho-mqtt==2.1.0 \
  onvif-zeep==0.2.12 \
  wsdiscovery==2.0.0

# Instalar utilidades
pip3 install \
  opencv-python==4.10.0.84 \
  numpy==1.26.4 \
  pillow==11.0.0 \
  psutil==6.1.0
```

---

## 📋 FASE 4: CONVERTIR YOLO A TENSORRT

**CRÍTICO:** La conversión a TensorRT **debe hacerse EN el Jetson** (arquitectura ARM64).

### Paso 4.1: Copiar modelo YOLO desde DGX

```bash
# Desde el DGX, copiar YOLOv8s al Jetson
scp /home/daviddgx/seedy/yolo_models/yolov8s.pt jetson@10.10.10.250:~/seedy-edge/models/

# Copiar también el modelo Breed (para clasificación en DGX, no se usa en edge)
scp /home/daviddgx/seedy/yolo_models/seedy_breeds_best.pt jetson@10.10.10.250:~/seedy-edge/models/
```

### Paso 4.2: Convertir YOLOv8s a TensorRT FP16

```bash
# SSH al Jetson
ssh jetson@10.10.10.250

# Activar venv
cd ~/seedy-edge
source .venv/bin/activate

# Convertir YOLOv8s a TensorRT (formato .engine)
python3 << 'EOF'
from ultralytics import YOLO

# Cargar modelo
model = YOLO("models/yolov8s.pt")

# Exportar a TensorRT FP16 (optimizado para Jetson)
# Esto tarda ~10 minutos en Jetson Orin Nano
model.export(
    format="engine",
    imgsz=640,
    half=True,  # FP16 para velocidad
    device=0,   # GPU
    workspace=4,  # 4GB workspace para TensorRT
    verbose=True
)

print("✅ Conversión completada: models/yolov8s.engine")
EOF
```

**El archivo resultante será `models/yolov8s.engine` (~22MB).**

### Paso 4.3: Verificar modelo TensorRT

```bash
# Test rápido del modelo TensorRT
python3 << 'EOF'
from ultralytics import YOLO
import time

model = YOLO("models/yolov8s.engine")

# Test de inferencia
start = time.time()
results = model.predict(source="https://ultralytics.com/images/bus.jpg", conf=0.20, classes=[14, 15, 16])
elapsed = time.time() - start

print(f"⏱️ Tiempo de inferencia: {elapsed*1000:.1f}ms")
print(f"🎯 Detecciones: {len(results[0].boxes)}")
EOF
```

**Objetivo:** ≤50ms por frame (≥20 FPS) en 640×640.

---

## 📋 FASE 5: IMPLEMENTAR EDGE PIPELINE

### Paso 5.1: Crear supervisor de cámara

```bash
# Crear script de supervisión de cámaras
cat > ~/seedy-edge/scripts/camera_supervisor.py << 'EOF'
#!/usr/bin/env python3
"""
Seedy Edge Camera Supervisor
Procesa sub-stream de una cámara, detecta aves con YOLO TensorRT,
envía eventos al DGX vía Redis queue.
"""

import cv2
import redis
import json
import time
from ultralytics import YOLO
from datetime import datetime
import logging

# Configuración
CAMERA_ID = "gallinero_palacio_d1"  # Se sobrescribe por arg
RTSP_URL = "rtsp://admin:123456@10.10.10.108/stream2"
YOLO_MODEL = "/home/jetson/seedy-edge/models/yolov8s.engine"
REDIS_HOST = "192.168.20.57"  # DGX Spark
REDIS_PORT = 6379
REDIS_QUEUE = "seedy:edge:events"

# Clases COCO: bird(14), cat(15), dog(16)
TARGET_CLASSES = [14, 15, 16]

# Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'/home/jetson/seedy-edge/logs/{CAMERA_ID}.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

def main():
    log.info(f"🚀 Iniciando supervisor para {CAMERA_ID}")
    
    # Conectar Redis
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    log.info(f"✅ Redis conectado a {REDIS_HOST}:{REDIS_PORT}")
    
    # Cargar modelo YOLO TensorRT
    model = YOLO(YOLO_MODEL, task="detect")
    log.info(f"✅ Modelo YOLO cargado: {YOLO_MODEL}")
    
    # Abrir stream RTSP
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        log.error(f"❌ No se pudo abrir stream: {RTSP_URL}")
        return
    
    log.info(f"✅ Stream abierto: {RTSP_URL}")
    
    frame_count = 0
    detection_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            log.warning("⚠️ Frame vacío, reconectando...")
            cap.release()
            time.sleep(2)
            cap = cv2.VideoCapture(RTSP_URL)
            continue
        
        frame_count += 1
        
        # Inferencia YOLO cada frame (sub-stream 10-15fps es manejable)
        results = model.predict(
            source=frame,
            conf=0.20,
            classes=TARGET_CLASSES,
            verbose=False,
            device=0
        )
        
        boxes = results[0].boxes
        if len(boxes) > 0:
            detection_count += 1
            
            # Crear evento para DGX
            event = {
                "camera_id": CAMERA_ID,
                "timestamp": datetime.now().isoformat(),
                "frame_id": frame_count,
                "detections": []
            }
            
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                
                event["detections"].append({
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                    "confidence": conf,
                    "class": cls,
                    "class_name": model.names[cls]
                })
            
            # Enviar a Redis
            r.rpush(REDIS_QUEUE, json.dumps(event))
            
            if detection_count % 100 == 0:
                log.info(f"📊 Frames: {frame_count}, Detecciones: {detection_count}")
    
    cap.release()

if __name__ == "__main__":
    main()
EOF

chmod +x ~/seedy-edge/scripts/camera_supervisor.py
```

### Paso 5.2: Crear systemd service para auto-start

```bash
# Crear servicio systemd para cada cámara
sudo bash -c 'cat > /etc/systemd/system/seedy-edge-camera1.service << EOF
[Unit]
Description=Seedy Edge Camera Supervisor - Dahua
After=network.target redis.service

[Service]
Type=simple
User=jetson
WorkingDirectory=/home/jetson/seedy-edge
ExecStart=/home/jetson/seedy-edge/.venv/bin/python3 scripts/camera_supervisor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF'

# Habilitar y arrancar
sudo systemctl daemon-reload
sudo systemctl enable seedy-edge-camera1.service
sudo systemctl start seedy-edge-camera1.service

# Ver logs
sudo journalctl -u seedy-edge-camera1.service -f
```

---

## 📋 FASE 6: RECONFIGURAR DGX PARA RECIBIR EVENTOS EDGE

### Paso 6.1: Crear endpoint en backend DGX

Archivo: `backend/routers/edge_events.py`

```python
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import redis.asyncio as redis
import json
from typing import List

router = APIRouter(prefix="/vision/edge", tags=["Edge"])

# Redis client
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

class EdgeDetection(BaseModel):
    bbox: List[float]
    confidence: float
    class_: int
    class_name: str

class EdgeEvent(BaseModel):
    camera_id: str
    timestamp: str
    frame_id: int
    detections: List[EdgeDetection]

@router.post("/event")
async def receive_edge_event(event: EdgeEvent, background_tasks: BackgroundTasks):
    """
    Recibe eventos de detección del Jetson edge.
    El edge hace el YOLO tracking, el DGX solo recibe eventos de interés.
    """
    # Guardar evento
    await r.rpush(f"edge:events:{event.camera_id}", json.dumps(event.dict()))
    
    # TODO: Procesar con behavior_inference, mating_detector, etc.
    
    return {"status": "received", "camera": event.camera_id, "detections": len(event.detections)}
```

### Paso 6.2: Modificar capture_manager.py

Marcar cámaras como `edge_managed=True` para desactivar sub-stream YOLO en DGX:

```python
# En backend/services/capture_manager.py
# Agregar flag en CameraConfig:

@dataclass
class CameraConfig:
    camera_id: str
    rtsp_url_main: str
    rtsp_url_sub: str
    tile_size: int
    edge_managed: bool = False  # NUEVO: True si el Jetson procesa esta cámara

# En _start_sub_stream_loop, skip si edge_managed:
async def _start_sub_stream_loop(self, config: CameraConfig):
    if config.edge_managed:
        logger.info(f"📡 {config.camera_id} gestionada por edge, skip sub-stream en DGX")
        return
    
    # ... resto del código existente
```

---

## 📋 PRÓXIMOS PASOS (PTZ MVPSECAM)

Cuando lleguen las 2 cámaras PTZ MVPSECAM (1-2 días):

1. **Auto-discovery Onvif:**
   ```bash
   python3 -c "from wsdiscovery.discovery import ThreadedWSDiscovery; d = ThreadedWSDiscovery(); d.start(); devices = d.searchServices(); print([dev.getXAddrs() for dev in devices]); d.stop()"
   ```

2. **Asignar IPs estáticas:** 10.10.10.20 y 10.10.10.21

3. **Implementar MvpsecamPTZAdapter** (heredar de OnvifPTZAdapter)

4. **Integrar con edge pipeline:** supervisores adicionales para PTZ

---

## ✅ CHECKLIST COMPLETO

### Fase 1: Hardware
- [ ] Conectar alimentación DC al Jetson
- [ ] Conectar USB-C Jetson → Portátil
- [ ] Poner Jetson en modo recovery (botón REC)
- [ ] Verificar `lsusb | grep nvidia`

### Fase 2: Flasheo JetPack
- [ ] Instalar SDK Manager en portátil MSI
- [ ] Flashear JetPack 6.2 (~45 min)
- [ ] Configurar usuario `jetson` / password `4431Durr`
- [ ] Activar Super Mode (`nvpmodel -m 2`)
- [ ] Hacer Super Mode persistente (`/etc/rc.local`)

### Fase 3: Red y SSH
- [ ] Configurar IP estática 10.10.10.250/24 en eth0
- [ ] Copiar SSH keys desde DGX
- [ ] Verificar `ssh jetson@10.10.10.250`

### Fase 4: Software
- [ ] Instalar dependencias (Redis, MQTT, FFmpeg, etc.)
- [ ] Crear estructura `~/seedy-edge/`
- [ ] Instalar PyTorch + Ultralytics
- [ ] Copiar `yolov8s.pt` desde DGX
- [ ] Convertir a TensorRT: `yolov8s.engine`
- [ ] Verificar inferencia ≤50ms

### Fase 5: Edge Pipeline
- [ ] Crear `camera_supervisor.py`
- [ ] Crear systemd services (3 cámaras)
- [ ] Iniciar supervisores
- [ ] Verificar eventos en Redis queue del DGX

### Fase 6: DGX Reconfiguration
- [ ] Crear `edge_events.py` router
- [ ] Modificar `capture_manager.py` (flag `edge_managed`)
- [ ] Reiniciar seedy-backend en DGX
- [ ] Verificar flujo completo: Jetson → Redis → DGX

### Fase 7: PTZ (cuando lleguen)
- [ ] Onvif discovery
- [ ] Asignar 10.10.10.20 y .21
- [ ] Implementar MvpsecamPTZAdapter
- [ ] Agregar supervisores PTZ

---

## 📞 SOPORTE

Si encuentras problemas:
- **SDK Manager no detecta Jetson:** Verifica `lsusb`, reinicia en modo recovery
- **TensorRT conversión falla:** Actualiza Ultralytics `pip install -U ultralytics`
- **Inferencia lenta (>50ms):** Verifica Super Mode activo `nvpmodel -q`
- **Redis connection refused:** Firewall DGX, abrir puerto 6379

---

**Documento creado:** 4 mayo 2026  
**Autor:** GitHub Copilot (ia-expert mode)  
**Versión:** 1.0  
**Basado en:** prompt_seedy_v4.5_edge_jetson.md
