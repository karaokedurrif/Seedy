"""
Seedy Backend — Router /vision/identify

Bridge entre cámaras en directo y el sistema de tracking de aves.
Periódicamente captura un frame de cada cámara (via go2rtc),
lo analiza con YOLO (detección local) + Gemini Vision (identificación de raza),
y registra/actualiza las aves en el registro de birds.

Estrategia híbrida:
  - YOLO: detección rápida (conteo + bboxes) en cada ciclo (~50ms)
  - Gemini: identificación de raza solo cuando hay aves nuevas no registradas
  - Entrenamiento: cada frame con detecciones → dataset YOLO para fine-tune
"""

import asyncio
import base64
import io
import json
import httpx
import logging
import time
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response

from services.vision_breeds import (
    BIRD_ID_PROMPT,
    BREED_YOLO_TO_CENSUS as _BREED_YOLO_TO_CENSUS,
    FALLBACK_BREEDS as _FALLBACK_BREEDS,
    build_vision_id as _build_vision_id,
    classify_breeds_yolo as _classify_breeds_yolo,
    resolve_unknown_by_census as _resolve_unknown_by_census,
    merge_breed_yolo_into_gemini as _merge_breed_yolo_into_gemini,
    bbox_iou as _bbox_iou,
    validate_breeds_against_census as _validate_breeds_against_census,
    normalize_to_census as _normalize_to_census,
    fuzzy_match as _fuzzy_match,
    map_sex as _map_sex,
    match_breed_ovosfera as _match_breed_ovosfera,
    match_color_ovosfera as _match_color_ovosfera,
)
from services.vision_gallery import (
    crop_bird_photo as _crop_bird_photo,
    make_thumbnail as _make_thumbnail,
    save_crop_to_gallery as _save_crop_to_gallery,
    get_gallery_photos as _get_gallery_photos,
    build_contact_sheet as _build_contact_sheet,
    visual_reidentify as _visual_reidentify,
)

logger = logging.getLogger(__name__)

try:
    from runtime.logger import log_agent_run, RunTimer
except ImportError:
    log_agent_run = None
    RunTimer = None

router = APIRouter(prefix="/vision/identify", tags=["vision-identify"])

# ── Config ──

GO2RTC_URL = os.environ.get("GO2RTC_URL", "http://172.18.0.1:1984")
OVOSFERA_API = os.environ.get("OVOSFERA_API_URL", "https://hub.ovosfera.com/api/ovosfera")
OVOSFERA_FARM = os.environ.get("OVOSFERA_FARM_SLUG", "palacio")
CAMERAS = {
    "gallinero_durrif_1": {
        "stream": "gallinero_durrif_1",
        "stream_sub": "gallinero_durrif_1_sub",
        "snapshot_url": "http://10.10.10.11/cgi-bin/snapshot.cgi",
        "name": "Gallinero Durrif I",
        "distant": True,       # ~20m desde lateral G II, aves pequeñas
        "yolo_imgsz": 1920,   # 4K frame needs large inference size
        "use_tiled": True,     # SAHI-style tiled detection for small objects
    },
    "gallinero_durrif_2": {
        "stream": "gallinero_durrif_2",
        "stream_sub": "gallinero_durrif_2_sub",
        "snapshot_url": "http://10.10.10.10/cgi-bin/snapshot.cgi",
        "name": "Gallinero Durrif II",
        "distant": False,      # cámara dentro del recinto, cerca
        "yolo_imgsz": 1280,
        "use_tiled": False,
    },
    "sauna_durrif_1": {
        "stream": "sauna_durrif_1",
        "stream_sub": "sauna_durrif_1_sub",
        "snapshot_url": "http://10.10.10.108/cgi-bin/snapshot.cgi",
        "snapshot_auth": ("admin", "1234567a"),
        "name": "Sauna Durrif I (Dahua)",
        "distant": False,
        "yolo_imgsz": 1920,
        "use_tiled": False,
    },
}

# Estado del loop
_running = False
_last_results: dict[str, dict] = {}
_task: asyncio.Task | None = None
_night_logged = False  # evita spam de log nocturno
MIN_BRIGHTNESS = 25   # luminancia mínima para procesar (0-255)

# ── Gemini rate limiter (solo identification loop, NO afecta al chat) ──
_GEMINI_LOOP_COOLDOWN = 300  # 5 min entre llamadas Gemini desde el loop
_gemini_last_call: float = 0.0  # timestamp de la última llamada


async def _capture_frame(camera_stream: str, *, use_sub: bool = False, snapshot_url: str = "",
                         snapshot_auth: tuple[str, str] = ("admin", "123456"),
                         force_hires: bool = False) -> bytes | None:
    """Captura un frame JPEG.

    Estrategia:
    - force_hires=True: siempre go2rtc main stream (4K, ~800KB, ~1s)
      Necesario para cámaras lejanas donde CGI da solo 704x576.
    - Normal: CGI directo (~100ms, 704x576), fallback go2rtc.
    """
    import httpx

    # Cámaras lejanas: go2rtc main stream directamente (4K)
    if force_hires:
        url = f"{GO2RTC_URL}/api/frame.jpeg?src={camera_stream}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return resp.content
        except Exception as e:
            logger.debug(f"go2rtc hires capture failed ({camera_stream}): {e}")
        # Fallback to CGI if go2rtc fails

    # CGI snapshot directo (rápido pero 704x576)
    if snapshot_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(snapshot_url, auth=httpx.BasicAuth(*snapshot_auth))
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return resp.content
        except Exception:
            pass

    # Fallback: go2rtc
    stream_key = camera_stream
    if use_sub:
        stream_key = camera_stream + "_sub" if not camera_stream.endswith("_sub") else camera_stream
    url = f"{GO2RTC_URL}/api/frame.jpeg?src={stream_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as e:
        logger.debug(f"Frame capture failed ({stream_key}): {e}")
    return None


async def _capture_from_cam(cam: dict, *, use_sub: bool = False, force_hires: bool = False) -> bytes | None:
    """Helper: captura frame usando la config completa de la cámara."""
    return await _capture_frame(
        cam["stream"],
        use_sub=use_sub,
        snapshot_url=cam.get("snapshot_url", ""),
        snapshot_auth=tuple(cam.get("snapshot_auth", ("admin", "123456"))),
        force_hires=force_hires,
    )


def _detect_with_yolo(frame_bytes: bytes, *, imgsz: int | None = None, use_tiled: bool = False) -> dict | None:
    """Detección rápida con YOLO local. Devuelve conteo + bboxes.

    Args:
        imgsz: Resolución de inferencia (overrides YOLO_IMGSZ default).
        use_tiled: Si True, usa detección por tiles (SAHI) — mejor para aves lejanas.
    """
    try:
        if use_tiled:
            from services.yolo_detector import detect_tiled
            return detect_tiled(frame_bytes, tile_size=imgsz or 1280)
        from services.yolo_detector import detect_birds
        return detect_birds(frame_bytes, imgsz=imgsz)
    except Exception as e:
        logger.warning(f"YOLO detection failed: {e}")
        return None


async def _identify_breeds_gemini(frame_bytes: bytes, gallinero_id: str = "") -> dict | None:
    """Envía frame a Gemini Vision para identificación de raza.

    Si hay censo de cabaña, inyecta contexto con las razas esperadas
    y el estado de asignación actual.
    """
    from services.gemini_vision import analyze_image

    # ── Construir prompt con contexto del censo ──
    prompt = BIRD_ID_PROMPT
    if gallinero_id:
        try:
            from services.flock_census import build_gemini_context
            import httpx
            # Obtener aves ya registradas en este gallinero
            async with httpx.AsyncClient(timeout=3.0, base_url="http://localhost:8000") as c:
                resp = await c.get("/birds/", params={"gallinero": gallinero_id})
                registered = resp.json().get("birds", []) if resp.status_code == 200 else []
            context = build_gemini_context(gallinero_id, registered)
            if context:
                prompt = context + "\n\n" + BIRD_ID_PROMPT
        except Exception as e:
            logger.debug(f"Census context build failed: {e}")

    try:
        b64 = base64.b64encode(frame_bytes).decode()
        result = await analyze_image(
            image_b64=b64,
            question=prompt,
            mime_type="image/jpeg",
            save_for_training=True,
        )
        # Parsear JSON de la respuesta
        answer = result.get("answer", "")
        # Extraer JSON del texto
        start = answer.find("{")
        end = answer.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(answer[start:end])
    except json.JSONDecodeError as e:
        logger.warning(f"Gemini response not valid JSON: {e}")
    except Exception as e:
        logger.warning(f"Vision analysis failed: {e}")
    return None


async def _identify_unknowns_with_together(
    frame_bytes: bytes,
    breed_result: list[dict],
    yolo_result: dict,
    gallinero_id: str,
) -> list[dict] | None:
    """Fallback Together.ai: identifica aves 'Desconocida' por crop individual.

    Usa Qwen2.5-VL-72B via Together.ai para las aves que YOLO breed
    no pudo clasificar y Gemini está rate-limited.
    """
    try:
        from services.together_vision import identify_bird
        from services.flock_census import get_census
    except ImportError:
        return None

    census_breeds = get_census(gallinero_id) if gallinero_id else []
    enriched = list(breed_result)  # copia
    identified_count = 0

    for i, bird in enumerate(enriched):
        if bird.get("breed") != "Desconocida":
            continue

        # Crop del ave usando bbox
        bbox = bird.get("bbox", [])
        if len(bbox) != 4:
            continue

        crop_result = _crop_bird_photo(frame_bytes, bbox)
        if not crop_result:
            continue

        crop_b64 = crop_result[0]
        try:
            result = await identify_bird(crop_b64, census_breeds)
            breed = result.get("breed", "desconocida")
            if breed.lower() not in ("desconocida", "unknown", ""):
                enriched[i] = {
                    **bird,
                    "breed": breed,
                    "color": result.get("color", bird.get("color", "")),
                    "sex": _map_sex(result.get("sex", "unknown")),
                    "confidence": result.get("confidence", 0.6),
                    "distinguishing_features": ", ".join(result.get("distinctive_features", [])),
                    "engine": "together_fallback",
                }
                identified_count += 1
                logger.info(f"🔍 Together fallback: ave {i+1} → {breed} ({result.get('confidence', 0):.0%})")
        except Exception as e:
            logger.warning(f"Together fallback failed for bird {i+1}: {e}")

    if identified_count > 0:
        logger.info(f"🔍 Together fallback: {identified_count} aves identificadas de {len(breed_result)} desconocidas")
        return enriched
    return None


# Máximo de aves para procesar un frame (1-5 = identificable)
_QUALITY_MAX_BIRDS = 5
# Mínimo de confianza para considerar un ave
_QUALITY_MIN_CONF = 0.40
# Mínimo área del frame que debe cubrir el ave
_QUALITY_MIN_AREA = 0.008  # 0.8%, relajado desde 1.5%
# Margen de borde
_QUALITY_BORDER_MARGIN = 0.02  # 2%, relajado desde 3%
# Mínimo de nitidez
_QUALITY_MIN_SHARPNESS = 30  # relajado desde 50


