"""
Seedy Backend — API endpoints para dataset curado

Endpoints para consultar estadísticas de curación,
ver gaps de dataset, y navegar crops curados.
"""

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision/curated", tags=["curated"])


@router.get("/stats")
async def curated_stats():
    """Estadísticas del dataset curado (crops + frames)."""
    from services.crop_curator import get_curator
    curator = get_curator()
    return curator.get_stats()


@router.get("/gaps")
async def dataset_gaps():
    """Razas con pocos crops + progreso de frames para entrenamiento de detector."""
    from services.crop_curator import get_curator
    curator = get_curator()
    return curator.get_dataset_gaps()


@router.get("/browse/{breed}")
async def browse_breed(breed: str, limit: int = 20):
    """Lista crops curados de una raza específica."""
    if limit > 200:
        limit = 200
    from services.crop_curator import get_curator
    curator = get_curator()
    items = curator.browse_breed(breed, limit)
    return {"breed": breed, "count": len(items), "items": items}


@router.get("/frames/stats")
async def frames_stats():
    """Estadísticas de frames anotados para entrenamiento de detector."""
    from services.crop_curator import get_curator, CURATED_FRAMES_DIR
    curator = get_curator()
    stats = curator.get_stats()

    # Contar labels
    labels_dir = CURATED_FRAMES_DIR / "labels"
    label_count = len(list(labels_dir.glob("*.txt"))) if labels_dir.exists() else 0

    return {
        "frames_annotated": stats.get("frames_annotated", 0),
        "labels_count": label_count,
        "target": 500,
        "ready_to_train": stats.get("frames_annotated", 0) >= 500,
    }


@router.post("/capture-all")
async def capture_all_cameras(rounds: int = 5, delay: float = 3.0):
    """Captura y cura frames de las 3 cámaras en múltiples rondas.

    Diseñado para acelerar la acumulación de frames anotados para
    el entrenamiento del detector de gallinas.

    Args:
        rounds: Número de rondas de captura (default 5 → 15 frames potenciales)
        delay: Segundos entre rondas (default 3s para variedad de poses)
    """
    import asyncio
    import numpy as np
    import cv2

    rounds = min(rounds, 50)  # Max 50 rondas por llamada

    from services.crop_curator import get_curator
    from routers.vision_identify import _detect_with_yolo, _capture_frame, CAMERAS

    curator = get_curator()
    results = {"total_curated": 0, "total_skipped": 0, "rounds": rounds, "details": []}

    for rnd in range(rounds):
        if rnd > 0:
            await asyncio.sleep(delay)

        for cam_id, cam in CAMERAS.items():
            try:
                frame = await _capture_frame(
                    cam["stream"],
                    snapshot_url=cam.get("snapshot_url", ""),
                    force_hires=cam.get("distant", False),
                )
                if not frame:
                    continue

                yolo_result = _detect_with_yolo(
                    frame,
                    imgsz=cam.get("yolo_imgsz"),
                    use_tiled=cam.get("use_tiled", False),
                    use_breed=cam.get("use_breed", False),
                    camera_id=cam_id,
                )
                if not yolo_result or not yolo_result.get("detections"):
                    results["total_skipped"] += 1
                    continue

                # Decodificar frame para curación
                arr = np.frombuffer(frame, dtype=np.uint8)
                frame_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame_cv is None:
                    continue

                entry = await curator.curate_frame(
                    frame=frame_cv,
                    detections=yolo_result["detections"],
                    camera_id=cam_id,
                )
                if entry:
                    results["total_curated"] += 1
                    results["details"].append({
                        "round": rnd + 1,
                        "camera": cam_id,
                        "birds": entry.bird_count,
                    })
                else:
                    results["total_skipped"] += 1

            except Exception as e:
                logger.debug(f"Capture-all {cam_id} round {rnd}: {e}")
                results["total_skipped"] += 1

    # Stats actualizadas
    stats = curator.get_stats()
    results["frames_total"] = stats.get("frames_annotated", 0)
    results["frames_target"] = 500

    return results


# ══════════════════════════════════════════════════════
#  Acumulación continua en background
# ══════════════════════════════════════════════════════

_accumulation_task = None
_accumulation_status = {
    "running": False,
    "frames_curated": 0,
    "frames_skipped": 0,
    "started_at": None,
    "target": 500,
    "errors": 0,
}


