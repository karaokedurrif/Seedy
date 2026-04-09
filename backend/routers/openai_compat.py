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
from services.llm import generate, generate_stream, generate_report
from services.web_search import search_web, format_web_results, should_search_web, needs_product_search
from services.url_fetcher import fetch_urls_from_query
from services.critic import evaluate_response, BLOCKED_FALLBACK
from services.critic import evaluate_technical
from services.critic_log import log_critic_result
from services.gold_capture import regenerate_on_block, capture_informe_gold
from services.evidence import extract_evidence, build_evidence_context, deduplicate_chunks
from services.metadata_filter import get_species_hint
from services.gemini_vision import analyze_image as gemini_analyze, get_dataset_stats
from services.temporality import classify_temporality, needs_web_augmentation
from services.postprocess import clean_markdown
from routers.report import generate_pdf_bytes

# Directorio de informes PDF generados
import pathlib as _pathlib
_REPORTS_DIR = _pathlib.Path("/app/data/reports")
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Patrón para detectar queries malformadas que OWUI envía como prefill
_JUNK_QUERY_RE = re.compile(
    r"^(###\s*Task|\[\")|^\s*$",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)

# ── Límite de historial para evitar desbordamiento de contexto ──────────
# Máximo N turnos completos (user+assistant) a enviar al LLM.
# Un turno ≈ 1-3K tokens.  10 turnos = ~20 mensajes ≈ 15-25K tokens de historial.
_MAX_HISTORY_TURNS = 10  # Últimos 10 turnos (20 mensajes user+assistant)

# Regex para limpiar links de PDF alucinados por el LLM en el historial.
# Captura tanto el formato alucinado como el auto-generado (para no re-inyectar en contexto).
_PDF_LINK_RE = re.compile(
    r"\n*---\n\*\*PDF generado:\*\*[^\n]*\.pdf\)[^\n]*"
    r"|"
    r"\n*PDF generado:[^\n]*\.pdf[^\n]*",
    re.DOTALL,
)


def _truncate_history(history: list[dict], max_turns: int = _MAX_HISTORY_TURNS) -> list[dict]:
    """Trunca el historial a los últimos `max_turns` pares user/assistant.

    También limpia links de PDF de mensajes anteriores para evitar que el LLM
    los use como ejemplo para generar links alucinados.
    """
    if not history:
        return history

    # Quedarnos con los últimos max_turns*2 mensajes (user+assistant)
    if len(history) > max_turns * 2:
        history = history[-(max_turns * 2):]
        logger.info(f"[History] Truncado a últimos {max_turns} turnos ({len(history)} msgs)")

    # Limpiar links de PDF del historial para que no se propaguen
    cleaned = []
    for msg in history:
        content = msg.get("content", "")
        if content and _PDF_LINK_RE.search(content):
            content = _PDF_LINK_RE.sub("", content).rstrip()
        cleaned.append({**msg, "content": content})

    return cleaned


# ── Detector de queries complejas que necesitan DeepSeek-R1 (brain) ────
# Queries que piden análisis profundo, BOM, diseño de sistemas, etc.
# van al modelo brain (generate_report) aunque no se clasifiquen como INFORME.
_COMPLEX_QUERY_RE = re.compile(
    r"(?:"
    r"BOM\b|bill\s+of\s+materials|lista\s+de\s+materiales"
    r"|presupuesto\s+detallad|estudio\s+detallad|an[aá]lisis\s+detallad"
    r"|plan\s+de\s+implementaci[oó]n|dise[ñn][ao]\s+(?:de\s+)?(?:sistema|instalaci[oó]n|red)"
    r"|qu[eé]\s+(?:dispositivos?|sensores?|c[aá]maras?|equipos?)\s+(?:pondr[ií]as|recomiendas|necesit)"
    r"|qu[eé]\s+razas?\s+(?:recomiendas|pondr[ií]as|usar[ií]as|elegir[ií]as)"
    r"|hazme\s+un\s+(?:estudio|an[aá]lisis|dise[ñn]o|plan|documento)"
    r"|informe\s+(?:t[eé]cnico|ejecutivo|detallado)"
    r"|tabla\s+comparativ|comparativa\s+(?:detallada|t[eé]cnica|de\s+(?:dispositivos|sensores|equipos|razas))"
    r"|arquitectura\s+(?:IoT|de\s+red|del?\s+sistema)"
    r"|ranking\s+(?:de\s+)?razas|mejor(?:es)?\s+razas?\s+para"
    r")",
    re.IGNORECASE,
)


def _is_complex_query(query: str) -> bool:
    """Detecta queries que necesitan análisis profundo (→ brain model DeepSeek-R1)."""
    return bool(_COMPLEX_QUERY_RE.search(query))

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
                "id": "seedy-think",
                "object": "model",
                "created": 1700000000,
                "owned_by": "neofarm",
                "meta": {
                    "description": "Seedy Deep Thinking — DeepSeek-R1 para razonamiento profundo",
                },
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


def _get_known_gallinero_ids() -> list[str]:
    """Devuelve IDs de gallineros conocidos desde telemetry DEVICE_GALLINERO_MAP."""
    try:
        from services.telemetry import DEVICE_GALLINERO_MAP
        return list(DEVICE_GALLINERO_MAP.keys())
    except Exception:
        return []