def _quality_gate(frame_bytes: bytes, yolo_result: dict) -> dict | None:
    """Quality gate: selecciona la MEJOR ave candidata del frame.

    Acepta frames con 1 a _QUALITY_MAX_BIRDS aves.
    Elige la mejor candidata por: tamaño (40%) + confianza (30%) + centrado (30%).

    Returns dict con métricas de calidad si pasa, None si no.
    """
    detections = yolo_result.get("detections", [])
    n_birds = len(detections)
    if n_birds == 0 or n_birds > _QUALITY_MAX_BIRDS:
        return None

    # Pre-carga imagen para sharpness (una vez)
    img = None
    ih, iw = 0, 0
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(frame_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        ih, iw = img.shape[:2]
    except Exception:
        pass

    best = None
    best_score = -1

    for det in detections:
        bbox = det.get("bbox_norm", [])
        conf = det.get("confidence", 0)

        if conf < _QUALITY_MIN_CONF:
            continue
        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        area = w * h

        if area < _QUALITY_MIN_AREA:
            continue

        # Borde: descartar si está cortada
        if x1 < _QUALITY_BORDER_MARGIN or y1 < _QUALITY_BORDER_MARGIN:
            continue
        if x2 > (1 - _QUALITY_BORDER_MARGIN) or y2 > (1 - _QUALITY_BORDER_MARGIN):
            continue

        # Sharpness
        sharpness = None
        if img is not None:
            try:
                import cv2
                crop = img[int(y1*ih):int(y2*ih), int(x1*iw):int(x2*iw)]
                if crop.size > 0:
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
                    if sharpness < _QUALITY_MIN_SHARPNESS:
                        continue
            except Exception:
                pass

        # Score: tamaño (40%) + confianza (30%) + centrado (30%)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        center_dist = ((cx - 0.5)**2 + (cy - 0.5)**2) ** 0.5
        center_score = max(0, 1 - center_dist / 0.7071)  # 0.7071 = esquina

        score = (
            0.40 * min(area / 0.10, 1.0)  # normalizar: 10% del frame = max
            + 0.30 * conf
            + 0.30 * center_score
        )

        if score > best_score:
            best_score = score
            best = {
                "detection": det,
                "bbox": bbox,
                "area": area,
                "confidence": conf,
                "sharpness": sharpness,
            }

    return best


async def _analyze_frame(frame_bytes: bytes, gallinero_id: str = "", *, imgsz: int | None = None, use_tiled: bool = False, force_gemini: bool = False) -> dict | None:
    """Análisis híbrido: YOLO COCO + Breed YOLO + fallback censo + Gemini.

    Pipeline:
      1) YOLO COCO: detección rápida (conteo + bboxes)
      2) Breed YOLO: clasifica raza de cada ave por crop
      3) Aves sin breed → fallback por censo (araucana, F1 por descarte)
      4) Gemini: solo si quedan aves sin identificar o force_gemini
    """
    # 1) YOLO COCO: detección local (~50ms)
    yolo_result = _detect_with_yolo(frame_bytes, imgsz=imgsz, use_tiled=use_tiled)
    yolo_count = yolo_result["count"] if yolo_result else 0

    if yolo_result:
        logger.info(
            f"[YOLO] {yolo_count} aves detectadas "
            f"({yolo_result['inference_ms']:.0f}ms, {yolo_result['model']})"
        )

    # 2) Guardar frame + etiquetas YOLO para entrenamiento
    if yolo_result and yolo_result["detections"]:
        try:
            from services.yolo_trainer import save_confirmed_detection
            save_confirmed_detection(
                frame_bytes, yolo_result["detections"], split="auto",
            )
        except Exception as e:
            logger.debug(f"Training data save failed: {e}")

    # 3) Breed YOLO: clasificar raza de cada ave por crop
    breed_result = None
    if yolo_count > 0:
        breed_result = _classify_breeds_yolo(frame_bytes, yolo_result)

    # 4) Si breed YOLO resolvió todas las aves → devolver sin Gemini
    if breed_result and not force_gemini:
        identified = [b for b in breed_result if b.get("breed") != "Desconocida"]
        # Intentar resolver las desconocidas por censo (araucana, F1)
        if len(identified) < len(breed_result) and gallinero_id:
            breed_result = _resolve_unknown_by_census(gallinero_id, breed_result)
            identified = [b for b in breed_result if b.get("breed") != "Desconocida"]

        if len(identified) == len(breed_result):
            logger.info(
                f"[Breed YOLO] Todas las aves identificadas sin Gemini: "
                f"{len(identified)} aves"
            )
            return {
                "birds": breed_result,
                "total_visible": yolo_count,
                "conditions": f"Breed YOLO ({yolo_result['inference_ms']:.0f}ms)",
                "engine": "yolo_breed",
            }

    # 5) Gemini: si quedan aves sin identificar, o force_gemini
    #    Rate limiter: en el identification loop, no llamar Gemini más de 1/5min
    if yolo_count > 0 or force_gemini:
        global _gemini_last_call
        now = time.time()
        gemini_available = force_gemini or (now - _gemini_last_call >= _GEMINI_LOOP_COOLDOWN)

        gemini_result = None
        if gemini_available:
            _gemini_last_call = now
            gemini_result = await _identify_breeds_gemini(frame_bytes, gallinero_id)
        if gemini_result:
            # Enriquecer con datos YOLO (bboxes más precisos)
            _merge_yolo_gemini(yolo_result, gemini_result)

            # Enriquecer Gemini con breed YOLO donde coincida
            if breed_result:
                _merge_breed_yolo_into_gemini(breed_result, gemini_result)

            # Validar contra censo: corregir razas que no existen en la cabaña
            if gallinero_id:
                _validate_breeds_against_census(gallinero_id, gemini_result)

            return gemini_result

    # 6) Together.ai fallback: cuando Gemini falla y hay aves desconocidas
    # Si no hay breed_result pero sí YOLO detections, construir una lista sintética
    if not breed_result and yolo_result and yolo_count > 0:
        breed_result = [
            {
                "breed": "Desconocida",
                "color": "",
                "sex": "unknown",
                "confidence": d["confidence"],
                "bbox": d["bbox_norm"],
            }
            for d in yolo_result["detections"]
        ]

    if breed_result and yolo_result:
        unknown_birds = [b for b in breed_result if b.get("breed") == "Desconocida"]
        if unknown_birds:
            together_enriched = await _identify_unknowns_with_together(
                frame_bytes, breed_result, yolo_result, gallinero_id
            )
            if together_enriched:
                breed_result = together_enriched

    # Sin aves detectadas por YOLO, o Gemini falló → devolver breed YOLO parcial o YOLO básico
    if breed_result:
        # Detectar engine apropiado
        engines = {b.get("engine", "yolo_breed") for b in breed_result}
        if "together_fallback" in engines:
            engine = "yolo_breed+together"
        else:
            engine = "yolo_breed_partial"
        return {
            "birds": breed_result,
            "total_visible": yolo_count,
            "conditions": f"{engine} ({yolo_result['inference_ms']:.0f}ms)" if yolo_result else engine,
            "engine": engine,
        }

    if yolo_result and yolo_count > 0:
        return {
            "birds": [
                {
                    "breed": "Desconocida",
                    "color": "",
                    "sex": "unknown",
                    "confidence": d["confidence"],
                    "bbox": d["bbox_norm"],
                    "distinguishing_features": "Detectado por YOLO, pendiente identificación de raza",
                }
                for d in yolo_result["detections"]
            ],
            "total_visible": yolo_count,
            "conditions": f"Detección YOLO ({yolo_result['inference_ms']:.0f}ms)",
            "yolo_only": True,
        }

    return None


def _merge_yolo_gemini(yolo_result: dict, gemini_result: dict):
    """Enriquece resultado de Gemini con bboxes más precisos de YOLO si los de Gemini son pobres."""
    gemini_birds = gemini_result.get("birds", [])
    yolo_dets = yolo_result.get("detections", []) if yolo_result else []

    if not yolo_dets or not gemini_birds:
        return

    # Si hay mismo número de aves, emparejar por posición (bbox overlap)
    if len(gemini_birds) == len(yolo_dets):
        for i, gb in enumerate(gemini_birds):
            gb_bbox = gb.get("bbox", [])
            # Si Gemini no dio bbox o dio uno dudoso, usar el de YOLO
            if not gb_bbox or len(gb_bbox) != 4 or all(v == 0 for v in gb_bbox):
                gb["bbox"] = yolo_dets[i]["bbox_norm"]
                gb["bbox_source"] = "yolo"


def _enrich_with_tracking(gallinero_id: str, frame_bytes: bytes):
    """Ejecuta tracker + pest alerts + health + behavior snapshots + mating en cada ciclo YOLO."""
    try:
        from services.yolo_detector import detect
        from services.bird_tracker import get_tracker
        from services.pest_alert import get_pest_manager
        from services.health_analyzer import get_growth_tracker
        from services.behavior_event_store import get_event_store
        from services.mating_detector import get_mating_detector

        result = detect(frame_bytes)
        if not result or not result.get("detections"):
            return

        # 1. Tracking: actualizar posiciones
        tracker = get_tracker(gallinero_id)
        tracker.update(result["detections"])

        # 1b. Breed classification periódica (cada 30s) sobre tracks sin breed
        #     v4.2: usa parse_breed_class para extraer breed+color+sex
        #           + VotingBuffer para tracks con breed pero sin lock
        try:
            _breed_last = getattr(_enrich_with_tracking, "_breed_last", {})
            now_bc = time.time()
            if now_bc - _breed_last.get(gallinero_id, 0) >= 30:
                _breed_last[gallinero_id] = now_bc
                _enrich_with_tracking._breed_last = _breed_last
                from services.yolo_detector import classify_breed_crop
                from services.identity.breed_parser import parse_breed_class, BREED_ALIASES
                from services.identity.identity_voting import IdentityVotingBuffer
                from PIL import Image

                # VotingBuffer singleton
                if not hasattr(_enrich_with_tracking, "_voting_buffers"):
                    _enrich_with_tracking._voting_buffers = {}
                voting_buffers = _enrich_with_tracking._voting_buffers
                if gallinero_id not in voting_buffers:
                    voting_buffers[gallinero_id] = IdentityVotingBuffer()
                voting = voting_buffers[gallinero_id]

                img = Image.open(io.BytesIO(frame_bytes))
                w, h = img.size
                # Classify tracks sin breed O tracks con breed pero sin lock
                need_classify = [
                    t for t in tracker.tracks.values()
                    if t.active and t.last_bbox_norm and len(t.last_bbox_norm) == 4
                    and (not t.breed or (t.breed and not t.identity_locked))
                ]
                classified = 0
                skipped_small = 0
                for t in need_classify:
                    bn = t.last_bbox_norm
                    x1 = max(0, int(bn[0] * w))
                    y1 = max(0, int(bn[1] * h))
                    x2 = min(w, int(bn[2] * w))
                    y2 = min(h, int(bn[3] * h))
                    cw, ch = x2 - x1, y2 - y1
                    if cw < 32 or ch < 32:
                        skipped_small += 1
                        continue
                    crop = img.crop((x1, y1, x2, y2))

                    # T2: upscale 2× para sub-streams pequeños (VIGI ≤800px)
                    if w <= 800 and cw < 96:
                        try:
                            import cv2
                            import numpy as np
                            crop_np = np.array(crop)
                            crop_np = cv2.resize(crop_np, None, fx=2, fy=2,
                                                 interpolation=cv2.INTER_CUBIC)
                            crop = Image.fromarray(crop_np)
                        except Exception:
                            pass

                    buf = io.BytesIO()
                    crop.save(buf, format="JPEG", quality=85)
                    res = classify_breed_crop(buf.getvalue(), confidence=0.25)
                    if res and res["confidence"] >= 0.30:
                        raw = res["breed_class"]
                        parsed = parse_breed_class(raw)

                        # Aplicar al track
                        if parsed["breed"]:
                            t.breed = parsed["breed"]
                        if parsed["sex"]:
                            t.sex = parsed["sex"]
                        if parsed["color"]:
                            t.color = parsed["color"]
                        t.breed_raw_class = raw

                        # Añadir voto al VotingBuffer
                        vote_result = voting.add_vote(
                            track_id=t.track_id,
                            breed=parsed["breed"],
                            color=parsed["color"],
                            sex=parsed["sex"],
                            confidence=res["confidence"],
                        )

                        # Si el voting confirma y el track no tiene lock, refrescar
                        if vote_result.confirmed and t.identity_locked and t.identity_lock:
                            t.identity_lock.refresh(vote_result.mean_confidence)

                        classified += 1
                    elif res:
                        logger.debug(
                            f"Breed low conf: {res['breed_class']} {res['confidence']:.2f} "
                            f"crop={cw}x{ch}"
                        )
                if need_classify:
                    logger.info(
                        f"[{gallinero_id}] Breed classify: {len(need_classify)} need classify, "
                        f"{classified} classified, {skipped_small} small, frame={w}x{h}"
                    )
        except Exception as e:
            logger.debug(f"Breed classification failed ({gallinero_id}): {e}")

        # 1c. Sync periódico: propagar ai_vision_id del registro → tracker (cada 60s)
        try:
            _sync_last = getattr(_enrich_with_tracking, "_sync_last", {})
            now_sync = time.time()
            if now_sync - _sync_last.get(gallinero_id, 0) >= 60:
                _sync_last[gallinero_id] = now_sync
                _enrich_with_tracking._sync_last = _sync_last
                import httpx
                import asyncio
                async def _do_sync():
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(
                            "http://localhost:8000/birds/",
                            params={"gallinero": "gallinero_palacio"},
                        )
                        if resp.status_code == 200:
                            registered = resp.json().get("birds", [])
                            if registered:
                                synced = tracker.sync_registered_ids(registered)
                                if synced:
                                    logger.info(
                                        f"[{gallinero_id}] Sync Re-ID: {synced} aves identificadas"
                                    )
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(_do_sync())
                except RuntimeError:
                    pass
        except Exception as e:
            logger.debug(f"Sync Re-ID failed ({gallinero_id}): {e}")

        # 2. Behavior event store: snapshot periódico (respeta intervalo interno)
        try:
            event_store = get_event_store()
            event_store.snapshot(gallinero_id, tracker)
        except Exception as e:
            logger.debug(f"Behavior snapshot failed ({gallinero_id}): {e}")

        # 3. Mating detection: detectar montas entre tracks activos
        try:
            mating = get_mating_detector(gallinero_id)
            mating_events = mating.process_frame(tracker)
            # Los eventos ya se logean y persisten dentro del detector
        except Exception as e:
            logger.debug(f"Mating detection failed ({gallinero_id}): {e}")

        # 4. Pest alerts
        if result.get("pest_count", 0) > 0:
            pest_mgr = get_pest_manager()
            alerts = pest_mgr.process_detections(gallinero_id, result)
            if alerts:
                logger.warning(
                    f"[{gallinero_id}] Pest alerts: "
                    f"{[a['pest_type'] for a in alerts]}"
                )

        # 5. Growth tracking (registrar tamaños)
        growth = get_growth_tracker()
        for t in tracker.tracks.values():
            if t.active and t.sizes:
                growth.record(t.track_id, t.sizes[-1])

        # 6. ML conductual: analizar anomalías en tiempo real
        try:
            import asyncio
            from services.behavior_ml import get_behavior_ml_engine
            ml_engine = get_behavior_ml_engine()
            for t in tracker.tracks.values():
                if not t.active or not t.ai_vision_id:
                    continue
                total_zone = max(sum(t.zone_time.values()), 1)
                snapshot = {
                    "bird_id": t.ai_vision_id,
                    "zone_nido_pct": t.zone_time.get("nido", 0) / total_zone,
                    "zone_comedero_pct": t.zone_time.get("comedero", 0) / total_zone,
                    "zone_bebedero_pct": t.zone_time.get("bebedero", 0) / total_zone,
                    "zone_aseladero_pct": t.zone_time.get("aseladero", 0) / total_zone,
                    "zone_libre_pct": t.zone_time.get("zona_libre", 0) / total_zone,
                    "avg_speed": 0.0,
                    "distance_moved": 0.0,
                    "social_proximity": 0,
                    "interactions_count": 0,
                    "ts": result.get("timestamp", ""),
                }
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(ml_engine.analyze_snapshot(gallinero_id, snapshot))
                except RuntimeError:
                    pass
        except Exception as e:
            logger.debug(f"ML analysis failed ({gallinero_id}): {e}")

    except Exception as e:
        logger.debug(f"Tracking enrichment failed ({gallinero_id}): {e}")


def _enrich_with_tracking_v2(gallinero_id: str, frame_bytes: bytes, detections: dict):
    """v4.2: Tracking + behavior reutilizando detecciones ya computadas.

    Elimina la doble inferencia YOLO: el CaptureManager ya ejecutó detect()
    y pasa el resultado directamente. Esto reduce la carga de CPU ~50%.
    """
    try:
        from services.bird_tracker import get_tracker
        from services.pest_alert import get_pest_manager
        from services.health_analyzer import get_growth_tracker
        from services.behavior_event_store import get_event_store
        from services.mating_detector import get_mating_detector

        result = detections
        if not result or not result.get("detections"):
            return

        # 1. Tracking: actualizar posiciones
        tracker = get_tracker(gallinero_id)
        tracker.update(result["detections"])

        # 1b. Breed classification periódica (cada 30s) sobre tracks sin breed
        try:
            _breed_last = getattr(_enrich_with_tracking_v2, "_breed_last", {})
            now_bc = time.time()
            if now_bc - _breed_last.get(gallinero_id, 0) >= 30:
                _breed_last[gallinero_id] = now_bc
                _enrich_with_tracking_v2._breed_last = _breed_last
                from services.yolo_detector import classify_breed_crop
                from services.identity.breed_parser import parse_breed_class
                from services.identity.identity_voting import IdentityVotingBuffer
                from PIL import Image

                if not hasattr(_enrich_with_tracking_v2, "_voting_buffers"):
                    _enrich_with_tracking_v2._voting_buffers = {}
                voting_buffers = _enrich_with_tracking_v2._voting_buffers
                if gallinero_id not in voting_buffers:
                    voting_buffers[gallinero_id] = IdentityVotingBuffer()
                voting = voting_buffers[gallinero_id]

                img = Image.open(io.BytesIO(frame_bytes))
                w, h = img.size
                need_classify = [
                    t for t in tracker.tracks.values()
                    if t.active and t.last_bbox_norm and len(t.last_bbox_norm) == 4
                    and (not t.breed or (t.breed and not t.identity_locked))
                ]
                classified = 0
                skipped_small = 0
                for t in need_classify:
                    bn = t.last_bbox_norm
                    x1 = max(0, int(bn[0] * w))
                    y1 = max(0, int(bn[1] * h))
                    x2 = min(w, int(bn[2] * w))
                    y2 = min(h, int(bn[3] * h))
                    cw, ch = x2 - x1, y2 - y1
                    if cw < 32 or ch < 32:
                        skipped_small += 1
                        continue
                    crop = img.crop((x1, y1, x2, y2))

                    # T2: upscale 2× para sub-streams pequeños (VIGI ≤800px)
                    if w <= 800 and cw < 96:
                        try:
                            import cv2
                            import numpy as np
                            crop_np = np.array(crop)
                            crop_np = cv2.resize(crop_np, None, fx=2, fy=2,
                                                 interpolation=cv2.INTER_CUBIC)
                            crop = Image.fromarray(crop_np)
                        except Exception:
                            pass

                    buf = io.BytesIO()
                    crop.save(buf, format="JPEG", quality=85)
                    res = classify_breed_crop(buf.getvalue(), confidence=0.25)
                    if res and res["confidence"] >= 0.30:
                        raw = res["breed_class"]
                        parsed = parse_breed_class(raw)

                        if parsed["breed"]:
                            t.breed = parsed["breed"]
                        if parsed["sex"]:
                            t.sex = parsed["sex"]
                        if parsed["color"]:
                            t.color = parsed["color"]
                        t.breed_raw_class = raw

                        vote_result = voting.add_vote(
                            track_id=t.track_id,
                            breed=parsed["breed"],
                            color=parsed["color"],
                            sex=parsed["sex"],
                            confidence=res["confidence"],
                        )

                        if vote_result.confirmed and t.identity_locked and t.identity_lock:
                            t.identity_lock.refresh(vote_result.mean_confidence)

                        classified += 1
                if need_classify:
                    logger.info(
                        f"[{gallinero_id}] Breed classify: {len(need_classify)} need classify, "
                        f"{classified} classified, {skipped_small} small, frame={w}x{h}"
                    )
        except Exception as e:
            logger.debug(f"Breed classification failed ({gallinero_id}): {e}")

        # 1c. Sync periódico (cada 60s)
        try:
            _sync_last = getattr(_enrich_with_tracking_v2, "_sync_last", {})
            now_sync = time.time()
            if now_sync - _sync_last.get(gallinero_id, 0) >= 60:
                _sync_last[gallinero_id] = now_sync
                _enrich_with_tracking_v2._sync_last = _sync_last
                import httpx as httpx_sync
                import asyncio
                async def _do_sync():
                    async with httpx_sync.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(
                            "http://localhost:8000/birds/",
                            params={"gallinero": "gallinero_palacio"},
                        )
                        if resp.status_code == 200:
                            registered = resp.json().get("birds", [])
                            if registered:
                                synced = tracker.sync_registered_ids(registered)
                                if synced:
                                    logger.info(
                                        f"[{gallinero_id}] Sync Re-ID: {synced} aves identificadas"
                                    )
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(_do_sync())
                except RuntimeError:
                    pass
        except Exception as e:
            logger.debug(f"Sync Re-ID failed ({gallinero_id}): {e}")

        # 2. Behavior event store
        try:
            event_store = get_event_store()
            event_store.snapshot(gallinero_id, tracker)
        except Exception as e:
            logger.debug(f"Behavior snapshot failed ({gallinero_id}): {e}")

        # 3. Mating detection
        try:
            mating = get_mating_detector(gallinero_id)
            mating.process_frame(tracker)
        except Exception as e:
            logger.debug(f"Mating detection failed ({gallinero_id}): {e}")

        # 4. Pest alerts
        if result.get("pest_count", 0) > 0:
            pest_mgr = get_pest_manager()
            alerts = pest_mgr.process_detections(gallinero_id, result)
            if alerts:
                logger.warning(
                    f"[{gallinero_id}] Pest alerts: "
                    f"{[a['pest_type'] for a in alerts]}"
                )

        # 5. Growth tracking
        growth = get_growth_tracker()
        for t in tracker.tracks.values():
            if t.active and t.sizes:
                growth.record(t.track_id, t.sizes[-1])

        # 6. ML conductual
        try:
            import asyncio
            from services.behavior_ml import get_behavior_ml_engine
            ml_engine = get_behavior_ml_engine()
            for t in tracker.tracks.values():
                if not t.active or not t.ai_vision_id:
                    continue
                total_zone = max(sum(t.zone_time.values()), 1)
                snapshot = {
                    "bird_id": t.ai_vision_id,
                    "zone_nido_pct": t.zone_time.get("nido", 0) / total_zone,
                    "zone_comedero_pct": t.zone_time.get("comedero", 0) / total_zone,
                    "zone_bebedero_pct": t.zone_time.get("bebedero", 0) / total_zone,
                    "zone_aseladero_pct": t.zone_time.get("aseladero", 0) / total_zone,
                    "zone_libre_pct": t.zone_time.get("zona_libre", 0) / total_zone,
                    "avg_speed": 0.0,
                    "distance_moved": 0.0,
                    "social_proximity": 0,
                    "interactions_count": 0,
                    "ts": result.get("timestamp", ""),
                }
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(ml_engine.analyze_snapshot(gallinero_id, snapshot))
                except RuntimeError:
                    pass
        except Exception as e:
            logger.debug(f"ML analysis failed ({gallinero_id}): {e}")

    except Exception as e:
        logger.debug(f"Tracking enrichment v2 failed ({gallinero_id}): {e}")


# Mapeo stream go2rtc → nombre gallinero en OvoSfera
_STREAM_TO_GALLINERO_NAME = {
    "gallinero_durrif_1": "Gallinero Durrif I",
    "gallinero_durrif_2": "Gallinero Durrif II",
    "sauna_durrif_1": "Gallinero Durrif I",
}


# Mapeo gallinero_stream → ID de gallinero en OvoSfera
_STREAM_TO_GALLINERO_ID = {
    "gallinero_durrif_1": 2,
    "gallinero_durrif_2": 3,
}


async def _sync_vision_id_to_ovosfera(
    vision_id: str, breed: str, color: str, sex: str,
    gallinero_stream: str, photo_b64: str | None = None,
):
    """Sincroniza ai_vision_id y foto a OvoSfera.

    Matching: breed (con aliases) + sex. Color como desempate.
    Foto: sube el crop como data URI si disponible.
    NOTA: NO cambia gallinero automáticamente — solo el usuario lo hace.
    """
    gallinero_name = _STREAM_TO_GALLINERO_NAME.get(gallinero_stream, "")
    sex_ovo = "M" if sex == "male" else "H"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
            if resp.status_code != 200:
                return
            aves = resp.json()

            # ¿Ya sincronizado? → solo upgradeear foto si falta
            existing = next((a for a in aves if a.get("ai_vision_id") == vision_id), None)
            if existing:
                if photo_b64 and not existing.get("foto"):
                    await client.put(
                        f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{existing['id']}",
                        json={"foto": f"data:image/jpeg;base64,{photo_b64}"},
                    )
                    logger.info(f"📸 Photo uploaded for {vision_id} → OvoSfera ave {existing['id']}")
                return

            # Buscar candidatas: match breed + sex, sin ai_vision_id
            candidates = [
                a for a in aves
                if _match_breed_ovosfera(breed, a.get("raza", ""))
                and a.get("sexo", "") == sex_ovo
                and not a.get("ai_vision_id")
            ]
            if not candidates:
                # Fallback: match por breed solo (sin filtro de sex)
                candidates = [
                    a for a in aves
                    if _match_breed_ovosfera(breed, a.get("raza", ""))
                    and not a.get("ai_vision_id")
                ]

            if not candidates:
                logger.debug(f"No unassigned OvoSfera ave for breed={breed} sex={sex_ovo}")
                return

            # Preferir las que coincidan en color
            color_match = [
                a for a in candidates
                if _match_color_ovosfera(color, a.get("color", ""))
            ]
            ave = color_match[0] if color_match else candidates[0]

            update_payload = {"ai_vision_id": vision_id}
            # No asignar gallinero automáticamente
            if photo_b64:
                update_payload["foto"] = f"data:image/jpeg;base64,{photo_b64}"

            await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave['id']}",
                json=update_payload,
            )
            logger.info(
                f"✅ Synced '{vision_id}' → OvoSfera ave {ave['id']} "
                f"({ave.get('anilla','')}) raza={ave.get('raza')} "
                f"foto={'SI' if photo_b64 else 'NO'}"
            )
    except Exception as e:
        logger.debug(f"OvoSfera sync failed: {e}")


