"""Seedy Backend — Query rewriter para mejorar retrieval RAG.

Reformula la query del usuario incorporando contexto conversacional
para que la búsqueda vectorial sea más precisa.
Ejemplo:
  Historial: "háblame de la Sulmtaler" → asistente responde sobre Sulmtaler
  Query: "y cómo la ves para capón gourmet?"
  Reescrita: "Sulmtaler gallina para capón gourmet cruces"
"""

import logging

from config import get_settings
from services.together_client import get_together_client

logger = logging.getLogger(__name__)

REWRITER_PROMPT = (
    "Eres un reformulador de consultas para un sistema RAG de avicultura y ganadería. "
    "Dada la conversación previa y la última pregunta del usuario, genera UNA SOLA "
    "consulta de búsqueda optimizada para recuperar documentos relevantes.\n\n"
    "Reglas:\n"
    "- Incorpora el tema/raza/especie del historial si la pregunta es una continuación\n"
    "- Corrige posibles errores ortográficos en nombres de razas "
    "(ej: 'sulmtahler'→'Sulmtaler', 'coucou de renes'→'Coucou de Rennes')\n"
    "- Mantén la consulta en el idioma original del usuario\n"
    "- La consulta debe ser concisa (máximo 15 palabras), sin explicaciones\n"
    "- Si no hay historial relevante, devuelve la pregunta original limpia\n"
    "- Responde SOLO con la consulta reformulada, sin comillas ni explicación"
)


async def rewrite_query(query: str, history: list[dict] | None = None) -> str:
    """
    Reformula la query usando historial conversacional.
    Usa Together.ai (rápido, ~10 tokens) para reformular.
    Fallback: devuelve query original si falla.
    """
    # Sin historial o historial corto: no reformular
    if not history or len(history) < 2:
        return query

    settings = get_settings()

    if not settings.together_api_key:
        return query

    # Construir contexto conversacional (últimos 4 mensajes máximo)
    conv_context = ""
    recent = history[-4:]
    for msg in recent:
        role = "Usuario" if msg["role"] == "user" else "Asistente"
        content = msg["content"][:200]  # Truncar para no gastar tokens
        conv_context += f"{role}: {content}\n"

    user_prompt = (
        f"Conversación previa:\n{conv_context}\n"
        f"Última pregunta del usuario: {query}\n\n"
        f"Consulta de búsqueda optimizada:"
    )

    try:
        client = await get_together_client()
        resp = await client.post(
            f"{settings.together_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.together_api_key}"},
            json={
                "model": settings.together_classifier_model,
                "messages": [
                    {"role": "system", "content": REWRITER_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 40,
                "temperature": 0,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        rewritten = data["choices"][0]["message"]["content"].strip()

        # Sanitizar: quitar comillas y prefijos
        rewritten = rewritten.strip('"\'')
        if rewritten.lower().startswith("consulta"):
            rewritten = rewritten.split(":", 1)[-1].strip()

        # Si la reescritura es vacía o muy corta, usar original
        if len(rewritten) < 3:
            return query

        logger.info(f"Query reescrita: '{query[:50]}' → '{rewritten[:50]}'")
        return rewritten

    except Exception as e:
        logger.warning(f"Error en query rewriting: {e}. Usando query original.")
        return query
