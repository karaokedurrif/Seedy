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
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response

logger = logging.getLogger(__name__)

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
        "name": "Cám. Nueva (VIGI)",
        "gallinero": "gallinero_durrif",
        "distant": True,       # ~2-8m lateral, muchas aves visibles
        "yolo_imgsz": 960,     # tile size para breed tiled (con tile-artifact filter)
        "use_tiled": True,     # SAHI-style tiled detection
        "use_breed": True,     # breed model + tile-artifact filter — detecta aves reales, descarta artefactos
    },
    "gallinero_durrif_2": {
        "stream": "gallinero_durrif_2",
        "stream_sub": "gallinero_durrif_2_sub",
        "snapshot_url": "http://10.10.10.10/cgi-bin/snapshot.cgi",
        "name": "Cám. Gallinero (VIGI)",
        "gallinero": "gallinero_durrif",
        "distant": False,      # cámara dentro del recinto, cerca
        "yolo_imgsz": 1280,
        "use_tiled": True,     # Tileado para mejor detección en 4K
        "use_breed": True,     # breed model detects chickens much better than COCO
    },
    "sauna_durrif_1": {
        "stream": "sauna_durrif_1",
        "stream_sub": "sauna_durrif_1_sub",
        "snapshot_url": "http://10.10.10.108/cgi-bin/snapshot.cgi",
        "snapshot_auth": ("admin", "1234567a"),
        "snapshot_digest": True,  # Dahua requires HTTP Digest Auth
        "name": "Cám. Sauna (Dahua)",
        "gallinero": "gallinero_durrif",
        "distant": True,       # escena amplia exterior, aves a varias distancias
        "yolo_imgsz": 800,     # tile size para breed tiled (800 > 960 en tests: más aves)
        "use_tiled": True,     # SAHI-style tiling — imprescindible en 4K con muchas aves
        "use_breed": True,     # breed model + tile-artifact filter
    },
}

# Prompt especializado para identificar aves individuales
BIRD_ID_PROMPT = """Analiza esta imagen de un gallinero.

TAREA: Identifica CADA ave visible individualmente.

Para CADA ave que veas, devuelve EXACTAMENTE un bloque JSON con:
{
  "birds": [
    {
      "breed": "nombre de la raza",
      "color": "color principal del plumaje en español",
      "sex": "male" o "female" o "unknown",
      "confidence": 0.0-1.0,
      "bbox": [x1, y1, x2, y2],
      "distinguishing_features": "rasgos distintivos breves"
    }
  ],
  "total_visible": número total de aves visibles,
  "conditions": "breve descripción del gallinero (luz, actividad)"
}

RAZAS POSIBLES EN ESTA CABAÑA (solo estas, no inventes otras):
- Sussex White (armiñada): blanca con RAYAS NEGRAS en cuello (armiñado). NO es igual a Bresse.
- Sussex Light (Silver): plateada con marcas negras. Gallo grande (4.5kg).
- Bresse: completamente blanca, SIN rayas en cuello, más pequeña (2kg), patas GRIS AZULADO.
- Marans: negro cobrizo, reflejos cobrizos en cuello.
- Araucana: trigueña o negra. Sin cola (rumpless). Huevos azules/verdes.
- Ameraucana: trigueña, similar a araucana pero con cola.
- Sulmtaler: trigueño/atigrado (Weizenfarbig). Cresta pequeña, porte elegante.
- Andaluza Azul: gris azulado uniforme, cresta grande simple.
- Pita Pinta Asturiana: blanca con muchos puntos/motas negros distribuidos (pinta).
- Vorwerk: cuerpo leonado/dorado, cuello y cola NEGROS.
- Cruce F1: fenotipo mixto, color variado.

CLAVES PARA NO CONFUNDIR:
- Sussex White vs Bresse: Sussex tiene rayas negras en cuello (armiñada), Bresse es blanca pura con patas azuladas.
- Pita Pinta vs Sussex White: Pita Pinta tiene motas/puntos negros distribuidos por todo el cuerpo (no solo cuello).
- Vorwerk vs Sulmtaler: Vorwerk tiene cuello/cola negro con cuerpo dorado. Sulmtaler es trigueño atigrado sin contraste tan marcado.

REGLAS:
- El campo 'color' es OBLIGATORIO.
- bbox: coordenadas normalizadas [0.0-1.0] [x1_sup_izq, y1_sup_izq, x2_inf_der, y2_inf_der].
- Si el sexo es evidente (cresta grande, cola larga = male; más pequeña = female), indícalo.
- Confianza: 0.9+ si evidente, 0.5-0.8 si razonable, <0.5 si dudosa.
- Si no se distingue la raza, pon "breed": "Desconocida".
- Responde SOLO con el JSON, sin texto adicional."""

# Abreviaturas de color para generar ai_vision_id compactos
_COLOR_ABBREV = {
    "blanco": "bl", "blanca": "bl", "white": "bl",
    "negro": "ng", "negra": "ng", "black": "ng",
    "silver": "silver", "plateado": "silver", "plateada": "silver",
    "dorado": "gold", "dorada": "gold", "gold": "gold",
    "azul": "az", "blue": "az",
    "rojo": "rj", "roja": "rj", "red": "rj",
    "pardo": "pardo", "parda": "pardo", "brown": "pardo",
    "leonado": "leon", "leonada": "leon", "buff": "leon",
    "barrado": "barr", "barrada": "barr", "barred": "barr",
    "negro cobrizo": "nc", "negra cobriza": "nc",
    "gris": "gris", "grey": "gris", "gray": "gris",
    "perdiz": "perdiz", "partridge": "perdiz",
    "splash": "splash",
    "tricolor": "tri",
}

