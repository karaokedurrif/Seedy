"""
Seedy Backend — Servicio de detección YOLO

Motor de detección local con YOLOv8/v11 para monitorización avícola.

Modelos:
  1. Detección: localiza aves, gorriones, plagas en el frame
  2. Clasificación: identifica raza/tipo una vez recortado el bbox
  (3. Pose — futuro: estima postura corporal para salud/comportamiento)

Estrategia de desacoplamiento de Gemini:
  Fase 1 — COCO preentrenado (bird=14) + Gemini para raza
  Fase 2 — Modelo custom Seedy (gallina/gallo/gorrión/...) + Gemini reducido
  Fase 3 — Detección + Clasificación propios → Gemini solo puntualmente
"""

import io
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuración ──

YOLO_MODEL = os.environ.get("YOLO_MODEL", "yolov8s.pt")
YOLO_CONFIDENCE = float(os.environ.get("YOLO_CONFIDENCE", "0.25"))
YOLO_DEVICE = os.environ.get("YOLO_DEVICE", "0")
YOLO_CUSTOM_MODEL = os.environ.get("YOLO_CUSTOM_MODEL", "")
YOLO_DATA_DIR = Path(os.environ.get("YOLO_DATA_DIR", "/app/yolo_dataset"))

# ── Clases COCO relevantes ──
# Filtramos solo las que nos interesan del modelo COCO preentrenado
COCO_CLASSES_OF_INTEREST = {
    14: "bird",       # ave genérica (gallinas + gorriones + todo)
    15: "cat",        # depredador
    16: "dog",        # depredador / perro guardián
    21: "cow",        # vaca (puede colarse si hay pasto cerca)
}

# ── Taxonomía Seedy completa ──
# Estas son las clases objetivo del modelo custom
SEEDY_DETECTION_CLASSES = {
    # ── Aves de corral (nuestras) ──
    0: "gallina",          # hembra adulta genérica
    1: "gallo",            # macho adulto (cresta grande, cola larga, espolones)
    2: "pollito",          # cría < 8 semanas
    3: "pollo_juvenil",    # 8-20 semanas (todavía no adulto)
    # ── Razas específicas (fase 2+) ──
    4: "sussex",           # Sussex (blanco con collar negro)
    5: "bresse",           # Bresse (blancos, patas azules)
    6: "marans",           # Marans (negro cobrizo, huevos oscuros)
    7: "orpington",        # Orpington (leonado/dorado, grande)
    8: "araucana",         # Araucana (sin cola, huevos azules)
    9: "castellana",       # Castellana negra
    10: "pita_pinta",      # Pita Pinta asturiana
    # ── Plagas / intrusos ──
    11: "gorrion",         # Passer domesticus — ladrón de pienso
    12: "paloma",          # Columba livia
    13: "rata",            # Rattus / roedor
    14: "depredador",      # gato, rapaz, etc.
    # ── Infraestructura (para zonas) ──
    15: "comedero",        # tolva / comedero
    16: "bebedero",        # nipple / bebedero
    17: "nido",            # nidal / ponedero
    18: "aseladero",       # percha / barra
    19: "huevo",           # huevo visible en nido o suelo
}

# Inverso
SEEDY_CLASS_NAMES = {v: k for k, v in SEEDY_DETECTION_CLASSES.items()}

# Categorías para análisis
SEEDY_POULTRY_CLASSES = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10}  # aves nuestras
SEEDY_PEST_CLASSES = {11, 12, 13, 14}                          # intrusos
SEEDY_INFRA_CLASSES = {15, 16, 17, 18, 19}                     # infraestructura

# ── Modelo cargado (singleton) ──
_model = None
_model_name: str = ""
_model_type: str = ""  # "coco" | "custom"
_custom_classes: dict[int, str] = {}


