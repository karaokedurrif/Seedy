"""
Seedy Backend — Dron Parrot Bebop 2 espantapájaros autónomo

Cuando la Dahua detecta gorriones persistentes sobre el comedero:
1. Seedy confirma (≥3 gorriones, persistente >10s / 3 ciclos YOLO)
2. Envía comando al Bebop 2 vía WiFi (Olympe SDK)
3. El Bebop despega, vuela ~20m al comedero, hover 5s, regresa, aterriza

Conexión WiFi: el Bebop 2 crea red propia "BebopDrone-XXXXX".
Requiere interfaz WiFi secundaria (USB dongle) en el servidor.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Plan de vuelo ──
FLIGHT_PLAN = {
    "target_forward_m": 20.0,   # metros hacia el comedero (norte)
    "target_altitude_m": 2.5,   # metros de altura
    "hover_time_s": 5,          # segundos hovering sobre comedero
}

BEBOP_IP = "192.168.42.1"  # IP default del Bebop 2 en su red WiFi

# Bridge HTTP en el host (Olympe corre fuera de Docker)
DRONE_BRIDGE_URL = os.environ.get("DRONE_BRIDGE_URL", "http://host.docker.internal:9090")

# ── Reglas de seguridad ──
SAFETY = {
    "max_flights_per_hour": 5,
    "max_flights_per_day": 20,
    "no_fly_hours": (22, 7),         # no volar de 22:00 a 07:00
    "min_battery_pct": 30,
    "max_wind_speed_kmh": 25,
    "max_altitude_m": 4.0,
    "max_distance_m": 30.0,
    "emergency_landing_on_disconnect": True,
    "cooldown_s": 120,               # mínimo 2 minutos entre vuelos
}

# ── Trigger desde YOLO ──
SPARROW_TRIGGER = {
    "min_count": 3,             # mínimo 3 gorriones simultáneos
    "min_consecutive": 3,       # 3 ciclos consecutivos (≈12s a 4s/ciclo)
    "max_bbox_size": 150,       # bbox < 150px = gorrión (no gallina)
    "only_cameras": {"dahua"},  # solo cámaras que apuntan al comedero
}


@dataclass
class FlightRecord:
    timestamp: float
    status: str  # "completed" | "error" | "skipped"
    reason: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
            "status": self.status,
            "reason": self.reason,
            "duration_s": round(self.duration_s, 1),
        }


class SparrowDeterrent:
    def __init__(self):
        self._connected = False
        self.is_flying = False
        self.last_flight = 0.0
        self.flight_log: deque[FlightRecord] = deque(maxlen=200)
        self._lock = threading.Lock()
        # Contadores para rate limiting
        self._flights_this_hour: deque[float] = deque(maxlen=SAFETY["max_flights_per_hour"])
        self._flights_today: deque[float] = deque(maxlen=SAFETY["max_flights_per_day"])
        # Sparrow consecutive counter per camera
        self._sparrow_counter: dict[str, int] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> dict:
        """Conectar al Bebop 2 via bridge HTTP en el host."""
        try:
            import httpx
            resp = httpx.post(f"{DRONE_BRIDGE_URL}/connect", timeout=10.0)
            data = resp.json()
            self._connected = data.get("connected", False)
            if self._connected:
                logger.info(f"🚁 Dron Bebop 2 conectado via bridge ({DRONE_BRIDGE_URL})")
            return {"status": "connected" if self._connected else "failed", **data}
        except Exception as e:
            logger.warning(f"🚁 Bridge no disponible: {e} — modo simulación")
            self._connected = False
            return {"status": "simulation", "reason": str(e)}

    def disconnect(self):
        self._connected = False

    def can_fly(self) -> tuple[bool, str]:
        """Verifica si puede volar (cooldown, horario, rate limits)."""
        if self.is_flying:
            return False, "already_flying"

        now = time.time()

        # Cooldown
        elapsed = now - self.last_flight
        if elapsed < SAFETY["cooldown_s"]:
            remaining = int(SAFETY["cooldown_s"] - elapsed)
            return False, f"cooldown_{remaining}s"

        # Horario
        hour = datetime.now().hour
        no_fly_start, no_fly_end = SAFETY["no_fly_hours"]
        if no_fly_start <= hour or hour < no_fly_end:
            return False, f"no_fly_hours_{no_fly_start}-{no_fly_end}"

        # Rate: vuelos/hora
        self._flights_this_hour = deque(
            [t for t in self._flights_this_hour if now - t < 3600],
            maxlen=SAFETY["max_flights_per_hour"],
        )
        if len(self._flights_this_hour) >= SAFETY["max_flights_per_hour"]:
            return False, "max_flights_per_hour"

        # Rate: vuelos/día
        self._flights_today = deque(
            [t for t in self._flights_today if now - t < 86400],
            maxlen=SAFETY["max_flights_per_day"],
        )
        if len(self._flights_today) >= SAFETY["max_flights_per_day"]:
            return False, "max_flights_per_day"

        return True, "ready"

    def execute_deterrent_flight(self) -> dict:
        """Ejecuta vuelo de espantamiento (bloqueante, ejecutar en thread)."""
        with self._lock:
            can, reason = self.can_fly()
            if not can:
                rec = FlightRecord(time.time(), "skipped", reason)
                self.flight_log.append(rec)
                return rec.to_dict()

            self.is_flying = True

        t0 = time.time()
        try:
            if self._connected:
                result = self._execute_real_flight()
            else:
                result = self._execute_simulated_flight()

            duration = time.time() - t0
            self.last_flight = time.time()
            self._flights_this_hour.append(time.time())
            self._flights_today.append(time.time())

            rec = FlightRecord(time.time(), "completed", duration_s=duration)
            self.flight_log.append(rec)
            _publish_drone_event("flight_completed", rec.to_dict())
            return rec.to_dict()

        except Exception as e:
            duration = time.time() - t0
            logger.error(f"🚁 Error en vuelo: {e}")
            rec = FlightRecord(time.time(), "error", str(e), duration)
            self.flight_log.append(rec)
            _publish_drone_event("flight_error", rec.to_dict())
            return rec.to_dict()
        finally:
            self.is_flying = False

    def _execute_real_flight(self) -> str:
        """Vuelo real delegado al bridge HTTP en el host (Olympe)."""
        import httpx

        resp = httpx.post(f"{DRONE_BRIDGE_URL}/fly", timeout=60.0)
        data = resp.json()
        if data.get("status") == "completed":
            logger.info(f"🚁 Vuelo real completado ({data.get('duration_s', '?')}s)")
            return "real_flight"
        else:
            raise RuntimeError(f"Bridge flight failed: {data}")

    def _execute_simulated_flight(self) -> str:
        """Vuelo simulado (sin Olympe / sin dron conectado)."""
        fwd = FLIGHT_PLAN["target_forward_m"]
        alt = FLIGHT_PLAN["target_altitude_m"]
        hover = FLIGHT_PLAN["hover_time_s"]

        logger.info(f"🚁 [SIM] Despegue → +{alt}m → +{fwd}m → hover {hover}s → vuelta → aterrizaje")
        # Simular tiempos reducidos
        time.sleep(2)
        return "simulated_flight"

    def check_sparrow_trigger(self, detections: list[dict], camera_id: str) -> bool:
        """Evalúa si las detecciones activan un vuelo anti-gorriones.

        Llamar desde el ciclo YOLO principal tras cada frame.
        """
        if camera_id not in SPARROW_TRIGGER["only_cameras"]:
            return False

        # Contar aves pequeñas (gorriones, no gallinas)
        small_birds = []
        for d in detections:
            cls = d.get("class_name", "")
            if cls not in ("gorrion", "bird"):
                continue
            bbox = d.get("bbox", [0, 0, 0, 0])
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if max(w, h) < SPARROW_TRIGGER["max_bbox_size"]:
                small_birds.append(d)

        if len(small_birds) >= SPARROW_TRIGGER["min_count"]:
            self._sparrow_counter[camera_id] = self._sparrow_counter.get(camera_id, 0) + 1
            consec = self._sparrow_counter[camera_id]

            if consec >= SPARROW_TRIGGER["min_consecutive"]:
                logger.warning(
                    f"🐦 Gorriones persistentes: {len(small_birds)} en {camera_id} "
                    f"({consec} ciclos). Desplegando dron."
                )
                self._sparrow_counter[camera_id] = 0
                self._trigger_flight_async()
                return True
        else:
            self._sparrow_counter[camera_id] = 0

        return False

    def _trigger_flight_async(self):
        """Lanza vuelo en thread separado para no bloquear el ciclo YOLO."""
        can, reason = self.can_fly()
        if not can:
            logger.info(f"🚁 Dron no disponible: {reason}")
            _publish_drone_event("flight_skipped", {"reason": reason})
            return
        thread = threading.Thread(
            target=self.execute_deterrent_flight,
            name="drone-deterrent",
            daemon=True,
        )
        thread.start()

    def get_status(self) -> dict:
        can, reason = self.can_fly()
        # Cooldown remaining
        cooldown_remaining = 0
        if self.last_flight > 0:
            elapsed = time.time() - self.last_flight
            if elapsed < SAFETY["cooldown_s"]:
                cooldown_remaining = int(SAFETY["cooldown_s"] - elapsed)
        return {
            "connected": self._connected,
            "is_flying": self.is_flying,
            "can_fly": can,
            "reason": reason,
            "battery_pct": None,  # TODO: read from bridge when available
            "cooldown_remaining": cooldown_remaining,
            "last_flight": self.last_flight,
            "last_flight_dt": (
                datetime.fromtimestamp(self.last_flight).isoformat()
                if self.last_flight > 0 else None
            ),
            "flights_last_hour": len(self._flights_this_hour),
            "flights_today": len(self._flights_today),
            "safety": SAFETY,
            "flight_plan": FLIGHT_PLAN,
            "trigger_config": SPARROW_TRIGGER,
        }

    def get_flight_log(self, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in list(self.flight_log)[-limit:]]


def _publish_drone_event(event_type: str, data: dict):
    """Publica evento del dron a MQTT (fire & forget)."""
    try:
        import paho.mqtt.publish as publish
        payload = {"event": event_type, **data}
        publish.single(
            f"seedy/dron/{event_type}",
            payload=json.dumps(payload, default=str),
            hostname="mosquitto",
            port=1883,
            qos=1,
        )
    except Exception as e:
        logger.debug(f"MQTT drone event publish failed: {e}")


# ── Singleton ──
_deterrent = SparrowDeterrent()


def get_deterrent() -> SparrowDeterrent:
    return _deterrent
