"""
Render IA — Genera renders fotorrealistas via Together API (FLUX.1.1 Pro).
"""

import base64
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/renders", tags=["Renders IA"])

RENDERS_DIR = Path(os.environ.get("RENDERS_DIR", "/app/data/renders"))
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
TOGETHER_URL = "https://api.together.xyz/v1/images/generations"

# ──────────────────── Context & Prompts ────────────────────

FARM_CONTEXT = """
Small heritage poultry farm "El Gallinero del Palacio" in Segovia, Spain, at 1000m altitude.
Layout: Stone retaining wall along the north side (30m long, 2.5m high) with blooming pink prunus trees on top.
Main park (Parque GI): L-shaped open area ~120m², with a large almond tree in the center (green canopy, 3.5m radius).
Wooden sauna building (3.5m × 6m) on the west side, tan/brown wood.
Two small chicken coops: Gallinero I (tiny 1.5m × 0.9m white wooden shed near the wall) and Gallinero II (2m × 2m wooden coop with dark roof, east side).
Wire mesh fencing with wooden posts separating areas.
Vegetable garden with 6 raised wooden beds south of the chicken area.
~26 heritage chickens of multiple breeds: white Bresse, golden Vorwerk, light Sussex, dark Marans, buff Sulmtaler, blue Andaluza.
Ground is bare earth/dirt, March atmosphere, overcast soft light.
""".strip()

PROMPTS = {
    "isometric": f"""Photorealistic aerial photograph taken from a drone at 12 meters altitude, 45 degree angle, looking northeast. Small heritage poultry farm in rural Segovia, Spain, March, altitude 1000m.

Scene layout from south to north:
- Foreground: 6 rectangular raised wooden garden beds with green seedlings, arranged in 2 rows of 3
- Low wire mesh fence with wooden stakes separating garden from chicken area
- Main chicken area: bare earth ground, ~20 heritage chickens scattered naturally (white, golden, brown, grey, blue-grey breeds)
- Large almond tree in center with broad green canopy, ~7m diameter
- Small white-painted wooden chicken coop (1.5m wide) near the north wall
- Left side: wooden sauna/shed building, natural wood color, 3.5m x 6m, dark shingled roof
- Right side: larger wooden chicken coop (2m x 2m) with dark roof and round porthole window
- Separate fenced area on far right with 6 more chickens
- North boundary: old stone retaining wall, 30m long, 2.5m high, covered in vegetation
- On top of wall: row of prunus trees in full pink blossom (March in Spain)
- Background: distant view of Segovia countryside, soft overcast sky

Equipment visible: blue plastic waterer, grey metal feeder, compost bin.
Style: High-end editorial documentary photography, natural soft lighting, high detail, no HDR, no oversaturation. Like a feature in Monocle magazine about artisanal farming. 8K quality.
No text, no labels, no watermarks, no UI elements, no people.""",

    "ground": f"""Eye-level photograph inside a small heritage chicken farm in Segovia, Spain, March. Camera at 1.2m height, looking north across the main park.

Foreground: 3-4 heritage chickens at close range — a white Bresse hen, a golden Vorwerk rooster with iridescent tail feathers, a dark brown Marans hen. Sharp focus on the closest bird.

Middle ground: more chickens scattered across bare earth, a large almond tree with spreading green canopy, blue waterer, metal feeder. Wire mesh fence with wooden posts visible.

Background: stone retaining wall covered in moss and ivy, row of prunus trees in spectacular pink cherry blossom above the wall. Small white wooden chicken coop nestled against the wall. Wooden sauna building on the left.

Right side: second fenced area visible through mesh, with a few more chickens and a wooden coop with dark roof.

Atmosphere: Soft overcast March day in central Spain at 1000m altitude. Cool air, gentle light. The pink blossoms contrast beautifully with the grey stone wall.

Style: Award-winning documentary photography. Shallow depth of field (f/2.8), natural colors, no filters. Like a Sebastiao Salgado rural portrait. Tangible texture on feathers, earth, and weathered wood.
No people, no text, no watermarks.""",

    "golden": f"""Golden hour aerial photograph of a small heritage poultry farm, warm sunset light from the west. Segovia, Spain.

The scene is bathed in warm golden light. Long shadows stretch across the bare earth. A wooden sauna building on the left catches the warm light on its planks. Heritage chickens cast small shadows as they forage — white Bresse hens glow in the sunset, golden Vorwerk birds blend with the light.

A large almond tree in the center creates a dramatic shadow pattern. Pink prunus blossoms on the stone wall catch the last light, turning almost luminous against the darkening sky to the east.

Two small wooden chicken coops with dark roofs. Wire mesh fencing with wooden posts. Raised vegetable garden beds in the foreground.

The whole scene feels intimate, warm, artisanal. This is premium heritage poultry farming — not industrial, not hobby, but the serious craft of breeding exceptional birds.

Style: National Geographic golden hour, cinematic, atmospheric, warm color palette. The kind of image that makes investors write checks and chefs call to order capons.
Drone shot at 10m, 40 degree angle, looking east.
No people, no text, no watermarks.""",
}


