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
}

# Prompt especializado para identificar aves individuales
BIRD_ID_PROMPT = """Analiza esta imagen de un gallinero.

TAREA: Identifica CADA ave visible individualmente.

Para CADA ave que veas, devuelve EXACTAMENTE un bloque JSON con:
{
  "birds": [
    {
      "breed": "nombre de la raza (Sussex, Bresse, Marans, Orpington, Araucana, Sulmtaler, Andaluza Azul, Pita Pinta, Vorwerk, Castellana Negra, Cruce F1)",
      "color": "color principal del plumaje en español (blanco, negro, silver, dorado, azul, pardo, rojo, barrado, negro cobrizo, leonado, etc.)",
      "sex": "male" o "female" o "unknown",
      "confidence": 0.0-1.0,
      "bbox": [x1, y1, x2, y2],
      "distinguishing_features": "rasgos distintivos breves"
    }
  ],
  "total_visible": número total de aves visibles,
  "conditions": "breve descripción del gallinero (luz, actividad)"
}

REGLAS:
- Sé específico con la raza. Si hay varias aves parecidas de la misma raza, lístalas por separado.
- El campo 'color' es OBLIGATORIO: describe el color/variedad real del plumaje (blanco, negro, silver, dorado, azul, barrado, etc.).
  Ejemplos: Sussex blanco, Sussex silver (plateado), Marans negro cobrizo, Orpington leonado.
- bbox: coordenadas normalizadas [0.0-1.0] de la caja que encierra al ave [esquina_sup_izq_x, esquina_sup_izq_y, esquina_inf_der_x, esquina_inf_der_y]. Estima la posición lo mejor posible.
- Si el sexo es evidente (cresta grande, espolones, cola larga = male; más pequeña y redonda = female), indícalo.
- Confianza: 0.9+ si la raza es evidente, 0.5-0.8 si razonable, <0.5 si dudosa.
- Si hay aves pero no se distingue la raza, pon "breed": "Desconocida".
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

# Estado del loop
_running = False
_last_results: dict[str, dict] = {}
_task: asyncio.Task | None = None


async def _capture_frame(camera_stream: str, *, use_sub: bool = False, snapshot_url: str = "", force_hires: bool = False) -> bytes | None:
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
                resp = await client.get(snapshot_url, auth=httpx.BasicAuth("admin", "123456"))
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


async def _analyze_frame(frame_bytes: bytes, gallinero_id: str = "", *, imgsz: int | None = None, use_tiled: bool = False, force_gemini: bool = False) -> dict | None:
    """Análisis híbrido: YOLO (detección rápida) + Gemini (raza, solo si necesario).

    Args:
        imgsz: Resolución YOLO (para cámaras lejanas).
        use_tiled: Usar detección SAHI por tiles.
        force_gemini: Ejecutar Gemini incluso si YOLO no detecta nada (para cámaras lejanas).
    """
    # 1) YOLO: detección local (~50ms)
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

    # 3) Gemini: si YOLO detectó aves, o si force_gemini (cámaras lejanas)
    if yolo_count > 0 or force_gemini:
        gemini_result = await _identify_breeds_gemini(frame_bytes, gallinero_id)
        if gemini_result:
            # Enriquecer con datos YOLO (bboxes más precisos)
            _merge_yolo_gemini(yolo_result, gemini_result)
            return gemini_result

    # Sin aves detectadas por YOLO, o Gemini falló → devolver resultado YOLO básico
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
    "gallinero_durrif_1": "Gallinero Durrif I",
    "gallinero_durrif_2": "Gallinero Durrif II",
}


# Mapeo gallinero_stream → ID de gallinero en OvoSfera
_STREAM_TO_GALLINERO_ID = {
    "gallinero_durrif_1": 2,
    "gallinero_durrif_2": 3,
}


async def _sync_vision_id_to_ovosfera(vision_id: str, breed: str, gallinero_stream: str):
    """Sincroniza ai_vision_id y gallinero a OvoSfera.

    Busca un ave de la misma raza sin ai_vision_id asignado,
    le escribe el vision_id y la asigna al gallinero correcto.
    """
    gallinero_name = _STREAM_TO_GALLINERO_NAME.get(gallinero_stream, gallinero_stream)
    gallinero_ovo_id = _STREAM_TO_GALLINERO_ID.get(gallinero_stream)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
            if resp.status_code != 200:
                return
            aves = resp.json()

            # Primero: ¿ya existe un ave con ESTE vision_id? → ya sincronizada
            if any(a.get("ai_vision_id") == vision_id for a in aves):
                return

            # Buscar ave de misma raza sin ai_vision_id (sin importar gallinero,
            # porque empiezan todas "sin asignar")
            candidates = [
                a for a in aves
                if a.get("raza", "").lower() == breed.lower()
                and not a.get("ai_vision_id")
            ]
            if not candidates:
                logger.debug(f"No unassigned OvoSfera ave for breed={breed}")
                return

            ave = candidates[0]
            update_payload = {"ai_vision_id": vision_id}
            if gallinero_ovo_id:
                update_payload["gallinero"] = gallinero_ovo_id

            await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave['id']}",
                json=update_payload,
            )
            logger.info(
                f"Synced '{vision_id}' → OvoSfera ave {ave['id']} ({ave.get('anilla','')}), "
                f"gallinero={gallinero_name}"
            )
    except Exception as e:
        logger.debug(f"OvoSfera sync failed: {e}")


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


def _crop_bird_photo(frame_bytes: bytes, bbox_norm: list[float], padding: float = 0.05) -> str | None:
    """Recorta la zona del ave del frame y devuelve JPEG base64.

    Args:
        bbox_norm: [x1, y1, x2, y2] normalizadas 0-1
        padding: margen extra alrededor del bbox (5%)
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(frame_bytes))
        W, H = img.size
        x1, y1, x2, y2 = bbox_norm
        # Añadir padding
        pw = (x2 - x1) * padding
        ph = (y2 - y1) * padding
        left = max(0, int((x1 - pw) * W))
        top = max(0, int((y1 - ph) * H))
        right = min(W, int((x2 + pw) * W))
        bottom = min(H, int((y2 + ph) * H))

        crop = img.crop((left, top, right, bottom))
        # Resize to max 512px wide keeping aspect
        if crop.width > 512:
            ratio = 512 / crop.width
            crop = crop.resize((512, int(crop.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
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
    4. Sincronizar con OvoSfera
    """
    import httpx
    from collections import Counter

    # Contar cuántas aves de cada (breed, color, sex) ha detectado Gemini
    seen_counts: Counter[tuple[str, str, str]] = Counter()
    bird_bboxes: dict[tuple[str, str, str], list] = {}  # acumular bboxes por grupo
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
        bird_bboxes[key].append(bird.get("bbox", []))

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

                # Actualizar sighting de las que ya tenemos
                for bird_rec in existing:
                    await client.post(
                        f"/birds/{bird_rec['bird_id']}/sighting",
                        params={"confidence": 0.5},
                    )

                # Cuántas nuevas registrar — respetando cuota
                new_count = max(0, seen_n - have_n)
                if quota > 0:
                    new_count = min(new_count, max(0, quota - have_n))

                bboxes = bird_bboxes.get((breed, color, sex), [])
                for i in range(new_count):
                    # Crop individual si tenemos bbox
                    crop_b64 = None
                    bbox_idx = have_n + i  # index into the group's bboxes
                    if frame_bytes and bbox_idx < len(bboxes) and len(bboxes[bbox_idx]) == 4:
                        crop_b64 = _crop_bird_photo(frame_bytes, bboxes[bbox_idx])

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
                            f"🐔 New bird: {breed} {color} → {vision_id} "
                            f"in {gallinero} ({have_n + i + 1}/{quota or '∞'})"
                        )
                        if vision_id:
                            await _sync_vision_id_to_ovosfera(vision_id, breed, gallinero)

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

            # CGI directo para todos los ciclos (~100ms); fallback go2rtc
            # Cámaras lejanas: siempre stream principal (4K) para no perder resolución
            snap_url = cam_config.get("snapshot_url", "")
            if is_full_cycle or is_distant:
                frame = await _capture_frame(cam_config["stream"], snapshot_url=snap_url)
            else:
                frame = await _capture_frame(cam_config["stream"], use_sub=True, snapshot_url=snap_url)
            if not frame:
                continue

            if is_full_cycle:
                # Ciclo completo: YOLO + Gemini (identificación de raza)
                analysis = await _analyze_frame(
                    frame, gallinero_id,
                    imgsz=cam_imgsz,
                    use_tiled=use_tiled,
                    force_gemini=is_distant,
                )
            else:
                # Ciclo rápido: solo YOLO (conteo + training data)
                yolo_result = _detect_with_yolo(frame, imgsz=cam_imgsz, use_tiled=use_tiled)
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
    frame = await _capture_frame(
        cam["stream"],
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
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

    # Cámaras lejanas: go2rtc 4K directo; normales: CGI rápido
    frame = await _capture_frame(
        cam["stream"],
        use_sub=not is_distant,
        snapshot_url=cam.get("snapshot_url", ""),
        force_hires=is_distant,
    )
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
