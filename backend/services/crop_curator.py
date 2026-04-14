"""
Seedy Backend — Curación dual de datos de visión

Track A: Crops individuales → data/curated_crops/{raza}/
  Para mantener/mejorar breed como clasificador.

Track B: Frames completos anotados → data/curated_frames/
  Para entrenar un detector YOLO real de gallinas que reemplace COCO.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Directorios
CURATED_CROPS_DIR = Path(os.getenv("CURATED_CROPS_DIR", "data/curated_crops"))
CURATED_FRAMES_DIR = Path(os.getenv("CURATED_FRAMES_DIR", "data/curated_frames"))
METADATA_FILE = CURATED_CROPS_DIR / "_metadata.jsonl"
STATS_FILE = CURATED_CROPS_DIR / "_stats.json"

# ══════════════════════════════════════════════════════
#  Track A: Curación de CROPS para clasificación
# ══════════════════════════════════════════════════════

CURATION_MIN_CONF_YOLO = 0.65
CURATION_MIN_CONF_GEMINI = 0.80
CURATION_MIN_CROP_SIZE = 128     # pixels mínimo por lado
CURATION_MIN_SHARPNESS = 40
CURATION_MAX_PER_CLASS_DAY = 50

# ══════════════════════════════════════════════════════
#  Track B: Curación de FRAMES ANOTADOS para detección
# ══════════════════════════════════════════════════════

FRAME_MIN_BIRDS = 1              # Mín 1 ave para guardar frame (antes 3, pero con COCO detectamos 0-2)
FRAME_MAX_PER_CAMERA_DAY = 500   # Subido — queremos acumular 500 frames rápido (3 cámaras × ~170)
FRAME_MIN_INTERVAL = 10          # 10s entre frames por cámara — suficiente variedad de poses

# Clases para el dataset de detección YOLO
DETECTION_CLASSES = [
    "gallina",      # 0 — ave genérica (si breed no clasifica)
    "bresse",       # 1
    "sussex",       # 2
    "vorwerk",      # 3
    "marans",       # 4
    "sulmtaler",    # 5
    "araucana",     # 6
    "orpington",    # 7
    "castellana",   # 8
    "pita_pinta",   # 9
    "andaluza",     # 10
    "f1_cruce",     # 11
    "ameraucana",   # 12
    "gallo",        # 13
    "gorrion",      # 14
    "paloma",       # 15
    "rata",         # 16
    "depredador",   # 17
]

# Mapeo breed → clase de detección
_BREED_TO_CLASS = {
    "bresse": 1, "sussex": 2, "vorwerk": 3, "marans": 4,
    "sulmtaler": 5, "araucana": 6, "orpington": 7,
    "castellana": 8, "pita_pinta": 9, "andaluza": 10,
    "andaluza_azul": 10, "f1_(cruce)": 11, "f1_cruce": 11,
    "ameraucana": 12, "gallo": 13,
    "gorrion": 14, "paloma": 15, "rata": 16, "depredador": 17,
}


@dataclass
class CuratedCrop:
    filepath: str
    breed: str
    color: str
    sex: str
    confidence: float
    engine: str
    camera_id: str
    bird_id: Optional[str]
    timestamp: str
    crop_size: tuple
    sharpness: float
    quality_score: float
    trigger_event: str


@dataclass
class CuratedFrame:
    image_path: str
    label_path: str
    camera_id: str
    timestamp: str
    bird_count: int
    trigger_event: str


class CropCurator:
    """Curación dual: crops para clasificación + frames para detección."""

    def __init__(self):
        CURATED_CROPS_DIR.mkdir(parents=True, exist_ok=True)
        (CURATED_CROPS_DIR / "_rejected").mkdir(exist_ok=True)
        CURATED_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        (CURATED_FRAMES_DIR / "images").mkdir(exist_ok=True)
        (CURATED_FRAMES_DIR / "labels").mkdir(exist_ok=True)
        self._write_classes_file()

        self._daily_crop_counts: Dict[str, int] = {}
        self._daily_frame_counts: Dict[str, int] = {}
        self._last_frame_save: Dict[str, float] = {}

    # ══════════════════════════════════════════════════
    #  Track A: Crops individuales (clasificación)
    # ══════════════════════════════════════════════════

    async def curate_crop(
        self,
        crop: np.ndarray,
        identification: dict,
        camera_id: str,
        trigger_event: str = "loop",
    ) -> Optional[CuratedCrop]:
        """Evalúa y guarda un crop individual si pasa los filtros de calidad."""
        breed = identification.get("breed", "unknown")
        confidence = identification.get("confidence", identification.get("breed_conf", 0))
        engine = identification.get("engine", "yolo_breed")

        if breed in ("unknown", "Desconocida", "sin_clasificar", None, ""):
            return None

        h, w = crop.shape[:2]
        if min(h, w) < CURATION_MIN_CROP_SIZE:
            return None

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        if sharpness < CURATION_MIN_SHARPNESS:
            return None

        # Threshold según motor
        if "gemini" in str(engine).lower():
            if confidence < CURATION_MIN_CONF_GEMINI:
                return None
        else:
            if confidence < CURATION_MIN_CONF_YOLO:
                return None

        # Límite diario por clase
        today = datetime.now().strftime("%Y-%m-%d")
        day_key = f"{breed}_{today}"
        if self._daily_crop_counts.get(day_key, 0) >= CURATION_MAX_PER_CLASS_DAY:
            return None

        color = identification.get("color", "variado")
        sex = identification.get("sex", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        quality = self._compute_crop_quality(crop, confidence, sharpness)

        breed_clean = breed.lower().replace(" ", "_")
        breed_dir = CURATED_CROPS_DIR / breed_clean
        breed_dir.mkdir(exist_ok=True)

        filename = f"{breed_clean}_{color}_{sex}_{timestamp}_{camera_id}_{confidence:.2f}.jpg"
        filepath = breed_dir / filename
        cv2.imwrite(str(filepath), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

        entry = CuratedCrop(
            filepath=str(filepath), breed=breed, color=color, sex=sex,
            confidence=confidence, engine=engine, camera_id=camera_id,
            bird_id=identification.get("bird_id"),
            timestamp=timestamp, crop_size=(w, h),
            sharpness=round(sharpness, 1), quality_score=round(quality, 3),
            trigger_event=trigger_event,
        )

        # Append a metadata
        with open(METADATA_FILE, "a") as f:
            f.write(json.dumps(entry.__dict__, ensure_ascii=False) + "\n")

        self._daily_crop_counts[day_key] = self._daily_crop_counts.get(day_key, 0) + 1
        self._update_stats()
        logger.info(f"📸 Crop curado: {breed} conf={confidence:.0%} → {filepath.name}")
        return entry

    # ══════════════════════════════════════════════════
    #  Track B: Frames anotados (detección)
    # ══════════════════════════════════════════════════

    async def curate_frame(
        self,
        frame: np.ndarray,
        detections: List[dict],
        camera_id: str,
        trigger_event: str = "loop",
    ) -> Optional[CuratedFrame]:
        """Guarda un frame completo con bboxes en formato YOLO para entrenamiento."""
        bird_dets = [d for d in detections if not d.get("is_pest")]
        if len(bird_dets) < FRAME_MIN_BIRDS:
            return None

        now = time.time()
        today = datetime.now().strftime("%Y-%m-%d")
        day_key = f"{camera_id}_{today}"

        if self._daily_frame_counts.get(day_key, 0) >= FRAME_MAX_PER_CAMERA_DAY:
            return None

        last = self._last_frame_save.get(camera_id, 0)
        if now - last < FRAME_MIN_INTERVAL:
            return None

        h, w = frame.shape[:2]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{camera_id}_{timestamp}"

        # Guardar imagen
        img_path = CURATED_FRAMES_DIR / "images" / f"{base_name}.jpg"
        cv2.imwrite(str(img_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Labels YOLO format: class x_center y_center width height (normalizado)
        label_lines = []
        saved_count = 0
        for det in detections:
            class_id = self._breed_to_detection_class(det)
            if class_id is None:
                continue

            x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
            x_center = ((x1 + x2) / 2) / w
            y_center = ((y1 + y2) / 2) / h
            bbox_w = (x2 - x1) / w
            bbox_h = (y2 - y1) / h

            if not (0 <= x_center <= 1 and 0 <= y_center <= 1):
                continue
            if bbox_w <= 0 or bbox_h <= 0:
                continue

            label_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {bbox_w:.6f} {bbox_h:.6f}")
            saved_count += 1

        if not label_lines:
            img_path.unlink(missing_ok=True)
            return None

        label_path = CURATED_FRAMES_DIR / "labels" / f"{base_name}.txt"
        label_path.write_text("\n".join(label_lines))

        self._daily_frame_counts[day_key] = self._daily_frame_counts.get(day_key, 0) + 1
        self._last_frame_save[camera_id] = now

        logger.info(f"🖼️ Frame curado: {camera_id} {saved_count} aves → {img_path.name}")

        self._update_stats()

        return CuratedFrame(
            image_path=str(img_path), label_path=str(label_path),
            camera_id=camera_id, timestamp=timestamp,
            bird_count=saved_count, trigger_event=trigger_event,
        )

    # ── Utilidades ──

    def _breed_to_detection_class(self, det: dict) -> Optional[int]:
        """Mapea breed/pest a clase de detección YOLO."""
        breed = (det.get("breed") or "").lower().replace(" ", "_")
        coco_class = det.get("coco_class", "")

        if breed in _BREED_TO_CLASS:
            return _BREED_TO_CLASS[breed]

        # Ave genérica (COCO detectó pero breed no clasificó)
        if coco_class in ("bird", "dog", "cat") and breed in ("sin_clasificar", "", "gallina"):
            return 0

        return None

    def _write_classes_file(self):
        classes_file = CURATED_FRAMES_DIR / "classes.txt"
        classes_file.write_text("\n".join(DETECTION_CLASSES))

    def _compute_crop_quality(self, crop: np.ndarray, confidence: float, sharpness: float) -> float:
        h, w = crop.shape[:2]
        size_score = min(1.0, (min(h, w) - 128) / 384)
        sharp_score = min(1.0, (sharpness - 40) / 160)
        conf_score = min(1.0, confidence)
        return 0.35 * conf_score + 0.35 * sharp_score + 0.30 * size_score

    def _update_stats(self):
        stats: Dict[str, int] = {}
        if METADATA_FILE.exists():
            with open(METADATA_FILE) as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            breed = entry.get("breed", "unknown")
                            stats[breed] = stats.get(breed, 0) + 1
                        except json.JSONDecodeError:
                            continue

        frame_count = len(list((CURATED_FRAMES_DIR / "images").glob("*.jpg")))

        with open(STATS_FILE, "w") as f:
            json.dump({
                "crops_total": sum(stats.values()),
                "crops_by_breed": dict(sorted(stats.items(), key=lambda x: -x[1])),
                "frames_annotated": frame_count,
                "updated": datetime.now().isoformat(),
            }, f, indent=2, ensure_ascii=False)

    def get_stats(self) -> dict:
        """Estadísticas actuales del dataset curado."""
        if STATS_FILE.exists():
            return json.loads(STATS_FILE.read_text())
        return {"crops_total": 0, "crops_by_breed": {}, "frames_annotated": 0}

    def get_dataset_gaps(self) -> dict:
        """Razas con pocos crops + progreso de frames para detección."""
        stats = self.get_stats()
        target_crops = 100
        crop_gaps = [
            {"breed": breed, "count": count, "needed": target_crops - count}
            for breed, count in stats.get("crops_by_breed", {}).items()
            if count < target_crops
        ]
        frames = stats.get("frames_annotated", 0)
        return {
            "crop_gaps": sorted(crop_gaps, key=lambda x: x["count"]),
            "frames_for_detection": frames,
            "frames_target": 500,
            "ready_to_train_detector": frames >= 500,
        }

    def browse_breed(self, breed: str, limit: int = 20) -> List[dict]:
        """Lista crops curados de una raza específica."""
        breed_dir = CURATED_CROPS_DIR / breed.lower().replace(" ", "_")
        if not breed_dir.exists():
            return []
        items = []
        for f in sorted(breed_dir.glob("*.jpg"), reverse=True)[:limit]:
            items.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "path": str(f),
            })
        return items


# ── Singleton ──
_curator_instance: Optional[CropCurator] = None


def get_curator() -> CropCurator:
    global _curator_instance
    if _curator_instance is None:
        _curator_instance = CropCurator()
    return _curator_instance
