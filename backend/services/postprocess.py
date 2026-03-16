"""Seedy Backend — Post-procesador de respuestas.

Limpia la salida del LLM antes de enviarla al usuario:
- Elimina markdown (###, **, *, ~~, etc.)
- Convierte headers a MAYÚSCULAS con guión bajo
- Normaliza bullets a guiones
- Limpia artefactos de generación

Se aplica ANTES del critic gate, para que el critic evalúe
la respuesta ya limpia (evita bloqueos por formato).
"""

import re
import logging

logger = logging.getLogger(__name__)


def clean_markdown(text: str) -> str:
    """
    Elimina formato markdown del texto generado por el LLM.
    Convierte a texto plano puro: sin #, **, *, -, ~~, ```, ni bullets.
    Los items de lista se convierten a líneas con prefijo numérico o punto medio (·).
    """
    if not text:
        return text

    lines = text.split("\n")
    cleaned = []
    bullet_counter = 0  # Para autonumerar bullets sueltos

    for line in lines:
        stripped = line.strip()

        # 1. Headers ### Título → TÍTULO (sin #)
        header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header_match:
            title = header_match.group(2).strip()
            title = _strip_inline_markdown(title)
            cleaned.append(title.upper())
            bullet_counter = 0
            continue

        # 2. Bullets con asterisco o guion: * item / - item → " · item"
        bullet_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
        if bullet_match:
            indent = bullet_match.group(1)
            content = bullet_match.group(2)
            content = _strip_inline_markdown(content)
            # Sub-bullets (indentados) → punto medio
            if len(indent) >= 2:
                cleaned.append(f"  · {content}")
            else:
                bullet_counter += 1
                cleaned.append(f"{bullet_counter}. {content}")
            continue

        # 3. Bullets numerados con negritas: 1. **Algo**: → 1. Algo:
        num_match = re.match(r"^(\s*\d+\.)\s+\*\*(.+?)\*\*(.*)$", line)
        if num_match:
            prefix = num_match.group(1)
            bold_content = num_match.group(2)
            rest = num_match.group(3)
            rest = _strip_inline_markdown(rest)
            cleaned.append(f"{prefix} {bold_content}{rest}")
            bullet_counter = int(re.search(r"\d+", prefix).group())
            continue

        # 4. Línea vacía resetea counter de bullets
        if not stripped:
            bullet_counter = 0
            cleaned.append("")
            continue

        # 5. Líneas normales: limpiar markdown inline
        line = _strip_inline_markdown(line)
        cleaned.append(line)
        # Si es texto normal (no bullet), resetear counter
        if not re.match(r"^\s*\d+\.", line):
            bullet_counter = 0

    result = "\n".join(cleaned)

    # 6. Limpiar líneas vacías múltiples (max 2 seguidas)
    result = re.sub(r"\n{3,}", "\n\n", result)

    # 7. Limpiar separadores horizontales markdown
    result = re.sub(r"^-{3,}$", "", result, flags=re.MULTILINE)
    result = re.sub(r"^\*{3,}$", "", result, flags=re.MULTILINE)
    result = re.sub(r"^_{3,}$", "", result, flags=re.MULTILINE)

    # 8. Limpiar code blocks residuales
    result = result.replace("```", "")

    # 9. Sweep final: eliminar cualquier ** o __ residual que haya escapado
    #    (puede pasar con patrones multilinea o anidados)
    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
    result = re.sub(r"__(.+?)__", r"\1", result)
    # Eliminar ** sueltos (sin cierre) — artefactos
    result = result.replace("**", "")

    logger.debug(f"[Postprocess] Limpieza aplicada, longitud: {len(result)}")

    return result.strip()


def _strip_inline_markdown(text: str) -> str:
    """Elimina formato markdown inline: negritas, cursivas, tachado, código."""
    # Negritas **texto** o __texto__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Cursivas *texto* o _texto_ (cuidado con no romper guiones bajos en variables)
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"\1", text)
    # Tachado ~~texto~~
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Código inline `texto`
    text = re.sub(r"`([^`]+?)`", r"\1", text)
    # Links [texto](url) → texto (url)
    text = re.sub(r"\[([^\]]+?)\]\(([^)]+?)\)", r"\1 (\2)", text)
    return text
