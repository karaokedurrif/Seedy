"""Seedy Backend — Query rewriter para mejorar retrieval RAG.

Reformula la query del usuario incorporando contexto conversacional
para que la búsqueda vectorial sea más precisa.
Ejemplo:
  Historial: "háblame de la Sulmtaler" → asistente responde sobre Sulmtaler
  Query: "y cómo la ves para capón gourmet?"
  Reescrita: "Sulmtaler gallina para capón gourmet cruces"
"""

import logging
import re

from services.llm_router import llm_router, POLICIES, LLMRequest

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


def _smart_truncate_for_context(content: str, query: str, max_chars: int = 500) -> str:
    """
    Trunca inteligentemente el contenido preservando información relevante para la query.
    
    Si la query menciona "punto N" o "medida N", busca ese punto en el contenido
    y lo incluye en el truncado.
    
    Args:
        content: Contenido del mensaje a truncar
        query: Query del usuario (para detectar referencias)
        max_chars: Máximo de caracteres si no hay match específico
        
    Returns:
        Contenido truncado inteligentemente
    """
    # Detectar si la query menciona un punto/medida/paso específico
    match = re.search(r'punto\s+(\d+)|medida\s+(\d+)|paso\s+(\d+)|opción\s+(\d+)', query.lower())
    
    if match:
        # Extraer el número mencionado
        numero = match.group(1) or match.group(2) or match.group(3) or match.group(4)
        
        # Buscar ese punto en el contenido
        # Patrones: "9. Texto", "9) Texto", "punto 9: Texto", etc.
        patterns = [
            rf'{numero}\.\s+([^\n]+)',
            rf'{numero}\)\s+([^\n]+)',
            rf'punto\s+{numero}[:\s]+([^\n]+)',
            rf'medida\s+{numero}[:\s]+([^\n]+)',
        ]
        
        for pattern in patterns:
            punto_match = re.search(pattern, content, re.IGNORECASE)
            if punto_match:
                # Encontrado - construir contexto: inicio + punto específico + algo después
                inicio = content[:150]  # Primeros 150 chars (contexto general)
                
                # Extraer contexto alrededor del punto (100 chars antes, 250 después)
                start_pos = max(0, punto_match.start() - 100)
                end_pos = min(len(content), punto_match.end() + 250)
                contexto_punto = content[start_pos:end_pos]
                
                resultado = f"{inicio}...\n\n[Contexto relevante]\n{contexto_punto}"
                logger.info(f"[Rewriter] Smart truncate: detectado '{numero}' en query, incluido en contexto")
                return resultado
    
    # Sin match o sin punto específico: truncado normal ampliado
    return content[:max_chars]


async def rewrite_query(query: str, history: list[dict] | None = None) -> str:
    """
    Reformula la query usando historial conversacional.
    Usa Ollama qwen2.5:7b (primario) con fallback automático a Together.ai.
    Fallback: devuelve query original si todo falla.
    """
    # Sin historial o historial corto: no reformular
    if not history or len(history) < 2:
        return query

    # Construir contexto conversacional (últimos 4 mensajes máximo)
    conv_context = ""
    recent = history[-4:]
    for msg in recent:
        role = "Usuario" if msg["role"] == "user" else "Asistente"
        # Smart truncate: preserva puntos mencionados en la query
        content = _smart_truncate_for_context(msg["content"], query, max_chars=500)
        conv_context += f"{role}: {content}\n"

    user_prompt = (
        f"Conversación previa:\n{conv_context}\n"
        f"Última pregunta del usuario: {query}\n\n"
        f"Consulta de búsqueda optimizada:"
    )

    try:
        result = await llm_router.call_with_policy(
            policy=POLICIES["rewriter"],
            request=LLMRequest(
                messages=[
                    {"role": "system", "content": REWRITER_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=50,  # Aumentado de 40 a 50 para queries más complejas
                temperature=0.0,
            ),
        )
        
        rewritten = result.content.strip()

        # Sanitizar: quitar comillas y prefijos
        # Usar caracteres literales para evitar problemas de escape
        rewritten = rewritten.strip('"' + "'")
        if rewritten.lower().startswith("consulta"):
            rewritten = rewritten.split(":", 1)[-1].strip()

        # Si la reescritura es vacía o muy corta, usar original
        if len(rewritten) < 3:
            return query

        logger.info(
            f"Query reescrita via {result.provider}: '{query[:50]}' → '{rewritten[:60]}' "
            f"(latency: {result.total_latency_s:.2f}s, cost: ${result.cost:.6f})"
        )
        return rewritten

    except Exception as e:
        logger.warning(f"Error en query rewriting: {e}. Usando query original.")
        return query
