"""
Seedy Vision — Dataset Discovery & Download
Descarga datasets desde Kaggle, Roboflow, Zenodo y GitHub
"""
import os
import shutil
import subprocess
import zipfile
import tarfile
from pathlib import Path
from typing import Optional

import httpx
import yaml
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from tqdm import tqdm

from config import (
    load_catalog, DatasetEntry,
    DATASETS_DIR, CONFIGS_DIR,
)

console = Console()


# ─────────────────────────────────────────────────────
# Listar datasets del catálogo
# ─────────────────────────────────────────────────────

def list_datasets(species: Optional[str] = None, priority: Optional[str] = None):
    """Muestra el catálogo de datasets en tabla bonita"""
    catalog = load_catalog()
    
    if species:
        catalog = [d for d in catalog if d.species == species]
    if priority:
        catalog = [d for d in catalog if d.priority == priority]
    
    table = Table(title="📦 Seedy Vision — Catálogo de Datasets")
    table.add_column("#", style="dim", width=3)
    table.add_column("Nombre", style="cyan", max_width=40)
    table.add_column("Especie", style="green")
    table.add_column("Tarea", style="yellow")
    table.add_column("Formato", style="magenta")
    table.add_column("Imgs", justify="right", style="bold")
    table.add_column("Fuente", style="blue")
    table.add_column("Prior.", style="red")
    
    for i, d in enumerate(catalog, 1):
        prior_style = {"high": "bold red", "medium": "yellow", "low": "dim"}.get(d.priority, "")
        table.add_row(
            str(i),
            d.name,
            d.species,
            d.task,
            d.annotation_format,
            str(d.images),
            d.source,
            f"[{prior_style}]{d.priority}[/]"
        )
    
    console.print(table)
    console.print(f"\nTotal: {len(catalog)} datasets")
    return catalog


# ─────────────────────────────────────────────────────
# Descarga por fuente
# ─────────────────────────────────────────────────────

def download_kaggle(dataset: DatasetEntry, target_dir: Path) -> Path:
    """Descarga dataset desde Kaggle API"""
    if not dataset.kaggle_id:
        raise ValueError(f"Dataset {dataset.name} no tiene kaggle_id")
    
    target_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]⬇ Kaggle:[/] {dataset.kaggle_id}")
    
    # Verificar que kaggle CLI está configurado
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists():
        console.print("[red]❌ Configura ~/.kaggle/kaggle.json primero[/]")
        console.print("   → https://www.kaggle.com/settings → API → Create New Token")
        return target_dir
    
    cmd = [
        "kaggle", "datasets", "download",
        "-d", dataset.kaggle_id,
        "-p", str(target_dir),
        "--unzip",
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        console.print(f"  [green]✅ Descargado → {target_dir}[/]")
    else:
        console.print(f"  [red]❌ Error: {result.stderr}[/]")
    
    return target_dir


def download_roboflow(dataset: DatasetEntry, target_dir: Path,
                       format: str = "yolov8") -> Path:
    """Descarga dataset desde Roboflow"""
    if not dataset.roboflow_id:
        raise ValueError(f"Dataset {dataset.name} no tiene roboflow_id")
    
    target_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]⬇ Roboflow:[/] {dataset.roboflow_id}")
    
    api_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not api_key:
        console.print("[yellow]⚠ ROBOFLOW_API_KEY no definida — usando descarga pública[/]")
    
    try:
        from roboflow import Roboflow
        rf = Roboflow(api_key=api_key) if api_key else Roboflow()
        
        parts = dataset.roboflow_id.split("/")
        project = rf.workspace(parts[0]).project(parts[1])
        version = project.version(1)  # Última versión
        ds = version.download(format, location=str(target_dir))
        
        console.print(f"  [green]✅ Descargado → {target_dir}[/]")
    except Exception as e:
        console.print(f"  [red]❌ Error Roboflow: {e}[/]")
        console.print(f"  [dim]Descarga manual: {dataset.url}[/]")
    
    return target_dir


