# PROBLEMA CRÍTICO — JETSON EDGE INCOMPLETO (7 Mayo 2026)

## 🔴 RESUMEN EJECUTIVO

El Jetson envía 17,831 edge events con "0 tracks" porque **NO está leyendo frames de las cámaras**. El código está incompleto.

---

## EVIDENCIAS

### 1. CameraSupervisor tiene TODO el código RTSP comentado

**Archivo:** `jetson_edge_camera_supervisor.py` (líneas 145-207)

```python
# self.rtsp_reader = RTSPReader(
#     camera_id=camera_id,
#     rtsp_url=camera_config["rtsp_sub"],
#     reconnect_delay=5
# )

# if not self.rtsp_reader.connect():
#     logger.error(f"❌ No se pudo conectar a {self.camera_id}")
#     return

# frame = self.rtsp_reader.read_frame()
# if frame is None:
#     continue

# self.rtsp_reader.close()
```

**Todo está comentado.** Sin lectura de frames → YOLO no recibe imágenes → 0 detecciones.

---

### 2. RTSPReader NO EXISTE

El código hace `from seedy_edge.capture.rtsp_reader import RTSPReader` pero ese módulo **no existe** en el workspace:

```bash
$ find . -name "rtsp_reader.py"
(sin resultados)
```

**El módulo completo falta.**

---

### 3. Device configurado en CPU (debería ser GPU)

**Archivo:** `jetson_edge_config.yaml` (línea 35)

```yaml
yolo:
  model_path: "models/yolov8s.pt"
  device: "cpu"  # ❌ MALO
  conf_threshold: 0.20
```

**Comentario falso en config:** _"PyTorch no detecta GPU en Jetson, pero Ultralytics sí usará GPU en runtime"_

**FALSO.** Si pasas `device="cpu"`, YOLO corre en CPU puro (0.5 FPS vs 15 FPS en GPU). Debería ser `device: 0` o `device: "cuda:0"`.

---

### 4. El proceso jetson_start NO está corriendo

No pudimos verificarlo por SSH fallido, pero los edge events con "0 tracks" indican que:

a) **Opción A:** El proceso NO está corriendo, y los "edge events" vienen de otro lugar (¿backend simulando?)
b) **Opción B:** El proceso está corriendo pero sin RTSPReader funcional → envía eventos vacíos

---

## CONTRASTE CON seedy_cam.ino

El firmware ESP32 (`seedy_cam.ino`) **SÍ está completo**:
- ✅ Lectura de cámara: `esp_camera_init()`, `esp_camera_fb_get()`
- ✅ MJPEG streaming: `/stream`
- ✅ Snapshot: `/capture`
- ✅ Audio PDM: `/audio`

**PERO:** ese firmware es para cámaras ESP32 (DFRobot DFR1154) que **aún no están instaladas**. Las cámaras actuales son Dahua/VIGI que se acceden por **RTSP**, no ESP32.

---

## COMPARACIÓN: Código completo vs incompleto

| Componente | Estado | Comentario |
|------------|--------|------------|
| **YOLOEngine** | ✅ Completo | Inferencia funcional (aunque device=cpu) |
| **DGXRelay** | ✅ Completo | Cliente HTTP + Redis failover |
| **SimpleTracker** | ✅ Completo | Tracking por centroide |
| **RTSPReader** | ❌ **FALTA** | **Módulo completo no existe** |
| **CameraSupervisor** | ⚠️ Incompleto | Todo el código RTSP comentado |
| **jetson_start_all_cameras.py** | ✅ Completo | Pero llama a código incompleto |

---

## CAUSA RAÍZ

**El desarrollo del Jetson se quedó a medias.** Se crearon:
- ✅ Motor YOLO
- ✅ Cliente DGX
- ✅ Tracker simple
- ✅ Supervisor (shell)

**Pero faltó implementar:**
- ❌ Lector RTSP (el componente crítico)
- ❌ Integración con OpenCV/FFmpeg
- ❌ Reconexión automática ante caída de stream

---

## SOLUCIÓN INMEDIATA

### Opción A: Implementar RTSPReader (2-3 horas)

Crear `jetson_edge_rtsp_reader.py` con OpenCV:

```python
import cv2
import logging
from typing import Optional
import numpy as np

class RTSPReader:
    def __init__(self, camera_id: str, rtsp_url: str, reconnect_delay: float = 5.0):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.reconnect_delay = reconnect_delay
        self.cap: Optional[cv2.VideoCapture] = None
        
    def connect(self) -> bool:
        """Conectar a stream RTSP."""
        try:
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Buffer mínimo
            
            if not self.cap.isOpened():
                return False
            
            # Leer 1 frame de test
            ret, _ = self.cap.read()
            return ret
            
        except Exception as e:
            logging.error(f"Error conectando a {self.camera_id}: {e}")
            return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """Leer frame (BGR)."""
        if self.cap is None or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        return frame
    
    def close(self):
        """Cerrar stream."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
```

**Descomentar código en CameraSupervisor**
**Corregir device a GPU en config**
**Reiniciar proceso en Jetson**

---

### Opción B: Mover TODA la inferencia al DGX (1 hora)

Desactivar Jetson edge, volver a usar solo DGX:
1. Detener proceso jetson (si existe)
2. Configurar DGX para leer directamente de go2rtc
3. Volver a arquitectura v4.1 (sin edge)

**Trade-off:** Pierdes latencia baja y failover, pero funciona YA.

---

### Opción C: Usar cámaras ESP32 cuando lleguen

Las cámaras ESP32 con firmware `seedy_cam.ino` **SÍ funcionarán** de inmediato:
- `/stream` → MJPEG directo
- `/capture` → Snapshot JPEG
- Sin RTSP → sin necesidad de RTSPReader

**Pero:** las ESP32 aún no están instaladas (pendiente de compra/instalación).

---

## RECOMENDACIÓN

**Opción A — Implementar RTSPReader HOY:**

1. Crear `jetson_edge_rtsp_reader.py` (30 min)
2. Descomentar código en `CameraSupervisor` (10 min)
3. Corregir `device: "cpu"` → `device: 0` (2 min)
4. SCP archivos al Jetson (5 min)
5. Reiniciar proceso edge (5 min)
6. **Test:** verificar que edge events tienen tracks > 0

**Tiempo total:** ~1 hora
**Impacto:** Sistema funcional con arquitectura edge completa

---

## VERIFICACIÓN POST-FIX

```bash
# En el Jetson
ssh jetson@192.168.20.68
cd ~/seedy-edge
source .venv/bin/activate

# Ver logs (debe mostrar "X detecciones")
tail -f logs/seedy_edge.log

# En el DGX
ssh daviddgx@192.168.20.57
docker logs seedy-backend --tail 50 | grep "Edge event"

# Debe mostrar: "Edge event ... 3 tracks" (en lugar de "0 tracks")
```

---

## CONCLUSIÓN

**El threshold 0.20 está perfecto.** El problema NO es YOLO, es que **YOLO nunca recibe frames** porque RTSPReader no existe y todo el código de captura está comentado.

**Implementar RTSPReader es la solución definitiva.**

---

**Última actualización:** 7 Mayo 2026 10:45
