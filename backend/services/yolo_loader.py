"""
Seedy Backend — Loader unificado de modelos YOLO v4.1

Carga lazy con soporte dual YOLOv8 / YOLOv11, caché singleton,
y exportación opcional a TensorRT para inferencia acelerada.

Uso:
    from services.yolo_loader import load_model, export_tensorrt

    # Carga lazy (singleton por ruta)
    model = load_model("yolov8s.pt")
    model = load_model("/app/yolo_models/seedy_breeds_best.pt")

    # Exportar a TensorRT (una sola vez, el .engine se cachea en disco)
    engine_path = export_tensorrt("yolov8s.pt", imgsz=640, half=True)
    model = load_model(engine_path)
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

YOLO_DEVICE = os.getenv("YOLO_DEVICE", "0")

# Caché global: path → (model, load_time, info)
_model_cache: Dict[str, Tuple] = {}


def load_model(
    model_path: str,
    device: str = YOLO_DEVICE,
    *,
    prefer_engine: bool = True,
) -> "YOLO":
    """Carga un modelo YOLO con caché singleton.

    Si prefer_engine=True y existe un .engine junto al .pt, carga TensorRT.
    Compatible con YOLOv8 y YOLOv11 (ambos usan ultralytics).

    Args:
        model_path: Ruta al .pt o .engine
        device: Device CUDA (default "0")
        prefer_engine: Si True, busca .engine antes de cargar .pt

    Returns:
        Modelo YOLO cargado
    """
    resolved = _resolve_path(model_path, prefer_engine)

    if resolved in _model_cache:
        model, _, _ = _model_cache[resolved]
        return model

    from ultralytics import YOLO

    t0 = time.time()
    logger.info(f"Cargando YOLO model: {resolved} en device={device}")

    model = YOLO(resolved)
    elapsed = time.time() - t0

    # Detectar versión
    version = _detect_version(model)

    info = {
        "path": resolved,
        "version": version,
        "task": getattr(model, "task", "detect"),
        "names": dict(model.names) if hasattr(model, "names") else {},
        "is_engine": resolved.endswith(".engine"),
        "load_time_ms": round(elapsed * 1000, 1),
    }

    _model_cache[resolved] = (model, time.time(), info)
    logger.info(
        f"YOLO {version} cargado: {os.path.basename(resolved)} "
        f"({len(info['names'])} clases, {info['task']}, {elapsed:.2f}s)"
    )

    return model


def get_model_info(model_path: str) -> Optional[dict]:
    """Info del modelo cacheado (sin cargarlo si no está)."""
    resolved = _resolve_path(model_path, prefer_engine=False)
    if resolved in _model_cache:
        _, _, info = _model_cache[resolved]
        return info
    # Probar con engine
    engine = resolved.rsplit(".", 1)[0] + ".engine"
    if engine in _model_cache:
        _, _, info = _model_cache[engine]
        return info
    return None


def export_tensorrt(
    model_path: str,
    *,
    imgsz: int = 640,
    half: bool = True,
    batch: int = 1,
    device: str = YOLO_DEVICE,
    workspace: int = 4,
) -> str:
    """Exporta modelo .pt a TensorRT .engine.

    El .engine se guarda junto al .pt. Si ya existe, retorna la ruta directamente.

    Args:
        model_path: Ruta al .pt
        imgsz: Resolución de entrada
        half: FP16 (recomendado para RTX 5080)
        batch: Batch size
        device: Device CUDA
        workspace: GB de workspace para TensorRT

    Returns:
        Ruta al .engine generado
    """
    pt_path = _resolve_path(model_path, prefer_engine=False)
    engine_path = pt_path.rsplit(".", 1)[0] + ".engine"

    if os.path.exists(engine_path):
        logger.info(f"TensorRT engine ya existe: {engine_path}")
        return engine_path

    from ultralytics import YOLO

    logger.info(f"Exportando TensorRT: {pt_path} → imgsz={imgsz}, half={half}, batch={batch}")
    t0 = time.time()

    model = YOLO(pt_path)
    model.export(
        format="engine",
        imgsz=imgsz,
        half=half,
        batch=batch,
        device=device,
        workspace=workspace,
    )

    elapsed = time.time() - t0
    logger.info(f"TensorRT export completado en {elapsed:.1f}s → {engine_path}")

    return engine_path


def unload_model(model_path: str) -> bool:
    """Descarga un modelo del caché."""
    resolved = _resolve_path(model_path, prefer_engine=False)
    removed = False
    for key in list(_model_cache.keys()):
        if key == resolved or key.startswith(resolved.rsplit(".", 1)[0]):
            del _model_cache[key]
            removed = True
            logger.info(f"Modelo descargado del caché: {key}")
    return removed


def reload_model(model_path: str, device: str = YOLO_DEVICE) -> "YOLO":
    """Recarga un modelo (descarga + carga fresca)."""
    unload_model(model_path)
    return load_model(model_path, device)


def list_cached_models() -> list:
    """Lista modelos actualmente en caché."""
    return [
        {**info, "cached_since": load_time}
        for _, (_, load_time, info) in _model_cache.items()
    ]


def warmup(model_path: str, device: str = YOLO_DEVICE, imgsz: int = 640) -> float:
    """Carga modelo + una inferencia dummy para calentar GPU.

    Returns: tiempo total de warmup en ms.
    """
    import numpy as np

    t0 = time.time()
    model = load_model(model_path, device)

    # Inferencia dummy
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    model(dummy, device=device, verbose=False)

    elapsed = (time.time() - t0) * 1000
    logger.info(f"Warmup completado: {os.path.basename(model_path)} en {elapsed:.0f}ms")
    return elapsed


# ── Utilidades internas ──

def _resolve_path(model_path: str, prefer_engine: bool = True) -> str:
    """Resuelve la ruta del modelo, prefiriendo .engine si existe."""
    if prefer_engine and model_path.endswith(".pt"):
        engine = model_path[:-3] + ".engine"
        if os.path.exists(engine):
            return engine
    return model_path


def _detect_version(model) -> str:
    """Detecta si el modelo es YOLOv8, v11, u otro."""
    try:
        # ultralytics >= 8.1 expone model.cfg o model.yaml
        cfg = getattr(model, "cfg", "") or ""
        if "yolo11" in str(cfg).lower() or "v11" in str(cfg).lower():
            return "v11"
        if "yolov8" in str(cfg).lower() or "v8" in str(cfg).lower():
            return "v8"
        # Fallback: buscar en el nombre del archivo
        name = str(getattr(model, "model_name", model.ckpt_path if hasattr(model, "ckpt_path") else ""))
        if "11" in name:
            return "v11"
        if "v8" in name or "8" in name:
            return "v8"
    except Exception:
        pass
    return "v8"  # default
