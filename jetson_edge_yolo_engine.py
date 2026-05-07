"""
Seedy Edge v4.5 — YOLOv8s TensorRT Inference Engine
Jetson Orin Nano 8GB

Inferencia optimizada con TensorRT FP16.
Detector COCO (bird+dog+cat como candidatos a ave).
"""

import time
import logging
from typing import List, Tuple, Optional
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class Detection:
    """Detección individual."""
    def __init__(
        self,
        bbox: Tuple[float, float, float, float],  # x1, y1, x2, y2
        confidence: float,
        class_id: int,
        class_name: str
    ):
        self.bbox = bbox
        self.confidence = confidence
        self.class_id = class_id
        self.class_name = class_name
        
        # Calcular centroide y área
        self.centroid = (
            (bbox[0] + bbox[2]) / 2,
            (bbox[1] + bbox[3]) / 2
        )
        self.area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    
    def to_dict(self) -> dict:
        """Serializar a dict."""
        return {
            "bbox": list(self.bbox),
            "centroid": list(self.centroid),
            "area": float(self.area),
            "confidence": float(self.confidence),
            "class_id": int(self.class_id),
            "class_name": self.class_name
        }


class YOLOEngine:
    """
    Motor de inferencia YOLOv8s con TensorRT.
    Optimizado para Jetson Orin Nano.
    """
    
    def __init__(
        self,
        model_path: str,
        device: int = 0,
        conf_threshold: float = 0.20,
        iou_threshold: float = 0.45,
        classes: Optional[List[int]] = None,
        max_det: int = 50,
        imgsz: int = 640
    ):
        self.model_path = model_path
        self.device = device
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.classes = classes  # [14, 15, 16] = bird, cat, dog
        self.max_det = max_det
        self.imgsz = imgsz
        
        self.model: Optional[YOLO] = None
        self.inference_count = 0
        self.total_inference_time = 0.0
        
        # COCO class names
        self.class_names = {
            14: "bird",
            15: "cat", 
            16: "dog"
        }
    
    def load_model(self) -> bool:
        """Cargar modelo TensorRT."""
        try:
            logger.info(f"Cargando modelo TensorRT: {self.model_path}")
            start = time.time()
            
            self.model = YOLO(self.model_path, task='detect')
            
            # Warmup (primera inferencia es lenta)
            dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
            _ = self.model.predict(
                dummy,
                device=self.device,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                verbose=False
            )
            
            load_time = time.time() - start
            logger.info(f"✅ Modelo cargado en {load_time:.2f}s (incluye warmup)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cargando modelo: {e}")
            return False
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Ejecutar detección sobre un frame.
        
        Args:
            frame: Imagen BGR (H×W×3)
            
        Returns:
            Lista de detecciones
        """
        if self.model is None:
            logger.error("Modelo no cargado")
            return []
        
        try:
            start = time.time()
            
            # Inferencia
            results = self.model.predict(
                frame,
                device=self.device,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                classes=self.classes,
                max_det=self.max_det,
                verbose=False,
                stream=False
            )
            
            inference_time = time.time() - start
            self.inference_count += 1
            self.total_inference_time += inference_time
            
            # Parsear resultados
            detections = []
            if len(results) > 0:
                result = results[0]
                boxes = result.boxes
                
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].cpu().numpy()  # x1, y1, x2, y2
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    cls_name = self.class_names.get(cls_id, f"class_{cls_id}")
                    
                    detection = Detection(
                        bbox=tuple(bbox),
                        confidence=conf,
                        class_id=cls_id,
                        class_name=cls_name
                    )
                    detections.append(detection)
            
            # Log periódico
            if self.inference_count % 100 == 0:
                avg_time = self.total_inference_time / self.inference_count
                fps = 1.0 / avg_time if avg_time > 0 else 0
                logger.info(
                    f"Inferencias: {self.inference_count} — "
                    f"Avg time: {avg_time*1000:.1f}ms — "
                    f"FPS: {fps:.1f}"
                )
            
            return detections
            
        except Exception as e:
            logger.error(f"Error en detección: {e}")
            return []
    
    def get_stats(self) -> dict:
        """Obtener estadísticas de inferencia."""
        avg_time = (
            self.total_inference_time / self.inference_count
            if self.inference_count > 0 else 0
        )
        fps = 1.0 / avg_time if avg_time > 0 else 0
        
        return {
            "inference_count": self.inference_count,
            "total_time_s": self.total_inference_time,
            "avg_time_ms": avg_time * 1000,
            "fps": fps
        }


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Crear frame de prueba
    test_frame = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    # Inicializar engine
    engine = YOLOEngine(
        model_path="models/yolov8s.engine",
        device=0,
        conf_threshold=0.20,
        iou_threshold=0.45,
        classes=[14, 15, 16]
    )
    
    if engine.load_model():
        print("✅ Modelo cargado")
        
        # Test 10 inferencias
        for i in range(10):
            dets = engine.detect(test_frame)
            print(f"Frame {i+1}: {len(dets)} detecciones")
        
        stats = engine.get_stats()
        print(f"\n📊 Stats: {stats}")
    else:
        print("❌ Error cargando modelo")
