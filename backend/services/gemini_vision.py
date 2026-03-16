"""
Seedy Backend — Servicio de visión con Gemini 2.0 Flash.

Recibe imágenes (base64 o URL), las analiza con Gemini,
y guarda los pares (imagen, respuesta) para futuro LoRA fine-tune.
"""

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────

# Modelos Gemini en orden de preferencia (fallback si uno está rate-limited)
_GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Directorio para guardar pares imagen+respuesta (dataset LoRA futuro)
_DATASET_DIR = Path("/app/vision_dataset")
_DATASET_DIR.mkdir(parents=True, exist_ok=True)

# System prompt para análisis de aves/ganado
VISION_SYSTEM_PROMPT = """Eres un veterinario experto en identificación visual de razas ganaderas (aves de corral, porcino, vacuno).

Cuando recibas una foto de un animal, analiza SIEMPRE con este protocolo:

OBSERVACIÓN:
Describe EXACTAMENTE lo que ves en la foto:
- Especie y sexo (gallo/gallina, verraco/cerda, toro/vaca)
- Color exacto del plumaje o capa
- Cresta: tipo (simple, roseta, guisante) y color (solo aves)
- Tarsos/patas: color, con o sin plumas (solo aves)
- Porte y conformación (pesado, ligero, erguido, rechoncho)
- Rasgos distintivos (collar negro, barrado, copete, barbas, plumas en tarsos)
- Lo que NO puedes ver claramente en la foto

IDENTIFICACIÓN:
Basándote SOLO en los rasgos observados:
- Raza más probable y por qué
- 1-2 alternativas con el rasgo diferencial
- Confianza: alta / media / baja

CONDICIÓN CORPORAL:
BCS estimado si la foto lo permite (escala 1-5 aves, 1-9 vacuno).

REGLAS:
- SIEMPRE intenta identificar. NUNCA digas "no puedo identificar la raza".
- NO inventes rasgos que no ves. Si algo no es visible, dilo.
- Responde SIEMPRE en español (España).
- Sé técnico pero accesible.
- NO uses Markdown (asteriscos, almohadillas, negritas). Usa texto plano: guiones para listas, MAYÚSCULAS para títulos de sección."""

# ── Cliente HTTP reutilizable ────────────────────────

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


async def close():
    """Cierra el cliente HTTP."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


# ── API Gemini ───────────────────────────────────────


async def analyze_image(
    image_b64: str,
    question: str = "Identifica este animal",
    mime_type: str = "image/jpeg",
    save_for_training: bool = True,
) -> dict:
    """
    Envía imagen a Gemini 2.0 Flash y devuelve análisis estructurado.

    Args:
        image_b64: Imagen codificada en base64
        question: Pregunta del usuario
        mime_type: Tipo MIME de la imagen (image/jpeg, image/png, image/webp)
        save_for_training: Si True, guarda el par para LoRA fine-tune

    Returns:
        dict con keys: answer, model, elapsed_s, saved_path (si aplica)
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurada")

    t0 = time.time()

    # Construir request para Gemini
    payload = {
        "system_instruction": {
            "parts": [{"text": VISION_SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
                    {"text": question},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "topP": 0.9,
            "maxOutputTokens": 2048,
            "thinkingConfig": {"thinkingBudget": 0},  # Gemini 2.5: desactivar thinking (ya tenemos protocolo estructurado)
        },
    }

    client = _get_client()

    # Intentar cada modelo en orden (fallback si rate-limited)
    last_error = None
    model_used = _GEMINI_MODELS[0]
    for model_name in _GEMINI_MODELS:
        url = f"{_GEMINI_BASE_URL}/{model_name}:generateContent?key={api_key}"
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                logger.warning(f"[Vision] {model_name} rate-limited, trying next...")
                last_error = f"{model_name}: 429 Too Many Requests"
                continue
            resp.raise_for_status()
            model_used = model_name
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"[Vision] {model_name} rate-limited, trying next...")
                last_error = str(e)
                continue
            raise
    else:
        # Todos los modelos rate-limited
        raise RuntimeError(f"Todos los modelos Gemini rate-limited: {last_error}")

    data = resp.json()
    elapsed = time.time() - t0

    # Extraer texto de respuesta
    answer = ""
    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        answer = " ".join(p.get("text", "") for p in parts).strip()

    # Tokens usados
    usage = data.get("usageMetadata", {})
    logger.info(
        f"[Vision] Gemini {model_used}: {elapsed:.1f}s | "
        f"prompt={usage.get('promptTokenCount', '?')} "
        f"completion={usage.get('candidatesTokenCount', '?')} tokens"
    )

    # Guardar par (imagen, respuesta) para futuro fine-tune
    saved_path = None
    if save_for_training and answer:
        saved_path = _save_training_pair(image_b64, question, answer, mime_type)

    return {
        "answer": answer,
        "model": f"gemini/{model_used}",
        "elapsed_s": round(elapsed, 2),
        "saved_path": str(saved_path) if saved_path else None,
        "usage": {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        },
    }


async def analyze_image_from_url(
    image_url: str,
    question: str = "Identifica este animal",
    save_for_training: bool = True,
) -> dict:
    """Descarga imagen desde URL y la analiza."""
    client = _get_client()
    resp = await client.get(image_url)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
    b64 = base64.b64encode(resp.content).decode()

    return await analyze_image(
        image_b64=b64,
        question=question,
        mime_type=content_type,
        save_for_training=save_for_training,
    )


# ── Dataset LoRA ─────────────────────────────────────

_dataset_counter = 0


def _save_training_pair(
    image_b64: str,
    question: str,
    answer: str,
    mime_type: str,
) -> Path | None:
    """
    Guarda un par (imagen, respuesta) en formato compatible con LLaMA-Factory.

    Estructura:
      vision_dataset/
        images/        → archivos de imagen
        dataset.jsonl  → pares conversacionales
    """
    global _dataset_counter

    try:
        img_dir = _DATASET_DIR / "images"
        img_dir.mkdir(exist_ok=True)

        # Extensión según MIME
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        ext = ext_map.get(mime_type, ".jpg")

        # Nombre de archivo con timestamp
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        _dataset_counter += 1
        img_name = f"vision_{ts}_{_dataset_counter:04d}{ext}"
        img_path = img_dir / img_name

        # Guardar imagen
        img_bytes = base64.b64decode(image_b64)
        img_path.write_bytes(img_bytes)

        # Guardar conversación en JSONL (formato LLaMA-Factory ShareGPT)
        record = {
            "image": f"images/{img_name}",
            "conversations": [
                {"from": "human", "value": f"<image>\n{question}"},
                {"from": "gpt", "value": answer},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        jsonl_path = _DATASET_DIR / "dataset.jsonl"
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"[Vision] Dataset: guardado {img_name} ({len(img_bytes) / 1024:.0f}KB)")
        return img_path

    except Exception as e:
        logger.warning(f"[Vision] Error guardando par de training: {e}")
        return None


def get_dataset_stats() -> dict:
    """Estadísticas del dataset de visión acumulado."""
    jsonl_path = _DATASET_DIR / "dataset.jsonl"
    img_dir = _DATASET_DIR / "images"

    n_records = 0
    if jsonl_path.exists():
        n_records = sum(1 for _ in open(jsonl_path))

    n_images = len(list(img_dir.glob("*"))) if img_dir.exists() else 0
    total_size = sum(f.stat().st_size for f in img_dir.glob("*")) if img_dir.exists() else 0

    return {
        "records": n_records,
        "images": n_images,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "path": str(_DATASET_DIR),
    }
