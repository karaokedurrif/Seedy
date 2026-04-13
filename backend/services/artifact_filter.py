"""
Seedy Backend — Filtro de artefactos de tile para YOLO

El modelo breed (seedy_breeds_best.pt) fue entrenado con crops de 1 ave llenando
el frame. Cuando se usa como detector sobre tiles, genera bboxes del tamaño del tile.
Este filtro elimina esos artefactos.

También filtra ruido (bboxes demasiado pequeñas) y detecciones parciales
(bboxes tocando múltiples bordes del tile).
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

# Parámetros por defecto (Fase 25 calibrados)
DEFAULT_MAX_AREA_RATIO = 0.45    # Bbox > 45% del tile = artefacto
DEFAULT_MIN_AREA_RATIO = 0.008   # Bbox < 0.8% del frame = ruido
DEFAULT_BORDER_MARGIN = 0.02     # 2% del tile
DEFAULT_MAX_ASPECT_RATIO = 3.5   # Ratio ancho/alto máximo


def filter_tile_artifacts(
    detections: List[dict],
    tile_w: int,
    tile_h: int,
    max_area_ratio: float = DEFAULT_MAX_AREA_RATIO,
    min_area_ratio: float = DEFAULT_MIN_AREA_RATIO,
    border_margin: float = DEFAULT_BORDER_MARGIN,
    max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
) -> List[dict]:
    """
    Filtra artefactos del modelo breed y detecciones ruidosas.

    Args:
        detections: Lista de detecciones con keys: x1, y1, x2, y2, conf
        tile_w, tile_h: Dimensiones del tile (o frame si no hay tileado)
        max_area_ratio: Máximo ratio bbox/tile permitido (>0.45 = artefacto)
        min_area_ratio: Mínimo ratio bbox/tile (< = ruido)
        border_margin: Margen de borde como ratio del tile
        max_aspect_ratio: Máximo ratio width/height (o inverso)

    Returns:
        Lista filtrada de detecciones reales
    """
    tile_area = tile_w * tile_h
    if tile_area <= 0:
        return detections

    margin_x = tile_w * border_margin
    margin_y = tile_h * border_margin
    valid = []
    filtered_counts = {"artifact": 0, "noise": 0, "border": 0, "aspect": 0}

    for det in detections:
        x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
        w = x2 - x1
        h = y2 - y1

        if w <= 0 or h <= 0:
            continue

        bbox_area = w * h
        area_ratio = bbox_area / tile_area

        # Artefacto: bbox ocupa >45% del tile
        if area_ratio > max_area_ratio:
            filtered_counts["artifact"] += 1
            continue

        # Ruido: bbox demasiado pequeña
        if area_ratio < min_area_ratio:
            filtered_counts["noise"] += 1
            continue

        # Parcial: bbox toca 2 o más bordes del tile (crop incompleto)
        touches_border = sum([
            x1 < margin_x,
            y1 < margin_y,
            x2 > tile_w - margin_x,
            y2 > tile_h - margin_y,
        ])
        if touches_border >= 2:
            filtered_counts["border"] += 1
            continue

        # Aspect ratio anómalo
        aspect = max(w / h, h / w)
        if aspect > max_aspect_ratio:
            filtered_counts["aspect"] += 1
            continue

        valid.append(det)

    total_filtered = sum(filtered_counts.values())
    if total_filtered > 0:
        logger.debug(
            f"Artifact filter: {len(detections)} → {len(valid)} "
            f"(filtered: {filtered_counts})"
        )

    return valid


def filter_frame_artifacts(
    detections: List[dict],
    frame_w: int,
    frame_h: int,
    max_area_ratio: float = 0.45,
    min_area_ratio: float = 0.002,
) -> List[dict]:
    """
    Filtro simplificado a nivel de frame completo (post-NMS global).
    Menos restrictivo que el filtro de tile.
    """
    frame_area = frame_w * frame_h
    if frame_area <= 0:
        return detections

    valid = []
    for det in detections:
        x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
        bbox_area = (x2 - x1) * (y2 - y1)
        ratio = bbox_area / frame_area

        if ratio > max_area_ratio:
            continue
        if ratio < min_area_ratio:
            continue

        valid.append(det)

    return valid
