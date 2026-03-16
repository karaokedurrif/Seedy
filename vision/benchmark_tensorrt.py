#!/usr/bin/env python3
"""
Seedy Vision — Benchmark & Optimización TensorRT para Jetson

Usage:
  # Exportar modelo a TensorRT FP16
  python benchmark_tensorrt.py export --model best.pt --precision fp16

  # Benchmark completo (FP32 / FP16 / INT8)
  python benchmark_tensorrt.py benchmark --model best.pt --images cal_images/

  # Generar dataset de calibración INT8
  python benchmark_tensorrt.py calibrate --dataset data/train/images --n 500
"""
import os
import time
import shutil
import argparse
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.table import Table

console = Console()


# ─────────────────────────────────────────────────────
# Export a TensorRT
# ─────────────────────────────────────────────────────

def export_tensorrt(model_path: str,
                    precision: str = "fp16",
                    imgsz: int = 640,
                    batch: int = 1,
                    workspace: int = 4,
                    calibration_dir: str | None = None,
                    device: str = "0") -> Path:
    """
    Exporta modelo YOLO a TensorRT engine.
    
    Args:
        model_path: Ruta al modelo .pt
        precision: fp32, fp16, int8
        imgsz: Tamaño de imagen
        batch: Batch size
        workspace: GB de workspace para TensorRT
        calibration_dir: Directorio con imágenes de calibración (requerido para INT8)
        device: GPU device
    
    Returns: Ruta al .engine exportado
    """
    from ultralytics import YOLO
    
    console.print(f"[bold cyan]Exportando {model_path} → TensorRT {precision.upper()}[/]")
    
    model = YOLO(model_path)
    
    export_args = {
        "format": "engine",
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "workspace": workspace,
        "verbose": True,
    }
    
    if precision == "fp16":
        export_args["half"] = True
    elif precision == "int8":
        export_args["int8"] = True
        if calibration_dir:
            export_args["data"] = calibration_dir
    
    result = model.export(**export_args)
    engine_path = Path(result)
    
    size_mb = engine_path.stat().st_size / 1024 / 1024
    console.print(f"[green]✓ Engine: {engine_path} ({size_mb:.1f} MB)[/]")
    
    return engine_path


# ─────────────────────────────────────────────────────
# Benchmark
# ─────────────────────────────────────────────────────

def benchmark_model(model_path: str,
                    imgsz: int = 640,
                    warmup: int = 50,
                    iterations: int = 200,
                    device: str = "0") -> dict:
    """
    Benchmark de latencia y throughput.
    
    Returns: {
        "model": str,
        "avg_ms": float,
        "p50_ms": float,
        "p95_ms": float,
        "p99_ms": float,
        "fps": float,
        "gpu_mem_mb": float,
    }
    """
    from ultralytics import YOLO
    
    model = YOLO(model_path)
    
    # Imagen de prueba sintética
    dummy = np.random.randint(0, 255, (imgsz, imgsz, 3), dtype=np.uint8)
    
    # Warmup
    console.print(f"[dim]Warmup ({warmup} iters)...[/]")
    for _ in range(warmup):
        model(dummy, imgsz=imgsz, device=device, verbose=False)
    
    # Benchmark
    latencies = []
    console.print(f"[cyan]Benchmarking ({iterations} iters)...[/]")
    for i in range(iterations):
        t0 = time.perf_counter()
        model(dummy, imgsz=imgsz, device=device, verbose=False)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)  # ms
    
    latencies = np.array(latencies)
    
    # GPU memory (si CUDA disponible)
    gpu_mem = 0
    try:
        import torch
        if torch.cuda.is_available():
            gpu_mem = torch.cuda.max_memory_allocated(device) / 1024 / 1024
    except ImportError:
        pass
    
    return {
        "model": str(model_path),
        "avg_ms": float(np.mean(latencies)),
        "p50_ms": float(np.percentile(latencies, 50)),
        "p95_ms": float(np.percentile(latencies, 95)),
        "p99_ms": float(np.percentile(latencies, 99)),
        "fps": float(1000.0 / np.mean(latencies)),
        "gpu_mem_mb": gpu_mem,
    }


