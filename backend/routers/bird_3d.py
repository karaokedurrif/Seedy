"""
Seedy Backend — Router /api/birds/{id}/3D

Pipeline: FLUX reference image → Tripo3D .glb model → model-viewer.
Generates studio-quality breed images via Together API (FLUX.1.1 Pro),
then converts to rotatable 3D models via Tripo3D API.
"""

import asyncio
import base64
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/birds", tags=["bird-3d"])

TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
TOGETHER_URL = "https://api.together.xyz/v1/images/generations"
TRIPO_API_KEY = os.environ.get("TRIPO_API_KEY", "")
TRIPO_BASE = "https://api.tripo3d.ai/v2/openapi"

MODELS_DIR = Path("/app/data/bird_3d_models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
REF_IMG_DIR = Path("/app/data/bird_3d_refs")
REF_IMG_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_PATH = Path("/app/data/birds_registry.json")

# ── Breed prompts for FLUX studio reference images ──

BREED_PROMPTS = {
    # ── Bresse (blanca pura, patas azuladas) ──
    "Bresse_blanco_M": (
        "Photorealistic studio photograph of a single white Bresse Gauloise rooster, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Bright white plumage, steel-blue legs, single red comb, red wattles, white earlobes. "
        "Full body visible including feet and tail. Clean studio lighting, no shadows on background. "
        "High detail on feather texture, sharp focus. Professional poultry breed photography. "
        "Isolated subject, no other objects, no text."
    ),
    "Bresse_blanco_F": (
        "Photorealistic studio photograph of a single white Bresse Gauloise hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "White plumage, steel-blue legs, small single red comb. "
        "Full body visible. Clean studio lighting. Professional poultry photography. "
        "Isolated subject, no other objects."
    ),
    # ── Sussex Light / blanco (armiñada: blanca con collar negro) ──
    "Sussex_blanco_F": (
        "Photorealistic studio photograph of a single Light Sussex hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "White body with black neck hackles (columbian pattern), black tail feathers. Pink-white legs. "
        "Full body visible. Clean studio lighting. High detail on feather patterns. "
        "Isolated subject, no other objects."
    ),
    # ── Sussex Silver (plateada: cuerpo plateado-gris con collar negro, muy distinta de Light) ──
    "Sussex_silver_M": (
        "Photorealistic studio photograph of a single Silver Sussex rooster, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Silvery-white body with bold black striping on each feather, black neck hackles edged in silver, "
        "glossy black tail with green sheen. Pink-white legs. Large single red comb and wattles. "
        "Muscular heavy build, 4-5 kg. Full body visible including feet and tail. "
        "Clean studio lighting. Professional poultry breed photography. "
        "Isolated subject, no other objects, no text."
    ),
    "Sussex_silver_F": (
        "Photorealistic studio photograph of a single Silver Sussex hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Silver-grey body feathers with fine black penciling, black neck hackles edged silver, "
        "dark tail. Pink-white legs. Small neat single red comb. "
        "Full body visible. Clean studio lighting. Detail on silvered feather pattern. "
        "Isolated subject, no other objects."
    ),
    # ── Vorwerk (cuerpo dorado, cuello y cola negros) ──
    "Vorwerk_dorado_M": (
        "Photorealistic studio photograph of a single Vorwerk rooster, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Black head and neck hackles with golden buff body plumage. Slate-blue legs. Single red comb. "
        "Full body visible including feet and long arched tail. Clean studio lighting. "
        "High detail on the contrast between black neck and golden body feathers. "
        "Isolated subject, no other objects."
    ),
    "Vorwerk_dorado_F": (
        "Photorealistic studio photograph of a single Vorwerk hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Black neck hackles transitioning to golden buff body. Slate-blue legs. Small single comb. "
        "Full body visible. Clean studio lighting. Professional poultry photography. "
        "Isolated subject, no other objects."
    ),
    # ── Sulmtaler (trigueño/atigrado, cresta tipo corona) ──
    "Sulmtaler_trigueño_M": (
        "Photorealistic studio photograph of a single Sulmtaler rooster, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Wheaten golden-brown plumage with dark tail, small crest on head. Light legs. "
        "Wickler (rose) comb. Strong build. Full body visible. Clean studio lighting. "
        "Austrian heritage breed. Isolated subject, no other objects."
    ),
    "Sulmtaler_trigueño_F": (
        "Photorealistic studio photograph of a single Sulmtaler hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Wheaten golden buff plumage with subtle darker lacing, small crest on head. Light legs. "
        "Wickler (rose) comb. Full body visible. Clean studio lighting. Professional breed photography. "
        "Isolated subject, no other objects."
    ),
    # ── Marans (negro cobrizo, patas emplumadas) ──
    "Marans_negro cobrizo_F": (
        "Photorealistic studio photograph of a single Black Copper Marans hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Dark brown-black plumage with copper hackles. Feathered legs. Single red comb. "
        "Full body visible. Clean studio lighting. Rich dark feather detail. "
        "Isolated subject, no other objects."
    ),
    "Marans_negro cobrizo_M": (
        "Photorealistic studio photograph of a single Black Copper Marans rooster, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Glossy black body with bright copper hackles and saddle. Feathered legs. Large single red comb. "
        "Full body visible. Clean studio lighting. "
        "Isolated subject, no other objects."
    ),
    # ── Andaluza Azul (gris-azulado uniforme) ──
    "Andaluza Azul_azul_F": (
        "Photorealistic studio photograph of a single Blue Andalusian hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Blue-grey slate plumage with darker lacing. White earlobes. Single large red comb. "
        "Full body visible. Clean studio lighting. Detail on blue-laced feather pattern. "
        "Isolated subject, no other objects."
    ),
    # ── Pita Pinta Asturiana (moteada blanco y negro) ──
    "Pita Pinta_pinta_F": (
        "Photorealistic studio photograph of a single Pita Pinta Asturiana hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Black and white mottled plumage (pinta pattern). Yellow-green legs. Single red comb. "
        "Full body visible. Clean studio lighting. Spanish heritage breed. "
        "Isolated subject, no other objects."
    ),
    # ── Araucana negra (sin cola, penachos auriculares) ──
    "Araucana_negra_F": (
        "Photorealistic studio photograph of a single black Araucana hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Solid glossy black plumage with green iridescence, ear tufts, rumpless (no tail). "
        "Yellow-green legs. Small pea comb. Full body visible. Clean studio lighting. "
        "Blue egg-laying breed from Chile. Isolated subject, no other objects."
    ),
    # ── Araucana trigueña (sin cola, penachos auriculares) ──
    "Araucana_trigueña_F": (
        "Photorealistic studio photograph of a single wheaten Araucana hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Warm wheaten-brown plumage, ear tufts, rumpless (no tail). Yellow-green legs. "
        "Small pea comb. Full body visible. Clean studio lighting. "
        "Blue egg-laying breed from Chile. Isolated subject, no other objects."
    ),
    # ── F1 (cruce) — aspecto rústico variable ──
    "F1 (cruce)_variado_F": (
        "Photorealistic studio photograph of a single mixed-breed heritage hen, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Mixed coloring showing hybrid vigor: reddish-brown body with dark tail, medium build. "
        "Full body visible. Clean studio lighting. Rustic farm chicken appearance. "
        "Isolated subject, no other objects."
    ),
    "F1 (cruce)_variado_M": (
        "Photorealistic studio photograph of a single mixed-breed heritage rooster, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Reddish-brown plumage with dark green-black tail feathers, strong build. "
        "Full body visible. Clean studio lighting. "
        "Isolated subject, no other objects."
    ),
    # ── Fallback: ave genérica por determinar ──
    "Por determinar_desconocido_F": (
        "Photorealistic studio photograph of a single brown heritage chicken, "
        "standing in 3/4 profile view on a plain light grey background. "
        "Brown-red plumage, medium build, single red comb. "
        "Full body visible. Clean studio lighting. "
        "Isolated subject, no other objects."
    ),
}


def _find_bird(bird_id: str) -> dict | None:
    """Find a bird in the registry by ID."""
    if not REGISTRY_PATH.exists():
        return None
    data = json.loads(REGISTRY_PATH.read_text())
    birds = data if isinstance(data, list) else data.get("birds", [])
    for b in birds:
        if b.get("bird_id") == bird_id:
            return b
    return None


def _get_prompt_key(breed: str, sex: str, color: str = "") -> str:
    """Get the best matching prompt key for breed + color + sex.

    Keys follow the format: ``{breed}_{color}_{sex_code}``.
    Searches with decreasing specificity:
      1. breed_color_sex  (exact)
      2. breed_*_sex       (any color, same sex)
      3. breed_*_*         (any entry for breed)
      4. F1 (cruce) fallback
    """
    sex_code = "M" if sex in ("M", "male") else "F"
    color = (color or "").strip().lower()

    # 1. Exact: breed_color_sex
    key = f"{breed}_{color}_{sex_code}"
    if key in BREED_PROMPTS:
        return key

    # 2. Any color, same sex
    for k in BREED_PROMPTS:
        if k.startswith(f"{breed}_") and k.endswith(f"_{sex_code}"):
            return k

    # 3. Any entry for this breed
    for k in BREED_PROMPTS:
        if k.startswith(f"{breed}_"):
            return k

    # 4. Fallback
    fb = f"F1 (cruce)_variado_{sex_code}"
    return fb if fb in BREED_PROMPTS else "Por determinar_desconocido_F"


async def _generate_flux_image(prompt: str) -> bytes:
    """Generate a single image via FLUX.1.1 Pro and return raw PNG bytes."""
    if not TOGETHER_API_KEY:
        raise HTTPException(status_code=503, detail="TOGETHER_API_KEY not configured")
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            TOGETHER_URL,
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "black-forest-labs/FLUX.1.1-pro",
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "steps": 28,
                "n": 1,
                "response_format": "b64_json",
            },
        )
        if resp.status_code != 200:
            logger.error("Together API error %d: %s", resp.status_code, resp.text[:500])
            raise HTTPException(status_code=502, detail=f"Together API returned {resp.status_code}")
        data = resp.json().get("data", [])
        if not data or not data[0].get("b64_json"):
            raise HTTPException(status_code=502, detail="No image data returned")
        return base64.b64decode(data[0]["b64_json"])


