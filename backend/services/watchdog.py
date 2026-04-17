"""Seedy Backend — Watchdog: monitorización periódica de servicios (cada 2h, pausa nocturna).

Comprueba que todos los servicios del stack Seedy estén operativos.
Si detecta caídas, loguea alertas y envía email con resumen de incidencias.
Pausa entre 00:00 y 07:00 (las cámaras pueden estar apagadas).
"""

import asyncio
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger(__name__)

CHECK_INTERVAL = int(os.environ.get("WATCHDOG_INTERVAL", 2 * 3600))  # 2h
NIGHT_START = 0   # 00:00
NIGHT_END = 7     # 07:00

# Email config (reutiliza las mismas vars que reporting_agent)
REPORT_EMAIL = os.environ.get("REPORT_EMAIL", "durrif@gmail.com")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")


# ── Checks individuales ─────────────────────────────────

async def _check_ollama() -> tuple[bool, str]:
    """Ollama LLM server."""
    url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{url}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                return True, f"{len(models)} modelos"
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def _check_qdrant() -> tuple[bool, str]:
    """Qdrant vector store."""
    host = os.environ.get("QDRANT_HOST", "qdrant")
    port = int(os.environ.get("QDRANT_PORT", 6333))
    try:
        from qdrant_client import QdrantClient
        qc = QdrantClient(host=host, port=port, timeout=5)
        cols = qc.get_collections().collections
        qc.close()
        return True, f"{len(cols)} colecciones"
    except Exception as e:
        return False, str(e)


async def _check_together() -> tuple[bool, str]:
    """Together.ai API (LLM externo)."""
    api_key = os.environ.get("TOGETHER_API_KEY", "")
    base = os.environ.get("TOGETHER_BASE_URL", "https://api.together.xyz/v1")
    if not api_key:
        return False, "TOGETHER_API_KEY no configurada"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{base}/models", headers={"Authorization": f"Bearer {api_key}"})
            return r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def _check_go2rtc() -> tuple[bool, str]:
    """go2rtc RTSP proxy — verifica que responde y streams activos."""
    url = os.environ.get("GO2RTC_URL", "http://host.docker.internal:1984")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{url}/api/streams")
            if r.status_code == 200:
                streams = r.json()
                return True, f"{len(streams)} streams"
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def _check_cameras() -> tuple[bool, str]:
    """Captura un frame de cada cámara vía go2rtc."""
    url = os.environ.get("GO2RTC_URL", "http://host.docker.internal:1984")
    cams = ["gallinero_durrif_1_sub", "gallinero_durrif_2_sub", "sauna_durrif_1_sub"]
    ok = []
    fail = []
    async with httpx.AsyncClient(timeout=8.0) as c:
        for cam in cams:
            try:
                r = await c.get(f"{url}/api/frame.jpeg?src={cam}")
                if r.status_code == 200 and len(r.content) > 1000:
                    ok.append(cam)
                else:
                    fail.append(f"{cam}(HTTP {r.status_code})")
            except Exception as e:
                fail.append(f"{cam}({e})")
    if fail:
        return False, f"OK: {len(ok)}, FAIL: {', '.join(fail)}"
    return True, f"{len(ok)}/3 cámaras"


async def _check_influxdb() -> tuple[bool, str]:
    """InfluxDB series temporales."""
    url = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{url}/health")
            if r.status_code == 200:
                return True, r.json().get("message", "ok")
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def _check_mqtt() -> tuple[bool, str]:
    """MQTT broker (Mosquitto) — verifica puerto 1883."""
    host = os.environ.get("MQTT_BROKER", "mosquitto")
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 1883), timeout=3.0
        )
        writer.close()
        await writer.wait_closed()
        return True, "puerto 1883 abierto"
    except Exception as e:
        return False, str(e)


async def _check_searxng() -> tuple[bool, str]:
    """SearXNG meta-buscador."""
    url = os.environ.get("SEARXNG_URL", "http://searxng:8080")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url)
            return r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def _check_smtp() -> tuple[bool, str]:
    """SMTP (Gmail) — verifica conexión TLS y login."""
    if not SMTP_USER or not SMTP_PASS:
        return False, "SMTP_USER/SMTP_PASS no configurados"
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _smtp_test)
        return result
    except Exception as e:
        return False, str(e)


def _smtp_test() -> tuple[bool, str]:
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            return True, f"{SMTP_HOST}:{SMTP_PORT} login OK"
    except Exception as e:
        return False, str(e)


async def _check_bird_registry() -> tuple[bool, str]:
    """Registro de aves — 25 aves en gallinero_palacio."""
    try:
        from routers.birds import _registry
        total = len(_registry)
        gallineros = {}
        for b in _registry:
            g = b.get("gallinero", "?")
            gallineros[g] = gallineros.get(g, 0) + 1
        if total == 0:
            return False, "Registro vacío"
        return True, f"{total} aves, gallineros: {gallineros}"
    except Exception as e:
        return False, str(e)