# Abreviaturas de raza
_BREED_ABBREV = {
    "sussex": "sussex",
    "bresse": "bresse",
    "marans": "marans",
    "orpington": "orpington",
    "araucana": "araucana",
    "sulmtaler": "sulmtaler",
    "andaluza azul": "andaluza",
    "andaluza": "andaluza",
    "pita pinta": "pitapinta",
    "vorwerk": "vorwerk",
    "castellana negra": "castellana",
    "castellana": "castellana",
    "cruce f1": "cruceF1",
    "cruce": "cruceF1",
    "plymouth rock": "plymouth",
}


def _build_vision_id(breed: str, color: str, seq: int) -> str:
    """Genera ai_vision_id compacto: sussexbl1, maransnc2, etc."""
    breed_low = breed.strip().lower()
    color_low = color.strip().lower()
    breed_slug = _BREED_ABBREV.get(breed_low, breed_low.replace(" ", ""))
    color_slug = _COLOR_ABBREV.get(color_low, color_low.split()[0][:4] if color_low else "x")
    return f"{breed_slug}{color_slug}{seq}"


# ── OvoSfera breed/color matching ──

_BREED_OVOSFERA_ALIASES = {
    "f1 (cruce)": ["cruce f1", "cruce", "f1"],
    "cruce f1": ["f1 (cruce)", "cruce", "f1"],
    "cruce": ["cruce f1", "f1 (cruce)"],
    "pita pinta": ["pita pinta asturiana"],
    "pita pinta asturiana": ["pita pinta"],
}

_COLOR_OVOSFERA_ALIASES = {
    "silver": ["light (silver)", "plateado", "plateada"],
    "dorado": ["gold-black", "gold", "dorada"],
    "blanco": ["white", "blanca"],
    "negro cobrizo": ["black copper", "negra cobriza"],
    "trigueño": ["wheaten (weizenfarbig)", "wheaten", "trigueña"],
    "variado": ["varied", "variada"],
    "azul": ["blue"],
    "negro": ["negra", "black"],
    "pinta": ["mottled"],
    # reverse mappings (OvoSfera → census)
    "light (silver)": ["silver", "plateado"],
    "gold-black": ["dorado", "gold"],
    "white": ["blanco", "blanca"],
    "black copper": ["negro cobrizo"],
    "wheaten (weizenfarbig)": ["trigueño", "wheaten"],
}


def _match_breed_ovosfera(seedy_breed: str, ovo_breed: str) -> bool:
    """Check if Seedy breed matches OvoSfera breed (handles aliases)."""
    a = seedy_breed.lower().strip()
    b = ovo_breed.lower().strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    return b in _BREED_OVOSFERA_ALIASES.get(a, [])


def _match_color_ovosfera(seedy_color: str, ovo_color: str) -> bool:
    """Check if Seedy color matches OvoSfera color (handles aliases)."""
    a = seedy_color.lower().strip()
    b = ovo_color.lower().strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    return b in _COLOR_OVOSFERA_ALIASES.get(a, [])


# Estado del loop
_running = False
_last_results: dict[str, dict] = {}
_task: asyncio.Task | None = None

# ── Breed YOLO → Census mapping ──
# Mapea clase del modelo de razas a (breed, color, sex) del censo
_BREED_YOLO_TO_CENSUS = {
    "vorwerk_gallina":         ("Vorwerk",        "dorado",        "female"),
    "vorwerk_gallo":           ("Vorwerk",        "dorado",        "male"),
    "sussex_silver_gallina":   ("Sussex",         "silver",        "female"),
    "sussex_silver_gallo":     ("Sussex",         "silver",        "male"),
    "sussex_white_gallina":    ("Sussex",         "white",         "female"),
    "sulmtaler_gallina":       ("Sulmtaler",      "trigueño",      "female"),
    "sulmtaler_gallo":         ("Sulmtaler",      "trigueño",      "male"),
    "marans_gallina":          ("Marans",         "negro cobrizo", "female"),
    "bresse_gallina":          ("Bresse",         "blanco",        "female"),
    "bresse_gallo":            ("Bresse",         "blanco",        "male"),
    "andaluza_azul_gallina":   ("Andaluza Azul",  "azul",          "female"),
    "pita_pinta_gallina":      ("Pita Pinta",     "pinta",         "female"),
    "araucana_gallina":        ("Araucana",       "trigueño",      "female"),
    "ameraucana_gallina":      ("Ameraucana",     "trigueño",      "female"),
}

# Razas que NO están en YOLO → se detectan por descarte del censo
_FALLBACK_BREEDS = {
    "F1 (cruce)":       {"color": "variado",   "sexo": "female"},
    "Araucana (negra)": {"color": "negra",     "sexo": "female"},
}


async def _capture_frame(camera_stream: str, *, use_sub: bool = False, snapshot_url: str = "",
                         snapshot_auth: tuple[str, str] = ("admin", "123456"),
                         snapshot_digest: bool = False,
                         force_hires: bool = False) -> bytes | None:
    """Captura un frame JPEG.

    Estrategia:
    - force_hires=True: siempre go2rtc main stream (4K, ~800KB, ~1s)
      Necesario para cámaras lejanas o para breed model que necesita resolución.
    - Normal: CGI directo (~100ms, 704x576), fallback go2rtc.
    """
    import httpx

    # Hi-res: go2rtc main stream directamente (4K)
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
            auth = httpx.DigestAuth(*snapshot_auth) if snapshot_digest else httpx.BasicAuth(*snapshot_auth)
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(snapshot_url, auth=auth)
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
        snapshot_digest=cam.get("snapshot_digest", False),
        force_hires=force_hires,
    )


