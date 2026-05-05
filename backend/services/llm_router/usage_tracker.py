"""
Usage Tracker — Telemetría de llamadas LLM a InfluxDB.
Permite análisis histórico de costes, latencias, y patrones de uso.
"""

import logging
from typing import Optional
from datetime import datetime

log = logging.getLogger(__name__)

# Import InfluxDB client (opcional)
try:
    from influxdb_client import Point
    from influxdb_client.client.write_api import ASYNCHRONOUS
    INFLUXDB_AVAILABLE = True
except ImportError:
    Point = None
    ASYNCHRONOUS = None
    INFLUXDB_AVAILABLE = False
    log.warning("influxdb_client not available. Usage tracking disabled.")

# Import telemetry config (opcional)
try:
    from backend.services.telemetry import get_influx_client, INFLUX_BUCKET, INFLUX_ORG
except ImportError:
    get_influx_client = None
    INFLUX_BUCKET = None
    INFLUX_ORG = None
    if INFLUXDB_AVAILABLE:
        log.warning("Telemetry service not available. Usage tracking disabled.")
        INFLUXDB_AVAILABLE = False


def track_usage_influx(
    step_name: str,
    model_id: str,
    result,  # LLMResult
    cost_usd: float,
    status: str = "ok",
    mode: str = "default",
):
    """
    Escribe una medición de uso LLM a InfluxDB.
    
    Measurement: llm_call
    Tags: step, provider, model, status, mode
    Fields: prompt_tokens, completion_tokens, first_token_latency_s, total_latency_s, cost_usd
    """
    if not INFLUXDB_AVAILABLE:
        return
    
    try:
        client = get_influx_client()
        if not client:
            return
        
        write_api = client.write_api(write_options=ASYNCHRONOUS)
        
        # Extraer provider del model_id (ej: "ollama:qwen2.5-7b" → "ollama")
        provider = model_id.split(":")[0] if ":" in model_id else "unknown"
        model_name = model_id.split(":", 1)[1] if ":" in model_id else model_id
        
        point = (
            Point("llm_call")
            .tag("step", step_name)
            .tag("provider", provider)
            .tag("model", model_name)
            .tag("status", status)
            .tag("mode", mode)
            .field("prompt_tokens", result.prompt_tokens)
            .field("completion_tokens", result.completion_tokens)
            .field("first_token_latency_s", result.first_token_latency_s)
            .field("total_latency_s", result.total_latency_s)
            .field("cost_usd", cost_usd)
            .time(datetime.utcnow())
        )
        
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        
        log.debug(
            f"📊 Usage tracked: {step_name} | {model_id} | "
            f"{result.total_latency_s:.2f}s | ${cost_usd:.4f}"
        )
    
    except Exception as exc:
        log.warning(f"Failed to track usage to InfluxDB: {exc}")


def track_error_influx(
    step_name: str,
    model_id: str,
    error_type: str,
    mode: str = "default",
):
    """Registra un error de LLM en InfluxDB."""
    if not INFLUXDB_AVAILABLE:
        return
    
    try:
        client = get_influx_client()
        if not client:
            return
        
        write_api = client.write_api(write_options=ASYNCHRONOUS)
        
        provider = model_id.split(":")[0] if ":" in model_id else "unknown"
        model_name = model_id.split(":", 1)[1] if ":" in model_id else model_id
        
        point = (
            Point("llm_call")
            .tag("step", step_name)
            .tag("provider", provider)
            .tag("model", model_name)
            .tag("status", error_type)  # "timeout" | "error" | "fallback"
            .tag("mode", mode)
            .field("error_count", 1)
            .time(datetime.utcnow())
        )
        
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
    
    except Exception as exc:
        log.warning(f"Failed to track error to InfluxDB: {exc}")
