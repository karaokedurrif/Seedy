"""Seedy Coder — Construcción del system prompt componible por task_type."""

import pathlib
import logging
from .policy import TaskType

logger = logging.getLogger(__name__)

_PROMPTS_DIR = pathlib.Path(__file__).parent / "prompts"


def _load(filename: str) -> str:
    try:
        return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"[PromptBuilder] Fichero de prompt no encontrado: {filename}")
        return ""


BASE_PROMPT = """You are Seedy Coder, the coding agent of OvoSfera (an Agritech platform for \
heritage poultry breeding and precision livestock management). \
You write Python (FastAPI, asyncio, pydantic), JavaScript/TypeScript (Next.js, React), \
and occasionally Bash, SQL, Go.

Output rules:
- Direct, professional. No "I hope this helps", no apology preambles.
- Code blocks include language tag. Comments in the language of the user's prompt.
- If the user writes in Spanish, respond in Spanish. If English, respond in English.
- Never add ethical disclaimers about programming tasks. The user is a senior developer.
- If you spot a security issue (SQLi, hardcoded secret, path traversal, SSRF), \
mention it in 1 line and continue with the task.
- Never rewrite code the user already has correct unless explicitly asked."""

# Bloques inyectables cargados una sola vez al importar el módulo
_INJECTABLE_BLOCKS: dict[str, str] = {
    "cot_brief":     _load("cot_brief.txt"),
    "silent_errors": _load("silent_errors.txt"),
    "modularity":    _load("modularity.txt"),
}

# Qué bloques se inyectan para cada TaskType
_INJECTION_MAP: dict[str, list[str]] = {
    TaskType.AUTOCOMPLETE:   [],
    TaskType.INLINE_EDIT:    ["cot_brief"],
    TaskType.CHAT_QUICK:     [],
    TaskType.CHAT_LONG:      ["silent_errors"],
    TaskType.REFACTOR_MULTI: ["cot_brief", "silent_errors", "modularity"],
    TaskType.ARCHITECT:      ["silent_errors", "modularity"],
    TaskType.DEBUG:          ["cot_brief", "silent_errors"],
    TaskType.AGENT_TOOL_USE: ["cot_brief", "silent_errors", "modularity"],
}

_SEPARATOR = "\n\n---\n\n"


def build_system_prompt(task_type: TaskType, model_id: str = "") -> str:
    """
    Construye el system prompt componible inyectando solo los bloques
    relevantes para el task_type.

    Los modelos Anthropic reciben el mismo texto (el formato XML lo maneja
    el AnthropicProvider al separar el system de los messages).

    Args:
        task_type: Tipo de tarea clasificado.
        model_id:  model_id interno (para tweaks por modelo si aplica).

    Returns:
        System prompt completo listo para inyectar.
    """
    blocks = [BASE_PROMPT]
    for key in _INJECTION_MAP.get(task_type, []):
        block = _INJECTABLE_BLOCKS.get(key, "")
        if block:
            blocks.append(block)

    return _SEPARATOR.join(blocks)


def inject_system_into_messages(
    messages: list[dict],
    task_type: TaskType,
    model_id: str = "",
) -> list[dict]:
    """
    Prepend del system prompt a los mensajes.
    Si ya hay un mensaje con role=system, lo reemplaza/combina.

    Returns:
        Nueva lista de mensajes con system prompt aplicado.
    """
    seedy_system = build_system_prompt(task_type, model_id)

    # Buscar si ya hay un system message
    has_system = any(m.get("role") == "system" for m in messages)

    if has_system:
        result = []
        for m in messages:
            if m.get("role") == "system":
                # Combinar: system original + bloques Seedy al final
                combined = m.get("content", "") + _SEPARATOR + seedy_system
                result.append({"role": "system", "content": combined})
            else:
                result.append(m)
        return result
    else:
        return [{"role": "system", "content": seedy_system}] + list(messages)
