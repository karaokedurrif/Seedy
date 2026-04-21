"""Seedy Coder — Política de routing: cadenas de degradación y reglas declarativas."""

from enum import Enum


class TaskType(str, Enum):
    AUTOCOMPLETE    = "AUTOCOMPLETE"
    INLINE_EDIT     = "INLINE_EDIT"
    CHAT_QUICK      = "CHAT_QUICK"
    CHAT_LONG       = "CHAT_LONG"
    REFACTOR_MULTI  = "REFACTOR_MULTI"
    ARCHITECT       = "ARCHITECT"
    DEBUG           = "DEBUG"
    AGENT_TOOL_USE  = "AGENT_TOOL_USE"


class CoderTier(str, Enum):
    AUTO     = "auto"
    LOCAL    = "local"
    BALANCED = "balanced"
    MAX      = "max"


# Cadena de degradación por task_type
# Primer elemento = modelo preferido; siguientes = fallbacks en orden
DEGRADATION_CHAIN: dict[str, list[str]] = {
    TaskType.AUTOCOMPLETE:   ["ollama:agritech", "together:qwen3-coder-next"],
    TaskType.INLINE_EDIT:    ["together:qwen3-coder-next", "together:glm-5.1", "ollama:agritech"],
    TaskType.CHAT_QUICK:     ["together:qwen3-coder-next", "together:glm-5.1", "ollama:agritech"],
    TaskType.CHAT_LONG:      ["together:glm-5.1", "together:qwen3-coder-480b", "together:qwen3-coder-next"],
    TaskType.REFACTOR_MULTI: ["together:qwen3-coder-480b", "together:glm-5.1", "ollama:agritech"],
    TaskType.ARCHITECT:      ["together:glm-5.1", "together:minimax-m2.7", "anthropic:claude-opus-4-7"],
    TaskType.DEBUG:          ["together:glm-5.1", "together:qwen3-coder-480b", "ollama:agritech"],
    TaskType.AGENT_TOOL_USE: ["together:glm-5.1", "together:minimax-m2.7", "together:qwen3-coder-480b"],
}

# Para tier=max, ARCHITECT usa Claude si está disponible
DEGRADATION_CHAIN_MAX: dict[str, list[str]] = {
    **DEGRADATION_CHAIN,
    TaskType.ARCHITECT: ["anthropic:claude-opus-4-7", "together:glm-5.1", "together:minimax-m2.7"],
}

# Para tier=local, todo va a Ollama
DEGRADATION_CHAIN_LOCAL: dict[str, list[str]] = {
    task: ["ollama:agritech"] for task in TaskType
}

# Tabla de capacidades: qué modelos soportan tool_use
TOOL_USE_MODELS = {
    "together:glm-5.1",
    "together:minimax-m2.7",
    "together:qwen3-coder-480b",
    "anthropic:claude-opus-4-7",
    "anthropic:claude-sonnet-4-6",
}

# Límites de contexto por modelo (tokens)
CONTEXT_LIMITS: dict[str, int] = {
    "together:glm-5.1":          200_000,
    "together:glm-5":            200_000,
    "together:qwen3-coder-next":  32_768,
    "together:qwen3-coder-480b": 262_144,
    "together:minimax-m2.7":     128_000,
    "ollama:agritech":            32_768,
    "anthropic:claude-opus-4-7": 200_000,
    "anthropic:claude-sonnet-4-6": 200_000,
}

# Triggers de degradación:
# - HTTP 5xx del provider 1 → intentar provider 2
# - timeout > 30s primer token → degradar
# - HTTP 429 (rate-limit) → degradar
# - budget_guard.should_degrade → forzar tier local