def _load_model():
    """Carga el modelo YOLO. Intenta custom primero, luego COCO."""
    global _model, _model_name, _model_type, _custom_classes

    from ultralytics import YOLO

    if YOLO_CUSTOM_MODEL and Path(YOLO_CUSTOM_MODEL).exists():
        try:
            _model = YOLO(YOLO_CUSTOM_MODEL)
            _model_name = Path(YOLO_CUSTOM_MODEL).name
            _model_type = "custom"
            if hasattr(_model, "names"):
                _custom_classes = dict(_model.names)
            logger.info(
                f"🐔 YOLO custom model loaded: {_model_name} "
                f"({len(_custom_classes)} classes) on device={YOLO_DEVICE}"
            )
            return
        except Exception as e:
            logger.warning(f"Failed loading custom YOLO model: {e}")

    _model = YOLO(YOLO_MODEL)
    _model_name = YOLO_MODEL
    _model_type = "coco"
    logger.info(f"🐔 YOLO COCO model loaded: {_model_name} on device={YOLO_DEVICE}")


def get_model():
    if _model is None:
        _load_model()
    return _model


def detect(frame_bytes: bytes, confidence: float | None = None) -> dict:
    """
    Detección completa: aves, plagas, infraestructura.

    Returns:
        {
            "detections": [...],
            "poultry": [...],    # solo aves nuestras
            "pests": [...],      # intrusos (gorriones, ratas...)
            "infra": [...],      # comederos, nidos...
            "poultry_count": 5,
            "pest_count": 2,
            "model": "yolov8s.pt",
            "model_type": "coco" | "custom",
            "inference_ms": 23.4,
            "frame_width": 3840,
            "frame_height": 2160,
        }
    """
    import numpy as np
    from PIL import Image

    model = get_model()
    conf = confidence or YOLO_CONFIDENCE
    t0 = time.time()

    img = Image.open(io.BytesIO(frame_bytes))
    W, H = img.size

    results = model.predict(
        source=np.array(img),
        conf=conf,
        device=YOLO_DEVICE,
        verbose=False,
    )

    elapsed_ms = (time.time() - t0) * 1000

    detections = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_conf = float(box.conf[0])

            # Filtrar clases según tipo de modelo
            if _model_type == "coco":
                if cls_id not in COCO_CLASSES_OF_INTEREST:
                    continue
                class_name = COCO_CLASSES_OF_INTEREST[cls_id]
                # Reclasificar para coherencia interna
                category = "poultry" if cls_id == 14 else "pest"
            else:
                class_name = _custom_classes.get(cls_id, f"class_{cls_id}")
                if cls_id in SEEDY_POULTRY_CLASSES:
                    category = "poultry"
                elif cls_id in SEEDY_PEST_CLASSES:
                    category = "pest"
                elif cls_id in SEEDY_INFRA_CLASSES:
                    category = "infra"
                else:
                    category = "other"

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x1n, y1n = x1 / W, y1 / H
            x2n, y2n = x2 / W, y2 / H

            det = {
                "class_name": class_name,
                "class_id": cls_id,
                "confidence": round(cls_conf, 3),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "bbox_norm": [round(x1n, 4), round(y1n, 4), round(x2n, 4), round(y2n, 4)],
                "category": category,
                "area_norm": round((x2n - x1n) * (y2n - y1n), 6),
            }
            detections.append(det)

    # Separar por categoría
    poultry = [d for d in detections if d["category"] == "poultry"]
    pests = [d for d in detections if d["category"] == "pest"]
    infra = [d for d in detections if d["category"] == "infra"]

    return {
        "detections": detections,
        "poultry": poultry,
        "pests": pests,
        "infra": infra,
        "poultry_count": len(poultry),
        "pest_count": len(pests),
        "model": _model_name,
        "model_type": _model_type,
        "inference_ms": round(elapsed_ms, 1),
        "frame_width": W,
        "frame_height": H,
    }


# Alias retrocompatible
def detect_birds(frame_bytes: bytes, confidence: float | None = None) -> dict:
    """Alias retrocompatible: devuelve detect() con 'count' = poultry_count."""
    result = detect(frame_bytes, confidence)
    result["count"] = result["poultry_count"]
    return result


