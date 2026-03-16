"""
Seedy Vision — Pipeline de Preparación de Datasets
Orquesta descarga → conversión → limpieza → split → YOLO format
"""
import shutil
import random
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from config import (
    load_catalog, DatasetEntry,
    DATASETS_DIR, CONFIGS_DIR, MODELS_DIR,
    DETECTION_CLASSES, BREED_CLASSES,
)
from dataset_discovery import download_dataset
from utils.convert_annotations import (
    coco_to_yolo, voc_to_yolo, folder_to_yolo_cls,
    validate_yolo_labels,
)
from utils.dataset_cleaning import (
    remove_duplicates, clean_bad_images, analyze_class_balance,
)

console = Console()


# ─────────────────────────────────────────────────────
# Estructura NAS / local para datasets YOLO
# ─────────────────────────────────────────────────────
#
# datasets/
# ├── raw/                    ← Datasets originales descargados
# │   ├── chicken/
# │   ├── pig/
# │   ├── cattle/
# │   └── multi/
# ├── unified/                ← Convertidos a YOLO, limpiados
# │   ├── detection/          ← Multi-especie detección
# │   │   ├── images/
# │   │   │   ├── train/
# │   │   │   ├── val/
# │   │   │   └── test/
# │   │   └── labels/
# │   │       ├── train/
# │   │       ├── val/
# │   │       └── test/
# │   ├── classification/     ← Razas, BCS, estado sanitario
# │   │   ├── chicken_breed/
# │   │   ├── pig_breed/
# │   │   ├── cattle_bcs/
# │   │   └── ...
# │   ├── segmentation/       ← Instance/semantic seg
# │   ├── behaviour/          ← Clasificación temporal
# │   ├── weight_estimation/  ← Regresión de peso
# │   ├── thermal/            ← Imágenes térmicas
# │   └── audio/              ← Clips de audio (tos, etc.)
# └── configs/                ← data.yaml para cada tarea YOLO
#


def setup_directory_structure(base: Optional[Path] = None):
    """Crea la estructura completa de directorios para datasets"""
    base = base or DATASETS_DIR
    
    dirs = [
        # Raw downloads
        "raw/chicken", "raw/pig", "raw/cattle", "raw/multi",
        
        # Unified detection
        "unified/detection/images/train",
        "unified/detection/images/val",
        "unified/detection/images/test",
        "unified/detection/labels/train",
        "unified/detection/labels/val",
        "unified/detection/labels/test",
        
        # Classification
        "unified/classification/chicken_breed",
        "unified/classification/pig_breed",
        "unified/classification/cattle_breed",
        "unified/classification/cattle_bcs",
        "unified/classification/health_status",
        
        # Other tasks
        "unified/segmentation/images/train",
        "unified/segmentation/images/val",
        "unified/segmentation/labels/train",
        "unified/segmentation/labels/val",
        "unified/behaviour",
        "unified/weight_estimation",
        "unified/thermal/images/train",
        "unified/thermal/images/val",
        "unified/thermal/labels/train",
        "unified/thermal/labels/val",
        "unified/audio",
        
        # Configs
        "configs",
    ]
    
    for d in dirs:
        (base / d).mkdir(parents=True, exist_ok=True)
    
    console.print(f"[green]✅ Estructura de directorios creada en {base}[/]")


# ─────────────────────────────────────────────────────
# Split train/val/test
# ─────────────────────────────────────────────────────

def split_dataset(images_dir: Path, labels_dir: Path,
                   output_base: Path,
                   train_ratio: float = 0.8,
                   val_ratio: float = 0.15,
                   test_ratio: float = 0.05,
                   seed: int = 42):
    """
    Divide un dataset YOLO en train/val/test.
    
    Args:
        images_dir: Directorio con imágenes
        labels_dir: Directorio con labels .txt
        output_base: Directorio base de salida
        train_ratio: Proporción train (0.8 = 80%)
    """
    random.seed(seed)
    
    img_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = sorted([
        f for f in images_dir.iterdir()
        if f.suffix.lower() in img_extensions
    ])
    
    # Solo incluir imágenes que tengan label
    paired = []
    for img in images:
        label = labels_dir / f"{img.stem}.txt"
        if label.exists():
            paired.append((img, label))
    
    random.shuffle(paired)
    
    n = len(paired)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    
    splits = {
        "train": paired[:n_train],
        "val": paired[n_train:n_train + n_val],
        "test": paired[n_train + n_val:],
    }
    
    for split_name, items in splits.items():
        img_out = output_base / "images" / split_name
        lbl_out = output_base / "labels" / split_name
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)
        
        for img, lbl in items:
            shutil.copy2(img, img_out / img.name)
            shutil.copy2(lbl, lbl_out / lbl.name)
        
        console.print(f"  {split_name}: {len(items)} imágenes")
    
    console.print(f"[green]✅ Split completado: {n} total → {output_base}[/]")
    return {k: len(v) for k, v in splits.items()}


# ─────────────────────────────────────────────────────
# Generar data.yaml para YOLO
# ─────────────────────────────────────────────────────

