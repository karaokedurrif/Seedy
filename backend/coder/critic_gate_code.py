"""Seedy Coder — Critic Gate adaptado a código.

No bloquea el output. Solo añade un comentario de advertencia al final
del stream si detecta problemas estructurales graves.
"""

import logging
import os
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
CRITIC_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"  # barato y rápido para esta tarea
CRITIC_TIMEOUT = 20.0

_CRITIC_PROMPT = """You are a code reviewer. Evaluate ONLY if the response has serious structural problems.
Do NOT evaluate style, do NOT suggest improvements, do NOT comment on architecture.

SERIOUS PROBLEMS (flag these):
- import of a module that clearly does not exist (e.g., `from fastapi.utils.magic import X`)
- await outside async def
- dangerous absolute path (/etc/passwd, /root, ~/.ssh/...)
- SQL string-concatenation with user input (SQL injection)
- hardcoded API key or secret in generated code (not in placeholders like YOUR_KEY_HERE)
- code in wrong language (user asked Python, got JavaScript returned as Python)

VERDICT: PASS | WARN
- PASS: no serious problems found
- WARN: at least one problem. Also return a one-line description.

Respond ONLY in this exact format:
VERDICT: PASS
or
VERDICT: WARN
REASON: <one-line description>"""

_VERDICT_RE = re.compile(r"VERDICT:\s*(PASS|WARN)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE)


@dataclass
class CriticVerdict:
    passed: bool
    reason: str = ""


async def evaluate(response_text: str) -> CriticVerdict:
    """
    Evalúa el código generado con un LLM ligero.
    Siempre devuelve PASS si el critic falla (no bloquear por timeout).
    """
    api_key = os.environ.get("TOGETHER_API_KEY", "")
    if not api_key:
        return CriticVerdict(passed=True)

    user_content = f"Evaluate this code response:\n\n```\n{response_text[:3000]}\n```"

    try:
        async with httpx.AsyncClient(timeout=CRITIC_TIMEOUT) as client:
            resp = await client.post(
                f"{TOGETHER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": CRITIC_MODEL,
                    "messages": [
                        {"role": "system", "content": _CRITIC_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 60,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

            verdict_match = _VERDICT_RE.search(raw)
            if not verdict_match:
                return CriticVerdict(passed=True)

            passed = verdict_match.group(1).upper() == "PASS"
            reason = ""
            if not passed:
                reason_match = _REASON_RE.search(raw)
                reason = reason_match.group(1).strip() if reason_match else "problema estructural detectado"

            return CriticVerdict(passed=passed, reason=reason)

    except Exception as exc:
        logger.debug(f"[CriticCode] Error evaluando: {exc}. PASS por defecto.")
        return CriticVerdict(passed=True)