async def _call_together(prompt: str, width: int, height: int, n: int) -> list[dict]:
    """Call Together API to generate images with FLUX.1.1 Pro."""
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
                "width": width,
                "height": height,
                "steps": 28,
                "n": n,
                "response_format": "b64_json",
            },
        )
        if resp.status_code != 200:
            logger.error("Together API error %d: %s", resp.status_code, resp.text[:500])
            raise HTTPException(status_code=502, detail=f"Together API returned {resp.status_code}")
        return resp.json().get("data", [])


def _save_image(b64: str, concept: str, index: int) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"farm_{concept}_{ts}_{index}.png"
    path = RENDERS_DIR / filename
    path.write_bytes(base64.b64decode(b64))
    return path


def _latest_for_concept(concept: str) -> Path | None:
    pattern = f"farm_{concept}_*.png"
    files = sorted(RENDERS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


# ──────────────────── Endpoints ────────────────────


@router.post("/generate")
async def generate_render(
    concept: str = Query("isometric", regex="^(isometric|ground|golden)$"),
    width: int = Query(1344, ge=256, le=2048),
    height: int = Query(768, ge=256, le=2048),
    n: int = Query(1, ge=1, le=4),
):
    """Generate photorealistic farm renders via FLUX.1.1 Pro."""
    prompt = PROMPTS.get(concept, PROMPTS["isometric"])
    images = await _call_together(prompt, width, height, n)

    results = []
    for i, img in enumerate(images):
        b64 = img.get("b64_json", "")
        if not b64:
            continue
        path = _save_image(b64, concept, i)
        results.append({
            "concept": concept,
            "filename": path.name,
            "url": f"/api/renders/file/{path.name}",
            "size_bytes": path.stat().st_size,
        })
        logger.info("Saved render %s (%d bytes)", path.name, path.stat().st_size)

    return {"generated": len(results), "renders": results}


@router.get("/latest")
async def latest_renders(concept: str = Query(None)):
    """Return most recent render(s). If concept given, return only that one."""
    if concept:
        path = _latest_for_concept(concept)
        if not path:
            return {"url": None, "concept": concept}
        return {
            "concept": concept,
            "filename": path.name,
            "url": f"/api/renders/file/{path.name}",
        }

    # All concepts
    out = {}
    for c in PROMPTS:
        path = _latest_for_concept(c)
        if path:
            out[c] = {"filename": path.name, "url": f"/api/renders/file/{path.name}"}
    return out


@router.get("/file/{filename}")
async def serve_render(filename: str):
    """Serve a generated render file."""
    # Sanitize filename to prevent path traversal
    safe = Path(filename).name
    path = RENDERS_DIR / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Render not found")
    return FileResponse(path, media_type="image/png")
