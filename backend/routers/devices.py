"""
Seedy Backend — Router /ovosfera/devices

Gestión de sensores Zigbee para gallineros:
- Lista de dispositivos detectados por el bridge
- Último estado de cada sensor (temp, humedad, batería)
- Asignación sensor → gallinero
- Histórico de telemetría (vía InfluxDB)
"""

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.ecowitt import fetch_realtime as ecowitt_fetch_realtime
from services.telemetry import (
    get_bridge_devices,
    get_device_category,
    get_device_map,
    get_last_values,
    query_influx_history,
    register_device,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ovosfera/devices", tags=["devices"])


class AssignDeviceRequest(BaseModel):
    friendly_name: str
    gallinero_id: int
    gallinero_name: str


@router.get("")
async def list_devices():
    """Lista todos los sensores Zigbee detectados con su estado actual."""
    bridge_devices = get_bridge_devices()
    last_values = get_last_values()
    device_map = get_device_map()

    devices = []
    for dev in bridge_devices:
        fname = dev["friendly_name"]
        last = last_values.get(fname, {})
        assignment = device_map.get(fname, {})
        devices.append({
            **dev,
            "gallinero_id": assignment.get("gallinero_id"),
            "gallinero_name": assignment.get("gallinero_name"),
            "device_category": get_device_category(fname),
            "last_temperature": last.get("temperature"),
            "last_humidity": last.get("humidity"),
            "last_battery": last.get("battery"),
            "last_linkquality": last.get("linkquality"),
            "last_co2": last.get("co2"),
            "last_voc": last.get("voc"),
            "last_formaldehyd": last.get("formaldehyd"),
            "last_seen": last.get("_ts"),
        })

    # También añadir sensores con datos pero no en bridge list (por si Z2M aún no reportó devices)
    known = {d["friendly_name"] for d in bridge_devices}
    for fname, last in last_values.items():
        if fname not in known and ("temperature" in last or "humidity" in last):
            assignment = device_map.get(fname, {})
            devices.append({
                "ieee_address": "",
                "friendly_name": fname,
                "model": "unknown",
                "vendor": "unknown",
                "description": "Sensor detectado vía MQTT",
                "supported": True,
                "interview_completed": True,
                "gallinero_id": assignment.get("gallinero_id"),
                "gallinero_name": assignment.get("gallinero_name"),
                "device_category": get_device_category(fname),
                "last_temperature": last.get("temperature"),
                "last_humidity": last.get("humidity"),
                "last_battery": last.get("battery"),
                "last_linkquality": last.get("linkquality"),
                "last_co2": last.get("co2"),
                "last_voc": last.get("voc"),
                "last_formaldehyd": last.get("formaldehyd"),
                "last_seen": last.get("_ts"),
            })

    # Añadir Ecowitt como dispositivo
    ecowitt = await ecowitt_fetch_realtime()
    if "error" not in ecowitt:
        outdoor = ecowitt.get("outdoor", {})
        devices.append({
            "ieee_address": "",
            "friendly_name": "Estación Meteo Ecowitt",
            "type": "ecowitt",
            "model": "Ecowitt GW2000A",
            "vendor": "Ecowitt",
            "description": "Estación meteorológica exterior",
            "supported": True,
            "interview_completed": True,
            "gallinero_id": None,
            "gallinero_name": "Finca Palacio",
            "device_category": "weather",
            "last_temperature": outdoor.get("temperature"),
            "last_humidity": outdoor.get("humidity"),
            "last_battery": None,
            "last_linkquality": None,
            "last_co2": None,
            "last_voc": None,
            "last_formaldehyd": None,
            "last_seen": ecowitt.get("last_seen"),
            "ecowitt": ecowitt,
        })

    # Añadir cámaras ESP32 Seedy como dispositivos
    import httpx
    for cam_name, cam_url, gall_id, gall_name in [
        ("Cám. Interior Palacio (ESP32 IR)", "http://host.docker.internal:8061", 2, "Gallinero Palacio"),
        ("Cám. Interior Pequeño (ESP32 IR)", "http://host.docker.internal:8062", 3, "Gallinero Pequeño"),
    ]:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{cam_url}/status")
                if resp.status_code == 200:
                    cam_data = resp.json()
                    devices.append({
                        "ieee_address": cam_data.get("mac", ""),
                        "friendly_name": cam_name,
                        "type": "esp32_cam",
                        "model": "DFRobot DFR1154 ESP32-S3 AI CAM",
                        "vendor": "DFRobot / Seedy",
                        "description": f"Cámara IR interior - {cam_data.get('camera', 'OV3660')}",
                        "supported": True,
                        "interview_completed": True,
                        "gallinero_id": gall_id,
                        "gallinero_name": gall_name,
                        "device_category": "camera",
                        "last_temperature": None,
                        "last_humidity": None,
                        "last_battery": None,
                        "last_linkquality": cam_data.get("rssi"),
                        "last_co2": None,
                        "last_voc": None,
                        "last_formaldehyd": None,
                        "last_seen": None,
                        "esp32_cam": {
                            "ip": cam_data.get("ip"),
                            "firmware": cam_data.get("firmware"),
                            "lux": cam_data.get("lux"),
                            "ir_on": cam_data.get("ir_on"),
                            "free_psram": cam_data.get("free_psram"),
                            "uptime_s": cam_data.get("uptime_s"),
                            "audio_available": cam_data.get("audio_available", False),
                            "audio_recording": cam_data.get("audio_recording", False),
                            "stream_url": f"{cam_url}/stream",
                            "snapshot_url": f"{cam_url}/capture",
                        },
                    })
        except Exception:
            pass

    return {"devices": devices, "count": len(devices)}


@router.post("/assign")
async def assign_device(req: AssignDeviceRequest):
    """Asigna un sensor Zigbee a un gallinero."""
    register_device(req.friendly_name, req.gallinero_id, req.gallinero_name)
    return {
        "status": "ok",
        "message": f"Sensor '{req.friendly_name}' asignado a {req.gallinero_name}",
    }


@router.get("/status")
async def devices_status():
    """Estado resumido: un registro por gallinero con sensores agregados."""
    last_values = get_last_values()
    device_map = get_device_map()

    gallineros: dict[int, dict] = {}
    for fname, info in device_map.items():
        gid = info["gallinero_id"]
        gname = info["gallinero_name"]
        last = last_values.get(fname, {})
        temp = last.get("temperature")
        hum = last.get("humidity")

        if gid not in gallineros:
            gallineros[gid] = {
                "gallinero_id": gid,
                "gallinero_name": gname.split(" (")[0] if " (" in gname else gname,
                "sensors": [],
                "temperature": None,
                "humidity": None,
                "online": False,
            }

        g = gallineros[gid]
        g["sensors"].append({
            "sensor": fname,
            "category": get_device_category(fname),
            "temperature": temp,
            "humidity": hum,
            "battery": last.get("battery"),
            "linkquality": last.get("linkquality"),
            "co2": last.get("co2"),
            "voc": last.get("voc"),
            "formaldehyd": last.get("formaldehyd"),
            "last_seen": last.get("_ts"),
            "online": last.get("_ts") is not None,
        })

        # Agregar: usar la temp/hum del sensor de tipo 'sensor' (no soil/air)
        cat = get_device_category(fname)
        if cat == "sensor" and temp is not None:
            if g["temperature"] is None:
                g["temperature"] = temp
            else:
                g["temperature"] = round((g["temperature"] + temp) / 2, 1)
        if cat == "sensor" and hum is not None:
            if g["humidity"] is None:
                g["humidity"] = hum
            else:
                g["humidity"] = round((g["humidity"] + hum) / 2, 1)
        if last.get("_ts"):
            g["online"] = True

    # Ecowitt weather
    ecowitt = await ecowitt_fetch_realtime()
    weather = ecowitt if "error" not in ecowitt else None

    return {"gallineros": gallineros, "weather": weather}


@router.get("/history")
async def device_history(
    gallinero_id: int | None = Query(None, description="Filtrar por gallinero"),
    sensor: str | None = Query(None, description="Filtrar por nombre de sensor"),
    hours: int = Query(24, ge=1, le=168, description="Horas de histórico (1-168)"),
):
    """Histórico de telemetría de un sensor o gallinero."""
    data = await query_influx_history(gallinero_id=gallinero_id, sensor=sensor, hours=hours)
    return {"data": data, "count": len(data), "hours": hours}
