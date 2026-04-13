"""
Seedy Backend — Capture Manager v4.1

Gestiona la arquitectura dual-stream:
  - Sub-stream (704×576, 10-15fps): tracking continuo, behavior, plagas, mating
  - Main-stream (4K): event-triggered para ID, curación de datos

El sub-stream corre SIEMPRE. El main-stream solo se dispara bajo trigger.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import cv2
import httpx
import numpy as np

logger = logging.getLogger(__name__)

GO2RTC_URL = os.getenv("GO2RTC_URL", "http://host.docker.internal:1984")


class CaptureEvent(Enum):
    NEW_BIRD = "new_bird"
    MATING = "mating"
    PEST_ALERT = "pest_alert"
    RARE_BEHAVIOR = "rare_behavior"
    SCHEDULED = "scheduled"
    QUALITY_BIRD = "quality_bird"
    HIGH_COUNT = "high_count"
    MANUAL = "manual"


@dataclass
class CameraConfig:
    camera_id: str
    ip: str
    gallinero_id: str = "gallinero_durrif"
    # Sub-stream
    sub_stream_url: str = ""
    sub_stream_fps: int = 10
    # Main-stream
    main_snapshot_url: str = ""
    # Tileado
    tile_size: int = 1280
    tile_overlap: float = 0.20
    use_tiled: bool = True
    # Auth
    auth_type: str = "basic"
    username: str = "admin"
    password: str = ""
    # Dahua-specific
    is_dahua: bool = False


@dataclass
class CaptureRequest:
    camera_id: str
    event: CaptureEvent
    priority: int
    bird_count: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def __lt__(self, other):
        return self.priority < other.priority


# Las 3 cámaras cubren el MISMO gallinero unificado (26 aves)
CAMERAS: Dict[str, CameraConfig] = {
    "gallinero_durrif_1": CameraConfig(
        camera_id="gallinero_durrif_1",
        ip="10.10.10.11",
        sub_stream_url="rtsp://admin:123456@10.10.10.11:554/stream2",
        sub_stream_fps=10,
        main_snapshot_url="http://10.10.10.11/cgi-bin/snapshot.cgi",
        tile_size=960,
        password="123456",
    ),
    "sauna_durrif_1": CameraConfig(
        camera_id="sauna_durrif_1",
        ip="10.10.10.108",
        sub_stream_url="rtsp://admin:1234567a@10.10.10.108/cam/realmonitor?channel=1&subtype=1",
        sub_stream_fps=15,
        main_snapshot_url="http://10.10.10.108/cgi-bin/snapshot.cgi?channel=1",
        tile_size=800,
        auth_type="digest",
        password="1234567a",
        is_dahua=True,
    ),
    "gallinero_durrif_2": CameraConfig(
        camera_id="gallinero_durrif_2",
        ip="10.10.10.10",
        sub_stream_url="rtsp://admin:123456@10.10.10.10:554/stream2",
        sub_stream_fps=10,
        main_snapshot_url="http://10.10.10.10/cgi-bin/snapshot.cgi",
        tile_size=1280,
        password="123456",
    ),
}


class CaptureManager:
    """Gestiona la lógica dual-stream para el gallinero unificado."""

    def __init__(self):
        self._capture_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._last_main_capture: Dict[str, float] = {}
        self._min_capture_interval = 10.0  # 10s entre capturas 4K por cámara
        self._sub_stream_tasks: Dict[str, asyncio.Task] = {}
        self._main_worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "sub_frames_processed": 0,
            "main_captures": 0,
            "triggers": {e.value: 0 for e in CaptureEvent},
            "errors": 0,
            "started_at": None,
        }

    async def start(self):
        """Inicia todos los sub-streams + worker de main-stream."""
        if self._running:
            logger.warning("CaptureManager ya está corriendo")
            return

        self._running = True
        self._stats["started_at"] = time.time()

        # Iniciar sub-stream loops
        for cam_id, config in CAMERAS.items():
            task = asyncio.create_task(
                self._sub_stream_loop(config),
                name=f"sub_{cam_id}",
            )
            self._sub_stream_tasks[cam_id] = task

        # Worker que procesa la cola de capturas main-stream
        self._main_worker_task = asyncio.create_task(
            self._main_capture_worker(),
            name="main_capture_worker",
        )

        logger.info(f"🚀 CaptureManager started: {len(CAMERAS)} cámaras")

    async def stop(self):
        """Detiene todos los streams."""
        self._running = False

        for task in self._sub_stream_tasks.values():
            task.cancel()
        if self._main_worker_task:
            self._main_worker_task.cancel()

        self._sub_stream_tasks.clear()
        self._main_worker_task = None
        logger.info("⏹️ CaptureManager stopped")

    def get_status(self) -> dict:
        """Estado actual del CaptureManager."""
        return {
            "running": self._running,
            "cameras": list(CAMERAS.keys()),
            "sub_streams_active": [
                cid for cid, t in self._sub_stream_tasks.items() if not t.done()
            ],
            "queue_size": self._capture_queue.qsize(),
            "stats": self._stats,
        }

    # ── Sub-stream loop (SIEMPRE activo) ──

    async def _sub_stream_loop(self, config: CameraConfig):
        """Lee el sub-stream, ejecuta COCO detect + tracker + behavior."""
        frame_interval = 1.0 / config.sub_stream_fps
        cap = None
        consecutive_errors = 0

        while self._running:
            try:
                if cap is None or not cap.isOpened():
                    cap = await asyncio.to_thread(
                        cv2.VideoCapture, config.sub_stream_url,
                    )
                    if not cap.isOpened():
                        logger.warning(f"⚠️ No se pudo abrir sub-stream {config.camera_id}")
                        await asyncio.sleep(5)
                        consecutive_errors += 1
                        if consecutive_errors > 10:
                            await asyncio.sleep(30)
                        continue

                    consecutive_errors = 0
                    logger.info(f"📹 Sub-stream conectado: {config.camera_id}")

                # Leer frame en thread (blocking I/O)
                ret, frame = await asyncio.to_thread(cap.read)
                if not ret or frame is None:
                    cap.release()
                    cap = None
                    await asyncio.sleep(2)
                    continue

                # Skip si es de noche (luminancia baja)
                if frame.mean() < 25:
                    await asyncio.sleep(frame_interval)
                    continue

                # Procesar frame del sub-stream
                await self._process_sub_frame(config, frame)
                self._stats["sub_frames_processed"] += 1

                await asyncio.sleep(frame_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error en sub-stream {config.camera_id}: {e}")
                self._stats["errors"] += 1
                await asyncio.sleep(2)

        if cap is not None:
            cap.release()

    async def _process_sub_frame(self, config: CameraConfig, frame: np.ndarray):
        """Procesa un frame del sub-stream: detect + track + behavior + triggers."""
        from services.yolo_detector_v4 import get_detector
        from services.bird_tracker import get_tracker

        detector = get_detector()

        # Encode frame to bytes for detector
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if buf is None:
            return
        frame_bytes = buf.tobytes()

        # Detectar con COCO (sin tileado en sub-stream 704×576)
        result = detector.detect_birds(
            frame_bytes,
            camera_id=config.camera_id,
            use_tiled=False,
            classify_breeds=False,  # Sub-stream: solo detectar, no clasificar
        )

        detections = result.get("detections", [])
        bird_count = result.get("count", 0)

        # Feed tracker
        tracker = get_tracker(config.gallinero_id)
        tracker.update(detections)

        # Feed pest alert
        pest_dets = [d for d in detections if d.get("is_pest")]
        if pest_dets:
            try:
                from services.pest_alert import get_pest_manager
                mgr = get_pest_manager()
                mgr.process_detections(config.gallinero_id, pest_dets)
            except Exception:
                pass

        # Evaluar triggers de captura 4K
        await self._evaluate_triggers(config, frame_bytes, detections, bird_count)

    # ── Trigger evaluation ──

    async def _evaluate_triggers(
        self, config: CameraConfig, frame_bytes: bytes,
        detections: list, bird_count: int,
    ):
        """Evalúa si se debe disparar una captura main-stream 4K."""
        now = time.time()
        last = self._last_main_capture.get(config.camera_id, 0)
        if now - last < self._min_capture_interval:
            return

        from services.bird_tracker import get_tracker
        tracker = get_tracker(config.gallinero_id)

        # Trigger 1: Ave nueva sin ID (tracker la ve ≥5 frames)
        for track in tracker.get_active_tracks():
            if not track.get("breed") and track.get("total_frames", 0) >= 5:
                if not track.get("ai_vision_id"):
                    await self._enqueue_capture(config, CaptureEvent.NEW_BIRD, 2, bird_count)
                    return

        # Trigger 2: Plaga severa
        try:
            from services.pest_alert import get_pest_manager
            mgr = get_pest_manager()
            stats = mgr.get_stats()
            if stats.get("active_alerts"):
                await self._enqueue_capture(
                    config, CaptureEvent.PEST_ALERT, 1, bird_count,
                    metadata={"pest_count": len(stats["active_alerts"])},
                )
                return
        except Exception:
            pass

        # Trigger 3: Frame con muchas aves (excelente para dataset de detección)
        if bird_count >= 10:
            await self._enqueue_capture(config, CaptureEvent.HIGH_COUNT, 3, bird_count)
            return

        # Trigger 4: Ave aislada con buena calidad (para crop)
        if bird_count == 1 and detections:
            det = detections[0]
            bbox = det.get("bbox_norm", [0, 0, 0, 0])
            if len(bbox) == 4:
                area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                if area > 0.02:
                    await self._enqueue_capture(config, CaptureEvent.QUALITY_BIRD, 3, bird_count)
                    return

        # Trigger 5: Muestreo periódico (5 min fallback)
        if now - last > 300:
            await self._enqueue_capture(config, CaptureEvent.SCHEDULED, 4, bird_count)

    async def _enqueue_capture(
        self, config: CameraConfig, event: CaptureEvent,
        priority: int, bird_count: int, metadata: dict = None,
    ):
        req = CaptureRequest(
            camera_id=config.camera_id,
            event=event,
            priority=priority,
            bird_count=bird_count,
            metadata=metadata or {},
        )
        await self._capture_queue.put((priority, time.time(), req))
        self._last_main_capture[config.camera_id] = time.time()
        self._stats["triggers"][event.value] = self._stats["triggers"].get(event.value, 0) + 1
        logger.info(f"📋 Trigger {event.value} (P{priority}) para {config.camera_id} ({bird_count} aves)")

    # ── Main-stream worker ──

    async def _main_capture_worker(self):
        """Worker que procesa capturas 4K de la cola."""
        while self._running:
            try:
                priority, ts, request = await asyncio.wait_for(
                    self._capture_queue.get(), timeout=5.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._process_main_capture(request)
                self._stats["main_captures"] += 1
            except Exception as e:
                logger.error(f"Error procesando captura main-stream: {e}")
                self._stats["errors"] += 1

    async def _process_main_capture(self, request: CaptureRequest):
        """Captura 4K + pipeline completo: detect + classify + curate."""
        config = CAMERAS.get(request.camera_id)
        if not config:
            return

        logger.info(
            f"🎯 Main capture: {request.camera_id} event={request.event.value}"
        )

        # Capturar snapshot 4K
        frame_bytes = await self._capture_main_stream(config)
        if not frame_bytes:
            logger.warning(f"No se pudo capturar main-stream de {config.camera_id}")
            return

        # Pipeline completo con breed classification
        from services.yolo_detector_v4 import get_detector
        detector = get_detector()

        result = detector.detect_birds(
            frame_bytes,
            camera_id=config.camera_id,
            use_tiled=config.use_tiled,
            classify_breeds=True,
        )

        detections = result.get("detections", [])
        bird_count = result.get("count", 0)

        logger.info(
            f"📊 Main result: {bird_count} aves, {result.get('pest_count', 0)} plagas, "
            f"{result.get('inference_ms', 0):.0f}ms"
        )

        # Curación dual
        try:
            from services.crop_curator import get_curator
            curator = get_curator()

            # Decodificar frame para curación
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame_cv is None:
                return

            # Track A: Curar crops individuales
            for det in detections:
                if det.get("breed") and det["breed"] not in ("sin_clasificar", "Desconocida"):
                    crop_bytes = det.get("crop_bytes", b"")
                    if crop_bytes:
                        crop_arr = np.frombuffer(crop_bytes, dtype=np.uint8)
                        crop_cv = cv2.imdecode(crop_arr, cv2.IMREAD_COLOR)
                        if crop_cv is not None:
                            await curator.curate_crop(
                                crop=crop_cv,
                                identification={
                                    "breed": det["breed"],
                                    "confidence": det.get("breed_conf", 0),
                                    "engine": "yolo_breed",
                                    "color": det.get("color", ""),
                                    "sex": det.get("sex", ""),
                                },
                                camera_id=config.camera_id,
                                trigger_event=request.event.value,
                            )

            # Track B: Curar frame completo con bboxes
            await curator.curate_frame(
                frame=frame_cv,
                detections=detections,
                camera_id=config.camera_id,
                trigger_event=request.event.value,
            )
        except Exception as e:
            logger.error(f"Error en curación: {e}")

    async def _capture_main_stream(self, config: CameraConfig) -> Optional[bytes]:
        """Captura snapshot vía CGI o go2rtc."""
        # Intento 1: CGI snapshot directo
        if config.main_snapshot_url:
            try:
                auth = None
                if config.auth_type == "digest":
                    auth = httpx.DigestAuth(config.username, config.password)
                else:
                    auth = httpx.BasicAuth(config.username, config.password)

                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(config.main_snapshot_url, auth=auth)
                    if r.status_code == 200 and len(r.content) > 5000:
                        return r.content
            except Exception as e:
                logger.debug(f"CGI snapshot failed for {config.camera_id}: {e}")

        # Intento 2: go2rtc MJPEG snapshot
        main_stream_name = config.camera_id  # Usa el nombre del stream en go2rtc
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{GO2RTC_URL}/api/frame.jpeg?src={main_stream_name}")
                if r.status_code == 200 and len(r.content) > 5000:
                    return r.content
        except Exception as e:
            logger.debug(f"go2rtc snapshot failed for {config.camera_id}: {e}")

        return None

    # ── Manual trigger ──

    async def trigger_capture(self, camera_id: str, event: str = "manual") -> dict:
        """Trigger manual de captura 4K."""
        config = CAMERAS.get(camera_id)
        if not config:
            return {"error": f"Cámara {camera_id} no configurada"}

        try:
            evt = CaptureEvent(event)
        except ValueError:
            evt = CaptureEvent.MANUAL

        await self._enqueue_capture(config, evt, 2, 0)
        return {"queued": True, "camera": camera_id, "event": event}


# ── Singleton ──
_manager_instance: Optional[CaptureManager] = None


def get_capture_manager() -> CaptureManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = CaptureManager()
    return _manager_instance
