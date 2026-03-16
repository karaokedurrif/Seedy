"""
Seedy Vision — Conversores de Anotaciones
Convierte diferentes formatos a YOLO unificado
"""
import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from rich.console import Console

console = Console()


@dataclass
class BBox:
    """Bounding box normalizada YOLO: class_id x_center y_center width height"""
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float
    
    def to_yolo_line(self) -> str:
        return f"{self.class_id} {self.x_center:.6f} {self.y_center:.6f} {self.width:.6f} {self.height:.6f}"


# ─────────────────────────────────────────────────────
# COCO → YOLO
# ─────────────────────────────────────────────────────

def coco_to_yolo(coco_json: Path, output_dir: Path,
                 class_map: Optional[dict[int, int]] = None):
    """
    Convierte anotaciones COCO (JSON) a YOLO (txt por imagen).
    
    Args:
        coco_json: Path al archivo JSON COCO
        output_dir: Directorio donde crear los .txt YOLO
        class_map: Mapeo {coco_cat_id: yolo_class_id} (opcional)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(coco_json, "r") as f:
        coco = json.load(f)
    
    # Mapear image_id → filename
    img_map = {img["id"]: img for img in coco["images"]}
    
    # Agrupar anotaciones por imagen
    ann_by_img: dict[int, list] = {}
    for ann in coco.get("annotations", []):
        img_id = ann["image_id"]
        ann_by_img.setdefault(img_id, []).append(ann)
    
    # Mapeo de categorías
    if class_map is None:
        class_map = {cat["id"]: i for i, cat in enumerate(coco.get("categories", []))}
    
    count = 0
    for img_id, img_info in img_map.items():
        w_img = img_info["width"]
        h_img = img_info["height"]
        filename = Path(img_info["file_name"]).stem
        
        anns = ann_by_img.get(img_id, [])
        if not anns:
            continue
        
        lines = []
        for ann in anns:
            cat_id = ann["category_id"]
            yolo_cls = class_map.get(cat_id)
            if yolo_cls is None:
                continue
            
            # COCO bbox: [x_min, y_min, width, height] (absoluto)
            bx, by, bw, bh = ann["bbox"]
            
            x_center = (bx + bw / 2) / w_img
            y_center = (by + bh / 2) / h_img
            w_norm = bw / w_img
            h_norm = bh / h_img
            
            bbox = BBox(yolo_cls, x_center, y_center, w_norm, h_norm)
            lines.append(bbox.to_yolo_line())
        
        if lines:
            txt_path = output_dir / f"{filename}.txt"
            txt_path.write_text("\n".join(lines) + "\n")
            count += 1
    
    console.print(f"  [green]COCO → YOLO: {count} archivos de anotación creados[/]")
    return count


# ─────────────────────────────────────────────────────
# Pascal VOC (XML) → YOLO
# ─────────────────────────────────────────────────────

def voc_to_yolo(xml_dir: Path, output_dir: Path,
                class_names: list[str]):
    """
    Convierte anotaciones Pascal VOC (XML) a YOLO.
    
    Args:
        xml_dir: Directorio con los XMLs
        output_dir: Directorio salida .txt
        class_names: Lista ordenada de nombres de clase
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    class_to_id = {name: i for i, name in enumerate(class_names)}
    count = 0
    
    for xml_file in sorted(xml_dir.glob("*.xml")):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        size = root.find("size")
        w_img = int(size.find("width").text)
        h_img = int(size.find("height").text)
        
        lines = []
        for obj in root.findall("object"):
            cls_name = obj.find("name").text.strip().lower()
            cls_id = class_to_id.get(cls_name)
            if cls_id is None:
                continue
            
            bndbox = obj.find("bndbox")
            xmin = float(bndbox.find("xmin").text)
            ymin = float(bndbox.find("ymin").text)
            xmax = float(bndbox.find("xmax").text)
            ymax = float(bndbox.find("ymax").text)
            
            x_center = ((xmin + xmax) / 2) / w_img
            y_center = ((ymin + ymax) / 2) / h_img
            w_norm = (xmax - xmin) / w_img
            h_norm = (ymax - ymin) / h_img
            
            bbox = BBox(cls_id, x_center, y_center, w_norm, h_norm)
            lines.append(bbox.to_yolo_line())
        
        if lines:
            txt_path = output_dir / f"{xml_file.stem}.txt"
            txt_path.write_text("\n".join(lines) + "\n")
            count += 1
    
    console.print(f"  [green]VOC → YOLO: {count} archivos de anotación creados[/]")
    return count


# ─────────────────────────────────────────────────────
# Folder classification → YOLO cls format
# ─────────────────────────────────────────────────────