def _extract_gallinero_from_query(query: str) -> str | None:
    """Intenta extraer el gallinero de la query del usuario."""
    q = query.lower()
    # Patrones por nombre
    if "durrif 1" in q or "durrif_1" in q or "durrif i" in q or "gallinero 1" in q:
        return "gallinero_durrif_1"
    if "durrif 2" in q or "durrif_2" in q or "durrif ii" in q or "gallinero 2" in q:
        return "gallinero_durrif_2"
    # Match directo con IDs conocidos
    for gid in _get_known_gallinero_ids():
        if gid in q:
            return gid
    return None


# ── Regex para detectar queries sobre aves registradas ──
_BIRDS_QUERY_RE = re.compile(
    r"(?:"
    r"(?:qu[eé]|cu[aá]ntas?|cu[aá]les|lista|dime|muestra|ense[ñn]a)"
    r"\s+(?:las\s+)?(?:aves?|gallinas?|gallos?|p[aá]jaros?|razas?)"
    r"|(?:aves?|gallinas?|gallos?|razas?)\s+(?:tengo|hay|registrad|identificad|exist)"
    r"|registro\s+de\s+aves|mis\s+(?:aves|gallinas|gallos)"
    r"|PAL-\d{4}-\d+"
    r"|(?:aves?|gallinas?|gallos?)\s+(?:del?|en)\s+(?:palacio|gallinero|durrif)"
    r"|hub\.ovosfera\.com/farm/palacio/aves"
    r"|ovosfera.*aves|aves.*ovosfera"
    r"|(?:cada|todas?\s+las|las)\s+aves"
    r"|cualidad|caracter[ií]stica|individual|por\s+ave"
    r"|censo\s+(?:de\s+)?(?:aves?|gallinero)"
    r")",
    re.IGNORECASE,
)


def _needs_bird_registry(query: str, categories: list[tuple[str, float]]) -> bool:
    """Detecta si la query necesita datos del registro de aves."""
    if _BIRDS_QUERY_RE.search(query):
        return True
    cat_names = {cat for cat, _ in categories}
    # Si es AVICULTURA y menciona aves/gallinero concreto, inyectar
    if "AVICULTURA" in cat_names:
        q = query.lower()
        if any(w in q for w in ("palacio", "granja", "gallinero", "durrif", "tengo", "nuestr", "registr", "mi ")):
            return True
    return False


