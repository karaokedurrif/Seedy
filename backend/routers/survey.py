"""
Seedy — Router de Survey Fotográfico y Plano Digital Twin.

Permite subir fotos del móvil geoetiquetadas con posición/dirección
dentro del gallinero, y genera un plano SVG interactivo combinando
el layout configurado con las fotos y la visión de las cámaras.

Endpoints:
  POST /survey/photo             — Subir foto del móvil con metadatos
  GET  /survey/photos/{gall_id}  — Listar fotos de un gallinero
  GET  /survey/layout/{gall_id}  — Layout JSON del gallinero
  PUT  /survey/layout/{gall_id}  — Actualizar layout (zonas, dims)
  GET  /survey/floorplan/{gall_id}       — Plano SVG del gallinero
  GET  /survey/floorplan/{gall_id}/html  — Plano interactivo HTML
  DELETE /survey/photo/{photo_id}        — Eliminar foto
"""

import json
import logging
import math
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("seedy.survey")

router = APIRouter(prefix="/survey", tags=["survey-floorplan"])

# ── Paths ──
_CONFIG_DIR = Path("/app/config") if Path("/app/config").exists() else Path(__file__).resolve().parent.parent / "config"
_LAYOUT_FILE = _CONFIG_DIR / "gallinero_layouts.json"
_SURVEY_DIR = Path("/app/data/survey") if Path("/app").exists() else Path(__file__).resolve().parent.parent / "data" / "survey"
_SURVEY_DIR.mkdir(parents=True, exist_ok=True)

# ── In-memory state ──
_layouts: dict = {}
_photos: dict[str, list] = {}  # gallinero_id -> [photo_meta]


def _load_layouts():
    global _layouts
    if _LAYOUT_FILE.exists():
        with open(_LAYOUT_FILE) as f:
            _layouts = json.load(f)
        logger.info(f"📐 Gallinero layouts loaded: {[k for k in _layouts if not k.startswith('_')]}")


def _save_layouts():
    with open(_LAYOUT_FILE, "w") as f:
        json.dump(_layouts, f, indent=2, ensure_ascii=False)


def _load_photos():
    """Load photo metadata from disk."""
    global _photos
    for gdir in _SURVEY_DIR.iterdir():
        if gdir.is_dir():
            meta_file = gdir / "photos.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    _photos[gdir.name] = json.load(f)


def _save_photos(gallinero_id: str):
    gdir = _SURVEY_DIR / gallinero_id
    gdir.mkdir(parents=True, exist_ok=True)
    with open(gdir / "photos.json", "w") as f:
        json.dump(_photos.get(gallinero_id, []), f, indent=2, ensure_ascii=False)


# Load on import
_load_layouts()
_load_photos()


# ── Photo Upload ──

@router.post("/photo")
async def upload_survey_photo(
    gallinero_id: str = Form(...),
    foto: UploadFile = File(...),
    pos_x: float = Form(0.0, description="Posición X en metros dentro del gallinero"),
    pos_y: float = Form(0.0, description="Posición Y en metros dentro del gallinero"),
    direccion: float = Form(0.0, description="Dirección de la cámara en grados (0=norte, 90=este)"),
    descripcion: str = Form("", description="Qué se ve en la foto"),
    tipo: str = Form("general", description="general|ponedero|perchas|comedero|bebedero|puerta|valla|patio|techo|detalle"),
):
    """Subir una foto tomada con el móvil, con posición dentro del gallinero."""
    if not foto.content_type or not foto.content_type.startswith("image/"):
        raise HTTPException(400, "El archivo debe ser una imagen (JPEG/PNG)")

    content = await foto.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Foto demasiado grande (máx 20MB)")

    photo_id = str(uuid.uuid4())[:8]
    ext = foto.filename.rsplit(".", 1)[-1] if foto.filename and "." in foto.filename else "jpg"
    filename = f"{photo_id}.{ext}"

    # Save file
    gdir = _SURVEY_DIR / gallinero_id
    gdir.mkdir(parents=True, exist_ok=True)
    filepath = gdir / filename
    with open(filepath, "wb") as f:
        f.write(content)

    # Save metadata
    meta = {
        "id": photo_id,
        "filename": filename,
        "gallinero_id": gallinero_id,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "direccion": direccion,
        "descripcion": descripcion,
        "tipo": tipo,
        "timestamp": time.time(),
        "size_bytes": len(content),
    }

    if gallinero_id not in _photos:
        _photos[gallinero_id] = []
    _photos[gallinero_id].append(meta)
    _save_photos(gallinero_id)

    logger.info(f"📸 Survey photo {photo_id} saved for {gallinero_id} at ({pos_x},{pos_y}) dir={direccion}° — {descripcion}")
    return {"ok": True, "photo_id": photo_id, "total_photos": len(_photos[gallinero_id])}


