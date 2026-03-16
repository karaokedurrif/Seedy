"""
Seedy Vision — Análisis de Comportamiento Animal
Tracking multi-objeto + clasificación temporal de actividad.

Pipeline:
  1. YOLO detecta animales en cada frame
  2. ByteTrack/BoT-SORT asigna IDs temporales (tracking)
  3. Ventana temporal de N frames → clasificación de actividad
  4. Alertas por comportamiento anómalo
"""
import time
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque
from typing import Optional
from dataclasses import dataclass, field, asdict

import numpy as np
from rich.console import Console

console = Console()


# ─────────────────────────────────────────────────────
# Estructuras de datos
# ─────────────────────────────────────────────────────

@dataclass
class TrackedAnimal:
    """Animal trackeado con historial de posiciones"""
    track_id: int
    class_name: str
    positions: deque = field(default_factory=lambda: deque(maxlen=300))  # ~10s a 30fps
    velocities: deque = field(default_factory=lambda: deque(maxlen=300))
    last_seen: float = 0.0
    current_activity: str = "unknown"
    activity_confidence: float = 0.0
    alerts: list = field(default_factory=list)


@dataclass
class BehaviourEvent:
    """Evento de comportamiento detectado"""
    timestamp: str
    camera_id: str
    track_id: int
    species: str
    behaviour: str
    confidence: float
    duration_seconds: float
    severity: str  # info, warning, alert
    bbox: list[float]
    
    def to_dict(self):
        return asdict(self)


# ─────────────────────────────────────────────────────
# Tracker (YOLO built-in BoT-SORT)
# ─────────────────────────────────────────────────────

class AnimalTracker:
    """
    Wrapper sobre el tracking integrado de Ultralytics YOLO.
    Mantiene historial de cada animal individualmente.
    """
    
    def __init__(self, model_path: str,
                 tracker_type: str = "botsort",
                 conf: float = 0.4,
                 iou: float = 0.5,
                 imgsz: int = 640,
                 device: str = "0",
                 max_age: float = 5.0):
        """
        Args:
            model_path: Modelo YOLO entrenado
            tracker_type: "botsort" o "bytetrack"
            max_age: Segundos sin ver un animal antes de eliminarlo
        """
        from ultralytics import YOLO
        
        self.model = YOLO(model_path)
        self.tracker_type = tracker_type
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.device = device
        self.max_age = max_age
        
        # Estado
        self.tracked: dict[int, TrackedAnimal] = {}
        self.frame_count = 0
        self.fps = 30.0
    
    def update(self, frame: np.ndarray, class_names: list[str]) -> list[TrackedAnimal]:
        """
        Procesa un frame: detección + tracking + actualización de estado.
        
        Returns: Lista de animales actualmente trackeados
        """
        self.frame_count += 1
        now = time.time()
        h, w = frame.shape[:2]
        
        # YOLO tracking
        results = self.model.track(
            frame,
            persist=True,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            device=self.device,
            tracker=f"{self.tracker_type}.yaml",
            verbose=False,
        )
        
        active_ids = set()
        
        for result in results:
            if result.boxes is None or result.boxes.id is None:
                continue
            
            for box, track_id, cls_id in zip(
                result.boxes.xyxy.cpu().numpy(),
                result.boxes.id.cpu().numpy().astype(int),
                result.boxes.cls.cpu().numpy().astype(int),
            ):
                active_ids.add(track_id)
                x1, y1, x2, y2 = box
                
                # Centro normalizado
                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                
                cls_name = class_names[cls_id] if cls_id < len(class_names) else f"class_{cls_id}"
                
                if track_id not in self.tracked:
                    self.tracked[track_id] = TrackedAnimal(
                        track_id=track_id,
                        class_name=cls_name,
                    )
                
                animal = self.tracked[track_id]
                
                # Calcular velocidad
                if animal.positions:
                    prev_cx, prev_cy, _ = animal.positions[-1]
                    dt = 1.0 / self.fps
                    vx = (cx - prev_cx) / dt
                    vy = (cy - prev_cy) / dt
                    speed = np.sqrt(vx**2 + vy**2)
                    animal.velocities.append(speed)
                
                animal.positions.append((cx, cy, now))
                animal.last_seen = now
        
        # Limpiar animales no vistos
        stale = [
            tid for tid, a in self.tracked.items()
            if now - a.last_seen > self.max_age and tid not in active_ids
        ]
        for tid in stale:
            del self.tracked[tid]
        
        return list(self.tracked.values())


