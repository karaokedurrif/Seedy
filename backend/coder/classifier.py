"""Seedy Coder — Clasificador de tipo de tarea a partir del request de Continue."""

import re
from .policy import TaskType


# Patrones para detectar intención
_FIM_RE = re.compile(r"<\|fim_(?:prefix|suffix|middle)\|>", re.IGNORECASE)
_STACK_TRACE_RE = re.compile(
    r"Traceback \(most recent call last\)|"
    r"Error:|Exception:|raise \w+Error|"
    r"  File \".*\", line \d+",
    re.IGNORECASE,
)
_EDIT_KEYWORDS_RE = re.compile(
    r"\b(refactori[zs]a?|extrae?|mueve?|renombra?|separa?|divide?|"
    r"reestructura?|reorgani[zs]a?|split|extract|rename|move|restructure|"
    r"reescribe?|rewrite)\b",
    re.IGNORECASE,
)
_ARCHITECT_KEYWORDS_RE = re.compile(
    r"\b(diseñ[ao]|arquitectura?|deber[ií]a usar|cuál es mejor|"
    r"design|architecture|should I use|which is better|qué enfoque|"
    r"trade.?off|pattern|patrón|decisión|decision)\b",
    re.IGNORECASE,
)
_DEBUG_KEYWORDS_RE = re.compile(
    r"\b(por qué falla|arregla?|fix|debug|error en|bug|why does it fail|"
    r"no funciona|not working|crash|exception)\b",
    re.IGNORECASE,
)


def classify(
    messages: list[dict],
    has_tools: bool = False,
    context_tokens: int = 0,
    has_fim: bool = False,
) -> TaskType:
    """
    Clasifica el request en un TaskType basándose en heurísticas sobre los mensajes.

    Args:
        messages: Lista de mensajes en formato OpenAI.
        has_tools: True si el request incluye tools (Continue agent mode).
        context_tokens: Número estimado de tokens en el contexto.
        has_fim: True si el request usa Fill-In-the-Middle (suffix presente).

    Returns:
        TaskType elegido.
    """
    if has_fim:
        return TaskType.AUTOCOMPLETE

    if has_tools:
        return TaskType.AGENT_TOOL_USE

    # Extraer el último mensaje del usuario para análisis
    last_user = ""
    full_context = ""
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):
            # OpenAI format con partes (vision)
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        full_context += content + "\n"
        if m.get("role") == "user":
            last_user = content

    # Stack trace → DEBUG
    if _STACK_TRACE_RE.search(full_context):
        return TaskType.DEBUG

    if last_user:
        # Intención de debug
        if _DEBUG_KEYWORDS_RE.search(last_user):
            return TaskType.DEBUG

        # Intención de arquitectura
        if _ARCHITECT_KEYWORDS_RE.search(last_user):
            return TaskType.ARCHITECT

        # Intención de edición/refactor con múltiple contexto
        if _EDIT_KEYWORDS_RE.search(last_user):
            if context_tokens > 4_000:
                return TaskType.REFACTOR_MULTI
            return TaskType.INLINE_EDIT

    # Por tamaño de contexto
    if context_tokens > 4_000:
        return TaskType.CHAT_LONG

    # Default: chat rápido
    return TaskType.CHAT_QUICK


def estimate_tokens(messages: list[dict]) -> int:
    """Estimación rápida de tokens (4 caracteres ≈ 1 token)."""
    total_chars = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total_chars += len(part.get("text", ""))
        else:
            total_chars += len(content)
    return total_chars // 4
