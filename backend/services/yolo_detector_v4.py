"""
Seedy Backend — Detector de aves v4.1

Arquitectura corregida:
  - COCO v8s como DETECTOR primario (genera bboxes individuales)
  - Breed v3 como CLASIFICADOR sobre crops (asigna raza)
  - Filtro de artefactos integrado
  - Clases COCO extendidas: bird(14) + cat(15) + dog(16) como candidatos a gallina

El modelo breed (seedy_breeds_best.pt) fue entrenado con imágenes de 1 ave
llenando el frame completo → solo funciona como clasificador sobre crops
individuales, NUNCA como detector sobre tiles/frames completos.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Config desde entorno ──
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8s.pt")
YOLO_BREED_MODEL = os.getenv("YOLO_BREED_MODEL", "/app/yolo_models/seedy_breeds_best.pt")
YOLO_DEVICE = os.getenv("YOLO_DEVICE", "0")

# Clases COCO que pueden ser gallinas
POULTRY_CANDIDATE_CLASSES = {
    14: "bird",   # Clase directa
    15: "cat",    # Gallinas agachadas → silueta tipo gato
    16: "dog",    # Gallinas de pie → silueta tipo perro (muy común en campo)
}

# Clases COCO de plagas
PEST_CLASSES = {14: "bird"}  # bird en COCO puede ser gorrión/paloma

# Config de detección
COCO_CONFIDENCE = float(os.getenv("YOLO_COCO_CONFIDENCE", "0.20"))
COCO_NMS_IOU = float(os.getenv("YOLO_COCO_NMS_IOU", "0.45"))
BREED_MIN_CONF = float(os.getenv("YOLO_BREED_MIN_CONF", "0.20"))

# Config de tiles por cámara
CAMERA_TILE_CONFIG = {
    "gallinero_durrif_1": {"tile_size": 960, "overlap": 0.20},
    "sauna_durrif_1": {"tile_size": 800, "overlap": 0.20},
    "gallinero_durrif_2": {"tile_size": 1280, "overlap": 0.20},
    # Aliases de nueva nomenclatura
    "cam_nueva_vigi": {"tile_size": 960, "overlap": 0.20},
    "cam_sauna_dahua": {"tile_size": 800, "overlap": 0.20},
    "cam_gallinero_vigi": {"tile_size": 1280, "overlap": 0.20},
}

# Clases de breed que son plagas
BREED_PEST_CLASSES = {"gorrion", "paloma", "rata", "depredador"}
# Clases de breed que son infraestructura (ignorar)
BREED_INFRA_CLASSES = {"comedero", "bebedero", "nido", "aseladero", "huevo"}


class YOLODetectorV4:
    """
    Detector de aves v4.1:
    - COCO v8s como DETECTOR primario (bboxes)
    - Breed v3 como CLASIFICADOR sobre crops (raza)
    - Filtro de artefactos en tiles
    - Clases COCO extendidas: bird + dog + cat como candidatos
    """

    def __init__(self, device: str = YOLO_DEVICE):
        self.device = device
        self._coco_model = None
        self._breed_model = None
        self._breed_names: Dict[int, str] = {}

    def _load_coco(self):
        """Carga lazy del modelo COCO."""
        if self._coco_model is None:
            from ultralytics import YOLO
            logger.info(f"Cargando COCO model: {YOLO_MODEL} en device={self.device}")
            self._coco_model = YOLO(YOLO_MODEL)
            logger.info("COCO model cargado OK")

    def _load_breed(self):
        """Carga lazy del modelo breed (clasificador)."""
        if self._breed_model is None:
            if not os.path.exists(YOLO_BREED_MODEL):
                logger.warning(f"Breed model no encontrado: {YOLO_BREED_MODEL}")
                return
            from ultralytics import YOLO
            logger.info(f"Cargando Breed model: {YOLO_BREED_MODEL}")
            self._breed_model = YOLO(YOLO_BREED_MODEL)
            self._breed_names = dict(self._breed_model.names) if self._breed_model else {}
            logger.info(f"Breed model cargado: {len(self._breed_names)} clases")

    def reload_models(self):
        """Fuerza recarga de ambos modelos."""
        self._coco_model = None
        self._breed_model = None
        self._breed_names = {}
        self._load_coco()
        self._load_breed()

    # ── Detección principal ──

    def detect_birds(
        self,
        frame_bytes: bytes,
        camera_id: str = "",
        use_tiled: bool = True,
        coco_conf: float = COCO_CONFIDENCE,
        nms_iou: float = COCO_NMS_IOU,
        classify_breeds: bool = True,
    ) -> dict:
        """
        Pipeline completo: COCO detector → artifact filter → breed classifier.

        Args:
            frame_bytes: Frame JPEG como bytes
            camera_id: ID de cámara para seleccionar config de tiles
            use_tiled: Si True, usa tileado (para main-stream 4K)
            coco_conf: Confianza mínima COCO
            nms_iou: IoU threshold para NMS
            classify_breeds: Si True, clasifica cada crop con breed model

        Returns:
            dict con keys: detections, count, inference_ms, model, poultry_count, pest_count
        """
        self._load_coco()
        t0 = time.time()

        # Decodificar frame
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"detections": [], "count": 0, "inference_ms": 0, "model": YOLO_MODEL}

        h, w = frame.shape[:2]

        # Paso 1: Detección COCO
        tile_config = CAMERA_TILE_CONFIG.get(camera_id) if use_tiled else None
        if tile_config and max(h, w) > 1000:
            raw_dets = self._detect_tiled_coco(frame, tile_config, coco_conf, nms_iou)
        else:
            raw_dets = self._detect_single_coco(frame, coco_conf, nms_iou)

        # Paso 2: Filtro de artefactos a nivel de frame
        from services.artifact_filter import filter_frame_artifacts
        filtered = filter_frame_artifacts(raw_dets, w, h)

        # Paso 3: Clasificar cada crop con breed
        results = []
        for det in filtered:
            x1 = max(0, int(det["x1"]))
            y1 = max(0, int(det["y1"]))
            x2 = min(w, int(det["x2"]))
            y2 = min(h, int(det["y2"]))

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # Clasificar con breed si disponible
            breed_info = {"breed": "sin_clasificar", "breed_conf": 0.0, "breed_class": "", "is_pest": False}
            if classify_breeds:
                breed_info = self._classify_crop(crop)

            # Calcular bbox normalizado
            bbox_norm = [x1 / w, y1 / h, x2 / w, y2 / h]

            # Crop JPEG para curación/display
            _, crop_jpg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            crop_bytes = crop_jpg.tobytes() if crop_jpg is not None else b""

            # Categorizar
            breed_name = breed_info.get("breed", "sin_clasificar")
            is_pest = breed_info.get("is_pest", False)
            if is_pest:
                category = "pest"
            elif breed_name in BREED_INFRA_CLASSES:
                category = "infrastructure"
            else:
                category = "poultry"

            results.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "bbox": [x1, y1, x2, y2],
                "bbox_norm": bbox_norm,
                "confidence": det["conf"],
                "coco_class": det.get("coco_class", "bird"),
                "coco_class_id": det.get("coco_class_id", 14),
                "class_name": breed_name,
                "breed": breed_name,
                "breed_conf": breed_info.get("breed_conf", 0.0),
                "breed_class": breed_info.get("breed_class", ""),
                "is_pest": is_pest,
                "category": category,
                "crop_bytes": crop_bytes,
            })

        elapsed = (time.time() - t0) * 1000
        poultry = [r for r in results if r["category"] == "poultry"]
        pests = [r for r in results if r["category"] == "pest"]

        return {
            "detections": results,
            "count": len(poultry),
            "pest_count": len(pests),
            "total_detections": len(results),
            "inference_ms": round(elapsed, 1),
            "model": YOLO_MODEL,
            "breed_model": os.path.basename(YOLO_BREED_MODEL),
            "frame_size": (w, h),
            "tiled": tile_config is not None,
        }

    # ── Detección COCO con tileado ──

    def _detect_tiled_coco(
        self, frame: np.ndarray, tile_config: dict,
        conf: float, nms_iou: float,
    ) -> List[dict]:
        """Detección COCO con tileado + filtro de artefactos por tile."""
        from services.artifact_filter import filter_tile_artifacts

        h, w = frame.shape[:2]
        tile_size = tile_config["tile_size"]
        overlap = tile_config.get("overlap", 0.20)
        stride = int(tile_size * (1 - overlap))
        all_detections = []

        for y_start in range(0, h, stride):
            for x_start in range(0, w, stride):
                y_end = min(y_start + tile_size, h)
                x_end = min(x_start + tile_size, w)
                tile = frame[y_start:y_end, x_start:x_end]

                tile_h, tile_w = tile.shape[:2]
                if tile_h < 100 or tile_w < 100:
                    continue

                results = self._coco_model(
                    tile, conf=conf, iou=nms_iou,
                    device=self.device, verbose=False,
                    classes=list(POULTRY_CANDIDATE_CLASSES.keys()),
                )

                tile_dets = []
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        if cls_id not in POULTRY_CANDIDATE_CLASSES:
                            continue
                        bx1, by1, bx2, by2 = box.xyxy[0].cpu().numpy()
                        tile_dets.append({
                            "x1": float(bx1), "y1": float(by1),
                            "x2": float(bx2), "y2": float(by2),
                            "conf": float(box.conf[0]),
                            "coco_class": POULTRY_CANDIDATE_CLASSES[cls_id],
                            "coco_class_id": cls_id,
                        })

                # Filtro de artefactos a nivel de tile
                tile_dets = filter_tile_artifacts(tile_dets, tile_w, tile_h)

                # Traducir coordenadas tile → frame
                for d in tile_dets:
                    d["x1"] += x_start
                    d["y1"] += y_start
                    d["x2"] += x_start
                    d["y2"] += y_start
                    all_detections.append(d)

        # NMS global para eliminar duplicados de tiles solapados
        if all_detections:
            all_detections = self._global_nms(all_detections, nms_iou)

        return all_detections

    # ── Detección COCO sin tileado ──

    def _detect_single_coco(
        self, frame: np.ndarray, conf: float, nms_iou: float,
    ) -> List[dict]:
        """Detección COCO sin tileado (sub-stream o frames pequeños)."""
        results = self._coco_model(
            frame, conf=conf, iou=nms_iou,
            device=self.device, verbose=False,
            classes=list(POULTRY_CANDIDATE_CLASSES.keys()),
        )

        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in POULTRY_CANDIDATE_CLASSES:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                detections.append({
                    "x1": float(x1), "y1": float(y1),
                    "x2": float(x2), "y2": float(y2),
                    "conf": float(box.conf[0]),
                    "coco_class": POULTRY_CANDIDATE_CLASSES[cls_id],
                    "coco_class_id": cls_id,
                })

        return detections

    # ── Clasificador breed sobre crop ──

    def _classify_crop(self, crop: np.ndarray) -> dict:
        """
        Clasifica un crop individual con el modelo breed.

        El breed model tiene task=detect (no classify), así que al pasarle un crop
        donde el ave llena la mayor parte de la imagen (como fue entrenado),
        devuelve una detección con la clase de raza + confidence.
        Tomamos la detección de mayor confianza como clasificación.
        """
        self._load_breed()
        if self._breed_model is None:
            return {"breed": "sin_clasificar", "breed_conf": 0.0, "breed_class": "", "is_pest": False}

        # Padding del crop para dar contexto (YOLO detecta mejor con margen)
        ch, cw = crop.shape[:2]
        pad = max(10, int(max(ch, cw) * 0.15))  # 15% padding mínimo 10px
        padded = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(114, 114, 114))

        # Resize crop al tamaño que el breed model espera (~640 imgsz de detección)
        results = self._breed_model(padded, device=self.device, verbose=False, conf=0.10)

        # El breed model es task=detect → devuelve boxes, no probs
        if results and results[0].boxes is not None and len(results[0].boxes) > 0:
            # Tomar la detección de mayor confianza
            boxes = results[0].boxes
            best_idx = int(boxes.conf.argmax())
            best_conf = float(boxes.conf[best_idx])
            best_cls = int(boxes.cls[best_idx])
            class_name = results[0].names.get(best_cls, "unknown")

            if class_name in BREED_PEST_CLASSES:
                return {
                    "breed": class_name, "breed_conf": best_conf,
                    "breed_class": class_name, "is_pest": True,
                }
            if class_name in BREED_INFRA_CLASSES:
                return {
                    "breed": class_name, "breed_conf": best_conf,
                    "breed_class": class_name, "is_pest": False,
                }
            if best_conf >= BREED_MIN_CONF:
                return {
                    "breed": class_name, "breed_conf": best_conf,
                    "breed_class": class_name, "is_pest": False,
                }

        # Fallback: intentar con probs (por si el modelo fuera classify)
        if results and results[0].probs is not None:
            probs = results[0].probs
            top_class_id = int(probs.top1)
            top_conf = float(probs.top1conf)
            class_name = results[0].names.get(top_class_id, "unknown")

            if top_conf >= BREED_MIN_CONF:
                is_pest = class_name in BREED_PEST_CLASSES
                return {
                    "breed": class_name, "breed_conf": top_conf,
                    "breed_class": class_name, "is_pest": is_pest,
                }

        return {"breed": "sin_clasificar", "breed_conf": 0.0, "breed_class": "", "is_pest": False}

    def classify_crop_from_bytes(self, crop_bytes: bytes) -> dict:
        """Clasifica un crop JPEG dado como bytes."""
        arr = np.frombuffer(crop_bytes, dtype=np.uint8)
        crop = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if crop is None:
            return {"breed": "sin_clasificar", "breed_conf": 0.0, "breed_class": "", "is_pest": False}
        return self._classify_crop(crop)

    # ── NMS global ──

    def _global_nms(self, detections: List[dict], iou_threshold: float) -> List[dict]:
        """NMS global sobre detecciones de todos los tiles."""
        if not detections:
            return []

        boxes = np.array([[d["x1"], d["y1"], d["x2"], d["y2"]] for d in detections])
        scores = np.array([d["conf"] for d in detections])

        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []

        while order.size > 0:
            i = order[0]
            keep.append(i)

            if order.size == 1:
                break

            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            union = areas[i] + areas[order[1:]] - inter
            iou = inter / np.maximum(union, 1e-6)

            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]

        return [detections[i] for i in keep]

    # ── Utilidades ──

    def get_model_info(self) -> dict:
        """Info de modelos cargados."""
        return {
            "coco_model": YOLO_MODEL,
            "breed_model": os.path.basename(YOLO_BREED_MODEL),
            "breed_classes": self._breed_names,
            "coco_loaded": self._coco_model is not None,
            "breed_loaded": self._breed_model is not None,
            "device": self.device,
            "coco_confidence": COCO_CONFIDENCE,
            "nms_iou": COCO_NMS_IOU,
            "breed_min_conf": BREED_MIN_CONF,
            "poultry_candidate_classes": POULTRY_CANDIDATE_CLASSES,
        }

    def draw_detections(
        self,
        frame_bytes: bytes,
        detections: List[dict],
        label: str = "",
    ) -> bytes:
        """Dibuja bboxes con anotaciones sobre el frame."""
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return frame_bytes

        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.4, min(h, w) / 1500)
        thickness = max(1, int(min(h, w) / 500))

        # Colores por categoría
        colors = {
            "poultry": (0, 200, 0),       # Verde
            "pest": (0, 0, 220),           # Rojo
            "infrastructure": (200, 200, 0),  # Cyan
        }

        for det in detections:
            x1, y1, x2, y2 = int(det["x1"]), int(det["y1"]), int(det["x2"]), int(det["y2"])
            category = det.get("category", "poultry")
            color = colors.get(category, (200, 200, 200))

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

            breed = det.get("breed", det.get("class_name", "ave"))
            conf = det.get("confidence", det.get("conf", 0))
            breed_conf = det.get("breed_conf", 0)
            coco_cls = det.get("coco_class", "")

            text = f"{breed} {breed_conf:.0%}" if breed_conf > 0 else f"{coco_cls} {conf:.0%}"
            text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
            ty = max(y1 - 5, text_size[1] + 5)
            cv2.rectangle(frame, (x1, ty - text_size[1] - 4), (x1 + text_size[0] + 4, ty + 4), color, -1)
            cv2.putText(frame, text, (x1 + 2, ty), font, font_scale, (255, 255, 255), thickness)

        # Watermark
        wm = f"Seedy v4.1 · {label} · {len([d for d in detections if d.get('category') == 'poultry'])} aves"
        cv2.putText(frame, wm, (10, h - 15), font, font_scale * 0.8, (180, 180, 180), 1)

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return buf.tobytes() if buf is not None else frame_bytes


# ── Singleton ──
_detector_instance: Optional[YOLODetectorV4] = None


def get_detector() -> YOLODetectorV4:
    """Obtiene la instancia singleton del detector v4."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = YOLODetectorV4()
    return _detector_instance
