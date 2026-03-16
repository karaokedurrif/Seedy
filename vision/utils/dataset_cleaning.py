"""
Seedy Vision — Limpieza y Deduplicación de Datasets
"""
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import Optional

from PIL import Image
from rich.console import Console
from rich.progress import track
from tqdm import tqdm

console = Console()


# ─────────────────────────────────────────────────────
# Deduplicación por hash
# ─────────────────────────────────────────────────────

def compute_image_hash(path: Path, method: str = "md5") -> str:
    """Calcula hash de una imagen (contenido binario)"""
    h = hashlib.md5() if method == "md5" else hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(directory: Path, extensions: set = None) -> dict[str, list[Path]]:
    """
    Encuentra imágenes duplicadas por hash MD5.
    Returns: {hash: [path1, path2, ...]} solo para hashes con >1 archivo
    """
    if extensions is None:
        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    hash_map: dict[str, list[Path]] = defaultdict(list)
    
    files = [
        f for f in directory.rglob("*")
        if f.suffix.lower() in extensions and f.is_file()
    ]
    
    console.print(f"[cyan]🔍 Escaneando {len(files)} imágenes para duplicados...[/]")
    
    for f in track(files, description="Hashing..."):
        h = compute_image_hash(f)
        hash_map[h].append(f)
    
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    
    total_dupes = sum(len(paths) - 1 for paths in duplicates.values())
    console.print(f"  Encontrados: [bold]{total_dupes}[/] duplicados en {len(duplicates)} grupos")
    
    return duplicates


def remove_duplicates(directory: Path, dry_run: bool = True) -> int:
    """
    Elimina imágenes duplicadas (conserva la primera de cada grupo).
    
    Args:
        directory: Directorio a limpiar
        dry_run: Si True, solo muestra lo que haría sin borrar
    """
    duplicates = find_duplicates(directory)
    
    removed = 0
    for h, paths in duplicates.items():
        # Mantener la primera, eliminar el resto
        keep = paths[0]
        for dupe in paths[1:]:
            if dry_run:
                console.print(f"  [dim]DUPE: {dupe} (keep: {keep.name})[/]")
            else:
                # También eliminar el .txt de anotación si existe
                label = dupe.with_suffix(".txt")
                dupe.unlink()
                if label.exists():
                    label.unlink()
            removed += 1
    
    action = "Se eliminarían" if dry_run else "Eliminados"
    console.print(f"[green]{action} {removed} duplicados[/]")
    return removed


# ─────────────────────────────────────────────────────
# Perceptual hashing (imágenes similares)
# ─────────────────────────────────────────────────────

def perceptual_hash(path: Path, hash_size: int = 8) -> int:
    """
    Average hash perceptual — detecta imágenes visualmente similares
    incluso con diferente resolución o compresión
    """
    img = Image.open(path).convert("L").resize(
        (hash_size, hash_size), Image.Resampling.LANCZOS
    )
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return int(bits, 2)


def hamming_distance(h1: int, h2: int) -> int:
    """Distancia de Hamming entre dos hashes"""
    return bin(h1 ^ h2).count("1")


def find_similar_images(directory: Path, threshold: int = 5,
                         extensions: set = None) -> list[tuple[Path, Path, int]]:
    """
    Encuentra imágenes perceptualmente similares.
    
    Args:
        directory: Directorio a escanear 
        threshold: Distancia máxima de Hamming (0=idéntico, <5=muy similar)
    
    Returns: Lista de (img1, img2, distancia)
    """
    if extensions is None:
        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    
    files = [
        f for f in directory.rglob("*")
        if f.suffix.lower() in extensions and f.is_file()
    ]
    
    console.print(f"[cyan]🔍 Calculando hashes perceptuales para {len(files)} imágenes...[/]")
    
    hashes = {}
    for f in track(files, description="Hashing..."):
        try:
            hashes[f] = perceptual_hash(f)
        except Exception:
            continue
    
    # Comparar pares (O(n²) — aceptable para <50K imágenes)
    similar = []
    paths = list(hashes.keys())
    
    console.print(f"[cyan]🔍 Comparando {len(paths)} pares...[/]")
    
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            dist = hamming_distance(hashes[paths[i]], hashes[paths[j]])
            if dist <= threshold:
                similar.append((paths[i], paths[j], dist))
    
    console.print(f"  Encontrados: [bold]{len(similar)}[/] pares similares (threshold≤{threshold})")
    return similar


