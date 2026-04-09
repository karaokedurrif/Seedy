"""Seedy Backend — YOLO Model Loader con soporte dual v8/v11 + TensorRT.

Carga modelos YOLO de forma centralizada, con soporte para:
- YOLOv8 (actual producción)
- YOLOv11 (cuando esté disponible)
- TensorRT export para RTX 5080
"""

import logging
import os
from pathlib import Path
from typing import Any

from ultralytics import YOLO

logger = logging.getLogger(__name__)

# Registrar modelos disponibles
YOLO_MODELS: dict[str, dict[str, Any]] = {
    "coco_v8": {
        "path": os.environ.get("YOLO_MODEL", "yolov8s.pt"),
        "type": "detect",
        "classes": {14: "bird", 15: "cat"},
        "tensorrt": False,
    },
    "coco_v11": {
        "path": "yolo11s.pt",
        "type": "detect",
        "classes": {14: "bird", 15: "cat"},
        "tensorrt": True,
    },
    "breed_v3": {
        "path": os.environ.get("YOLO_BREED_MODEL", "/app/yolo_models/seedy_breeds_best.pt"),
        "type": "classify",
        "classes_count": 20,
        "tensorrt": False,
    },
}

# Cache de modelos cargados
_loaded: dict[str, YOLO] = {}


def load_yolo(model_key: str, device: str | None = None) -> YOLO:
    """Carga un modelo YOLO por clave. Cache en memoria.

    Args:
        model_key: Clave del modelo en YOLO_MODELS.
        device: Dispositivo CUDA (default: YOLO_DEVICE env o '0').

    Returns:
        Modelo YOLO cargado.
    """
    if model_key in _loaded:
        return _loaded[model_key]

    config = YOLO_MODELS.get(model_key)
    if not config:
        raise ValueError(f"Modelo YOLO desconocido: {model_key}. Disponibles: {list(YOLO_MODELS.keys())}")

    model_path = config["path"]
    if device is None:
        device = os.environ.get("YOLO_DEVICE", "0")

    # TensorRT export si corresponde
    if config.get("tensorrt") and Path(model_path).exists():
        engine_path = model_path.replace(".pt", ".engine")
        if not Path(engine_path).exists():
            logger.info(f"[YOLOLoader] Exporting {model_key} to TensorRT...")
            try:
                model = YOLO(model_path)
                model.export(format="engine", device=device, half=True, imgsz=640)
                model_path = engine_path
                logger.info(f"[YOLOLoader] TensorRT export done: {engine_path}")
            except Exception as e:
                logger.warning(f"[YOLOLoader] TensorRT export failed: {e}. Using .pt")
        else:
            model_path = engine_path

    model = YOLO(model_path)
    _loaded[model_key] = model
    logger.info(f"[YOLOLoader] Loaded {model_key}: {model_path} (device={device})")
    return model


def get_active_coco_model() -> str:
    """Devuelve la clave del modelo COCO activo (configurable via env)."""
    return os.environ.get("YOLO_COCO_MODEL", "coco_v8")


def list_models() -> dict[str, dict]:
    """Lista modelos registrados y su estado de carga."""
    return {
        key: {
            "path": cfg["path"],
            "type": cfg["type"],
            "loaded": key in _loaded,
            "tensorrt": cfg.get("tensorrt", False),
        }
        for key, cfg in YOLO_MODELS.items()
    }
