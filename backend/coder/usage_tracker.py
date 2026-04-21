"""Seedy Coder — Telemetría de uso: escribe measurements a InfluxDB."""

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "neofarm")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "porcidata")


def record(
    *,
    provider: str,
    model: str,
    task_type: str,
    tier: str,
    project: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_first_token_ms: int,
    latency_total_ms: int,
    request_id: str,
    status: str = "ok",
    critic: str = "pass",
) -> None:
    """
    Escribe un punto de telemetría a InfluxDB usando line protocol.
    Fire-and-forget (no bloquea el stream).
    """
    if not INFLUXDB_TOKEN:
        return

    def _escape_tag(v: str) -> str:
        return v.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

    tags = ",".join([
        f"provider={_escape_tag(provider)}",
        f"model={_escape_tag(model.replace('/', '_'))}",
        f"task_type={_escape_tag(task_type)}",
        f"tier={_escape_tag(tier)}",
        f"project={_escape_tag(project or 'default')}",
        f"status={_escape_tag(status)}",
        f"critic={_escape_tag(critic)}",
    ])

    fields = ",".join([
        f"prompt_tokens={prompt_tokens}i",
        f"completion_tokens={completion_tokens}i",
        f"cost_usd={cost_usd}",
        f"latency_first_token_ms={latency_first_token_ms}i",
        f"latency_total_ms={latency_total_ms}i",
        f'request_id="{request_id}"',
    ])

    timestamp_ns = int(time.time() * 1e9)
    line = f"coder_usage,{tags} {fields} {timestamp_ns}"

    try:
        import threading

        def _write():
            import httpx as _httpx
            try:
                _httpx.post(
                    f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=ns",
                    headers={
                        "Authorization": f"Token {INFLUXDB_TOKEN}",
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                    content=line.encode(),
                    timeout=5.0,
                )
            except Exception as exc:
                logger.debug(f"[UsageTracker] Error escribiendo a InfluxDB: {exc}")

        threading.Thread(target=_write, daemon=True).start()
    except Exception as exc:
        logger.debug(f"[UsageTracker] Error lanzando thread: {exc}")