# ── Ejecución del watchdog ──────────────────────────────

# Servicios que NO se comprueban de noche (cámaras apagadas)
_NIGHT_SKIP = {"cameras", "go2rtc"}

ALL_CHECKS = {
    "ollama": _check_ollama,
    "qdrant": _check_qdrant,
    "together_ai": _check_together,
    "go2rtc": _check_go2rtc,
    "cameras": _check_cameras,
    "influxdb": _check_influxdb,
    "mqtt": _check_mqtt,
    "searxng": _check_searxng,
    "smtp": _check_smtp,
    "bird_registry": _check_bird_registry,
}


async def run_checks(skip_cameras: bool = False) -> dict:
    """Ejecuta todos los checks y devuelve resultados."""
    results = {}
    for name, fn in ALL_CHECKS.items():
        if skip_cameras and name in _NIGHT_SKIP:
            results[name] = {"ok": True, "detail": "skip (noche)", "skipped": True}
            continue
        try:
            ok, detail = await fn()
            results[name] = {"ok": ok, "detail": detail}
            level = "INFO" if ok else "WARNING"
            getattr(logger, level.lower())(f"[Watchdog] {name}: {'✅' if ok else '❌'} {detail}")
        except Exception as e:
            results[name] = {"ok": False, "detail": f"error: {e}"}
            logger.error(f"[Watchdog] {name}: ❌ excepción: {e}")
    return results


def _send_alert_email(results: dict, timestamp: str):
    """Envía email de alerta si hay servicios caídos."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("[Watchdog] No se puede enviar alerta — SMTP no configurado")
        return

    failed = {k: v for k, v in results.items() if not v["ok"] and not v.get("skipped")}
    if not failed:
        return  # Todo OK, no enviar

    subject = f"🔴 Seedy Watchdog — {len(failed)} servicio(s) caído(s) [{timestamp}]"

    rows = ""
    for name, info in results.items():
        if info.get("skipped"):
            icon = "⏸️"
            status = "Pausado (noche)"
        elif info["ok"]:
            icon = "✅"
            status = info["detail"]
        else:
            icon = "❌"
            status = info["detail"]
        rows += f"<tr><td>{icon}</td><td><b>{name}</b></td><td>{status}</td></tr>\n"

    html = f"""
    <html><body style="font-family: sans-serif;">
    <h2>🔴 Alerta Seedy Watchdog — {timestamp}</h2>
    <p>{len(failed)} servicio(s) con problemas:</p>
    <ul>{''.join(f'<li><b>{k}</b>: {v["detail"]}</li>' for k, v in failed.items())}</ul>
    <h3>Estado completo:</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
    <tr style="background: #f0f0f0;"><th></th><th>Servicio</th><th>Detalle</th></tr>
    {rows}
    </table>
    <p style="color: #888; margin-top: 20px;">Seedy Watchdog · Gallinero Palacio · {timestamp}</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = REPORT_EMAIL
    msg.attach(MIMEText(f"{len(failed)} servicios caídos: {', '.join(failed.keys())}", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [REPORT_EMAIL], msg.as_string())
        logger.info(f"[Watchdog] 📧 Alerta enviada a {REPORT_EMAIL}: {', '.join(failed.keys())}")
    except Exception as e:
        logger.error(f"[Watchdog] Error enviando alerta: {e}")


async def watchdog_loop():
    """Loop principal: cada 2h comprueba servicios, pausa de noche [00-07h]."""
    # Esperar 3 min tras arranque para que todo suba
    await asyncio.sleep(180)
    logger.info(f"[Watchdog] Iniciado — check cada {CHECK_INTERVAL // 3600}h, pausa nocturna {NIGHT_START}:00-{NIGHT_END}:00")

    while True:
        now = datetime.now(timezone.utc)
        local_hour = (now.hour + 2) % 24  # UTC+2 para España (aprox.)

        is_night = NIGHT_START <= local_hour < NIGHT_END
        if is_night:
            logger.info("[Watchdog] 🌙 Horario nocturno — salta chequeo de cámaras")

        timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
        results = await run_checks(skip_cameras=is_night)

        # Contar fallos
        failed = [k for k, v in results.items() if not v["ok"] and not v.get("skipped")]
        if failed:
            logger.warning(f"[Watchdog] 🔴 {len(failed)} servicio(s) caído(s): {', '.join(failed)}")
            _send_alert_email(results, timestamp)
        else:
            logger.info(f"[Watchdog] ✅ Todos los servicios operativos ({len(results)} checks)")

        await asyncio.sleep(CHECK_INTERVAL)