def _detect_with_yolo(frame_bytes: bytes, *, imgsz: int | None = None,
                      use_tiled: bool = False, use_breed: bool = False,
                      camera_id: str = "") -> dict | None:
    """Detección v4.1: COCO como detector primario + breed como clasificador sobre crops.

    Args:
        imgsz: Resolución de inferencia (overrides default).
        use_tiled: Si True, usa detección por tiles — mejor para aves lejanas.
        use_breed: Si True, clasifica raza de cada crop con breed model.
        camera_id: ID de cámara para seleccionar config de tiles.
    """
    try:
        # v4.1: Usar detector unificado (COCO primary + breed classifier)
        from services.yolo_detector_v4 import get_detector
        detector = get_detector()
        return detector.detect_birds(
            frame_bytes,
            camera_id=camera_id,
            use_tiled=use_tiled,
            classify_breeds=use_breed,
        )
    except Exception as e:
        logger.warning(f"YOLO v4 detection failed, fallback to legacy: {e}")
        # Fallback al detector legacy
        try:
            if use_tiled and use_breed:
                from services.yolo_detector import detect_tiled_breed
                result = detect_tiled_breed(frame_bytes, tile_size=imgsz or 960)
                if result and result.get("count", 0) == 0:
                    from services.yolo_detector import detect_tiled
                    coco_result = detect_tiled(frame_bytes, tile_size=1280,
                                               confidence=0.20, overlap=0.3)
                    if coco_result and coco_result.get("count", 0) > 0:
                        return coco_result
                return result
            if use_tiled:
                from services.yolo_detector import detect_tiled
                return detect_tiled(frame_bytes, tile_size=imgsz or 1280)
            if use_breed:
                from services.yolo_detector import detect_breed
                return detect_breed(frame_bytes, imgsz=imgsz)
            from services.yolo_detector import detect_birds
            return detect_birds(frame_bytes, imgsz=imgsz)
        except Exception as e2:
            logger.warning(f"Legacy YOLO also failed: {e2}")
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


async def _curate_detections(frame_bytes: bytes, yolo_result: dict, camera_id: str = ""):
    """Curación v4.1: guarda crops y frames anotados para futuro reentrenamiento."""
    try:
        from services.crop_curator import get_curator
        import cv2
        import numpy as np

        curator = get_curator()
        detections = yolo_result.get("detections", [])
        if not detections:
            return

        # Decodificar frame
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame_cv is None:
            return

        # Track A: Curar crops individuales
        for det in detections:
            breed = det.get("breed", det.get("class_name", ""))
            if breed and breed not in ("sin_clasificar", "Desconocida", "unknown", ""):
                crop_bytes = det.get("crop_bytes", b"")
                if crop_bytes:
                    crop_arr = np.frombuffer(crop_bytes, dtype=np.uint8)
                    crop_cv = cv2.imdecode(crop_arr, cv2.IMREAD_COLOR)
                    if crop_cv is not None:
                        await curator.curate_crop(
                            crop=crop_cv,
                            identification={
                                "breed": breed,
                                "confidence": det.get("breed_conf", det.get("confidence", 0)),
                                "engine": "yolo_breed",
                            },
                            camera_id=camera_id,
                        )

        # Track B: Curar frame completo con bboxes
        await curator.curate_frame(
            frame=frame_cv,
            detections=detections,
            camera_id=camera_id,
        )
    except Exception as e:
        logger.debug(f"Curation failed (non-critical): {e}")


