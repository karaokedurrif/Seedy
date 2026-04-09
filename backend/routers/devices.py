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

from services.telemetry import (
    get_bridge_devices,
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
            "last_temperature": last.get("temperature"),
            "last_humidity": last.get("humidity"),
            "last_battery": last.get("battery"),
            "last_linkquality": last.get("linkquality"),
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
                "last_temperature": last.get("temperature"),
                "last_humidity": last.get("humidity"),
                "last_battery": last.get("battery"),
                "last_linkquality": last.get("linkquality"),
                "last_seen": last.get("_ts"),
            })

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
    """Estado resumido: un registro por gallinero con su sensor asignado."""
    last_values = get_last_values()
    device_map = get_device_map()

    gallineros = {}
    for fname, info in device_map.items():
        gid = info["gallinero_id"]
        gname = info["gallinero_name"]
        last = last_values.get(fname, {})
        gallineros[gid] = {
            "gallinero_id": gid,
            "gallinero_name": gname,
            "sensor": fname,
            "temperature": last.get("temperature"),
            "humidity": last.get("humidity"),
            "battery": last.get("battery"),
            "linkquality": last.get("linkquality"),
            "last_seen": last.get("_ts"),
            "online": last.get("_ts") is not None,
        }

    return {"gallineros": gallineros}


@router.get("/history")
async def device_history(
    gallinero_id: int | None = Query(None, description="Filtrar por gallinero"),
    sensor: str | None = Query(None, description="Filtrar por nombre de sensor"),
    hours: int = Query(24, ge=1, le=168, description="Horas de histórico (1-168)"),
):
    """Histórico de telemetría de un sensor o gallinero."""
    data = await query_influx_history(gallinero_id=gallinero_id, sensor=sensor, hours=hours)
    return {"data": data, "count": len(data), "hours": hours}
