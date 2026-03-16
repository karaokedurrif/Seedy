#!/usr/bin/env python3
"""
NeoFarm — Entrenamiento YOLOv11 para detección de aves de corral.
Dataset: loum/poultry-chicken (2.1k imágenes, 5 clases)
Clases: Boiler-Chicken, Chicken, chicken, chicks, poussin
"""

from ultralytics import YOLO
from pathlib import Path
import argparse

DATASET_DIR = Path(__file__).parent / "poultry" / "poultry-chicken-1"
DATA_YAML = DATASET_DIR / "data.yaml"
PROJECT_DIR = Path(__file__).parent / "runs"


def train(epochs: int = 50, imgsz: int = 640, batch: int = 16, model_size: str = "n"):
    """Entrena YOLOv11 en el dataset de poultry."""
    model_name = f"yolo11{model_size}.pt"  # n=nano, s=small, m=medium, l=large, x=xlarge
    model = YOLO(model_name)

    results = model.train(
        data=str(DATA_YAML),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=0,  # GPU 0 (RTX 5080)
        project=str(PROJECT_DIR),
        name=f"poultry_yolo11{model_size}",
        patience=10,  # early stopping
        save=True,
        plots=True,
        amp=True,  # mixed precision (FP16) — aprovecha la 5080
        workers=8,
        exist_ok=True,
    )

    print(f"\n✅ Entrenamiento completado!")
    print(f"   Best model: {PROJECT_DIR}/poultry_yolo11{model_size}/weights/best.pt")
    print(f"   mAP@50: {results.results_dict.get('metrics/mAP50(B)', 'N/A')}")
    return results


def validate(model_path: str = None, model_size: str = "n"):
    """Valida el modelo en el set de validación."""
    if model_path is None:
        model_path = str(PROJECT_DIR / f"poultry_yolo11{model_size}" / "weights" / "best.pt")
    model = YOLO(model_path)
    metrics = model.val(data=str(DATA_YAML), device=0)
    print(f"\nmAP@50: {metrics.box.map50:.4f}")
    print(f"mAP@50-95: {metrics.box.map:.4f}")
    return metrics


def predict_image(image_path: str, model_path: str = None, model_size: str = "n", conf: float = 0.25):
    """Inferencia sobre una imagen."""
    if model_path is None:
        model_path = str(PROJECT_DIR / f"poultry_yolo11{model_size}" / "weights" / "best.pt")
    model = YOLO(model_path)
    results = model.predict(
        source=image_path,
        conf=conf,
        device=0,
        save=True,
        project=str(PROJECT_DIR),
        name="predict",
        exist_ok=True,
    )
    for r in results:
        print(f"Detecciones: {len(r.boxes)}")
        for box in r.boxes:
            cls = r.names[int(box.cls)]
            conf_val = float(box.conf)
            print(f"  → {cls}: {conf_val:.2f}")
    return results


def live_camera(model_path: str = None, model_size: str = "n", source: int = 0, conf: float = 0.25):
    """Inferencia en tiempo real con cámara."""
    if model_path is None:
        model_path = str(PROJECT_DIR / f"poultry_yolo11{model_size}" / "weights" / "best.pt")
    model = YOLO(model_path)
    results = model.predict(
        source=source,  # 0 = webcam, o URL RTSP
        conf=conf,
        device=0,
        show=True,
        stream=True,
    )
    for r in results:
        # Cada frame
        n = len(r.boxes)
        if n > 0:
            classes = [r.names[int(b.cls)] for b in r.boxes]
            print(f"Frame: {n} aves detectadas → {classes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeoFarm Poultry Vision — YOLOv11")
    parser.add_argument("mode", choices=["train", "val", "predict", "camera"],
                        help="Modo: train, val, predict, camera")
    parser.add_argument("--epochs", type=int, default=50, help="Épocas (default: 50)")
    parser.add_argument("--imgsz", type=int, default=640, help="Tamaño imagen (default: 640)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--model-size", type=str, default="n", choices=["n", "s", "m", "l", "x"],
                        help="Tamaño modelo: n(ano), s(mall), m(ed), l(arge), x(large)")
    parser.add_argument("--model-path", type=str, default=None, help="Path a modelo .pt custom")
    parser.add_argument("--image", type=str, default=None, help="Imagen para predict")
    parser.add_argument("--source", type=str, default="0", help="Cámara (0=webcam, URL RTSP)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confianza mínima (default: 0.25)")

    args = parser.parse_args()

    if args.mode == "train":
        train(epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, model_size=args.model_size)
    elif args.mode == "val":
        validate(model_path=args.model_path, model_size=args.model_size)
    elif args.mode == "predict":
        if args.image is None:
            # Usar una imagen de test del dataset
            test_imgs = list((DATASET_DIR / "test" / "images").glob("*"))
            if test_imgs:
                args.image = str(test_imgs[0])
                print(f"Usando imagen de test: {args.image}")
            else:
                print("Error: proporciona --image o pon imágenes en test/")
                exit(1)
        predict_image(args.image, model_path=args.model_path, model_size=args.model_size, conf=args.conf)
    elif args.mode == "camera":
        src = int(args.source) if args.source.isdigit() else args.source
        live_camera(model_path=args.model_path, model_size=args.model_size, source=src, conf=args.conf)
