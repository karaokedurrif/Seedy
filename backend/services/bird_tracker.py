"""
Seedy Backend — Tracker de aves individuales

Tracking por centroide + IoU entre frames consecutivos.
Mantiene un perfil por ave: posiciones, zonas visitadas,
tamaño corporal, actividad, y genera alertas de comportamiento.

Funciona sin re-ID visual (eso vendrá con embeddings en Fase 3).
Por ahora: matching por proximidad/overlap entre detecciones.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuración del tracker ──
MAX_LOST_FRAMES = 5       # Frames sin detectar antes de "perder" el track
IOU_THRESHOLD = 0.25      # IoU mínimo para match
MAX_TRACKS = 50           # Máximo de tracks activos por gallinero
HISTORY_LENGTH = 120      # Frames de historial por track (~30min a 15s/frame)

# ── Zonas del gallinero (se configuran por gallinero) ──
# Coordenadas normalizadas [x1, y1, x2, y2]
DEFAULT_ZONES = {
    "comedero":   {"bbox": [0.0, 0.6, 0.3, 1.0], "type": "feeding"},
    "bebedero":   {"bbox": [0.3, 0.6, 0.5, 1.0], "type": "drinking"},
    "aseladero":  {"bbox": [0.0, 0.0, 1.0, 0.3], "type": "perching"},
    "nido":       {"bbox": [0.7, 0.0, 1.0, 0.4], "type": "nesting"},
    "zona_libre": {"bbox": [0.2, 0.3, 0.8, 0.7], "type": "roaming"},
}

# Zonas configuradas por gallinero
_zones: dict[str, dict] = {}


def configure_zones(gallinero_id: str, zones: dict):
    """Configura las zonas de un gallinero específico."""
    _zones[gallinero_id] = zones
    logger.info(f"Zones configured for {gallinero_id}: {list(zones.keys())}")


def get_zones(gallinero_id: str) -> dict:
    return _zones.get(gallinero_id, DEFAULT_ZONES)


# ── Modelo de datos del track ──

@dataclass
class TrackPoint:
    """Un punto en el historial de un track."""
    timestamp: float           # time.time()
    center: tuple[float, float]  # (cx, cy) normalizado
    bbox_norm: list[float]     # [x1, y1, x2, y2]
    area_norm: float
    zone: str = ""             # zona actual
    confidence: float = 0.0


@dataclass
class BirdTrack:
    """Perfil de un ave trackeada."""
    track_id: int
    gallinero: str
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_bbox_norm: list = field(default_factory=list)
    lost_frames: int = 0
    active: bool = True

    # Historial de posiciones
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))

    # Estadísticas acumuladas
    total_frames: int = 0
    zone_time: dict = field(default_factory=lambda: defaultdict(int))  # zona → frames
    sizes: list = field(default_factory=list)  # area_norm por frame
    distances: list = field(default_factory=list)  # distancia entre frames

    # Clasificación (se actualiza con Gemini/YOLO custom)
    class_name: str = "bird"
    breed: str = ""
    sex: str = ""
    ai_vision_id: str = ""

    def update(self, detection: dict, zones: dict):
        """Actualiza track con nueva detección."""
        now = time.time()
        bn = detection.get("bbox_norm", [])
        if len(bn) != 4:
            return

        cx = (bn[0] + bn[2]) / 2
        cy = (bn[1] + bn[3]) / 2
        area = detection.get("area_norm", (bn[2] - bn[0]) * (bn[3] - bn[1]))

        # Calcular zona
        zone = _point_in_zone(cx, cy, zones)

        # Distancia desde último punto
        if self.history:
            prev = self.history[-1]
            dx = cx - prev.center[0]
            dy = cy - prev.center[1]
            dist = (dx**2 + dy**2) ** 0.5
            self.distances.append(dist)
        else:
            dist = 0.0

        point = TrackPoint(
            timestamp=now,
            center=(cx, cy),
            bbox_norm=bn,
            area_norm=area,
            zone=zone,
            confidence=detection.get("confidence", 0),
        )
        self.history.append(point)

        self.last_seen = now
        self.last_bbox_norm = bn
        self.lost_frames = 0
        self.active = True
        self.total_frames += 1
        self.sizes.append(area)
        if zone:
            self.zone_time[zone] += 1

        # Actualizar clase si el modelo custom la da
        if detection.get("class_name") and detection["class_name"] != "bird":
            self.class_name = detection["class_name"]

    def mark_lost(self):
        self.lost_frames += 1
        if self.lost_frames >= MAX_LOST_FRAMES:
            self.active = False

    def get_profile(self) -> dict:
        """Devuelve perfil resumido del track."""
        elapsed = self.last_seen - self.first_seen
        avg_size = sum(self.sizes[-20:]) / max(len(self.sizes[-20:]), 1)
        total_dist = sum(self.distances)

        # Zona principal
        main_zone = ""
        if self.zone_time:
            main_zone = max(self.zone_time, key=self.zone_time.get)

        # Nivel de actividad
        recent_dists = self.distances[-10:] if self.distances else []
        avg_movement = sum(recent_dists) / max(len(recent_dists), 1)
        if avg_movement < 0.01:
            activity = "quieta"
        elif avg_movement < 0.05:
            activity = "normal"
        else:
            activity = "activa"

        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "breed": self.breed,
            "sex": self.sex,
            "ai_vision_id": self.ai_vision_id,
            "active": self.active,
            "total_frames": self.total_frames,
            "elapsed_s": round(elapsed, 1),
            "avg_size": round(avg_size, 6),
            "total_distance": round(total_dist, 4),
            "avg_movement": round(avg_movement, 4),
            "activity": activity,
            "main_zone": main_zone,
            "zone_time": dict(self.zone_time),
            "current_zone": self.history[-1].zone if self.history else "",
        }


def _point_in_zone(cx: float, cy: float, zones: dict) -> str:
    """Devuelve la zona en la que cae el punto (cx, cy)."""
    for name, info in zones.items():
        bbox = info.get("bbox", [])
        if len(bbox) != 4:
            continue
        if bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]:
            return name
    return "zona_libre"


def _iou(box1: list, box2: list) -> float:
    """Calcula IoU entre dos bboxes normalizados [x1,y1,x2,y2]."""
    if len(box1) != 4 or len(box2) != 4:
        return 0.0
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    return inter / (a1 + a2 - inter)


# ── Tracker por gallinero ──

class GallineroTracker:
    """Tracker multi-objeto para un gallinero."""

    def __init__(self, gallinero_id: str):
        self.gallinero_id = gallinero_id
        self.tracks: dict[int, BirdTrack] = {}
        self._next_id = 1
        self._frame_count = 0

    def update(self, detections: list[dict]) -> list[dict]:
        """
        Actualiza todos los tracks con las nuevas detecciones.

        Usa matching por IoU (greedy) entre tracks activos y detecciones.

        Returns: detecciones enriquecidas con track_id
        """
        self._frame_count += 1
        zones = get_zones(self.gallinero_id)
        active_tracks = {tid: t for tid, t in self.tracks.items() if t.active}

        # Filtrar solo aves (no plagas ni infra)
        bird_dets = [d for d in detections if d.get("category", "poultry") == "poultry"]

        if not active_tracks:
            # Primer frame o todos los tracks perdidos → crear nuevos
            for det in bird_dets:
                track = BirdTrack(
                    track_id=self._next_id,
                    gallinero=self.gallinero_id,
                )
                track.update(det, zones)
                self.tracks[self._next_id] = track
                det["track_id"] = self._next_id
                self._next_id += 1
            return detections

        # Calcular matriz de IoU
        track_ids = list(active_tracks.keys())
        matches = []
        for di, det in enumerate(bird_dets):
            det_bbox = det.get("bbox_norm", [])
            best_iou = 0.0
            best_tid = None
            for tid in track_ids:
                t = active_tracks[tid]
                iou = _iou(t.last_bbox_norm, det_bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid
            if best_iou >= IOU_THRESHOLD and best_tid is not None:
                matches.append((di, best_tid, best_iou))

        # Greedy match: ordenar por IoU desc, asignar sin repetir
        matches.sort(key=lambda x: x[2], reverse=True)
        matched_dets = set()
        matched_tracks = set()

        for di, tid, _ in matches:
            if di in matched_dets or tid in matched_tracks:
                continue
            active_tracks[tid].update(bird_dets[di], zones)
            bird_dets[di]["track_id"] = tid
            matched_dets.add(di)
            matched_tracks.add(tid)

        # Detecciones sin match → nuevos tracks
        for di, det in enumerate(bird_dets):
            if di not in matched_dets:
                if len(self.tracks) < MAX_TRACKS:
                    track = BirdTrack(
                        track_id=self._next_id,
                        gallinero=self.gallinero_id,
                    )
                    track.update(det, zones)
                    self.tracks[self._next_id] = track
                    det["track_id"] = self._next_id
                    self._next_id += 1

        # Tracks sin match → mark lost
        for tid in track_ids:
            if tid not in matched_tracks:
                active_tracks[tid].mark_lost()

        return detections

    def get_active_tracks(self) -> list[dict]:
        return [t.get_profile() for t in self.tracks.values() if t.active]

    def get_all_profiles(self) -> list[dict]:
        return [t.get_profile() for t in self.tracks.values()]

    def get_summary(self) -> dict:
        """Resumen del gallinero."""
        active = [t for t in self.tracks.values() if t.active]
        profiles = [t.get_profile() for t in active]

        # Distribución por zona
        zone_counts = defaultdict(int)
        for p in profiles:
            z = p.get("current_zone", "")
            if z:
                zone_counts[z] += 1

        # Distribución por actividad
        activity_counts = defaultdict(int)
        for p in profiles:
            activity_counts[p.get("activity", "?")] += 1

        # Distribución por clase
        class_counts = defaultdict(int)
        for p in profiles:
            class_counts[p.get("class_name", "bird")] += 1

        return {
            "gallinero": self.gallinero_id,
            "active_tracks": len(active),
            "total_tracks": len(self.tracks),
            "frames_processed": self._frame_count,
            "zone_distribution": dict(zone_counts),
            "activity_distribution": dict(activity_counts),
            "class_distribution": dict(class_counts),
        }

    def detect_anomalies(self) -> list[dict]:
        """
        Detecta comportamientos anómalos.

        Alertas:
          - Inmovilidad prolongada (>10 frames quieta)
          - Aislamiento (ave sola lejos del grupo)
          - Actividad excesiva (>10x movimiento normal)
          - Ave en nido demasiado tiempo (posible clueca/encerrada)
        """
        alerts = []
        active = [t for t in self.tracks.values() if t.active]

        if len(active) < 2:
            return alerts

        # Centros de todas las aves activas
        centers = []
        for t in active:
            if t.history:
                centers.append(t.history[-1].center)

        # Media de movimiento del grupo
        group_movements = []
        for t in active:
            recent = t.distances[-5:] if t.distances else [0]
            group_movements.append(sum(recent) / len(recent))
        avg_group_movement = sum(group_movements) / max(len(group_movements), 1)

        for t in active:
            profile = t.get_profile()
            tid = t.track_id

            # 1. Inmovilidad prolongada
            if t.total_frames >= 10 and profile["activity"] == "quieta":
                recent_dists = t.distances[-10:] if t.distances else [0]
                total_recent = sum(recent_dists)
                if total_recent < 0.005:
                    alerts.append({
                        "type": "inmovilidad",
                        "track_id": tid,
                        "severity": "warning",
                        "detail": (
                            f"Ave #{tid} inmóvil durante {t.total_frames} frames "
                            f"en zona {profile['current_zone']}"
                        ),
                        "zone": profile["current_zone"],
                    })

            # 2. Aislamiento
            if centers and t.history:
                my_center = t.history[-1].center
                dists_to_others = []
                for c in centers:
                    if c != my_center:
                        d = ((my_center[0]-c[0])**2 + (my_center[1]-c[1])**2)**0.5
                        dists_to_others.append(d)
                if dists_to_others:
                    min_dist = min(dists_to_others)
                    avg_dist = sum(dists_to_others) / len(dists_to_others)
                    if min_dist > 0.3:  # >30% del frame de distancia al más cercano
                        alerts.append({
                            "type": "aislamiento",
                            "track_id": tid,
                            "severity": "info",
                            "detail": (
                                f"Ave #{tid} aislada del grupo "
                                f"(dist mínima: {min_dist:.2f})"
                            ),
                            "distance": round(min_dist, 3),
                        })

            # 3. Hiperactividad
            if avg_group_movement > 0 and profile["avg_movement"] > avg_group_movement * 5:
                alerts.append({
                    "type": "hiperactividad",
                    "track_id": tid,
                    "severity": "info",
                    "detail": (
                        f"Ave #{tid} movimiento {profile['avg_movement']:.4f} "
                        f"vs grupo {avg_group_movement:.4f}"
                    ),
                })

            # 4. Permanencia excesiva en nido (>20 frames = ~5min)
            nido_time = t.zone_time.get("nido", 0)
            if nido_time > 20 and profile["current_zone"] == "nido":
                alerts.append({
                    "type": "nido_prolongado",
                    "track_id": tid,
                    "severity": "info",
                    "detail": (
                        f"Ave #{tid} en nido durante {nido_time} frames "
                        f"(¿clueca? ¿empollando? ¿atrapada?)"
                    ),
                })

        return alerts

    def reset(self):
        """Reset completo del tracker."""
        self.tracks.clear()
        self._next_id = 1
        self._frame_count = 0


# ── Singleton de trackers por gallinero ──
_trackers: dict[str, GallineroTracker] = {}


def get_tracker(gallinero_id: str) -> GallineroTracker:
    if gallinero_id not in _trackers:
        _trackers[gallinero_id] = GallineroTracker(gallinero_id)
    return _trackers[gallinero_id]


def get_all_summaries() -> dict:
    """Resumen de todos los gallineros activos."""
    return {gid: t.get_summary() for gid, t in _trackers.items()}
