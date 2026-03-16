"""
Seedy Vision — Configuración global del pipeline
"""
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import yaml


# ── Paths ────────────────────────────────────────────
VISION_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = VISION_ROOT.parent
DATASETS_DIR = VISION_ROOT / "datasets"
CONFIGS_DIR = VISION_ROOT / "configs"
MODELS_DIR = VISION_ROOT / "models"
SCRIPTS_DIR = VISION_ROOT / "scripts"

# NAS backup target (configurable)
NAS_DATASETS = Path("/mnt/nas/seedy-datasets")


@dataclass
class DatasetEntry:
    """Un dataset del catálogo"""
    name: str
    url: str
    source: str   # kaggle | roboflow | zenodo | github
    species: str   # chicken | pig | cattle | multi
    task: str      # detection | classification | segmentation | pose | ...
    annotation_format: str
    images: int = 0
    audio_samples: int = 0
    license: str = ""
    priority: str = "medium"
    notes: str = ""
    # Source-specific IDs
    kaggle_id: Optional[str] = None
    roboflow_id: Optional[str] = None
    zenodo_id: Optional[str] = None


@dataclass
class YOLOConfig:
    """Configuración de entrenamiento YOLO"""
    model_size: str = "yolov8m"          # nano/small/medium/large/xlarge
    imgsz: int = 640
    epochs: int = 100
    batch: int = 16
    patience: int = 20
    lr0: float = 0.01
    lrf: float = 0.01
    augment: bool = True
    mosaic: float = 1.0
    mixup: float = 0.15
    copy_paste: float = 0.1
    device: str = "0"                     # GPU 0 (RTX 5080)
    workers: int = 8
    project: str = str(MODELS_DIR)
    exist_ok: bool = True


# ── Mapas de clases unificadas ───────────────────────

# Detección: clases unificadas para las 3 especies
DETECTION_CLASSES = {
    0: "chicken",
    1: "pig",
    2: "cattle",
    3: "chick",       # pollito
    4: "piglet",      # lechón
    5: "calf",        # ternero
}

# Razas (clasificación multi-label)
BREED_CLASSES = {
    # Gallinas / Capones
    "chicken": [
        "castellana_negra", "pita_pinta", "extremena_azul",
        "euskal_oiloa", "andaluza_azul", "empordanesa",
        "cornish", "brahma", "cochinchina", "orpington",
        "sussex", "faverolles", "marans", "plymouth_rock",
        "rhode_island", "leghorn", "castellana_blanca",
    ],
    # Porcino
    "pig": [
        "iberico", "iberico_retinto", "iberico_entrepelado",
        "duroc", "landrace", "large_white", "pietrain",
        "hampshire", "berkshire", "mangalica",
    ],
    # Vacuno
    "cattle": [
        "angus", "hereford", "charolais", "limousin",
        "simmental", "rubia_gallega", "retinta",
        "avileña_negra", "morucha", "pirenaica",
        "asturiana_valles", "asturiana_montaña",
        "blonde_aquitaine", "wagyu", "brahman",
    ],
}

# Comportamiento (clasificación temporal)
BEHAVIOUR_CLASSES = [
    "eating", "drinking", "resting", "walking",
    "running", "fighting", "mounting", "abnormal_grouping",
    "stereotypy", "panting",   # jadeo / estrés calórico
]

# Sanitario (detección de lesiones / enfermedades)
HEALTH_CLASSES = [
    "lameness", "wound", "skin_lesion", "tail_bite",
    "ear_necrosis", "hernia", "prolapse",
    "respiratory_distress", "diarrhea",
]

# Condición corporal (clasificación ordinal)
BCS_CLASSES = ["bcs_1", "bcs_2", "bcs_3", "bcs_4", "bcs_5"]


def load_catalog() -> list[DatasetEntry]:
    """Carga el catálogo de datasets desde YAML"""
    catalog_path = CONFIGS_DIR / "dataset_catalog.yaml"
    with open(catalog_path, "r") as f:
        data = yaml.safe_load(f)
    
    entries = []
    for item in data.get("datasets", []):
        entries.append(DatasetEntry(**{
            k: v for k, v in item.items()
            if k in DatasetEntry.__dataclass_fields__
        }))
    return entries


def get_datasets_by_species(species: str) -> list[DatasetEntry]:
    """Filtra datasets por especie"""
    return [d for d in load_catalog() if d.species == species]


def get_datasets_by_priority(priority: str = "high") -> list[DatasetEntry]:
    """Filtra datasets por prioridad"""
    return [d for d in load_catalog() if d.priority == priority]
