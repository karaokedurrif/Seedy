"""
Seedy Backend — Router /ovosfera

Bridge entre Seedy y OvoSfera (hub.ovosfera.com).
- Mapa gallineros → cámaras (go2rtc streams)
- Proxy de frames/snapshots para embed en OvoSfera
- Sincronización de ai_vision_id hacia la API de OvoSfera
- Widget chat proxy (evita exponer API key en frontend)
- Chat con visión: Seedy puede ver las cámaras en tiempo real
"""

import base64
import logging
import os
import re
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ovosfera", tags=["ovosfera-bridge"])

# ── Config ──

OVOSFERA_API = os.environ.get("OVOSFERA_API_URL", "https://hub.ovosfera.com/api/ovosfera")
OVOSFERA_FARM = os.environ.get("OVOSFERA_FARM_SLUG", "palacio")
GO2RTC_URL = os.environ.get("GO2RTC_URL", "http://localhost:1984")

# Mapeo gallinero OvoSfera ID → stream go2rtc
GALLINERO_CAMERAS = {
    2: {
        "stream": "gallinero_durrif_1",
        "stream_sub": "gallinero_durrif_1_sub",
        "snapshot_url": "http://10.10.10.11/cgi-bin/snapshot.cgi",
        "name": "Gallinero Durrif I",
        "camera": "TP-Link VIGI C340 4K",
    },
    3: {
        "stream": "gallinero_durrif_2",
        "stream_sub": "gallinero_durrif_2_sub",
        "snapshot_url": "http://10.10.10.10/cgi-bin/snapshot.cgi",
        "name": "Gallinero Durrif II",
        "camera": "TP-Link VIGI C340 4K",
    },
}


# ── Gallineros + cámaras ──