async def _sync_photo_to_ovosfera(vision_id: str, photo_b64: str):
    """Sube/actualiza foto de un ave ya sincronizada en OvoSfera."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
            if resp.status_code != 200:
                return
            aves = resp.json()
            ave = next((a for a in aves if a.get("ai_vision_id") == vision_id), None)
            if not ave:
                return
            await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave['id']}",
                json={"foto": f"data:image/jpeg;base64,{photo_b64}"},
            )
            logger.info(f"📸 Photo upgraded: {vision_id} → OvoSfera ave {ave['id']}")
    except Exception as e:
        logger.debug(f"Photo sync failed: {e}")


async def _register_or_update_birds(detected: list[dict], gallinero: str, frame_bytes: bytes | None):
    """Registra aves nuevas respetando el censo de la cabaña.

    Flujo:
    1. Normalizar breed/color al censo si coincide (evitar "Marrans" vs "Marans")
    2. Respetar cuotas: si el censo dice 5 Sussex blancas, nunca registrar más de 5
    3. Crop individual de cada ave (usando bbox de Gemini/YOLO)
    4. Sincronizar con OvoSfera (ai_vision_id, gallinero, foto)
    """
    import httpx
    from collections import Counter

    # Contar cuántas aves de cada (breed, color, sex) ha detectado Gemini
    seen_counts: Counter[tuple[str, str, str]] = Counter()
    bird_bboxes: dict[tuple[str, str, str], list] = {}  # acumular bboxes por grupo
    bird_confs: dict[tuple[str, str, str], list] = {}   # confianza por grupo
    for bird in detected:
        breed = bird.get("breed", "Desconocida")
        color = bird.get("color", "")
        sex = bird.get("sex", "unknown")
        confidence = bird.get("confidence", 0.0)
        if breed == "Desconocida" or confidence < 0.4:
            continue
        # Normalizar breed/color al censo
        breed, color, sex = _normalize_to_census(gallinero, breed, color, sex)
        key = (breed, color, sex)
        seen_counts[key] += 1
        if key not in bird_bboxes:
            bird_bboxes[key] = []
            bird_confs[key] = []
        bird_bboxes[key].append(bird.get("bbox", []))
        bird_confs[key].append(confidence)

    try:
        async with httpx.AsyncClient(timeout=5.0, base_url="http://localhost:8000") as client:
            for (breed, color, sex), seen_n in seen_counts.items():
                # Cuota del censo (0 = ilimitado / no en censo)
                from services.flock_census import get_quota
                quota = get_quota(gallinero, breed, color, sex)

                # ¿Cuántas de esta (breed+color) ya tenemos en este gallinero?
                resp = await client.get("/birds/", params={
                    "gallinero": gallinero, "breed": breed, "color": color,
                })
                existing = resp.json().get("birds", []) if resp.status_code == 200 else []
                have_n = len(existing)

                bboxes = bird_bboxes.get((breed, color, sex), [])
                confs = bird_confs.get((breed, color, sex), [])

                # Actualizar sighting de las que ya tenemos + upgrade foto
                for idx, bird_rec in enumerate(existing):
                    best_conf = max(confs) if confs else 0.5
                    stored_conf = bird_rec.get("confidence", 0)

                    # Intentar mejorar foto solo con alta confianza
                    crop_upgrade = None
                    if best_conf > stored_conf and best_conf >= 0.85 and frame_bytes:
                        for bbox in bboxes:
                            if len(bbox) == 4:
                                crop_result = _crop_bird_photo(frame_bytes, bbox, expected_breed=breed)
                                if crop_result:
                                    crop_upgrade = crop_result[0]
                                    break

                    await client.post(
                        f"/birds/{bird_rec['bird_id']}/sighting",
                        params={"confidence": best_conf},
                    )

                    # Sync foto mejorada a OvoSfera
                    if crop_upgrade and bird_rec.get("ai_vision_id"):
                        await _sync_photo_to_ovosfera(bird_rec["ai_vision_id"], crop_upgrade)

                # Cuántas nuevas registrar — respetando cuota
                new_count = max(0, seen_n - have_n)
                if quota > 0:
                    new_count = min(new_count, max(0, quota - have_n))
                else:
                    # quota=0 → raza/gallinero no en censo, no registrar nuevas
                    new_count = 0

                for i in range(new_count):
                    # Crop individual si tenemos bbox
                    crop_b64 = None
                    bbox_idx = have_n + i  # index into the group's bboxes
                    if frame_bytes and bbox_idx < len(bboxes) and len(bboxes[bbox_idx]) == 4:
                        crop_result = _crop_bird_photo(frame_bytes, bboxes[bbox_idx], expected_breed=breed)
                        if crop_result:
                            crop_b64 = crop_result[0]

                    # Sin crop de calidad → no registrar foto (evitar thumbnails del frame completo)
                    if not crop_b64:
                        logger.debug(f"Skip photo for {breed}: no quality crop available")

                    reg_resp = await client.post("/birds/register", json={
                        "breed": breed,
                        "color": color,
                        "sex": sex,
                        "gallinero": gallinero,
                        "confidence": 0.7,
                        "photo_b64": crop_b64,
                    })
                    if reg_resp.status_code == 200:
                        reg_data = reg_resp.json()
                        vision_id = reg_data.get("ai_vision_id", "")
                        logger.info(
                            f"🐔 New bird: {breed} {color} {sex} → {vision_id} "
                            f"in {gallinero} ({have_n + i + 1}/{quota or '∞'})"
                        )
                        if vision_id:
                            await _sync_vision_id_to_ovosfera(
                                vision_id, breed, color, sex,
                                gallinero, crop_b64,
                            )

                if new_count == 0 and existing:
                    logger.debug(
                        f"Sighting update: {breed} {color} ×{seen_n} "
                        f"(have {have_n}/{quota or '∞'}) in {gallinero}"
                    )
    except Exception as e:
        logger.warning(f"Bird register/update failed: {e}")


async def _identification_loop():
    """Loop principal: captura calidad-primero de aves individuales.

    Estrategia calidad-primero:
    - Solo procesa frames donde YOLO detecta EXACTAMENTE 1 ave aislada
    - Verifica calidad: tamaño en frame, nitidez, no truncada en bordes
    - Pipeline de identificación: Breed YOLO → Gemini → Together
    - NUNCA cambia gallineros automáticamente
    - Intervalo pausado (60s) para capturas deliberadas
    """
    global _running, _last_results, _night_logged
    _running = True
    INTERVAL = 60  # segundos entre capturas por cámara

    logger.info("🐔 Identification loop started (quality-first, single-bird)")

    while _running:
        for gallinero_id, cam_config in CAMERAS.items():
            if not _running:
                break

            cam_imgsz = cam_config.get("yolo_imgsz")
            use_tiled = cam_config.get("use_tiled", False)

            # Captura frame (siempre main stream para máxima resolución)
            snap_url = cam_config.get("snapshot_url", "")
            snap_auth = tuple(cam_config.get("snapshot_auth", ("admin", "123456")))
            frame = await _capture_frame(
                cam_config["stream"],
                snapshot_url=snap_url,
                snapshot_auth=snap_auth,
            )
            if not frame:
                continue

            # ── Brightness check: skip dark frames (night) ──
            try:
                from PIL import Image, ImageStat
                _img = Image.open(io.BytesIO(frame))
                _brightness = ImageStat.Stat(_img.convert("L")).mean[0]
                if _brightness < MIN_BRIGHTNESS:
                    if not _night_logged:
                        logger.info(f"🌙 Poca luz ({_brightness:.0f}/255) — pausando hasta amanecer")
                        _night_logged = True
                    continue
                elif _night_logged:
                    logger.info(f"☀️ Luz detectada ({_brightness:.0f}/255) — reanudando")
                    _night_logged = False
            except Exception:
                pass

            # ── YOLO detection ──
            yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled)
            if not yolo_result:
                continue

            yolo_count = yolo_result["count"]

            # Guardar training data siempre (independiente de calidad)
            if yolo_result["detections"]:
                try:
                    from services.yolo_trainer import save_confirmed_detection
                    save_confirmed_detection(frame, yolo_result["detections"], split="auto")
                except Exception:
                    pass

            # Tracking + pest alerts (siempre)
            _enrich_with_tracking(gallinero_id, frame)

            # ── QUALITY GATE: selecciona la mejor ave candidata ──
            quality = _quality_gate(frame, yolo_result)
            if not quality:
                reason = (
                    f"{yolo_count} aves (máx {_QUALITY_MAX_BIRDS})"
                    if yolo_count > _QUALITY_MAX_BIRDS or yolo_count == 0
                    else "calidad insuficiente (conf/tamaño/borde/nitidez)"
                )
                _last_results[gallinero_id] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "analysis": {
                        "total_visible": yolo_count,
                        "birds": [],
                        "yolo_only": True,
                        "conditions": f"Skipped: {reason}",
                    },
                    "camera": cam_config["name"],
                    "quality_skip": True,
                    "skip_reason": reason,
                }
                logger.info(
                    f"[{cam_config['name']}] ⏭️ Skip: {reason} "
                    f"({yolo_result['inference_ms']:.0f}ms)"
                )
                continue

            # ── QUALITY PASSED: pipeline completo de identificación ──
            sharp_str = f", sharp={quality['sharpness']:.0f}" if quality.get('sharpness') else ""
            logger.info(
                f"[{cam_config['name']}] ✅ Quality OK: mejor de {yolo_count} aves "
                f"(conf={quality['confidence']:.0%}, area={quality['area']:.1%}{sharp_str})"
            )

            analysis = await _analyze_frame(
                frame, gallinero_id,
                imgsz=cam_imgsz,
                use_tiled=use_tiled,
            )
            if not analysis:
                continue

            _last_results[gallinero_id] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis": analysis,
                "camera": cam_config["name"],
                "quality_pass": True,
            }

            # Registrar/actualizar el ave identificada
            detected_birds = analysis.get("birds", [])
            if detected_birds:
                await _register_or_update_birds(detected_birds, gallinero_id, frame)
                bird = detected_birds[0]
                logger.info(
                    f"[{cam_config['name']}] ✅ Identified: {bird.get('breed', '?')} "
                    f"{bird.get('color', '')} {bird.get('sex', '')} "
                    f"(engine={analysis.get('engine', '?')})"
                )

                # ── Curación automática de crops para fine-tune ──
                try:
                    from services.crop_curator import get_crop_curator
                    curator = get_crop_curator()
                    for b in detected_birds:
                        if b.get("breed") and b["breed"] != "Desconocida":
                            await curator.evaluate_and_save(
                                frame_bytes=frame,
                                bird_result=b,
                                camera_id=cam_config["name"],
                                gallinero_id=gallinero_id,
                                trigger_event="identification_loop",
                            )
                except Exception as e:
                    logger.debug(f"Crop curation skip: {e}")

        await asyncio.sleep(INTERVAL)

    logger.info("🐔 Identification loop stopped")


# ── Funciones helper para auto-start desde main.py ──

def start_loop():
    """Inicia el loop (llamable desde lifespan sin await)."""
    global _task, _running
    if _running and _task and not _task.done():
        return
    _task = asyncio.create_task(_identification_loop())


def stop_loop():
    """Detiene el loop (llamable desde lifespan)."""
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        _task = None


# ── Endpoints ──

@router.post("/start")
async def start_identification():
    """Inicia el loop de identificación de aves."""
    global _task, _running
    if _running and _task and not _task.done():
        return {"status": "already_running"}
    _task = asyncio.create_task(_identification_loop())
    return {"status": "started"}


@router.post("/stop")
async def stop_identification():
    """Detiene el loop de identificación."""
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        _task = None
    return {"status": "stopped"}


@router.get("/status")
async def identification_status():
    """Estado actual del identificador + salud de cámaras."""
    from services.capture_manager import get_capture_manager
    
    capture_mgr = get_capture_manager()
    return capture_mgr.get_status_with_health()


@router.get("/doubts")
async def get_identity_doubts(
    gallinero: str = "gallinero_palacio",
    hours: int = 24,
):
    """v4.2: Devuelve tracks con identidad dudosa para revisión manual."""
    try:
        from services.identity.doubt_escalator import get_doubt_escalator
        escalator = get_doubt_escalator(gallinero)
        doubts = escalator.query_recent(hours=hours)
        return {"gallinero": gallinero, "hours": hours, "doubts": doubts, "count": len(doubts)}
    except ImportError:
        return {"error": "Identity subsystem not available", "doubts": []}


@router.get("/tracks/live")
async def get_live_tracks(gallinero: str = "gallinero_palacio"):
    """v4.2: Estado en tiempo real de tracks con su identidad."""
    try:
        from services.bird_tracker import get_tracker
        tracker = get_tracker(gallinero)
        tracks = []
        for t in tracker.tracks.values():
            if not t.active:
                continue
            lock_info = None
            if t.identity_lock:
                lock_info = {
                    "confidence": round(t.identity_lock.confidence, 3),
                    "reason": t.identity_lock.reason,
                    "locked_at": t.identity_lock.locked_at,
                }
            tracks.append({
                "track_id": t.track_id,
                "breed": t.breed,
                "sex": t.sex,
                "color": t.color,
                "ai_vision_id": t.ai_vision_id,
                "identity_locked": t.identity_locked,
                "lock_info": lock_info,
                "total_frames": t.total_frames,
                "last_seen": t.last_seen,
            })

        # También obtener dudas recientes
        doubts = []
        try:
            from services.identity.doubt_escalator import get_doubt_escalator
            escalator = get_doubt_escalator(gallinero)
            doubts = escalator.query_recent(hours=1)
        except ImportError:
            pass

        return {
            "gallinero": gallinero,
            "tracks": tracks,
            "doubts": doubts,
            "active_count": len(tracks),
        }
    except ImportError:
        return {"error": "Tracker not available", "tracks": []}


@router.get("/identity/registry")
async def get_identity_registry(gallinero: str = "gallinero_palacio"):
    """v4.2: Estado del AssignmentRegistry — qué ai_vision_ids están asignados."""
    try:
        from services.identity.identity_lock import get_registry
        registry = get_registry(gallinero)
        return {"gallinero": gallinero, **registry.get_summary()}
    except ImportError:
        return {"error": "Identity subsystem not available"}


@router.post("/snapshot/{gallinero_id}")
async def snapshot_identify(gallinero_id: str):
    """Captura un frame ahora y lo analiza (one-shot)."""
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    frame = await _capture_from_cam(cam, force_hires=True)
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    analysis = await _analyze_frame(
        frame,
        gallinero_id,
        imgsz=cam.get("yolo_imgsz"),
        use_tiled=cam.get("use_tiled", False),
        force_gemini=is_distant,
    )
    if not analysis:
        raise HTTPException(503, "Gemini no pudo analizar la imagen")

    # Registrar aves detectadas (comparación por conteo)
    await _register_or_update_birds(analysis.get("birds", []), gallinero_id, frame)

    n_birds = len(analysis.get("birds", []))
    if log_agent_run:
        log_agent_run(
            task_type="reid",
            expert_used="expert_vision",
            model_used="together:qwen3-vl-8b",
            tools_invoked=["yolo_detect", "reid_identify"],
            input_summary=f"snapshot cam={gallinero_id}",
            output_summary=f"{n_birds} aves identificadas",
            confidence=max((b.get("confidence", 0) for b in analysis.get("birds", [])), default=0.0),
        )

    return {
        "gallinero": gallinero_id,
        "camera": cam["name"],
        "analysis": analysis,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Colores para bboxes (palette tipo Roboflow) ──
_BBOX_COLORS = [
    (255, 76, 76),   # rojo
    (76, 175, 255),  # azul
    (76, 255, 76),   # verde
    (255, 200, 50),  # amarillo
    (200, 76, 255),  # morado
    (255, 150, 50),  # naranja
    (50, 255, 200),  # turquesa
    (255, 100, 200), # rosa
    (150, 255, 50),  # lima
    (100, 200, 255), # celeste
]


def _draw_annotations(frame_bytes: bytes, birds: list[dict], gallinero_id: str) -> bytes:
    """Dibuja bounding boxes + etiquetas estilo Roboflow sobre el frame."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(frame_bytes))
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Fuente: intentar una monospace grande, fallback a default
    font_size = max(16, min(W, H) // 40)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    # Contar por breed+color para numerar: "Sussex bl #1", "Sussex bl #2"...
    breed_color_count: dict[str, int] = {}

    for i, bird in enumerate(birds):
        breed = bird.get("breed", "?")
        color = bird.get("color", "")
        sex = bird.get("sex", "")
        conf = bird.get("confidence", 0)
        bbox = bird.get("bbox", [])

        # Numerar por grupo
        key = f"{breed}|{color}".lower()
        breed_color_count[key] = breed_color_count.get(key, 0) + 1
        seq = breed_color_count[key]

        # Generar etiqueta estilo vision_id
        breed_low = breed.strip().lower()
        color_low = color.strip().lower()
        breed_slug = _BREED_ABBREV.get(breed_low, breed_low.replace(" ", "")[:8])
        color_slug = _COLOR_ABBREV.get(color_low, color_low.split()[0][:4] if color_low else "")
        label = f"{breed_slug}{color_slug}{seq}"
        sex_icon = "♂" if sex == "male" else ("♀" if sex == "female" else "")
        if sex_icon:
            label = f"{label} {sex_icon}"
        label = f"{label}  {conf:.0%}"

        box_color = _BBOX_COLORS[i % len(_BBOX_COLORS)]
        line_w = max(2, min(W, H) // 300)

        if bbox and len(bbox) == 4:
            x1 = int(bbox[0] * W)
            y1 = int(bbox[1] * H)
            x2 = int(bbox[2] * W)
            y2 = int(bbox[3] * H)
        else:
            # Sin bbox → distribuir en cuadrícula
            cols = 3
            col = i % cols
            row = i // cols
            cell_w = W // cols
            cell_h = H // max(1, (len(birds) + cols - 1) // cols)
            x1 = col * cell_w + 10
            y1 = row * cell_h + 10
            x2 = x1 + cell_w - 20
            y2 = y1 + cell_h - 20

        # Dibujar rectángulo
        draw.rectangle([x1, y1, x2, y2], outline=box_color, width=line_w)

        # Fondo de la etiqueta
        text_bbox = draw.textbbox((0, 0), label, font=font)
        tw = text_bbox[2] - text_bbox[0] + 10
        th = text_bbox[3] - text_bbox[1] + 6
        label_y = max(0, y1 - th - 2)
        draw.rectangle([x1, label_y, x1 + tw, label_y + th], fill=box_color)
        draw.text((x1 + 5, label_y + 2), label, fill=(255, 255, 255), font=font)

    # Marca de agua
    wm = f"Seedy Vision · {gallinero_id} · {len(birds)} aves"
    draw.text((10, H - font_size - 8), wm, fill=(200, 200, 200, 180), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


@router.post("/snapshot/{gallinero_id}/annotated")
async def snapshot_annotated(gallinero_id: str):
    """Captura + analiza + devuelve JPEG anotado con bboxes estilo Roboflow."""
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    frame = await _capture_from_cam(cam, force_hires=True)
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    cam_imgsz = cam.get("yolo_imgsz")
    use_tiled = cam.get("use_tiled", False)

    analysis = await _analyze_frame(
        frame, gallinero_id,
        imgsz=cam_imgsz,
        use_tiled=use_tiled,
        force_gemini=is_distant,
    )
    if not analysis:
        # Sin aves detectadas → devolver frame limpio con watermark
        return Response(
            content=frame,
            media_type="image/jpeg",
            headers={"X-Birds-Detected": "0", "X-Engine": "none"},
        )

    birds = analysis.get("birds", [])

    # Registrar nuevas aves
    await _register_or_update_birds(birds, gallinero_id, frame)

    # Dibujar anotaciones
    annotated = _draw_annotations(frame, birds, gallinero_id)

    return Response(
        content=annotated,
        media_type="image/jpeg",
        headers={
            "X-Birds-Detected": str(len(birds)),
            "X-Total-Visible": str(analysis.get("total_visible", 0)),
            "X-Conditions": analysis.get("conditions", ""),
            "X-Engine": "yolo+gemini" if not analysis.get("yolo_only") else "yolo",
        },
    )


@router.get("/snapshot/{gallinero_id}/yolo")
async def snapshot_yolo_only(gallinero_id: str):
    """Captura + YOLO rápido (~50ms) → JPEG con bboxes. Sin Gemini, rápido para live."""
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    cam_imgsz = cam.get("yolo_imgsz")
    use_tiled = cam.get("use_tiled", False)

    # Siempre hires para YOLO — CGI es 704x576, inservible para detección
    frame = await _capture_from_cam(cam, force_hires=True)
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled)
    if not yolo_result or not yolo_result["detections"]:
        return Response(content=frame, media_type="image/jpeg",
                        headers={"X-Birds-Detected": "0", "X-Engine": "yolo"})

    from services.yolo_detector import draw_detections
    annotated = draw_detections(frame, yolo_result["detections"], cam["name"])
    return Response(
        content=annotated,
        media_type="image/jpeg",
        headers={
            "X-Birds-Detected": str(yolo_result["count"]),
            "X-Inference-Ms": f"{yolo_result['inference_ms']:.0f}",
            "X-Engine": "yolo",
        },
    )


# ── Helpers para identificación manual ──

async def _get_gallinero_aves(gallinero_id: str) -> list[dict]:
    """Obtiene las aves de OvoSfera asignadas a este gallinero."""
    # Mapear cámaras que ven el mismo gallinero
    _CAMERA_TO_GALLINERO = {
        "sauna_durrif_1": "gallinero_durrif_1",  # sauna ve G1 y G2
    }
    census_key = _CAMERA_TO_GALLINERO.get(gallinero_id, gallinero_id)

    try:
        from services.flock_census import _load, _census
        _load()
        gal_info = _census.get(census_key, {})
        ovo_gallinero_id = gal_info.get("ovosfera_id")
    except Exception:
        ovo_gallinero_id = None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
            if resp.status_code != 200:
                return []
            all_aves = resp.json()
            if not isinstance(all_aves, list):
                all_aves = all_aves.get("aves", [])
    except Exception:
        return []

    # Resolver nombre legible del gallinero en OvoSfera
    # OvoSfera devuelve "Gallinero Durrif II" (string), no ID numérico
    _GAL_NAME_MAP = {
        "gallinero_durrif_1": "Gallinero Durrif I",
        "gallinero_durrif_2": "Gallinero Durrif II",
    }
    ovo_gal_name = _GAL_NAME_MAP.get(census_key)

    # Filtrar por gallinero (sin_asignar también pueden estar aquí)
    result = []
    for ave in all_aves:
        ave_gal = ave.get("gallinero")  # string name or None/"(sin asignar)"
        if ave_gal == ovo_gal_name:
            result.append(ave)
        elif not ave_gal or ave_gal == "(sin asignar)":
            result.append(ave)
        elif ovo_gallinero_id is not None and ave_gal == ovo_gallinero_id:
            result.append(ave)  # fallback numérico
    return result


def _suggest_aves_for_detection(
    breed_guess: str, color: str, sex: str, known_aves: list[dict]
) -> list[dict]:
    """Sugiere qué aves de OvoSfera podrían ser esta detección, ordenadas por probabilidad."""
    if not known_aves:
        return []

    clean_breed = breed_guess.rstrip("?").strip().lower()
    is_uncertain = breed_guess.endswith("?") or clean_breed == "desconocida"

    scored = []
    for ave in known_aves:
        score = 0
        ave_breed = (ave.get("raza") or "").lower()
        ave_color = (ave.get("color") or "").lower()
        ave_sex = (ave.get("sexo") or "").upper()

        # Breed match (con aliases)
        if clean_breed and clean_breed != "desconocida":
            if _match_breed_ovosfera(clean_breed, ave_breed):
                score += 50
            elif not is_uncertain:
                score -= 20  # penalizar si YOLO dice otra raza

        # Color match
        if color and ave_color:
            if _match_color_ovosfera(color.lower(), ave_color):
                score += 20

        # Sex match
        sex_map = {"male": "M", "female": "H", "M": "M", "H": "H"}
        if sex and ave_sex:
            if sex_map.get(sex, sex.upper()) == ave_sex:
                score += 15
            else:
                score -= 10

        # Bonus si no tiene foto (priorizar sin identificar)
        if not ave.get("foto"):
            score += 10
        if not ave.get("ai_vision_id"):
            score += 5

        scored.append({
            "id": ave.get("id"),
            "anilla": ave.get("anilla", ""),
            "raza": ave.get("raza", ""),
            "color": ave.get("color", ""),
            "sexo": ave.get("sexo", ""),
            "has_photo": bool(ave.get("foto")),
            "ai_vision_id": ave.get("ai_vision_id", ""),
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:8]


@router.get("/snapshot/{gallinero_id}/detect")
async def snapshot_detect(gallinero_id: str):
    """Captura + YOLO → JSON con frame base64 + detections + breed crops.

    Para el modo de identificación manual: el frontend muestra las cajas
    y el usuario asigna cada detección a un PAL.
    """
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    cam_imgsz = cam.get("yolo_imgsz")
    use_tiled = cam.get("use_tiled", False)

    # Siempre hires para detección — CGI es 704x576, inservible
    frame = await _capture_from_cam(cam, force_hires=True)
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled)

    # Obtener aves conocidas de OvoSfera para este gallinero (match asistido)
    known_aves = await _get_gallinero_aves(gallinero_id)
    # Censo de razas esperadas
    try:
        from services.flock_census import get_expected_breeds
        census = get_expected_breeds(gallinero_id)
    except Exception:
        census = []

    detections = []
    if yolo_result and yolo_result["detections"]:
        # Intentar classify breed en cada crop
        breed_results = _classify_breeds_yolo(frame, yolo_result)

        for i, det in enumerate(yolo_result["detections"]):
            bbox = det.get("bbox_norm", [])
            breed_info = breed_results[i] if breed_results and i < len(breed_results) else None

            breed_guess = breed_info.get("breed", "Desconocida") if breed_info else "Desconocida"
            breed_conf = breed_info.get("confidence", 0) if breed_info else 0
            breed_color = breed_info.get("color", "") if breed_info else ""
            breed_sex = breed_info.get("sex", "unknown") if breed_info else "unknown"

            # Census-aware correction: si YOLO dice una raza que NO está en este
            # gallinero, marcar como "Desconocida" para que el usuario corrija
            if breed_guess != "Desconocida" and census:
                raza_en_censo = any(
                    e["raza"].lower() == breed_guess.lower() for e in census
                )
                if not raza_en_censo:
                    breed_guess = f"{breed_guess}?"  # marcar con ? como dudosa

            # Crop para preview
            crop_b64 = None
            if len(bbox) == 4:
                crop_result = _crop_bird_photo(frame, bbox, padding=0.20)
                if crop_result:
                    crop_b64 = crop_result[0]

            # Buscar posibles matches entre aves conocidas del gallinero
            suggested_aves = _suggest_aves_for_detection(
                breed_guess, breed_color, breed_sex, known_aves
            )

            detections.append({
                "index": i,
                "bbox": bbox,
                "confidence": det.get("confidence", 0),
                "breed_guess": breed_guess,
                "breed_confidence": breed_conf,
                "breed_color": breed_color,
                "breed_sex": breed_sex,
                "crop_b64": crop_b64,
                "suggested_aves": suggested_aves,
            })

    frame_b64 = base64.b64encode(frame).decode()

    return {
        "gallinero": gallinero_id,
        "camera": cam["name"],
        "frame_b64": frame_b64,
        "detections": detections,
        "count": len(detections),
        "inference_ms": yolo_result["inference_ms"] if yolo_result else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/manual-assign")
async def manual_assign(body: dict):
    """Asigna manualmente una detección YOLO a un ave de OvoSfera.

    Body:
        ove_ave_id: int   — ID del ave en OvoSfera (ej: 1 para PAL-2026-0001)
        crop_b64: str     — Foto crop del ave (base64 JPEG)
        breed: str        — Raza identificada por el usuario
        color: str        — Color
        sex: str          — "M" o "H"
        gallinero: str    — Stream ID (para referencia)
    """
    ove_ave_id = body.get("ove_ave_id")
    crop_b64 = body.get("crop_b64", "")
    breed = body.get("breed", "")
    color = body.get("color", "")
    sex = body.get("sex", "")

    if not ove_ave_id:
        raise HTTPException(400, "ove_ave_id requerido")

    update_data = {}

    # Generar ai_vision_id
    if breed and breed.lower() not in ("desconocida", "unknown", ""):
        vision_id = _build_vision_id(breed, color, ove_ave_id)
        update_data["ai_vision_id"] = vision_id

    # Subir foto crop
    if crop_b64:
        if not crop_b64.startswith("data:"):
            crop_b64 = f"data:image/jpeg;base64,{crop_b64}"
        update_data["foto"] = crop_b64

    if not update_data:
        raise HTTPException(400, "Nada que actualizar")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}",
                json=update_data,
            )
            if resp.status_code != 200:
                raise HTTPException(502, f"OvoSfera error: {resp.status_code}")
            ave = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"OvoSfera error: {e}")

    logger.info(
        f"🏷️ Manual assign: ave {ove_ave_id} ({ave.get('anilla', '')}) "
        f"→ {breed} {color} {sex} (foto={'SI' if crop_b64 else 'NO'})"
    )

    # Guardar para dataset de entrenamiento
    try:
        from pathlib import Path
        import json as jsonmod
        train_dir = Path("/app/data/vision_training")
        train_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ave_id": ove_ave_id,
            "action": "manual_assign",
            "breed": breed,
            "color": color,
            "sex": sex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(train_dir / "confirmations.jsonl", "a") as f:
            f.write(jsonmod.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Guardar crop en galería local (acumula fotos para re-entrenar YOLO breed)
    _save_crop_to_gallery(ove_ave_id, crop_b64, breed, color, sex)

    return {
        "status": "assigned",
        "ave_id": ove_ave_id,
        "anilla": ave.get("anilla", ""),
        "ai_vision_id": update_data.get("ai_vision_id", ""),
        "updated_fields": list(update_data.keys()),
    }


@router.post("/smart-match")
async def smart_match(body: dict):
    """Identificación inteligente de un crop usando Together.ai Vision + galería de referencia.

    Body:
        crop_b64: str         — Foto crop del ave a identificar (base64 JPEG)
        gallinero_id: str     — ID del gallinero (para censo + aves conocidas)
        breed_hint: str       — Pista de raza de YOLO (opcional)
    """
    crop_b64 = body.get("crop_b64", "")
    gallinero_id = body.get("gallinero_id", "")
    breed_hint = body.get("breed_hint", "")

    if not crop_b64:
        raise HTTPException(400, "crop_b64 requerido")

    known_aves = await _get_gallinero_aves(gallinero_id) if gallinero_id else []

    result = await _visual_reidentify(
        crop_b64, known_aves,
        breed_hint=breed_hint,
        color_hint=body.get("color_hint", ""),
        sex_hint=body.get("sex_hint", ""),
    )

    if result.get("error"):
        raise HTTPException(502, result["error"])
    return result


@router.post("/auto-identify")
async def auto_identify(body: dict):
    """Identifica automáticamente TODAS las detecciones de un frame usando la galería de fotos.

    Body:
        gallinero_id: str  — ID del gallinero / stream name
    Captura un frame, detecta con YOLO, y para cada ave pide a Together.ai que la identifique
    comparándola visualmente con la galería de fotos acumuladas.
    """
    gallinero_id = body.get("gallinero_id", "")
    if not gallinero_id or gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    cam_imgsz = cam.get("yolo_imgsz")
    use_tiled = cam.get("use_tiled", False)

    frame = await _capture_from_cam(cam, force_hires=True)
    if not frame:
        raise HTTPException(503, "No se pudo capturar frame")

    yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled)
    if not yolo_result or not yolo_result.get("detections"):
        return {"results": [], "count": 0, "message": "No birds detected"}

    known_aves = await _get_gallinero_aves(gallinero_id)
    breed_results = _classify_breeds_yolo(frame, yolo_result)

    results = []
    for i, det in enumerate(yolo_result["detections"]):
        bbox = det.get("bbox_norm", [])
        breed_info = breed_results[i] if breed_results and i < len(breed_results) else None

        breed_guess = breed_info.get("breed", "Desconocida") if breed_info else "Desconocida"
        breed_color = breed_info.get("color", "") if breed_info else ""
        breed_sex = breed_info.get("sex", "unknown") if breed_info else "unknown"

        # Crop para enviar a la LLM
        crop_b64 = None
        if len(bbox) == 4:
            crop_result = _crop_bird_photo(frame, bbox, padding=0.20)
            if crop_result:
                crop_b64 = crop_result[0]

        if not crop_b64:
            results.append({"index": i, "error": "no crop", "confidence": 0})
            continue

        # Re-ID visual con galería
        match = await _visual_reidentify(
            crop_b64, known_aves,
            breed_hint=breed_guess,
            color_hint=breed_color,
            sex_hint=breed_sex,
        )
        match["index"] = i
        match["yolo_breed"] = breed_guess
        match["crop_b64"] = crop_b64
        results.append(match)

    frame_b64 = base64.b64encode(frame).decode()
    return {
        "gallinero": gallinero_id,
        "frame_b64": frame_b64,
        "results": results,
        "count": len(results),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Endpoints YOLO específicos ──

@router.post("/full/{gallinero_id}")
async def full_analysis(gallinero_id: str):
    """Ciclo completo bajo demanda: YOLO + Gemini + registro + foto crop.

    Usa el censo de cabaña para guiar la identificación de razas.
    """
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    analysis = await _analyze_frame(
        frame, gallinero_id,
        imgsz=cam.get("yolo_imgsz"),
        use_tiled=cam.get("use_tiled", False),
        force_gemini=is_distant,
    )
    if not analysis:
        raise HTTPException(503, "No se pudo analizar el frame")

    _enrich_with_tracking(gallinero_id, frame)

    # Registrar aves detectadas
    detected = analysis.get("birds", [])
    await _register_or_update_birds(detected, gallinero_id, frame)

    return {
        "gallinero": gallinero_id,
        "camera": cam["name"],
        "analysis": analysis,
        "registered_count": len([b for b in detected if b.get("confidence", 0) >= 0.4 and b.get("breed") != "Desconocida"]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Endpoints YOLO estáticos (antes de los parametrizados para evitar conflicto) ──

@router.get("/yolo/stats")
async def yolo_stats():
    """Estadísticas del modelo YOLO y dataset de entrenamiento."""
    try:
        from services.yolo_detector import get_model_info, get_dataset_stats
        from services.yolo_trainer import get_dataset_summary
        return {
            "model": get_model_info(),
            "detector_dataset": get_dataset_stats(),
            "training": get_dataset_summary(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/yolo/train")
async def yolo_train(epochs: int = 50, batch: int = 16, imgsz: int = 640):
    """Lanza fine-tune de YOLO con datos recopilados."""
    from services.yolo_trainer import train_model
    return await train_model(epochs=epochs, batch=batch, imgsz=imgsz)


@router.post("/yolo/reload")
async def yolo_reload():
    """Recarga el modelo YOLO (tras fine-tune nuevo)."""
    from services.yolo_detector import reload_model, get_model_info
    reload_model()
    return {"status": "reloaded", "model": get_model_info()}


@router.post("/yolo/reload-breed")
async def yolo_reload_breed():
    """Recarga el modelo YOLO de razas (tras entrenar nuevas razas)."""
    from services.yolo_detector import reload_breed_model, get_breed_model
    reload_breed_model()
    model = get_breed_model()
    return {
        "status": "reloaded" if model else "no_model",
        "breed_classes": dict(model.names) if model else {},
    }


# ── Endpoints YOLO específicos ──

@router.post("/yolo/{gallinero_id}")
async def yolo_detect(gallinero_id: str):
    """Detección rápida YOLO-only (sin Gemini). Conteo + bboxes en <100ms."""
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    result = _detect_with_yolo(frame, imgsz=cam.get("yolo_imgsz"), use_tiled=cam.get("use_tiled", False))
    if not result:
        raise HTTPException(503, "YOLO no disponible")

    # Alimentar tracker, pest alerts y health con cada detección
    _enrich_with_tracking(gallinero_id, frame)

    return {
        "gallinero": gallinero_id,
        "camera": cam["name"],
        **result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/yolo/{gallinero_id}/annotated")
async def yolo_annotated(gallinero_id: str):
    """Detección YOLO + frame anotado con bboxes. Rápido, sin API externa."""
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    result = _detect_with_yolo(frame, imgsz=cam.get("yolo_imgsz"), use_tiled=cam.get("use_tiled", False))
    if not result:
        raise HTTPException(503, "YOLO no disponible")

    from services.yolo_detector import draw_detections
    annotated = draw_detections(frame, result["detections"], cam["name"])

    return Response(
        content=annotated,
        media_type="image/jpeg",
        headers={
            "X-Birds-Detected": str(result["count"]),
            "X-Inference-Ms": str(result["inference_ms"]),
            "X-Model": result["model"],
            "X-Engine": "yolo",
        },
    )


# ── Sincronización inteligente con OvoSfera ──

@router.post("/sync_birds/{gallinero_id}")
async def sync_birds(gallinero_id: str, reset: bool = False):
    """Sincronización completa: captura, identifica, registra y sincroniza con OvoSfera.

    - reset=true: limpia el registro previo de este gallinero antes de re-identificar.
    - Captura frame de alta calidad (4K via go2rtc).
    - YOLO + Gemini: identifica todas las aves visibles.
    - Registra secuencialmente: primera Vorwerk → vorwerkgold1, segunda → vorwerkgold2...
    - Sincroniza a OvoSfera: ai_vision_id, gallinero (nombre), foto (crop base64).
    """
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cleared = 0
    if reset:
        from routers.birds import _registry, _save_registry
        before = len(_registry)
        _registry[:] = [b for b in _registry if b.get("gallinero") != gallinero_id]
        _save_registry()
        cleared = before - len(_registry)
        logger.info(f"🗑️ Reset {cleared} birds in {gallinero_id}")

        # Limpiar ai_vision_id de aves OvoSfera de este gallinero
        gallinero_name = _STREAM_TO_GALLINERO_NAME.get(gallinero_id, "")
        if gallinero_name:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
                    if resp.status_code == 200:
                        for ave in resp.json():
                            if ave.get("gallinero") == gallinero_name and ave.get("ai_vision_id"):
                                await client.put(
                                    f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave['id']}",
                                    json={"ai_vision_id": None, "foto": None},
                                )
            except Exception as e:
                logger.debug(f"OvoSfera reset cleanup failed: {e}")

    cam = CAMERAS[gallinero_id]
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=True,
    )
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    analysis = await _analyze_frame(
        frame, gallinero_id,
        imgsz=cam.get("yolo_imgsz"),
        use_tiled=cam.get("use_tiled", False),
        force_gemini=True,
    )
    if not analysis:
        raise HTTPException(503, "Gemini no pudo analizar el frame")

    detected = analysis.get("birds", [])
    await _register_or_update_birds(detected, gallinero_id, frame)

    from routers.birds import _registry as reg
    synced = [b for b in reg if b.get("gallinero") == gallinero_id]

    return {
        "gallinero": gallinero_id,
        "camera": cam["name"],
        "cleared": cleared,
        "detected": len(detected),
        "registered": len(synced),
        "birds": [
            {
                "bird_id": b["bird_id"],
                "breed": b["breed"],
                "color": b["color"],
                "sex": b["sex"],
                "ai_vision_id": b["ai_vision_id"],
                "has_photo": bool(b.get("photo_b64")),
            }
            for b in synced
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Monitorización individual de aves ──

@router.get("/bird/{vision_id}/snapshot")
async def bird_snapshot(vision_id: str):
    """Captura frame de la cámara del gallinero del ave y la resalta.

    Usa Gemini para encontrar el ave específica en el frame actual,
    y devuelve un JPEG anotado con solo esa ave resaltada.
    """
    from routers.birds import _registry
    bird = next((b for b in _registry if b.get("ai_vision_id") == vision_id), None)
    if not bird:
        raise HTTPException(404, f"Ave {vision_id} no encontrada en registro")

    gallinero_id = bird.get("gallinero", "")
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} sin cámara configurada")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
    if not frame:
        raise HTTPException(503, "No se pudo capturar frame")

    analysis = await _analyze_frame(
        frame, gallinero_id,
        imgsz=cam.get("yolo_imgsz"),
        use_tiled=cam.get("use_tiled", False),
        force_gemini=is_distant,
    )

    target_breed = bird.get("breed", "").lower()
    target_color = bird.get("color", "").lower()

    if analysis:
        birds = analysis.get("birds", [])
        matching = [
            b for b in birds
            if b.get("breed", "").lower() == target_breed
            and (b.get("color", "").lower() == target_color or not target_color)
        ]
        if matching:
            annotated = _draw_annotations(frame, matching, gallinero_id)
            return Response(
                content=annotated,
                media_type="image/jpeg",
                headers={
                    "X-Bird-Found": "true",
                    "X-Vision-Id": vision_id,
                    "X-Breed": bird.get("breed", ""),
                },
            )

    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "X-Bird-Found": "false",
            "X-Vision-Id": vision_id,
            "X-Breed": bird.get("breed", ""),
        },
    )


@router.get("/bird/ovosfera/{ove_ave_id}/snapshot")
async def bird_snapshot_by_ovosfera(ove_ave_id: int):
    """Monitoring por ID de OvoSfera: captura frame y resalta el ave.

    Usado por el inject de OvoSfera para el botón "Cámara IA Vision"
    en la ficha del ave.
    """
    # 1. Obtener datos del ave de OvoSfera
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}")
        if resp.status_code != 200:
            raise HTTPException(404, f"Ave {ove_ave_id} no encontrada en OvoSfera")
        ove = resp.json()

    target_breed = ove.get("raza", "")
    target_color = ove.get("color", "")
    vision_id = ove.get("ai_vision_id", "")
    gallinero_name = ove.get("gallinero", "")

    # 2. Determinar gallinero stream
    gallinero_stream = None
    for stream, name in _STREAM_TO_GALLINERO_NAME.items():
        if name == gallinero_name:
            gallinero_stream = stream
            break

    # Fallback: buscar en registro Seedy
    if not gallinero_stream and vision_id:
        from routers.birds import _registry
        bird = next((b for b in _registry if b.get("ai_vision_id") == vision_id), None)
        if bird:
            gallinero_stream = bird.get("gallinero", "")

    # Fallback final: G2 por defecto (12 aves conocidas)
    if not gallinero_stream or gallinero_stream not in CAMERAS:
        gallinero_stream = "gallinero_durrif_2"

    cam = CAMERAS[gallinero_stream]
    is_distant = cam.get("distant", False)
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
    if not frame:
        raise HTTPException(503, "No se pudo capturar frame")

    analysis = await _analyze_frame(
        frame, gallinero_stream,
        imgsz=cam.get("yolo_imgsz"),
        use_tiled=cam.get("use_tiled", False),
        force_gemini=is_distant,
    )

    if analysis:
        birds = analysis.get("birds", [])
        matching = [
            b for b in birds
            if _match_breed_ovosfera(b.get("breed", ""), target_breed)
        ]
        if matching:
            annotated = _draw_annotations(frame, matching, gallinero_stream)
            return Response(
                content=annotated,
                media_type="image/jpeg",
                headers={
                    "X-Bird-Found": "true",
                    "X-Vision-Id": vision_id or "pending",
                    "X-Breed": target_breed,
                },
            )

    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "X-Bird-Found": "false",
            "X-Vision-Id": vision_id or "pending",
            "X-Breed": target_breed,
        },
    )


