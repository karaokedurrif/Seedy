"""
BIM-lite API — Fuente de verdad geométrica para el Digital Twin.

Endpoints:
  GET  /api/bim/{tenant}              → BIM JSON completo
  GET  /api/bim/{tenant}/elements     → solo elementos
  GET  /api/bim/{tenant}/elements/{id}→ un elemento
  GET  /api/bim/{tenant}/layers       → capas dinámicas
  POST /api/bim/{tenant}/elements     → añadir elemento
  PUT  /api/bim/{tenant}/elements/{id}→ editar elemento
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bim", tags=["BIM"])

# BIM data directory — in Docker: /app/bim (mounted from ./Digital Twin/)
BIM_DIR = Path(os.environ.get("BIM_DATA_DIR", "/app/bim"))

# Cache loaded BIM per tenant
_bim_cache: dict[str, dict] = {}


def _bim_path(tenant: str) -> Path:
    return BIM_DIR / "granja_bim_semantico.json"


def _load_bim(tenant: str) -> dict:
    """Load BIM JSON for a tenant, with file-based caching."""
    path = _bim_path(tenant)
    if not path.exists():
        raise HTTPException(404, f"BIM data not found for tenant '{tenant}'")

    mtime = path.stat().st_mtime
    cached = _bim_cache.get(tenant)
    if cached and cached.get("_mtime") == mtime:
        return cached

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_mtime"] = mtime
    _bim_cache[tenant] = data
    logger.info(f"BIM loaded for tenant={tenant}: {len(data.get('elements', []))} elements")
    return data


def _save_bim(tenant: str, data: dict):
    """Persist BIM JSON to disk."""
    path = _bim_path(tenant)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_data = {k: v for k, v in data.items() if k != "_mtime"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    # Invalidate cache
    _bim_cache.pop(tenant, None)


# ── Models ──

class BIMElement(BaseModel):
    id: str
    class_: str | None = None
    name: str
    geometry: dict[str, Any]
    properties: dict[str, Any] | None = None

    class Config:
        populate_by_name = True

    def to_bim_dict(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "name": self.name, "geometry": self.geometry}
        if self.class_:
            d["class"] = self.class_
        if self.properties:
            d["properties"] = self.properties
        return d


class BIMElementUpdate(BaseModel):
    name: str | None = None
    class_: str | None = None
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None


# ── Endpoints ──

@router.get("/{tenant}")
async def get_bim(tenant: str):
    """BIM JSON completo."""
    data = _load_bim(tenant)
    return {k: v for k, v in data.items() if k != "_mtime"}


@router.get("/{tenant}/elements")
async def get_elements(tenant: str):
    """Solo la lista de elementos."""
    data = _load_bim(tenant)
    return data.get("elements", [])


@router.get("/{tenant}/elements/{element_id}")
async def get_element(tenant: str, element_id: str):
    """Un elemento por ID."""
    data = _load_bim(tenant)
    for el in data.get("elements", []):
        if el.get("id") == element_id:
            return el
    raise HTTPException(404, f"Element '{element_id}' not found")


@router.get("/{tenant}/layers")
async def get_layers(tenant: str):
    """Capas dinámicas (schema + source info)."""
    data = _load_bim(tenant)
    return data.get("dynamic_layers", {})


@router.post("/{tenant}/elements", status_code=201)
async def add_element(tenant: str, element: BIMElement):
    """Añadir un nuevo elemento al BIM."""
    data = _load_bim(tenant)
    elements = data.get("elements", [])
    # Check duplicate ID
    if any(el.get("id") == element.id for el in elements):
        raise HTTPException(409, f"Element '{element.id}' already exists")
    elements.append(element.to_bim_dict())
    data["elements"] = elements
    _save_bim(tenant, data)
    return element.to_bim_dict()


@router.put("/{tenant}/elements/{element_id}")
async def update_element(tenant: str, element_id: str, update: BIMElementUpdate):
    """Editar un elemento existente."""
    data = _load_bim(tenant)
    elements = data.get("elements", [])
    for i, el in enumerate(elements):
        if el.get("id") == element_id:
            if update.name is not None:
                el["name"] = update.name
            if update.class_ is not None:
                el["class"] = update.class_
            if update.geometry is not None:
                el["geometry"] = update.geometry
            if update.properties is not None:
                el["properties"] = update.properties
            elements[i] = el
            data["elements"] = elements
            _save_bim(tenant, data)
            return el
    raise HTTPException(404, f"Element '{element_id}' not found")


# ── Ortofoto (Task F — Drone pipeline) ──

@router.post("/{tenant}/ortofoto", status_code=201)
async def upload_ortofoto(tenant: str):
    """
    Upload ortofoto GeoTIFF from drone (DJI Mini 4 Pro).
    Stores in BIM_DIR/ortofoto/ for use as terrain texture in 3D twin.
    Accepts multipart/form-data with 'file' field.
    """
    from fastapi import UploadFile, File
    # This is a stub — the actual upload handling requires the
    # endpoint to be re-declared with File() dependency.
    # For now, return the expected structure.
    ortofoto_dir = BIM_DIR / "ortofoto"
    ortofoto_dir.mkdir(parents=True, exist_ok=True)
    return {
        "status": "ready",
        "upload_path": str(ortofoto_dir),
        "supported_formats": ["GeoTIFF (.tif)", "JPEG (.jpg)", "PNG (.png)"],
        "notes": "POST multipart/form-data with 'file' field. Max 500MB.",
        "pipeline": {
            "step_1": "Upload raw drone photos (.jpg + EXIF GPS)",
            "step_2": "Process with OpenDroneMap/WebODM → ortofoto GeoTIFF",
            "step_3": "Upload GeoTIFF here → stored as terrain texture",
            "step_4": "Three.js loads as PlaneGeometry texture",
        },
    }


@router.get("/{tenant}/ortofoto")
async def get_ortofoto_info(tenant: str):
    """Check if ortofoto exists and return metadata."""
    ortofoto_dir = BIM_DIR / "ortofoto"
    files = []
    if ortofoto_dir.exists():
        for f in ortofoto_dir.iterdir():
            if f.suffix.lower() in (".tif", ".tiff", ".jpg", ".jpeg", ".png"):
                files.append({
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "url": f"/api/bim/{tenant}/ortofoto/{f.name}",
                })
    return {
        "tenant": tenant,
        "has_ortofoto": len(files) > 0,
        "files": files,
        "geotwin_url": "https://geoTwin.es",
        "geotwin_twin_id": "Yasg5zxsF_",
    }
