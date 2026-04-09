"""
Seedy Backend — Pipeline de entrenamiento YOLO

Gestiona el ciclo de vida del modelo YOLO custom:
  1. Recolección automática de datos etiquetados
  2. Fine-tune sobre modelo base
  3. Evaluación y promoción del nuevo modelo
  4. Exportación para producción

Los datos se recopilan durante la operación normal:
  - Cada detección YOLO (COCO) + confirmación Gemini → etiqueta refinada
  - Frames manuales del usuario → anotación asistida
  - El modelo se reentrena periódicamente con los datos acumulados
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

YOLO_DATA_DIR = Path(os.environ.get("YOLO_DATA_DIR", "/app/yolo_dataset"))
YOLO_MODELS_DIR = Path(os.environ.get("YOLO_MODELS_DIR", "/app/yolo_models"))
YOLO_BASE_MODEL = os.environ.get("YOLO_MODEL", "yolov8s.pt")

# Clases para el modelo custom de Seedy — sincronizado con yolo_detector.py
# 3 categorías: poultry (0-10), pests (11-14), infra (15-19)
SEEDY_CLASSES = {
    # ── Aves de corral ──
    "gallina": 0,
    "gallo": 1,
    "pollito": 2,
    "pollo_juvenil": 3,
    "sussex": 4,
    "bresse": 5,
    "marans": 6,
    "orpington": 7,
    "araucana": 8,
    "castellana": 9,
    "pita_pinta": 10,
    # ── Plagas ──
    "gorrion": 11,
    "paloma": 12,
    "rata": 13,
    "depredador": 14,
    # ── Infraestructura ──
    "comedero": 15,
    "bebedero": 16,
    "nido": 17,
    "aseladero": 18,
    "huevo": 19,
}

# Mapeo inverso
SEEDY_CLASS_NAMES = {v: k for k, v in SEEDY_CLASSES.items()}

# Sub-conjuntos por categoría (útil para filtrar etiquetas)
POULTRY_CLASS_IDS = set(range(0, 11))
PEST_CLASS_IDS = set(range(11, 15))
INFRA_CLASS_IDS = set(range(15, 20))


def save_confirmed_detection(
    frame_bytes: bytes,
    detections: list[dict],
    gemini_breeds: list[dict] | None = None,
    split: str = "train",
) -> Optional[str]:
    """
    Guarda un frame con detecciones confirmadas para entrenamiento.

    Si gemini_breeds está disponible, refina las etiquetas YOLO
    usando la identificación de raza de Gemini.

    Args:
        frame_bytes: JPEG original
        detections: detecciones YOLO (bbox, confidence)
        gemini_breeds: info de raza de Gemini [{"breed": ..., "bbox": ...}]
        split: "train" (85%) o "val" (15%)
    """
    if not detections:
        return None

    # Decidir split automáticamente (85/15)
    import random
    if split == "auto":
        split = "val" if random.random() < 0.15 else "train"

    images_dir = YOLO_DATA_DIR / "images" / split
    labels_dir = YOLO_DATA_DIR / "labels" / split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    # Nombre secuencial
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    existing = list(images_dir.glob(f"{ts}_*.jpg"))
    seq = len(existing) + 1
    stem = f"{ts}_{seq:04d}"

    img_path = images_dir / f"{stem}.jpg"
    img_path.write_bytes(frame_bytes)

    # Generar etiquetas
    lines = []
    for i, det in enumerate(detections):
        bn = det.get("bbox_norm", [])
        if len(bn) != 4:
            continue

        x1, y1, x2, y2 = bn
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        width = x2 - x1
        height = y2 - y1

        # Determinar clase: si hay info de Gemini, usar raza; si no, gallina/gallo
        cls_id = 0  # gallina por defecto
        if gemini_breeds and i < len(gemini_breeds):
            gb = gemini_breeds[i]
            breed = gb.get("breed", "").lower()
            sex = gb.get("sex", "unknown")

            # Buscar raza en SEEDY_CLASSES
            for class_name, cid in SEEDY_CLASSES.items():
                if class_name in breed:
                    cls_id = cid
                    break
            else:
                # No hay raza específica → usar sexo
                cls_id = 1 if sex == "male" else 0

        lines.append(f"{cls_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

    label_path = labels_dir / f"{stem}.txt"
    label_path.write_text("\n".join(lines))

    logger.debug(f"Training frame saved: {img_path} ({len(lines)} labels)")
    return str(img_path)


def get_dataset_summary() -> dict:
    """Resumen completo del dataset de entrenamiento."""
    stats = {
        "train_images": 0, "val_images": 0,
        "train_labels": 0, "val_labels": 0,
        "total_annotations": 0,
        "class_distribution": {},
        "dataset_ready": False,
    }

    for split in ("train", "val"):
        img_dir = YOLO_DATA_DIR / "images" / split
        lbl_dir = YOLO_DATA_DIR / "labels" / split

        if img_dir.exists():
            stats[f"{split}_images"] = len(list(img_dir.glob("*.jpg")))
        if lbl_dir.exists():
            label_files = list(lbl_dir.glob("*.txt"))
            stats[f"{split}_labels"] = len(label_files)

            # Contar anotaciones por clase
            for lf in label_files:
                for line in lf.read_text().strip().splitlines():
                    parts = line.split()
                    if not parts:
                        continue
                    cls_id = int(parts[0])
                    cls_name = SEEDY_CLASS_NAMES.get(cls_id, f"class_{cls_id}")
                    stats["class_distribution"][cls_name] = (
                        stats["class_distribution"].get(cls_name, 0) + 1
                    )
                    stats["total_annotations"] += 1

    # Consideramos "listo" si hay al menos 50 imágenes de train
    stats["dataset_ready"] = stats["train_images"] >= 50
    stats["classes"] = SEEDY_CLASSES
    stats["models_dir"] = str(YOLO_MODELS_DIR)
    return stats


def prepare_dataset_yaml() -> str:
    """Genera/actualiza dataset.yaml compatible con ultralytics."""
    yaml_path = YOLO_DATA_DIR / "dataset.yaml"

    names_block = "\n".join(f"  {v}: {k}" for k, v in SEEDY_CLASSES.items())

    content = (
        f"# Seedy YOLO Dataset\n"
        f"# Auto-generated — {datetime.now().isoformat()}\n"
        f"\n"
        f"path: {YOLO_DATA_DIR}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"\n"
        f"nc: {len(SEEDY_CLASSES)}\n"
        f"names:\n{names_block}\n"
    )
    yaml_path.write_text(content)
    logger.info(f"Dataset YAML written: {yaml_path}")
    return str(yaml_path)


async def train_model(
    epochs: int = 50,
    batch: int = 16,
    imgsz: int = 640,
    base_model: str | None = None,
) -> dict:
    """
    Lanza fine-tune de YOLO con los datos recopilados.

    Entrena en background y guarda el mejor modelo en YOLO_MODELS_DIR.

    Returns:
        {"status": "started"|"error", "run_dir": ..., "message": ...}
    """
    from ultralytics import YOLO

    dataset_yaml = prepare_dataset_yaml()

    # Verificar datos mínimos
    summary = get_dataset_summary()
    if not summary["dataset_ready"]:
        return {
            "status": "error",
            "message": (
                f"Dataset insuficiente: {summary['train_images']} imágenes de train "
                f"(mínimo 50). Sigue recopilando datos con las cámaras."
            ),
            "stats": summary,
        }

    YOLO_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    run_name = f"seedy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    model_base = base_model or YOLO_BASE_MODEL
    model = YOLO(model_base)

    try:
        results = model.train(
            data=dataset_yaml,
            epochs=epochs,
            batch=batch,
            imgsz=imgsz,
            project=str(YOLO_MODELS_DIR),
            name=run_name,
            device=os.environ.get("YOLO_DEVICE", "0"),
            patience=10,       # Early stopping
            save=True,
            plots=True,
            verbose=True,
            workers=0,         # Evita multiprocessing → no necesita /dev/shm grande
        )

        # Copiar best.pt a ubicación conocida
        best_pt = YOLO_MODELS_DIR / run_name / "weights" / "best.pt"
        if best_pt.exists():
            target = YOLO_MODELS_DIR / "seedy_best.pt"
            shutil.copy2(best_pt, target)
            logger.info(f"🐔 New best model: {target}")
            return {
                "status": "completed",
                "run_dir": str(YOLO_MODELS_DIR / run_name),
                "best_model": str(target),
                "message": f"Entrenamiento completado. Modelo guardado en {target}",
            }

        return {
            "status": "completed",
            "run_dir": str(YOLO_MODELS_DIR / run_name),
            "message": "Entrenamiento completado pero no se encontró best.pt",
        }

    except Exception as e:
        logger.error(f"Training failed: {e}")
        return {
            "status": "error",
            "message": f"Error en entrenamiento: {e}",
        }


def list_models() -> list[dict]:
    """Lista modelos YOLO disponibles."""
    models = []

    # Modelo base COCO
    models.append({
        "name": YOLO_BASE_MODEL,
        "type": "coco_pretrained",
        "path": YOLO_BASE_MODEL,
    })

    # Modelos entrenados
    if YOLO_MODELS_DIR.exists():
        for pt_file in sorted(YOLO_MODELS_DIR.glob("**/*.pt")):
            models.append({
                "name": pt_file.stem,
                "type": "custom",
                "path": str(pt_file),
                "size_mb": round(pt_file.stat().st_size / 1024 / 1024, 1),
            })

    return models