@router.post("/bird/ovosfera/{ove_ave_id}/capture-photo")
async def capture_bird_photo(ove_ave_id: int):
    """Captura una foto nítida de alta calidad del ave usando 4K + YOLO.

    Pipeline:
    1. Obtiene datos del ave de OvoSfera (raza, gallinero)
    2. Captura frame 4K desde la cámara del gallinero
    3. Detecta aves con YOLO + Breed YOLO
    4. Encuentra el crop de mejor calidad/confianza para la raza target
    5. Guarda en OvoSfera como foto del ave (hasta 1024px)
    """
    # 1. Obtener datos del ave
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}")
        if resp.status_code != 200:
            raise HTTPException(404, f"Ave {ove_ave_id} no encontrada en OvoSfera")
        ove = resp.json()

    target_breed = ove.get("raza", "")
    target_color = ove.get("color", "")
    vision_id = ove.get("ai_vision_id", "")
    gallinero_name = ove.get("gallinero", "")

    # 2. Determinar cámaras candidatas para este gallinero
    candidate_streams = []
    for stream, name in _STREAM_TO_GALLINERO_NAME.items():
        if name == gallinero_name and stream in CAMERAS:
            candidate_streams.append(stream)
    if not candidate_streams:
        candidate_streams = list(CAMERAS.keys())

    # 3. Probar múltiples capturas en TODAS las cámaras y elegir el mejor crop
    best_crop = None
    best_conf = 0.0
    best_resolution = ""
    best_crop_area = 0  # pixel area of the crop — bigger = sharper
    total_birds_seen = 0
    best_source = ""
    NUM_ATTEMPTS = 3  # capturar varios frames — las aves se mueven

    for attempt in range(NUM_ATTEMPTS):
        if attempt > 0:
            await asyncio.sleep(1.5)  # esperar entre intentos

        for gallinero_stream in candidate_streams:
            cam = CAMERAS[gallinero_stream]
            frame = await _capture_frame(
                cam["stream"],
                snapshot_url=cam.get("snapshot_url", ""),
                snapshot_auth=tuple(cam.get("snapshot_auth", ("admin", "123456"))),
                force_hires=True,
            )
            if not frame:
                continue

            from PIL import Image as PILImage
            img_temp = PILImage.open(io.BytesIO(frame))
            W, H = img_temp.size
            logger.info(
                f"📷 capture-photo [{attempt+1}/{NUM_ATTEMPTS}]: "
                f"{gallinero_stream} frame {W}×{H} ({len(frame)} bytes)"
            )

            # 4. Detectar aves con YOLO
            imgsz = cam.get("yolo_imgsz", 1280)
            use_tiled = cam.get("use_tiled", False)
            yolo_result = _detect_with_yolo(frame, imgsz=imgsz, use_tiled=use_tiled)
            if not yolo_result or yolo_result["count"] == 0:
                continue
            total_birds_seen += yolo_result["count"]

            poultry = [d for d in yolo_result.get("detections", []) if d.get("category") == "poultry"]
            if not poultry:
                continue

            # 5. Elegir el ave MÁS GRANDE del frame — a estas distancias la
            #    clasificación de raza no es fiable, priorizamos nitidez/tamaño.
            #    Opcionalmente anotamos raza si Breed YOLO la detecta.
            breed_result = _classify_breeds_yolo(frame, yolo_result)
            breed_by_bbox = {}
            if breed_result:
                for bird in breed_result:
                    bbox_key = tuple(bird.get("bbox", []))
                    if len(bbox_key) == 4:
                        breed_by_bbox[bbox_key] = (
                            bird.get("breed", ""),
                            bird.get("confidence", 0),
                        )

            for det in sorted(
                poultry,
                key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]),
                reverse=True,
            ):
                bbox_norm = det.get("bbox_norm", [])
                if len(bbox_norm) != 4:
                    continue
                det_area = (bbox_norm[2] - bbox_norm[0]) * W * (bbox_norm[3] - bbox_norm[1]) * H
                if det_area <= best_crop_area and best_crop:
                    break  # lista ordenada, si este no supera ya no lo hará ninguno

                crop_result = _crop_bird_photo(frame, bbox_norm, padding=0.20, expected_breed="")
                if crop_result:
                    best_crop = crop_result[0]
                    best_crop_area = det_area
                    best_resolution = f"{crop_result[1]}×{crop_result[2]}"
                    best_source = gallinero_stream
                    # Anotar confianza de raza si Breed YOLO la reconoció
                    breed_info = breed_by_bbox.get(tuple(bbox_norm))
                    if breed_info and _match_breed_ovosfera(breed_info[0], target_breed):
                        best_conf = breed_info[1]
                    else:
                        best_conf = det.get("confidence", 0.5)
                    break  # ya tenemos el más grande de este frame

    if not best_crop:
        if total_birds_seen == 0:
            return {"success": False, "message": "No se pudo capturar frame de las cámaras o no hay aves visibles"}
        return {
            "success": False,
            "message": f"No se encontró a la raza {target_breed} en el frame ({total_birds_seen} aves detectadas)",
        }

    # 8. Subir foto a OvoSfera
    photo_data_uri = f"data:image/jpeg;base64,{best_crop}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}",
                json={"foto": photo_data_uri},
            )
    except Exception as e:
        logger.warning(f"Photo upload to OvoSfera failed: {e}")

    # 9. También guardar en disco
    try:
        from pathlib import Path
        photo_dir = Path("/app/data/bird_photos")
        photo_dir.mkdir(parents=True, exist_ok=True)
        photo_path = photo_dir / f"ovo_{ove_ave_id}.jpg"
        photo_path.write_bytes(base64.b64decode(best_crop))
    except Exception:
        pass

    logger.info(
        f"📸 Captured photo for OvoSfera ave {ove_ave_id} ({target_breed}): "
        f"{best_resolution}, conf={best_conf:.0%}, source={best_source}"
    )
    return {
        "success": True,
        "message": f"{target_breed} capturada ({best_conf:.0%} confianza) desde {best_source}",
        "resolution": best_resolution,
        "photo_data_uri": photo_data_uri,
    }


