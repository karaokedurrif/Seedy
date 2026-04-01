"""Seedy Runtime — Pydantic models for agent traceability.

These models lay the foundation for the Seedy agent runtime:
- ToolDefinition: describes each tool in the platform
- AgentRun: logs every AI invocation (YOLO, RAG, Re-ID, genetics, etc.)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    tool_id: str = Field(..., description="Unique identifier, e.g. 'yolo_detect'")
    name: str = Field(..., description="Human-readable name")
    description: str = Field("", description="What the tool does")
    input_schema: dict = Field(default_factory=dict, description="JSON Schema of input params")
    output_schema: dict = Field(default_factory=dict, description="JSON Schema of output")
    requires_approval: bool = Field(False, description="True if action is destructive / needs human OK")
    max_latency_ms: int = Field(30000, description="Expected max latency in milliseconds")
    cost_tier: str = Field("free", description="free | low | medium | high")


class AgentRun(BaseModel):
    run_id: str = Field(..., description="UUID of this run")
    tenant_id: str = Field("palacio", description="Farm/tenant identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    task_type: str = Field(..., description="vision | rag | genetics | alert | twin | reid | sensor")
    expert_used: str = Field("", description="e.g. expert_vision, expert_rag, expert_genetics")
    model_used: str = Field("", description="e.g. seedy:v16, together:kimi-k2.5, yolov8s")
    tools_invoked: list[str] = Field(default_factory=list, description="List of tool_ids used")
    input_summary: str = Field("", description="Brief description of the input")
    output_summary: str = Field("", description="Brief description of the output")
    latency_ms: int = Field(0)
    cost_usd: float = Field(0.0)
    confidence: float = Field(0.0, description="0.0-1.0 confidence score")
    human_feedback: Optional[str] = Field(None, description="👍 | 👎 | None")
