"""Seedy Backend — Capture Manager: Dual Stream Architecture.

Sub-stream continuo (10-15fps, 640px) para tracking/behavior/pest.
Main-stream bajo demanda (4K snapshot) disparado por eventos.

Reemplaza el loop de 60s con un sistema event-driven donde el sub-stream
genera triggers que disparan capturas de alta resolución.
"""

import asyncio
import io
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import cv2
import httpx
import numpy as np
from PIL import Image, ImageStat

logger = logging.getLogger(__name__)


# ─── Tipos de evento de captura ───


class CaptureEvent(str, Enum):
    NEW_BIRD = "new_bird"
    MATING = "mating"
    PEST_ALERT = "pest_alert"
    RARE_BEHAVIOR = "rare_behavior"
    SCHEDULED = "scheduled"
    QUALITY_BIRD = "quality_bird"


# ─── Configuración de cámaras ───


@dataclass
class CameraConfig:
    camera_id: str
    ip: str
    gallinero_id: str
    # Sub-stream
    sub_stream_url: str
    sub_stream_fps: int = 10
    sub_imgsz: int = 640
    # Main-stream
    main_snapshot_url: str = ""
    main_imgsz: int = 1920
    use_tiled: bool = False
    # Auth
    auth_type: str = "basic"  # "basic" | "digest"
    username: str = "admin"
    password: str = ""
    snapshot_auth: tuple[str, str] = ("admin", "123456")
    # Dahua-specific
    is_dahua: bool = False
    optimize_exposure: bool = False
    # go2rtc stream names (for legacy compatibility)
    stream: str = ""
    stream_sub: str = ""
    name: str = ""


CAMERAS: dict[str, CameraConfig] = {
    "sauna_durrif_1": CameraConfig(
        camera_id="sauna_durrif_1",
        ip="10.10.10.108",
        gallinero_id="gallinero_durrif_1",
        sub_stream_url="rtsp://admin:1234567a@10.10.10.108/cam/realmonitor?channel=1&subtype=1",
        sub_stream_fps=15,
        sub_imgsz=640,
        main_snapshot_url="http://10.10.10.108/cgi-bin/snapshot.cgi?channel=1",
        main_imgsz=1920,
        use_tiled=False,
        auth_type="digest",
        username="admin",
        password="1234567a",
        snapshot_auth=("admin", "1234567a"),
        is_dahua=True,
        optimize_exposure=True,
        stream="sauna_durrif_1",
        stream_sub="sauna_durrif_1_sub",
        name="Sauna Durrif I (Dahua)",
    ),
    "gallinero_durrif_1": CameraConfig(
        camera_id="gallinero_durrif_1",
        ip="10.10.10.11",
        gallinero_id="gallinero_durrif_1",
        sub_stream_url="rtsp://admin:123456@10.10.10.11:554/stream2",
        sub_stream_fps=10,
        sub_imgsz=640,
        main_snapshot_url="http://10.10.10.11/cgi-bin/snapshot.cgi",
        main_imgsz=1920,
        use_tiled=True,
        auth_type="basic",
        username="admin",
        password="123456",
        snapshot_auth=("admin", "123456"),
        stream="gallinero_durrif_1",
        stream_sub="gallinero_durrif_1_sub",
        name="Gallinero Durrif I",
    ),
    "gallinero_durrif_2": CameraConfig(
        camera_id="gallinero_durrif_2",
        ip="10.10.10.10",
        gallinero_id="gallinero_durrif_2",
        sub_stream_url="rtsp://admin:123456@10.10.10.10:554/stream2",
        sub_stream_fps=10,
        sub_imgsz=640,
        main_snapshot_url="http://10.10.10.10/cgi-bin/snapshot.cgi",
        main_imgsz=1280,
        use_tiled=False,
        auth_type="basic",
        username="admin",
        password="123456",
        snapshot_auth=("admin", "123456"),
        stream="gallinero_durrif_2",
        stream_sub="gallinero_durrif_2_sub",
        name="Gallinero Durrif II",
    ),
}