@router.get("/photos/{gallinero_id}")
async def list_survey_photos(gallinero_id: str):
    """Listar fotos del survey de un gallinero."""
    photos = _photos.get(gallinero_id, [])
    return {"gallinero_id": gallinero_id, "photos": photos, "total": len(photos)}


@router.get("/photo/{gallinero_id}/{photo_id}")
async def get_survey_photo(gallinero_id: str, photo_id: str):
    """Devolver la imagen de una foto del survey."""
    photos = _photos.get(gallinero_id, [])
    meta = next((p for p in photos if p["id"] == photo_id), None)
    if not meta:
        raise HTTPException(404, f"Foto {photo_id} no encontrada")
    filepath = _SURVEY_DIR / gallinero_id / meta["filename"]
    if not filepath.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")
    ext = meta["filename"].rsplit(".", 1)[-1].lower()
    media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
    return Response(content=filepath.read_bytes(), media_type=media)


@router.delete("/photo/{photo_id}")
async def delete_survey_photo(photo_id: str):
    """Eliminar una foto del survey."""
    for gid, photos in _photos.items():
        for i, p in enumerate(photos):
            if p["id"] == photo_id:
                filepath = _SURVEY_DIR / gid / p["filename"]
                if filepath.exists():
                    filepath.unlink()
                photos.pop(i)
                _save_photos(gid)
                return {"ok": True, "deleted": photo_id}
    raise HTTPException(404, f"Foto {photo_id} no encontrada")


# ── Layout CRUD ──

@router.get("/layout/{gallinero_id}")
async def get_layout(gallinero_id: str):
    """Devolver layout de un gallinero."""
    layout = _layouts.get(gallinero_id)
    if not layout:
        raise HTTPException(404, f"Layout no encontrado para {gallinero_id}")
    return layout


@router.put("/layout/{gallinero_id}")
async def update_layout(gallinero_id: str, data: dict):
    """Actualizar layout de un gallinero (dims, zonas, cámara)."""
    if gallinero_id not in _layouts:
        raise HTTPException(404, f"Layout no encontrado para {gallinero_id}")
    _layouts[gallinero_id].update(data)
    _layouts[gallinero_id].pop("_placeholder", None)
    _save_layouts()
    return {"ok": True, "gallinero_id": gallinero_id}


# ── SVG Floor Plan Generator ──

_ZONE_COLORS = {
    "nido": "#FFE0B2",
    "descanso": "#C8E6C9",
    "comedero": "#BBDEFB",
    "bebedero": "#B3E5FC",
    "puerta": "#D7CCC8",
    "exterior": "#E8F5E9",
}


