"""Seedy Coder — Budget Guard: cap diario/mensual de gasto en providers cloud."""

import logging
import os
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "neofarm")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "porcidata")

# Caps por defecto (sobreescribibles vía env)
DAILY_CAP_USD = float(os.environ.get("CODER_DAILY_CAP_USD", "5.0"))
MONTHLY_CAP_USD = float(os.environ.get("CODER_MONTHLY_CAP_USD", "100.0"))
WARN_AT_PCT = 0.80
DEGRADE_AT_PCT = 0.95

# Cache simple para no consultar InfluxDB en cada request
_cache: dict[str, tuple[float, float]] = {}  # key → (value, timestamp)
_CACHE_TTL = 60.0  # segundos


@dataclass
class BudgetStatus:
    day_usd: float
    month_usd: float
    cap_day: float
    cap_month: float
    should_warn: bool
    should_degrade: bool


async def get_status(project: str | None = None) -> BudgetStatus:
    """Lee el gasto acumulado desde InfluxDB y devuelve el estado del budget."""
    day_usd = await _query_spend("1d", project)
    month_usd = await _query_spend("30d", project)

    return BudgetStatus(
        day_usd=day_usd,
        month_usd=month_usd,
        cap_day=DAILY_CAP_USD,
        cap_month=MONTHLY_CAP_USD,
        should_warn=(
            day_usd > DAILY_CAP_USD * WARN_AT_PCT
            or month_usd > MONTHLY_CAP_USD * WARN_AT_PCT
        ),
        should_degrade=(
            day_usd > DAILY_CAP_USD * DEGRADE_AT_PCT
            or month_usd > MONTHLY_CAP_USD * DEGRADE_AT_PCT
        ),
    )


async def _query_spend(window: str, project: str | None) -> float:
    """Consulta InfluxDB: SUM(cost_usd) del módulo coder en el periodo dado."""
    cache_key = f"{window}:{project or 'all'}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _CACHE_TTL:
        return cached[0]

    if not INFLUXDB_TOKEN:
        return 0.0

    project_filter = f'|> filter(fn: (r) => r.project == "{project}")' if project else ""
    flux_query = f"""
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "coder_usage")
  |> filter(fn: (r) => r._field == "cost_usd")
  {project_filter}
  |> sum()
"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
                headers={
                    "Authorization": f"Token {INFLUXDB_TOKEN}",
                    "Content-Type": "application/vnd.flux",
                    "Accept": "application/csv",
                },
                content=flux_query,
            )
            if resp.status_code != 200:
                return 0.0
            # Parsear CSV de InfluxDB: buscar la columna _value
            total = 0.0
            for line in resp.text.splitlines():
                parts = line.split(",")
                # El CSV de InfluxDB tiene _value en la columna con cabecera
                if parts and len(parts) > 3:
                    try:
                        total += float(parts[-1])
                    except ValueError:
                        pass
            _cache[cache_key] = (total, time.time())
            return total
    except Exception as exc:
        logger.debug(f"[BudgetGuard] Error consultando InfluxDB: {exc}")
        return 0.0
