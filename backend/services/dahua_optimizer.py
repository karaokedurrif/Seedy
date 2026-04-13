"""
Seedy Backend — Optimizador Dahua WizSense IPC

Configura parámetros óptimos de la cámara Dahua vía CGI para captura
de aves en movimiento: exposición rápida, WDR, sub-stream H.264.
"""

import logging
from typing import Optional

import httpx
from httpx import DigestAuth

logger = logging.getLogger(__name__)

# Config Dahua
DAHUA_IP = "10.10.10.108"
DAHUA_USER = "admin"
DAHUA_PASSWORD = "1234567a"
DAHUA_BASE = f"http://{DAHUA_IP}/cgi-bin"

# Auth digest (Dahua require digest auth)
_auth = DigestAuth(DAHUA_USER, DAHUA_PASSWORD)


async def optimize_dahua_settings() -> dict:
    """
    Aplica configuración óptima para captura de aves en movimiento.

    - Exposición manual 1/200s (congelar aves en movimiento)
    - Sub-stream: H.264, D1, 15fps, 1Mbps
    - Main: H.265, 4K, GOP=15 (1 I-frame/s)
    - WDR activo (80%) para contraluz
    - Sharpness 70, Contraste 60, Saturación 55
    """
    results = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Exposición manual para congelar movimiento de aves
        try:
            r = await client.get(
                f"{DAHUA_BASE}/configManager.cgi",
                params={
                    "action": "setConfig",
                    "VideoInExposure[0].ExposureMode": "Manual",
                    "VideoInExposure[0].ExposureSpeed": "1/200",
                    "VideoInExposure[0].GainMax": "80",
                },
                auth=_auth,
            )
            results["exposure"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            results["exposure"] = f"error:{e}"

        # 2. WDR para contraluz (gallinero con ventanas)
        try:
            r = await client.get(
                f"{DAHUA_BASE}/configManager.cgi",
                params={
                    "action": "setConfig",
                    "VideoInBacklight[0].BacklightMode": "WDR",
                    "VideoInBacklight[0].WideDynamic.Range": "80",
                },
                auth=_auth,
            )
            results["wdr"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            results["wdr"] = f"error:{e}"

        # 3. Imagen: sharpness, contraste, saturación
        try:
            r = await client.get(
                f"{DAHUA_BASE}/configManager.cgi",
                params={
                    "action": "setConfig",
                    "VideoColor[0][0].Sharpness": "70",
                    "VideoColor[0][0].Contrast": "60",
                    "VideoColor[0][0].Saturation": "55",
                },
                auth=_auth,
            )
            results["image"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            results["image"] = f"error:{e}"

        # 4. Sub-stream: H.264, D1, 15fps, 1Mbps (para tracking continuo)
        try:
            r = await client.get(
                f"{DAHUA_BASE}/configManager.cgi",
                params={
                    "action": "setConfig",
                    "Encode[0].ExtraFormat[0].Video.Compression": "H.264",
                    "Encode[0].ExtraFormat[0].Video.Resolution": "D1",
                    "Encode[0].ExtraFormat[0].Video.FPS": "15",
                    "Encode[0].ExtraFormat[0].Video.BitRate": "1024",
                    "Encode[0].ExtraFormat[0].Video.BitRateControl": "CBR",
                },
                auth=_auth,
            )
            results["sub_stream"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            results["sub_stream"] = f"error:{e}"

        # 5. Main-stream: H.265, 4K, GOP=15 (1 I-frame/s a 15fps)
        try:
            r = await client.get(
                f"{DAHUA_BASE}/configManager.cgi",
                params={
                    "action": "setConfig",
                    "Encode[0].MainFormat[0].Video.Compression": "H.265",
                    "Encode[0].MainFormat[0].Video.Resolution": "3840x2160",
                    "Encode[0].MainFormat[0].Video.GOP": "15",
                    "Encode[0].MainFormat[0].Video.FPS": "15",
                },
                auth=_auth,
            )
            results["main_stream"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            results["main_stream"] = f"error:{e}"

    all_ok = all(v == "ok" for v in results.values())
    logger.info(f"🎥 Dahua optimizer: {'✅ ALL OK' if all_ok else '⚠️ PARTIAL'} — {results}")
    return {"success": all_ok, "results": results}


async def get_dahua_config() -> Optional[dict]:
    """Lee la configuración actual de la Dahua."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            configs = {}
            for name in ("Encode", "VideoInExposure", "VideoInBacklight", "VideoColor"):
                r = await client.get(
                    f"{DAHUA_BASE}/configManager.cgi",
                    params={"action": "getConfig", "name": name},
                    auth=_auth,
                )
                if r.status_code == 200:
                    configs[name] = r.text[:2000]  # Truncar para legibilidad
            return configs
    except Exception as e:
        logger.error(f"Error leyendo config Dahua: {e}")
        return None


async def take_snapshot() -> Optional[bytes]:
    """Captura snapshot 4K vía CGI (más rápido que RTSP)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"http://{DAHUA_IP}/cgi-bin/snapshot.cgi?channel=1",
                auth=_auth,
            )
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
            return None
    except Exception as e:
        logger.error(f"Error capturando snapshot Dahua: {e}")
        return None
