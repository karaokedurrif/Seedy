"""
Seedy — Vision Gallery Helpers

Bird photo gallery management: crop, thumbnail, contact sheet, and
visual re-identification via Together.ai Vision.
Extracted from routers/vision_identify.py.
"""

import base64
import io
import json
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


def crop_bird_photo(
    frame_bytes: bytes,
    bbox_norm: list[float],
    padding: float = 0.15,
    expected_breed: str = "",
) -> tuple[str, int, int] | None:
    """Recorta la zona del ave del frame y devuelve (JPEG base64, width, height).

    Args:
        bbox_norm: [x1, y1, x2, y2] normalizadas 0-1
        padding: margen extra alrededor del bbox (15% para capturar ave completa)
        expected_breed: si se indica, valida con breed YOLO que el crop corresponde

    Returns:
        (base64_str, crop_width, crop_height) o None si falla
    """
    from services.vision_breeds import BREED_YOLO_TO_CENSUS

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(frame_bytes))
        W, H = img.size
        x1, y1, x2, y2 = bbox_norm
        pw = (x2 - x1) * padding
        ph = (y2 - y1) * padding
        left = max(0, int((x1 - pw) * W))
        top = max(0, int((y1 - ph) * H))
        right = min(W, int((x2 + pw) * W))
        bottom = min(H, int((y2 + ph) * H))

        crop = img.crop((left, top, right, bottom))

        if expected_breed:
            try:
                from services.yolo_detector import classify_breed_crop
                buf_check = io.BytesIO()
                crop.save(buf_check, format="JPEG", quality=85)
                breed_pred = classify_breed_crop(buf_check.getvalue())
                if breed_pred and breed_pred["confidence"] >= 0.35:
                    predicted = BREED_YOLO_TO_CENSUS.get(breed_pred["breed_class"], ("", "", ""))[0]
                    if predicted.lower() != expected_breed.lower():
                        logger.debug(
                            f"Photo crop mismatch: expected {expected_breed}, "
                            f"got {predicted} ({breed_pred['confidence']:.0%}) — skipping"
                        )
                        return None
            except Exception:
                pass

        if crop.width > 1024:
            ratio = 1024 / crop.width
            crop = crop.resize((1024, int(crop.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode(), crop.width, crop.height
    except Exception as e:
        logger.debug(f"Crop failed: {e}")
        return None


def make_thumbnail(frame_bytes: bytes, size: int = 256) -> str | None:
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


def save_crop_to_gallery(ave_id: int, crop_b64: str, breed: str, color: str, sex: str):
    """Guarda crop en /app/data/bird_gallery/<ave_id>/ para acumular fotos de referencia."""
    if not crop_b64:
        return
    try:
        from pathlib import Path
        gallery_dir = Path(f"/app/data/bird_gallery/{ave_id}")
        gallery_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        raw_b64 = crop_b64.split(",", 1)[-1] if "," in crop_b64 else crop_b64
        img_data = base64.b64decode(raw_b64)
        (gallery_dir / f"{ts}.jpg").write_bytes(img_data)
        meta_path = gallery_dir / "meta.json"
        meta = {"breed": breed, "color": color, "sex": sex, "ave_id": ave_id}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False))
        n_photos = len(list(gallery_dir.glob("*.jpg")))
        logger.info(f"📸 Gallery: ave {ave_id} now has {n_photos} reference photo(s)")
    except Exception as e:
        logger.debug(f"Gallery save failed for ave {ave_id}: {e}")


def get_gallery_photos(ave_id: int, max_photos: int = 3) -> list[str]:
    """Obtiene las últimas N fotos de la galería local como base64."""
    from pathlib import Path
    gallery_dir = Path(f"/app/data/bird_gallery/{ave_id}")
    if not gallery_dir.exists():
        return []
    photos = sorted(gallery_dir.glob("*.jpg"), reverse=True)[:max_photos]
    result = []
    for p in photos:
        result.append(base64.b64encode(p.read_bytes()).decode())
    return result


def build_contact_sheet(known_aves: list[dict], max_per_bird: int = 2) -> tuple[str, list[dict]]:
    """Construye un contact sheet (mosaico) con fotos de referencia de las aves conocidas.

    Returns:
        (base64_jpeg, legend) — imagen contact sheet y listado de qué ave está en cada posición
    """
    from pathlib import Path
    try:
        from PIL import Image
    except ImportError:
        return "", []

    CELL = 200
    entries = []
    for ave in known_aves:
        if not ave.get("anilla"):
            continue
        gallery_dir = Path(f"/app/data/bird_gallery/{ave['id']}")
        if not gallery_dir.exists():
            continue
        photos = sorted(gallery_dir.glob("*.jpg"), reverse=True)[:max_per_bird]
        for p in photos:
            entries.append({
                "path": p,
                "id": ave["id"],
                "anilla": ave.get("anilla", ""),
                "raza": ave.get("raza", ""),
                "sexo": ave.get("sexo", ""),
                "color": ave.get("color", ""),
            })

    if not entries:
        return "", []

    cols = min(len(entries), 6)
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * CELL, rows * CELL), (30, 30, 30))

    legend = []
    for idx, entry in enumerate(entries):
        try:
            img = Image.open(entry["path"])
            img.thumbnail((CELL - 4, CELL - 4))
            col = idx % cols
            row = idx // cols
            x = col * CELL + (CELL - img.width) // 2
            y = row * CELL + (CELL - img.height) // 2
            sheet.paste(img, (x, y))
            legend.append({
                "position": idx + 1,
                "grid": f"R{row+1}C{col+1}",
                "anilla": entry["anilla"],
                "raza": entry["raza"],
                "sexo": entry["sexo"],
                "color": entry["color"],
                "ave_id": entry["id"],
            })
        except Exception:
            continue

    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode(), legend


