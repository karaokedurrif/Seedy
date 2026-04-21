"""Seedy Backend — Router /chat (endpoint principal).

v15+: Multi-label classification + query rewriter + dual-query RAG.
"""

import json
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest, ChatResponse, Source
from models.prompts import CATEGORY_COLLECTIONS, get_system_prompt
from services.classifier import classify_query_multi
from services.rag import search as rag_search
from services.reranker import rerank
from services.llm import generate, generate_stream
from services.query_rewriter import rewrite_query

try:
    from runtime.logger import log_agent_run, RunTimer
except ImportError:
    log_agent_run = None
    RunTimer = None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_LIVE_KEYWORDS = {"gallinero", "palacio", "montas", "monta", "comportamiento", "aves", "comportamientos", "jerarquía", "jerarquia", "anomalía", "anomalia", "conducta"}


async def _get_live_behavior_chunk(gallinero_id: str = "gallinero_palacio") -> dict | None:
    """
    Llama a las APIs de comportamiento y mating en tiempo real y devuelve un chunk
    con los datos actuales para inyectar en el contexto RAG.
    """
    base = "http://localhost:8000"
    parts: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Comportamiento general / ML
            r_beh = await client.get(f"{base}/behavior/ml/anomalies/{gallinero_id}?hours=24")
            if r_beh.status_code == 200:
                data = r_beh.json()
                n = len(data.get("anomalies", []))
                parts.append(f"ANOMALIAS ULTIMAS 24H: {n} detectadas.")
                for a in data.get("anomalies", [])[:5]:
                    parts.append(f"  - Ave {a.get('bird_id','?')}: {a.get('description','')}")

            # Jerarquía / PageRank
            r_hier = await client.get(f"{base}/behavior/ml/hierarchy/{gallinero_id}")
            if r_hier.status_code == 200:
                hier = r_hier.json().get("hierarchy", [])
                if hier:
                    top3 = hier[:3]
                    parts.append("JERARQUIA (PageRank dominancia):")
                    for h in top3:
                        parts.append(f"  - {h.get('bird_id','?')} (score {h.get('score',0):.2f})")

            # Montas últimos 7 días
            r_mat = await client.get(f"{base}/behavior/mating/summary?gallinero_id={gallinero_id}&days=7")
            if r_mat.status_code == 200:
                mat = r_mat.json()
                total = mat.get("total_events", 0)
                pairs = mat.get("pairs", [])
                parts.append(f"MONTAS ULTIMOS 7 DIAS: {total} eventos registrados.")
                for p in pairs[:5]:
                    mounter = p.get("mounter_breed") or p.get("mounter_id", "?")
                    mounted = p.get("mounted_breed") or p.get("mounted_id", "?")
                    count = p.get("count", 0)
                    parts.append(f"  - {mounter} sobre {mounted}: {count} veces")

            # Tracks live (identidades activas)
            r_tracks = await client.get(f"{base}/vision/identify/tracks/live?gallinero_id={gallinero_id}")
            if r_tracks.status_code == 200:
                tracks = r_tracks.json()
                locked = [t for t in tracks if t.get("identity_locked")]
                parts.append(f"AVES IDENTIFICADAS ACTIVAS: {len(locked)} con identidad confirmada.")

    except Exception as e:
        logger.warning(f"Live behavior chunk error: {e}")

    if not parts:
        return None

    return {
        "file": "live_behavior_api",
        "collection": "live",
        "chunk_index": 0,
        "score": 1.0,
        "rerank_score": 1.0,
        "text": f"[DATOS EN TIEMPO REAL — {gallinero_id.upper()}]\n" + "\n".join(parts),
    }


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

        # 4b. Inyectar datos live si la query es sobre comportamiento/gallinero
        query_lower = req.query.lower()
        if primary_cat in ("COMPORTAMIENTO", "AVICULTURA") or any(kw in query_lower for kw in _LIVE_KEYWORDS):
            live_chunk = await _get_live_behavior_chunk()
            if live_chunk:
                top_chunks = [live_chunk] + top_chunks
                logger.info("Chunk live de comportamiento inyectado en contexto")

        # 5. System prompt según categoría principal
        system_prompt = get_system_prompt(primary_cat)

        # 6. Generar respuesta
        answer, model_used = await generate(
            system_prompt=system_prompt,
            user_message=req.query,
            context_chunks=top_chunks,
            max_tokens=4096,
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

        if log_agent_run:
            log_agent_run(
                task_type="rag",
                expert_used="expert_rag",
                model_used=model_used,
                tools_invoked=["rag_query"],
                input_summary=req.query[:200],
                output_summary=answer[:200],
                latency_ms=int(elapsed * 1000),
                confidence=top_chunks[0].get("rerank_score", 0.0) if top_chunks else 0.0,
                tenant_id=req.farm_id or "palacio",
            )

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

            # 4b. Inyectar datos live si la query es sobre comportamiento/gallinero
            query_lower = req.query.lower()
            if primary_cat in ("COMPORTAMIENTO", "AVICULTURA") or any(kw in query_lower for kw in _LIVE_KEYWORDS):
                live_chunk = await _get_live_behavior_chunk()
                if live_chunk:
                    top_chunks = [live_chunk] + top_chunks

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
                max_tokens=4096,
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