async def _accumulation_loop(target: int = 500, interval: float = 16.0):
    """Loop continuo de acumulación de frames anotados.

    Captura de cada cámara cada `interval` segundos hasta alcanzar el target.
    Se auto-detiene al llegar a target o si se cancela.
    """
    import asyncio
    import numpy as np
    import cv2

    from services.crop_curator import get_curator
    from routers.vision_identify import _detect_with_yolo, _capture_frame, CAMERAS

    curator = get_curator()
    _accumulation_status["running"] = True
    _accumulation_status["started_at"] = datetime.now().isoformat()
    _accumulation_status["target"] = target

    try:
        while _accumulation_status["running"]:
            stats = curator.get_stats()
            current = stats.get("frames_annotated", 0)
            if current >= target:
                logger.info(f"🎯 Acumulación completada: {current}/{target} frames")
                break

            for cam_id, cam in CAMERAS.items():
                if not _accumulation_status["running"]:
                    break
                try:
                    frame = await _capture_frame(
                        cam["stream"],
                        snapshot_url=cam.get("snapshot_url", ""),
                        force_hires=cam.get("distant", False),
                    )
                    if not frame:
                        continue

                    yolo_result = _detect_with_yolo(
                        frame,
                        imgsz=cam.get("yolo_imgsz"),
                        use_tiled=cam.get("use_tiled", False),
                        use_breed=cam.get("use_breed", False),
                        camera_id=cam_id,
                    )
                    if not yolo_result or not yolo_result.get("detections"):
                        _accumulation_status["frames_skipped"] += 1
                        continue

                    arr = np.frombuffer(frame, dtype=np.uint8)
                    frame_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame_cv is None:
                        continue

                    entry = await curator.curate_frame(
                        frame=frame_cv,
                        detections=yolo_result["detections"],
                        camera_id=cam_id,
                    )
                    if entry:
                        _accumulation_status["frames_curated"] += 1
                    else:
                        _accumulation_status["frames_skipped"] += 1

                except Exception as e:
                    _accumulation_status["errors"] += 1
                    logger.debug(f"Accumulation {cam_id}: {e}")

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Acumulación cancelada")
    finally:
        _accumulation_status["running"] = False


from datetime import datetime


@router.post("/accumulate/start")
async def start_accumulation(target: int = 500, interval: float = 16.0):
    """Inicia acumulación continua de frames en background.

    Args:
        target: Número total de frames objetivo (default 500)
        interval: Segundos entre rondas de captura (default 16, justo sobre el cooldown de 15s)
    """
    import asyncio

    global _accumulation_task

    if _accumulation_status["running"]:
        return {"status": "already_running", **_accumulation_status}

    # Reset counters
    _accumulation_status["frames_curated"] = 0
    _accumulation_status["frames_skipped"] = 0
    _accumulation_status["errors"] = 0

    _accumulation_task = asyncio.create_task(_accumulation_loop(target, interval))
    return {"status": "started", "target": target, "interval": interval}


@router.post("/accumulate/stop")
async def stop_accumulation():
    """Detiene la acumulación en curso."""
    global _accumulation_task

    if not _accumulation_status["running"]:
        return {"status": "not_running"}

    _accumulation_status["running"] = False
    if _accumulation_task:
        _accumulation_task.cancel()
        _accumulation_task = None

    return {"status": "stopped", **_accumulation_status}


@router.get("/accumulate/status")
async def accumulation_status():
    """Estado de la acumulación en curso."""
    from services.crop_curator import get_curator
    curator = get_curator()
    stats = curator.get_stats()

    return {
        **_accumulation_status,
        "frames_total": stats.get("frames_annotated", 0),
        "frames_target": _accumulation_status["target"],
    }


# ══════════════════════════════════════════════════════
#  CaptureManager endpoints
# ══════════════════════════════════════════════════════


@router.get("/capture-manager/status")
async def capture_manager_status():
    """Estado del CaptureManager (sub-stream tracking + behavior)."""
    from services.capture_manager import get_capture_manager
    mgr = get_capture_manager()
    return mgr.get_status()


@router.post("/capture-manager/start")
async def capture_manager_start():
    """Inicia el CaptureManager manualmente."""
    from services.capture_manager import get_capture_manager
    mgr = get_capture_manager()
    if mgr._running:
        return {"status": "already_running", **mgr.get_status()}
    await mgr.start()
    return {"status": "started", **mgr.get_status()}


@router.post("/capture-manager/stop")
async def capture_manager_stop():
    """Detiene el CaptureManager."""
    from services.capture_manager import get_capture_manager
    mgr = get_capture_manager()
    if not mgr._running:
        return {"status": "not_running"}
    await mgr.stop()
    return {"status": "stopped"}