# ── Endpoints de tracking ──

@router.get("/tracking/all/summary")
async def get_all_tracking_summaries():
    """Resumen de tracking de todos los gallineros."""
    from services.bird_tracker import get_all_summaries
    return get_all_summaries()


@router.get("/tracking/{gallinero_id}")
async def get_tracking(gallinero_id: str):
    """Tracks activos y posiciones actuales en un gallinero."""
    from services.bird_tracker import get_tracker
    tracker = get_tracker(gallinero_id)
    return {
        "gallinero": gallinero_id,
        "summary": tracker.get_summary(),
        "active_tracks": tracker.get_active_tracks(),
    }


@router.get("/tracking/{gallinero_id}/anomalies")
async def get_tracking_anomalies(gallinero_id: str):
    """Anomalías de comportamiento detectadas por el tracker."""
    from services.bird_tracker import get_tracker
    tracker = get_tracker(gallinero_id)
    return {
        "gallinero": gallinero_id,
        "anomalies": tracker.detect_anomalies(),
    }


@router.put("/tracking/{gallinero_id}/zones")
async def set_tracking_zones(gallinero_id: str, zones: dict):
    """Configura las zonas de un gallinero (coordenadas normalizadas)."""
    from services.bird_tracker import configure_zones
    configure_zones(gallinero_id, zones)
    return {"status": "ok", "gallinero": gallinero_id, "zones": list(zones.keys())}