# ─────────────────────────────────────────────────────
# Clasificador de comportamiento
# ─────────────────────────────────────────────────────

class BehaviourClassifier:
    """
    Clasifica el comportamiento de cada animal basado en su historial
    de movimiento (velocidad, posición, patrón temporal).
    
    Reglas heurísticas + umbrales configurables.
    En el futuro: reemplazar con transformer temporal (LSTM/Transformer).
    """
    
    # Umbrales de velocidad (normalizada, unidades/segundo)
    THRESHOLDS = {
        "resting": 0.005,      # Casi inmóvil
        "walking": 0.05,       # Movimiento lento
        "running": 0.15,       # Movimiento rápido
        "stereotypy_min_duration": 30,  # Segundos de movimiento repetitivo
    }
    
    def __init__(self, window_seconds: float = 3.0, fps: float = 30.0):
        """
        Args:
            window_seconds: Ventana temporal para clasificar
            fps: FPS del stream para calcular frames en ventana
        """
        self.window_frames = int(window_seconds * fps)
        self.fps = fps
        
        # Historial de actividades por animal
        self.activity_history: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=600)  # ~20s de historial
        )
    
    def classify(self, animal: TrackedAnimal) -> tuple[str, float]:
        """
        Clasifica el comportamiento actual de un animal.
        
        Returns: (behaviour_name, confidence)
        """
        if len(animal.velocities) < 5:
            return "unknown", 0.0
        
        # Velocidad media en la ventana
        recent_speeds = list(animal.velocities)[-self.window_frames:]
        avg_speed = np.mean(recent_speeds) if recent_speeds else 0.0
        speed_std = np.std(recent_speeds) if len(recent_speeds) > 1 else 0.0
        max_speed = max(recent_speeds) if recent_speeds else 0.0
        
        # Posiciones recientes para detectar patrones espaciales
        recent_pos = list(animal.positions)[-self.window_frames:]
        
        # ── Clasificación por reglas ──
        
        # 1. Resting (tumbado/quieto)
        if avg_speed < self.THRESHOLDS["resting"]:
            return "resting", 0.9
        
        # 2. Running (huida, persecución)
        if avg_speed > self.THRESHOLDS["running"]:
            return "running", min(0.95, avg_speed / 0.3)
        
        # 3. Walking normal
        if self.THRESHOLDS["resting"] <= avg_speed <= self.THRESHOLDS["walking"]:
            return "walking", 0.8
        
        # 4. Fighting (alta velocidad + cercanía a otro animal)
        if max_speed > self.THRESHOLDS["running"] and speed_std > 0.05:
            return "fighting", 0.6
        
        # 5. Stereotypy (movimiento repetitivo — bar biting, head weaving)
        if len(recent_pos) >= 30:
            x_positions = [p[0] for p in recent_pos]
            # Detectar oscilación: muchos cambios de dirección
            direction_changes = 0
            for i in range(2, len(x_positions)):
                d1 = x_positions[i-1] - x_positions[i-2]
                d2 = x_positions[i] - x_positions[i-1]
                if d1 * d2 < 0:  # Cambio de dirección
                    direction_changes += 1
            
            oscillation_rate = direction_changes / len(x_positions)
            if oscillation_rate > 0.3:
                return "stereotypy", min(0.9, oscillation_rate)
        
        # 6. Default: active (caminar con propósito)
        return "active", 0.7
    
    def detect_anomalies(self, animals: list[TrackedAnimal],
                          camera_id: str) -> list[BehaviourEvent]:
        """
        Detecta comportamientos anómalos que requieren alerta.
        """
        events = []
        now = datetime.now()
        
        for animal in animals:
            behaviour, confidence = self.classify(animal)
            animal.current_activity = behaviour
            animal.activity_confidence = confidence
            
            self.activity_history[animal.track_id].append(
                (now.timestamp(), behaviour, confidence)
            )
            
            # ── Reglas de alerta ──
            severity = None
            
            # Pelea detectada
            if behaviour == "fighting" and confidence > 0.7:
                severity = "alert"
            
            # Estereotipia prolongada
            elif behaviour == "stereotypy":
                history = self.activity_history[animal.track_id]
                stereo_count = sum(
                    1 for _, b, _ in list(history)[-90:]
                    if b == "stereotypy"
                )
                if stereo_count > 60:  # >2/3 del tiempo
                    severity = "warning"
            
            # Animal tumbado demasiado tiempo
            elif behaviour == "resting":
                history = self.activity_history[animal.track_id]
                rest_count = sum(
                    1 for _, b, _ in list(history)[-300:]
                    if b == "resting"
                )
                if rest_count > 270:  # >90% del tiempo en 10s
                    severity = "warning"
            
            # Animal corriendo (estrés / pánico)
            elif behaviour == "running" and confidence > 0.8:
                severity = "info"
            
            if severity:
                # Calcular duración
                history = self.activity_history[animal.track_id]
                duration = 0
                for ts, b, _ in reversed(list(history)):
                    if b == behaviour:
                        duration += 1.0 / self.fps
                    else:
                        break
                
                events.append(BehaviourEvent(
                    timestamp=now.isoformat(),
                    camera_id=camera_id,
                    track_id=animal.track_id,
                    species=animal.class_name,
                    behaviour=behaviour,
                    confidence=confidence,
                    duration_seconds=duration,
                    severity=severity,
                    bbox=[],
                ))
        
        return events
    
    def detect_grouping_anomaly(self, animals: list[TrackedAnimal],
                                  camera_id: str,
                                  max_density_threshold: float = 0.15
                                  ) -> Optional[BehaviourEvent]:
        """
        Detecta agrupamientos anormales: todos los animales en una esquina
        (posible problema ambiental, depredador, estrés).
        """
        if len(animals) < 3:
            return None
        
        positions = []
        for a in animals:
            if a.positions:
                cx, cy, _ = a.positions[-1]
                positions.append((cx, cy))
        
        if len(positions) < 3:
            return None
        
        # Calcular dispersión (std de posiciones)
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        spread = np.std(xs) + np.std(ys)
        
        if spread < max_density_threshold:
            return BehaviourEvent(
                timestamp=datetime.now().isoformat(),
                camera_id=camera_id,
                track_id=-1,  # Evento grupal
                species=animals[0].class_name,
                behaviour="abnormal_grouping",
                confidence=min(0.95, 1.0 - spread / max_density_threshold),
                duration_seconds=0,
                severity="alert",
                bbox=[min(xs), min(ys), max(xs), max(ys)],
            )
        
        return None