async def visual_reidentify(
    crop_b64: str,
    known_aves: list[dict],
    breed_hint: str = "",
    color_hint: str = "",
    sex_hint: str = "",
) -> dict:
    """Compara un crop contra la galería de fotos de referencia usando Together.ai Vision.

    Envía el contact sheet (mosaico de referencia) + el crop a identificar.
    Returns dict with best_match_anilla, confidence, reasoning, breed, sex, etc.
    """
    from config import get_settings
    settings = get_settings()
    if not settings.together_api_key:
        return {"error": "Together API key no configurada", "confidence": 0}

    contact_b64, legend = build_contact_sheet(known_aves, max_per_bird=2)

    aves_list = []
    for ave in known_aves:
        if not ave.get("anilla"):
            continue
        sex_txt = "♂ Macho" if ave.get("sexo") == "M" else "♀ Hembra" if ave.get("sexo") == "H" else "?"
        aves_list.append(
            f"  - {ave['anilla']}: {ave.get('raza','?')} {ave.get('color','')} {sex_txt}"
        )

    legend_text = ""
    if legend:
        legend_text = "\nFOTOS DE REFERENCIA (mosaico adjunto):\n"
        for L in legend:
            legend_text += f"  Pos.{L['position']} ({L['grid']}): {L['anilla']} — {L['raza']} {L['color']} ({L['sexo']})\n"

    hint_text = ""
    if breed_hint and breed_hint != "Desconocida":
        hint_text += f"\nPista del modelo YOLO: raza={breed_hint}"
    if color_hint:
        hint_text += f", color={color_hint}"
    if sex_hint and sex_hint != "unknown":
        hint_text += f", sexo={'macho' if sex_hint in ('M','male') else 'hembra'}"

    prompt = f"""Eres un experto avicultor. Identifica EXACTAMENTE qué ave individual del gallinero es la que aparece en la ÚLTIMA imagen.

AVES DEL GALLINERO:
{chr(10).join(aves_list) if aves_list else 'Sin datos'}
{legend_text}
{hint_text}

CLAVES DE DIFERENCIACIÓN:
- Sussex gallo ♂ (PAL-0001): MUY grande (~5kg), porte erguido, plumaje plateado con cola negra larga, cresta y barbillas rojas prominentes
- Sussex gallina ♀ (PAL-0003/4/5): Más pequeñas (~3kg), cuerpo redondeado, plumaje plateado o armiñado, cresta más pequeña
- Vorwerk gallo ♂ (PAL-0022): Cuello/cola NEGRO intenso con cuerpo dorado, cresta grande roja
- Vorwerk gallina ♀ (PAL-0023/24): Más pequeñas, menos contraste, cuello castaño oscuro con dorado
- Sulmtaler: Trigueño atigrado, no tiene el contraste marcado del Vorwerk
- Bresse gallo ♂ (PAL-0011): Blanco puro, patas gris-azulado, cresta roja grande — NO confundir con Sussex
- Bresse gallina ♀ (PAL-0002/12): Blancas puras, más pequeñas, patas gris-azulado
- Marans ♀ (PAL-0008): Negro cobrizo con reflejos, tarsos ligeramente emplumados
- Los MACHOS siempre tienen: cresta más grande, cola más larga, espolones, porte más erguido, mayor tamaño

INSTRUCCIONES:
1. Compara VISUALMENTE el ave de la última imagen con las fotos de referencia del mosaico
2. Fíjate en: tamaño relativo, forma de cresta, color de plumaje, porte, cola
3. Si hay 2+ aves de la misma raza y sexo, intenta distinguir por detalles sutiles
4. El gallo Sussex es MUCHO más grande que las gallinas — si el ave es grande y erguida, es el gallo

Responde SOLO con este JSON:
{{
  "best_match_anilla": "PAL-2026-XXXX",
  "best_match_id": número_id,
  "breed": "raza",
  "color": "color",
  "sex": "male o female",
  "confidence": 0.0-1.0,
  "reasoning": "explicación de por qué es esta ave y no otra"
}}"""

    content_parts = []

    if contact_b64:
        content_parts.append({"type": "text", "text": "[Mosaico de referencia de aves conocidas del gallinero:]"})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{contact_b64}"}
        })

    content_parts.append({"type": "text", "text": "[Ave a identificar:]"})
    raw_crop = crop_b64.split(",", 1)[-1] if "," in crop_b64 else crop_b64
    content_parts.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{raw_crop}"}
    })
    content_parts.append({"type": "text", "text": prompt})

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.together_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.together_vision_model,
                    "messages": [{"role": "user", "content": content_parts}],
                    "max_tokens": 512,
                    "temperature": 0.1,
                },
            )
            if resp.status_code != 200:
                logger.error(f"Visual re-ID error {resp.status_code}: {resp.text[:300]}")
                return {"error": f"Together API error {resp.status_code}", "confidence": 0}

            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"]

            text = raw_text.strip()
            if "<think>" in text:
                text = text.split("</think>")[-1].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            result = json.loads(text)
            logger.info(
                f"🧠 Visual re-ID: {result.get('breed','?')} "
                f"→ {result.get('best_match_anilla','?')} "
                f"conf={result.get('confidence',0):.0%} "
                f"({result.get('reasoning','')[:80]})"
            )
            return result

    except json.JSONDecodeError:
        return {"error": f"JSON parse failed: {raw_text[:100]}", "confidence": 0}
    except Exception as e:
        logger.error(f"Visual re-ID failed: {e}")
        return {"error": str(e), "confidence": 0}
