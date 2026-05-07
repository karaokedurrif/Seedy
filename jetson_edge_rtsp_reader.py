"""
Seedy Edge v4.5 — RTSP Stream Reader
Jetson Orin Nano 8GB

Lee sub-stream RTSP de cámaras con reconnect automático.
Usa OpenCV VideoCapture con ffmpeg backend optimizado para ARM64.
"""

import cv2
import time
import logging
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class RTSPReader:
    """
    RTSP stream reader con reconnect automático.
    Optimizado para sub-streams (10-15 FPS, resolución reducida).
    """
    
    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        reconnect_delay: int = 5,
        buffer_size: int = 1
    ):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.reconnect_delay = reconnect_delay
        self.buffer_size = buffer_size
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.error_count = 0
        self.last_frame_time = 0.0
        self._is_connected = False
        
    def connect(self) -> bool:
        """Conectar al stream RTSP."""
        try:
            # Cerrar conexión previa si existe
            if self.cap is not None:
                self.cap.release()
            
            # Crear VideoCapture con backend ffmpeg
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            # Configurar buffer pequeño (minimize latency)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
            
            # Verificar conexión
            if not self.cap.isOpened():
                logger.error(f"[{self.camera_id}] No se pudo abrir stream RTSP")
                return False
            
            # Leer frame de prueba
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.error(f"[{self.camera_id}] No se pudo leer frame inicial")
                self.cap.release()
                return False
            
            self._is_connected = True
            self.error_count = 0
            logger.info(
                f"[{self.camera_id}] Conectado a RTSP — "
                f"resolución: {frame.shape[1]}×{frame.shape[0]}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[{self.camera_id}] Error conectando: {e}")
            return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Leer un frame del stream.
        
        Returns:
            Frame (H×W×3 BGR) o None si error
        """
        if not self._is_connected:
            logger.warning(f"[{self.camera_id}] No conectado, intentando reconnect...")
            if not self.connect():
                time.sleep(self.reconnect_delay)
                return None
        
        try:
            ret, frame = self.cap.read()
            
            if not ret or frame is None:
                logger.warning(f"[{self.camera_id}] Frame vacío, reconnect en {self.reconnect_delay}s")
                self._is_connected = False
                self.error_count += 1
                time.sleep(self.reconnect_delay)
                return None
            
            self.frame_count += 1
            self.last_frame_time = time.time()
            
            # Log cada 100 frames
            if self.frame_count % 100 == 0:
                logger.debug(
                    f"[{self.camera_id}] Frame {self.frame_count} — "
                    f"shape: {frame.shape}, errors: {self.error_count}"
                )
            
            return frame
            
        except Exception as e:
            logger.error(f"[{self.camera_id}] Error leyendo frame: {e}")
            self._is_connected = False
            self.error_count += 1
            time.sleep(self.reconnect_delay)
            return None
    
    def get_fps(self) -> float:
        """Obtener FPS reportados por el stream."""
        if self.cap is not None and self.cap.isOpened():
            return self.cap.get(cv2.CAP_PROP_FPS)
        return 0.0
    
    def get_resolution(self) -> Tuple[int, int]:
        """Obtener resolución (width, height)."""
        if self.cap is not None and self.cap.isOpened():
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (width, height)
        return (0, 0)
    
    def is_healthy(self) -> bool:
        """Verificar salud del stream."""
        if not self._is_connected:
            return False
        
        # Verificar última lectura reciente (< 5s)
        time_since_last = time.time() - self.last_frame_time
        if time_since_last > 5.0:
            logger.warning(
                f"[{self.camera_id}] Sin frames por {time_since_last:.1f}s"
            )
            return False
        
        return True
    
    def close(self):
        """Cerrar stream."""
        if self.cap is not None:
            self.cap.release()
            self._is_connected = False
            logger.info(
                f"[{self.camera_id}] Stream cerrado — "
                f"frames procesados: {self.frame_count}, errors: {self.error_count}"
            )


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Test con Dahua Sauna (sub-stream)
    reader = RTSPReader(
        camera_id="test_dahua",
        rtsp_url="rtsp://admin:1234567a@10.10.10.108:554/cam/realmonitor?channel=1&subtype=1"
    )
    
    if reader.connect():
        print(f"✅ Conectado — FPS: {reader.get_fps()}, Resolución: {reader.get_resolution()}")
        
        # Leer 30 frames
        for i in range(30):
            frame = reader.read_frame()
            if frame is not None:
                print(f"Frame {i+1}: {frame.shape}")
            time.sleep(0.1)
        
        reader.close()
    else:
        print("❌ No se pudo conectar")