@router.post("/tracking/{gallinero_id}/reset")
async def reset_tracking(gallinero_id: str):
    """Reset del tracker de un gallinero."""
    from services.bird_tracker import get_tracker
    tracker = get_tracker(gallinero_id)
    tracker.reset()
    return {"status": "reset", "gallinero": gallinero_id}


# ── Endpoints de salud ──

@router.get("/health/growth/{track_id}")
async def get_bird_growth(track_id: int):
    """Curva de crecimiento de un ave específica."""
    from services.health_analyzer import get_growth_tracker
    growth = get_growth_tracker()
    return {
        "track_id": track_id,
        "curve": growth.get_growth_curve(track_id),
        "rate": growth.get_growth_rate(track_id),
    }


@router.get("/health/{gallinero_id}")
async def get_flock_health(gallinero_id: str):
    """Análisis de salud del rebaño en un gallinero."""
    from services.bird_tracker import get_tracker
    from services.health_analyzer import analyze_flock_health
    tracker = get_tracker(gallinero_id)
    return analyze_flock_health(tracker)


@router.get("/health/{gallinero_id}/growth")
async def get_growth_data(gallinero_id: str):
    """Datos de crecimiento de todas las aves trackadas."""
    from services.health_analyzer import get_growth_tracker
    growth = get_growth_tracker()
    return {
        "gallinero": gallinero_id,
        "comparison": growth.compare_growth(),
    }