def _get_bird_registry_context(gallinero_id: str | None = None) -> str:
    """Formatea el registro de aves como contexto compacto para el LLM.

    NO incluye fotos base64 — solo datos de identidad y stats.
    """
    try:
        from routers.birds import _registry
        birds = _registry
    except Exception:
        return ""

    if not birds:
        return ""

    if gallinero_id:
        birds = [b for b in birds if b.get("gallinero") == gallinero_id]

    if not birds:
        return ""

    # Agrupar por gallinero para el resumen
    from collections import Counter, defaultdict
    by_gallinero = defaultdict(list)
    for b in birds:
        by_gallinero[b.get("gallinero", "desconocido")].append(b)

    lines = []
    total = len(birds)
    breeds = Counter(f"{b['breed']} {b.get('color', '')}".strip() for b in birds)
    lines.append(f"REGISTRO DE AVES DEL PALACIO — {total} aves identificadas por IA")
    lines.append(f"Razas ({len(breeds)} variedades): " + ", ".join(
        f"{breed} ({n})" for breed, n in breeds.most_common()
    ))
    lines.append("")

    for gal_id, gal_birds in sorted(by_gallinero.items()):
        lines.append(f"── {gal_id} ({len(gal_birds)} aves) ──")
        gal_breeds = Counter(f"{b['breed']} {b.get('color', '')}".strip() for b in gal_birds)
        lines.append(f"  Razas: " + ", ".join(
            f"{breed} ({n})" for breed, n in gal_breeds.most_common()
        ))
        # Listar cada ave individualmente (compacto)
        for b in sorted(gal_birds, key=lambda x: x.get("bird_id", "")):
            sex_str = {"female": "♀", "male": "♂"}.get(b.get("sex", ""), "?")
            last_seen = b.get("last_seen", "")[:10]  # Solo fecha
            first_seen = b.get("first_seen", "")[:10]
            notes = b.get("notes", "")
            note_str = f" — {notes}" if notes else ""
            lines.append(
                f"  {b['bird_id']} | {b['breed']} {b.get('color', '')} | "
                f"{sex_str} | visto: {first_seen}→{last_seen}{note_str}"
            )
        lines.append("")

    return "\n".join(lines)


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
    is_report = category == "INFORME"
    rag_top_k = 30 if is_report else None   # INFORME: 3 por colección (10 cols)
    rag_results = await rag_search(search_query, collections, alt_query=alt_q, category=category, top_k=rag_top_k)
    logger.info(f"[OpenAI] RAG: {len(rag_results)} resultados de {collections}"
                f"{' (dual-query)' if alt_q else ''}")

    # 3. Búsqueda web: por insuficiencia RAG, temporalidad dinámica, o intención comercial/producto
    web_context = ""
    force_web = needs_web_augmentation(temporality)
    force_product = needs_product_search(query)
    # INFORME con contenido técnico/hardware siempre busca web para precios y modelos reales
    if is_report and not force_product:
        _hw_kw = re.search(
            r"(?:sensor|dispositivo|c[aá]mara|equip|BOM|iot|hardware|dron|collar|gateway|panel\s+solar)",
            query, re.IGNORECASE,
        )
        if _hw_kw:
            force_product = True
            logger.info(f"[OpenAI] INFORME con hardware ('{_hw_kw.group()}') → forzando búsqueda web")
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

    # 4. Rerank (INFORME usa más chunks para dar contexto rico al 70B)
    rerank_n = 15 if is_report else None
    top_chunks = rerank(query, rag_results, top_n=rerank_n) if rag_results else []
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

    # 5c. Inyectar datos conductuales si la query es de COMPORTAMIENTO
    behavior_cats = {cat for cat, _ in multi_cats}
    if "COMPORTAMIENTO" in behavior_cats:
        try:
            from services.behavior_inference import get_group_behavior_summary
            from services.behavior_serializer import to_llm_context
            # Intentar detectar gallinero de la query
            _gall_id = _extract_gallinero_from_query(query)
            if _gall_id:
                behavior_inferences = get_group_behavior_summary(_gall_id, window="6h")
            else:
                # Por defecto, todos los gallineros conocidos
                behavior_inferences = []
                for gid in _get_known_gallinero_ids():
                    behavior_inferences.extend(get_group_behavior_summary(gid, window="6h"))
            if behavior_inferences:
                behavior_text = to_llm_context(behavior_inferences)
                top_chunks.insert(0, {
                    "text": f"[Datos conductuales en vivo]\n{behavior_text}",
                    "file": "behavior_live",
                    "collection": "behavior",
                    "chunk_index": 0,
                    "rerank_score": 0.9,
                })
                logger.info(f"[OpenAI] Inyectados {len(behavior_inferences)} resúmenes conductuales")
        except Exception as e:
            logger.warning(f"[OpenAI] Error inyectando datos conductuales: {e}")

    # 5d. Inyectar registro de aves si la query lo necesita
    if _needs_bird_registry(query, multi_cats):
        try:
            _gall_id = _extract_gallinero_from_query(query)
            bird_context = _get_bird_registry_context(_gall_id)
            if bird_context:
                top_chunks.insert(0, {
                    "text": f"[Datos reales del registro de aves — Gallinero del Palacio]\n{bird_context}",
                    "file": "birds_registry_live",
                    "collection": "birds",
                    "chunk_index": 0,
                    "rerank_score": 0.95,
                })
                n_birds = bird_context.count("PAL-")
                logger.info(f"[OpenAI] Inyectado registro de aves: {n_birds} aves")
        except Exception as e:
            logger.warning(f"[OpenAI] Error inyectando registro de aves: {e}")

    # 5e. Inyectar predicciones ML (puesta, estrés, anomalías)
    _pred_cats = {cat for cat, _ in multi_cats}
    _q_low = query.lower()
    _needs_predictions = (
        _pred_cats & {"COMPORTAMIENTO", "AVICULTURA"}
        or any(w in _q_low for w in (
            "predicci", "puesta", "estrés", "estres", "anomal",
            "va a poner", "pondrá", "ponedora", "huevo",
            "estado", "salud", "alerta",
        ))
    )
    if _needs_predictions:
        try:
            from services.behavior_ml import get_behavior_ml_engine
            ml_engine = get_behavior_ml_engine()
            _gall_pred = _extract_gallinero_from_query(query)
            gallineros = [_gall_pred] if _gall_pred else _get_known_gallinero_ids()
            all_preds = []
            for gid in gallineros:
                preds = ml_engine.get_active_predictions(gid)
                for p in preds:
                    p["gallinero_id"] = gid
                all_preds.extend(preds)
            if all_preds:
                lines = ["PREDICCIONES ML ACTIVAS (última hora):"]
                for p in all_preds[:8]:
                    tipo = {"laying_likely": "🥚 Puesta probable",
                            "stress_likely": "⚠️ Estrés",
                            "flock_anomaly": "🔴 Anomalía grupo"}.get(p["type"], p["type"])
                    bird = p.get("bird_id", p.get("gallinero_id", ""))
                    prob = p.get("probability", 0)
                    ev = "; ".join(p.get("evidence", []))
                    lines.append(f"  {tipo} — {bird} (prob {prob:.0%}): {ev}")
                pred_text = "\n".join(lines)
                top_chunks.insert(0, {
                    "text": f"[Predicciones ML en vivo]\n{pred_text}",
                    "file": "ml_predictions_live",
                    "collection": "behavior",
                    "chunk_index": 0,
                    "rerank_score": 0.92,
                })
                logger.info(f"[OpenAI] Inyectadas {len(all_preds)} predicciones ML")
        except Exception as e:
            logger.warning(f"[OpenAI] Error inyectando predicciones ML: {e}")

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

    # ── Prefijo /think: forzar modelo brain (DeepSeek-R1) sin cambiar de modelo ──
    if query.lstrip().startswith("/think"):
        query = query.lstrip().removeprefix("/think").strip()
        req.model = "seedy-think"
        logger.info(f"[OpenAI] Prefijo /think detectado → forzando brain model")

    # Historial: todo excepto el último user y el system
    user_messages = [m for m in req.messages if m.role == "user"]
    if len(user_messages) > 1:
        # Multi-turn: incluir todos los mensajes previos como historial
        history = []
        for msg in req.messages[:-1]:  # Todos menos el último
            if msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": _content_to_str(msg.content)})

    # ── Truncar historial para evitar desbordamiento de contexto ──
    history = _truncate_history(history)

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