# ─── Request de captura ───


@dataclass(order=True)
class CaptureRequest:
    priority: int
    camera_id: str = field(compare=False)
    event: CaptureEvent = field(compare=False)
    trigger_detections: list = field(compare=False, default_factory=list)
    timestamp: float = field(compare=False, default_factory=time.time)
    metadata: dict = field(compare=False, default_factory=dict)


# ─── Constantes ───

MIN_BRIGHTNESS = 25
MIN_CAPTURE_INTERVAL = 10          # Mín 10s entre capturas 4K por cámara
SCHEDULED_INTERVAL = 300           # Captura periódica cada 5 min
SUB_FRAME_SKIP = 2                 # Procesar 1 de cada N frames del sub-stream
RECONNECT_DELAY = 5                # Segundos antes de reconectar sub-stream


# ─── Capture Manager ───


class CaptureManager:
    """Gestiona la lógica dual-stream para todas las cámaras."""

    def __init__(self):
        self._capture_queue: asyncio.PriorityQueue[CaptureRequest] = asyncio.PriorityQueue()
        self._last_main_capture: dict[str, float] = {}
        self._sub_tasks: dict[str, asyncio.Task] = {}
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._stats: dict[str, dict] = {}

    async def start(self):
        """Arranca sub-stream readers + main-capture worker."""
        self._running = True
        for cam_id, config in CAMERAS.items():
            self._stats[cam_id] = {
                "sub_frames": 0, "main_captures": 0,
                "triggers": {e.value: 0 for e in CaptureEvent},
            }
            self._sub_tasks[cam_id] = asyncio.create_task(
                self._sub_stream_loop(config), name=f"sub_{cam_id}"
            )
        self._worker_task = asyncio.create_task(
            self._main_capture_worker(), name="main_capture_worker"
        )
        logger.info(f"📹 CaptureManager started: {len(CAMERAS)} cameras")

    async def stop(self):
        """Detiene todas las tareas."""
        self._running = False
        for task in self._sub_tasks.values():
            task.cancel()
        if self._worker_task:
            self._worker_task.cancel()
        self._sub_tasks.clear()
        self._worker_task = None
        logger.info("📹 CaptureManager stopped")

    def get_stats(self) -> dict:
        return {"running": self._running, "cameras": self._stats}

    # ─── Sub-stream loop ───

    async def _sub_stream_loop(self, config: CameraConfig):
        """Lee sub-stream vía go2rtc MJPEG, ejecuta YOLO + tracking + behavior."""
        go2rtc = os.environ.get("GO2RTC_URL", "http://host.docker.internal:1984")
        mjpeg_url = f"{go2rtc}/api/frame.jpeg?src={config.stream_sub}"
        frame_interval = 1.0 / config.sub_stream_fps
        frame_count = 0

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(mjpeg_url)
                    if resp.status_code != 200 or len(resp.content) < 1000:
                        await asyncio.sleep(RECONNECT_DELAY)
                        continue
                    frame_bytes = resp.content

                frame_count += 1
                if config.camera_id in self._stats:
                    self._stats[config.camera_id]["sub_frames"] = frame_count

                # Skip frames para reducir carga GPU
                if frame_count % SUB_FRAME_SKIP != 0:
                    await asyncio.sleep(frame_interval)
                    continue

                # Brightness check
                if not self._check_brightness(frame_bytes):
                    await asyncio.sleep(frame_interval)
                    continue

                # YOLO COCO detection (sub-stream: 640px, rápido)
                detections = self._yolo_detect(frame_bytes, config.sub_imgsz)
                if not detections:
                    await asyncio.sleep(frame_interval)
                    continue

                # Tracking + behavior + mating + pests (SIEMPRE)
                self._enrich_tracking(config.gallinero_id, frame_bytes)

                # Evaluar triggers para captura 4K
                poultry = [d for d in detections.get("detections", [])
                           if d.get("category") == "poultry"]
                await self._evaluate_triggers(config, detections, len(poultry))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Sub-stream {config.camera_id} error: {e}")
                await asyncio.sleep(RECONNECT_DELAY)
                continue

            await asyncio.sleep(frame_interval)

        logger.info(f"Sub-stream {config.camera_id} stopped (frames: {frame_count})")

    # ─── Trigger evaluation ───

    async def _evaluate_triggers(
        self, config: CameraConfig, detections: dict, poultry_count: int
    ):
        """Decide si disparar captura del main-stream (4K)."""
        now = time.time()
        last = self._last_main_capture.get(config.camera_id, 0)
        if now - last < MIN_CAPTURE_INTERVAL:
            return

        # Trigger 1: Plaga severa (prioridad máxima)
        from services.pest_alert import get_pest_manager
        pest_mgr = get_pest_manager()
        if detections.get("pest_count", 0) > 0:
            await self._enqueue(config.camera_id, CaptureEvent.PEST_ALERT, priority=1,
                                metadata={"pests": detections["pest_count"]})
            return

        # Trigger 2: Ave nueva sin ID (5+ frames vistas)
        from services.bird_tracker import get_tracker
        tracker = get_tracker(config.gallinero_id)
        for t in tracker.tracks.values():
            if t.active and not t.ai_vision_id and t.total_frames >= 5:
                await self._enqueue(config.camera_id, CaptureEvent.NEW_BIRD, priority=2,
                                    metadata={"track_id": t.track_id})
                return

        # Trigger 3: Monta en curso
        from services.mating_detector import get_mating_detector
        mating = get_mating_detector(config.gallinero_id)
        if mating.is_active():
            await self._enqueue(config.camera_id, CaptureEvent.MATING, priority=2)
            return

        # Trigger 4: Ave aislada con buen quality (oportunista)
        if poultry_count == 1:
            await self._enqueue(config.camera_id, CaptureEvent.QUALITY_BIRD, priority=3)
            return

        # Trigger 5: Muestreo periódico (cada 5 min como fallback)
        if now - last > SCHEDULED_INTERVAL:
            await self._enqueue(config.camera_id, CaptureEvent.SCHEDULED, priority=4)

    async def _enqueue(
        self, camera_id: str, event: CaptureEvent,
        priority: int = 3, metadata: dict | None = None,
    ):
        req = CaptureRequest(
            priority=priority,
            camera_id=camera_id,
            event=event,
            metadata=metadata or {},
        )
        await self._capture_queue.put(req)
        if camera_id in self._stats:
            self._stats[camera_id]["triggers"][event.value] += 1
        logger.debug(f"📸 Trigger {event.value} (p={priority}) → {camera_id}")

    # ─── Main-stream capture worker ───

    async def _main_capture_worker(self):
        """Procesa la cola de capturas 4K: captura main-stream → pipeline completo."""
        while self._running:
            try:
                req: CaptureRequest = await asyncio.wait_for(
                    self._capture_queue.get(), timeout=30.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            cam_config = CAMERAS.get(req.camera_id)
            if not cam_config:
                continue

            now = time.time()
            last = self._last_main_capture.get(req.camera_id, 0)
            if now - last < MIN_CAPTURE_INTERVAL:
                continue  # Throttle: descartamos si capturamos hace poco

            try:
                # Capturar frame 4K del main-stream
                frame = await self._capture_main_stream(cam_config)
                if not frame:
                    continue

                self._last_main_capture[req.camera_id] = time.time()
                if req.camera_id in self._stats:
                    self._stats[req.camera_id]["main_captures"] += 1

                # Pipeline completo de identificación (importar desde vision_identify)
                from routers.vision_identify import _analyze_frame, _register_or_update_birds
                from routers.vision_identify import _last_results

                analysis = await _analyze_frame(
                    frame, cam_config.gallinero_id,
                    imgsz=cam_config.main_imgsz,
                    use_tiled=cam_config.use_tiled,
                )
                if not analysis:
                    continue

                _last_results[cam_config.gallinero_id] = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "analysis": analysis,
                    "camera": cam_config.name,
                    "trigger": req.event.value,
                    "trigger_metadata": req.metadata,
                }

                # Registrar aves identificadas
                detected_birds = analysis.get("birds", [])
                if detected_birds:
                    await _register_or_update_birds(detected_birds, cam_config.gallinero_id, frame)

                    # Curación de crops (si el módulo está disponible)
                    try:
                        from services.crop_curator import get_crop_curator
                        curator = get_crop_curator()
                        for bird in detected_birds:
                            if bird.get("breed") and bird["breed"] != "Desconocida":
                                await curator.evaluate_and_save(
                                    frame_bytes=frame,
                                    bird_result=bird,
                                    camera_id=cam_config.camera_id,
                                    gallinero_id=cam_config.gallinero_id,
                                    trigger_event=req.event.value,
                                )
                    except ImportError:
                        pass
                    except Exception as e:
                        logger.debug(f"Crop curation failed: {e}")

                    bird = detected_birds[0]
                    logger.info(
                        f"[{cam_config.name}] ✅ {req.event.value}: "
                        f"{bird.get('breed', '?')} {bird.get('color', '')} "
                        f"(engine={analysis.get('engine', '?')})"
                    )

            except Exception as e:
                logger.warning(f"Main capture failed {req.camera_id}: {e}")

    # ─── Helpers ───

    async def _capture_main_stream(self, config: CameraConfig) -> bytes | None:
        """Captura snapshot 4K del main-stream via CGI o go2rtc."""
        # Intentar CGI snapshot directo (máxima calidad)
        if config.main_snapshot_url:
            try:
                auth = None
                if config.auth_type == "digest":
                    from httpx import DigestAuth
                    auth = DigestAuth(config.username, config.password)
                elif config.auth_type == "basic":
                    auth = (config.username, config.password)

                async with httpx.AsyncClient(timeout=10.0, auth=auth) as client:
                    resp = await client.get(config.main_snapshot_url)
                    if resp.status_code == 200 and len(resp.content) > 5000:
                        return resp.content
            except Exception as e:
                logger.debug(f"CGI snapshot failed {config.camera_id}: {e}")

        # Fallback: go2rtc main stream
        go2rtc = os.environ.get("GO2RTC_URL", "http://host.docker.internal:1984")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{go2rtc}/api/frame.jpeg?src={config.stream}")
                if resp.status_code == 200 and len(resp.content) > 5000:
                    return resp.content
        except Exception as e:
            logger.debug(f"go2rtc main snapshot failed {config.camera_id}: {e}")

        return None

    @staticmethod
    def _check_brightness(frame_bytes: bytes) -> bool:
        """Retorna True si hay suficiente luz para procesar."""
        try:
            img = Image.open(io.BytesIO(frame_bytes))
            brightness = ImageStat.Stat(img.convert("L")).mean[0]
            return brightness >= MIN_BRIGHTNESS
        except Exception:
            return True  # En caso de error, procesar igualmente

    @staticmethod
    def _yolo_detect(frame_bytes: bytes, imgsz: int = 640) -> dict | None:
        """Detección YOLO COCO rápida para sub-stream."""
        try:
            from services.yolo_detector import detect_birds
            return detect_birds(frame_bytes, imgsz=imgsz)
        except Exception as e:
            logger.debug(f"YOLO sub-stream detect failed: {e}")
            return None

    @staticmethod
    def _enrich_tracking(gallinero_id: str, frame_bytes: bytes):
        """Ejecuta tracker + behavior + mating + pests (delegado a vision_identify)."""
        try:
            from routers.vision_identify import _enrich_with_tracking
            _enrich_with_tracking(gallinero_id, frame_bytes)
        except Exception as e:
            logger.debug(f"Tracking enrichment failed ({gallinero_id}): {e}")


# ─── Singleton ───

_manager: CaptureManager | None = None


def get_capture_manager() -> CaptureManager:
    global _manager
    if _manager is None:
        _manager = CaptureManager()
    return _manager


async def start_capture_manager():
    mgr = get_capture_manager()
    await mgr.start()


async def stop_capture_manager():
    mgr = get_capture_manager()
    await mgr.stop()