def crop_detections(frame_bytes: bytes, detections: list[dict]) -> list[bytes]:
    """Recorta cada detección del frame original. Útil para clasificación."""
    from PIL import Image

    img = Image.open(io.BytesIO(frame_bytes))
    W, H = img.size
    crops = []

    for det in detections:
        bbox = det.get("bbox", [])
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        # Margen 10% para contexto
        margin_x = int((x2 - x1) * 0.1)
        margin_y = int((y2 - y1) * 0.1)
        x1 = max(0, x1 - margin_x)
        y1 = max(0, y1 - margin_y)
        x2 = min(W, x2 + margin_x)
        y2 = min(H, y2 + margin_y)

        crop = img.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=85)
        crops.append(buf.getvalue())

    return crops


def estimate_body_size(detection: dict, frame_height_px: int) -> dict:
    """
    Estima tamaño corporal relativo a partir del bbox.

    Útil para:
      - Tracking de crecimiento de pollitos
      - Estimación burda de peso (calibración futura con pesos reales)
      - Distinguir adultos de juveniles

    Returns: {"height_px", "width_px", "area_px", "area_ratio", "size_category"}
    """
    bbox = detection.get("bbox", [])
    if len(bbox) != 4:
        return {}

    x1, y1, x2, y2 = bbox
    w_px = x2 - x1
    h_px = y2 - y1
    area_px = w_px * h_px
    area_ratio = detection.get("area_norm", 0)

    # Categorías de tamaño por ratio de área
    if area_ratio < 0.005:
        size_cat = "pollito"
    elif area_ratio < 0.015:
        size_cat = "juvenil"
    elif area_ratio < 0.04:
        size_cat = "adulto_normal"
    else:
        size_cat = "adulto_grande"

    return {
        "height_px": round(h_px),
        "width_px": round(w_px),
        "area_px": round(area_px),
        "area_ratio": round(area_ratio, 6),
        "size_category": size_cat,
        "aspect_ratio": round(w_px / max(h_px, 1), 2),
    }


def analyze_distribution(detections: list[dict]) -> dict:
    """
    Analiza cómo están distribuidas las aves en el frame.

    Detecta:
      - Amontonamiento (posible estrés, frío)
      - Distribución uniforme (normal)
      - Clustering en una zona (posible problema)
    """
    if not detections:
        return {"pattern": "vacío", "detail": "No hay aves detectadas"}

    from collections import Counter

    # Centros de cada detección
    centers = []
    zones = []
    for d in detections:
        bn = d.get("bbox_norm", [])
        if len(bn) != 4:
            continue
        cx = (bn[0] + bn[2]) / 2
        cy = (bn[1] + bn[3]) / 2
        centers.append((cx, cy))

        # Zona 3×3
        zx = int(cx * 3)
        zy = int(cy * 3)
        zx = min(zx, 2)
        zy = min(zy, 2)
        zones.append(f"{zy},{zx}")

    if not centers:
        return {"pattern": "vacío", "detail": "Sin coordenadas válidas"}

    zone_counts = Counter(zones)
    n_zones_occupied = len(zone_counts)
    max_in_zone = max(zone_counts.values())
    total = len(centers)

    # Detectar amontonamiento: >60% en una sola zona
    if total >= 3 and max_in_zone / total > 0.6:
        crowded_zone = zone_counts.most_common(1)[0][0]
        zy, zx = crowded_zone.split(",")
        zone_names = {
            "0,0": "arriba-izquierda", "0,1": "arriba-centro", "0,2": "arriba-derecha",
            "1,0": "centro-izquierda", "1,1": "centro", "1,2": "centro-derecha",
            "2,0": "abajo-izquierda", "2,1": "abajo-centro", "2,2": "abajo-derecha",
        }
        zone_label = zone_names.get(crowded_zone, crowded_zone)
        return {
            "pattern": "amontonadas",
            "detail": f"{max_in_zone}/{total} aves concentradas en zona {zone_label}",
            "zones_occupied": n_zones_occupied,
            "max_density_zone": zone_label,
            "concentration_ratio": round(max_in_zone / total, 2),
            "alert": True,
        }

    # Distribución normal
    if n_zones_occupied >= min(4, total):
        pattern = "distribuidas"
    else:
        pattern = "agrupadas"

    return {
        "pattern": pattern,
        "detail": f"{total} aves en {n_zones_occupied} zonas",
        "zones_occupied": n_zones_occupied,
        "concentration_ratio": round(max_in_zone / total, 2),
        "alert": False,
    }