def folder_to_yolo_cls(src_dir: Path, output_dir: Path,
                       class_names: Optional[list[str]] = None):
    """
    Convierte estructura de carpetas (folder_class) a formato YOLO classification.
    
    Estructura entrada:
        src_dir/class_a/img001.jpg
        src_dir/class_b/img002.jpg
    
    Estructura salida:
        output_dir/class_a/img001.jpg
        output_dir/class_b/img002.jpg
    (YOLO cls usa la misma estructura, así que básicamente es un symlink/copy)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Detectar clases si no se proporcionan
    if class_names is None:
        class_names = sorted([
            d.name for d in src_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])
    
    total = 0
    for cls_name in class_names:
        cls_src = src_dir / cls_name
        cls_dst = output_dir / cls_name
        
        if not cls_src.exists():
            console.print(f"  [yellow]⚠ Clase '{cls_name}' no encontrada[/]")
            continue
        
        cls_dst.mkdir(parents=True, exist_ok=True)
        
        imgs = list(cls_src.glob("*.[jJ][pP][gG]")) + \
               list(cls_src.glob("*.[pP][nN][gG]")) + \
               list(cls_src.glob("*.[jJ][pP][eE][gG]"))
        
        for img in imgs:
            dst = cls_dst / img.name
            if not dst.exists():
                # Symlink para ahorrar espacio
                dst.symlink_to(img.resolve())
            total += 1
    
    console.print(f"  [green]Folder → YOLO cls: {total} imágenes, {len(class_names)} clases[/]")
    return total


# ─────────────────────────────────────────────────────
# CSV regression → YOLO (labels + metadata)
# ─────────────────────────────────────────────────────

def csv_regression_to_metadata(csv_path: Path, output_dir: Path,
                                img_col: str = "image",
                                value_col: str = "weight"):
    """
    Para datasets de estimación de peso:
    Crea un JSON de metadatos por imagen con valor de regresión.
    
    Args:
        csv_path: CSV con columnas imagen y valor
        output_dir: Directorio salida
        img_col: Nombre columna imagen
        value_col: Nombre columna valor (peso, BCS, etc.)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    count = 0
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            img_name = Path(row[img_col]).stem
            value = float(row[value_col])
            
            meta = {
                "image": row[img_col],
                "value": value,
                "task": "regression",
            }
            
            meta_path = output_dir / f"{img_name}.json"
            meta_path.write_text(json.dumps(meta, indent=2))
            count += 1
    
    console.print(f"  [green]CSV → metadata: {count} archivos JSON creados[/]")
    return count


# ─────────────────────────────────────────────────────
# Verificar / validar anotaciones YOLO
# ─────────────────────────────────────────────────────

def validate_yolo_labels(labels_dir: Path, images_dir: Path,
                          num_classes: int) -> dict:
    """
    Valida que las anotaciones YOLO sean correctas:
    - Cada imagen debe tener un .txt correspondiente
    - Valores normalizados entre 0 y 1
    - class_id dentro del rango
    """
    stats = {
        "total_images": 0,
        "with_labels": 0,
        "without_labels": 0,
        "invalid_labels": 0,
        "class_distribution": {},
        "errors": [],
    }
    
    img_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = [
        f for f in images_dir.iterdir()
        if f.suffix.lower() in img_extensions
    ]
    stats["total_images"] = len(images)
    
    for img in images:
        label_path = labels_dir / f"{img.stem}.txt"
        
        if not label_path.exists():
            stats["without_labels"] += 1
            continue
        
        stats["with_labels"] += 1
        
        for line_num, line in enumerate(label_path.read_text().strip().split("\n"), 1):
            if not line.strip():
                continue
            
            parts = line.strip().split()
            if len(parts) < 5:
                stats["invalid_labels"] += 1
                stats["errors"].append(f"{label_path.name}:{line_num} — campos insuficientes")
                continue
            
            try:
                cls_id = int(parts[0])
                x, y, w, h = [float(p) for p in parts[1:5]]
                
                if cls_id < 0 or cls_id >= num_classes:
                    stats["errors"].append(f"{label_path.name}:{line_num} — class_id {cls_id} fuera de rango")
                    stats["invalid_labels"] += 1
                
                for val, name in [(x, "x"), (y, "y"), (w, "w"), (h, "h")]:
                    if val < 0 or val > 1:
                        stats["errors"].append(f"{label_path.name}:{line_num} — {name}={val} fuera de [0,1]")
                        stats["invalid_labels"] += 1
                
                stats["class_distribution"][cls_id] = stats["class_distribution"].get(cls_id, 0) + 1
                
            except ValueError:
                stats["invalid_labels"] += 1
                stats["errors"].append(f"{label_path.name}:{line_num} — parse error")
    
    # Summary
    console.print(f"\n[bold]Validación YOLO:[/]")
    console.print(f"  Imágenes: {stats['total_images']}")
    console.print(f"  Con labels: {stats['with_labels']}")
    console.print(f"  Sin labels: {stats['without_labels']}")
    console.print(f"  Labels inválidos: {stats['invalid_labels']}")
    
    if stats["class_distribution"]:
        console.print(f"  Distribución clases: {stats['class_distribution']}")
    
    if stats["errors"][:5]:
        console.print(f"  [red]Primeros errores:[/]")
        for err in stats["errors"][:5]:
            console.print(f"    - {err}")
    
    return stats