def benchmark_all_precisions(model_path: str,
                              imgsz: int = 640,
                              calibration_dir: str | None = None,
                              device: str = "0") -> list[dict]:
    """
    Benchmark comparativo: PyTorch, ONNX, TensorRT FP16, TensorRT INT8.
    """
    from ultralytics import YOLO
    
    results = []
    model_dir = Path(model_path).parent
    
    # 1. PyTorch original
    console.rule("[bold]PyTorch (FP32)")
    results.append(benchmark_model(model_path, imgsz=imgsz, device=device))
    results[-1]["precision"] = "PyTorch FP32"
    
    # 2. ONNX
    console.rule("[bold]ONNX")
    m = YOLO(model_path)
    onnx_path = m.export(format="onnx", imgsz=imgsz, device=device)
    results.append(benchmark_model(onnx_path, imgsz=imgsz, device=device))
    results[-1]["precision"] = "ONNX FP32"
    
    # 3. TensorRT FP16
    console.rule("[bold]TensorRT FP16")
    fp16_path = export_tensorrt(model_path, precision="fp16", imgsz=imgsz, device=device)
    results.append(benchmark_model(str(fp16_path), imgsz=imgsz, device=device))
    results[-1]["precision"] = "TensorRT FP16"
    
    # 4. TensorRT INT8 (si hay datos de calibración)
    if calibration_dir and Path(calibration_dir).exists():
        console.rule("[bold]TensorRT INT8")
        int8_path = export_tensorrt(
            model_path, precision="int8", imgsz=imgsz,
            calibration_dir=calibration_dir, device=device
        )
        results.append(benchmark_model(str(int8_path), imgsz=imgsz, device=device))
        results[-1]["precision"] = "TensorRT INT8"
    
    # Tabla comparativa
    table = Table(title="🏁 Benchmark Comparativo Seedy Vision")
    table.add_column("Formato", style="cyan")
    table.add_column("Avg (ms)", justify="right")
    table.add_column("P95 (ms)", justify="right")
    table.add_column("FPS", justify="right", style="green")
    table.add_column("GPU MB", justify="right")
    table.add_column("Speedup", justify="right", style="yellow")
    
    base_fps = results[0]["fps"]
    for r in results:
        speedup = r["fps"] / base_fps
        table.add_row(
            r["precision"],
            f"{r['avg_ms']:.1f}",
            f"{r['p95_ms']:.1f}",
            f"{r['fps']:.1f}",
            f"{r['gpu_mem_mb']:.0f}",
            f"{speedup:.2f}x",
        )
    
    console.print(table)
    
    return results


# ─────────────────────────────────────────────────────
# Dataset de calibración INT8
# ─────────────────────────────────────────────────────