async def _analyze_frame(frame_bytes: bytes, gallinero_id: str = "", *, imgsz: int | None = None,
                         use_tiled: bool = False, use_breed: bool = False,
                         force_gemini: bool = False) -> dict | None:
    """Análisis híbrido: YOLO COCO + Breed YOLO + fallback censo + Gemini.

    Pipeline:
      1) YOLO COCO: detección rápida (conteo + bboxes)
      2) Breed YOLO: clasifica raza de cada ave por crop
      3) Aves sin breed → fallback por censo (araucana, F1 por descarte)
      4) Gemini: solo si quedan aves sin identificar o force_gemini
    """
    # 1) YOLO: detección local (~50ms COCO, ~800ms breed tiled)
    yolo_result = _detect_with_yolo(frame_bytes, imgsz=imgsz, use_tiled=use_tiled, use_breed=use_breed, camera_id=gallinero_id)
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
            await _curate_detections(frame_bytes, yolo_result, camera_id=gallinero_id)
            return {
                "birds": breed_result,
                "total_visible": yolo_count,
                "conditions": f"Breed YOLO ({yolo_result['inference_ms']:.0f}ms)",
                "engine": "yolo_breed",
            }

    # 5) Gemini: si quedan aves sin identificar, o force_gemini
    if yolo_count > 0 or force_gemini:
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

            await _curate_detections(frame_bytes, yolo_result, camera_id=gallinero_id)
            return gemini_result

    # Sin aves detectadas por YOLO, o Gemini falló → devolver breed YOLO parcial o YOLO básico
    if breed_result:
        await _curate_detections(frame_bytes, yolo_result, camera_id=gallinero_id)
        return {
            "birds": breed_result,
            "total_visible": yolo_count,
            "conditions": f"Breed YOLO parcial ({yolo_result['inference_ms']:.0f}ms)",
            "engine": "yolo_breed_partial",
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


def _classify_breeds_yolo(frame_bytes: bytes, yolo_result: dict) -> list[dict] | None:
    """Clasifica la raza de cada ave detectada por COCO YOLO usando el modelo de razas.

    Para cada detección de COCO YOLO:
    1. Crop la zona del ave del frame
    2. Ejecutar breed YOLO sobre el crop
    3. Mapear clase breed → (breed, color, sex) del censo

    Returns list of bird dicts compatible con el formato Gemini, o None si no hay breed model.
    """
    try:
        from services.yolo_detector import classify_breed_crop, crop_detections, get_breed_model
    except ImportError:
        return None

    if get_breed_model() is None:
        return None

    poultry = [d for d in yolo_result.get("detections", []) if d.get("category") == "poultry"]
    if not poultry:
        return None

    crops = crop_detections(frame_bytes, poultry)
    if not crops:
        return None

    birds = []
    for det, crop_bytes in zip(poultry, crops):
        breed_pred = classify_breed_crop(crop_bytes)

        if breed_pred and breed_pred["confidence"] >= 0.45:
            breed_class = breed_pred["breed_class"]
            census_info = _BREED_YOLO_TO_CENSUS.get(breed_class)
            if census_info:
                breed, color, sex = census_info
                birds.append({
                    "breed": breed,
                    "color": color,
                    "sex": sex,
                    "confidence": breed_pred["confidence"],
                    "bbox": det["bbox_norm"],
                    "distinguishing_features": f"Breed YOLO: {breed_class} ({breed_pred['confidence']:.0%})",
                    "engine": "yolo_breed",
                })
                continue

        # Breed YOLO no pudo clasificar → marcar como Desconocida
        birds.append({
            "breed": "Desconocida",
            "color": "",
            "sex": "unknown",
            "confidence": det["confidence"],
            "bbox": det["bbox_norm"],
            "distinguishing_features": "Breed YOLO: sin match suficiente",
            "engine": "yolo_breed_unknown",
        })

    return birds if birds else None


def _resolve_unknown_by_census(gallinero_id: str, birds: list[dict]) -> list[dict]:
    """Resuelve aves 'Desconocida' cruzando con el censo de la cabaña.

    Si YOLO identificó N aves de razas conocidas, las que quedan sin identificar
    se asignan por descarte a las razas del censo que no tienen match YOLO
    (araucana, F1). Se usan las cantidades esperadas del censo.
    """
    try:
        from services.flock_census import get_expected_breeds
    except ImportError:
        return birds

    census = get_expected_breeds(gallinero_id)
    if not census:
        return birds

    # Contar cuántas de cada raza ya identificó breed YOLO
    from collections import Counter
    identified_counts: Counter = Counter()
    for b in birds:
        if b["breed"] != "Desconocida":
            key = (b["breed"].lower(), b["sex"])
            identified_counts[key] += 1

    # Calcular qué razas del censo NO están cubiertas por breed YOLO
    unmatched_census = []  # [(breed, color, sex, remaining_count)]
    for entry in census:
        raza = entry["raza"]
        if raza == "Por determinar":
            continue
        color = entry["color"]
        sexo = entry["sexo"]
        cantidad = entry.get("cantidad", 0)

        # ¿Cuántas de esta raza ya identificó YOLO?
        key = (raza.lower(), sexo)
        already = identified_counts.get(key, 0)
        remaining = max(0, cantidad - already)

        if remaining > 0 and raza in _FALLBACK_BREEDS:
            for _ in range(remaining):
                unmatched_census.append((raza, color, sexo))

    # Asignar las desconocidas a las razas unmatched del censo
    unknown_indices = [i for i, b in enumerate(birds) if b["breed"] == "Desconocida"]

    for idx, unk_i in enumerate(unknown_indices):
        if idx < len(unmatched_census):
            raza, color, sexo = unmatched_census[idx]
            birds[unk_i]["breed"] = raza
            birds[unk_i]["color"] = color
            birds[unk_i]["sex"] = sexo
            birds[unk_i]["distinguishing_features"] = (
                f"Asignada por descarte del censo ({raza} {color})"
            )
            birds[unk_i]["engine"] = "census_fallback"

    return birds


def _merge_breed_yolo_into_gemini(breed_birds: list[dict], gemini_result: dict):
    """Si breed YOLO tiene alta confianza para un ave, sobrescribe la predicción de Gemini."""
    gemini_birds = gemini_result.get("birds", [])
    if not gemini_birds or not breed_birds:
        return

    # Emparejar por bbox overlap (IoU)
    for bb in breed_birds:
        if bb.get("engine") != "yolo_breed" or bb["confidence"] < 0.6:
            continue
        bb_bbox = bb.get("bbox", [])
        if len(bb_bbox) != 4:
            continue

        best_iou = 0
        best_gb = None
        for gb in gemini_birds:
            gb_bbox = gb.get("bbox", [])
            if len(gb_bbox) != 4:
                continue
            iou = _bbox_iou(bb_bbox, gb_bbox)
            if iou > best_iou:
                best_iou = iou
                best_gb = gb

        if best_gb and best_iou > 0.3:
            # Breed YOLO tiene mayor confianza → sobrescribir
            if bb["confidence"] > best_gb.get("confidence", 0):
                best_gb["breed"] = bb["breed"]
                best_gb["color"] = bb["color"]
                best_gb["sex"] = bb["sex"]
                best_gb["confidence"] = bb["confidence"]
                best_gb["engine"] = "yolo_breed+gemini"


def _bbox_iou(a: list[float], b: list[float]) -> float:
    """IoU entre dos bboxes normalizados [x1,y1,x2,y2]."""
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def _validate_breeds_against_census(gallinero_id: str, gemini_result: dict):
    """Valida las razas identificadas por Gemini contra el censo de la cabaña.

    Si Gemini identifica una raza que no existe en la cabaña, se marca como
    Desconocida (para no introducir errores en el registro).
    También corrige nombres cercanos (typos).
    """
    try:
        from services.flock_census import get_all_breeds, get_canonical_breed_name
    except ImportError:
        return

    valid_breeds = get_all_breeds(gallinero_id)  # solo razas de este gallinero
    if not valid_breeds:
        # Fallback: si el gallinero no tiene censo, usar todas las razas
        valid_breeds = get_all_breeds()

    for bird in gemini_result.get("birds", []):
        breed = bird.get("breed", "")
        if not breed or breed == "Desconocida":
            continue

        breed_low = breed.strip().lower()

        # Exact match → ok
        if breed_low in valid_breeds:
            continue

        # Partial match: "Sussex Silver" contains "sussex" which is in census
        partial = None
        for vb in valid_breeds:
            if vb in breed_low or breed_low in vb:
                partial = vb
                break

        if partial:
            # Gemini dijo algo más específico que el censo (ej "Sussex Silver" vs "Sussex")
            # Aceptar como válido, mantener el nombre de Gemini (más específico)
            continue

        # Fuzzy match (typos)
        match = None
        for vb in valid_breeds:
            if _fuzzy_match(breed_low, vb):
                match = vb
                break

        if match:
            # Corregir al nombre canónico del censo
            corrected = get_canonical_breed_name(match)
            logger.debug(f"Census correction: '{breed}' → '{corrected}'")
            bird["breed"] = corrected
        else:
            logger.info(f"[Census] Raza '{breed}' no existe en la cabaña — marcada como Desconocida")
            bird["breed"] = "Desconocida"
            bird["confidence"] = min(bird.get("confidence", 0.5), 0.3)
            bird["distinguishing_features"] = (
                bird.get("distinguishing_features", "") +
                f" (Gemini dijo: {breed}, no en censo)"
            )


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
    """Ejecuta tracker + pest alerts + health en cada ciclo YOLO."""
    try:
        from services.yolo_detector import detect
        from services.bird_tracker import get_tracker
        from services.pest_alert import get_pest_manager
        from services.health_analyzer import get_growth_tracker

        result = detect(frame_bytes)
        if not result or not result.get("detections"):
            return

        # 1. Tracking: actualizar posiciones
        tracker = get_tracker(gallinero_id)
        tracker.update(result["detections"])

        # 2. Pest alerts
        if result.get("pest_count", 0) > 0:
            pest_mgr = get_pest_manager()
            alerts = pest_mgr.process_detections(gallinero_id, result)
            if alerts:
                logger.warning(
                    f"[{gallinero_id}] Pest alerts: "
                    f"{[a['pest_type'] for a in alerts]}"
                )

        # 3. Growth tracking (registrar tamaños)
        growth = get_growth_tracker()
        for t in tracker.tracks.values():
            if t.active and t.sizes:
                growth.record(t.track_id, t.sizes[-1])

    except Exception as e:
        logger.debug(f"Tracking enrichment failed ({gallinero_id}): {e}")


# Mapeo stream go2rtc → nombre gallinero en OvoSfera
_STREAM_TO_GALLINERO_NAME = {
    "gallinero_durrif": "Gallinero Durrif",
    "gallinero_durrif_1": "Gallinero Durrif",
    "gallinero_durrif_2": "Gallinero Durrif",
    "sauna_durrif_1": "Gallinero Durrif",
}


# Mapeo gallinero_stream → ID de gallinero en OvoSfera
_STREAM_TO_GALLINERO_ID = {
    "gallinero_durrif": 2,
    "gallinero_durrif_1": 2,
    "gallinero_durrif_2": 2,
    "sauna_durrif_1": 2,
}


async def _sync_vision_id_to_ovosfera(
    vision_id: str, breed: str, color: str, sex: str,
    gallinero_stream: str, photo_b64: str | None = None,
):
    """Sincroniza ai_vision_id, gallinero y foto a OvoSfera.

    Matching: breed (con aliases) + sex. Color como desempate.
    Foto: sube el crop como data URI si disponible.
    Gallinero: asigna el nombre (String, no FK).
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
            if gallinero_name:
                update_payload["gallinero"] = gallinero_name
            if photo_b64:
                update_payload["foto"] = f"data:image/jpeg;base64,{photo_b64}"

            await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave['id']}",
                json=update_payload,
            )
            logger.info(
                f"✅ Synced '{vision_id}' → OvoSfera ave {ave['id']} "
                f"({ave.get('anilla','')}) raza={ave.get('raza')} "
                f"gallinero='{gallinero_name}' foto={'SI' if photo_b64 else 'NO'}"
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


def _normalize_to_census(gallinero_id: str, breed: str, color: str, sex: str) -> tuple[str, str, str]:
    """Normaliza breed/color/sex al censo de la cabaña.

    Si Gemini dice "Marrans negro cobrizo" pero el censo dice "Marans negro cobrizo",
    lo corrige. Usa fuzzy matching simple (Levenshtein no necesario para razas cortas).
    """
    try:
        from services.flock_census import get_expected_breeds
    except ImportError:
        return breed, color, sex

    entries = get_expected_breeds(gallinero_id)
    if not entries:
        return breed, color, sex

    breed_low = breed.lower().strip()
    color_low = color.lower().strip()

    # Exact match first
    for e in entries:
        if e["raza"].lower() == breed_low and e["color"].lower() == color_low:
            return e["raza"], e["color"], sex

    # Breed match only (color may differ slightly)
    for e in entries:
        if e["raza"].lower() == breed_low:
            # Check if colors are similar (one contains the other)
            ec = e["color"].lower()
            if ec in color_low or color_low in ec:
                return e["raza"], e["color"], sex

    # Fuzzy breed match: Gemini typos like "Marrans" → "Marans"
    for e in entries:
        census_breed = e["raza"].lower()
        # Simple: if >=80% chars match in sequence
        if _fuzzy_match(breed_low, census_breed):
            ec = e["color"].lower()
            if ec in color_low or color_low in ec or not color_low:
                return e["raza"], e["color"], sex

    return breed, color, sex


def _fuzzy_match(a: str, b: str) -> bool:
    """Simple fuzzy match: True if strings differ by at most 2 chars."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 2:
        return False
    # Count differing chars at each position (longer vs shorter)
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    diffs = sum(1 for i, c in enumerate(short) if i < len(long) and c != long[i])
    diffs += len(long) - len(short)
    return diffs <= 2


def _crop_bird_photo(frame_bytes: bytes, bbox_norm: list[float], padding: float = 0.15,
                     expected_breed: str = "") -> tuple[str, int, int] | None:
    """Recorta la zona del ave del frame y devuelve (JPEG base64, width, height).

    Args:
        bbox_norm: [x1, y1, x2, y2] normalizadas 0-1
        padding: margen extra alrededor del bbox (15% para capturar ave completa)
        expected_breed: si se indica, valida con breed YOLO que el crop corresponde

    Returns:
        (base64_str, crop_width, crop_height) o None si falla
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(frame_bytes))
        W, H = img.size
        x1, y1, x2, y2 = bbox_norm
        # Añadir padding generoso para capturar ave completa
        pw = (x2 - x1) * padding
        ph = (y2 - y1) * padding
        left = max(0, int((x1 - pw) * W))
        top = max(0, int((y1 - ph) * H))
        right = min(W, int((x2 + pw) * W))
        bottom = min(H, int((y2 + ph) * H))

        crop = img.crop((left, top, right, bottom))

        # Validar con breed YOLO si se espera una raza concreta
        if expected_breed:
            try:
                from services.yolo_detector import classify_breed_crop
                buf_check = io.BytesIO()
                crop.save(buf_check, format="JPEG", quality=85)
                breed_pred = classify_breed_crop(buf_check.getvalue())
                if breed_pred and breed_pred["confidence"] >= 0.35:
                    predicted = _BREED_YOLO_TO_CENSUS.get(breed_pred["breed_class"], ("", "", ""))[0]
                    if predicted.lower() != expected_breed.lower():
                        logger.debug(
                            f"Photo crop mismatch: expected {expected_breed}, "
                            f"got {predicted} ({breed_pred['confidence']:.0%}) — skipping"
                        )
                        return None
            except Exception:
                pass  # Si falla la validación, se usa el crop igualmente

        # Resize to max 1024px wide keeping aspect (high quality for review)
        if crop.width > 1024:
            ratio = 1024 / crop.width
            crop = crop.resize((1024, int(crop.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode(), crop.width, crop.height
    except Exception as e:
        logger.debug(f"Crop failed: {e}")
        return None


def _make_thumbnail(frame_bytes: bytes, size: int = 256) -> str | None:
    """Genera thumbnail del frame completo como fallback."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(frame_bytes))
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


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

                    # Intentar mejorar foto si la confianza es mayor
                    crop_upgrade = None
                    if best_conf > stored_conf and best_conf >= 0.7 and frame_bytes:
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

                for i in range(new_count):
                    # Crop individual si tenemos bbox
                    crop_b64 = None
                    bbox_idx = have_n + i  # index into the group's bboxes
                    if frame_bytes and bbox_idx < len(bboxes) and len(bboxes[bbox_idx]) == 4:
                        crop_result = _crop_bird_photo(frame_bytes, bboxes[bbox_idx], expected_breed=breed)
                        if crop_result:
                            crop_b64 = crop_result[0]

                    # Fallback: thumbnail del frame completo
                    if not crop_b64 and frame_bytes:
                        crop_b64 = _make_thumbnail(frame_bytes)

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
    """Loop principal: captura y analiza frames periódicamente.

    Estrategia híbrida:
    - Cada 15s: YOLO (conteo rápido, guarda training data)
    - Cada 120s: YOLO + Gemini (identificación de raza si hay aves nuevas)
    """
    global _running, _last_results
    _running = True
    _cycle = 0
    QUICK_INTERVAL = 15   # YOLO solo (rápido)
    FULL_INTERVAL = 8     # cada 8 ciclos × 15s = 120s → Gemini

    logger.info("🐔 Bird identification loop started (YOLO + Gemini hybrid)")

    while _running:
        _cycle += 1
        is_full_cycle = (_cycle % FULL_INTERVAL == 0)

        for gallinero_id, cam_config in CAMERAS.items():
            if not _running:
                break

            is_distant = cam_config.get("distant", False)
            cam_imgsz = cam_config.get("yolo_imgsz")
            use_tiled = cam_config.get("use_tiled", False)
            use_breed = cam_config.get("use_breed", False)

            # CGI directo para todos los ciclos (~100ms); fallback go2rtc
            # Cámaras lejanas: siempre stream principal (4K) para no perder resolución
            snap_url = cam_config.get("snapshot_url", "")
            snap_auth = tuple(cam_config.get("snapshot_auth", ("admin", "123456")))
            if is_full_cycle or is_distant:
                frame = await _capture_frame(cam_config["stream"], snapshot_url=snap_url, snapshot_auth=snap_auth)
            else:
                frame = await _capture_frame(cam_config["stream"], use_sub=True, snapshot_url=snap_url, snapshot_auth=snap_auth)
            if not frame:
                continue

            if is_full_cycle:
                # Ciclo completo: YOLO + Gemini (identificación de raza)
                analysis = await _analyze_frame(
                    frame, gallinero_id,
                    imgsz=cam_imgsz,
                    use_tiled=use_tiled,
                    use_breed=use_breed,
                    force_gemini=is_distant,
                )
            else:
                # Ciclo rápido: solo YOLO (conteo + training data)
                yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled, use_breed=use_breed, camera_id=gallinero_id)
                if yolo_result and yolo_result["detections"]:
                    try:
                        from services.yolo_trainer import save_confirmed_detection
                        save_confirmed_detection(
                            frame, yolo_result["detections"], split="auto",
                        )
                    except Exception:
                        pass
                analysis = {
                    "birds": [],
                    "total_visible": yolo_result["count"] if yolo_result else 0,
                    "conditions": f"YOLO quick scan ({yolo_result['inference_ms']:.0f}ms)" if yolo_result else "no detection",
                    "yolo_only": True,
                } if yolo_result else None

            if not analysis:
                continue

            # ── Tracking + pest alerts + health (cada ciclo) ──
            _enrich_with_tracking(gallinero_id, frame)

            _last_results[gallinero_id] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis": analysis,
                "camera": cam_config["name"],
                "cycle": _cycle,
                "full_analysis": is_full_cycle,
            }

            # Registrar/actualizar aves detectadas (solo en ciclos completos)
            if is_full_cycle:
                detected_birds = analysis.get("birds", [])
                await _register_or_update_birds(detected_birds, gallinero_id, frame)
                logger.info(
                    f"[{cam_config['name']}] Full cycle: {len(detected_birds)} birds ID'd, "
                    f"total_visible={analysis.get('total_visible', '?')}"
                )
            else:
                count = analysis.get("total_visible", 0)
                if count > 0:
                    logger.debug(
                        f"[{cam_config['name']}] Quick scan: {count} aves "
                        f"({analysis.get('conditions', '')})"
                    )

        await asyncio.sleep(QUICK_INTERVAL)

    logger.info("🐔 Bird identification loop stopped")


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
    """Estado actual del identificador."""
    return {
        "running": _running,
        "last_results": _last_results,
        "cameras_configured": list(CAMERAS.keys()),
    }


