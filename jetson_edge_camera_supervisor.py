"""
Seedy Edge v4.5 — Camera Supervisor (Orchestrator)
Jetson Orin Nano 8GB

Supervisor por cámara: integra RTSP reader + YOLO inference + tracking simple + DGX relay.
Tracking básico por centroide (el backend DGX hará el tracking robusto).
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime

# Imports locales
from jetson_edge_rtsp_reader import RTSPReader
from jetson_edge_yolo_engine import YOLOEngine, Detection
from jetson_edge_dgx_relay import DGXRelay

logger = logging.getLogger(__name__)


class SimpleTracker:
    """
    Tracker simple por centroide para el edge.
    Solo asigna track_id temporal, el backend hará tracking robusto.
    """
    
    def __init__(self, max_age: int = 120, iou_threshold: float = 0.30):
        self.max_age = max_age  # frames
        self.iou_threshold = iou_threshold
        
        self.tracks: Dict[int, Dict] = {}  # track_id → {centroid, bbox, age, class_name}
        self.next_id = 1
    
    def update(self, detections: List) -> List[Dict]:
        """
        Actualizar tracks con nuevas detecciones.
        
        Args:
            detections: Lista de Detection objects
            
        Returns:
            Lista de tracks con {track_id, bbox, centroid, class_name, confidence}
        """
        # Incrementar age de tracks existentes
        for track_id in list(self.tracks.keys()):
            self.tracks[track_id]["age"] += 1
            
            # Eliminar tracks antiguos
            if self.tracks[track_id]["age"] > self.max_age:
                del self.tracks[track_id]
        
        # Si no hay detecciones, devolver tracks existentes
        if len(detections) == 0:
            return self._export_tracks()
        
        # Matching simple por distancia centroide
        det_centroids = np.array([det.centroid for det in detections])
        
        assigned = set()
        
        for track_id, track_data in self.tracks.items():
            track_centroid = np.array(track_data["centroid"])
            
            # Calcular distancias a detecciones no asignadas
            dists = []
            for i, det in enumerate(detections):
                if i in assigned:
                    continue
                dist = np.linalg.norm(det_centroid - track_centroid)
                dists.append((i, dist))
            
            if len(dists) == 0:
                continue
            
            # Match con la detección más cercana (si < 100px)
            dists.sort(key=lambda x: x[1])
            best_idx, best_dist = dists[0]
            
            if best_dist < 100.0:  # threshold arbitrario
                det = detections[best_idx]
                self.tracks[track_id] = {
                    "centroid": det.centroid,
                    "bbox": det.bbox,
                    "age": 0,
                    "class_name": det.class_name,
                    "confidence": det.confidence
                }
                assigned.add(best_idx)
        
        # Crear nuevos tracks para detecciones no asignadas
        for i, det in enumerate(detections):
            if i not in assigned:
                self.tracks[self.next_id] = {
                    "centroid": det.centroid,
                    "bbox": det.bbox,
                    "age": 0,
                    "class_name": det.class_name,
                    "confidence": det.confidence
                }
                self.next_id += 1
        
        return self._export_tracks()
    
    def _export_tracks(self) -> List[Dict]:
        """Exportar tracks actuales a formato serializable."""
        result = []
        for track_id, data in self.tracks.items():
            result.append({
                "track_id": track_id,
                "bbox": list(data["bbox"]),
                "centroid": list(data["centroid"]),
                "class_name": data["class_name"],
                "confidence": float(data["confidence"]),
                "age": data["age"]
            })
        return result


class CameraSupervisor:
    """
    Supervisor por cámara: lee sub-stream, ejecuta YOLO, trackea, publica a DGX.
    """
    
    def __init__(
        self,
        camera_id: str,
        camera_config: Dict,
        yolo_engine,  # YOLOEngine instance
        dgx_relay,     # DGXRelay instance
        gallinero_id: str,
        edge_node_id: str,
        tracking_config: Dict
    ):
        self.camera_id = camera_id
        self.camera_config = camera_config
        self.yolo_engine = yolo_engine
        self.dgx_relay = dgx_relay
        self.gallinero_id = gallinero_id
        self.edge_node_id = edge_node_id
        
        # Componentes
        self.rtsp_reader = RTSPReader(
            camera_id=camera_id,
            rtsp_url=camera_config["rtsp_sub"],
            reconnect_delay=5
        )
        
        self.tracker = SimpleTracker(
            max_age=tracking_config["max_age"],
            iou_threshold=tracking_config["iou_threshold"]
        )
        
        # Estado
        self.running = False
        self.frame_count = 0
        self.last_publish_time = 0.0
        self.publish_interval = 1.0  # Publicar cada 1s
    
    async def start(self):
        """Iniciar supervisor (loop infinito)."""
        logger.info(f"[{self.camera_id}] 🚀 Iniciando supervisor...")
        
        # Conectar RTSP
        if not self.rtsp_reader.connect():
            logger.error(f"[{self.camera_id}] ❌ No se pudo conectar al stream")
            return
        
        self.running = True
        
        try:
            while self.running:
                # Leer frame
                frame = self.rtsp_reader.read_frame()
                if frame is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Detectar
                detections = self.yolo_engine.detect(frame)
                
                # Trackear
                tracks = self.tracker.update(detections)
                
                self.frame_count += 1
                
                # Publicar a DGX cada 1s
                now = time.time()
                if now - self.last_publish_time >= self.publish_interval:
                    await self._publish_event(tracks, now)
                    self.last_publish_time = now
                
                # Control de FPS (dormir un poco para no saturar CPU)
                await asyncio.sleep(0.05)  # ~20 FPS max
                
        except KeyboardInterrupt:
            logger.info(f"[{self.camera_id}] ⏸️  Supervisor detenido por usuario")
        except Exception as e:
            logger.error(f"[{self.camera_id}] ❌ Error en supervisor: {e}")
        finally:
            self.running = False
            self.rtsp_reader.close()
    
    async def _publish_event(self, tracks: List[Dict], timestamp: float):
        """Publicar evento al backend DGX."""
        event = {
            "schema_version": "4.5",
            "timestamp": timestamp,
            "edge_node_id": self.edge_node_id,
            "camera_id": self.camera_id,
            "gallinero_id": self.gallinero_id,
            "event_type": "tracking",
            "tracks": tracks,
            "frame_count": self.frame_count
        }
        
        await self.dgx_relay.publish_event(event)
    
    def stop(self):
        """Detener supervisor."""
        logger.info(f"[{self.camera_id}] 🛑 Deteniendo supervisor...")
        self.running = False


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("CameraSupervisor — Componente orchestrator edge v4.5")
    print("(Test completo requiere YOLOEngine y DGXRelay instanciados)")
