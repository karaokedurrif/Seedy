"""
Seedy Backend — Router OpenAI-compatible /v1/chat/completions.

Permite que Open WebUI use el backend como si fuera un modelo OpenAI.
Flujo automático: Classify → Qdrant RAG → SearXNG (si RAG insuficiente) → Rerank → LLM.
Modelo seedy-vision: detecta imágenes → Gemini 2.0 Flash (análisis visual).
"""

import base64
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from models.prompts import CATEGORY_COLLECTIONS, get_system_prompt
from services.classifier import classify_query, classify_query_multi
from services.query_rewriter import rewrite_query
from services.rag import search as rag_search, FRESH_WEB_COLLECTION
from services.reranker import rerank
from services.llm import generate, generate_stream
from services.web_search import search_web, format_web_results, should_search_web, needs_product_search
from services.url_fetcher import fetch_urls_from_query
from services.critic import evaluate_response, BLOCKED_FALLBACK
from services.critic import evaluate_technical
from services.critic_log import log_critic_result
from services.evidence import extract_evidence, build_evidence_context
from services.metadata_filter import get_species_hint
from services.gemini_vision import analyze_image as gemini_analyze, get_dataset_stats
from services.temporality import classify_temporality, needs_web_augmentation
from services.postprocess import clean_markdown

# Patrón para detectar queries malformadas que OWUI envía como prefill
_JUNK_QUERY_RE = re.compile(
    r"^(###\s*Task|\[\")|^\s*$",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["openai-compat"])


# ── Schemas OpenAI-compatible ────────────────────────

class OAIMessage(BaseModel):
    role: str
    content: str | list[Any] = ""


class OAIChatRequest(BaseModel):
    model: str = "seedy"
    messages: list[OAIMessage] = Field(default_factory=list)
    temperature: float = 0.3
    max_tokens: int | None = None
    stream: bool = False
    # Ignorar campos OpenAI que no usamos
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | None = None
    n: int = 1


class OAIModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 1700000000
    owned_by: str = "neofarm"


# ── /v1/models ───────────────────────────────────────

@router.get("/models")
async def list_models():
    """Lista modelos disponibles (formato OpenAI)."""
    vision_stats = get_dataset_stats()
    return {
        "object": "list",
        "data": [
            {
                "id": "seedy",
                "object": "model",
                "created": 1700000000,
                "owned_by": "neofarm",
            },
            {
                "id": "seedy-turbo",
                "object": "model",
                "created": 1700000000,
                "owned_by": "neofarm",
            },
            {
                "id": "seedy-vision",
                "object": "model",
                "created": 1700000000,
                "owned_by": "neofarm",
                "meta": {
                    "description": f"Gemini 2.0 Flash Vision — {vision_stats['records']} training pairs",
                },
            },
        ],
    }


# ── Pipeline RAG unificado ───────────────────────────

# Modelos de visión (ruteados a Gemini)
_VISION_MODELS = {"seedy-vision"}


def _extract_multimodal(content: str | list) -> tuple[str, str | None, str]:
    """
    Extrae texto e imagen de un content multimodal OpenAI.

    Returns: (text_query, image_b64_or_None, mime_type)
    """
    if isinstance(content, str):
        return content, None, "image/jpeg"

    text_parts: list[str] = []
    image_b64 = None
    mime_type = "image/jpeg"

    for part in content:
        if isinstance(part, dict):
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                # data:image/jpeg;base64,/9j/4AAQ...
                if url.startswith("data:"):
                    header, _, b64data = url.partition(",")
                    # Extraer MIME: data:image/webp;base64
                    mime_type = header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg"
                    image_b64 = b64data
                # URL externa — descargar en el servicio
                else:
                    image_b64 = url  # marcador: se descarga luego

    return " ".join(text_parts).strip() or "Identifica este animal", image_b64, mime_type


