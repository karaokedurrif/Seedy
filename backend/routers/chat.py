"""Seedy Backend — Router /chat (endpoint principal)."""

import logging
import time

from fastapi import APIRouter, HTTPException

from models.schemas import ChatRequest, ChatResponse, Source
from models.prompts import CATEGORY_COLLECTIONS, get_system_prompt
from services.classifier import classify_query
from services.rag import search as rag_search
from services.reranker import rerank
from services.llm import generate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Endpoint principal de Seedy.
    
    Flujo:
    1. Clasificar query → categoría
    2. Buscar en Qdrant (Top K=8, búsqueda híbrida)
    3. Rerank → Top 3
    4. Construir prompt con contexto
    5. Generar respuesta (Together.ai / Ollama fallback)
    """
    t0 = time.time()

    try:
        # 1. Clasificar
        category = await classify_query(req.query)
        logger.info(f"Categoría: {category} | Query: {req.query[:80]}...")

        # 2. Determinar colecciones y buscar
        collections = CATEGORY_COLLECTIONS.get(category, CATEGORY_COLLECTIONS["GENERAL"])
        rag_results = await rag_search(req.query, collections)
        logger.info(f"RAG: {len(rag_results)} resultados de {collections}")

        # 3. Rerank
        top_chunks = rerank(req.query, rag_results) if rag_results else []
        logger.info(f"Rerank: {len(top_chunks)} chunks seleccionados")

        # 4. System prompt según categoría
        system_prompt = get_system_prompt(category)

        # 5. Generar respuesta
        answer, model_used = await generate(
            system_prompt=system_prompt,
            user_message=req.query,
            context_chunks=top_chunks,
        )

        # Construir sources
        sources = [
            Source(
                file=c.get("file", ""),
                collection=c.get("collection", ""),
                chunk_index=c.get("chunk_index", 0),
                score=c.get("rerank_score", c.get("score", 0.0)),
                text=c.get("text", "")[:200],  # Truncar para la respuesta
            )
            for c in top_chunks
        ]

        elapsed = time.time() - t0
        logger.info(f"Respuesta generada en {elapsed:.2f}s vía {model_used}")

        return ChatResponse(
            answer=answer,
            category=category,
            sources=sources,
            model_used=model_used,
        )

    except Exception as e:
        logger.exception(f"Error en /chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