@router.post("/snapshot/{gallinero_id}")
async def snapshot_identify(gallinero_id: str):
    """Captura un frame ahora y lo analiza (one-shot)."""
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
        frame,
        gallinero_id,
        imgsz=cam.get("yolo_imgsz"),
        use_tiled=cam.get("use_tiled", False),
        use_breed=cam.get("use_breed", False),
        force_gemini=is_distant,
    )
    if not analysis:
        raise HTTPException(503, "Gemini no pudo analizar la imagen")

    # Registrar aves detectadas (comparación por conteo)
    await _register_or_update_birds(analysis.get("birds", []), gallinero_id, frame)

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
    use_breed = cam.get("use_breed", False)
    census_gid = cam.get("gallinero", gallinero_id)

    # Breed model necesita resolución alta
    needs_hires = use_breed or is_distant
    frame = await _capture_from_cam(cam, force_hires=needs_hires)
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    cam_imgsz = cam.get("yolo_imgsz")
    use_tiled = cam.get("use_tiled", False)

    analysis = await _analyze_frame(
        frame, census_gid,
        imgsz=cam_imgsz,
        use_tiled=use_tiled,
        use_breed=use_breed,
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

    # Registrar nuevas aves — usar census_gid para que se asignen al gallinero correcto
    await _register_or_update_birds(birds, census_gid, frame)

    # Dibujar anotaciones
    annotated = _draw_annotations(frame, birds, census_gid)

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
    use_breed = cam.get("use_breed", False)
    census_gid = cam.get("gallinero", gallinero_id)

    # Breed model necesita resolución alta (4K→resize interno YOLO)
    # Sub-stream 704×576 produce 0 detecciones con breed model
    needs_hires = use_breed or is_distant
    frame = await _capture_from_cam(
        cam,
        use_sub=not needs_hires,
        force_hires=needs_hires,
    )
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled, use_breed=use_breed, camera_id=gallinero_id)
    if not yolo_result or not yolo_result["detections"]:
        return Response(content=frame, media_type="image/jpeg",
                        headers={"X-Birds-Detected": "0", "X-Engine": "yolo"})

    # v4: usar draw_detections del detector v4 si disponible
    try:
        from services.yolo_detector_v4 import get_detector
        annotated = get_detector().draw_detections(frame, yolo_result["detections"], cam["name"])
    except Exception:
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