def _has_images(messages: list[OAIMessage]) -> bool:
    """¿Algún mensaje contiene imágenes?"""
    for msg in messages:
        if isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _content_to_str(content: str | list) -> str:
    """Convierte content (str o list multimodal) a texto plano."""
    if isinstance(content, str):
        return content
    return " ".join(
        p.get("text", "") for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()


# Almacén simple de categoría previa por sesión (para coherencia multi-turno)
_last_category: str | None = None


async def _rag_pipeline(query: str, history: list[dict] | None = None):
    """
    Pipeline completo: URL crawl → rewrite → classify → RAG → web search → rerank.
    Returns: (system_prompt, top_chunks, category, web_context)
    """
    global _last_category

    # 0a. Detectar y crawlear URLs mencionadas en la query
    url_chunks = await fetch_urls_from_query(query)
    if url_chunks:
        logger.info(f"[OpenAI] {len(url_chunks)} URL(s) crawleadas del query")

    # 0b. Reescribir query con contexto conversacional
    search_query = await rewrite_query(query, history)
    if search_query != query:
        logger.info(f"[OpenAI] Query reescrita: {search_query[:80]}")

    # 1. Clasificar categoría + temporalidad (multi-label para mejor recall)
    #    + hint de categoría previa para coherencia conversacional
    prev_cat = _last_category if (history and len(history) >= 2) else None
    classify_input = search_query if search_query != query else query
    multi_cats = await classify_query_multi(classify_input, prev_category=prev_cat)
    category = multi_cats[0][0] if multi_cats else "GENERAL"
    temporality = await classify_temporality(query)
    _last_category = category
    logger.info(f"[OpenAI] Categorías: {multi_cats} (prev={prev_cat}) | "
                f"Temporalidad: {temporality} | Query: {query[:80]}...")

    # 2. RAG search en Qdrant — dual query para mejor recall
    #    search_query = reescrita (más tokens útiles para BM25 + semántica expandida)
    #    alt_query = query original (sin sesgo del rewriter, captura intención directa)
    #    Multi-label: unir colecciones de todas las categorías con peso >= 0.3
    collections_set: set[str] = set()
    for cat, weight in multi_cats:
        for col in CATEGORY_COLLECTIONS.get(cat, CATEGORY_COLLECTIONS["GENERAL"]):
            collections_set.add(col)
    collections = list(collections_set)
    # Para queries dinámicas/breaking, añadir fresh_web al retrieval
    if needs_web_augmentation(temporality) and FRESH_WEB_COLLECTION not in collections:
        collections.append(FRESH_WEB_COLLECTION)
    alt_q = query if search_query != query else None
    rag_results = await rag_search(search_query, collections, alt_query=alt_q, category=category)
    logger.info(f"[OpenAI] RAG: {len(rag_results)} resultados de {collections}"
                f"{' (dual-query)' if alt_q else ''}")

    # 3. Búsqueda web: por insuficiencia RAG, temporalidad dinámica, o intención comercial/producto
    web_context = ""
    force_web = needs_web_augmentation(temporality)
    force_product = needs_product_search(query)
    if should_search_web(rag_results) or force_web or force_product:
        if force_product:
            reason = "intención comercial/producto"
        elif force_web:
            reason = "temporalidad " + temporality
        else:
            reason = "RAG insuficiente"
        logger.info(f"[OpenAI] {reason} → buscando en SearXNG...")
        web_results = await search_web(query, product_mode=force_product)
        web_context = format_web_results(web_results)
        if web_context:
            logger.info(f"[OpenAI] SearXNG: {len(web_results)} resultados web añadidos")

    # 4. Rerank
    top_chunks = rerank(query, rag_results) if rag_results else []
    logger.info(f"[OpenAI] Rerank: {len(top_chunks)} chunks seleccionados")

    # 5. Si hay contexto web, añadirlo como chunks adicionales
    if web_context:
        product_guard = ""
        if force_product:
            product_guard = (
                "[INSTRUCCION CRITICA: El usuario pregunta por productos, precios o recomendaciones de compra. "
                "Usa UNICAMENTE la informacion de estos resultados web. NO inventes productos, marcas, "
                "precios, tiendas ni URLs que no aparezcan aqui. Si la informacion es insuficiente, "
                "dilo claramente y sugiere al usuario buscar en tiendas especializadas.]\n\n"
            )
        top_chunks.append({
            "text": f"{product_guard}[Resultados de búsqueda web]\n{web_context}",
            "file": "searxng_web",
            "collection": "web",
            "chunk_index": 0,
            "rerank_score": 0.5,
        })
    elif force_product:
        # No hay resultados web pero es query de producto → guardia anti-alucinación
        top_chunks.append({
            "text": (
                "[INSTRUCCION CRITICA: El usuario pregunta por productos, precios o recomendaciones de compra, "
                "pero NO se encontraron resultados web. NO inventes productos, marcas, precios ni tiendas. "
                "Informa al usuario de que no has podido obtener datos actualizados de productos y "
                "sugierele buscar en tiendas especializadas de avicultura o agricultura.]"
            ),
            "file": "product_guard",
            "collection": "web",
            "chunk_index": 0,
            "rerank_score": 0.6,
        })

    # 5b. Añadir contenido de URLs crawleadas (prioridad alta)
    if url_chunks:
        top_chunks = url_chunks + top_chunks

    # 6. System prompt según categoría
    system_prompt = get_system_prompt(category)

    return system_prompt, top_chunks, category, web_context


# ── /v1/chat/completions ─────────────────────────────

@router.post("/chat/completions")
async def chat_completions(req: OAIChatRequest):
    """
    Endpoint OpenAI-compatible.
    Open WebUI lo llama como si fuera un modelo OpenAI.
    - seedy / seedy-turbo: classify → Qdrant RAG → SearXNG → rerank → Ollama.
    - seedy-vision (o imágenes detectadas): Gemini 2.0 Flash.
    """
    t0 = time.time()

    # ── Detectar si es request de visión ──
    is_vision = req.model in _VISION_MODELS or _has_images(req.messages)

    if is_vision:
        return await _vision_response(req, t0)

    # ── Flujo RAG normal ──
    # Extraer query (último mensaje user) e historial
    query = ""
    history = []
    system_override = None

    for msg in req.messages:
        if msg.role == "user":
            query = _content_to_str(msg.content)
        elif msg.role == "assistant":
            history.append({"role": "assistant", "content": _content_to_str(msg.content)})
        elif msg.role == "system":
            system_override = _content_to_str(msg.content)

    if not query:
        return _error_response("No user message found")

    # Filtrar queries malformadas (OWUI a veces envía "### Task:" como prefill)
    if _JUNK_QUERY_RE.search(query):
        logger.warning(f"[OpenAI] Query malformada filtrada: {query[:60]}")
        return _error_response("Malformed query filtered")

    # Historial: todo excepto el último user y el system
    user_messages = [m for m in req.messages if m.role == "user"]
    if len(user_messages) > 1:
        # Multi-turn: incluir todos los mensajes previos como historial
        history = []
        for msg in req.messages[:-1]:  # Todos menos el último
            if msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": _content_to_str(msg.content)})

    if req.stream:
        return StreamingResponse(
            _stream_response(query, history, req, t0),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    else:
        return await _non_stream_response(query, history, req, t0)


# ── Flujo Vision (Gemini 2.0 Flash) ─────────────────

async def _vision_response(req: OAIChatRequest, t0: float):
    """
    Rutea imágenes a Gemini 2.0 Flash.
    Soporta streaming y non-streaming.
    """
    # Extraer imagen y texto del último mensaje user
    last_user = None
    for msg in reversed(req.messages):
        if msg.role == "user":
            last_user = msg
            break

    if not last_user:
        return _error_response("No user message found for vision")

    question, image_b64, mime_type = _extract_multimodal(last_user.content)

    if not image_b64:
        # Modelo vision pero sin imagen — responder indicando que se necesita imagen
        logger.warning("[Vision] Request a seedy-vision sin imagen adjunta")
        answer = ("Soy el modelo de visión de Seedy. "
                  "Para identificar animales, adjunta una foto y pregúntame. "
                  "Puedo identificar razas de aves, porcino y vacuno.")
        return _oai_response(answer, req.model, t0)

    try:
        # Si image_b64 es una URL (no data:), descargar
        if image_b64.startswith("http"):
            from services.gemini_vision import analyze_image_from_url
            result = await analyze_image_from_url(image_b64, question)
        else:
            result = await gemini_analyze(image_b64, question, mime_type)

        answer = result["answer"]
        elapsed = time.time() - t0
        logger.info(
            f"[Vision] Gemini respondió en {elapsed:.1f}s | "
            f"tokens={result['usage']['total_tokens']} | "
            f"saved={result.get('saved_path', 'no')}"
        )

    except Exception as e:
        logger.error(f"[Vision] Error Gemini: {e}")
        answer = f"Error al analizar la imagen: {e}"

    if req.stream:
        return StreamingResponse(
            _stream_vision_answer(answer, req.model, t0),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    return _oai_response(answer, req.model, t0)


def _oai_response(answer: str, model: str, t0: float):
    """Respuesta no-streaming en formato OpenAI."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(t0),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": len(answer.split()),
            "total_tokens": len(answer.split()),
        },
    }


async def _stream_vision_answer(answer: str, model: str, t0: float):
    """Stream una respuesta vision ya completa token a token."""
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Primer chunk con role
    first = {
        "id": chat_id, "object": "chat.completion.chunk",
        "created": int(t0), "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(first)}\n\n"

    # Emitir por palabras para simular streaming
    words = answer.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else f" {word}"
        chunk = {
            "id": chat_id, "object": "chat.completion.chunk",
            "created": int(t0), "model": model,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    # Chunk final
    done = {
        "id": chat_id, "object": "chat.completion.chunk",
        "created": int(t0), "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done)}\n\n"
    yield "data: [DONE]\n\n"


# ── Respuestas RAG (texto) ──────────────────────────


async def _non_stream_response(query: str, history: list[dict], req: OAIChatRequest, t0: float):
    """Respuesta no-streaming (formato OpenAI). Fase 2: evidence builder + doble critic."""
    system_prompt, top_chunks, category, _ = await _rag_pipeline(query, history)

    # ── Fase 2: Evidence Builder ──
    species_hint = get_species_hint(query)
    evidence_text, filtered_chunks, evidence_extracted = await extract_evidence(query, top_chunks, species_hint)

    max_tokens = req.max_tokens or 1024

    # Construir mensaje con evidencia estructurada (en vez de chunks crudos)
    evidence_context = build_evidence_context(evidence_text, filtered_chunks)
    answer, model_used = await generate(
        system_prompt=system_prompt,
        user_message=query,
        context_chunks=filtered_chunks,  # Chunks para _build_user_message fallback
        history=history if history else None,
        max_tokens=max_tokens,
        temperature=req.temperature,
        evidence_override=evidence_context if evidence_extracted else None,
    )

    # ── Post-procesado: limpiar markdown ──
    answer = clean_markdown(answer)

    # ── Fase 2: Doble Critic ──
    # A) Critic estructural (confusión especie, incoherencia)
    structural_verdict = await evaluate_response(query, filtered_chunks, answer)
    # B) Critic técnico (fidelidad factual)
    technical_verdict = await evaluate_technical(query, evidence_text, answer, species_hint)

    was_blocked = (
        structural_verdict["verdict"] == "BLOCK"
        or technical_verdict["verdict"] == "BLOCK"
    )

    if was_blocked:
        block_source = "structural" if structural_verdict["verdict"] == "BLOCK" else "technical"
        all_reasons = (
            structural_verdict.get("reasons", [])
            + technical_verdict.get("reasons", [])
        )
        logger.warning(
            f"[Critic] BLOQUEADO ({block_source}): {all_reasons} "
            f"tags={structural_verdict.get('tags', []) + technical_verdict.get('tags', [])}"
        )
        logger.info(f"[Critic] Draft bloqueado: {answer[:200]}...")

        # ── Retry con Together.ai (skip Ollama que generó el error) ──
        correction_hint = (
            "\n\nAVISO INTERNO — CORRECCIÓN OBLIGATORIA:\n"
            "Un borrador anterior fue rechazado por el control de calidad por estos motivos:\n"
            + "\n".join(f"• {r}" for r in all_reasons)
            + "\nGenera una respuesta nueva que evite estos errores. "
            "Sé preciso con la terminología y no confundas conceptos. "
            "Si el contexto RAG no es relevante para la pregunta, responde "
            "usando tu conocimiento general como experto."
        )
        # Si la evidencia extraída fue 0 hechos, los chunks RAG son irrelevantes
        # y pueden confundir al modelo — no pasarlos en el retry
        retry_chunks = filtered_chunks if evidence_extracted else None
        retry_evidence = evidence_context if evidence_extracted else None
        logger.info(
            f"[Critic] Reintentando con Together.ai tras bloqueo... "
            f"(evidence={evidence_extracted}, chunks={'sí' if retry_chunks else 'no'})"
        )
        retry_answer, retry_model = await generate(
            system_prompt=system_prompt + correction_hint,
            user_message=query,
            context_chunks=retry_chunks,
            history=history if history else None,
            max_tokens=max_tokens,
            temperature=req.temperature,
            evidence_override=retry_evidence,
            force_together=True,
        )
        retry_answer = clean_markdown(retry_answer)
        logger.info(f"[Critic] Retry response ({retry_model}): {retry_answer[:200]}...")

        retry_s = await evaluate_response(query, filtered_chunks, retry_answer)
        retry_t = await evaluate_technical(query, evidence_text, retry_answer, species_hint)
        retry_blocked = retry_s["verdict"] == "BLOCK" or retry_t["verdict"] == "BLOCK"

        if retry_blocked:
            logger.warning("[Critic] Retry Together.ai también bloqueado — usando fallback")
            final_answer = BLOCKED_FALLBACK
        else:
            logger.info(f"[Critic] Retry APROBADO vía {retry_model}")
            final_answer = retry_answer
            answer = retry_answer
            model_used = retry_model
            structural_verdict = retry_s
            technical_verdict = retry_t
    else:
        final_answer = answer

    # ── Fase 2: Log DPO ──
    elapsed_ms = int((time.time() - t0) * 1000)
    log_critic_result(
        query=query,
        evidence_summary=evidence_text[:2000],
        draft_answer=answer,
        structural_verdict=structural_verdict,
        technical_verdict=technical_verdict,
        final_answer=final_answer,
        category=category,
        species_hint=species_hint,
        latency_ms=elapsed_ms,
    )

    elapsed = time.time() - t0
    logger.info(f"[OpenAI] Respuesta en {elapsed:.2f}s vía {model_used} (cat={category})")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(t0),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": final_answer,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(query.split()),
            "completion_tokens": len(final_answer.split()),
            "total_tokens": len(query.split()) + len(final_answer.split()),
        },
    }


async def _stream_response(query: str, history: list[dict], req: OAIChatRequest, t0: float):
    """Respuesta streaming con doble critic gate (Fase 2).

    Genera la respuesta completa primero, la evalúa con ambos critics,
    y luego la emite como fake-stream (mismo patrón que vision).
    Esto garantiza que ninguna respuesta bloqueada llegue al usuario.
    """
    system_prompt, top_chunks, category, _ = await _rag_pipeline(query, history)

    # ── Fase 2: Evidence Builder ──
    species_hint = get_species_hint(query)
    evidence_text, filtered_chunks, evidence_extracted = await extract_evidence(query, top_chunks, species_hint)

    max_tokens = req.max_tokens or 1024

    # Generar respuesta con evidencia estructurada
    evidence_context = build_evidence_context(evidence_text, filtered_chunks)
    answer, model_used = await generate(
        system_prompt=system_prompt,
        user_message=query,
        context_chunks=filtered_chunks,
        history=history if history else None,
        max_tokens=max_tokens,
        temperature=req.temperature,
        evidence_override=evidence_context if evidence_extracted else None,
    )

    # ── Post-procesado: limpiar markdown ──
    answer = clean_markdown(answer)

    # ── Fase 2: Doble Critic ──
    structural_verdict = await evaluate_response(query, filtered_chunks, answer)
    technical_verdict = await evaluate_technical(query, evidence_text, answer, species_hint)

    was_blocked = (
        structural_verdict["verdict"] == "BLOCK"
        or technical_verdict["verdict"] == "BLOCK"
    )

    if was_blocked:
        block_source = "structural" if structural_verdict["verdict"] == "BLOCK" else "technical"
        all_reasons = (
            structural_verdict.get("reasons", [])
            + technical_verdict.get("reasons", [])
        )
        logger.warning(
            f"[Critic] BLOQUEADO (stream, {block_source}): {all_reasons} "
            f"tags={structural_verdict.get('tags', []) + technical_verdict.get('tags', [])}"
        )
        logger.info(f"[Critic] Draft bloqueado (stream): {answer[:200]}...")

        # ── Retry con Together.ai (skip Ollama que generó el error) ──
        correction_hint = (
            "\n\nAVISO INTERNO — CORRECCIÓN OBLIGATORIA:\n"
            "Un borrador anterior fue rechazado por el control de calidad por estos motivos:\n"
            + "\n".join(f"• {r}" for r in all_reasons)
            + "\nGenera una respuesta nueva que evite estos errores. "
            "Sé preciso con la terminología y no confundas conceptos. "
            "Si el contexto RAG no es relevante para la pregunta, responde "
            "usando tu conocimiento general como experto."
        )
        # Si la evidencia extraída fue 0 hechos, los chunks RAG son irrelevantes
        # y pueden confundir al modelo — no pasarlos en el retry
        retry_chunks = filtered_chunks if evidence_extracted else None
        retry_evidence = evidence_context if evidence_extracted else None
        logger.info(
            f"[Critic] Reintentando con Together.ai tras bloqueo (stream)... "
            f"(evidence={evidence_extracted}, chunks={'sí' if retry_chunks else 'no'})"
        )
        retry_answer, retry_model = await generate(
            system_prompt=system_prompt + correction_hint,
            user_message=query,
            context_chunks=retry_chunks,
            history=history if history else None,
            max_tokens=max_tokens,
            temperature=req.temperature,
            evidence_override=retry_evidence,
            force_together=True,
        )
        retry_answer = clean_markdown(retry_answer)
        logger.info(f"[Critic] Retry response (stream, {retry_model}): {retry_answer[:200]}...")

        retry_s = await evaluate_response(query, filtered_chunks, retry_answer)
        retry_t = await evaluate_technical(query, evidence_text, retry_answer, species_hint)
        retry_blocked = retry_s["verdict"] == "BLOCK" or retry_t["verdict"] == "BLOCK"

        if retry_blocked:
            logger.warning("[Critic] Retry Together.ai también bloqueado (stream) — usando fallback")
            final_answer = BLOCKED_FALLBACK
        else:
            logger.info(f"[Critic] Retry APROBADO (stream) vía {retry_model}")
            final_answer = retry_answer
            answer = retry_answer
            model_used = retry_model
            structural_verdict = retry_s
            technical_verdict = retry_t
    else:
        final_answer = answer

    # ── Fase 2: Log DPO ──
    elapsed_ms = int((time.time() - t0) * 1000)
    log_critic_result(
        query=query,
        evidence_summary=evidence_text[:2000],
        draft_answer=answer,
        structural_verdict=structural_verdict,
        technical_verdict=technical_verdict,
        final_answer=final_answer,
        category=category,
        species_hint=species_hint,
        latency_ms=elapsed_ms,
    )

    elapsed = time.time() - t0
    logger.info(f"[OpenAI] Stream+critic en {elapsed:.2f}s vía {model_used} (cat={category})")

    # Fake-stream: emitir la respuesta aprobada palabra a palabra
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    first_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": int(t0),
        "model": req.model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(first_chunk)}\n\n"

    words = final_answer.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else f" {word}"
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": int(t0),
            "model": req.model,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    done_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": int(t0),
        "model": req.model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_chunk)}\n\n"
    yield "data: [DONE]\n\n"


def _error_response(msg: str):
    return {
        "error": {
            "message": msg,
            "type": "invalid_request_error",
            "param": None,
            "code": None,
        }
    }