def download_zenodo(dataset: DatasetEntry, target_dir: Path) -> Path:
    """Descarga dataset desde Zenodo API"""
    if not dataset.zenodo_id:
        raise ValueError(f"Dataset {dataset.name} no tiene zenodo_id")
    
    target_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]⬇ Zenodo:[/] record {dataset.zenodo_id}")
    
    api_url = f"https://zenodo.org/api/records/{dataset.zenodo_id}"
    
    try:
        resp = httpx.get(api_url, timeout=30)
        resp.raise_for_status()
        record = resp.json()
        
        files = record.get("files", [])
        console.print(f"  [dim]{len(files)} archivo(s) encontrado(s)[/]")
        
        for f in files:
            fname = f["key"]
            furl = f["links"]["self"]
            fsize = f.get("size", 0)
            
            dest = target_dir / fname
            if dest.exists() and dest.stat().st_size == fsize:
                console.print(f"  ⏭  {fname} ya existe, skip")
                continue
            
            console.print(f"  ⬇ {fname} ({fsize / 1024 / 1024:.1f} MB)")
            with httpx.stream("GET", furl, timeout=300) as stream:
                stream.raise_for_status()
                with open(dest, "wb") as fout:
                    for chunk in stream.iter_bytes(chunk_size=131072):
                        fout.write(chunk)
            
            # Auto-extract zips
            if fname.endswith(".zip"):
                console.print(f"  📦 Extrayendo {fname}...")
                with zipfile.ZipFile(dest, "r") as zf:
                    zf.extractall(target_dir)
            elif fname.endswith((".tar.gz", ".tgz")):
                console.print(f"  📦 Extrayendo {fname}...")
                with tarfile.open(dest, "r:gz") as tf:
                    tf.extractall(target_dir)
        
        console.print(f"  [green]✅ Descargado → {target_dir}[/]")
    except Exception as e:
        console.print(f"  [red]❌ Error Zenodo: {e}[/]")
    
    return target_dir


def download_github(dataset: DatasetEntry, target_dir: Path) -> Path:
    """Clona repo desde GitHub"""
    target_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]⬇ GitHub:[/] {dataset.url}")
    
    if (target_dir / ".git").exists():
        console.print("  ⏭  Ya clonado, haciendo pull...")
        subprocess.run(["git", "-C", str(target_dir), "pull"], capture_output=True)
    else:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", dataset.url, str(target_dir)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            console.print(f"  [green]✅ Clonado → {target_dir}[/]")
        else:
            console.print(f"  [red]❌ Error: {result.stderr}[/]")
    
    return target_dir


# ─────────────────────────────────────────────────────
# Dispatcher principal
# ─────────────────────────────────────────────────────

DOWNLOADERS = {
    "kaggle": download_kaggle,
    "roboflow": download_roboflow,
    "zenodo": download_zenodo,
    "github": download_github,
}


def download_dataset(dataset: DatasetEntry, base_dir: Optional[Path] = None) -> Path:
    """Descarga un dataset según su fuente"""
    base = base_dir or DATASETS_DIR
    # Estructura: datasets/{species}/{sanitized_name}/
    safe_name = dataset.name.lower().replace(" ", "_").replace("/", "_")[:60]
    target = base / dataset.species / safe_name
    
    downloader = DOWNLOADERS.get(dataset.source)
    if not downloader:
        console.print(f"[red]❌ Fuente no soportada: {dataset.source}[/]")
        return target
    
    return downloader(dataset, target)


def download_all(species: Optional[str] = None,
                 priority: Optional[str] = None,
                 base_dir: Optional[Path] = None):
    """Descarga todos los datasets del catálogo (filtrado opcional)"""
    catalog = load_catalog()
    
    if species:
        catalog = [d for d in catalog if d.species == species]
    if priority:
        catalog = [d for d in catalog if d.priority == priority]
    
    console.print(f"\n[bold]📥 Descargando {len(catalog)} datasets...[/]\n")
    
    results = {"ok": [], "error": []}
    for ds in catalog:
        try:
            download_dataset(ds, base_dir)
            results["ok"].append(ds.name)
        except Exception as e:
            console.print(f"[red]❌ {ds.name}: {e}[/]")
            results["error"].append(ds.name)
    
    console.print(f"\n[green]✅ Descargados: {len(results['ok'])}[/]")
    if results["error"]:
        console.print(f"[red]❌ Errores: {len(results['error'])}[/]")
        for name in results["error"]:
            console.print(f"  - {name}")


# ─────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    args = sys.argv[1:]
    
    if not args or args[0] == "list":
        species = args[1] if len(args) > 1 else None
        list_datasets(species=species)
    
    elif args[0] == "download":
        species = None
        priority = None
        for i, arg in enumerate(args[1:], 1):
            if arg in ("chicken", "pig", "cattle", "multi"):
                species = arg
            elif arg in ("high", "medium", "low"):
                priority = arg
        
        if not species and not priority:
            console.print("[yellow]Uso: python dataset_discovery.py download [species] [priority][/]")
            console.print("  Ejemplo: python dataset_discovery.py download pig high")
        else:
            download_all(species=species, priority=priority)
    
    elif args[0] == "download-one":
        if len(args) < 2:
            console.print("[yellow]Uso: python dataset_discovery.py download-one <índice>[/]")
        else:
            catalog = load_catalog()
            idx = int(args[1]) - 1
            if 0 <= idx < len(catalog):
                download_dataset(catalog[idx])
            else:
                console.print(f"[red]Índice fuera de rango (1-{len(catalog)})[/]")
    
    else:
        console.print("[yellow]Comandos: list, download, download-one[/]")
