"""
Seedy Backend — Telemetry Service

Escucha topics MQTT de Zigbee2MQTT y almacena en InfluxDB.
También permite consultar el último estado y el histórico de cada sensor.

Topics Zigbee2MQTT:
  zigbee2mqtt/<friendly_name> → {"temperature": 22.5, "humidity": 65, "battery": 98, ...}
  zigbee2mqtt/bridge/devices  → lista de dispositivos vinculados
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Config ──

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "neofarm")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "porcidata")

# Mapeo nombre friendly Zigbee → gallinero OvoSfera
# Gallinero unificado: gallinero_palacio (antes durrif_1 + durrif_2)
DEVICE_GALLINERO_MAP: dict[str, dict] = {
    "gallinero_durrif_1": {"gallinero_id": 2, "gallinero_name": "Palacio (zona 1)"},
    "gallinero_durrif_2": {"gallinero_id": 2, "gallinero_name": "Palacio (zona 2)"},
    "sensor_tierra_gallineros": {"gallinero_id": 2, "gallinero_name": "Palacio (suelo)"},
    "sensor_aire_gallinero_grande": {"gallinero_id": 2, "gallinero_name": "Palacio (aire grande)"},
    "sensor_aire_gallinero_pequeno": {"gallinero_id": 2, "gallinero_name": "Palacio (aire pequeño)"},
}

# Categoría de cada sensor (para el inject.js de OvoSfera)
DEVICE_CATEGORY_MAP: dict[str, str] = {
    "gallinero_durrif_1": "sensor",
    "gallinero_durrif_2": "sensor",
    "sensor_tierra_gallineros": "soil",
    "sensor_aire_gallinero_grande": "air_quality",
    "sensor_aire_gallinero_pequeno": "air_quality",
    "router_gallineros": "infrastructure",
    "enchufe_switch_poe": "infrastructure",
}

# Último valor recibido de cada sensor (cache en memoria)
_last_values: dict[str, dict[str, Any]] = {}

# Lista de dispositivos conocidos del bridge
_bridge_devices: list[dict] = []

# MQTT client reference
_mqtt_client = None


def get_device_map() -> dict[str, dict]:
    """Devuelve el mapeo actual de dispositivos → gallineros."""
    return DEVICE_GALLINERO_MAP.copy()


def get_device_category(friendly_name: str) -> str:
    """Devuelve la categoría de un sensor (sensor/soil/air_quality)."""
    return DEVICE_CATEGORY_MAP.get(friendly_name, "sensor")


def get_last_values() -> dict[str, dict]:
    """Devuelve el último valor conocido de cada sensor."""
    return {k: v.copy() for k, v in _last_values.items()}


def get_bridge_devices() -> list[dict]:
    """Devuelve la lista de dispositivos del bridge Zigbee2MQTT."""
    return _bridge_devices.copy()


def register_device(friendly_name: str, gallinero_id: int, gallinero_name: str):
    """Asigna un sensor Zigbee a un gallinero."""
    DEVICE_GALLINERO_MAP[friendly_name] = {
        "gallinero_id": gallinero_id,
        "gallinero_name": gallinero_name,
    }
    logger.info(f"[Telemetry] Sensor '{friendly_name}' asignado a {gallinero_name} (id:{gallinero_id})")


def _on_message(client, userdata, msg):
    """Callback MQTT — procesa mensajes de Zigbee2MQTT."""
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    # Bridge devices list
    if topic == "zigbee2mqtt/bridge/devices":
        _bridge_devices.clear()
        for dev in payload:
            dtype = dev.get("type", "")
            fname = dev.get("friendly_name", "")
            # Incluir EndDevice (sensores) y Routers que son sensores (air quality, plugs con sensor)
            # Excluir Coordinator y dispositivos sin friendly_name útil
            if dtype in ("EndDevice", "Router") and fname and fname != "Coordinator":
                _bridge_devices.append({
                    "ieee_address": dev.get("ieee_address", ""),
                    "friendly_name": fname,
                    "model": dev.get("definition", {}).get("model", "unknown"),
                    "vendor": dev.get("definition", {}).get("vendor", "unknown"),
                    "description": dev.get("definition", {}).get("description", ""),
                    "supported": dev.get("supported", False),
                    "interview_completed": dev.get("interview_completed", False),
                })
        logger.info(f"[Telemetry] Bridge: {len(_bridge_devices)} dispositivos detectados")
        return

    # Bridge state/log — skip
    if topic.startswith("zigbee2mqtt/bridge/"):
        return

    # Sensor data: zigbee2mqtt/<friendly_name>
    if topic.startswith("zigbee2mqtt/"):
        friendly_name = topic.replace("zigbee2mqtt/", "")
        if not isinstance(payload, dict):
            return

        # Guardar último valor en cache
        _last_values[friendly_name] = {
            **payload,
            "_ts": datetime.now(timezone.utc).isoformat(),
            "_topic": topic,
        }

        # Si tiene temperatura o humedad, escribir a InfluxDB
        if "temperature" in payload or "humidity" in payload:
            gallinero_info = DEVICE_GALLINERO_MAP.get(friendly_name, {})
            gallinero_name = gallinero_info.get("gallinero_name", "sin_asignar")
            gallinero_id = gallinero_info.get("gallinero_id", 0)

            _write_to_influx(
                friendly_name=friendly_name,
                gallinero_name=gallinero_name,
                gallinero_id=gallinero_id,
                payload=payload,
            )


def _write_to_influx(friendly_name: str, gallinero_name: str, gallinero_id: int, payload: dict):
    """Escribe un punto de telemetría a InfluxDB (line protocol)."""
    if not INFLUXDB_TOKEN:
        return

    fields = []
    for key in ("temperature", "humidity", "battery", "voltage", "pressure", "linkquality", "co2", "voc", "formaldehyd"):
        if key in payload:
            val = payload[key]
            if isinstance(val, (int, float)):
                fields.append(f"{key}={val}")

    if not fields:
        return

    # Line protocol: measurement,tags fields timestamp
    # Escapar espacios y caracteres especiales en tag values para InfluxDB line protocol
    def _escape_tag(v: str) -> str:
        return v.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

    tags = f"sensor={_escape_tag(friendly_name)},gallinero={_escape_tag(gallinero_name)},gallinero_id={gallinero_id}"
    fields_str = ",".join(fields)
    ts_ns = int(time.time() * 1e9)
    line = f"gallinero_climate,{tags} {fields_str} {ts_ns}"

    try:
        # Fire-and-forget sync HTTP (se llama desde callback MQTT sync)
        import urllib.request
        url = f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=ns"
        req = urllib.request.Request(
            url,
            data=line.encode("utf-8"),
            headers={
                "Authorization": f"Token {INFLUXDB_TOKEN}",
                "Content-Type": "text/plain",
            },
            method="POST",
        )
        # Retry con backoff (max 3 intentos)
        for attempt in range(3):
            try:
                urllib.request.urlopen(req, timeout=5)
                return
            except Exception as retry_err:
                if attempt < 2:
                    import time as _t
                    _t.sleep(0.5 * (attempt + 1))
                else:
                    raise retry_err
    except Exception as e:
        logger.warning(f"[Telemetry] Error escribiendo a InfluxDB: {e}")


async def query_influx_history(
    gallinero_id: int | None = None,
    sensor: str | None = None,
    hours: int = 24,
) -> list[dict]:
    """Consulta histórico de telemetría desde InfluxDB."""
    if not INFLUXDB_TOKEN:
        return []

    # Flux query
    filters = ['r._measurement == "gallinero_climate"']
    if gallinero_id is not None:
        filters.append(f'r.gallinero_id == "{gallinero_id}"')
    if sensor:
        filters.append(f'r.sensor == "{sensor}"')

    filter_str = " and ".join(filters)
    flux = f"""
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => {filter_str})
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 500)
"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
                headers={
                    "Authorization": f"Token {INFLUXDB_TOKEN}",
                    "Content-Type": "application/vnd.flux",
                    "Accept": "application/csv",
                },
                content=flux,
            )
            resp.raise_for_status()

            # Parse CSV response
            lines = resp.text.strip().split("\n")
            if len(lines) < 2:
                return []

            headers = lines[0].split(",")
            results = []
            for line in lines[1:]:
                if line.startswith(","):  # data rows start with empty annotation col
                    vals = line.split(",")
                    row = {}
                    for h, v in zip(headers, vals):
                        if h in ("_time", "sensor", "gallinero", "gallinero_id",
                                 "temperature", "humidity", "battery", "voltage",
                                 "pressure", "linkquality", "co2", "voc", "formaldehyd"):
                            row[h.lstrip("_")] = v
                    if row:
                        results.append(row)
            return results

    except Exception as e:
        logger.error(f"[Telemetry] Error consultando InfluxDB: {e}")
        return []


def start_mqtt_listener():
    """Inicia el listener MQTT en un thread aparte. Llamar desde lifespan."""
    global _mqtt_client
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning("[Telemetry] paho-mqtt no instalado — telemetría MQTT desactivada")
        return

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="seedy-telemetry")
    client.on_message = _on_message

    def on_connect(client, userdata, flags, rc, properties=None):
        logger.info(f"[Telemetry] Conectado a MQTT broker ({MQTT_HOST}:{MQTT_PORT})")
        client.subscribe("zigbee2mqtt/#")
        logger.info("[Telemetry] Suscrito a zigbee2mqtt/#")

    client.on_connect = on_connect

    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()  # Thread aparte
        _mqtt_client = client
        logger.info(f"[Telemetry] MQTT listener iniciado → {MQTT_HOST}:{MQTT_PORT}")
    except Exception as e:
        logger.error(f"[Telemetry] Error conectando a MQTT: {e}")


def stop_mqtt_listener():
    """Para el listener MQTT."""
    global _mqtt_client
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        _mqtt_client = None
        logger.info("[Telemetry] MQTT listener detenido")
