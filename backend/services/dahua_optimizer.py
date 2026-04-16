"""Seedy Backend — Optimización de cámaras Dahua via CGI.

Configura exposición, sub-stream, compresión e imagen para captura
óptima de aves en movimiento.
"""

import logging
from typing import Any

import httpx
from httpx import DigestAuth

logger = logging.getLogger(__name__)


async def optimize_dahua_settings(
    ip: str,
    user: str = "admin",
    password: str = "1234567a",
) -> dict[str, Any]:
    """Configura la Dahua WizSense para captura óptima de aves.

    Returns:
        dict con resultado por parámetro configurado.
    """
    auth = DigestAuth(user, password)
    base = f"http://{ip}/cgi-bin/configManager.cgi"

    settings: list[tuple[str, str]] = [
        # ── Exposición: 1/200s para congelar movimiento ──
        ("Encode[0].MainFormat[0].Video.ExposureMode", "Manual"),
        ("Encode[0].MainFormat[0].Video.ExposureValue", "200"),

        # ── Sub-stream: H.264, D1, 15fps, 1Mbps (tracking) ──
        ("Encode[0].ExtraFormat[0].Video.Compression", "H.264"),
        ("Encode[0].ExtraFormat[0].Video.FPS", "15"),
        ("Encode[0].ExtraFormat[0].Video.BitRate", "1024"),
        ("Encode[0].ExtraFormat[0].Video.Resolution", "D1"),

        # ── Main-stream: H.265, 4K, GOP=15 (1 I-frame/s) ──
        ("Encode[0].MainFormat[0].Video.Compression", "H.265"),
        ("Encode[0].MainFormat[0].Video.FPS", "15"),
        ("Encode[0].MainFormat[0].Video.GOP", "15"),
        ("Encode[0].MainFormat[0].Video.BitRate", "8192"),

        # ── Mejora de imagen para plumaje ──
        ("VideoColor[0][0].Brightness", "55"),
        ("VideoColor[0][0].Contrast", "60"),
        ("VideoColor[0][0].Saturation", "55"),
        ("VideoColor[0][0].Sharpness", "70"),
        ("VideoColor[0][0].Gamma", "60"),

        # ── WDR para contraluz (aves contra cielo) ──
        ("VideoInOptions[0].BacklightMode", "2"),
        ("VideoInOptions[0].DynamicRange", "80"),

        # ── Anti-flicker off (exterior) ──
        ("VideoInOptions[0].AntiFlicker", "0"),

        # ── Detección de movimiento Dahua (complementaria a YOLO) ──
        ("MotionDetect[0].Enable", "true"),
        ("MotionDetect[0].Sensitivity", "4"),
    ]

    results: dict[str, str] = {}
    async with httpx.AsyncClient(auth=auth, timeout=10) as client:
        for param, value in settings:
            url = f"{base}?action=setConfig&{param}={value}"
            try:
                resp = await client.get(url)
                ok = resp.status_code == 200 and "OK" in resp.text
                results[param] = "ok" if ok else f"fail:{resp.status_code}"
                if not ok:
                    logger.warning(f"Dahua config failed: {param}={value} → {resp.text}")
            except Exception as e:
                results[param] = f"error:{e}"
                logger.error(f"Dahua config error: {param} → {e}")

    ok_count = sum(1 for v in results.values() if v == "ok")
    logger.info(f"Dahua {ip} optimizada: {ok_count}/{len(settings)} parámetros configurados")
    return {"ip": ip, "configured": ok_count, "total": len(settings), "details": results}