# ─────────────────────────────────────────────────────
# Pipeline integrado
# ─────────────────────────────────────────────────────

class BehaviourPipeline:
    """
    Pipeline completo: tracking + clasificación + alertas.
    Se integra con el SeedyCameraPipeline de jetson_inference.py.
    """
    
    def __init__(self, model_path: str,
                 class_names: list[str],
                 camera_id: str = "cam0",
                 device: str = "0",
                 fps: float = 30.0):
        self.tracker = AnimalTracker(model_path, device=device)
        self.tracker.fps = fps
        self.classifier = BehaviourClassifier(fps=fps)
        self.class_names = class_names
        self.camera_id = camera_id
        self.event_buffer: list[BehaviourEvent] = []
    
    def process_frame(self, frame: np.ndarray) -> dict:
        """
        Procesa un frame completo.
        
        Returns: {
            "animals": [...],
            "events": [...],
            "summary": {...}
        }
        """
        # 1. Track
        animals = self.tracker.update(frame, self.class_names)
        
        # 2. Classify + detect anomalies
        events = self.classifier.detect_anomalies(animals, self.camera_id)
        
        # 3. Check grouping
        grouping = self.classifier.detect_grouping_anomaly(
            animals, self.camera_id
        )
        if grouping:
            events.append(grouping)
        
        self.event_buffer.extend(events)
        
        # 4. Summary
        activity_counts = defaultdict(int)
        for a in animals:
            activity_counts[a.current_activity] += 1
        
        return {
            "animals": [
                {
                    "track_id": a.track_id,
                    "species": a.class_name,
                    "activity": a.current_activity,
                    "confidence": a.activity_confidence,
                }
                for a in animals
            ],
            "events": [e.to_dict() for e in events],
            "summary": {
                "total_animals": len(animals),
                "activities": dict(activity_counts),
                "alerts": len([e for e in events if e.severity == "alert"]),
            },
        }
    
    def flush_events(self) -> list[BehaviourEvent]:
        """Retorna y limpia el buffer de eventos"""
        events = self.event_buffer.copy()
        self.event_buffer.clear()
        return events