def _generate_svg(gallinero_id: str, include_photos: bool = True) -> str:
    """Genera un SVG del plano del gallinero con zonas, cámara y fotos."""
    layout = _layouts.get(gallinero_id)
    if not layout:
        return "<svg><text>Layout no configurado</text></svg>"

    dims = layout.get("dims", {"largo": 6, "ancho": 4, "alto": 2.5})
    largo = dims["largo"]
    ancho = dims["ancho"]
    scale = 100  # px per meter
    margin = 40
    w = int(largo * scale + margin * 2)
    h = int(ancho * scale + margin * 2)
    # Add space for patio below
    patio_h = 0
    for z in layout.get("zonas", []):
        r = z["rect"]
        if r[1] < 0:
            patio_h = max(patio_h, abs(r[1]) * scale)
    h_total = h + int(patio_h) + margin

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h_total}" width="{w}" height="{h_total}">']
    svg.append('<style>')
    svg.append('  text { font-family: sans-serif; font-size: 11px; }')
    svg.append('  .zone-label { font-size: 10px; fill: #555; text-anchor: middle; }')
    svg.append('  .dim-label { font-size: 9px; fill: #888; text-anchor: middle; }')
    svg.append('  .photo-marker { cursor: pointer; }')
    svg.append('  .camera-fov { fill: rgba(255,0,0,0.08); stroke: red; stroke-width: 0.5; }')
    svg.append('</style>')
    svg.append(f'<rect x="0" y="0" width="{w}" height="{h_total}" fill="#fafafa"/>')

    def tx(x):
        return margin + x * scale

    def ty(y):
        return margin + (ancho - y) * scale  # flip Y so 0,0 is bottom-left

    # Title
    name = layout.get("name", gallinero_id)
    svg.append(f'<text x="{w // 2}" y="18" text-anchor="middle" font-size="14" font-weight="bold" fill="#333">{name}</text>')

    # Building outline
    svg.append(f'<rect x="{margin}" y="{margin}" width="{largo * scale}" height="{ancho * scale}" '
               f'fill="#FFF8E1" stroke="#795548" stroke-width="2" rx="3"/>')

    # Dimensions
    svg.append(f'<text x="{w // 2}" y="{margin - 8}" class="dim-label">{largo}m</text>')
    svg.append(f'<text x="{margin - 12}" y="{margin + ancho * scale // 2}" class="dim-label" '
               f'transform="rotate(-90,{margin - 12},{margin + ancho * scale // 2})">{ancho}m</text>')

    # Zones
    for z in layout.get("zonas", []):
        r = z["rect"]
        x, y_start, zw, zh = r
        color = _ZONE_COLORS.get(z.get("tipo"), "#E0E0E0")
        rx = tx(x)
        ry = ty(y_start + zh)
        rw = zw * scale
        rh = zh * scale
        svg.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" '
                   f'fill="{color}" stroke="#999" stroke-width="1" rx="2" opacity="0.7"/>')
        svg.append(f'<text x="{rx + rw / 2}" y="{ry + rh / 2 + 4}" class="zone-label">{z["id"]}</text>')

    # Camera + FOV cone
    cam = layout.get("camera")
    if cam:
        cx, cy = cam["posicion"][0], cam["posicion"][1]
        fov = cam.get("fov_h", 100)
        aim_x, aim_y = cam.get("apunta_hacia", [cx, 0])[:2]
        angle_to = math.atan2(aim_y - cy, aim_x - cx)
        fov_rad = math.radians(fov / 2)
        reach = max(largo, ancho) * 1.2
        # FOV triangle
        lx = cx + reach * math.cos(angle_to - fov_rad)
        ly = cy + reach * math.sin(angle_to - fov_rad)
        rx_fov = cx + reach * math.cos(angle_to + fov_rad)
        ry_fov = cy + reach * math.sin(angle_to + fov_rad)
        svg.append(f'<polygon points="{tx(cx)},{ty(cy)} {tx(lx)},{ty(ly)} {tx(rx_fov)},{ty(ry_fov)}" class="camera-fov"/>')
        # Camera icon
        svg.append(f'<circle cx="{tx(cx)}" cy="{ty(cy)}" r="6" fill="red" stroke="darkred" stroke-width="1.5"/>')
        svg.append(f'<text x="{tx(cx) + 10}" y="{ty(cy) + 4}" font-size="9" fill="red">📷</text>')

    # Fence info
    fence = layout.get("valla_compartida")
    if fence:
        pts = fence["segmento"]
        svg.append(f'<line x1="{tx(pts[0][0])}" y1="{ty(pts[0][1])}" '
                   f'x2="{tx(pts[1][0])}" y2="{ty(pts[1][1])}" '
                   f'stroke="#FF5722" stroke-width="3" stroke-dasharray="8,4"/>')
        mid_x = (tx(pts[0][0]) + tx(pts[1][0])) / 2
        mid_y = (ty(pts[0][1]) + ty(pts[1][1])) / 2
        svg.append(f'<text x="{mid_x + 8}" y="{mid_y}" font-size="9" fill="#FF5722">🐔 valla</text>')

    # Photo markers
    if include_photos:
        photos = _photos.get(gallinero_id, [])
        for i, p in enumerate(photos):
            px, py = p["pos_x"], p["pos_y"]
            pdir = p.get("direccion", 0)
            svg.append(f'<g class="photo-marker" data-photo="{p["id"]}">')
            svg.append(f'<circle cx="{tx(px)}" cy="{ty(py)}" r="5" fill="#2196F3" stroke="white" stroke-width="1.5"/>')
            # Direction arrow
            arrow_len = 15
            ax = tx(px) + arrow_len * math.sin(math.radians(pdir))
            ay = ty(py) - arrow_len * math.cos(math.radians(pdir))
            svg.append(f'<line x1="{tx(px)}" y1="{ty(py)}" x2="{ax}" y2="{ay}" stroke="#2196F3" stroke-width="1.5" marker-end="url(#arrow)"/>')
            svg.append(f'<text x="{tx(px) + 8}" y="{ty(py) - 6}" font-size="8" fill="#1565C0">{i + 1}</text>')
            svg.append('</g>')

    # Arrow marker def
    svg.append('<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">')
    svg.append('<path d="M0,0 L6,3 L0,6 Z" fill="#2196F3"/></marker></defs>')

    # Legend
    ly = h_total - 20
    svg.append(f'<text x="10" y="{ly}" font-size="9" fill="#666">'
               f'🔴 Cámara  🔵 Foto móvil  ▬▬ Valla saltable  '
               f'Zonas: ponederos / perchas / comedero / bebedero / puerta / patio</text>')

    svg.append('</svg>')
    return "\n".join(svg)