def _decompose_report_requirements(query: str) -> str:
    """Extrae requisitos explícitos del query del usuario para inyectar como checklist.

    Evita que el 70B ignore sub-temas de la solicitud (ej: 'para luego crecer'
    → el modelo debe cubrir escalado). No usa LLM — es keyword-based para no
    añadir latencia.
    """
    q = query.lower()
    reqs = []

    # Detectar temas clave por keywords
    if any(w in q for w in ("piloto", "prueba", "poc", "prototipo", "fase inicial")):
        reqs.append("Diseño del piloto: alcance, duración, superficie, objetivos medibles")
    if any(w in q for w in ("crecer", "escalar", "ampliar", "expandir", "luego", "siguiente fase")):
        reqs.append("Plan de escalado: criterios de éxito para pasar de piloto a producción, fases de crecimiento")
    if any(w in q for w in ("sensor", "sensores", "monitoriz", "iot", "dispositivo")):
        reqs.append("Equipamiento: tipos de sensor específicos, cantidades, modelos si disponibles, gateway/conectividad")
    if any(w in q for w in ("bodega", "vino", "viña", "viñedo", "viticultur", "vendimia", "ferment")):
        reqs.append("Contexto vitícola: parámetros críticos de viña/bodega, riesgos del cultivo, estacionalidad")
    if any(w in q for w in ("cost", "precio", "presupuesto", "inversión", "roi", "rentab")):
        reqs.append("Análisis económico: CAPEX, OPEX, ROI estimado, payback period")
    if any(w in q for w in ("1ha", "1 ha", "hectárea", "parcela", "superficie")):
        reqs.append("Dimensionamiento para la superficie indicada: densidad de sensores, cobertura, layout")
    if any(w in q for w in ("bom", "bill of material", "lista de material")):
        reqs.append("BOM completo: tabla con Categoría, Dispositivo, Modelo concreto, Cantidad, Precio unitario (EUR), Subtotal, Proveedor/URL")
    if any(w in q for w in ("sin luz", "sin electricidad", "off-grid", "sin red", "sin corriente", "aislad")):
        reqs.append("Solución energética off-grid: paneles solares, baterías, consumo estimado (W), autonomía")
    if any(w in q for w in ("capón", "capon", "gallina", "ave", "gallinero", "avícola", "avicultura")):
        reqs.append("Contexto avícola: adaptar recomendaciones a aves (no ganado vacuno/porcino). Cámaras para identificación visual de razas, sensores ambientales para gallineros")
    if any(w in q for w in ("geotwin", "gemelo digital", "digital twin", "twin")):
        reqs.append("Arquitectura del gemelo digital: capas de datos, visualización 3D, integración con sensores, NDVI/ortofoto si aplica")
    if any(w in q for w in ("dispositivo", "sensor", "cámara", "hardware", "equipo", "iot")):
        reqs.append("CADA dispositivo DEBE tener: marca y modelo concreto (ej: 'Dragino LHT65N'), protocolo (Zigbee/LoRa/WiFi/4G), precio real de mercado (EUR), proveedor")

    # Siempre incluir presupuesto y cronograma para INFORME
    if not any("económico" in r for r in reqs):
        reqs.append("Presupuesto estimado desglosado por concepto (equipamiento, instalación, SaaS, mantenimiento)")
    reqs.append("Cronograma de 12 semanas con hitos y entregables concretos")

    if not reqs:
        return ""

    checklist = "\n".join(f"  ☐ {r}" for r in reqs)
    return (
        "REQUISITOS DETECTADOS EN LA SOLICITUD (DEBES cubrir TODOS):\n"
        f"{checklist}\n"
    )