# ── Endpoints de plagas ──

@router.get("/pests/stats")
async def get_pest_stats():
    """Estadísticas globales de plagas."""
    from services.pest_alert import get_pest_manager
    return get_pest_manager().get_stats()


@router.get("/pests/{gallinero_id}")
async def get_pest_history(gallinero_id: str, limit: int = 50):
    """Historial de detecciones de plagas en un gallinero."""
    from services.pest_alert import get_pest_manager
    mgr = get_pest_manager()
    return {
        "gallinero": gallinero_id,
        "history": mgr.get_history(gallinero_id, limit),
    }


# ── Endpoints de censo de cabaña ──

@router.get("/census/{gallinero_id}")
async def get_census(gallinero_id: str):
    """Censo esperado de la cabaña en un gallinero."""
    from services.flock_census import get_census as _get
    entries = _get(gallinero_id)
    if not entries:
        raise HTTPException(404, f"No census data for {gallinero_id}")
    return {"gallinero": gallinero_id, "census": entries}


@router.get("/census/{gallinero_id}/status")
async def get_census_status(gallinero_id: str):
    """Estado de asignación: cuántas aves identificadas vs esperadas."""
    import httpx
    from services.flock_census import get_assignment_status

    try:
        async with httpx.AsyncClient(timeout=5.0, base_url="http://localhost:8000") as c:
            resp = await c.get("/birds/", params={"gallinero": gallinero_id})
            registered = resp.json().get("birds", []) if resp.status_code == 200 else []
    except Exception:
        registered = []

    return {
        "gallinero": gallinero_id,
        **get_assignment_status(gallinero_id, registered),
    }


