"""Seedy Backend — Curación automática de crops para dataset de entrenamiento.

Cada vez que el pipeline identifica un ave con alta confianza, el crop
se guarda como dato de entrenamiento etiquetado en data/curated_crops/.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CURATED_DIR = Path("data/curated_crops")
METADATA_FILE = CURATED_DIR / "_metadata.jsonl"
STATS_FILE = CURATED_DIR / "_stats.json"

# ── Umbrales de curación ──
CURATION_MIN_CONF_YOLO = 0.65
CURATION_MIN_CONF_GEMINI = 0.80
CURATION_MIN_CROP_SIZE = 128       # px mínimo (ancho o alto)
CURATION_MIN_SHARPNESS = 40.0      # Varianza Laplaciana
CURATION_MAX_PER_CLASS_DAY = 50    # Evitar desbalance


class CropCurator:
    """Evalúa y guarda crops de alta calidad como training data."""

    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or CURATED_DIR
        self._base.mkdir(parents=True, exist_ok=True)
        (self._base / "_rejected").mkdir(exist_ok=True)
        self._daily_counts: dict[str, int] = {}

    async def evaluate_and_save(
        self,
        frame_bytes: bytes,
        bird_result: dict,
        camera_id: str,
        gallinero_id: str,
        trigger_event: str = "unknown",
    ) -> Optional[dict]:
        """Evalúa si un crop merece ser curado y lo guarda.

        Args:
            frame_bytes: Frame JPEG completo (main-stream).
            bird_result: Dict con breed, color, sex, confidence, bbox, engine.
            camera_id: ID de la cámara.
            gallinero_id: ID del gallinero.
            trigger_event: Evento que disparó la captura.

        Returns:
            dict con metadatos si se curó, None si rechazado.
        """
        breed = bird_result.get("breed", "unknown")
        confidence = bird_result.get("confidence", 0)
        engine = bird_result.get("engine", "unknown")

        if breed in ("unknown", "Desconocida", ""):
            return None

        # Confidence threshold según engine
        if engine.startswith("yolo_breed") and confidence < CURATION_MIN_CONF_YOLO:
            return None
        if engine == "gemini" and confidence < CURATION_MIN_CONF_GEMINI:
            return None

        # Daily cap
        today = datetime.now().strftime("%Y-%m-%d")
        day_key = f"{breed}_{today}"
        if self._daily_counts.get(day_key, 0) >= CURATION_MAX_PER_CLASS_DAY:
            return None

        # Crop del frame
        bbox = bird_result.get("bbox") or bird_result.get("bbox_norm")
        if not bbox or len(bbox) != 4:
            return None

        crop = self._extract_crop(frame_bytes, bbox)
        if crop is None:
            return None

        h, w = crop.shape[:2]
        if min(h, w) < CURATION_MIN_CROP_SIZE:
            return None

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if sharpness < CURATION_MIN_SHARPNESS:
            return None

        # Guardar
        color = bird_result.get("color", "variado")
        sex = bird_result.get("sex", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        quality = self._quality_score(crop, confidence, sharpness)

        breed_slug = breed.lower().replace(" ", "_").replace("(", "").replace(")", "")
        breed_dir = self._base / breed_slug
        breed_dir.mkdir(exist_ok=True)

        filename = f"{breed_slug}_{color}_{sex}_{timestamp}_{camera_id}_{confidence:.2f}.jpg"
        filepath = breed_dir / filename
        cv2.imwrite(str(filepath), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

        # Metadata
        entry = {
            "filepath": str(filepath),
            "breed": breed,
            "color": color,
            "sex": sex,
            "confidence": round(confidence, 4),
            "engine": engine,
            "camera_id": camera_id,
            "gallinero_id": gallinero_id,
            "bird_id": bird_result.get("bird_id", ""),
            "timestamp": timestamp,
            "crop_size": [w, h],
            "sharpness": round(sharpness, 2),
            "quality_score": round(quality, 4),
            "trigger_event": trigger_event,
        }

        try:
            with open(METADATA_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[CropCurator] Metadata write failed: {e}")

        self._daily_counts[day_key] = self._daily_counts.get(day_key, 0) + 1
        self._update_stats()

        logger.info(
            f"[CropCurator] Saved {breed} {color} ({confidence:.0%}, "
            f"q={quality:.2f}, {w}×{h}) → {filepath.name}"
        )
        return entry

    def get_stats(self) -> dict:
        """Stats del dataset curado."""
        if not STATS_FILE.exists():
            return {"total": 0, "by_breed": {}}
        try:
            return json.loads(STATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"total": 0, "by_breed": {}}

    def get_dataset_gaps(self, target: int = 100) -> list[str]:
        """Razas con menos de `target` crops curados."""
        stats = self.get_stats()
        by_breed = stats.get("by_breed", {})
        return [breed for breed, count in by_breed.items() if count < target]

    def browse(self, breed: str, limit: int = 20) -> list[dict]:
        """Últimos N crops curados de una raza."""
        if not METADATA_FILE.exists():
            return []
        results = []
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("breed", "").lower() == breed.lower():
                            results.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return results[-limit:]

    def reject(self, breed: str, filename: str) -> dict:
        """Mueve un crop mal etiquetado a _rejected/."""
        breed_slug = breed.lower().replace(" ", "_")
        src = self._base / breed_slug / filename
        dst = self._base / "_rejected" / filename
        if src.exists():
            src.rename(dst)
            return {"status": "rejected", "moved_to": str(dst)}
        return {"status": "not_found"}

    # ── Internal ──

    def _extract_crop(self, frame_bytes: bytes, bbox: list) -> np.ndarray | None:
        """Extrae crop del frame usando bbox normalizado (0-1)."""
        try:
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None

            h_img, w_img = img.shape[:2]
            x1, y1, x2, y2 = bbox

            # Si parece normalizado (0-1), escalar a píxeles
            if all(0 <= v <= 1.0 for v in bbox):
                x1, y1, x2, y2 = int(x1 * w_img), int(y1 * h_img), int(x2 * w_img), int(y2 * h_img)
            else:
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # Padding 15%
            pad_x = int((x2 - x1) * 0.15)
            pad_y = int((y2 - y1) * 0.15)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w_img, x2 + pad_x)
            y2 = min(h_img, y2 + pad_y)

            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                return None
            return crop
        except Exception:
            return None

    @staticmethod
    def _quality_score(crop: np.ndarray, confidence: float, sharpness: float) -> float:
        """Score compuesto 0-1: 35% confianza + 35% nitidez + 30% tamaño."""
        h, w = crop.shape[:2]
        size_score = min(1.0, (min(h, w) - 128) / 384)
        sharp_score = min(1.0, (sharpness - 40) / 160)
        conf_score = min(1.0, confidence)
        return 0.35 * conf_score + 0.35 * sharp_score + 0.30 * size_score

    def _update_stats(self):
        """Actualiza stats globales."""
        stats: dict[str, int] = {}
        if METADATA_FILE.exists():
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            breed = entry.get("breed", "unknown")
                            stats[breed] = stats.get(breed, 0) + 1
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass
        try:
            STATS_FILE.write_text(
                json.dumps({
                    "total": sum(stats.values()),
                    "by_breed": dict(sorted(stats.items(), key=lambda x: -x[1])),
                    "updated": datetime.now().isoformat(),
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"Stats update failed: {e}")


# ── Singleton ──

_curator: CropCurator | None = None


def get_crop_curator() -> CropCurator:
    global _curator
    if _curator is None:
        _curator = CropCurator()
    return _curator