def generate_calibration_dataset(dataset_dir: str,
                                  output_dir: str = "calibration",
                                  n_images: int = 500,
                                  seed: int = 42) -> Path:
    """
    Genera un subset representativo para calibración INT8.
    Selecciona imágenes diversas del dataset de entrenamiento.
    """
    import random
    from PIL import Image
    
    random.seed(seed)
    dataset_path = Path(dataset_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Recoger todas las imágenes
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    all_images = [
        p for p in dataset_path.rglob("*")
        if p.suffix.lower() in exts
    ]
    
    if not all_images:
        console.print(f"[red]No se encontraron imágenes en {dataset_dir}[/]")
        return output_path
    
    # Seleccionar subset
    n = min(n_images, len(all_images))
    selected = random.sample(all_images, n)
    
    console.print(f"[cyan]Copiando {n} imágenes para calibración INT8[/]")
    
    for i, img_path in enumerate(selected):
        # Validar que se puede abrir
        try:
            Image.open(img_path).verify()
            dest = output_path / f"cal_{i:04d}{img_path.suffix}"
            shutil.copy2(img_path, dest)
        except Exception:
            continue
    
    final_count = len(list(output_path.glob("*")))
    console.print(f"[green]✓ {final_count} imágenes en {output_path}[/]")
    
    return output_path


# ─────────────────────────────────────────────────────
# Profiler de memoria Jetson
# ─────────────────────────────────────────────────────

def profile_jetson() -> dict:
    """
    Lee métricas del sistema Jetson (tegrastats).
    Para usar en combinación con benchmark.
    """
    info = {
        "platform": "unknown",
        "gpu_freq_mhz": 0,
        "gpu_util_pct": 0,
        "ram_used_mb": 0,
        "ram_total_mb": 0,
        "power_w": 0,
        "temp_c": 0,
    }
    
    # Detectar Jetson
    try:
        with open("/proc/device-tree/model", "r") as f:
            info["platform"] = f.read().strip()
    except FileNotFoundError:
        info["platform"] = "Not Jetson (or /proc/device-tree/model not found)"
    
    # GPU frequency
    try:
        with open("/sys/devices/gpu.0/devfreq/17000000.ga10b/cur_freq", "r") as f:
            info["gpu_freq_mhz"] = int(f.read().strip()) // 1_000_000
    except FileNotFoundError:
        pass
    
    # RAM
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
            for line in meminfo.split("\n"):
                if line.startswith("MemTotal"):
                    info["ram_total_mb"] = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable"):
                    available = int(line.split()[1]) // 1024
                    info["ram_used_mb"] = info["ram_total_mb"] - available
    except FileNotFoundError:
        pass
    
    # Temperatura GPU
    try:
        for zone in Path("/sys/class/thermal/").glob("thermal_zone*"):
            type_file = zone / "type"
            if type_file.exists():
                zone_type = type_file.read_text().strip()
                if "gpu" in zone_type.lower():
                    temp = int((zone / "temp").read_text().strip()) / 1000
                    info["temp_c"] = temp
                    break
    except Exception:
        pass
    
    return info


# ─────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seedy Vision — TensorRT Benchmark")
    sub = parser.add_subparsers(dest="command")
    
    # Export
    p_export = sub.add_parser("export", help="Exportar a TensorRT")
    p_export.add_argument("--model", required=True)
    p_export.add_argument("--precision", default="fp16", choices=["fp32", "fp16", "int8"])
    p_export.add_argument("--imgsz", type=int, default=640)
    p_export.add_argument("--batch", type=int, default=1)
    p_export.add_argument("--calibration-dir", default=None)
    p_export.add_argument("--device", default="0")
    
    # Benchmark
    p_bench = sub.add_parser("benchmark", help="Benchmark completo")
    p_bench.add_argument("--model", required=True)
    p_bench.add_argument("--imgsz", type=int, default=640)
    p_bench.add_argument("--calibration-dir", default=None)
    p_bench.add_argument("--device", default="0")
    
    # Calibrate
    p_cal = sub.add_parser("calibrate", help="Generar dataset de calibración INT8")
    p_cal.add_argument("--dataset", required=True)
    p_cal.add_argument("--output", default="calibration")
    p_cal.add_argument("--n", type=int, default=500)
    
    # Jetson info
    sub.add_parser("jetson-info", help="Info del sistema Jetson")
    
    args = parser.parse_args()
    
    if args.command == "export":
        export_tensorrt(
            args.model,
            precision=args.precision,
            imgsz=args.imgsz,
            batch=args.batch,
            calibration_dir=args.calibration_dir,
            device=args.device,
        )
    
    elif args.command == "benchmark":
        results = benchmark_all_precisions(
            args.model,
            imgsz=args.imgsz,
            calibration_dir=args.calibration_dir,
            device=args.device,
        )
        # Guardar resultados
        import json
        out = Path("benchmark_results.json")
        out.write_text(json.dumps(results, indent=2))
        console.print(f"[green]Resultados guardados en {out}[/]")
    
    elif args.command == "calibrate":
        generate_calibration_dataset(args.dataset, args.output, args.n)
    
    elif args.command == "jetson-info":
        info = profile_jetson()
        for k, v in info.items():
            console.print(f"  {k}: {v}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
