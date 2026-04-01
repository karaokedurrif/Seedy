"""Seedy Runtime — AgentRun logger.

Lightweight logging of every AI invocation. Stores runs in an append-only
JSONL file and in-memory buffer for the API. No DB dependency yet.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import AgentRun

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.environ.get("SEEDY_DATA_DIR", "/app/data"))
_LOG_FILE = _DATA_DIR / "agent_runs.jsonl"
_recent_runs: list[dict] = []
_MAX_RECENT = 200


def log_agent_run(
    *,
    task_type: str,
    expert_used: str = "",
    model_used: str = "",
    tools_invoked: list[str] | None = None,
    input_summary: str = "",
    output_summary: str = "",
    latency_ms: int = 0,
    cost_usd: float = 0.0,
    confidence: float = 0.0,
    tenant_id: str = "palacio",
) -> str:
    """Log an AgentRun and return its run_id."""
    run = AgentRun(
        run_id=str(uuid.uuid4())[:12],
        tenant_id=tenant_id,
        timestamp=datetime.now(timezone.utc),
        task_type=task_type,
        expert_used=expert_used,
        model_used=model_used,
        tools_invoked=tools_invoked or [],
        input_summary=input_summary[:500],
        output_summary=output_summary[:500],
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        confidence=confidence,
    )
    record = run.model_dump()
    record["timestamp"] = record["timestamp"].isoformat()

    _recent_runs.append(record)
    if len(_recent_runs) > _MAX_RECENT:
        _recent_runs.pop(0)

    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write agent_run to disk: {e}")

    return run.run_id


def get_recent_runs(limit: int = 50, task_type: str | None = None) -> list[dict]:
    """Return recent AgentRun records, optionally filtered by task_type."""
    runs = _recent_runs if not task_type else [r for r in _recent_runs if r["task_type"] == task_type]
    return list(reversed(runs[-limit:]))


class RunTimer:
    """Context manager to measure latency for log_agent_run."""
    def __init__(self):
        self.start = 0
        self.elapsed_ms = 0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.monotonic() - self.start) * 1000)