def _build_report_context(query: str, chunks: list[dict]) -> str:
    """Construye contexto expandido para informes (bypass evidence extractor).

    A diferencia del evidence extractor (6000 chars, orientado a Q&A),
    esto pasa TODOS los chunks deduplicados al 70B con instrucciones
    explícitas de usar los datos reales.
    """
    if not chunks:
        return ""

    ctx_parts = []
    total_len = 0
    max_ctx = 24000  # Generoso para DeepSeek-R1 (163k ctx) / Kimi-K2.5 (262k ctx)
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("file", "desconocido")
        text = chunk.get("text", "")
        if total_len + len(text) > max_ctx:
            remaining = max_ctx - total_len
            if remaining > 100:
                ctx_parts.append(f"[Fuente {i}: {source}]\n{text[:remaining]}…")
            break
        ctx_parts.append(f"[Fuente {i}: {source}]\n{text}")
        total_len += len(text)

    context_str = "\n\n".join(ctx_parts)

    # Checklist de requisitos detectados en la solicitud del usuario
    requirements = _decompose_report_requirements(query)

    return (
        "══════════════════════════════════════\n"
        "DATOS REALES DE NEOFARM (fuentes internas verificadas):\n"
        "══════════════════════════════════════\n"
        f"{context_str}\n\n"
        f"{requirements}\n"
        "══════════════════════════════════════\n"
        "INSTRUCCIONES CRÍTICAS PARA EL INFORME:\n"
        "══════════════════════════════════════\n"
        "REGLAS DE ESPECIFICIDAD (violación = informe rechazado):\n"
        "- NUNCA escribas tablas con '-' o celdas vacías ni 'Modelo: -'. Si no sabes el modelo exacto, "
        "propón uno real del mercado con '(recomendación NeoFarm)'.\n"
        "- NUNCA cites nombres de ficheros internos. PROHIBIDO: 'Según el documento SEEDY_MASTER_ROADMAP_2026...', "
        "'Según el fichero auto_Ganadería...'. Cita por CONTENIDO: 'Según estudios de ganadería de precisión en Andalucía...'.\n"
        "- NUNCA pongas frases genéricas sin dato: 'mejorar la eficiencia', 'optimizar recursos', "
        "'reducir costes' SIN un número o porcentaje concreto. Si no tienes dato, no lo digas.\n"
        "- En 'Hallazgos principales', la columna 'Dato' NUNCA puede ser '-'. Pon un dato real o elimina la fila.\n\n"
        "PRODUCTOS Y HARDWARE:\n"
        "- CADA dispositivo debe tener: marca + modelo real (ej: 'Dragino LHT65N', 'Dahua IPC-HFW2841T'), "
        "protocolo (Zigbee 3.0, LoRaWAN, WiFi, MQTT), precio unitario en EUR.\n"
        "- Usa los resultados de búsqueda web incluidos abajo para obtener precios y modelos reales actuales.\n"
        "- Si recomiendas algo off-grid (sin electricidad), DEBES incluir solución energética: panel solar + batería + regulador.\n"
        "- Si recomiendas cámaras, sé específico: resolución, visión nocturna IR, protocolo, alimentación.\n\n"
        "EXPERIENCIA PROPIA NEOFARM:\n"
        "- NeoFarm tiene un piloto REAL desplegado en 'El Gallinero del Palacio' (Segovia): "
        "cámaras IP 4K (TP-Link VIGI C340, Dahua WizSense), sensores Zigbee eWeLink CK-TLSR8656 para temp/humedad, "
        "YOLO v3 para identificación visual de aves, Zigbee2MQTT + MQTT + InfluxDB + Grafana. "
        "Cuando sea relevante, CITA esta experiencia real como caso de éxito probado.\n\n"
        "EXTRACCIÓN OBLIGATORIA:\n"
        "- ANTES de escribir cada sección, RELEE las fuentes y extrae TODOS los datos concretos: "
        "nombres de sensores, cantidades, modelos, protocolos, resultados numéricos, "
        "nombres de proyectos, universidades, empresas, fechas, zonas geográficas.\n"
        "- Si las fuentes dicen '11 sensores capacitivos', tu informe DEBE decir '11 sensores capacitivos' — "
        "NUNCA marques como pendiente un dato que SÍ aparece en las fuentes.\n"
        "- Cita por contenido, no por nombre de fichero: 'Según el estudio de monitorización "
        "de fermentación (INRAE, 2022)...' — NO 'Según el documento xyz.md'.\n\n"
        "ESTIMACIONES ECONÓMICAS:\n"
        "- Para cifras que NO están en las fuentes pero se pueden estimar: usa los resultados web "
        "para precios reales. Si no hay dato web, usa rangos del sector marcados como "
        "'(estimación NeoFarm basada en pilotos comparables)'.\n"
        "- Solo usa '[Dato no disponible en fuentes]' cuando el dato es IMPOSIBLE de estimar "
        "(ej: código de parcela, nombre del propietario).\n"
        "- NO repitas '(estimación NeoFarm basada en datos del sector)' en cada línea. Una vez basta.\n\n"
        "RAZONAMIENTO EXPERTO:\n"
        "- NO te limites a copiar fuentes. RAZONA: ¿por qué este sensor y no otro? ¿Cuál es el trade-off? "
        "¿Qué pasa si el usuario tiene 500ha vs 50ha? ¿Por qué LoRa y no Zigbee para extensivo?\n"
        "- Adapta CADA recomendación al contexto del usuario: superficie, nº animales, infraestructura existente.\n"
        "- Si el usuario dice 'sin luz', TODA la solución debe ser off-grid. No propongas equipos que necesiten red eléctrica.\n\n"
        "ESTRUCTURA OBLIGATORIA:\n"
        "- Mínimo 6 secciones ## desarrolladas, cada una con 2+ párrafos + tabla + lectura clave.\n"
        "- El cronograma SIEMPRE tiene exactamente 6 filas: S1-S2, S3-S4, S5-S6, S7-S8, S9-S10, S11-S12.\n"
        "- Las acciones (A/B/C) SIEMPRE incluyen business case con EUR estimado.\n"
        "- Al final, sección '## Fuentes' listando cada documento citado por nombre.\n"
    )


def _extract_title_from_markdown(md: str) -> str:
    """Extrae título del primer # del markdown, o devuelve genérico."""
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped.lstrip("# ").strip()
    return "Informe NeoFarm"


