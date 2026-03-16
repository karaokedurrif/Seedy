"""
Seedy Vision — Jetson Orin Nano Edge Inference Pipeline
Inferencia optimizada en Jetson con TensorRT + DeepStream
"""
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

import cv2
import numpy as np
from rich.console import Console

console = Console()


@dataclass
class Detection:
    """Resultado de una detección"""
    class_id: int
    class_name: str
    confidence: float
    bbox: list[float]       # [x1, y1, x2, y2] absoluto
    bbox_norm: list[float]  # [x_center, y_center, w, h] normalizado
    area_px: float = 0.0
    
    def to_dict(self):
        return asdict(self)


@dataclass
class FrameResult:
    """Resultado completo de un frame"""
    timestamp: str
    camera_id: str
    frame_id: int
    detections: list[Detection]
    inference_ms: float
    resolution: tuple[int, int]
    
    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "num_detections": len(self.detections),
            "inference_ms": self.inference_ms,
            "resolution": list(self.resolution),
            "detections": [d.to_dict() for d in self.detections],
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ─────────────────────────────────────────────────────
# Motor de inferencia YOLO
# ─────────────────────────────────────────────────────

class SeedyInferenceEngine:
    """
    Motor de inferencia optimizado para Jetson Orin Nano.
    Soporta PyTorch (.pt), ONNX (.onnx) y TensorRT (.engine).
    """
    
    def __init__(self,
                 model_path: str,
                 class_names: list[str],
                 conf_threshold: float = 0.4,
                 iou_threshold: float = 0.5,
                 imgsz: int = 640,
                 device: str = "0"):
        """
        Args:
            model_path: Path al modelo (.pt, .onnx o .engine)
            class_names: Lista de nombres de clase
            conf_threshold: Umbral mínimo de confianza
            iou_threshold: Umbral NMS
            imgsz: Tamaño de imagen de entrada
            device: GPU device
        """
        self.model_path = model_path
        self.class_names = class_names
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.imgsz = imgsz
        self.device = device
        self.model = None
        self.frame_count = 0
        
        self._load_model()
    
    def _load_model(self):
        """Carga el modelo según formato"""
        from ultralytics import YOLO
        
        console.print(f"[cyan]🔧 Cargando modelo: {self.model_path}[/]")
        t0 = time.time()
        
        self.model = YOLO(self.model_path)
        
        # Warmup (importante en Jetson para TensorRT)
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False)
        
        elapsed = (time.time() - t0) * 1000
        console.print(f"[green]✅ Modelo cargado ({elapsed:.0f}ms, device={self.device})[/]")
    
    def predict(self, frame: np.ndarray, camera_id: str = "cam0") -> FrameResult:
        """
        Ejecuta inferencia en un frame.
        
        Args:
            frame: Imagen BGR (OpenCV)
            camera_id: ID de la cámara
        
        Returns: FrameResult con todas las detecciones
        """
        self.frame_count += 1
        h, w = frame.shape[:2]
        
        t0 = time.time()
        results = self.model.predict(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )
        inference_ms = (time.time() - t0) * 1000
        
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                
                # Normalizar
                x_center = ((x1 + x2) / 2) / w
                y_center = ((y1 + y2) / 2) / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                
                cls_name = self.class_names[cls_id] if cls_id < len(self.class_names) else f"class_{cls_id}"
                area = (x2 - x1) * (y2 - y1)
                
                detections.append(Detection(
                    class_id=cls_id,
                    class_name=cls_name,
                    confidence=conf,
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    bbox_norm=[x_center, y_center, bw, bh],
                    area_px=area,
                ))
        
        return FrameResult(
            timestamp=datetime.now().isoformat(),
            camera_id=camera_id,
            frame_id=self.frame_count,
            detections=detections,
            inference_ms=inference_ms,
            resolution=(w, h),
        )
    
    def draw_detections(self, frame: np.ndarray,
                         result: FrameResult) -> np.ndarray:
        """Dibuja bounding boxes en el frame"""
        img = frame.copy()
        
        colors = {
            "chicken": (0, 200, 255),    # naranja
            "pig": (200, 100, 200),       # rosa
            "cattle": (100, 200, 100),    # verde
            "chick": (0, 255, 255),       # amarillo
            "piglet": (255, 150, 200),    # rosa claro
            "calf": (150, 255, 150),      # verde claro
        }
        default_color = (200, 200, 200)
        
        for det in result.detections:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            color = colors.get(det.class_name, default_color)
            
            # Box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            
            # Label
            label = f"{det.class_name} {det.confidence:.2f}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, y1 - lh - 6), (x1 + lw, y1), color, -1)
            cv2.putText(img, label, (x1, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # FPS / info overlay
        fps_text = f"Seedy Vision | {result.inference_ms:.1f}ms | {len(result.detections)} det"
        cv2.putText(img, fps_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return img


# ─────────────────────────────────────────────────────
# Pipeline de cámara completo
# ─────────────────────────────────────────────────────

class SeedyCameraPipeline:
    """
    Pipeline cámara → inferencia → eventos → API/MQTT.
    Para Jetson Orin Nano con cámaras CSI/USB/RTSP.
    """
    
    def __init__(self,
                 engine: SeedyInferenceEngine,
                 camera_source: str = "0",
                 camera_id: str = "cam0",
                 mqtt_topic: Optional[str] = None,
                 api_url: Optional[str] = None,
                 save_events: bool = True,
                 events_dir: str = "events"):
        """
        Args:
            engine: Motor de inferencia
            camera_source: 0 (USB), CSI GStreamer string, o URL RTSP
            camera_id: Identificador de cámara
            mqtt_topic: Topic MQTT (e.g. "seedy/vision/cam0")
            api_url: URL del backend Seedy (e.g. "http://seedy:8000/vision/event")
            save_events: Guardar frames con detecciones
        """
        self.engine = engine
        self.camera_source = camera_source
        self.camera_id = camera_id
        self.mqtt_topic = mqtt_topic
        self.api_url = api_url
        self.save_events = save_events
        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        
        self.mqtt_client = None
        self._setup_mqtt()
    
    def _setup_mqtt(self):
        """Configura cliente MQTT si hay topic definido"""
        if not self.mqtt_topic:
            return
        try:
            import paho.mqtt.client as mqtt
            self.mqtt_client = mqtt.Client(client_id=f"seedy-vision-{self.camera_id}")
            self.mqtt_client.connect("localhost", 1883, 60)
            self.mqtt_client.loop_start()
            console.print(f"[green]✅ MQTT conectado → {self.mqtt_topic}[/]")
        except Exception as e:
            console.print(f"[yellow]⚠ MQTT no disponible: {e}[/]")
            self.mqtt_client = None
    
    def _get_camera_capture(self) -> cv2.VideoCapture:
        """Abre la cámara según el tipo de source"""
        src = self.camera_source
        
        # USB camera
        if src.isdigit():
            return cv2.VideoCapture(int(src))
        
        # CSI camera (Jetson) via GStreamer
        if "nvarguscamerasrc" in src or "v4l2src" in src:
            return cv2.VideoCapture(src, cv2.CAP_GSTREAMER)
        
        # RTSP / file
        return cv2.VideoCapture(src)
    
    def _publish_event(self, result: FrameResult):
        """Publica evento via MQTT y/o API"""
        payload = result.to_json()
        
        # MQTT
        if self.mqtt_client and self.mqtt_topic:
            self.mqtt_client.publish(
                self.mqtt_topic, payload, qos=1
            )
        
        # HTTP API
        if self.api_url:
            try:
                import httpx
                httpx.post(self.api_url, content=payload,
                          headers={"Content-Type": "application/json"},
                          timeout=5)
            except Exception:
                pass
    
    def _save_event_frame(self, frame: np.ndarray, result: FrameResult):
        """Guarda frame con detecciones para dataset futuro"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        img_path = self.events_dir / f"{self.camera_id}_{ts}.jpg"
        json_path = self.events_dir / f"{self.camera_id}_{ts}.json"
        
        annotated = self.engine.draw_detections(frame, result)
        cv2.imwrite(str(img_path), annotated)
        json_path.write_text(result.to_json())
    
    def run(self, show_preview: bool = False, max_frames: int = 0):
        """
        Loop principal de inferencia.
        
        Args:
            show_preview: Mostrar ventana con detecciones (no en headless)
            max_frames: Máximo de frames a procesar (0 = infinito)
        """
        console.print(Panel.fit(
            f"[bold cyan]📹 Seedy Vision — Camera Pipeline[/]\n"
            f"Cámara: {self.camera_source} ({self.camera_id})\n"
            f"MQTT: {self.mqtt_topic or 'desactivado'}\n"
            f"API: {self.api_url or 'desactivado'}\n"
            f"Guardar eventos: {self.save_events}",
            border_style="cyan",
        ))
        
        cap = self._get_camera_capture()
        if not cap.isOpened():
            console.print(f"[red]❌ No se pudo abrir la cámara: {self.camera_source}[/]")
            return
        
        fps_list = []
        frame_count = 0
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    console.print("[yellow]⚠ Frame vacío, reconectando...[/]")
                    time.sleep(1)
                    cap = self._get_camera_capture()
                    continue
                
                frame_count += 1
                
                # Inferencia
                result = self.engine.predict(frame, self.camera_id)
                fps = 1000.0 / max(result.inference_ms, 1)
                fps_list.append(fps)
                
                # Publicar si hay detecciones
                if result.detections:
                    self._publish_event(result)
                    
                    if self.save_events:
                        self._save_event_frame(frame, result)
                
                # Preview
                if show_preview:
                    annotated = self.engine.draw_detections(frame, result)
                    cv2.imshow(f"Seedy Vision — {self.camera_id}", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                
                # Log cada 100 frames
                if frame_count % 100 == 0:
                    avg_fps = sum(fps_list[-100:]) / min(len(fps_list), 100)
                    console.print(
                        f"[dim]Frame {frame_count} | "
                        f"{avg_fps:.1f} FPS avg | "
                        f"{result.inference_ms:.1f}ms | "
                        f"{len(result.detections)} det[/]"
                    )
                
                if max_frames and frame_count >= max_frames:
                    break
                    
        except KeyboardInterrupt:
            console.print("\n[yellow]⏹ Pipeline detenido[/]")
        finally:
            cap.release()
            if show_preview:
                cv2.destroyAllWindows()
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
            
            avg_fps = sum(fps_list) / max(len(fps_list), 1)
            console.print(
                f"\n[green]📊 Resumen: {frame_count} frames, "
                f"{avg_fps:.1f} FPS promedio[/]"
            )


# ─────────────────────────────────────────────────────
# GStreamer pipelines para Jetson
# ─────────────────────────────────────────────────────

GSTREAMER_PIPELINES = {
    # CSI camera (IMX219, IMX477)
    "csi_1080p": (
        "nvarguscamerasrc sensor-id=0 ! "
        "video/x-raw(memory:NVMM), width=1920, height=1080, "
        "framerate=30/1, format=NV12 ! "
        "nvvidconv ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    ),
    "csi_4k": (
        "nvarguscamerasrc sensor-id=0 ! "
        "video/x-raw(memory:NVMM), width=3840, height=2160, "
        "framerate=15/1, format=NV12 ! "
        "nvvidconv ! video/x-raw, width=1920, height=1080, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    ),
    # USB camera
    "usb_1080p": (
        "v4l2src device=/dev/video0 ! "
        "video/x-raw, width=1920, height=1080, framerate=30/1 ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    ),
    # RTSP (IP camera)
    "rtsp": (
        "rtspsrc location={url} latency=100 ! "
        "rtph264depay ! h264parse ! nvv4l2decoder ! "
        "nvvidconv ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    ),
}


# ─────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from config import DETECTION_CLASSES
    
    parser = argparse.ArgumentParser(description="Seedy Vision — Jetson Inference")
    parser.add_argument("--model", "-m", required=True,
                       help="Path al modelo (.pt, .onnx, .engine)")
    parser.add_argument("--source", "-s", default="0",
                       help="Fuente: 0 (USB), rtsp://..., o gstreamer pipeline name")
    parser.add_argument("--camera-id", default="cam0",
                       help="ID de cámara")
    parser.add_argument("--conf", type=float, default=0.4,
                       help="Umbral de confianza")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--mqtt-topic", default=None,
                       help="Topic MQTT (e.g. seedy/vision/cam0)")
    parser.add_argument("--api-url", default=None,
                       help="URL API backend")
    parser.add_argument("--show", action="store_true",
                       help="Mostrar preview")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--events-dir", default="events")
    
    args = parser.parse_args()
    
    # Resolver GStreamer pipeline si es un nombre conocido
    source = args.source
    if source in GSTREAMER_PIPELINES:
        source = GSTREAMER_PIPELINES[source]
    
    class_names = list(DETECTION_CLASSES.values())
    
    engine = SeedyInferenceEngine(
        model_path=args.model,
        class_names=class_names,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
    )
    
    pipeline = SeedyCameraPipeline(
        engine=engine,
        camera_source=source,
        camera_id=args.camera_id,
        mqtt_topic=args.mqtt_topic,
        api_url=args.api_url,
        events_dir=args.events_dir,
    )
    
    pipeline.run(show_preview=args.show, max_frames=args.max_frames)
