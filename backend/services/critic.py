"""
Seedy Backend — Critic Gate: evalúa respuestas antes de enviarlas al usuario.

Fase 2 v14: Doble critic:
  A) Critic estructural: detecta confusión de especie, items no-animal, incoherencia
  B) Critic técnico: verifica fidelidad factual contra la evidencia

Usa Together.ai (Llama 70B) como juez independiente del modelo principal (Ollama 14B).
Veredicto binario: PASS o BLOCK (sin REVISE — no hay loop de re-generación).
Si BLOCK, el pipeline sustituye la respuesta por un fallback seguro.
"""

import json
import logging
import httpx

from config import get_settings

logger = logging.getLogger(__name__)

CRITIC_SYSTEM = (
    "Eres el revisor de coherencia de Seedy, un asistente de ganadería y agricultura. "
    "Tu trabajo es detectar SOLO errores ESTRUCTURALES obvios, NO evalúes si los datos son correctos "
    "(el modelo principal es experto en agricultura y sabe más que tú sobre razas y variedades).\n\n"
    "SOLO BLOQUEAR si detectas ALGUNO de estos patrones:\n"
    "1. CONFUSIÓN DE ESPECIE: La pregunta es sobre una especie (ej: cerdos) pero la respuesta "
    "AFIRMA HECHOS de otra especie como si fueran de la especie preguntada. "
    "Ejemplo: 'qué razas de cerdo ibérico hay' → responde listando razas de gallina COMO SI fueran cerdos.\n"
    "IMPORTANTE para especie: Si la respuesta RECONOCE que no tiene información sobre la especie "
    "preguntada, eso NO es confusión — es honestidad. PASS.\n"
    "IMPORTANTE: Si el CONTEXTO es de una especie diferente pero la RESPUESTA contesta correctamente "
    "la pregunta original, eso es PASS — el modelo puede usar conocimiento propio.\n"
    "2. ITEM NO-ANIMAL: Lista un accesorio, producto o marca comercial como si fuera una raza/variedad. "
    "Ejemplo: 'Selle de protection poules' (es un accesorio, no una raza).\n"
    "3. RESPUESTA VACÍA O INCOHERENTE: No tiene relación alguna con la pregunta.\n\n"
    "NO evalúes el formato de la respuesta (listas, numeración, etc.) — eso ya está manejado.\n"
    "EN CASO DE DUDA → PASS. Siempre PASS. No bloquees por precaución.\n"
    "NO evalúes si las razas existen o no — el modelo principal sabe más que tú.\n"
    "NO evalúes si los atributos son correctos — eso no es tu trabajo.\n\n"
    "Responde SOLO JSON:\n"
    '{"verdict": "PASS"}\n'
    "o\n"
    '{"verdict": "BLOCK", "reasons": ["motivo concreto"], "tags": ["etiqueta"]}\n\n'
    "Tags válidos: especie_incorrecta, ruido_rag, incoherencia."
)

# Respuesta fallback cuando el critic bloquea
BLOCKED_FALLBACK = (
    "No puedo darte una respuesta fiable sobre esta consulta con la información "
    "disponible en este momento. La evidencia recuperada es insuficiente o "
    "ambigua para responder con rigor. Te recomiendo reformular la pregunta "
    "con más detalle o consultar fuentes especializadas adicionales."
)

# Frases de admisión honesta — PASS directo sin evaluación
_honest_phrases = [
    "no se corresponde con el contexto",
    "no se responde directamente con el contexto",
    "no contiene información",
    "no dispongo de información",
    "no tengo información",
    "el contexto no aborda",
    "fuera del alcance del contexto",
    "no está respaldada por el contexto",
    "no es relevante para el contexto",
    "no hay información sobre",
    "la pregunta no es relevante",
    "la pregunta no está respaldada",
    "no aparece en el contexto",
    "no está directamente cubierta",
    "no está cubierta por el contexto",
]