@router.get("/floorplan/{gallinero_id}")
async def get_floorplan_svg(gallinero_id: str):
    """Devolver plano SVG del gallinero."""
    if gallinero_id not in _layouts:
        raise HTTPException(404, f"Layout no encontrado para {gallinero_id}")
    svg = _generate_svg(gallinero_id)
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/floorplan/{gallinero_id}/html")
async def get_floorplan_html(gallinero_id: str):
    """Plano interactivo HTML — muestra el SVG con las fotos al hacer click."""
    if gallinero_id not in _layouts:
        raise HTTPException(404, f"Layout no encontrado para {gallinero_id}")

    layout = _layouts[gallinero_id]
    photos = _photos.get(gallinero_id, [])
    svg = _generate_svg(gallinero_id)
    photos_json = json.dumps(photos, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{layout.get('name', gallinero_id)} — Plano Digital Twin</title>
<style>
  body {{ font-family: sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
  h1 {{ font-size: 1.3em; color: #333; }}
  .container {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .svg-wrap {{ background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .sidebar {{ max-width: 350px; }}
  .photo-card {{ background: white; padding: 8px; margin: 8px 0; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); cursor: pointer; }}
  .photo-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.2); }}
  .photo-card img {{ width: 100%; border-radius: 4px; }}
  .photo-card .meta {{ font-size: 0.85em; color: #666; margin-top: 4px; }}
  #preview {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8);
              display: none; justify-content: center; align-items: center; z-index: 100; }}
  #preview img {{ max-width: 90%; max-height: 90%; border-radius: 8px; }}
  .upload-form {{ background: white; padding: 12px; border-radius: 8px; margin-bottom: 12px;
                  box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
  .upload-form input, .upload-form select {{ margin: 4px 0; display: block; width: 100%; padding: 6px; box-sizing: border-box; }}
  .upload-form button {{ background: #2196F3; color: white; border: none; padding: 10px 20px;
                         border-radius: 4px; cursor: pointer; margin-top: 8px; font-size: 1em; }}
  .badge {{ display: inline-block; background: #E3F2FD; color: #1565C0; padding: 2px 6px;
            border-radius: 3px; font-size: 0.8em; }}
</style>
</head>
<body>
<h1>📐 {layout.get('name', gallinero_id)} — Plano Digital Twin</h1>
<div class="container">
  <div class="svg-wrap">{svg}</div>
  <div class="sidebar">
    <div class="upload-form">
      <h3>📱 Subir foto del móvil</h3>
      <form id="uploadForm" enctype="multipart/form-data">
        <input type="file" name="foto" accept="image/*" capture="environment" required>
        <input type="number" name="pos_x" placeholder="Pos X (metros)" step="0.1" value="0">
        <input type="number" name="pos_y" placeholder="Pos Y (metros)" step="0.1" value="0">
        <input type="number" name="direccion" placeholder="Dirección (0°=N, 90°=E)" step="15" value="0">
        <select name="tipo">
          <option value="general">General</option>
          <option value="ponedero">Ponedero</option>
          <option value="perchas">Perchas</option>
          <option value="comedero">Comedero</option>
          <option value="bebedero">Bebedero</option>
          <option value="puerta">Puerta</option>
          <option value="valla">Valla</option>
          <option value="patio">Patio</option>
          <option value="techo">Techo</option>
          <option value="detalle">Detalle</option>
        </select>
        <input type="text" name="descripcion" placeholder="¿Qué se ve en la foto?">
        <button type="submit">📤 Subir</button>
      </form>
    </div>
    <h3>📸 Fotos ({len(photos)})</h3>
    <div id="photoList"></div>
  </div>
</div>
<div id="preview" onclick="this.style.display='none'"><img id="previewImg"></div>
<script>
const GID = "{gallinero_id}";
const API = window.location.origin;
let photos = {photos_json};

function renderPhotos() {{
  const list = document.getElementById('photoList');
  list.innerHTML = photos.map((p, i) => `
    <div class="photo-card" onclick="showPreview('${{p.id}}')">
      <img src="${{API}}/survey/photo/${{GID}}/${{p.id}}" loading="lazy">
      <div class="meta">
        <span class="badge">#${{i+1}}</span>
        <span class="badge">${{p.tipo}}</span>
        (${{p.pos_x}},${{p.pos_y}}) → ${{p.direccion}}°
        ${{p.descripcion ? '— ' + p.descripcion : ''}}
      </div>
    </div>
  `).join('');
}}

function showPreview(id) {{
  document.getElementById('previewImg').src = `${{API}}/survey/photo/${{GID}}/${{id}}`;
  document.getElementById('preview').style.display = 'flex';
}}

document.getElementById('uploadForm').addEventListener('submit', async e => {{
  e.preventDefault();
  const fd = new FormData(e.target);
  fd.append('gallinero_id', GID);
  try {{
    const r = await fetch(`${{API}}/survey/photo`, {{ method: 'POST', body: fd }});
    const d = await r.json();
    if (d.ok) {{
      alert('✅ Foto subida (#' + d.total_photos + ')');
      location.reload();
    }} else {{
      alert('❌ Error: ' + JSON.stringify(d));
    }}
  }} catch(err) {{ alert('❌ ' + err); }}
}});

renderPhotos();
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
