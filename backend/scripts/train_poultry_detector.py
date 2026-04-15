#!/usr/bin/env python3
"""
Seedy — Script de entrenamiento del detector de gallinas

Ejecutar cuando data/curated_frames/ tenga ≥500 frames anotados.
Esto entrenará un YOLOv8s detector específico para gallinas que
reemplazará la dependencia de COCO para detección.

Uso:
    python scripts/train_poultry_detector.py [--epochs 100] [--batch 16] [--imgsz 640]

Fases de integración:
    Fase 1 (ahora):     COCO detector → breed clasificador → Gemini
    Fase 2 (≥500 frames): COCO + Poultry detector (ensemble) → breed clasificador
    Fase 3 (≥2000 frames): Poultry detector solo (COCO eliminado)
"""

import argparse
import sys
from pathlib import Path

FRAMES_DIR = Path("data/curated_frames")
CLASSES_FILE = FRAMES_DIR / "classes.txt"


def check_dataset():
    """Verifica que hay suficientes datos para entrenar."""
    images = list((FRAMES_DIR / "images").glob("*.jpg"))
    labels = list((FRAMES_DIR / "labels").glob("*.txt"))

    print(f"📊 Dataset status:")
    print(f"   Images: {len(images)}")
    print(f"   Labels: {len(labels)}")

    if len(images) < 500:
        print(f"\n⚠️ Necesitas al menos 500 frames. Tienes {len(images)}.")
        print(f"   Faltan {500 - len(images)} frames más.")
        print(f"   El CaptureManager genera ~50-100 frames/día.")
        return False

    if not CLASSES_FILE.exists():
        print("❌ Falta classes.txt en data/curated_frames/")
        return False

    return True


def create_dataset_yaml(split_ratio: float = 0.8):
    """Crea dataset.yaml con split train/val."""
    import random
    import shutil

    images = sorted((FRAMES_DIR / "images").glob("*.jpg"))
    random.seed(42)
    random.shuffle(images)

    split = int(len(images) * split_ratio)
    train_images = images[:split]
    val_images = images[split:]

    # Crear directorios split
    for d in ["train/images", "train/labels", "val/images", "val/labels"]:
        (FRAMES_DIR / d).mkdir(parents=True, exist_ok=True)

    # Copiar a train/val
    for img in train_images:
        label = FRAMES_DIR / "labels" / f"{img.stem}.txt"
        shutil.copy2(img, FRAMES_DIR / "train/images" / img.name)
        if label.exists():
            shutil.copy2(label, FRAMES_DIR / "train/labels" / label.name)

    for img in val_images:
        label = FRAMES_DIR / "labels" / f"{img.stem}.txt"
        shutil.copy2(img, FRAMES_DIR / "val/images" / img.name)
        if label.exists():
            shutil.copy2(label, FRAMES_DIR / "val/labels" / label.name)

    # Leer clases
    classes = CLASSES_FILE.read_text().strip().split("\n")
    names_block = "\n".join(f"  {i}: {c}" for i, c in enumerate(classes))

    yaml_content = f"""# Seedy Poultry Detector Dataset
# Auto-generated from curated frames
path: {FRAMES_DIR.resolve()}
train: train/images
val: val/images

names:
{names_block}
"""
    yaml_path = FRAMES_DIR / "dataset.yaml"
    yaml_path.write_text(yaml_content)

    print(f"✅ Dataset split: {len(train_images)} train, {len(val_images)} val")
    print(f"   YAML: {yaml_path}")

    return str(yaml_path)


def train(epochs: int = 100, batch: int = 16, imgsz: int = 640):
    """Entrena el detector de gallinas."""
    from ultralytics import YOLO

    yaml_path = create_dataset_yaml()

    print(f"\n🚀 Iniciando entrenamiento:")
    print(f"   Epochs: {epochs}")
    print(f"   Batch: {batch}")
    print(f"   ImgSz: {imgsz}")

    model = YOLO("yolov8s.pt")  # Pre-trained COCO como base
    model.train(
        data=yaml_path,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=0,
        project="data/yolo_training",
        name="poultry_detector_v1",
        freeze=10,          # Congelar 10 capas del backbone (transfer learning)
        lr0=0.001,
        augment=True,
        mosaic=1.0,
        mixup=0.3,
        degrees=15,
        flipud=0.5,
        fliplr=0.5,
        workers=4,          # Necesita shm_size: 2g en docker-compose
        exist_ok=True,      # Reusar directorio si existe
    )

    print("\n✅ Entrenamiento completado")
    print("   Copiar best.pt a yolo_models/seedy_poultry_detect.pt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Seedy poultry detector")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--check-only", action="store_true", help="Solo verificar dataset")
    args = parser.parse_args()

    if not check_dataset():
        if not args.check_only:
            print("\nUsa --check-only para ver estado sin entrenar")
        sys.exit(1)

    if args.check_only:
        sys.exit(0)

    train(args.epochs, args.batch, args.imgsz)
