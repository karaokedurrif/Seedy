"""
Seedy Backend — Ecowitt Weather Station Service

Consulta datos en tiempo real de la estación Ecowitt GW2000A
vía API cloud (api.ecowitt.net).

MAC: 88:57:21:17:AC:A7
"""

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ECOWITT_API_URL = "https://api.ecowitt.net/api/v3/device/real_time"
ECOWITT_APPLICATION_KEY = os.environ.get("ECOWITT_APPLICATION_KEY", "")
ECOWITT_API_KEY = os.environ.get("ECOWITT_API_KEY", "")
ECOWITT_MAC = os.environ.get("ECOWITT_MAC", "")

# Cache: evitar bombardear la API (max 1 req/60s)
_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60  # segundos


def _val(obj: dict | None, key: str = "value") -> float | str | None:
    """Extrae el valor numérico de un campo Ecowitt {time, unit, value}."""
    if not obj or not isinstance(obj, dict):
        return None
    raw = obj.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return raw


async def fetch_realtime() -> dict[str, Any]:
    """Obtiene datos en tiempo real de la Ecowitt. Cachea 60s."""
    global _cache, _cache_ts

    if not ECOWITT_APPLICATION_KEY or not ECOWITT_API_KEY or not ECOWITT_MAC:
        return {"error": "Ecowitt API keys no configuradas en .env"}

    now = time.time()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    params = {
        "application_key": ECOWITT_APPLICATION_KEY,
        "api_key": ECOWITT_API_KEY,
        "mac": ECOWITT_MAC,
        "call_back": "outdoor,indoor,wind,pressure,rainfall,rainfall_piezo,solar_and_uvi",
        "temp_unitid": "1",       # Celsius
        "pressure_unitid": "3",   # hPa
        "wind_speed_unitid": "7", # km/h
        "rainfall_unitid": "12",  # mm
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(ECOWITT_API_URL, params=params)
            resp.raise_for_status()
            body = resp.json()

        if body.get("code") != 0:
            msg = body.get("msg", "unknown error")
            logger.warning(f"[Ecowitt] API error: {msg}")
            return {"error": f"Ecowitt API: {msg}"}

        data = body.get("data", {})

        outdoor = data.get("outdoor", {})
        indoor = data.get("indoor", {})
        wind = data.get("wind", {})
        pressure_data = data.get("pressure", {})
        rain = data.get("rainfall_piezo") or data.get("rainfall", {})
        solar = data.get("solar_and_uvi", {})

        result: dict[str, Any] = {
            "outdoor": {
                "temperature": _val(outdoor.get("temperature")),
                "feels_like": _val(outdoor.get("feels_like")),
                "dew_point": _val(outdoor.get("dew_point")),
                "humidity": _val(outdoor.get("humidity")),
            },
            "indoor": {
                "temperature": _val(indoor.get("temperature")),
                "humidity": _val(indoor.get("humidity")),
            },
            "wind": {
                "speed": _val(wind.get("wind_speed")),
                "gust": _val(wind.get("wind_gust")),
                "direction": _val(wind.get("wind_direction")),
            },
            "pressure": {
                "relative": _val(pressure_data.get("relative")),
                "absolute": _val(pressure_data.get("absolute")),
            },
            "rain": {
                "rate": _val(rain.get("rain_rate")),
                "daily": _val(rain.get("daily")),
                "event": _val(rain.get("event")),
            },
            "solar": {
                "radiation": _val(solar.get("solar")),
                "uvi": _val(solar.get("uvi")),
            },
            "last_seen": outdoor.get("temperature", {}).get("time"),
        }

        _cache = result
        _cache_ts = now
        logger.debug("[Ecowitt] Datos actualizados correctamente")
        return result

    except httpx.TimeoutException:
        logger.warning("[Ecowitt] Timeout consultando API cloud")
        if _cache:
            return _cache
        return {"error": "Ecowitt API timeout"}
    except Exception as e:
        logger.warning(f"[Ecowitt] Error: {e}")
        if _cache:
            return _cache
        return {"error": str(e)}