@router.get("/snapshot/{gallinero_id}/detect")
async def snapshot_detect_json(gallinero_id: str):
    """Captura + YOLO → JSON con detecciones + frame base64 + crops.

    Usado por el modo ID Manual para dibujar bboxes en canvas
    y permitir asignación individual de cada detección a un ave.
    """
    if gallinero_id not in CAMERAS:
        raise HTTPException(404, f"Gallinero {gallinero_id} no configurado")

    cam = CAMERAS[gallinero_id]
    is_distant = cam.get("distant", False)
    cam_imgsz = cam.get("yolo_imgsz")
    use_tiled = cam.get("use_tiled", False)
    use_breed = cam.get("use_breed", False)
    census_gid = cam.get("gallinero", gallinero_id)

    # Breed model necesita resolución alta
    needs_hires = use_breed or is_distant
    frame = await _capture_from_cam(
        cam,
        use_sub=not needs_hires,
        force_hires=needs_hires,
    )
    if not frame:
        raise HTTPException(503, f"No se pudo capturar frame de {cam['name']}")

    yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled,
                                    use_breed=use_breed, camera_id=gallinero_id)
    detections_out = []

    if yolo_result and yolo_result.get("detections"):
        for idx, det in enumerate(yolo_result["detections"]):
            # v4: crop_bytes ya viene del detector; fallback a legacy crop_detections
            crop_b64 = ""
            crop_raw = det.get("crop_bytes", b"")
            if crop_raw:
                crop_b64 = base64.b64encode(crop_raw).decode()
            else:
                try:
                    from services.yolo_detector import crop_detections
                    crops = crop_detections(frame, [det])
                    if crops and crops[0]:
                        crop_b64 = base64.b64encode(crops[0]).decode()
                except Exception:
                    pass

            # Breed info del v4 o legacy
            breed_name = det.get("breed", det.get("class_name", "sin_clasificar"))
            breed_conf = det.get("breed_conf", det.get("confidence", 0))
            coco_class = det.get("coco_class", "")

            # Extraer sexo del nombre de clase (e.g. sussex_silver_gallo → M)
            breed_sex = ""
            if breed_name.endswith("_gallo") or breed_name.endswith("_male"):
                breed_sex = "M"
            elif breed_name.endswith("_gallina") or breed_name.endswith("_female"):
                breed_sex = "H"

            detections_out.append({
                "index": idx,
                "bbox": det.get("bbox_norm", det.get("bbox", [])),
                "breed_guess": breed_name,
                "breed_confidence": breed_conf,
                "breed_color": "",
                "breed_sex": breed_sex,
                "coco_class": coco_class,
                "crop_b64": crop_b64,
            })

    # Resize frame for browser display (4K → 1920 max, ~200KB vs 1.5MB)
    from PIL import Image as _PilImg
    _pil = _PilImg.open(io.BytesIO(frame))
    _fw, _fh = _pil.size
    _max_display = 1920
    if max(_fw, _fh) > _max_display:
        _sc = _max_display / max(_fw, _fh)
        _pil = _pil.resize((int(_fw * _sc), int(_fh * _sc)), _PilImg.LANCZOS)
    _buf = io.BytesIO()
    _pil.save(_buf, format="JPEG", quality=80)
    frame_b64 = base64.b64encode(_buf.getvalue()).decode()

    inference_ms = yolo_result["inference_ms"] if yolo_result else 0

    # Curación automática (Track A crops + Track B frames anotados)
    if yolo_result:
        await _curate_detections(frame, yolo_result, camera_id=gallinero_id)

    return {
        "detections": detections_out,
        "count": len(detections_out),
        "inference_ms": round(inference_ms, 1),
        "frame_b64": frame_b64,
        "frame_width": _fw,
        "frame_height": _fh,
    }


