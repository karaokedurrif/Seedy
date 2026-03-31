"""
Seedy Backend — Vision ID Service (Together.ai → Gemini fallback)

Identifica razas de aves usando Together.ai VL models (serverless) con
fallback automático a Gemini 2.5 Flash cuando Together no está disponible.

El prompt recibe el CENSO del gallinero para restringir la identificación
a razas que realmente existen en la cabaña.
"""

import json
import logging
import httpx

from config import get_settings

logger = logging.getLogger(__name__)

# Track Together availability to skip retries after first failure
_together_available: bool | None = None  # None = not tested yet

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


def _build_census_block(breeds: list[dict]) -> str:
    """Formatea el censo del gallinero para el prompt.

    breeds: list of {"raza": "Sussex", "color": "blanco", "sexo": "gallina", "cantidad": 3}
    """
    if not breeds:
        return "No hay censo disponible — identifica libremente."
    lines = []
    for b in breeds:
        qty = b.get("cantidad", "?")
        sex = b.get("sexo", "")
        lines.append(f"- {b['raza']} ({b.get('color', '?')}), {sex}, ×{qty}")
    return "\n".join(lines)


_SYSTEM_PROMPT = """Eres un experto avicultor veterinario especializado en identificación visual de razas de gallinas.
Analiza la fotografía proporcionada con máximo rigor."""


def _build_user_prompt(census_block: str) -> str:
    return f"""Analiza esta fotografía de un ave de corral capturada por una cámara en un gallinero.

CENSO DEL GALLINERO (razas presentes):
{census_block}

INSTRUCCIONES:
1. OBSERVA con detalle: plumaje (color base, patrón, reflejos), cresta (tipo, tamaño, color),
   barbillas, tarsos (color, escamas), porte corporal, cola.
2. IDENTIFICA la raza más probable del censo. Si no coincide con ninguna, indica "desconocida".
3. EVALÚA la calidad de la imagen: ¿permite identificar con certeza?

CLAVES PARA NO CONFUNDIR:
- Sussex White vs Bresse: Sussex tiene rayas negras en cuello (armiñada), Bresse es blanca pura con patas gris azulado.
- Pita Pinta vs Sussex White: Pita Pinta tiene motas/puntos negros distribuidos por todo el cuerpo.
- Vorwerk vs Sulmtaler: Vorwerk tiene cuello/cola negro con cuerpo dorado. Sulmtaler es trigueño atigrado sin contraste marcado.
- Marans: negro cobrizo con reflejos cobrizos en cuello, tarsos ligeramente emplumados.
- Araucana: sin cola (rumpless), mejillas con mechón, forma compacta.

RESPONDE SOLO con este JSON (sin markdown, sin texto fuera del JSON):
{{
  "breed": "nombre de raza exacto del censo o desconocida",
  "color": "color/variedad del plumaje",
  "sex": "gallina|gallo|indeterminado",
  "confidence": 0.0-1.0,
  "distinctive_features": ["rasgo 1", "rasgo 2", "rasgo 3"],
  "image_quality": "buena|aceptable|mala",
  "reasoning": "explicación breve de por qué esta raza y no otra del censo"
}}"""


async def identify_bird(
    image_b64: str,
    census_breeds: list[dict],
    mime_type: str = "image/jpeg",
) -> dict:
    """Identifica un ave usando Together.ai VL → Gemini fallback.

    Args:
        image_b64: Imagen del crop en base64 (sin prefijo data:...)
        census_breeds: Lista de razas del gallinero (del flock_census)
        mime_type: Tipo MIME (image/jpeg, image/png)

    Returns:
        dict con breed, color, sex, confidence, distinctive_features,
        image_quality, reasoning, model, usage
    """
    global _together_available
    settings = get_settings()

    census_block = _build_census_block(census_breeds)
    user_prompt = _build_user_prompt(census_block)

    # ── Try Together.ai first (if available) ──
    if settings.together_api_key and _together_available is not False:
        try:
            result = await _call_together(image_b64, user_prompt, mime_type, settings)
            _together_available = True
            return result
        except RuntimeError as e:
            if "400" in str(e) or "non-serverless" in str(e).lower():
                _together_available = False
                logger.warning("Together Vision models not available (non-serverless), switching to Gemini")
            else:
                logger.warning(f"Together Vision failed: {e}, trying Gemini fallback")

    # ── Gemini fallback ──
    if settings.gemini_api_key:
        try:
            result = await _call_gemini(image_b64, user_prompt, census_block, mime_type)
            return result
        except Exception as e:
            logger.error(f"Gemini Vision also failed: {e}")
            raise RuntimeError(f"All vision backends failed. Together: unavailable, Gemini: {e}")

    raise RuntimeError("No vision API configured (need TOGETHER_API_KEY or GEMINI_API_KEY)")


async def _call_together(
    image_b64: str, user_prompt: str, mime_type: str, settings
) -> dict:
    """Call Together.ai VL model."""
    payload = {
        "model": settings.together_vision_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}",
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ],
        "max_tokens": 512,
        "temperature": 0.1,
        "top_p": 0.9,
    }

    client = _get_client()
    resp = await client.post(
        f"{settings.together_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.together_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    if resp.status_code != 200:
        logger.error(f"Together Vision API error {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError(f"Together API error: {resp.status_code}")

    data = resp.json()
    raw = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    model = data.get("model", settings.together_vision_model)

    return _parse_vision_response(raw, model, usage)


async def _call_gemini(
    image_b64: str, user_prompt: str, census_block: str, mime_type: str
) -> dict:
    """Call Gemini Vision as fallback."""
    from services.gemini_vision import analyze_image

    # Use the structured ID prompt (not the generic gemini_vision prompt)
    gemini_result = await analyze_image(
        image_b64=image_b64,
        question=user_prompt,
        mime_type=mime_type,
        save_for_training=True,
    )

    raw = gemini_result.get("answer", "")
    model = gemini_result.get("model", "gemini-2.5-flash")

    result = _parse_vision_response(raw, model, {})
    logger.info(
        f"🔍 Gemini Vision fallback: {result.get('breed', '?')} "
        f"({result.get('confidence', 0):.0%}) — {result.get('reasoning', '')[:80]}"
    )
    return result


def _parse_vision_response(raw: str, model: str, usage: dict) -> dict:
    """Parse JSON from vision model response."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    # Find JSON block in text
    start = text.find("{")
    end = text.rfind("}") + 1

    try:
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
        else:
            result = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Vision response not valid JSON: {text[:200]}")
        result = {
            "breed": "desconocida",
            "color": "",
            "sex": "indeterminado",
            "confidence": 0.0,
            "distinctive_features": [],
            "image_quality": "mala",
            "reasoning": f"Respuesta no-JSON del modelo: {text[:100]}",
        }

    result["model"] = model
    result["usage"] = usage
    logger.info(
        f"🔍 Vision ID: {result.get('breed', '?')} "
        f"({result.get('confidence', 0):.0%}) via {model}"
    )
    return result
