"""
Seedy Vision — Script de Entrenamiento YOLO
Entrena modelos YOLOv8/v11 para detección, segmentación y clasificación
Optimizado para RTX 5080 16GB VRAM
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime

from ultralytics import YOLO
from rich.console import Console
from rich.panel import Panel

console = Console()

# ── Configurations por tarea ─────────────────────────

TASK_CONFIGS = {
    # ── Detección multi-especie (principal) ──────────
    "detection": {
        "model": "yolo11m.pt",        # YOLOv11 medium
        "data": "configs/detection.yaml",
        "task": "detect",
        "imgsz": 640,
        "epochs": 150,
        "batch": 16,
        "patience": 25,
        "lr0": 0.01,
        "lrf": 0.01,
        "mosaic": 1.0,
        "mixup": 0.15,
        "copy_paste": 0.1,
        "degrees": 10.0,
        "translate": 0.1,
        "scale": 0.5,
        "shear": 2.0,
        "flipud": 0.0,
        "fliplr": 0.5,
        "hsv_h": 0.015,
        "hsv_s": 0.7,
        "hsv_v": 0.4,
    },
    
    # ── Detección sanitaria (lesiones) ───────────────
    "health": {
        "model": "yolo11m.pt",
        "data": "configs/health_detection.yaml",
        "task": "detect",
        "imgsz": 640,
        "epochs": 200,
        "batch": 16,
        "patience": 30,
        "lr0": 0.005,          # LR más bajo (clases difíciles)
        "lrf": 0.005,
        "mosaic": 1.0,
        "mixup": 0.2,
        "copy_paste": 0.2,     # Más copy-paste (clases raras)
    },
    
    # ── Detección térmica ────────────────────────────
    "thermal": {
        "model": "yolo11s.pt",         # Small (térmico más simple)
        "data": "configs/thermal_detection.yaml",
        "task": "detect",
        "imgsz": 640,
        "epochs": 100,
        "batch": 32,           # Batch más grande (imágenes simples)
        "patience": 20,
        "lr0": 0.01,
        "mosaic": 0.5,
        "hsv_h": 0.0,         # Sin augment de color en térmico
        "hsv_s": 0.0,
        "hsv_v": 0.2,
    },
    
    # ── Segmentación de instancia ────────────────────
    "segmentation": {
        "model": "yolo11m-seg.pt",
        "data": "configs/detection.yaml",
        "task": "segment",
        "imgsz": 640,
        "epochs": 150,
        "batch": 8,            # Batch reducido (seg usa más VRAM)
        "patience": 25,
        "lr0": 0.01,
    },
    
    # ── Clasificación de razas ───────────────────────
    "breed_chicken": {
        "model": "yolo11m-cls.pt",
        "data": "datasets/unified/classification/chicken_breed",
        "task": "classify",
        "imgsz": 224,
        "epochs": 100,
        "batch": 64,
        "patience": 20,
        "lr0": 0.001,          # Fine-tune LR
    },
    "breed_pig": {
        "model": "yolo11m-cls.pt",
        "data": "datasets/unified/classification/pig_breed",
        "task": "classify",
        "imgsz": 224,
        "epochs": 100,
        "batch": 64,
        "patience": 20,
        "lr0": 0.001,
    },
    "breed_cattle": {
        "model": "yolo11m-cls.pt",
        "data": "datasets/unified/classification/cattle_breed",
        "task": "classify",
        "imgsz": 224,
        "epochs": 100,
        "batch": 64,
        "patience": 20,
        "lr0": 0.001,
    },
}


def train(task: str, resume: bool = False, device: str = "0",
          extra_args: dict = None):
    """
    Entrena un modelo YOLO para la tarea especificada.
    
    Args:
        task: Nombre de la tarea (ver TASK_CONFIGS)
        resume: Continuar entrenamiento desde último checkpoint
        device: GPU device (0 = RTX 5080)
        extra_args: Argumentos extra para sobreescribir defaults
    """
    if task not in TASK_CONFIGS:
        console.print(f"[red]❌ Tarea '{task}' no encontrada[/]")
        console.print(f"   Tareas disponibles: {list(TASK_CONFIGS.keys())}")
        return
    
    cfg = TASK_CONFIGS[task].copy()
    
    if extra_args:
        cfg.update(extra_args)
    
    model_name = cfg.pop("model")
    data_path = cfg.pop("data")
    yolo_task = cfg.pop("task")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    project_name = f"models/{task}"
    run_name = f"{task}_{timestamp}"
    
    console.print(Panel.fit(
        f"[bold cyan]🏋️ Entrenamiento YOLO — {task}[/]\n"
        f"Modelo: {model_name}\n"
        f"Data: {data_path}\n"
        f"Épocas: {cfg.get('epochs', 100)}\n"
        f"Batch: {cfg.get('batch', 16)}\n"
        f"ImgSz: {cfg.get('imgsz', 640)}\n"
        f"Device: {device}",
        border_style="cyan",
    ))
    
    # Cargar modelo
    model = YOLO(model_name)
    
    # Entrenar
    results = model.train(
        data=data_path,
        task=yolo_task,
        device=device,
        project=project_name,
        name=run_name,
        exist_ok=True,
        resume=resume,
        verbose=True,
        save=True,
        save_period=10,
        plots=True,
        workers=8,
        **cfg,
    )
    
    console.print(Panel.fit(
        f"[bold green]✅ Entrenamiento completado[/]\n"
        f"Resultados: {project_name}/{run_name}\n"
        f"Best model: {project_name}/{run_name}/weights/best.pt",
        border_style="green",
    ))
    
    return results


def validate(task: str, weights: str = None, device: str = "0"):
    """Valida un modelo entrenado"""
    cfg = TASK_CONFIGS[task]
    
    if weights is None:
        # Buscar último best.pt
        runs = sorted(Path(f"models/{task}").glob("*/weights/best.pt"))
        if not runs:
            console.print(f"[red]❌ No se encontraron pesos para '{task}'[/]")
            return
        weights = str(runs[-1])
    
    console.print(f"[cyan]📊 Validando {task} con {weights}...[/]")
    
    model = YOLO(weights)
    results = model.val(data=cfg["data"], device=device, imgsz=cfg.get("imgsz", 640))
    
    return results


def export_model(task: str, weights: str = None,
                  formats: list[str] = None, device: str = "0"):
    """
    Exporta modelo a formatos optimizados.
    
    Formatos: onnx, engine (TensorRT), torchscript, coreml, openvino
    """
    if formats is None:
        formats = ["onnx", "engine"]  # ONNX + TensorRT por defecto
    
    if weights is None:
        runs = sorted(Path(f"models/{task}").glob("*/weights/best.pt"))
        if not runs:
            console.print(f"[red]❌ No se encontraron pesos para '{task}'[/]")
            return
        weights = str(runs[-1])
    
    console.print(f"[cyan]📦 Exportando {task}: {weights}[/]")
    
    model = YOLO(weights)
    cfg = TASK_CONFIGS.get(task, {})
    imgsz = cfg.get("imgsz", 640)
    
    for fmt in formats:
        console.print(f"\n  [yellow]→ Exportando a {fmt}...[/]")
        try:
            model.export(
                format=fmt,
                imgsz=imgsz,
                device=device,
                half=True if fmt == "engine" else False,  # FP16 para TensorRT
                simplify=True if fmt == "onnx" else False,
                dynamic=False,
            )
            console.print(f"  [green]✅ {fmt} exportado[/]")
        except Exception as e:
            console.print(f"  [red]❌ Error exportando {fmt}: {e}[/]")


# ─────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seedy Vision — YOLO Training")
    parser.add_argument("action", choices=["train", "val", "export", "list"],
                       help="Acción a ejecutar")
    parser.add_argument("--task", "-t", default="detection",
                       help="Tarea a entrenar")
    parser.add_argument("--device", "-d", default="0",
                       help="GPU device")
    parser.add_argument("--weights", "-w", default=None,
                       help="Path a pesos (.pt)")
    parser.add_argument("--resume", "-r", action="store_true",
                       help="Continuar entrenamiento")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--imgsz", type=int, default=None)
    parser.add_argument("--formats", nargs="+", default=None,
                       help="Formatos de export: onnx engine torchscript")
    
    args = parser.parse_args()
    
    if args.action == "list":
        console.print("[bold]Tareas disponibles:[/]")
        for name, cfg in TASK_CONFIGS.items():
            console.print(f"  [cyan]{name:20s}[/] → {cfg['model']} ({cfg['task']}, {cfg.get('epochs', '?')} epochs)")
        sys.exit(0)
    
    extra = {}
    if args.epochs:
        extra["epochs"] = args.epochs
    if args.batch:
        extra["batch"] = args.batch
    if args.imgsz:
        extra["imgsz"] = args.imgsz
    
    if args.action == "train":
        train(args.task, resume=args.resume, device=args.device,
              extra_args=extra if extra else None)
    
    elif args.action == "val":
        validate(args.task, weights=args.weights, device=args.device)
    
    elif args.action == "export":
        export_model(args.task, weights=args.weights,
                     formats=args.formats, device=args.device)