@router.post("/manual-assign")
async def manual_assign(payload: dict):
    """Asigna manualmente un crop de detección a un ave de OvoSfera.

    Body JSON:
      ove_ave_id: int  — ID del ave en OvoSfera
      crop_b64: str    — base64 del crop JPEG
      breed: str       — raza detectada
      color: str       — color (opcional)
      sex: str         — sexo M/H (opcional)
      gallinero: str   — stream name del gallinero
    """
    ove_ave_id = payload.get("ove_ave_id")
    crop_b64 = payload.get("crop_b64", "")
    breed = payload.get("breed", "")
    color = payload.get("color", "")
    sex = payload.get("sex", "")
    gallinero = payload.get("gallinero", "")

    if not ove_ave_id:
        raise HTTPException(400, "ove_ave_id requerido")

    gallinero_name = _STREAM_TO_GALLINERO_NAME.get(gallinero, "")

    update_payload = {}
    if gallinero_name:
        update_payload["gallinero"] = gallinero_name

    # Subir crop como foto del ave
    if crop_b64:
        prefix = "data:image/jpeg;base64,"
        if not crop_b64.startswith("data:"):
            crop_b64 = prefix + crop_b64
        update_payload["foto"] = crop_b64

    # Generar ai_vision_id si no tiene
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
            if resp.status_code != 200:
                raise HTTPException(502, "No se pudo consultar OvoSfera")
            aves = resp.json()
            ave = next((a for a in aves if a.get("id") == ove_ave_id), None)
            if not ave:
                raise HTTPException(404, f"Ave {ove_ave_id} no encontrada en OvoSfera")

            # Si no tiene ai_vision_id, generar uno
            if not ave.get("ai_vision_id"):
                breed_for_id = breed or ave.get("raza", "ave")
                color_for_id = color or ave.get("color", "")
                # Contar existentes con misma raza para secuencia
                existing_ids = [
                    a.get("ai_vision_id", "") for a in aves
                    if a.get("ai_vision_id")
                ]
                seq = 1
                while True:
                    candidate = _build_vision_id(breed_for_id, color_for_id, seq)
                    if candidate not in existing_ids:
                        break
                    seq += 1
                update_payload["ai_vision_id"] = candidate

            if update_payload:
                put_resp = await client.put(
                    f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ove_ave_id}",
                    json=update_payload,
                )
                if put_resp.status_code not in (200, 204):
                    raise HTTPException(502, f"Error actualizando ave: {put_resp.status_code}")

            logger.info(
                f"✅ Manual assign: OvoSfera ave {ove_ave_id} ({ave.get('anilla','')}) "
                f"→ {update_payload.get('ai_vision_id', ave.get('ai_vision_id',''))} "
                f"foto={'SI' if crop_b64 else 'NO'}"
            )

            return {
                "ok": True,
                "ave_id": ove_ave_id,
                "anilla": ave.get("anilla", ""),
                "ai_vision_id": update_payload.get("ai_vision_id", ave.get("ai_vision_id", "")),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual assign failed: {e}")
        raise HTTPException(500, f"Error interno: {e}")


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
        use_breed=cam.get("use_breed", False),
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

    result = _detect_with_yolo(frame, imgsz=cam.get("yolo_imgsz"), use_tiled=cam.get("use_tiled", False), use_breed=cam.get("use_breed", False), camera_id=gallinero_id)
    if not result:
        raise HTTPException(503, "YOLO no disponible")

    # Alimentar tracker, pest alerts y health con cada detección
    _enrich_with_tracking(gallinero_id, frame)

    # Curación automática (Track A crops + Track B frames anotados)
    await _curate_detections(frame, result, camera_id=gallinero_id)

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

    result = _detect_with_yolo(frame, imgsz=cam.get("yolo_imgsz"), use_tiled=cam.get("use_tiled", False), use_breed=cam.get("use_breed", False), camera_id=gallinero_id)
    if not result:
        raise HTTPException(503, "YOLO no disponible")

    try:
        from services.yolo_detector_v4 import get_detector
        annotated = get_detector().draw_detections(frame, result["detections"], cam["name"])
    except Exception:
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
            use_breed = cam.get("use_breed", False)
            yolo_result = _detect_with_yolo(frame, imgsz=imgsz, use_tiled=use_tiled, use_breed=use_breed, camera_id=gallinero_stream)
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
