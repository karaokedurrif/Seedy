"""
Seedy Backend — Router API del dron Bebop 2

Endpoints:
  GET  /api/dron/status              Estado del dron
  POST /api/dron/connect             Conectar al Bebop 2
  POST /api/dron/disconnect          Desconectar
  POST /api/dron/sparrow-deterrent   Vuelo manual anti-gorriones
  GET  /api/dron/flight-log          Historial de vuelos
"""

import logging
from fastapi import APIRouter

from services.sparrow_deterrent import get_deterrent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dron", tags=["dron"])


@router.get("/status")
async def dron_status():
    """Estado actual del dron Bebop 2."""
    return get_deterrent().get_status()


@router.post("/connect")
async def dron_connect():
    """Conectar al Bebop 2 via WiFi."""
    return get_deterrent().connect()


@router.post("/disconnect")
async def dron_disconnect():
    """Desconectar del Bebop 2."""
    get_deterrent().disconnect()
    return {"status": "disconnected"}


@router.post("/sparrow-deterrent")
async def manual_sparrow_deterrent():
    """Lanzar vuelo de espantamiento manual."""
    det = get_deterrent()
    can, reason = det.can_fly()
    if not can:
        return {"status": "skipped", "reason": reason}

    result = det.execute_deterrent_flight()
    return result


@router.get("/flight-log")
async def flight_log(limit: int = 50):
    """Historial de vuelos del dron."""
    return get_deterrent().get_flight_log(limit)