def _check_report_quality(report: str) -> list[str]:
    """Critic ligero para informes — detecta fallos estructurales sin LLM.

    Retorna lista de issues. Lista vacía = calidad aceptable.
    """
    issues = []

    # 1. Longitud mínima (6+ secciones desarrolladas deberían dar >5000 chars)
    if len(report) < 4000:
        issues.append(f"Informe demasiado corto ({len(report)} chars, mínimo 4000)")

    # 2. Contar secciones ## (mínimo 5)
    sections = [l for l in report.splitlines() if l.strip().startswith("## ")]
    if len(sections) < 5:
        issues.append(f"Solo {len(sections)} secciones (mínimo 5)")

    # 3. Ratio de [Dato pendiente/no disponible] — si >40% de celdas de tabla son pendientes
    pending_count = report.lower().count("[dato pendiente") + report.lower().count("[dato no disponible")
    table_cells = report.count("|") // 2  # aproximación
    if table_cells > 0 and pending_count > 0:
        ratio = pending_count / max(table_cells // 3, 1)  # ~3 pipes por celda
        if ratio > 0.35:
            issues.append(f"Exceso de datos pendientes ({pending_count} marcadores)")

    # 4. Cronograma: debe tener 6 filas S*-S*
    crono_rows = len(re.findall(r"S\d+\s*[-–]\s*S\d+", report))
    if crono_rows < 5:
        issues.append(f"Cronograma incompleto ({crono_rows} filas, mínimo 6)")

    # 5. EUR: al menos 2 menciones de cifras económicas
    eur_mentions = len(re.findall(r"\d+[\.\d]*\s*(?:EUR|€)", report))
    if eur_mentions < 2:
        issues.append(f"Faltan cuantificaciones económicas ({eur_mentions} EUR, mínimo 2)")

    # 6. Celdas vacías en tablas: | - | o | — | es inaceptable
    empty_cells = len(re.findall(r"\|\s*[-–—]\s*\|", report))
    if empty_cells > 2:
        issues.append(f"Tabla con {empty_cells} celdas vacías '| - |' (máximo 2)")

    # 7. Cita de ficheros internos: PROHIBIDO citar nombres de archivo .md/.pdf/.jsonl
    internal_cites = re.findall(
        r"(?:Según|según|Basánd\w+|segun)\s+(?:el |la |los |las )?(?:documento|fichero|archivo)?\s*"
        r"[A-Z_a-z0-9]+(?:_[A-Za-z0-9]+){2,}",
        report,
    )
    if internal_cites:
        issues.append(f"Cita ficheros internos: {internal_cites[:2]} — usar contenido, no nombre de archivo")

    # 8. Frases genéricas vacías (sin número)
    generic_count = 0
    generics = [
        "mejorar la eficiencia y productividad",
        "mejora de la eficiencia",
        "uso eficiente de los recursos naturales",
        "mejorar la gestión y el análisis",
        "mejora en la monitorización y el control",
    ]
    report_lower = report.lower()
    for g in generics:
        generic_count += report_lower.count(g)
    if generic_count > 3:
        issues.append(f"Exceso de frases genéricas sin datos ({generic_count} instancias)")

    return issues


def _auto_generate_pdf(answer: str, category: str) -> str | None:
    """Si la categoría es INFORME, genera PDF y devuelve línea con enlace de descarga."""
    if category != "INFORME":
        return None
    try:
        title = _extract_title_from_markdown(answer)
        pdf_bytes = generate_pdf_bytes(answer, title=title)
        # Nombre único con timestamp
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r"[^\w\- ]", "", title).strip().replace(" ", "_")[:60]
        filename = f"{ts}_{safe_title}.pdf"
        out_path = _REPORTS_DIR / filename
        out_path.write_bytes(pdf_bytes)
        pages = len(pdf_bytes) // 3000 or 1  # estimación aprox.
        logger.info(f"[Report] PDF auto-generado: {filename} ({len(pdf_bytes)} bytes)")
        base_url = "https://seedy-api.neofarm.io"
        return (
            f"\n\n---\n"
            f"**PDF generado:** [{filename}]({base_url}/reports/{filename})"
        )
    except Exception as e:
        logger.error(f"[Report] Error auto-generando PDF: {e}")
        return None


