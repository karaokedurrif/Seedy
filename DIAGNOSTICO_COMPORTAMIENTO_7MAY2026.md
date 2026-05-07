# DIAGNÓSTICO — COMPORTAMIENTO Y MONTAS GALLINERO PALACIO
**Fecha:** 7 Mayo 2026 10:20  
**Estado:** 🔴 **CRÍTICO — No se detectan aves**

---

## RESUMEN EJECUTIVO

**El sistema está funcionando pero NO detecta aves.** El Jetson envía eventos cada 6 segundos pero todos reportan "0 tracks".

---

## ✅ QUÉ SÍ FUNCIONA

| Componente | Estado | Métricas |
|------------|--------|----------|
| **CaptureManager DGX** | ✅ Activo | 48,328 sub-frames procesados hoy |
| **Jetson → DGX** | ✅ Comunicación | 17,831 edge events recibidos hoy (~3 eventos/min) |
| **Behavior Store** | ✅ Escribiendo | 37 KB de eventos hoy (2026-05-07.jsonl) |
| **Cámaras** | ✅ Streaming | 3 cámaras enviando video (sauna, nueva, gallinero) |
| **go2rtc** | ✅ Activo | Streams sub-stream funcionando |

---

## ❌ PROBLEMA PRINCIPAL

### Todos los edge events tienen "0 tracks"

```
2026-05-07 08:17:08,803 [INFO] Edge event 667f1f01 from jetson_orin_nano_01/vigi_gallinero: 0 tracks
2026-05-07 08:17:08,825 [INFO] Edge event ad5961d1 from jetson_orin_nano_01/dahua_sauna: 0 tracks
2026-05-07 08:17:08,827 [INFO] Edge event 2c0bda85 from jetson_orin_nano_01/vigi_nueva: 0 tracks
```

**Consecuencias:**
- ❌ No hay datos de comportamiento (snapshots vacíos)
- ❌ No se detectan montas (0 en 7 días)
- ❌ Digital twins no se actualizan
- ❌ No se genera inteligencia conductual

---

## 🔍 CAUSA RAÍZ

**YOLO en el Jetson NO está detectando aves.**

### Hipótesis (en orden de probabilidad):

### 1. **Confidence threshold demasiado alto** (MÁS PROBABLE)
El Jetson puede estar usando `conf=0.40` o más, demasiado restrictivo para gallinas (que COCO clasifica como "dog" con conf baja).

**Solución:** Bajar a `conf=0.20` (mismo threshold que DGX)

### 2. **YOLO no tiene modelo cargado correctamente**
El auto-export a TensorRT puede haber fallado silenciosamente.

**Verificar:** 
```bash
ssh jetson@192.168.20.68
cd ~/seedy-edge
ls -lh models/
```

Debe existir `yolov8s.engine` (TensorRT) o al menos `yolov8s.pt` (PyTorch).

### 3. **Clases COCO incorrectas**
El código puede estar filtrando solo `bird(14)` y perdiendo `dog(16)` + `cat(15)` que son las clases donde COCO clasifica gallinas.

**Verificar:** Código debe incluir `classes=[14, 15, 16]`

### 4. **Jetson no está corriendo el proceso edge**
No pudimos verificarlo (Jetson no responde por SSH).

**Solución:** Reiniciar proceso edge en el Jetson.

---

## 📊 MÉTRICAS ACTUALES

| Métrica | Valor | Estado |
|---------|-------|--------|
| Edge events hoy | 17,831 | ✅ OK |
| Edge events con tracks > 0 | 0 | ❌ CRÍTICO |
| Behavior snapshots con tracks | 0 | ❌ CRÍTICO |
| Montas detectadas (7d) | 0 | ❌ CRÍTICO |
| Aves identificadas hoy | 0 | ❌ CRÍTICO |
| Cobertura Re-ID | 4% (1/26) | ⚠️ BAJO |

---

## 🛠️ PLAN DE ACCIÓN

### Paso 1: Verificar Jetson está corriendo
```bash
ssh jetson@192.168.20.68
ps aux | grep python | grep -E 'edge|jetson_start'
```

**Si no hay procesos:** Reiniciar edge processing (ver sección Reiniciar Jetson)

### Paso 2: Ver logs del Jetson
```bash
ssh jetson@192.168.20.68
tail -100 ~/seedy-edge/logs/*
```

Buscar:
- Errores de YOLO
- "Model loaded" (debe aparecer al inicio)
- Detecciones YOLO (debe mostrar bbox count)

### Paso 3: Bajar confidence threshold
Editar código del Jetson y cambiar `conf=0.40` → `conf=0.20`

### Paso 4: Verificar clases COCO
Asegurar que se buscan `classes=[14, 15, 16]` (bird + dog + cat)

### Paso 5: Test manual de detección
```bash
ssh jetson@192.168.20.68
cd ~/seedy-edge
source .venv/bin/activate
python3 << 'EOF'
from ultralytics import YOLO
import cv2

model = YOLO('models/yolov8s.pt')
frame = cv2.imread('/tmp/test_frame.jpg')  # Capturar frame primero
results = model(frame, classes=[14, 15, 16], conf=0.20, verbose=True)
print(f'Detecciones: {len(results[0].boxes)}')
for box in results[0].boxes:
    print(f'  Clase {int(box.cls[0])}: conf={float(box.conf[0]):.2f}')
EOF
```

---

## 🔄 REINICIAR JETSON EDGE

Si el Jetson no tiene procesos edge corriendo:

```bash
ssh jetson@192.168.20.68
cd ~/seedy-edge

# Matar cualquier proceso previo
pkill -f jetson_start

# Reiniciar
source .venv/bin/activate
nohup python3 jetson_start_all_cameras.py > logs/edge_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Verificar
sleep 5
tail -50 logs/edge_*.log
```

Debe aparecer:
```
✅ Model loaded: yolov8s
✅ Connected to DGX backend
🎥 Processing camera: vigi_nueva
```

---

## 📈 MÉTRICAS ESPERADAS TRAS FIX

| Métrica | Antes | Después (esperado) |
|---------|-------|-------------------|
| Edge events con tracks > 0 | 0% | 60-80% |
| Detecciones por frame | 0 | 3-8 aves |
| Montas detectadas/día | 0 | 5-15 |
| Behavior snapshots válidos | 0% | 70-90% |

---

## 🚨 PRIORIDAD

**CRÍTICA** — Sin detecciones de aves, todo el sistema de comportamiento está ciego.

**Tiempo estimado para fix:** 30-60 minutos  
**Impacto:** Alto — Recuperar capacidad de análisis conductual

---

## CONTACTOS Y SIGUIENTES PASOS

1. Verificar estado del Jetson (procesos, logs)
2. Si Jetson no responde → reiniciar físicamente
3. Revisar configuración de confidence y clases
4. Test manual de detección
5. Monitorear edge events tras fix (deben aparecer tracks > 0)
6. Una vez funcionando → esperar 24h para acumular datos de comportamiento

---

**Última actualización:** 7 Mayo 2026 10:20  
**Próxima revisión:** Tras implementar fix en Jetson
