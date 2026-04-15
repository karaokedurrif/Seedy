"""
Seedy Backend — Sistema de alertas de plagas

Detecta la presencia de gorriones, palomas, ratas u otros
depredadores en los gallineros y genera alertas vía MQTT.

Incluye:
  - Debouncing: no repetir alerta del mismo tipo en X segundos
  - Escalado: alerta info → warning → alert según persistencia
  - Historial: registro de todos los eventos para análisis
  - Acciones: publica a MQTT para que Node-RED active deterrentes
"""

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Configuración ──
DEBOUNCE_SECONDS = 60       # No repetir misma alerta en este intervalo
ESCALATION_FRAMES = 3       # Frames consecutivos para escalar severidad
HISTORY_MAX = 500           # Máximo de eventos en historial

# Mapeo de clases de plagas a prioridad
PEST_PRIORITY = {
    "rata": "alert",          # Máxima prioridad
    "depredador": "alert",    # Máxima (gato, perro, rapaz)
    "gorrion": "warning",     # Media — roba pienso
    "paloma": "warning",      # Media — roba pienso + transmite enfermedades
}

# Acciones sugeridas por tipo de plaga
PEST_ACTIONS = {
    "gorrion": "deterrent_sound",
    "paloma": "deterrent_sound",
    "rata": "deterrent_light_sound",
    "depredador": "alarm_full",
}

MQTT_BROKER = "mosquitto"
MQTT_PORT = 1883


@dataclass
class PestEvent:
    """Un evento de detección de plaga."""
    timestamp: float
    gallinero: str
    pest_type: str
    count: int
    severity: str
    confidence: float
    bbox_norm: list = field(default_factory=list)
    action_taken: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "gallinero": self.gallinero,
            "pest_type": self.pest_type,
            "count": self.count,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "action_taken": self.action_taken,
        }


class PestAlertManager:
    """Gestor de alertas de plagas por gallinero."""

    def __init__(self):
        # gallinero → pest_type → último timestamp de alerta
        self._last_alert: dict[str, dict[str, float]] = defaultdict(dict)
        # gallinero → pest_type → frames consecutivos
        self._consecutive: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Historial completo
        self._history: deque[PestEvent] = deque(maxlen=HISTORY_MAX)

    def process_detections(self, gallinero_id: str, detection_result: dict) -> list[dict]:
        """
        Procesa el resultado de detect() del yolo_detector.

        Args:
            gallinero_id: ID del gallinero
            detection_result: dict retornado por yolo_detector.detect()

        Returns:
            Lista de alertas generadas (pueden ser 0 si debounced)
        """
        pests = detection_result.get("pests", [])
        pest_count = detection_result.get("pest_count", 0)

        if pest_count == 0:
            # Reset contadores consecutivos
            for pt in list(self._consecutive.get(gallinero_id, {}).keys()):
                self._consecutive[gallinero_id][pt] = 0
            return []

        now = time.time()
        alerts = []

        # Agrupar por tipo de plaga
        pest_groups: dict[str, list] = defaultdict(list)
        for det in pests:
            ptype = det.get("class_name", "unknown")
            pest_groups[ptype].append(det)

        for pest_type, detections in pest_groups.items():
            count = len(detections)
            avg_conf = sum(d.get("confidence", 0) for d in detections) / count
            self._consecutive[gallinero_id][pest_type] += 1
            consec = self._consecutive[gallinero_id][pest_type]

            # Severidad base
            base_severity = PEST_PRIORITY.get(pest_type, "info")

            # Escalar severidad si persiste
            if consec >= ESCALATION_FRAMES:
                if base_severity == "info":
                    severity = "warning"
                elif base_severity == "warning":
                    severity = "alert"
                else:
                    severity = "alert"
            else:
                severity = base_severity

            # Debouncing
            last = self._last_alert.get(gallinero_id, {}).get(pest_type, 0)
            if now - last < DEBOUNCE_SECONDS:
                continue

            # Crear evento
            action = PEST_ACTIONS.get(pest_type, "notify")
            event = PestEvent(
                timestamp=now,
                gallinero=gallinero_id,
                pest_type=pest_type,
                count=count,
                severity=severity,
                confidence=avg_conf,
                bbox_norm=[d.get("bbox_norm", []) for d in detections],
                action_taken=action,
            )
            self._history.append(event)
            self._last_alert[gallinero_id][pest_type] = now

            alert_dict = {
                **event.to_dict(),
                "consecutive_frames": consec,
                "suggested_action": action,
            }
            alerts.append(alert_dict)

            # Publicar a MQTT
            _publish_pest_alert(alert_dict)

            logger.warning(
                f"PEST ALERT [{gallinero_id}]: {count}x {pest_type} "
                f"(severity={severity}, consec={consec})"
            )

        return alerts

    def get_history(self, gallinero_id: str = None, limit: int = 50) -> list[dict]:
        """Historial de eventos, opcionalmente filtrado por gallinero."""
        events = list(self._history)
        if gallinero_id:
            events = [e for e in events if e.gallinero == gallinero_id]
        return [e.to_dict() for e in events[-limit:]]

    def get_stats(self) -> dict:
        """Estadísticas globales de plagas."""
        by_type = defaultdict(int)
        by_gallinero = defaultdict(int)
        for e in self._history:
            by_type[e.pest_type] += 1
            by_gallinero[e.gallinero] += 1

        return {
            "total_events": len(self._history),
            "by_pest_type": dict(by_type),
            "by_gallinero": dict(by_gallinero),
            "active_consecutives": {
                gid: {pt: cnt for pt, cnt in pests.items() if cnt > 0}
                for gid, pests in self._consecutive.items()
            },
        }


def _publish_pest_alert(alert: dict):
    """Publica alerta de plaga a MQTT (fire & forget)."""
    try:
        import paho.mqtt.publish as publish
        topic = f"seedy/vision/alerts/pest/{alert.get('gallinero', 'unknown')}"
        publish.single(
            topic,
            payload=json.dumps(alert, default=str),
            hostname=MQTT_BROKER,
            port=MQTT_PORT,
            qos=1,  # At least once para alertas
        )
        logger.debug(f"MQTT pest alert published to {topic}")
    except Exception as e:
        logger.debug(f"MQTT pest alert publish failed: {e}")


# ── Singleton ──
_manager = PestAlertManager()


def get_pest_manager() -> PestAlertManager:
    return _manager