async def evaluate_response(
    query: str,
    context_chunks: list[dict],
    draft_answer: str,
) -> dict:
    """
    Evalúa un borrador de respuesta con el critic.

    Returns:
        {"verdict": "PASS"} o {"verdict": "BLOCK", "reasons": [...], "tags": [...]}
    """
    settings = get_settings()

    if not settings.together_api_key:
        logger.warning("[Critic] Sin TOGETHER_API_KEY — skip critic")
        return {"verdict": "PASS"}

    # Pre-filtro: si el modelo admite honestamente que no tiene contexto
    # Y el contexto realmente es vacío/pobre, PASS directo.
    # PERO si hay chunks relevantes, NO auto-PASS — el modelo debería haber usado la evidencia.
    answer_lower = draft_answer.lower()
    has_honest_phrase = any(phrase in answer_lower for phrase in _honest_phrases)
    
    if has_honest_phrase:
        # Solo auto-PASS si el contexto era realmente pobre (< 500 chars total)
        total_ctx_len = sum(len(c.get("text", "")) for c in context_chunks)
        if total_ctx_len < 500:
            logger.info(f"[Critic] PASS directo — admisión honesta + contexto pobre ({total_ctx_len} chars)")
            return {"verdict": "PASS"}
        else:
            logger.warning(
                f"[Critic] Modelo dice 'no hay info' pero contexto tiene {total_ctx_len} chars "
                f"en {len(context_chunks)} chunks — evaluando con critic"
            )

    # Construir contexto resumido (máx 3000 chars para no explotar tokens)
    ctx_parts = []
    total_len = 0
    for chunk in context_chunks:
        text = chunk.get("text", "")
        if total_len + len(text) > 3000:
            remaining = 3000 - total_len
            if remaining > 100:
                ctx_parts.append(text[:remaining] + "…")
            break
        ctx_parts.append(text)
        total_len += len(text)
    context_str = "\n---\n".join(ctx_parts) if ctx_parts else "(sin contexto recuperado)"

    user_msg = (
        f"PREGUNTA:\n{query}\n\n"
        f"CONTEXTO:\n{context_str}\n\n"
        f"BORRADOR (ya limpiado de markdown — listas numeradas y · son formato aceptable):\n{draft_answer}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_critic_model,
                    "messages": [
                        {"role": "system", "content": CRITIC_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.0,
                    "top_p": 0.9,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

        # Parsear JSON — el modelo puede meter texto antes/después
        result = _parse_verdict(raw)
        logger.info(
            f"[Critic] Veredicto: {result['verdict']}"
            + (f" — {result.get('reasons', [])}" if result["verdict"] == "BLOCK" else "")
        )
        return result

    except Exception as e:
        logger.error(f"[Critic] Error evaluando respuesta: {e}")
        # Si el critic falla, dejamos pasar (fail-open)
        return {"verdict": "PASS"}


def _parse_verdict(raw: str) -> dict:
    """Parsea la respuesta del critic a JSON, tolerando ruido alrededor."""
    # Intentar parsear directamente
    try:
        result = json.loads(raw)
        if "verdict" in result:
            return result
    except json.JSONDecodeError:
        pass

    # Buscar JSON embebido en texto
    import re
    match = re.search(r'\{[^}]*"verdict"\s*:\s*"(PASS|BLOCK)"[^}]*\}', raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Si no podemos parsear, extraer veredicto manualmente
    upper = raw.upper()
    if "BLOCK" in upper:
        return {"verdict": "BLOCK", "reasons": ["critic no parseable pero indicó BLOCK"], "tags": ["formato"]}
    
    # Default: PASS
    return {"verdict": "PASS"}


# ── Critic técnico (Fase 2) ──────────────────────────────

TECHNICAL_CRITIC_SYSTEM = (
    "Eres un evaluador de fidelidad factual para Seedy, un asistente de ganadería y agricultura "
    "FINE-TUNED con conocimiento propio del dominio.\n\n"
    "El modelo principal (Seedy 14B) está entrenado específicamente en ganadería, avicultura, "
    "IoT agrícola y genética animal. TIENE conocimiento propio legítimo que puede NO estar "
    "en la evidencia recuperada. Esto es NORMAL y CORRECTO.\n\n"
    "SOLO BLOQUEAR si detectas ALGUNO de estos errores CLAROS Y EVIDENTES:\n"
    "1. CONTRADICCIÓN DIRECTA: La respuesta afirma algo que la evidencia CONTRADICE explícitamente. "
    "Ejemplo: evidencia dice 'Prat pesa 3.5 kg' y la respuesta dice 'Prat pesa 8 kg'.\n"
    "2. CONFUSIÓN DE ESPECIE: La respuesta mezcla datos de una especie animal con otra "
    "(ej: atribuir peso de cerdo a una gallina, o listar razas bovinas como porcinas).\n"
    "3. ATRIBUCIÓN FALSA DIRECTA: La respuesta dice 'según las fuentes' o 'el contexto indica' "
    "para un hecho específico que la evidencia CONTRADICE (no que simplemente no menciona).\n\n"
    "NO BLOQUEAR por:\n"
    "- Hechos que NO están en la evidencia pero son plausibles en el dominio\n"
    "- Conocimiento técnico del modelo (razas, pesos típicos, protocolos)\n"
    "- Inferencias razonables basadas en la evidencia\n"
    "- Respuestas parciales o que admiten no tener toda la información\n"
    "- Datos técnicos específicos del dominio (Capon Score, EPDs, protocolos MQTT)\n"
    "- Diferencias de estilo o formato\n\n"
    "RECUERDA: El modelo principal es EXPERTO en su dominio. Si da un dato técnico "
    "que no aparece en la evidencia pero es plausible, eso es conocimiento propio, NO invención.\n\n"
    "EN CASO DE DUDA → PASS. SIEMPRE PASS. Solo bloquea ante contradicciones OBJETIVAS.\n\n"
    "Responde SOLO JSON:\n"
    '{"verdict": "PASS"}\n'
    "o\n"
    '{"verdict": "BLOCK", "reasons": ["motivo concreto"], "tags": ["etiqueta"]}\n\n'
    "Tags válidos: contradiccion, especie_confusa, atribucion_falsa."
)


async def evaluate_technical(
    query: str,
    evidence: str,
    draft_answer: str,
    species_hint: str | None = None,
) -> dict:
    """
    Evalúa fidelidad factual de la respuesta contra la evidencia.
    Complementario al critic estructural.

    Returns:
        {"verdict": "PASS"} o {"verdict": "BLOCK", "reasons": [...], "tags": [...]}
    """
    settings = get_settings()

    if not settings.together_api_key:
        return {"verdict": "PASS"}

    # Skip si no hay evidencia o respuesta es muy corta (saludo, etc.)
    if not evidence or len(draft_answer) < 50:
        return {"verdict": "PASS"}

    # Pre-filtro: admisiones honestas no necesitan verificación factual
    answer_lower = draft_answer.lower()
    for phrase in _honest_phrases:
        if phrase in answer_lower:
            return {"verdict": "PASS"}

    # Truncar evidencia si es muy larga
    ev_truncated = evidence[:4000] if len(evidence) > 4000 else evidence

    species_note = f"\nNOTA: La pregunta es sobre especie {species_hint}." if species_hint else ""

    user_msg = (
        f"PREGUNTA:\n{query}{species_note}\n\n"
        f"EVIDENCIA DISPONIBLE:\n{ev_truncated}\n\n"
        f"RESPUESTA A EVALUAR:\n{draft_answer}"
    )

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                f"{settings.together_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.together_api_key}"},
                json={
                    "model": settings.together_critic_model,  # Qwen3-235B
                    "messages": [
                        {"role": "system", "content": TECHNICAL_CRITIC_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.0,
                    "top_p": 0.9,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

        result = _parse_verdict(raw)
        logger.info(
            f"[CriticTech] Veredicto: {result['verdict']}"
            + (f" — {result.get('reasons', [])}" if result["verdict"] == "BLOCK" else "")
        )
        return result

    except Exception as e:
        logger.error(f"[CriticTech] Error: {e}")
        return {"verdict": "PASS"}  # Fail-open