async def _non_stream_response(query: str, history: list[dict], req: OAIChatRequest, t0: float):
    """Respuesta no-streaming (formato OpenAI). Fase 2: evidence builder + doble critic."""
    system_prompt, top_chunks, category, _ = await _rag_pipeline(query, history)

    # ── Fase 2: Evidence Builder ──
    species_hint = get_species_hint(query)

    max_tokens = req.max_tokens or 2048  # 2K default (antes 1024 — insuficiente para BOM/análisis)

    # ── INFORME: modelo brain (DeepSeek-R1) + más tokens + bypass critic ──
    is_report = category == "INFORME"
    use_brain = is_report  # use_brain = usar DeepSeek-R1 (no siempre es informe formal)

    # seedy-think: forzar modelo brain (DeepSeek-R1) para razonamiento profundo
    is_think = req.model == "seedy-think"
    if is_think and not use_brain:
        logger.info(f"[OpenAI] seedy-think → forzando brain model (cat={category})")
        use_brain = True

    # Upgrade a brain model para queries complejas aunque no sean INFORME
    is_complex = _is_complex_query(query)
    if is_complex and not use_brain:
        logger.info(f"[OpenAI] Query compleja detectada → upgrade a brain (cat={category})")
        use_brain = True

    if use_brain:
        max_tokens = max(max_tokens, 8192)  # Brain necesita espacio para razonamiento

    if use_brain:
        # Brain: bypass evidence extractor (es Q&A, no sirve para docs).
        # Pasamos chunks deduplicados directamente al brain con contexto ampliado.
        filtered_chunks = deduplicate_chunks(top_chunks)
        report_context = _build_report_context(query, filtered_chunks)

        answer, model_used = await generate_report(
            system_prompt=system_prompt,
            user_message=query,
            context_chunks=filtered_chunks,
            history=history if history else None,
            max_tokens=max_tokens,
            temperature=0.5,
            evidence_override=report_context,
        )
        evidence_text = ""  # No hay evidence extraction en ruta brain
    else:
        evidence_text, filtered_chunks, evidence_extracted = await extract_evidence(query, top_chunks, species_hint)

        # Construir mensaje con evidencia estructurada (en vez de chunks crudos)
        evidence_context = build_evidence_context(evidence_text, filtered_chunks)

        # SIEMPRE usar evidence_context — incluso el fallback de chunks crudos
        # es mejor que pasar chunks sin instrucciones de contexto
        answer, model_used = await generate(
            system_prompt=system_prompt,
            user_message=query,
            context_chunks=filtered_chunks,
            history=history if history else None,
            max_tokens=max_tokens,
            temperature=req.temperature,
            evidence_override=evidence_context if evidence_context else None,
        )

    # ── Post-procesado: limpiar markdown (no para INFORME formal) ──
    if not is_report:
        answer = clean_markdown(answer)

    # ── Fase 2: Critic gate ──
    # Tres rutas: INFORME formal (critic estructural ligero), brain/think (auto-PASS),
    #             normal (doble critic LLM)
    if is_report:
        # INFORME formal: critic de calidad de informe + posible regeneración
        report_issues = _check_report_quality(answer)
        if report_issues:
            logger.warning(f"[Critic] INFORME calidad baja — regenerando: {report_issues}")
            hint = "ATENCIÓN — tu primer borrador tenía estos problemas: " + "; ".join(report_issues) + ". CORRÍGELOS en esta versión."
            answer2, _ = await generate_report(
                system_prompt=system_prompt,
                user_message=query,
                context_chunks=filtered_chunks,
                history=history if history else None,
                max_tokens=max_tokens,
                temperature=0.65,
                evidence_override=report_context + f"\n\n{hint}",
            )
            report_issues2 = _check_report_quality(answer2)
            if not report_issues2 or len(report_issues2) < len(report_issues):
                answer = answer2
                logger.info(f"[Critic] INFORME regenerado — mejora: {len(report_issues)}→{len(report_issues2 or [])} issues")
            else:
                logger.info("[Critic] INFORME regenerado sin mejora, usando primer borrador")
        structural_verdict = {"verdict": "PASS", "report_issues": report_issues}
        technical_verdict = {"verdict": "PASS"}
        was_blocked = False
        final_answer = answer

        # ── Gold Capture: guardar informe del brain como ejemplo SFT ──
        capture_informe_gold(query=query, answer=answer, category=category)

        logger.info(f"[Critic] INFORME — {len(report_issues)} issues detectados")
    elif use_brain and not is_report:
        # /think o query compleja: brain (DeepSeek-R1) es de confianza, skip critics
        structural_verdict = {"verdict": "PASS"}
        technical_verdict = {"verdict": "PASS"}
        was_blocked = False
        final_answer = answer
        logger.info(f"[Critic] Brain/think → auto-PASS (cat={category}, {len(answer)} chars)")
    else:
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

            # ── Gold Capture: regenerar con brain en vez de fallback genérico ──
            gold_answer = await regenerate_on_block(
                query=query,
                system_prompt=system_prompt,
                blocked_draft=answer,
                top_chunks=top_chunks,
                history=history if history else None,
                category=category,
                species_hint=species_hint,
                block_reasons=all_reasons,
            )
            if gold_answer:
                final_answer = gold_answer
                logger.info(f"[GoldCapture] Brain regeneró respuesta gold: {len(gold_answer)} chars")
            else:
                final_answer = BLOCKED_FALLBACK
        else:
            final_answer = answer

    # ── Fase 2: Log DPO ──
    elapsed_ms = int((time.time() - t0) * 1000)
    _evidence_for_log = report_context[:2000] if use_brain else evidence_text[:2000]
    log_critic_result(
        query=query,
        evidence_summary=_evidence_for_log,
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

    # ── Limpiar links de PDF alucinados por el LLM ──
    if _PDF_LINK_RE.search(final_answer):
        final_answer = _PDF_LINK_RE.sub("", final_answer).rstrip()
        logger.info("[OpenAI] Links de PDF alucinados eliminados de la respuesta")

    # ── Auto-PDF: si es INFORME, generar PDF y añadir enlace ──
    pdf_link = _auto_generate_pdf(final_answer, category)
    if pdf_link:
        final_answer += pdf_link

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

    max_tokens = req.max_tokens or 2048  # 2K default (antes 1024)

    # ── INFORME: modelo brain (DeepSeek-R1) + más tokens + bypass critic ──
    is_report = category == "INFORME"
    use_brain = is_report

    # seedy-think: forzar modelo brain (DeepSeek-R1) para razonamiento profundo
    is_think = req.model == "seedy-think"
    if is_think and not use_brain:
        logger.info(f"[OpenAI] Stream: seedy-think → forzando brain model (cat={category})")
        use_brain = True

    # Upgrade a brain model para queries complejas aunque no sean INFORME
    is_complex = _is_complex_query(query)
    if is_complex and not use_brain:
        logger.info(f"[OpenAI] Stream: query compleja → upgrade a brain (cat={category})")
        use_brain = True

    if use_brain:
        max_tokens = max(max_tokens, 8192)  # Brain necesita espacio para razonamiento

    if use_brain:
        # INFORME: bypass evidence extractor — contexto directo al brain
        filtered_chunks = deduplicate_chunks(top_chunks)
        report_context = _build_report_context(query, filtered_chunks)

        answer, model_used = await generate_report(
            system_prompt=system_prompt,
            user_message=query,
            context_chunks=filtered_chunks,
            history=history if history else None,
            max_tokens=max_tokens,
            temperature=0.5,
            evidence_override=report_context,
        )
        evidence_text = ""  # No hay evidence extraction en ruta brain
    else:
        evidence_text, filtered_chunks, evidence_extracted = await extract_evidence(query, top_chunks, species_hint)
        evidence_context = build_evidence_context(evidence_text, filtered_chunks)

        # SIEMPRE usar evidence_context (mismo fix que non-stream)
        answer, model_used = await generate(
            system_prompt=system_prompt,
            user_message=query,
            context_chunks=filtered_chunks,
            history=history if history else None,
            max_tokens=max_tokens,
            temperature=req.temperature,
            evidence_override=evidence_context if evidence_context else None,
        )

    # ── Post-procesado: limpiar markdown (no para INFORME formal) ──
    if not is_report:
        answer = clean_markdown(answer)

    # ── Fase 2: Critic gate ──
    if is_report:
        report_issues = _check_report_quality(answer)
        if report_issues:
            logger.warning(f"[Critic] INFORME (stream) calidad baja — regenerando: {report_issues}")
            hint = "ATENCIÓN — tu primer borrador tenía estos problemas: " + "; ".join(report_issues) + ". CORRÍGELOS en esta versión."
            answer2, _ = await generate_report(
                system_prompt=system_prompt,
                user_message=query,
                context_chunks=filtered_chunks,
                history=history if history else None,
                max_tokens=max_tokens,
                temperature=0.65,
                evidence_override=report_context + f"\n\n{hint}",
            )
            report_issues2 = _check_report_quality(answer2)
            if not report_issues2 or len(report_issues2) < len(report_issues):
                answer = answer2
                logger.info(f"[Critic] INFORME (stream) regenerado — mejora: {len(report_issues)}→{len(report_issues2 or [])} issues")
            else:
                logger.info("[Critic] INFORME (stream) regenerado sin mejora, usando primer borrador")
        structural_verdict = {"verdict": "PASS", "report_issues": report_issues}
        technical_verdict = {"verdict": "PASS"}
        was_blocked = False
        final_answer = answer

        # ── Gold Capture: guardar informe del brain como ejemplo SFT ──
        capture_informe_gold(query=query, answer=answer, category=category)

        logger.info(f"[Critic] INFORME (stream) — {len(report_issues)} issues detectados")
    elif use_brain and not is_report:
        # /think o query compleja: brain (DeepSeek-R1) es de confianza, skip critics
        structural_verdict = {"verdict": "PASS"}
        technical_verdict = {"verdict": "PASS"}
        was_blocked = False
        final_answer = answer
        logger.info(f"[Critic] Stream brain/think → auto-PASS (cat={category}, {len(answer)} chars)")
    else:
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

            # ── Gold Capture: regenerar con brain en vez de fallback genérico ──
            gold_answer = await regenerate_on_block(
                query=query,
                system_prompt=system_prompt,
                blocked_draft=answer,
                top_chunks=top_chunks,
                history=history if history else None,
                category=category,
                species_hint=species_hint,
                block_reasons=all_reasons,
            )
            if gold_answer:
                final_answer = gold_answer
                logger.info(f"[GoldCapture] Stream: Brain regeneró respuesta gold: {len(gold_answer)} chars")
            else:
                final_answer = BLOCKED_FALLBACK
        else:
            final_answer = answer

    # ── Fase 2: Log DPO ──
    elapsed_ms = int((time.time() - t0) * 1000)
    _evidence_for_log = report_context[:2000] if use_brain else evidence_text[:2000]
    log_critic_result(
        query=query,
        evidence_summary=_evidence_for_log,
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

    # ── Limpiar links de PDF alucinados por el LLM ──
    if _PDF_LINK_RE.search(final_answer):
        final_answer = _PDF_LINK_RE.sub("", final_answer).rstrip()
        logger.info("[OpenAI] Stream: links de PDF alucinados eliminados")

    # ── Auto-PDF: si es INFORME, generar PDF y añadir enlace ──
    pdf_link = _auto_generate_pdf(final_answer, category)
    if pdf_link:
        final_answer += pdf_link

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
