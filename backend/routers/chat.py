"""Seedy Backend — Router /chat (endpoint principal).

v15+: Multi-label classification + query rewriter + dual-query RAG.
"""

import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest, ChatResponse, Source
from models.prompts import CATEGORY_COLLECTIONS, get_system_prompt
from services.classifier import classify_query_multi
from services.rag import search as rag_search
from services.reranker import rerank
from services.llm import generate, generate_stream
from services.query_rewriter import rewrite_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _merge_collections(categories: list[tuple[str, float]]) -> tuple[list[str], str]:
    """
    Dado un listado multi-label [(cat, peso), ...], fusiona las colecciones
    de todas las categorías (sin duplicados, preservando orden de prioridad).
    Devuelve (colecciones, categoría_principal).
    """
    seen: set[str] = set()
    merged: list[str] = []
    primary_cat = categories[0][0] if categories else "GENERAL"

    for cat, _weight in categories:
        for coll in CATEGORY_COLLECTIONS.get(cat, CATEGORY_COLLECTIONS["GENERAL"]):
            if coll not in seen:
                seen.add(coll)
                merged.append(coll)

    return merged, primary_cat


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Endpoint principal de Seedy.
    
    Flujo v15+:
    1. Clasificar query → multi-label (hasta 3 categorías con peso)
    2. Fusionar colecciones de todas las categorías
    3. Reescribir query con contexto conversacional (si hay historial)
    4. Buscar en Qdrant con dual-query (reescrita + original)
    5. Rerank → Top N diversificado
    6. Construir prompt con contexto según categoría principal
    7. Generar respuesta (Together.ai / Ollama fallback)
    """
    t0 = time.time()

    try:
        # 1. Clasificar (multi-label)
        history_dicts = [{"role": m.role, "content": m.content} for m in req.history] if req.history else None
        prev_cat = None
        if history_dicts and len(history_dicts) >= 2:
            # Extraer categoría previa del último turno del asistente (si existe)
            prev_cat = None  # Se podría pasar desde el frontend en el futuro

        categories = await classify_query_multi(req.query, prev_cat)
        collections, primary_cat = _merge_collections(categories)
        logger.info(
            f"Categorías: {categories} | Colecciones: {collections} | Query: {req.query[:80]}..."
        )

        # 2. Reescribir query (si hay historial conversacional)
        rewritten_query = await rewrite_query(req.query, history_dicts)
        use_dual = rewritten_query != req.query

        # 3. Buscar en Qdrant (dual-query si se reescribió)
        rag_results = await rag_search(
            query=rewritten_query,
            collections=collections,
            alt_query=req.query if use_dual else None,
            category=primary_cat,
        )
        logger.info(f"RAG: {len(rag_results)} resultados de {collections}")

        # 4. Rerank
        top_chunks = rerank(req.query, rag_results) if rag_results else []
        logger.info(f"Rerank: {len(top_chunks)} chunks seleccionados")

        # 5. System prompt según categoría principal
        system_prompt = get_system_prompt(primary_cat)

        # 6. Generar respuesta
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
                text=c.get("text", "")[:200],
            )
            for c in top_chunks
        ]

        elapsed = time.time() - t0
        logger.info(f"Respuesta generada en {elapsed:.2f}s vía {model_used}")

        return ChatResponse(
            answer=answer,
            category=primary_cat,
            sources=sources,
            model_used=model_used,
        )

    except Exception as e:
        logger.exception(f"Error en /chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Endpoint SSE streaming de Seedy.

    Flujo v15+ idéntico a /chat pero con streaming.
    Eventos:
      - metadata  → {step, category, categories, sources, ...}
      - token     → {content}
      - done      → {category, model_used, elapsed, sources}
      - error     → {error}
    """

    async def event_generator():
        t0 = time.time()

        try:
            # 1. Clasificar (multi-label)
            history_dicts = (
                [{"role": m.role, "content": m.content} for m in req.history]
                if req.history
                else None
            )
            categories = await classify_query_multi(req.query)
            collections, primary_cat = _merge_collections(categories)

            yield (
                f"event: metadata\n"
                f"data: {json.dumps({'step': 'classified', 'category': primary_cat, 'categories': [[c, w] for c, w in categories]})}\n\n"
            )

            # 2. Reescribir query
            rewritten_query = await rewrite_query(req.query, history_dicts)
            use_dual = rewritten_query != req.query

            # 3. RAG search (dual-query)
            rag_results = await rag_search(
                query=rewritten_query,
                collections=collections,
                alt_query=req.query if use_dual else None,
                category=primary_cat,
            )

            # 4. Rerank
            top_chunks = rerank(req.query, rag_results) if rag_results else []

            sources = [
                {
                    "file": c.get("file", ""),
                    "collection": c.get("collection", ""),
                    "chunk_index": c.get("chunk_index", 0),
                    "score": round(c.get("rerank_score", c.get("score", 0.0)), 4),
                    "text": c.get("text", "")[:200],
                }
                for c in top_chunks
            ]

            yield (
                f"event: metadata\n"
                f"data: {json.dumps({'step': 'context_ready', 'num_chunks': len(top_chunks), 'sources': sources})}\n\n"
            )

            # 5. Stream LLM
            system_prompt = get_system_prompt(primary_cat)
            model_used = "none"

            history = None
            if hasattr(req, "history") and req.history:
                history = [{"role": m.role, "content": m.content} for m in req.history]

            async for token, model in generate_stream(
                system_prompt=system_prompt,
                user_message=req.query,
                context_chunks=top_chunks,
                history=history,
            ):
                model_used = model
                yield f"event: token\ndata: {json.dumps({'content': token})}\n\n"

            elapsed = time.time() - t0
            yield (
                f"event: done\n"
                f"data: {json.dumps({'category': primary_cat, 'model_used': model_used, 'elapsed': round(elapsed, 2), 'sources': sources})}\n\n"
            )

        except Exception as e:
            logger.exception(f"Error en /chat/stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