# ─────────────────────────────────────────────────────
# Validación de calidad de imagen
# ─────────────────────────────────────────────────────

def validate_images(directory: Path,
                     min_size: int = 32,
                     max_size: int = 8192,
                     min_filesize_kb: int = 5) -> dict:
    """
    Valida calidad de imágenes:
    - Archivos corruptos
    - Demasiado pequeñas
    - Demasiado grandes
    - Archivos casi vacíos
    """
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    files = [
        f for f in directory.rglob("*")
        if f.suffix.lower() in extensions and f.is_file()
    ]
    
    stats = {
        "total": len(files),
        "valid": 0,
        "corrupt": [],
        "too_small": [],
        "too_large": [],
        "too_light": [],  # filesize muy bajo
    }
    
    for f in track(files, description="Validando imágenes..."):
        # Filesize check
        fsize_kb = f.stat().st_size / 1024
        if fsize_kb < min_filesize_kb:
            stats["too_light"].append(f)
            continue
        
        try:
            img = Image.open(f)
            img.verify()  # Verificar integridad
            
            # Re-abrir para obtener tamaño (verify cierra el handle)
            img = Image.open(f)
            w, h = img.size
            
            if w < min_size or h < min_size:
                stats["too_small"].append(f)
            elif w > max_size or h > max_size:
                stats["too_large"].append(f)
            else:
                stats["valid"] += 1
                
        except Exception:
            stats["corrupt"].append(f)
    
    console.print(f"\n[bold]Validación de imágenes:[/]")
    console.print(f"  Total: {stats['total']}")
    console.print(f"  Válidas: [green]{stats['valid']}[/]")
    console.print(f"  Corruptas: [red]{len(stats['corrupt'])}[/]")
    console.print(f"  Muy pequeñas (<{min_size}px): [yellow]{len(stats['too_small'])}[/]")
    console.print(f"  Muy grandes (>{max_size}px): [yellow]{len(stats['too_large'])}[/]")
    console.print(f"  Filesize muy bajo (<{min_filesize_kb}KB): [yellow]{len(stats['too_light'])}[/]")
    
    return stats


def clean_bad_images(directory: Path, dry_run: bool = True) -> int:
    """Elimina imágenes corruptas y de muy baja calidad"""
    stats = validate_images(directory)
    
    to_remove = stats["corrupt"] + stats["too_light"]
    
    removed = 0
    for f in to_remove:
        if dry_run:
            console.print(f"  [dim]REMOVE: {f}[/]")
        else:
            f.unlink()
            label = f.with_suffix(".txt")
            if label.exists():
                label.unlink()
        removed += 1
    
    action = "Se eliminarían" if dry_run else "Eliminados"
    console.print(f"[green]{action} {removed} archivos problemáticos[/]")
    return removed


# ─────────────────────────────────────────────────────
# Balance de clases
# ─────────────────────────────────────────────────────

def analyze_class_balance(labels_dir: Path, class_names: Optional[list[str]] = None) -> dict:
    """
    Analiza distribución de clases en labels YOLO.
    Devuelve estadísticas útiles para decidir augmentation/sampling.
    """
    class_counts = defaultdict(int)
    total_objects = 0
    
    for label_file in sorted(labels_dir.glob("*.txt")):
        for line in label_file.read_text().strip().split("\n"):
            if not line.strip():
                continue
            cls_id = int(line.split()[0])
            class_counts[cls_id] += 1
            total_objects += 1
    
    console.print(f"\n[bold]Balance de clases ({total_objects} objetos):[/]")
    
    max_count = max(class_counts.values()) if class_counts else 1
    
    for cls_id in sorted(class_counts.keys()):
        count = class_counts[cls_id]
        pct = count / total_objects * 100
        bar = "█" * int(count / max_count * 30)
        name = class_names[cls_id] if class_names and cls_id < len(class_names) else f"class_{cls_id}"
        console.print(f"  {cls_id:3d} {name:20s} {count:6d} ({pct:5.1f}%) {bar}")
    
    return dict(class_counts)
