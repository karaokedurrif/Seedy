"""Seedy Backend — Router /runtime

Exposes agent run logs and tool registry for observability.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["runtime"])

_TOOL_REGISTRY_PATH = Path(__file__).parent.parent / "runtime" / "tool_registry.json"


@router.get("/tools")
async def list_tools():
    """Return the tool registry."""
    try:
        with open(_TOOL_REGISTRY_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


@router.get("/runs")
async def list_runs(
    limit: int = Query(50, ge=1, le=500),
    task_type: str | None = Query(None),
):
    """Return recent AgentRun records."""
    try:
        from runtime.logger import get_recent_runs
        return get_recent_runs(limit=limit, task_type=task_type)
    except ImportError:
        return []