async def _create_tripo_task(image_bytes: bytes) -> str:
    """Upload image to Tripo3D and create image-to-model task. Returns task_id."""
    if not TRIPO_API_KEY:
        raise HTTPException(status_code=503, detail="TRIPO_API_KEY not configured — set it in .env or upload .glb manually")
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Upload image first
        upload_resp = await client.post(
            f"{TRIPO_BASE}/upload",
            headers={"Authorization": f"Bearer {TRIPO_API_KEY}"},
            files={"file": ("bird.png", image_bytes, "image/png")},
        )
        if upload_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Tripo upload error: {upload_resp.text[:300]}")
        upload_data = upload_resp.json()
        file_token = upload_data["data"]["image_token"]

        # Create task
        task_resp = await client.post(
            f"{TRIPO_BASE}/task",
            headers={
                "Authorization": f"Bearer {TRIPO_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "type": "image_to_model",
                "file": {"type": "image_token", "file_token": file_token},
                "model_version": "v2.0-20240919",
                "texture": True,
                "pbr": True,
            },
        )
        if task_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Tripo task error: {task_resp.text[:300]}")
        return task_resp.json()["data"]["task_id"]


async def _poll_tripo_task(task_id: str, bird_id: str) -> Path:
    """Poll Tripo3D task until done, download .glb, return path."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(60):  # max 5 minutes
            await asyncio.sleep(5)
            resp = await client.get(
                f"{TRIPO_BASE}/task/{task_id}",
                headers={"Authorization": f"Bearer {TRIPO_API_KEY}"},
            )
            if resp.status_code != 200:
                continue
            status = resp.json()["data"]
            if status["status"] == "success":
                model_url = status["output"]["model"]
                glb_resp = await client.get(model_url, timeout=60.0)
                filepath = MODELS_DIR / f"{bird_id}.glb"
                filepath.write_bytes(glb_resp.content)
                logger.info("Downloaded 3D model for %s (%d bytes)", bird_id, len(glb_resp.content))
                return filepath
            elif status["status"] == "failed":
                raise HTTPException(status_code=502, detail=f"Tripo3D failed: {status.get('message', 'unknown')}")
    raise HTTPException(status_code=504, detail="Tripo3D task timed out")


# ──────────────────── Endpoints ────────────────────


@router.get("/{bird_id}/model.glb")
async def serve_bird_model(bird_id: str):
    """Serve the .glb 3D model for a bird."""
    filepath = MODELS_DIR / f"{bird_id}.glb"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="3D model not yet generated")
    return FileResponse(filepath, media_type="model/gltf-binary", filename=f"{bird_id}.glb")


@router.get("/{bird_id}/reference-image.png")
async def serve_reference_image(bird_id: str):
    """Serve the FLUX reference image for a bird."""
    filepath = REF_IMG_DIR / f"{bird_id}.png"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Reference image not yet generated")
    return FileResponse(filepath, media_type="image/png", filename=f"{bird_id}_ref.png")


@router.post("/{bird_id}/generate-3d")
async def generate_bird_3d(bird_id: str):
    """Full pipeline: bird → FLUX reference image → Tripo3D → .glb model."""
    # Check if model already exists
    model_path = MODELS_DIR / f"{bird_id}.glb"
    if model_path.exists():
        return {
            "bird_id": bird_id,
            "status": "exists",
            "model_url": f"/api/birds/{bird_id}/model.glb",
            "size_bytes": model_path.stat().st_size,
        }

    # Find bird in registry
    bird = _find_bird(bird_id)
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} no found in registry")

    breed = bird.get("breed", "F1 (cruce)")
    sex = bird.get("sex", "female")
    color = bird.get("color", "")

    # Step 1: Generate or load FLUX reference image
    ref_path = REF_IMG_DIR / f"{bird_id}.png"
    if ref_path.exists():
        image_bytes = ref_path.read_bytes()
        logger.info("Using existing reference image for %s", bird_id)
    else:
        prompt_key = _get_prompt_key(breed, sex, color)
        prompt = BREED_PROMPTS[prompt_key]
        logger.info("Generating FLUX reference for %s (prompt key: %s)", bird_id, prompt_key)
        image_bytes = await _generate_flux_image(prompt)
        ref_path.write_bytes(image_bytes)
        logger.info("Saved reference image for %s (%d bytes)", bird_id, len(image_bytes))

    # Step 2: Tripo3D — generate 3D model
    if not TRIPO_API_KEY:
        # No Tripo key — return ref image only, user can generate manually
        return {
            "bird_id": bird_id,
            "status": "ref_only",
            "reference_image": f"/api/birds/{bird_id}/reference-image.png",
            "message": "Imagen FLUX generada. Sin TRIPO_API_KEY — sube el .glb manualmente o configura la key.",
        }

    task_id = await _create_tripo_task(image_bytes)
    logger.info("Tripo3D task created for %s: %s", bird_id, task_id)

    # Poll in background (return immediately)
    # For the demo, we'll do synchronous wait
    model_file = await _poll_tripo_task(task_id, bird_id)

    return {
        "bird_id": bird_id,
        "status": "success",
        "model_url": f"/api/birds/{bird_id}/model.glb",
        "reference_image": f"/api/birds/{bird_id}/reference-image.png",
        "size_bytes": model_file.stat().st_size,
    }


@router.post("/{bird_id}/generate-ref")
async def generate_reference_only(bird_id: str):
    """Generate only the FLUX reference image (no 3D model)."""
    bird = _find_bird(bird_id)
    if not bird:
        raise HTTPException(status_code=404, detail=f"Ave {bird_id} not found")

    breed = bird.get("breed", "F1 (cruce)")
    sex = bird.get("sex", "female")
    color = bird.get("color", "")
    prompt_key = _get_prompt_key(breed, sex, color)
    prompt = BREED_PROMPTS[prompt_key]

    ref_path = REF_IMG_DIR / f"{bird_id}.png"
    image_bytes = await _generate_flux_image(prompt)
    ref_path.write_bytes(image_bytes)

    return {
        "bird_id": bird_id,
        "breed": breed,
        "prompt_key": prompt_key,
        "reference_image": f"/api/birds/{bird_id}/reference-image.png",
        "size_bytes": len(image_bytes),
    }


@router.post("/batch-generate-refs")
async def batch_generate_refs(
    bird_ids: list[str] | None = None,
    limit: int = Query(6, ge=1, le=26),
):
    """Generate FLUX reference images for multiple birds. If no IDs given, picks top birds."""
    if not REGISTRY_PATH.exists():
        raise HTTPException(status_code=404, detail="No bird registry found")

    data = json.loads(REGISTRY_PATH.read_text())
    birds = data if isinstance(data, list) else data.get("birds", [])

    if bird_ids:
        targets = [b for b in birds if b["bird_id"] in bird_ids]
    else:
        # Pick the first N birds, prioritizing those without ref images
        targets = sorted(birds, key=lambda b: (REF_IMG_DIR / f"{b['bird_id']}.png").exists())[:limit]

    results = []
    for bird in targets:
        bid = bird["bird_id"]
        ref_path = REF_IMG_DIR / f"{bid}.png"
        if ref_path.exists():
            results.append({"bird_id": bid, "status": "exists", "url": f"/api/birds/{bid}/reference-image.png"})
            continue
        try:
            breed = bird.get("breed", "F1 (cruce)")
            sex = bird.get("sex", "female")
            color = bird.get("color", "")
            prompt_key = _get_prompt_key(breed, sex, color)
            prompt = BREED_PROMPTS[prompt_key]
            image_bytes = await _generate_flux_image(prompt)
            ref_path.write_bytes(image_bytes)
            results.append({"bird_id": bid, "status": "generated", "url": f"/api/birds/{bid}/reference-image.png", "size_bytes": len(image_bytes)})
            logger.info("Generated ref for %s (%s)", bid, prompt_key)
        except Exception as e:
            results.append({"bird_id": bid, "status": "error", "error": str(e)})
            logger.warning("Failed to generate ref for %s: %s", bid, e)

    return {"total": len(results), "results": results}