@router.get("/gallineros")
async def get_gallineros_with_cameras():
    """Devuelve gallineros de OvoSfera enriquecidos con info de cámaras."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/gallineros")
            resp.raise_for_status()
            gallineros = resp.json()
    except Exception as e:
        logger.warning(f"Error fetching gallineros from OvoSfera: {e}")
        gallineros = []

    result = []
    for g in gallineros:
        gid = g.get("id")
        cam = GALLINERO_CAMERAS.get(gid)
        entry = {**g}
        if cam:
            entry["camera"] = {
                "stream": cam["stream"],
                "stream_sub": cam["stream_sub"],
                "model": cam["camera"],
                "snapshot_url": f"/ovosfera/camera/{gid}/snapshot",
                "webrtc_url": f"{GO2RTC_URL}/api/ws?src={cam['stream']}",
                "mjpeg_url": f"/ovosfera/camera/{gid}/mjpeg",
            }
        result.append(entry)
    return result


@router.get("/camera/{gallinero_id}/snapshot")
async def camera_snapshot(gallinero_id: int):
    """Proxy: captura un frame JPEG de la cámara (CGI directo ~100ms, fallback go2rtc)."""
    cam = GALLINERO_CAMERAS.get(gallinero_id)
    if not cam:
        raise HTTPException(404, f"No hay cámara configurada para gallinero {gallinero_id}")

    # Intento 1: CGI snapshot directo (704x576, ~100ms vs 5s de go2rtc)
    cgi_url = cam.get("snapshot_url")
    if cgi_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(cgi_url, auth=httpx.BasicAuth("admin", "123456"))
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return Response(
                        content=resp.content,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache, no-store"},
                    )
        except Exception as e:
            logger.debug(f"CGI snapshot failed for gallinero {gallinero_id}: {e}")

    # Fallback: go2rtc substream
    try:
        stream_key = cam.get('stream_sub', cam['stream'])
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{GO2RTC_URL}/api/frame.jpeg?src={stream_key}")
            if resp.status_code == 200:
                return Response(
                    content=resp.content,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache, no-store"},
                )
    except Exception as e:
        logger.warning(f"Snapshot fallback failed for gallinero {gallinero_id}: {e}")
    raise HTTPException(503, "No se pudo capturar frame de la cámara")


@router.get("/camera/{gallinero_id}/mjpeg")
async def camera_mjpeg(gallinero_id: int):
    """Proxy: stream MJPEG continuo desde go2rtc."""
    cam = GALLINERO_CAMERAS.get(gallinero_id)
    if not cam:
        raise HTTPException(404, f"No hay cámara configurada para gallinero {gallinero_id}")

    async def stream_generator():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "GET",
                    f"{GO2RTC_URL}/api/stream.mjpeg?src={cam['stream_sub']}",
                ) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        yield chunk
        except Exception as e:
            logger.warning(f"MJPEG stream ended for gallinero {gallinero_id}: {e}")

    return StreamingResponse(
        stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── go2rtc WebRTC signaling proxy ──

@router.post("/camera/{gallinero_id}/webrtc")
async def webrtc_offer(gallinero_id: int, request: Request):
    """Proxy WebRTC offer/answer via go2rtc API (para navegadores remotos)."""
    cam = GALLINERO_CAMERAS.get(gallinero_id)
    if not cam:
        raise HTTPException(404, f"No hay cámara para gallinero {gallinero_id}")

    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{GO2RTC_URL}/api/webrtc?src={cam['stream']}",
                content=body,
                headers={"Content-Type": request.headers.get("content-type", "application/sdp")},
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/sdp"),
            )
    except Exception as e:
        raise HTTPException(503, f"WebRTC signaling failed: {e}")


# ── Sincronización aves: Seedy vision → OvoSfera ──

@router.post("/sync/vision-id")
async def sync_vision_id(
    anilla: str,
    ai_vision_id: str,
    foto_url: str | None = None,
):
    """Actualiza el ai_vision_id de un ave en OvoSfera por su anilla."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Buscar ave por anilla
            resp = await client.get(f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves")
            resp.raise_for_status()
            aves = resp.json()
            ave = next((a for a in aves if a.get("anilla") == anilla), None)
            if not ave:
                raise HTTPException(404, f"Ave con anilla {anilla} no encontrada en OvoSfera")

            # Actualizar ai_vision_id
            update_data = {"ai_vision_id": ai_vision_id}
            if foto_url:
                update_data["foto"] = foto_url
            resp = await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave['id']}",
                json=update_data,
            )
            resp.raise_for_status()
            return {"ok": True, "ave_id": ave["id"], "anilla": anilla, "ai_vision_id": ai_vision_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error sincronizando vision ID: {e}")


@router.post("/sync/assign-gallinero")
async def assign_ave_to_gallinero(ave_id: int, gallinero_name: str):
    """Asigna un ave a un gallinero en OvoSfera."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{ave_id}",
                json={"gallinero": gallinero_name},
            )
            resp.raise_for_status()
            return {"ok": True, "ave_id": ave_id, "gallinero": gallinero_name}
    except Exception as e:
        raise HTTPException(500, f"Error asignando gallinero: {e}")


@router.post("/sync/bulk-assign")
async def bulk_assign_gallineros(assignments: list[dict]):
    """Asigna múltiples aves a gallineros.
    Body: [{"ave_id": 1, "gallinero": "Gallinero Durrif I"}, ...]
    """
    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for a in assignments:
            try:
                resp = await client.put(
                    f"{OVOSFERA_API}/farms/{OVOSFERA_FARM}/aves/{a['ave_id']}",
                    json={"gallinero": a["gallinero"]},
                )
                results.append({
                    "ave_id": a["ave_id"],
                    "gallinero": a["gallinero"],
                    "ok": resp.status_code == 200,
                })
            except Exception as e:
                results.append({"ave_id": a["ave_id"], "error": str(e)})
    return {"results": results}


# ── Chat proxy con visión en tiempo real ──

_SEEDY_CHAT_URL = "https://seedy-api.neofarm.io/v1/chat/completions"
_SEEDY_API_KEY = os.environ.get(
    "OVOSFERA_API_KEY",
    os.environ.get("SEEDY_OVOSFERA_KEY", ""),
)

SEEDY_SYSTEM_PROMPT = (
    "Eres Seedy 🌱, asistente IA de OvoSfera especializado en avicultura de razas "
    "selectas, capones, genética, nutrición y manejo de gallineros. "
    "Responde siempre en español de forma clara y práctica. "
    "Cuando sea relevante, incluye datos técnicos sobre razas, pesos, "
    "alimentación y sanidad avícola. "
    "Tienes acceso a las cámaras de los gallineros en tiempo real a través "
    "de tu sistema de visión IA."
)

# Patrones que indican que el usuario pregunta sobre el estado actual/visual
_VISION_KEYWORDS = re.compile(
    r"(c[áa]mara|ve[sr]|mira[r]?|observa|qu[ée]\s*(hay|pasa|ocurre|se\s*ve|ves)|"
    r"est[áa]n?\s*(ahora|durmiendo|acosta|despiert|com[ie]|fuera|dentro)|"
    r"cu[áa]ntas?\s*(hay|ves|gallinas|aves|pollos)|"
    r"se\s*han?\s*(acosta|dormido|levantado|ido|metido|salido)|"
    r"noche|oscur|amanec|anochec|dormir|dormid|despert|activ|movi|"
    r"d[ií]me\s*(qu[eé]|c[oó]mo)|ense[ñn]a|muestra|foto|snapshot|"
    r"estado\s*(del|de\s*los?)\s*gallinero|c[oó]mo\s*(est[áa]|van)|"
    r"todo\s*bien|alguna?\s*(novedad|problem))",
    re.IGNORECASE,
)

_VISION_SITUATION_PROMPT = """Describe brevemente lo que ves en esta imagen de un gallinero.
Responde en español, en 2-3 frases, indicando:
1. ¿Es de día o de noche? (si la imagen está oscura o hay poca luz → noche/atardecer)
2. ¿Cuántas aves se ven? ¿Están activas, descansando, en el suelo, en el aseladero?
3. ¿Alguna observación relevante? (comederos vacíos, puerta abierta/cerrada, condiciones del espacio)
Responde SOLO con la descripción, sin JSON."""


def _needs_vision(query: str) -> bool:
    """Detecta si la pregunta del usuario requiere mirar las cámaras."""
    return bool(_VISION_KEYWORDS.search(query))


async def _get_camera_situation() -> str:
    """Captura frames de todas las cámaras y devuelve un resumen situacional.

    Estrategia: YOLO primero (conteo rápido local), Gemini solo si YOLO
    detecta aves y queremos descripción detallada.
    """
    from services.gemini_vision import analyze_image

    now = datetime.now()
    hour = now.hour
    reports = []

    for gid, cam in GALLINERO_CAMERAS.items():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{GO2RTC_URL}/api/frame.jpeg?src={cam['stream']}"
                )
                if resp.status_code != 200 or len(resp.content) < 1000:
                    reports.append(f"📷 {cam['name']}: sin imagen disponible")
                    continue
                frame = resp.content
                frame_size_kb = len(frame) // 1024
        except Exception as e:
            reports.append(f"📷 {cam['name']}: cámara no accesible ({e})")
            continue

        # 1) YOLO: conteo rápido local (~50ms)
        yolo_report = ""
        try:
            from services.yolo_detector import detect_birds
            yolo_result = detect_birds(frame)
            yolo_count = yolo_result["count"]
            yolo_ms = yolo_result["inference_ms"]
            yolo_report = (
                f"YOLO detecta {yolo_count} aves ({yolo_ms:.0f}ms). "
            )
            if yolo_count == 0:
                yolo_report += "El gallinero parece vacío o las aves no son visibles."
        except Exception as e:
            logger.debug(f"YOLO failed for {cam['name']}: {e}")

        # 2) Gemini: descripción detallada (solo si YOLO ve aves o queremos más info)
        try:
            b64 = base64.b64encode(frame).decode()
            result = await analyze_image(
                image_b64=b64,
                question=_VISION_SITUATION_PROMPT,
                mime_type="image/jpeg",
                save_for_training=False,
            )
            answer = result.get("answer", "").strip()
            if answer:
                reports.append(f"📷 {cam['name']}: {yolo_report}{answer}")
            else:
                reports.append(f"📷 {cam['name']}: {yolo_report}(sin descripción detallada)")
        except Exception as e:
            logger.warning(f"Vision analysis failed for {cam['name']}: {e}")
            # Fallback: usar solo YOLO + contexto temporal
            if yolo_report:
                if hour >= 20 or hour < 7:
                    reports.append(
                        f"📷 {cam['name']}: {yolo_report}"
                        f"Son las {now.strftime('%H:%M')} (de noche), "
                        f"las gallinas suelen estar recogidas en el aseladero."
                    )
                else:
                    reports.append(f"📷 {cam['name']}: {yolo_report}")
            elif hour >= 20 or hour < 7:
                reports.append(
                    f"📷 {cam['name']}: imagen capturada ({frame_size_kb}KB) — "
                    f"son las {now.strftime('%H:%M')} (de noche), "
                    f"las gallinas suelen estar recogidas en el aseladero"
                )
            else:
                reports.append(
                    f"📷 {cam['name']}: imagen capturada ({frame_size_kb}KB) — "
                    f"análisis IA temporalmente no disponible"
                )

    header = f"🕐 Hora actual: {now.strftime('%H:%M')} ({now.strftime('%d/%m/%Y')})"
    # Añadir contexto temporal
    if hour >= 21 or hour < 6:
        header += " — Es de noche, las gallinas deberían estar recogidas durmiendo."
    elif hour >= 19:
        header += " — Atardecer/anochecer, las gallinas empiezan a recogerse."
    elif hour < 8:
        header += " — Amanecer, las gallinas empiezan a despertar."

    return header + "\n" + "\n".join(reports)


@router.post("/chat")
async def chat_proxy(request: Request):
    """Proxy de chat Seedy para OvoSfera — con visión en tiempo real."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "JSON inválido")

    messages = body.get("messages", [])
    stream = body.get("stream", True)

    # Detectar la última pregunta del usuario
    user_query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_query = m.get("content", "")
            break

    logger.info(f"[Chat] Query: {user_query[:100]} | needs_vision={_needs_vision(user_query)}")

    # Si la pregunta requiere visión → capturar cámaras y enriquecer contexto
    vision_context = ""
    if user_query and _needs_vision(user_query):
        logger.info(f"[Chat+Vision] Pregunta visual detectada: {user_query[:80]}")
        try:
            vision_context = await _get_camera_situation()
            logger.info(f"[Chat+Vision] Contexto visual: {vision_context[:200]}")
        except Exception as e:
            logger.warning(f"Vision context failed: {e}")
            vision_context = f"🕐 Hora actual: {datetime.now().strftime('%H:%M')}\n⚠️ No se pudieron consultar las cámaras."

    # Construir system prompt
    system_content = SEEDY_SYSTEM_PROMPT

    # Inyectar system prompt
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_content})
    else:
        messages[0]["content"] = system_content

    # Enriquecer el último mensaje del usuario con el contexto visual
    if vision_context:
        for m in reversed(messages):
            if m.get("role") == "user":
                m["content"] = (
                    f"{m['content']}\n\n"
                    f"[CONTEXTO VISUAL EN TIEMPO REAL DE LOS GALLINEROS — "
                    f"usa esta información para responder con certeza]\n"
                    f"{vision_context}"
                )
                break

    # Limitar historial a los últimos 10 mensajes + system
    if len(messages) > 11:
        messages = [messages[0]] + messages[-10:]

    payload = {
        "model": body.get("model", "seedy"),
        "messages": messages,
        "temperature": body.get("temperature", 0.3),
        "stream": stream,
    }

    if not stream:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    _SEEDY_CHAT_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {_SEEDY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type="application/json",
                )
        except Exception as e:
            raise HTTPException(503, f"Error contactando Seedy: {e}")

    # Streaming SSE
    async def sse_generator():
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    _SEEDY_CHAT_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {_SEEDY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    async for line in resp.aiter_lines():
                        yield line + "\n"
        except Exception as e:
            logger.warning(f"SSE stream error: {e}")
            yield f"data: {{\"error\": \"{e}\"}}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