def generate_data_yaml(output_path: Path,
                        dataset_dir: Path,
                        class_names: list[str],
                        task: str = "detect"):
    """
    Genera el archivo data.yaml necesario para entrenar YOLO.
    """
    import yaml
    
    data = {
        "path": str(dataset_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(class_names),
        "names": class_names,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    
    console.print(f"[green]✅ data.yaml generado: {output_path}[/]")
    console.print(f"   Clases: {len(class_names)} → {class_names[:5]}...")


def generate_all_data_yamls():
    """Genera todos los data.yaml para las tareas principales"""
    configs_dir = DATASETS_DIR / "configs"
    unified = DATASETS_DIR / "unified"
    
    # 1. Detección multi-especie
    generate_data_yaml(
        configs_dir / "detection.yaml",
        unified / "detection",
        list(DETECTION_CLASSES.values()),
    )
    
    # 2. Clasificación de razas por especie
    for species, breeds in BREED_CLASSES.items():
        generate_data_yaml(
            configs_dir / f"{species}_breed.yaml",
            unified / "classification" / f"{species}_breed",
            breeds,
            task="classify",
        )
    
    # 3. Thermal detection
    generate_data_yaml(
        configs_dir / "thermal_detection.yaml",
        unified / "thermal",
        list(DETECTION_CLASSES.values()),
    )
    
    console.print(f"\n[green]✅ Todos los data.yaml generados en {configs_dir}[/]")


# ─────────────────────────────────────────────────────
# Pipeline completo
# ─────────────────────────────────────────────────────

def run_full_pipeline(species: Optional[str] = None,
                       priority: str = "high",
                       skip_download: bool = False,
                       dry_run: bool = False):
    """
    Pipeline completo: descarga → limpieza → conversión → split → YOLO yaml
    
    Args:
        species: Filtrar por especie (chicken/pig/cattle/None=todas)
        priority: Filtrar por prioridad (high/medium/low)
        skip_download: Si True, salta descarga (usa datasets ya descargados)
        dry_run: Si True, solo muestra plan sin ejecutar
    """
    console.print(Panel.fit(
        "[bold cyan]🚀 Seedy Vision — Pipeline de Preparación de Datasets[/]",
        border_style="cyan",
    ))
    
    # 1. Crear estructura
    console.print("\n[bold]1️⃣  Creando estructura de directorios...[/]")
    setup_directory_structure()
    
    # 2. Cargar catálogo
    catalog = load_catalog()
    if species:
        catalog = [d for d in catalog if d.species == species]
    if priority:
        catalog = [d for d in catalog if d.priority == priority]
    
    console.print(f"\n[bold]2️⃣  Datasets seleccionados: {len(catalog)}[/]")
    for d in catalog:
        console.print(f"  - {d.name} ({d.source}, {d.species}, {d.task})")
    
    if dry_run:
        console.print("\n[yellow]🏃 DRY RUN — no se ejecutarán acciones[/]")
        return
    
    # 3. Descargar
    if not skip_download:
        console.print(f"\n[bold]3️⃣  Descargando datasets...[/]")
        for ds in catalog:
            try:
                download_dataset(ds, DATASETS_DIR / "raw")
            except Exception as e:
                console.print(f"  [red]❌ {ds.name}: {e}[/]")
    
    # 4. Limpiar duplicados e imágenes malas
    console.print(f"\n[bold]4️⃣  Limpieza de datos...[/]")
    raw_dir = DATASETS_DIR / "raw"
    if raw_dir.exists():
        for species_dir in raw_dir.iterdir():
            if species_dir.is_dir():
                console.print(f"\n  [cyan]Limpiando {species_dir.name}...[/]")
                remove_duplicates(species_dir, dry_run=False)
                clean_bad_images(species_dir, dry_run=False)
    
    # 5. Generar data.yaml configs
    console.print(f"\n[bold]5️⃣  Generando configuraciones YOLO...[/]")
    generate_all_data_yamls()
    
    console.print(Panel.fit(
        "[bold green]✅ Pipeline completado[/]\n"
        f"Datasets en: {DATASETS_DIR}\n"
        f"Configs en: {DATASETS_DIR / 'configs'}",
        border_style="green",
    ))


# ─────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    args = sys.argv[1:]
    
    if not args or args[0] == "help":
        console.print("[bold]Seedy Vision — Dataset Preparation Pipeline[/]")
        console.print()
        console.print("Uso:")
        console.print("  python prepare_datasets.py setup        — Crear estructura de directorios")
        console.print("  python prepare_datasets.py yamls        — Generar data.yaml configs")
        console.print("  python prepare_datasets.py split <dir>  — Split train/val/test")
        console.print("  python prepare_datasets.py run [species] [priority] — Pipeline completo")
        console.print("  python prepare_datasets.py run --dry-run            — Solo mostrar plan")
    
    elif args[0] == "setup":
        setup_directory_structure()
    
    elif args[0] == "yamls":
        generate_all_data_yamls()
    
    elif args[0] == "split":
        if len(args) < 2:
            console.print("[yellow]Uso: python prepare_datasets.py split <dataset_dir>[/]")
        else:
            ds_dir = Path(args[1])
            imgs = ds_dir / "images"
            lbls = ds_dir / "labels"
            if imgs.exists() and lbls.exists():
                split_dataset(imgs, lbls, ds_dir)
            else:
                console.print(f"[red]Necesita {ds_dir}/images/ y {ds_dir}/labels/[/]")
    
    elif args[0] == "run":
        sp = None
        pr = "high"
        dry = "--dry-run" in args
        
        for a in args[1:]:
            if a in ("chicken", "pig", "cattle", "multi"):
                sp = a
            elif a in ("high", "medium", "low"):
                pr = a
        
        run_full_pipeline(species=sp, priority=pr, dry_run=dry)
    
    else:
        console.print(f"[red]Comando desconocido: {args[0]}[/]")
