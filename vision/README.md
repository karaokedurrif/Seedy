# Seedy Vision — Pipeline de Computer Vision

Sistema completo de visión artificial para monitorización de animales en granjas.

## Arquitectura

```
Cámara RGB/Thermal
       ↓
  Jetson Orin Nano (TensorRT)
       ↓
  Detección + Clasificación
       ↓
  ┌────┴────┐
  MQTT      API Backend
  ↓             ↓
  InfluxDB   Seedy App
  Grafana    Digital Twin
```

## Estructura

```
vision/
├── config.py                    # Configuración global + clases
├── dataset_discovery.py         # Descarga datasets públicos
├── prepare_datasets.py          # Pipeline: descarga → limpieza → YOLO
├── train_yolo.py                # Entrenamiento YOLO multi-tarea
├── jetson_inference.py          # Inferencia edge Jetson Orin Nano
├── dataset_factory.py           # Auto-captura de frames (dataset propio)
├── requirements.txt
│
├── configs/
│   ├── dataset_catalog.yaml     # Catálogo de 18 datasets públicos
│   ├── detection.yaml           # YOLO data config: 6 clases animales
│   ├── health_detection.yaml    # YOLO data config: 9 clases sanitarias
│   └── thermal_detection.yaml   # YOLO data config: detección térmico
│
├── utils/
│   ├── convert_annotations.py   # COCO/VOC/folder → YOLO
│   ├── dataset_cleaning.py      # Dedup, validación, balance
│   └── augmentation.py          # Data augmentation por especie
│
├── scripts/
│   └── deploy_jetson.sh         # Deploy modelos al Jetson
│
├── datasets/                    # Datasets descargados (gitignored)
│   ├── raw/
│   └── unified/
│
└── models/                      # Modelos entrenados (gitignored)
```

## Uso rápido

### 1. Listar datasets disponibles
```bash
cd vision
python dataset_discovery.py list
python dataset_discovery.py list chicken
```

### 2. Descargar datasets prioritarios
```bash
# Descargar todos los HIGH priority de cerdo
python dataset_discovery.py download pig high

# Descargar uno específico (por índice)
python dataset_discovery.py download-one 6
```

### 3. Preparar datasets para YOLO
```bash
# Pipeline completo (descarga + limpieza + split + yaml)
python prepare_datasets.py run pig high

# Solo crear estructura de directorios
python prepare_datasets.py setup

# Solo generar data.yaml
python prepare_datasets.py yamls
```

### 4. Entrenar modelo
```bash
# Listar tareas disponibles
python train_yolo.py list

# Entrenar detección multi-especie
python train_yolo.py train --task detection

# Entrenar con parámetros custom
python train_yolo.py train --task detection --epochs 200 --batch 8

# Exportar a TensorRT (para Jetson)
python train_yolo.py export --task detection --formats onnx engine
```

### 5. Deploy al Jetson
```bash
JETSON_HOST=jetson-seedy.local ./scripts/deploy_jetson.sh
```

### 6. Inferencia local (test)
```bash
# Webcam
python jetson_inference.py --model models/detection/best.pt --source 0 --show

# RTSP
python jetson_inference.py --model models/detection/best.engine \
  --source "rtsp://192.168.1.100:554/stream1" \
  --mqtt-topic seedy/vision/cam0
```

## Clases de detección

| ID | Clase   | Especie  |
|----|---------|----------|
| 0  | chicken | Gallina  |
| 1  | pig     | Cerdo    |
| 2  | cattle  | Vaca     |
| 3  | chick   | Pollito  |
| 4  | piglet  | Lechón   |
| 5  | calf    | Ternero  |

## Hardware requerido

### Entrenamiento (tu MSI Vector)
- RTX 5080 16GB VRAM
- 64GB RAM
- Ubuntu 24.04

### Inferencia (Jetson Orin Nano)
- 8GB RAM compartida
- JetPack 6.0+
- Cámara USB/CSI/RTSP

## Requisitos previos

```bash
# Kaggle API (para descargar datasets)
pip install kaggle
# Configurar: https://www.kaggle.com/settings → API → Create New Token
# Guardar en ~/.kaggle/kaggle.json

# Roboflow API (opcional)
export ROBOFLOW_API_KEY="tu-api-key"
```