def describe_situation(frame_bytes: bytes) -> str:
    """
    Genera descripción textual del estado del gallinero con YOLO local.
    Incluye: conteo, plagas, distribución, tamaños.
    """
    result = detect(frame_bytes)
    ms = result["inference_ms"]
    poultry_n = result["poultry_count"]
    pest_n = result["pest_count"]

    parts = []

    if poultry_n == 0 and pest_n == 0:
        return (
            f"No se detectan aves ni intrusos en el frame "
            f"(YOLO {result['model']}, {ms:.0f}ms). "
            f"Puede ser de noche o el gallinero estar vacío."
        )

    # Aves
    if poultry_n > 0:
        confs = [d["confidence"] for d in result["poultry"]]
        avg_conf = sum(confs) / len(confs)
        dist = analyze_distribution(result["poultry"])
        parts.append(
            f"Se detectan {poultry_n} aves ({dist['pattern']}, "
            f"confianza media {avg_conf:.0%})."
        )
        if dist.get("alert"):
            parts.append(f"⚠️ {dist['detail']}.")

        # Tamaños
        sizes = [estimate_body_size(d, result["frame_height"])
                 for d in result["poultry"]]
        size_cats = [s.get("size_category", "") for s in sizes if s]
        if size_cats:
            from collections import Counter
            sc = Counter(size_cats)
            size_desc = ", ".join(f"{v} {k}" for k, v in sc.most_common())
            parts.append(f"Tamaños: {size_desc}.")

    # Plagas
    if pest_n > 0:
        pest_names = [d["class_name"] for d in result["pests"]]
        from collections import Counter
        pc = Counter(pest_names)
        pest_desc = ", ".join(f"{v} {k}" for k, v in pc.most_common())
        parts.append(f"🚨 Intrusos detectados: {pest_desc}.")

    parts.append(f"(YOLO {result['model']}, {ms:.0f}ms)")
    return " ".join(parts)