@router.post("/census/reload")
async def reload_census():
    """Recarga el censo desde disco (tras editar flock_census.json)."""
    from services.flock_census import reload
    reload()
    return {"status": "reloaded"}


# ── Identificación con confirmación humana ──

@router.post("/bird/ovosfera/{ove_ave_id}/capture-identify")
async def capture_and_identify(ove_ave_id: int):
    """Captura foto + identifica con Qwen2.5-VL-72B. NO guarda hasta confirmar.

    Pipeline:
    1. Captura 4K desde cámaras → YOLO crop del ave más grande
    2. Envía crop a Together.ai Qwen2.5-VL-72B con censo del gallinero
    3. Devuelve foto + identificación para revisión humana
    """
    from services import together_vision
    from services.flock_census import get_expected_breeds

    # 1. Obtener datos del ave de OvoSfera
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}")
        if resp.status_code != 200:
            raise HTTPException(404, f"Ave {ove_ave_id} no encontrada en OvoSfera")
        ove = resp.json()

    gallinero_name = ove.get("gallinero", "")

    # 2. Determinar cámaras y capturar
    candidate_streams = []
    for stream, name in _STREAM_TO_GALLINERO_NAME.items():
        if name == gallinero_name and stream in CAMERAS:
            candidate_streams.append(stream)
    if not candidate_streams:
        candidate_streams = list(CAMERAS.keys())

    # Determinar gallinero_id para el censo
    gallinero_id = ""
    for stream in candidate_streams:
        for sid, sname in _STREAM_TO_GALLINERO_NAME.items():
            if sname == gallinero_name:
                gallinero_id = sid
                break
        if gallinero_id:
            break

    best_crop = None
    best_crop_area = 0
    best_crop_score = -1  # composite: isolation + size
    best_resolution = ""
    best_source = ""
    total_birds_seen = 0
    NUM_ATTEMPTS = 5

    for attempt in range(NUM_ATTEMPTS):
        if attempt > 0:
            await asyncio.sleep(2.0)  # more time between attempts for pose changes

        for gallinero_stream in candidate_streams:
            cam = CAMERAS[gallinero_stream]
            frame = await _capture_frame(
                cam["stream"],
                snapshot_url=cam.get("snapshot_url", ""),
                snapshot_auth=tuple(cam.get("snapshot_auth", ("admin", "123456"))),
                force_hires=True,
            )
            if not frame:
                continue

            # Check brightness — skip very dark frames (night)
            from PIL import Image as PILImage, ImageStat
            img_temp = PILImage.open(io.BytesIO(frame))
            W, H = img_temp.size
            brightness = ImageStat.Stat(img_temp.convert("L")).mean[0]
            if brightness < 25:
                logger.debug(f"Frame too dark ({brightness:.0f}/255), skipping")
                continue

            imgsz = cam.get("yolo_imgsz", 1280)
            use_tiled = cam.get("use_tiled", False)
            yolo_result = _detect_with_yolo(frame, imgsz=imgsz, use_tiled=use_tiled)
            if not yolo_result or yolo_result["count"] == 0:
                continue

            poultry = [d for d in yolo_result.get("detections", []) if d.get("category") == "poultry"]
            if not poultry:
                continue
            total_birds_seen += len(poultry)

            # Prefer frames with fewer birds (isolation = better crop)
            n_birds = len(poultry)
            isolation_bonus = 1.0 / max(n_birds, 1)  # 1 bird = 1.0, 5 birds = 0.2

            for det in sorted(
                poultry,
                key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]),
                reverse=True,
            ):
                bbox_norm = det.get("bbox_norm", [])
                if len(bbox_norm) != 4:
                    continue
                det_area = (bbox_norm[2] - bbox_norm[0]) * W * (bbox_norm[3] - bbox_norm[1]) * H
                # Score = area × isolation bonus (prefer lone birds)
                score = det_area * isolation_bonus

                if score <= best_crop_score and best_crop:
                    break

                crop_result = _crop_bird_photo(frame, bbox_norm, padding=0.25, expected_breed="")
                if crop_result:
                    best_crop = crop_result[0]
                    best_crop_area = det_area
                    best_crop_score = score
                    best_resolution = f"{crop_result[1]}×{crop_result[2]}"
                    best_source = gallinero_stream
                    break

    if not best_crop:
        if total_birds_seen == 0:
            # Check if it's a brightness issue
            msg = "No se pudo capturar: poca luz o sin aves visibles. Prueba de día o sube foto manual."
        else:
            msg = f"No se encontró ave en el frame ({total_birds_seen} aves detectadas)"
        return {"success": False, "message": msg}

    # 3. Identificar con Together Vision (Qwen2.5-VL-72B)
    census = get_expected_breeds(gallinero_id) if gallinero_id else []
    try:
        vision_result = await together_vision.identify_bird(best_crop, census)
    except Exception as e:
        logger.error(f"Together Vision failed: {e}")
        vision_result = {
            "breed": "desconocida", "color": "", "sex": "indeterminado",
            "confidence": 0.0, "distinctive_features": [],
            "image_quality": "mala", "reasoning": f"Error: {e}",
        }

    # 4. Guardar crop en disco (temporal, se confirma o descarta)
    try:
        from pathlib import Path
        tmp_dir = Path("/app/data/bird_photos/pending")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"ovo_{ove_ave_id}.jpg"
        import base64 as b64mod
        tmp_path.write_bytes(b64mod.b64decode(best_crop))
    except Exception:
        pass

    photo_data_uri = f"data:image/jpeg;base64,{best_crop}"

    logger.info(
        f"🔎 capture-identify ave {ove_ave_id}: "
        f"{vision_result.get('breed', '?')} ({vision_result.get('confidence', 0):.0%}) "
        f"from {best_source}, {best_resolution}"
    )

    return {
        "success": True,
        "photo_data_uri": photo_data_uri,
        "resolution": best_resolution,
        "bird_count": total_birds_seen,
        "source_camera": best_source,
        "identification": {
            "breed": vision_result.get("breed", "desconocida"),
            "color": vision_result.get("color", ""),
            "sex": vision_result.get("sex", "indeterminado"),
            "confidence": vision_result.get("confidence", 0.0),
            "distinctive_features": vision_result.get("distinctive_features", []),
            "image_quality": vision_result.get("image_quality", ""),
            "reasoning": vision_result.get("reasoning", ""),
            "model": vision_result.get("model", ""),
        },
        "ave": {
            "id": ove_ave_id,
            "raza": ove.get("raza", ""),
            "color": ove.get("color", ""),
            "gallinero": gallinero_name,
        },
    }


@router.post("/bird/ovosfera/{ove_ave_id}/identify-photo")
async def identify_manual_photo(ove_ave_id: int, body: dict):
    """Identifica un ave a partir de una foto subida manualmente (sin cámaras).

    Body:
        photo_data_uri: str  — "data:image/jpeg;base64,..." o "data:image/png;base64,..."
    """
    from services import together_vision
    from services.flock_census import get_expected_breeds

    photo_uri = body.get("photo_data_uri", "")
    if not photo_uri or "base64," not in photo_uri:
        raise HTTPException(400, "Se requiere photo_data_uri con base64")

    # Obtener datos del ave
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}")
        if resp.status_code != 200:
            raise HTTPException(404, f"Ave {ove_ave_id} no encontrada en OvoSfera")
        ove = resp.json()

    gallinero_name = ove.get("gallinero", "")
    gallinero_id = ""
    for sid, sname in _STREAM_TO_GALLINERO_NAME.items():
        if sname == gallinero_name:
            gallinero_id = sid
            break

    # Extraer base64
    b64_data = photo_uri.split("base64,", 1)[1]
    mime = "image/jpeg"
    if photo_uri.startswith("data:image/png"):
        mime = "image/png"

    census = get_expected_breeds(gallinero_id) if gallinero_id else []
    try:
        vision_result = await together_vision.identify_bird(b64_data, census, mime_type=mime)
    except Exception as e:
        logger.error(f"Together Vision failed (manual): {e}")
        vision_result = {
            "breed": "desconocida", "color": "", "sex": "indeterminado",
            "confidence": 0.0, "distinctive_features": [],
            "image_quality": "mala", "reasoning": f"Error: {e}",
        }

    logger.info(
        f"🔎 identify-photo manual ave {ove_ave_id}: "
        f"{vision_result.get('breed', '?')} ({vision_result.get('confidence', 0):.0%})"
    )

    return {
        "success": True,
        "photo_data_uri": photo_uri,
        "resolution": "manual",
        "bird_count": 1,
        "source_camera": "manual_upload",
        "identification": {
            "breed": vision_result.get("breed", "desconocida"),
            "color": vision_result.get("color", ""),
            "sex": vision_result.get("sex", "indeterminado"),
            "confidence": vision_result.get("confidence", 0.0),
            "distinctive_features": vision_result.get("distinctive_features", []),
            "image_quality": vision_result.get("image_quality", ""),
            "reasoning": vision_result.get("reasoning", ""),
            "model": vision_result.get("model", ""),
        },
        "ave": {
            "id": ove_ave_id,
            "raza": ove.get("raza", ""),
            "color": ove.get("color", ""),
            "gallinero": gallinero_name,
        },
    }


@router.post("/bird/ovosfera/{ove_ave_id}/confirm-identity")
async def confirm_bird_identity(ove_ave_id: int, body: dict):
    """Confirma/corrige/rechaza la identificación de un ave.

    Body:
        action: "confirm" | "correct" | "reject"
        breed: str (solo si action=correct)
        color: str (solo si action=correct)
        sex: str (solo si action=correct)
        photo_data_uri: str (la foto capturada — se sube si confirm/correct)
    """
    action = body.get("action", "")
    photo_uri = body.get("photo_data_uri", "")

    if action not in ("confirm", "correct", "reject"):
        raise HTTPException(400, f"Acción inválida: {action}")

    if action == "reject":
        # Borrar foto pendiente
        try:
            from pathlib import Path
            pending = Path(f"/app/data/bird_photos/pending/ovo_{ove_ave_id}.jpg")
            if pending.exists():
                pending.unlink()
        except Exception:
            pass

        # Limpiar ai_vision_id (y foto si la tenía) en OvoSfera
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(
                    f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}",
                    json={"ai_vision_id": None, "foto": None},
                )
        except Exception as e:
            logger.warning(f"OvoSfera clear on reject failed: {e}")

        logger.info(f"❌ Ave {ove_ave_id}: identificación rechazada, ai_vision_id limpiado")
        return {"status": "rejected", "ave_id": ove_ave_id, "cleared": ["ai_vision_id", "foto"]}

    # confirm o correct → subir foto y actualizar campos
    update_data = {}
    if photo_uri:
        update_data["foto"] = photo_uri

    if action == "correct":
        # El usuario corrige la raza/color/sexo
        if body.get("breed"):
            update_data["raza"] = body["breed"]
        if body.get("color"):
            update_data["color"] = body["color"]

    # Generar ai_vision_id para confirm o correct si hay breed válido
    if action in ("confirm", "correct"):
        breed = body.get("breed", "")
        color = body.get("color", "")
        if breed and breed.lower() not in ("desconocida", "unknown", ""):
            if not body.get("existing_vision_id"):
                seq = ove_ave_id
                vision_id = _build_vision_id(breed, color, seq)
                update_data["ai_vision_id"] = vision_id

    if update_data:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(
                    f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}",
                    json=update_data,
                )
                if resp.status_code != 200:
                    logger.warning(f"OvoSfera update failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"OvoSfera update error: {e}")

    # Mover foto de pending a confirmadas
    try:
        from pathlib import Path
        pending = Path(f"/app/data/bird_photos/pending/ovo_{ove_ave_id}.jpg")
        confirmed = Path(f"/app/data/bird_photos/ovo_{ove_ave_id}.jpg")
        if pending.exists():
            pending.rename(confirmed)
    except Exception:
        pass

    # Guardar para dataset de entrenamiento (correcciones humanas son oro)
    try:
        from pathlib import Path
        import json as jsonmod
        train_dir = Path("/app/data/vision_training")
        train_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ave_id": ove_ave_id,
            "action": action,
            "breed": body.get("breed", ""),
            "color": body.get("color", ""),
            "sex": body.get("sex", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(train_dir / "confirmations.jsonl", "a") as f:
            f.write(jsonmod.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

    logger.info(
        f"{'✅' if action == 'confirm' else '✏️'} Ave {ove_ave_id}: "
        f"{action} — {body.get('breed', '?')} {body.get('color', '')}"
    )
    return {
        "status": action + "ed",
        "ave_id": ove_ave_id,
        "updated_fields": list(update_data.keys()),
    }
