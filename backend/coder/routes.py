"""Seedy Coder v4.3 — Endpoints FastAPI: /v1/code/*

OpenAI-compatible para Continue.dev. Aislado del pipeline RAG y Vision.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .budget_guard import get_status as budget_status
from .classifier import classify, estimate_tokens
from .critic_gate_code import evaluate as critic_evaluate
from .policy import CoderTier, TaskType
from .prompt_builder import inject_system_into_messages
from .providers.base import CoderRequest
from .router import _provider_for, _get_chain, _filter_by_context, _filter_by_tools, stream_with_fallback
from . import usage_tracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["coder"])


# ── Modelos Pydantic ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: Any  # str o list (vision)


class ChatCompletionRequest(BaseModel):
    model: str = "seedy-auto"
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float = 0.2
    max_tokens: int = 2048
    tools: list[dict] | None = None


class CompletionRequest(BaseModel):
    """Legacy FIM completions endpoint."""
    model: str = "seedy-fim"
    prompt: str
    suffix: str | None = None
    max_tokens: int = 128
    stream: bool = True
    temperature: float = 0.1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_tier(header_value: str | None) -> CoderTier:
    try:
        return CoderTier(header_value or "auto")
    except ValueError:
        return CoderTier.AUTO


def _build_sse_chunk(content: str, request_id: str, finish_reason: str | None = None) -> str:
    delta: dict = {}
    if content:
        delta["content"] = content
    if finish_reason:
        delta["finish_reason"] = finish_reason

    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _build_sse_done_chunk(request_id: str, prompt_tokens: int, completion_tokens: int) -> str:
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/v1/code/models")
async def list_models():
    """Lista los modelos virtuales disponibles para Continue.dev."""
    models = [
        {"id": "seedy-auto",          "object": "model", "owned_by": "seedy", "description": "Router automático (recomendado)"},
        {"id": "seedy-local",         "object": "model", "owned_by": "seedy", "description": "Solo Ollama local"},
        {"id": "seedy-balanced",      "object": "model", "owned_by": "seedy", "description": "Balanced: cloud + local"},
        {"id": "seedy-max",           "object": "model", "owned_by": "seedy", "description": "Máxima calidad, mayor coste"},
        {"id": "seedy-fim",           "object": "model", "owned_by": "seedy", "description": "Fill-In-the-Middle para autocomplete"},
        {"id": "glm-5.1",             "object": "model", "owned_by": "seedy", "description": "GLM-5.1 directo (debug)"},
        {"id": "qwen3-coder-next",    "object": "model", "owned_by": "seedy", "description": "Qwen3-Coder-Next FP8 directo"},
        {"id": "qwen3-coder-480b",    "object": "model", "owned_by": "seedy", "description": "Qwen3-Coder-480B directo"},
        {"id": "minimax-m2.7",        "object": "model", "owned_by": "seedy", "description": "MiniMax M2.7 directo"},
    ]
    return {"object": "list", "data": models}


@router.post("/v1/code/chat/completions")
async def code_chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    x_seedy_tier: str | None = Header(None),
    x_seedy_project: str | None = Header(None),
    x_seedy_force_model: str | None = Header(None),
):
    """
    Endpoint principal OpenAI-compatible para Continue.dev.

    Headers opcionales:
    - X-Seedy-Tier: auto | local | balanced | max
    - X-Seedy-Project: slug del proyecto para telemetría
    - X-Seedy-Force-Model: bypass del router (debug)
    """
    request_id = f"seedy-{uuid.uuid4().hex[:12]}"
    t_start = time.time()

    tier = _parse_tier(x_seedy_tier)
    # Tier por nombre de modelo
    if req.model in ("seedy-local",):
        tier = CoderTier.LOCAL
    elif req.model in ("seedy-max",):
        tier = CoderTier.MAX
    elif req.model in ("seedy-balanced",):
        tier = CoderTier.BALANCED

    # Force model via X-Seedy-Force-Model o modelo específico en el request
    force_model: str | None = x_seedy_force_model
    if req.model not in ("seedy-auto", "seedy-local", "seedy-balanced", "seedy-max", "seedy-fim"):
        # El usuario especificó un modelo concreto (ej: "glm-5.1")
        model_alias_map = {
            "glm-5.1":          "together:glm-5.1",
            "qwen3-coder-next": "together:qwen3-coder-next",
            "qwen3-coder-480b": "together:qwen3-coder-480b",
            "minimax-m2.7":     "together:minimax-m2.7",
        }
        force_model = model_alias_map.get(req.model, req.seedy_force_model if hasattr(req, "seedy_force_model") else None)

    project = x_seedy_project or "default"
    messages_dicts = [m.model_dump() for m in req.messages]

    # Budget check
    budget = await budget_status(project)
    budget_degrade = budget.should_degrade

    # Clasificar tarea
    context_tokens = estimate_tokens(messages_dicts)
    has_fim = False
    task_type = classify(
        messages=messages_dicts,
        has_tools=bool(req.tools),
        context_tokens=context_tokens,
        has_fim=has_fim,
    )

    # Inyectar system prompt
    enriched_messages = inject_system_into_messages(messages_dicts, task_type)

    coder_req = CoderRequest(
        messages=enriched_messages,
        model_id="",  # se asignará en stream_with_fallback
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        tools=req.tools,
        stream=req.stream,
    )

    if req.stream:
        return StreamingResponse(
            _stream_response(
                coder_req=coder_req,
                task_type=task_type,
                tier=tier,
                budget_degrade=budget_degrade,
                budget=budget,
                project=project,
                request_id=request_id,
                t_start=t_start,
                force_model=force_model,
                context_tokens=context_tokens,
            ),
            media_type="text/event-stream",
            headers={
                "X-Seedy-Request-Id": request_id,
                "X-Seedy-Task-Type": task_type.value,
                "X-Seedy-Budget-Warn": str(budget.should_warn).lower(),
                "Cache-Control": "no-cache",
            },
        )

    # Non-streaming: acumular todo y devolver
    full_content = ""
    model_used = "none"
    async for chunk, m_id in stream_with_fallback(
        coder_req, task_type, tier, budget_degrade
    ):
        if chunk.content:
            full_content += chunk.content
        model_used = m_id

    return JSONResponse({
        "id": request_id,
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": full_content},
            "finish_reason": "stop",
        }],
        "model": model_used,
        "usage": {
            "prompt_tokens": context_tokens,
            "completion_tokens": len(full_content) // 4,
        },
    }, headers={
        "X-Seedy-Routed-To": model_used,
        "X-Seedy-Task-Type": task_type.value,
    })


async def _stream_response(
    *,
    coder_req: CoderRequest,
    task_type: TaskType,
    tier: CoderTier,
    budget_degrade: bool,
    budget,
    project: str,
    request_id: str,
    t_start: float,
    force_model: str | None,
    context_tokens: int,
):
    """Generador SSE del stream de respuesta con telemetría y critic."""
    full_response = ""
    model_used = "none"
    completion_tokens = 0
    t_first_token: float | None = None

    # Advertencia de budget en el primer chunk
    if budget.should_degrade:
        warn_msg = f"// ⚠️ Seedy: cap diario al {int(budget.day_usd/budget.cap_day*100)}% — degradado a tier local\n"
        yield _build_sse_chunk(warn_msg, request_id)
    elif budget.should_warn:
        warn_msg = f"// ⚠️ Seedy: {int(budget.day_usd/budget.cap_day*100)}% del cap diario consumido\n"
        yield _build_sse_chunk(warn_msg, request_id)

    # Forzar modelo si se especificó
    if force_model:
        from .router import _provider_for as _pfr
        provider = _pfr(force_model)
        if provider:
            coder_req.model_id = force_model
            try:
                async for chunk in provider.stream(coder_req):
                    if t_first_token is None and chunk.content:
                        t_first_token = time.time()
                    if chunk.content:
                        full_response += chunk.content
                        completion_tokens += len(chunk.content) // 4
                        yield _build_sse_chunk(chunk.content, request_id)
                    if chunk.finish_reason:
                        model_used = force_model
                model_used = force_model
            except Exception as exc:
                logger.warning(f"[Routes] Force model {force_model} failed: {exc}")
                # Fallback al stream normal
                force_model = None

    if not force_model or model_used == "none":
        async for chunk, m_id in stream_with_fallback(
            coder_req, task_type, tier, budget_degrade
        ):
            if t_first_token is None and chunk.content:
                t_first_token = time.time()
            model_used = m_id
            if chunk.content:
                full_response += chunk.content
                completion_tokens += len(chunk.content) // 4
                yield _build_sse_chunk(chunk.content, request_id)
            if chunk.finish_reason == "error":
                yield _build_sse_chunk(chunk.content, request_id, "stop")
                return

    # Critic Gate (no bloqueante, en paralelo con cierre del stream)
    if full_response and len(full_response) > 20:
        try:
            verdict = await asyncio.wait_for(
                critic_evaluate(full_response),
                timeout=15.0,
            )
            if not verdict.passed:
                critic_comment = f"\n// ⚠️ Seedy Critic: {verdict.reason}"
                yield _build_sse_chunk(critic_comment, request_id)
                full_response += critic_comment
        except (asyncio.TimeoutError, Exception) as exc:
            logger.debug(f"[Routes] Critic timeout/error: {exc}")

    # Determinar provider para telemetría
    provider_name = model_used.split(":")[0] if ":" in model_used else "unknown"
    t_end = time.time()
    t_first = t_first_token or t_end
    latency_first = int((t_first - t_start) * 1000)
    latency_total = int((t_end - t_start) * 1000)

    # Estimar coste
    cost = 0.0
    if ":" in model_used:
        from .router import _provider_for as _pfr
        p = _pfr(model_used)
        if p:
            cost = p.estimate_cost(model_used, context_tokens, completion_tokens)

    # Telemetría InfluxDB
    usage_tracker.record(
        provider=provider_name,
        model=model_used,
        task_type=task_type.value,
        tier=tier.value,
        project=project,
        prompt_tokens=context_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        latency_first_token_ms=latency_first,
        latency_total_ms=latency_total,
        request_id=request_id,
        status="ok",
        critic="warn" if full_response and "⚠️ Seedy Critic" in full_response else "pass",
    )

    # Done event con usage + headers extra en la respuesta SSE
    done_payload = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": context_tokens,
            "completion_tokens": completion_tokens,
        },
        "x_seedy_routed_to": model_used,
        "x_seedy_cost_usd": round(cost, 6),
        "x_seedy_latency_ms": latency_total,
    }
    yield f"data: {json.dumps(done_payload)}\n\ndata: [DONE]\n\n"


@router.post("/v1/code/completions")
async def code_fim_completions(
    req: CompletionRequest,
    x_seedy_project: str | None = Header(None),
):
    """
    Legacy completions endpoint para FIM (Fill-In-the-Middle).
    Continue.dev lo usa para autocompletado con `useLegacyCompletionsEndpoint: true`.
    Siempre va a Ollama local.
    """
    request_id = f"seedy-fim-{uuid.uuid4().hex[:8]}"
    t_start = time.time()
    project = x_seedy_project or "default"

    from .providers.ollama_provider import OllamaProvider
    ollama = OllamaProvider()

    coder_req = CoderRequest(
        messages=[],
        model_id="ollama:agritech",
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        prompt_fim=req.prompt,
        suffix_fim=req.suffix or "",
    )

    if req.stream:
        async def _fim_stream():
            full = ""
            async for chunk in ollama.stream(coder_req):
                if chunk.content:
                    full += chunk.content
                    payload = {
                        "id": request_id,
                        "object": "text_completion",
                        "choices": [{"text": chunk.content, "index": 0, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                if chunk.finish_reason:
                    done = {
                        "id": request_id,
                        "object": "text_completion",
                        "choices": [{"text": "", "index": 0, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n"
            usage_tracker.record(
                provider="ollama", model="ollama:agritech",
                task_type="AUTOCOMPLETE", tier="local",
                project=project, prompt_tokens=len(req.prompt) // 4,
                completion_tokens=len(full) // 4, cost_usd=0.0,
                latency_first_token_ms=0,
                latency_total_ms=int((time.time() - t_start) * 1000),
                request_id=request_id,
            )

        return StreamingResponse(_fim_stream(), media_type="text/event-stream")

    # Non-streaming
    full = ""
    async for chunk in ollama.stream(coder_req):
        if chunk.content:
            full += chunk.content
    return JSONResponse({
        "id": request_id,
        "object": "text_completion",
        "choices": [{"text": full, "index": 0, "finish_reason": "stop"}],
    })


@router.get("/v1/code/route/preview")
async def route_preview(
    task_type: str = "CHAT_QUICK",
    tier: str = "auto",
    context_tokens: int = 1000,
    needs_tools: bool = False,
):
    """Dry-run del router: muestra qué modelo se elegiría sin hacer ninguna llamada."""
    try:
        tt = TaskType(task_type)
        t = CoderTier(tier)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    chain = _get_chain(tt, t)
    chain = _filter_by_context(chain, context_tokens)
    chain = _filter_by_tools(chain, needs_tools)

    return {
        "task_type": tt.value,
        "tier": t.value,
        "context_tokens": context_tokens,
        "needs_tools": needs_tools,
        "selected_chain": chain,
        "primary_model": chain[0] if chain else "none",
    }


@router.get("/v1/code/telemetry")
async def get_telemetry(
    x_seedy_project: str | None = Header(None),
):
    """Resumen de uso y coste del módulo coder."""
    budget = await budget_status(x_seedy_project)
    return {
        "day_usd": round(budget.day_usd, 4),
        "month_usd": round(budget.month_usd, 4),
        "cap_day_usd": budget.cap_day,
        "cap_month_usd": budget.cap_month,
        "should_warn": budget.should_warn,
        "should_degrade": budget.should_degrade,
        "day_pct": round(budget.day_usd / budget.cap_day * 100, 1) if budget.cap_day else 0,
        "month_pct": round(budget.month_usd / budget.cap_month * 100, 1) if budget.cap_month else 0,
    }