def draw_detections(
    frame_bytes: bytes,
    detections: list[dict],
    gallinero_label: str = "",
) -> bytes:
    """Dibuja bboxes anotados estilo Roboflow con colores por categoría."""
    from PIL import Image, ImageDraw, ImageFont

    # Colores por categoría
    COLOR_POULTRY = [
        (76, 255, 76), (76, 175, 255), (255, 200, 50),
        (200, 76, 255), (50, 255, 200), (150, 255, 50),
    ]
    COLOR_PEST = (255, 50, 50)     # rojo
    COLOR_INFRA = (100, 100, 255)  # azul suave

    img = Image.open(io.BytesIO(frame_bytes))
    draw = ImageDraw.Draw(img)
    W, H = img.size

    font_size = max(16, min(W, H) // 40)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", font_size
        )
    except Exception:
        font = ImageFont.load_default()

    line_w = max(2, min(W, H) // 300)
    poultry_idx = 0

    for det in detections:
        bbox = det.get("bbox", [])
        if not bbox or len(bbox) != 4:
            continue

        x1, y1, x2, y2 = [int(v) for v in bbox]
        conf = det.get("confidence", 0)
        cls = det.get("class_name", "?")
        cat = det.get("category", "poultry")

        if cat == "pest":
            color = COLOR_PEST
        elif cat == "infra":
            color = COLOR_INFRA
        else:
            color = COLOR_POULTRY[poultry_idx % len(COLOR_POULTRY)]
            poultry_idx += 1

        # Rectángulo (línea doble para plagas)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_w)
        if cat == "pest":
            draw.rectangle(
                [x1 - 2, y1 - 2, x2 + 2, y2 + 2],
                outline=COLOR_PEST, width=line_w,
            )

        # Etiqueta
        icon = "🐦" if cat == "pest" else ("🔧" if cat == "infra" else "")
        label = f"{icon}{cls} {conf:.0%}"
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0] + 10, tb[3] - tb[1] + 6
        ly = max(0, y1 - th - 2)
        draw.rectangle([x1, ly, x1 + tw, ly + th], fill=color)
        draw.text((x1 + 5, ly + 2), label, fill=(255, 255, 255), font=font)

    # Resumen
    poultry_n = sum(1 for d in detections if d.get("category") == "poultry")
    pest_n = sum(1 for d in detections if d.get("category") == "pest")
    wm = f"Seedy YOLO · {gallinero_label} · {poultry_n} aves"
    if pest_n:
        wm += f" · {pest_n} intrusos!"
    draw.text((10, H - font_size - 8), wm, fill=(200, 200, 200), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


# ── Dataset / Training helpers ──

def save_training_frame(
    frame_bytes: bytes,
    detections: list[dict],
    class_map: dict[str, int] | None = None,
    split: str = "train",
) -> Optional[str]:
    """Guarda frame + etiquetas YOLO para entrenamiento."""
    if not detections:
        return None
    if class_map is None:
        class_map = {v: k for k, v in SEEDY_DETECTION_CLASSES.items()}

    images_dir = YOLO_DATA_DIR / "images" / split
    labels_dir = YOLO_DATA_DIR / "labels" / split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    existing = list(images_dir.glob("*.jpg"))
    seq = len(existing) + 1
    stem = f"frame_{seq:06d}"

    img_path = images_dir / f"{stem}.jpg"
    img_path.write_bytes(frame_bytes)

    lines = []
    for det in detections:
        cls_name = det.get("class_name", "gallina")
        cls_id = class_map.get(cls_name, 0)
        bn = det.get("bbox_norm", [])
        if len(bn) != 4:
            continue
        x1, y1, x2, y2 = bn
        lines.append(
            f"{cls_id} {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} "
            f"{x2-x1:.6f} {y2-y1:.6f}"
        )

    label_path = labels_dir / f"{stem}.txt"
    label_path.write_text("\n".join(lines))
    return str(img_path)


def get_dataset_stats() -> dict:
    stats = {"train_images": 0, "val_images": 0, "train_labels": 0, "val_labels": 0}
    for split in ("train", "val"):
        img_dir = YOLO_DATA_DIR / "images" / split
        lbl_dir = YOLO_DATA_DIR / "labels" / split
        if img_dir.exists():
            stats[f"{split}_images"] = len(list(img_dir.glob("*.jpg")))
        if lbl_dir.exists():
            stats[f"{split}_labels"] = len(list(lbl_dir.glob("*.txt")))
    stats["dataset_yaml"] = (YOLO_DATA_DIR / "dataset.yaml").exists()
    stats["custom_model"] = YOLO_CUSTOM_MODEL if YOLO_CUSTOM_MODEL else None
    stats["active_model"] = _model_name or YOLO_MODEL
    stats["model_type"] = _model_type or "not_loaded"
    return stats


def get_model_info() -> dict:
    model = get_model()
    return {
        "model_name": _model_name,
        "model_type": _model_type,
        "device": YOLO_DEVICE,
        "confidence_threshold": YOLO_CONFIDENCE,
        "custom_classes": _custom_classes if _model_type == "custom" else COCO_CLASSES_OF_INTEREST,
        "seedy_taxonomy": SEEDY_DETECTION_CLASSES,
    }


def reload_model():
    global _model, _model_name, _model_type
    _model = None
    _model_name = ""
    _model_type = ""
    _load_model()
