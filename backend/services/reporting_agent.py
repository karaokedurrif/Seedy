"""Seedy Backend — Reporting Agent: análisis diario de conversaciones + informe por email.

Ciclo de ejecución: cada 24h.

1. **Lectura de chats**: Lee la BD de Open WebUI (webui.db) y critic_log.jsonl
   para obtener todas las interacciones de las últimas 24h.

2. **Análisis**: Identifica patrones, preguntas recurrentes, bloqueos del critic,
   calidad de retrieval (RAG), temas con gaps, y oportunidades de mejora.

3. **Ejecución de mejoras**: Genera automáticamente queries para el knowledge_agent
   basadas en gaps detectados, propone nuevos SFT examples de queries frecuentes.

4. **Informe**: Envía email HTML al administrador con métricas, mejoras ejecutadas,
   y recomendaciones.
"""

import asyncio
import json
import logging
import os
import re
import smtplib
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Configuración ──

REPORT_INTERVAL = int(os.environ.get("REPORT_INTERVAL", 24 * 3600))  # 24h
REPORT_EMAIL = os.environ.get("REPORT_EMAIL", "durrif@gmail.com")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")  # Gmail App Password
SMTP_FROM = os.environ.get("SMTP_FROM", "")

# Rutas de datos
_DATA_DIR = Path("/app/data") if Path("/app/data").exists() else Path("data")
_CRITIC_LOG = _DATA_DIR / "critic_log.jsonl"
_GOLD_SFT = _DATA_DIR / "gold_sft.jsonl"
_GOLD_DPO = _DATA_DIR / "gold_dpo.jsonl"
_KNOWLEDGE_REPORTS = _DATA_DIR / "knowledge_reports"
_REPORT_HISTORY = _DATA_DIR / "reporting_agent"
_REPORT_HISTORY.mkdir(parents=True, exist_ok=True)

# Open WebUI DB (montado como volumen externo)
_WEBUI_DB = os.environ.get(
    "WEBUI_DB_PATH",
    "/app/backend/open-webui-data/webui.db",
)

# ── Lectura de chats de Open WebUI ──


def _read_webui_chats(since: datetime) -> list[dict]:
    """Lee chats de Open WebUI de las últimas N horas."""
    chats = []
    db_path = _WEBUI_DB

    if not Path(db_path).exists():
        logger.warning(f"[ReportAgent] webui.db no encontrada en {db_path}")
        return chats

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # chat_message.created_at es BIGINT (unix timestamp en seconds)
        since_ts = int(since.timestamp())

        cursor.execute(
            """
            SELECT cm.id, cm.chat_id, cm.role, cm.content, cm.model_id,
                   cm.sources, cm.usage, cm.created_at,
                   c.title as chat_title
            FROM chat_message cm
            JOIN chat c ON c.id = cm.chat_id
            WHERE cm.created_at >= ?
            ORDER BY cm.created_at ASC
            """,
            (since_ts,),
        )

        for row in cursor.fetchall():
            content = row["content"]
            # content puede ser JSON string o texto plano
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    pass

            # usage puede ser JSON
            usage = row["usage"]
            if isinstance(usage, str):
                try:
                    usage = json.loads(usage)
                except (json.JSONDecodeError, TypeError):
                    usage = None

            sources = row["sources"]
            if isinstance(sources, str):
                try:
                    sources = json.loads(sources)
                except (json.JSONDecodeError, TypeError):
                    sources = None

            chats.append({
                "id": row["id"],
                "chat_id": row["chat_id"],
                "chat_title": row["chat_title"],
                "role": row["role"],
                "content": content,
                "model_id": row["model_id"],
                "sources": sources,
                "usage": usage,
                "created_at": datetime.fromtimestamp(
                    row["created_at"], tz=timezone.utc
                ).isoformat() if row["created_at"] else None,
            })

        conn.close()
        logger.info(f"[ReportAgent] {len(chats)} mensajes leídos de Open WebUI (desde {since.isoformat()})")

    except Exception as e:
        logger.error(f"[ReportAgent] Error leyendo webui.db: {e}", exc_info=True)

    return chats


# ── Lectura de critic_log ──


def _read_critic_log(since: datetime) -> list[dict]:
    """Lee entradas del critic_log de las últimas 24h."""
    entries = []
    if not _CRITIC_LOG.exists():
        return entries

    since_str = since.isoformat()

    try:
        with open(_CRITIC_LOG) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    if ts >= since_str:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"[ReportAgent] Error leyendo critic_log: {e}")

    return entries


# ── Lectura de gold captures ──


def _read_gold_captures(since: datetime) -> dict:
    """Lee gold_sft y gold_dpo de las últimas 24h."""
    result = {"sft": [], "dpo": []}
    since_str = since.isoformat()

    for path, key in [(_GOLD_SFT, "sft"), (_GOLD_DPO, "dpo")]:
        if not path.exists():
            continue
        try:
            with open(path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts = entry.get("timestamp", entry.get("metadata", {}).get("timestamp", ""))
                        if ts >= since_str:
                            result[key].append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"[ReportAgent] Error leyendo {path.name}: {e}")

    return result


# ── Lectura de knowledge reports ──


def _read_knowledge_reports(since: datetime) -> list[dict]:
    """Lee reportes del knowledge agent de las últimas 24h."""
    reports = []
    if not _KNOWLEDGE_REPORTS.exists():
        return reports

    for f in sorted(_KNOWLEDGE_REPORTS.glob("*.json")):
        try:
            report = json.loads(f.read_text())
            started = report.get("started_at", "")
            if started >= since.isoformat():
                reports.append(report)
        except Exception:
            continue

    return reports


# ── Datos de comportamiento animal ──


async def _read_behavior_data(since: datetime) -> dict:
    """Recopila datos conductuales, mating, ML y visión de las últimas 24h."""
    behavior_data: dict = {
        "behavior_summary": {},
        "mating": {},
        "mating_7d": {},
        "ml_anomalies": [],
        "ml_hierarchy": [],
        "curated_crops": {},
        "bird_registry": {},
        "identification_loop": {},
    }

    gallineros = ["gallinero_durrif_1", "gallinero_durrif_2"]

    # ── 1. Resumen conductual (7 dimensiones) ──
    try:
        from services.behavior_inference import get_group_behavior_summary
        from services.behavior_serializer import to_dashboard_summary

        for gall in gallineros:
            inferences = get_group_behavior_summary(gall, "24h")
            if inferences:
                behavior_data["behavior_summary"][gall] = to_dashboard_summary(inferences)
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo behavior summary: {e}")

    # ── 2. Mating (últimas 24h + 7 días) ──
    try:
        from services.mating_detector import get_mating_summary

        for gall in gallineros:
            summary_24h = get_mating_summary(gall, days=1)
            if summary_24h.get("total_events", 0) > 0:
                behavior_data["mating"][gall] = summary_24h

            summary_7d = get_mating_summary(gall, days=7)
            if summary_7d.get("total_events", 0) > 0:
                behavior_data["mating_7d"][gall] = summary_7d
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo mating: {e}")

    # ── 3. Anomalías ML ──
    try:
        from services.behavior_ml import get_behavior_ml_engine

        engine = get_behavior_ml_engine()
        for gall in gallineros:
            anomalies = engine.get_recent_anomalies(gall, hours=24)
            if anomalies:
                behavior_data["ml_anomalies"].extend(anomalies)
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo ML anomalies: {e}")

    # ── 4. Jerarquía social (PageRank) ──
    try:
        from services.behavior_ml import get_behavior_ml_engine

        engine = get_behavior_ml_engine()
        for gall in gallineros:
            flock_model = engine._flock_models.get(gall)
            if flock_model:
                hierarchy = flock_model.get_hierarchy()
                if hierarchy:
                    behavior_data["ml_hierarchy"].extend(
                        [{**h, "gallinero": gall} for h in hierarchy]
                    )
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo hierarchy: {e}")

    # ── 5. Crops curados (para fine-tune YOLO) ──
    try:
        from services.crop_curator import get_crop_curator

        curator = get_crop_curator()
        behavior_data["curated_crops"] = curator.get_stats()
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo curated crops: {e}")

    # ── 6. Registro de aves + comportamiento individual ──
    try:
        registry_path = _DATA_DIR / "birds_registry.json"
        if registry_path.exists():
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            birds = registry.get("birds", [])
            breed_counts = Counter(b.get("breed", "?") for b in birds)

            # Recoger inferencias de comportamiento y mating por ave
            bird_behavior_map: dict[str, dict] = {}
            bird_mating_map: dict[str, dict] = {}
            try:
                from services.behavior_inference import get_bird_behavior
                from services.mating_detector import query_mating_events
                from collections import defaultdict as _defaultdict

                # Agrupar aves por gallinero para eficiencia
                birds_by_gall: dict[str, list] = {}
                for b in birds:
                    gall = b.get("gallinero", "sin_asignar")
                    birds_by_gall.setdefault(gall, []).append(b)

                end_ts = datetime.now(timezone.utc)
                start_7d = end_ts - timedelta(days=7)

                for gall, gall_birds in birds_by_gall.items():
                    # Mating events del gallinero (7 días, una sola lectura)
                    mating_events = query_mating_events(gall, start_7d, end_ts)
                    # Indexar montas por ave
                    for evt in mating_events:
                        mounter_id = evt.get("mounter", {}).get("bird_id", "")
                        mounted_id = evt.get("mounted", {}).get("bird_id", "")
                        if mounter_id:
                            m = bird_mating_map.setdefault(mounter_id, {"as_mounter": 0, "as_mounted": 0, "partners": set()})
                            m["as_mounter"] += 1
                            if mounted_id:
                                m["partners"].add(mounted_id)
                        if mounted_id:
                            m = bird_mating_map.setdefault(mounted_id, {"as_mounter": 0, "as_mounted": 0, "partners": set()})
                            m["as_mounted"] += 1
                            if mounter_id:
                                m["partners"].add(mounter_id)

                    # Inferencias conductuales por ave
                    for b in gall_birds:
                        bid = b.get("bird_id", "?")
                        try:
                            inference = get_bird_behavior(bid, gall, "24h")
                            # Extraer solo las inferencias relevantes (no "normal")
                            relevant = {}
                            for dim, result in inference.inferences.items():
                                if result.label not in ("normal", "social_normal", "no_nesting", "normal_nesting"):
                                    relevant[dim] = {
                                        "label": result.label,
                                        "confidence": result.confidence,
                                        "score": result.score,
                                    }
                            bird_behavior_map[bid] = {
                                "data_completeness": inference.data_completeness,
                                "relevant_inferences": relevant,
                                "anomalies": inference.anomalies[:3],
                                "observations": inference.observations[:3],
                            }
                        except Exception:
                            pass  # Sin datos de tracker, no hay inferencia
            except Exception as e:
                logger.warning(f"[ReportAgent] Error enriqueciendo aves con behavior: {e}")

            # Convertir sets a listas para JSON serialization
            for mid, mdata in bird_mating_map.items():
                mdata["partners"] = sorted(mdata["partners"])

            behavior_data["bird_registry"] = {
                "total": len(birds),
                "by_breed": dict(breed_counts.most_common()),
                "by_gallinero": dict(Counter(
                    b.get("gallinero", "sin_asignar") for b in birds
                )),
                "birds": [
                    {
                        "bird_id": b.get("bird_id", "?"),
                        "breed": b.get("breed", "?"),
                        "sex": b.get("sex", "?"),
                        "color": b.get("color", "?"),
                        "gallinero": b.get("gallinero", "sin_asignar"),
                        "first_seen": (b.get("first_seen") or "")[:10],
                        "last_seen": (b.get("last_seen") or "")[:10],
                        "confidence": b.get("confidence", 0),
                        "behavior": bird_behavior_map.get(b.get("bird_id", ""), {}),
                        "mating": bird_mating_map.get(b.get("bird_id", ""), {}),
                    }
                    for b in birds
                ],
            }
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo bird registry: {e}")

    # ── 7. Behavior event store stats ──
    try:
        from services.behavior_event_store import get_event_store

        store = get_event_store()
        for gall in gallineros:
            snapshots = store.query(gall, since, datetime.now(timezone.utc))
            if gall not in behavior_data.get("behavior_events", {}):
                behavior_data.setdefault("behavior_events", {})
            behavior_data["behavior_events"][gall] = len(snapshots)
    except Exception as e:
        logger.warning(f"[ReportAgent] Error leyendo behavior events: {e}")

    return behavior_data


# ── Estado de Qdrant ──


def _get_qdrant_stats() -> dict:
    """Obtiene conteo de chunks por colección."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient("qdrant", port=6333)
        collections = client.get_collections().collections
        stats = {}
        for col in collections:
            info = client.get_collection(col.name)
            stats[col.name] = info.points_count
        return stats
    except Exception as e:
        logger.error(f"[ReportAgent] Error consultando Qdrant: {e}")
        return {}


# ═══════════════════════════════════════════════════════
# Análisis de conversaciones
# ═══════════════════════════════════════════════════════


def _analyze_conversations(
    messages: list[dict],
    critic_entries: list[dict],
    gold: dict,
    knowledge_reports: list[dict],
    qdrant_stats: dict,
) -> dict:
    """
    Analiza las conversaciones y genera métricas + mejoras.

    Returns dict con secciones del informe.
    """
    analysis = {
        "periodo": {},
        "actividad": {},
        "categorias": {},
        "critic": {},
        "gold_capture": {},
        "knowledge_agent": {},
        "qdrant": {},
        "behavior": {},
        "queries_sin_respuesta": [],
        "temas_recurrentes": [],
        "mejoras_propuestas": [],
        "mejoras_ejecutadas": [],
    }

    # ── Periodo ──
    now = datetime.now(timezone.utc)
    analysis["periodo"] = {
        "desde": (now - timedelta(hours=24)).isoformat(),
        "hasta": now.isoformat(),
        "generado": now.isoformat(),
    }

    # ── Actividad ──
    user_msgs = [m for m in messages if m["role"] == "user"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    unique_chats = set(m["chat_id"] for m in messages)

    analysis["actividad"] = {
        "total_mensajes": len(messages),
        "mensajes_usuario": len(user_msgs),
        "respuestas_asistente": len(assistant_msgs),
        "conversaciones_unicas": len(unique_chats),
        "títulos_chats": list(set(
            m.get("chat_title", "Sin título") for m in messages
        ))[:20],
    }

    # ── Categorías (del critic_log) ──
    cat_counter = Counter()
    for entry in critic_entries:
        cat = entry.get("category", "UNKNOWN")
        cat_counter[cat] += 1
    analysis["categorias"] = dict(cat_counter.most_common(15))

    # ── Critic ──
    total_critic = len(critic_entries)
    blocked = [e for e in critic_entries if e.get("blocked")]
    passed = total_critic - len(blocked)

    block_reasons = Counter()
    for b in blocked:
        for r in (b.get("structural", {}).get("reasons", []) +
                  b.get("technical", {}).get("reasons", [])):
            block_reasons[r] += 1

    latencies = [e.get("latency_ms", 0) for e in critic_entries if e.get("latency_ms")]
    avg_latency = sum(latencies) / max(1, len(latencies))

    analysis["critic"] = {
        "total_evaluaciones": total_critic,
        "pass": passed,
        "block": len(blocked),
        "tasa_bloqueo": f"{len(blocked)/max(1,total_critic)*100:.1f}%",
        "razones_bloqueo": dict(block_reasons.most_common(10)),
        "latencia_media_ms": int(avg_latency),
    }

    # ── Gold Capture ──
    analysis["gold_capture"] = {
        "sft_nuevos": len(gold.get("sft", [])),
        "dpo_nuevos": len(gold.get("dpo", [])),
    }

    # ── Knowledge Agent ──
    total_indexed = sum(r.get("chunks_indexed", 0) for r in knowledge_reports)
    total_promoted = sum(r.get("chunks_promoted", 0) for r in knowledge_reports)
    total_searches = sum(r.get("searches_performed", 0) for r in knowledge_reports)
    total_errors = sum(len(r.get("errors", [])) for r in knowledge_reports)
    all_gaps = []
    for r in knowledge_reports:
        all_gaps.extend(r.get("gaps_detected", []))

    analysis["knowledge_agent"] = {
        "ciclos": len(knowledge_reports),
        "busquedas": total_searches,
        "chunks_indexados": total_indexed,
        "chunks_promovidos": total_promoted,
        "errores": total_errors,
        "gaps_detectados": [
            {"tema": g["topic"], "score": round(g["score"], 2), "razon": g["reason"]}
            for g in all_gaps
        ],
    }

    # ── Qdrant ──
    total_chunks = sum(qdrant_stats.values())
    analysis["qdrant"] = {
        "total_chunks": total_chunks,
        "por_coleccion": dict(sorted(qdrant_stats.items(), key=lambda x: -x[1])),
    }

    # ── Behavior (se inyecta directamente desde run_report) ──
    # analysis["behavior"] se rellena fuera de esta función

    # ── Queries sin buena respuesta ──
    # Identificar queries donde el LLM admitió no saber
    no_answer_patterns = [
        "no puedo", "no se proporciona", "no hay información",
        "evidencia insuficiente", "no dispongo", "no tengo datos",
        "información disponible no cubre", "no es posible determinar",
    ]
    for entry in critic_entries:
        final = entry.get("final", "").lower()
        if any(p in final for p in no_answer_patterns):
            analysis["queries_sin_respuesta"].append({
                "query": entry.get("query", "")[:150],
                "category": entry.get("category", ""),
            })

    # ── Temas recurrentes ──
    topic_words = Counter()
    for m in user_msgs:
        content = m.get("content", "")
        if isinstance(content, str):
            words = re.findall(r'\b[a-záéíóúñ]{4,}\b', content.lower())
            topic_words.update(words)

    # Eliminar stopwords comunes
    for sw in ["como", "para", "quiero", "puedes", "sobre", "tiene", "hacer",
               "dime", "dame", "hola", "seedy", "cuál", "qué", "cómo"]:
        topic_words.pop(sw, None)

    analysis["temas_recurrentes"] = [
        {"tema": word, "frecuencia": count}
        for word, count in topic_words.most_common(15)
    ]

    return analysis


# ═══════════════════════════════════════════════════════
# Proponer y ejecutar mejoras automáticas
# ═══════════════════════════════════════════════════════


async def _propose_and_execute_improvements(analysis: dict) -> list[dict]:
    """
    Analiza el reporte y ejecuta mejoras automáticas:
    - Genera queries de búsqueda para temas sin respuesta
    - Propone SFT examples para preguntas recurrentes
    - Ajusta parámetros si detecta patrones de fallos
    """
    improvements = []

    # 1. Búsquedas para queries sin respuesta
    queries_sin_resp = analysis.get("queries_sin_respuesta", [])
    if queries_sin_resp:
        from services.knowledge_agent import search_for_gap, index_gap_results, TOPIC_COLLECTION_MAP

        unique_queries = {}
        for q in queries_sin_resp:
            cat = q["category"].lower()
            query_text = q["query"]
            if cat not in unique_queries:
                unique_queries[cat] = query_text

        for cat, query_text in list(unique_queries.items())[:5]:
            target_col = TOPIC_COLLECTION_MAP.get(cat, "fresh_web")
            try:
                results = await search_for_gap(query_text, cat)
                if results:
                    indexed = await index_gap_results(results, target_col, cat)
                    improvements.append({
                        "tipo": "busqueda_gap",
                        "query": query_text[:100],
                        "coleccion": target_col,
                        "chunks_indexados": indexed,
                    })
                    logger.info(
                        f"[ReportAgent] Mejora: {indexed} chunks para "
                        f"'{query_text[:50]}' → {target_col}"
                    )
            except Exception as e:
                logger.error(f"[ReportAgent] Error buscando gap: {e}")

    # 2. Detección de bloqueos recurrentes → generar SFT examples
    blocked_queries = [
        q for q in analysis.get("queries_sin_respuesta", [])
        if len(q.get("query", "")) > 20
    ]
    if blocked_queries:
        # Guardar nota para el próximo fine-tune
        note = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tipo": "gap_finetune",
            "queries_problema": [q["query"][:200] for q in blocked_queries[:10]],
            "categorias": [q["category"] for q in blocked_queries[:10]],
            "accion": "Añadir exemplos SFT para estos patrones de query",
        }
        improvements.append({
            "tipo": "nota_finetune",
            "queries": len(blocked_queries),
            "detalle": "Queries problemáticas registradas para próximo dataset SFT",
        })

        notes_file = _REPORT_HISTORY / "finetune_notes.jsonl"
        try:
            with open(notes_file, "a") as f:
                f.write(json.dumps(note, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[ReportAgent] Error guardando nota: {e}")

    return improvements


# ═══════════════════════════════════════════════════════
# Generación del informe HTML
# ═══════════════════════════════════════════════════════


_DIM_ES = {
    "aggressiveness": "Agresividad",
    "dominance": "Dominancia",
    "subordination": "Subordinación",
    "feeding_level": "Ingesta",
    "stress": "Estrés",
    "sociality": "Socialización",
    "nesting_pattern": "Nidificación",
}


def _build_behavior_html(beh: dict) -> str:
    """Genera HTML de comportamiento animal (conductas + mating + anomalías)."""
    if not beh:
        return ""

    sections = []

    # ── Resumen conductual por gallinero ──
    summaries = beh.get("behavior_summary", {})
    events = beh.get("behavior_events", {})

    if summaries:
        for gall_id, summary in summaries.items():
            gall_name = gall_id.replace("gallinero_", "").replace("_", " ").title()
            s = summary.get("summary", {})
            total = s.get("total", 0)
            normal = s.get("normal", 0)
            attention = s.get("attention", 0)
            alert = s.get("alert", 0)
            snapshots = events.get(gall_id, 0)

            sections.append(f"""
<h3>📍 {gall_name}</h3>
<div class="metric-grid">
  <div class="metric"><div class="value">{total}</div><div class="label">Aves analizadas</div></div>
  <div class="metric"><div class="value" style="color:#28a745">{normal}</div><div class="label">Normal</div></div>
  <div class="metric"><div class="value" style="color:#ffc107">{attention}</div><div class="label">Atención</div></div>
  <div class="metric"><div class="value" style="color:#dc3545">{alert}</div><div class="label">Alerta</div></div>
</div>
<p style="font-size:12px;color:#666">Basado en {snapshots:,} snapshots conductuales (últimas 24h)</p>""")

            # Aves con flags
            birds = summary.get("birds", [])
            flagged = [b for b in birds if b.get("flags")]
            if flagged:
                rows = ""
                for b in flagged[:10]:
                    bid = b.get("bird_id", "?")
                    status = b.get("status", "normal")
                    status_icon = {"attention": "🟡", "alert": "🔴"}.get(status, "🟢")
                    flags_str = ", ".join(
                        f"{_DIM_ES.get(f['dimension'], f['dimension'])} ({f['confidence']})"
                        for f in b.get("flags", [])
                    )
                    rows += f"<tr><td>{status_icon} {bid}</td><td>{flags_str}</td></tr>\n"
                sections.append(f"""
<table>
<tr><th>Ave</th><th>Señales conductuales</th></tr>
{rows}
</table>""")

            # Alertas top
            alerts = summary.get("alerts", [])
            if alerts:
                alert_items = "".join(f"<li>{a}</li>" for a in alerts[:5])
                sections.append(f"<div class='alert'><strong>Alertas:</strong><ul>{alert_items}</ul></div>")

    elif events:
        # Sin inferencias pero con snapshots del event store — mostrar resumen básico
        ev_rows = ""
        total_snaps = 0
        for gall_id, count in events.items():
            gall_name = gall_id.replace("gallinero_", "").replace("_", " ").title()
            ev_rows += f"<tr><td>{gall_name}</td><td style='text-align:right'>{count:,}</td></tr>\n"
            total_snaps += count
        sections.append(f"""
<h3>📊 Monitorización activa</h3>
<div class="metric-grid">
  <div class="metric"><div class="value">{total_snaps:,}</div><div class="label">Snapshots conductuales (24h)</div></div>
  <div class="metric"><div class="value">{len(events)}</div><div class="label">Gallineros monitorizados</div></div>
</div>
<table>
<tr><th>Gallinero</th><th>Snapshots (24h)</th></tr>
{ev_rows}
</table>
<p style="font-size:12px;color:#666">Las inferencias de 7 dimensiones conductuales se activarán cuando el tracker acumule suficientes datos en memoria.</p>""")

    # ── Mating (24h + 7 días) ──
    mating_24h = beh.get("mating", {})
    mating_7d = beh.get("mating_7d", {})
    has_mating = any(m.get("total_events", 0) > 0 for m in mating_7d.values()) if mating_7d else False

    if has_mating or mating_24h:
        # Priorizar vista 7 días, con detalle 24h
        mating_src = mating_7d if has_mating else mating_24h
        period_label = "7 días" if has_mating else "24h"
        mating_rows = ""
        total_matings = 0
        for gall_id, m in mating_src.items():
            gall_name = gall_id.replace("gallinero_", "").replace("_", " ").title()
            total_ev = m.get("total_events", 0)
            total_matings += total_ev

            for pair in m.get("pairs", [])[:5]:
                mounter = pair.get("mounter_id", "?")
                mounted = pair.get("mounted_id", "?")
                count = pair.get("count", 0)
                mounter_breed = pair.get("mounter_breed", "")
                mounted_breed = pair.get("mounted_breed", "")
                mating_rows += (
                    f"<tr><td>{gall_name}</td>"
                    f"<td>{mounter} ({mounter_breed})</td>"
                    f"<td>{mounted} ({mounted_breed})</td>"
                    f"<td style='text-align:right'>{count}</td></tr>\n"
                )

        avg_per_day = sum(m.get("avg_per_day", 0) for m in mating_src.values())
        if mating_rows:
            sections.append(f"""
<h3>💞 Actividad reproductiva — últimos {period_label} ({total_matings} eventos)</h3>
<div class="metric-grid">
  <div class="metric"><div class="value">{total_matings}</div><div class="label">Montas totales</div></div>
  <div class="metric"><div class="value">{avg_per_day:.1f}</div><div class="label">Media diaria</div></div>
</div>
<table>
<tr><th>Gallinero</th><th>Gallo (mounter)</th><th>Gallina (mounted)</th><th>Montas</th></tr>
{mating_rows}
</table>""")
        elif total_matings == 0 and not mating_24h:
            sections.append("""
<h3>💞 Actividad reproductiva</h3>
<p>Sin eventos de monta detectados en las últimas 24h.</p>""")

    # ── Anomalías ML ──
    anomalies = beh.get("ml_anomalies", [])
    if anomalies:
        anom_rows = ""
        for a in anomalies[:10]:
            bid = a.get("bird_id", "?")
            score = a.get("score", 0)
            explanation = a.get("type", "Sin detalle")
            anom_rows += f"<tr><td>{bid}</td><td>{score:.2f}</td><td>{explanation}</td></tr>\n"
        sections.append(f"""
<h3>🔬 Anomalías ML detectadas ({len(anomalies)})</h3>
<table>
<tr><th>Ave</th><th>Score</th><th>Tipo</th></tr>
{anom_rows}
</table>""")

    # ── Jerarquía social ──
    hierarchy = beh.get("ml_hierarchy", [])
    if hierarchy:
        hier_rows = ""
        for i, h in enumerate(hierarchy[:10], 1):
            bid = h.get("bird_id", "?")
            score = h.get("dominance_score", 0)
            gall = h.get("gallinero", "").replace("gallinero_", "").replace("_", " ").title()
            hier_rows += f"<tr><td>{i}</td><td>{bid}</td><td>{gall}</td><td>{score:.3f}</td></tr>\n"
        sections.append(f"""
<h3>👑 Jerarquía social (PageRank)</h3>
<table>
<tr><th>#</th><th>Ave</th><th>Gallinero</th><th>Score</th></tr>
{hier_rows}
</table>""")

    if not sections:
        return ""

    return f"""
<h2>🐔 Comportamiento Animal</h2>
{"".join(sections)}
"""


def _build_vision_html(beh: dict) -> str:
    """Genera HTML de Vision Pipeline (registro de aves + crops curados)."""
    if not beh:
        return ""

    OVOSFERA_AVES_URL = "https://hub.ovosfera.com/farm/palacio/aves"
    sections = []

    # ── Registro de aves ──
    registry = beh.get("bird_registry", {})
    if registry and registry.get("total", 0) > 0:
        total_birds = registry.get("total", 0)
        by_breed = registry.get("by_breed", {})
        by_gall = registry.get("by_gallinero", {})
        birds = registry.get("birds", [])

        gall_items = ", ".join(
            f"{g.replace('gallinero_', '').replace('_', ' ').title()}: {c}"
            for g, c in by_gall.items()
        )

        # Resumen KPI
        males = sum(1 for b in birds if b.get("sex") == "male")
        females = sum(1 for b in birds if b.get("sex") == "female")
        active_24h = sum(1 for b in birds if b.get("last_seen", "") >= (
            datetime.now(timezone.utc) - timedelta(hours=24)
        ).strftime("%Y-%m-%d"))

        sections.append(f"""
<div class="metric-grid">
  <div class="metric"><div class="value">{total_birds}</div><div class="label">Aves registradas</div></div>
  <div class="metric"><div class="value">{len(by_breed)}</div><div class="label">Razas detectadas</div></div>
  <div class="metric"><div class="value">{males}♂ / {females}♀</div><div class="label">Machos / Hembras</div></div>
  <div class="metric"><div class="value">{active_24h}</div><div class="label">Vistas hoy</div></div>
</div>
<p style="font-size:12px;color:#666">Distribución: {gall_items} ·
  <a href="{OVOSFERA_AVES_URL}" style="color:#4a8c1c">Ver fichas en OvoSfera →</a>
</p>""")

        # Tabla detallada de razas
        breed_rows = ""
        for breed, count in sorted(by_breed.items(), key=lambda x: -x[1]):
            breed_birds = [b for b in birds if b.get("breed") == breed]
            breed_males = sum(1 for b in breed_birds if b.get("sex") == "male")
            breed_females = sum(1 for b in breed_birds if b.get("sex") == "female")
            colors = set(b.get("color", "") for b in breed_birds if b.get("color"))
            color_str = ", ".join(sorted(colors)[:3]) if colors else "—"
            breed_rows += (
                f"<tr><td><strong>{breed}</strong></td>"
                f"<td style='text-align:center'>{count}</td>"
                f"<td style='text-align:center'>{breed_males}♂ / {breed_females}♀</td>"
                f"<td>{color_str}</td></tr>\n"
            )

        sections.append(f"""
<table>
<tr><th>Raza</th><th>Total</th><th>Sexo</th><th>Colores</th></tr>
{breed_rows}
</table>""")

        # Tabla individual de aves con comportamiento y montas
        # Helper para badge de comportamiento
        _DIM_ICONS = {
            "aggressiveness": "⚔️",
            "dominance": "👑",
            "subordination": "🔽",
            "feeding_level": "🍽️",
            "stress": "⚠️",
            "sociality": "🤝",
            "nesting_pattern": "🪺",
        }
        _DIM_LABELS_ES = {
            "possible_aggressive": "Agresiva",
            "probable_dominant": "Dominante",
            "possible_dominant": "Dominante?",
            "possible_subordinate": "Subordinada",
            "low_feeding": "↓Alimentación",
            "high_feeding": "↑Alimentación",
            "possible_stress": "Estrés?",
            "high_stress": "Estrés!",
            "possible_asocial": "Asocial?",
            "possible_highly_social": "Muy social",
            "possible_early_brooding": "Clueca?",
        }

        bird_rows = ""
        for b in sorted(birds, key=lambda x: x.get("bird_id", "")):
            bid = b.get("bird_id", "?")
            breed = b.get("breed", "?")
            sex_icon = "♂" if b.get("sex") == "male" else "♀"
            color = b.get("color", "—")
            gall = b.get("gallinero", "").replace("gallinero_", "").replace("_", " ").title()
            if gall.startswith("Sauna"):
                gall = "Sauna"
            last = b.get("last_seen", "—")
            conf = b.get("confidence", 0)
            conf_bar = "🟢" if conf >= 0.8 else ("🟡" if conf >= 0.5 else "🔴")

            # Comportamiento
            beh_data = b.get("behavior", {})
            beh_badges = ""
            if beh_data:
                relevant = beh_data.get("relevant_inferences", {})
                if relevant:
                    badges = []
                    for dim, inf in relevant.items():
                        icon = _DIM_ICONS.get(dim, "🔵")
                        label = _DIM_LABELS_ES.get(inf.get("label", ""), inf.get("label", ""))
                        badges.append(f'{icon}{label}')
                    beh_badges = " ".join(badges)
                elif beh_data.get("data_completeness", 0) > 0:
                    beh_badges = '<span style="color:#999">✅ Normal</span>'

            if not beh_badges:
                beh_badges = '<span style="color:#ccc">—</span>'

            # Montas
            mat = b.get("mating", {})
            mat_str = ""
            if mat:
                as_m = mat.get("as_mounter", 0)
                as_f = mat.get("as_mounted", 0)
                partners = mat.get("partners", [])
                parts = []
                if as_m > 0:
                    parts.append(f"🐓 Monta ×{as_m}")
                if as_f > 0:
                    parts.append(f"🐔 Montada ×{as_f}")
                if partners:
                    parts.append(f"({len(partners)} parejas)")
                mat_str = " ".join(parts)
            if not mat_str:
                mat_str = '<span style="color:#ccc">—</span>'

            bird_rows += (
                f"<tr>"
                f"<td><strong>{bid}</strong></td>"
                f"<td>{breed}</td>"
                f"<td style='text-align:center'>{sex_icon}</td>"
                f"<td>{color}</td>"
                f"<td>{gall}</td>"
                f"<td>{last}</td>"
                f"<td style='text-align:center'>{conf_bar} {conf:.0%}</td>"
                f"<td style='font-size:11px'>{beh_badges}</td>"
                f"<td style='font-size:11px'>{mat_str}</td>"
                f"</tr>\n"
            )

        sections.append(f"""
<h3>📋 Registro individual de aves</h3>
<p style="font-size:12px;color:#666">Cada ave identificada por IA (YOLO + Gemini). Comportamiento: 7 dimensiones (24h). Montas: últimos 7 días.
  <a href="{OVOSFERA_AVES_URL}" style="color:#4a8c1c">Abrir fichas completas →</a>
</p>
<table>
<tr><th>ID</th><th>Raza</th><th>Sexo</th><th>Color</th><th>Gallinero</th><th>Última vista</th><th>Confianza</th><th>Comportamiento</th><th>Montas (7d)</th></tr>
{bird_rows}
</table>""")

    # ── Crops curados ──
    crops = beh.get("curated_crops", {})
    if crops and crops.get("total", 0) > 0:
        crop_total = crops.get("total", 0)
        by_breed_crops = crops.get("by_breed", {})
        crop_rows = ""
        for breed, count in sorted(by_breed_crops.items(), key=lambda x: -x[1]):
            crop_rows += f"<tr><td>{breed}</td><td style='text-align:right'>{count}</td></tr>\n"

        sections.append(f"""
<h3>📸 Dataset curado (crops para YOLO fine-tune)</h3>
<div class="metric-grid">
  <div class="metric"><div class="value">{crop_total}</div><div class="label">Crops curados total</div></div>
  <div class="metric"><div class="value">{len(by_breed_crops)}</div><div class="label">Razas cubiertas</div></div>
</div>
<table>
<tr><th>Raza</th><th>Crops</th></tr>
{crop_rows}
</table>""")

    if not sections:
        return ""

    return f"""
<h2>👁️ Vision Pipeline</h2>
{"".join(sections)}
"""


def _build_html_report(analysis: dict, improvements: list[dict]) -> str:
    """Genera un informe HTML legible para email."""

    act = analysis["actividad"]
    critic = analysis["critic"]
    gold = analysis["gold_capture"]
    ka = analysis["knowledge_agent"]
    qdrant = analysis["qdrant"]
    beh = analysis.get("behavior", {})

    # Tabla de Qdrant
    qdrant_rows = ""
    for col, count in qdrant.get("por_coleccion", {}).items():
        qdrant_rows += f"<tr><td>{col}</td><td style='text-align:right'>{count:,}</td></tr>\n"

    # Tabla de categorías
    cat_rows = ""
    for cat, count in analysis.get("categorias", {}).items():
        cat_rows += f"<tr><td>{cat}</td><td style='text-align:right'>{count}</td></tr>\n"

    # Queries sin respuesta
    no_resp_rows = ""
    for q in analysis.get("queries_sin_respuesta", [])[:10]:
        no_resp_rows += f"<tr><td>{q['category']}</td><td>{q['query'][:120]}</td></tr>\n"

    # Mejoras ejecutadas
    improvements_rows = ""
    for imp in improvements:
        tipo = imp.get("tipo", "")
        if tipo == "busqueda_gap":
            improvements_rows += (
                f"<tr><td>Búsqueda</td>"
                f"<td>{imp['query'][:80]}</td>"
                f"<td>{imp['chunks_indexados']} chunks → {imp['coleccion']}</td></tr>\n"
            )
        elif tipo == "nota_finetune":
            improvements_rows += (
                f"<tr><td>Nota SFT</td>"
                f"<td>{imp['queries']} queries problema</td>"
                f"<td>Registradas para próximo fine-tune</td></tr>\n"
            )

    # Gaps del knowledge agent
    gaps_rows = ""
    for g in ka.get("gaps_detectados", [])[:10]:
        score_pct = f"{g['score']*100:.0f}%"
        gaps_rows += f"<tr><td>{g['tema']}</td><td>{score_pct}</td><td>{g['razon']}</td></tr>\n"

    # Temas recurrentes
    temas_rows = ""
    for t in analysis.get("temas_recurrentes", [])[:10]:
        temas_rows += f"<tr><td>{t['tema']}</td><td style='text-align:right'>{t['frecuencia']}</td></tr>\n"

    # ── Sección Comportamiento Animal ──
    behavior_html = _build_behavior_html(beh)

    # ── Sección Vision Pipeline ──
    vision_html = _build_vision_html(beh)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 800px; margin: 20px auto; color: #333; line-height: 1.5; }}
  h1 {{ color: #2d5016; border-bottom: 3px solid #4a8c1c; padding-bottom: 8px; }}
  h2 {{ color: #4a8c1c; margin-top: 30px; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                  gap: 12px; margin: 15px 0; }}
  .metric {{ background: #f8faf5; border: 1px solid #d4e8c4; border-radius: 8px;
             padding: 15px; text-align: center; }}
  .metric .value {{ font-size: 28px; font-weight: bold; color: #2d5016; }}
  .metric .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 13px; }}
  th {{ background: #4a8c1c; color: white; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .alert {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
            padding: 12px; margin: 10px 0; }}
  .success {{ background: #d4edda; border: 1px solid #28a745; border-radius: 6px;
              padding: 12px; margin: 10px 0; }}
  .footer {{ margin-top: 40px; padding-top: 15px; border-top: 1px solid #ddd;
             font-size: 11px; color: #999; }}
</style>
</head>
<body>

<h1>🌱 Seedy — Informe Diario</h1>
<p style="color:#666">Periodo: {analysis['periodo']['desde'][:16]} → {analysis['periodo']['hasta'][:16]} UTC</p>

<h2>📊 Actividad</h2>
<div class="metric-grid">
  <div class="metric"><div class="value">{act['total_mensajes']}</div><div class="label">Mensajes totales</div></div>
  <div class="metric"><div class="value">{act['mensajes_usuario']}</div><div class="label">Preguntas usuario</div></div>
  <div class="metric"><div class="value">{act['conversaciones_unicas']}</div><div class="label">Conversaciones</div></div>
  <div class="metric"><div class="value">{critic['total_evaluaciones']}</div><div class="label">Evaluaciones critic</div></div>
</div>

<h2>🛡️ Critic Gate</h2>
<div class="metric-grid">
  <div class="metric"><div class="value">{critic['pass']}</div><div class="label">PASS</div></div>
  <div class="metric"><div class="value" style="color:#c0392b">{critic['block']}</div><div class="label">BLOCK</div></div>
  <div class="metric"><div class="value">{critic['tasa_bloqueo']}</div><div class="label">Tasa bloqueo</div></div>
  <div class="metric"><div class="value">{critic['latencia_media_ms']}ms</div><div class="label">Latencia media</div></div>
</div>
{"<h3>Razones de bloqueo</h3><table><tr><th>Razón</th><th>Count</th></tr>" + "".join(f"<tr><td>{r}</td><td>{c}</td></tr>" for r,c in critic.get('razones_bloqueo',{}).items()) + "</table>" if critic.get('razones_bloqueo') else ""}

<h2>🎯 Gold Capture (70B → 14B)</h2>
<div class="metric-grid">
  <div class="metric"><div class="value">{gold['sft_nuevos']}</div><div class="label">Nuevos SFT</div></div>
  <div class="metric"><div class="value">{gold['dpo_nuevos']}</div><div class="label">Nuevos DPO</div></div>
</div>

{behavior_html}

{vision_html}

<h2>📚 Categorías de consulta</h2>
<table>
<tr><th>Categoría</th><th>Consultas</th></tr>
{cat_rows}
</table>

<h2>🔍 Knowledge Agent</h2>
<div class="metric-grid">
  <div class="metric"><div class="value">{ka['ciclos']}</div><div class="label">Ciclos ejecutados</div></div>
  <div class="metric"><div class="value">{ka['busquedas']}</div><div class="label">Búsquedas</div></div>
  <div class="metric"><div class="value">{ka['chunks_indexados']}</div><div class="label">Chunks indexados</div></div>
  <div class="metric"><div class="value">{ka['chunks_promovidos']}</div><div class="label">Promovidos fresh→main</div></div>
</div>
{"<h3>Gaps detectados</h3><table><tr><th>Tema</th><th>Score</th><th>Razón</th></tr>" + gaps_rows + "</table>" if gaps_rows else ""}

<h2>💾 Qdrant — Estado de colecciones</h2>
<table>
<tr><th>Colección</th><th>Chunks</th></tr>
{qdrant_rows}
<tr style="font-weight:bold"><td>TOTAL</td><td style="text-align:right">{qdrant['total_chunks']:,}</td></tr>
</table>

{"<h2>⚠️ Queries sin respuesta adecuada</h2><div class='alert'>Estas queries no obtuvieron respuesta satisfactoria. El reporting agent ha buscado contenido para cubrirlas.</div><table><tr><th>Categoría</th><th>Query</th></tr>" + no_resp_rows + "</table>" if no_resp_rows else ""}

{"<h2>✅ Mejoras ejecutadas automáticamente</h2><div class='success'>El reporting agent ha ejecutado estas mejoras basadas en el análisis de las conversaciones.</div><table><tr><th>Tipo</th><th>Detalle</th><th>Resultado</th></tr>" + improvements_rows + "</table>" if improvements_rows else ""}

{"<h2>🔤 Temas recurrentes</h2><table><tr><th>Tema</th><th>Frecuencia</th></tr>" + temas_rows + "</table>" if temas_rows else ""}

<div class="footer">
  Generado automáticamente por Seedy Reporting Agent · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
  <br>Backend: seedy-backend · LLM: seedy:v16 (Qwen2.5-14B) · Qdrant: {qdrant['total_chunks']:,} chunks
</div>

</body>
</html>"""
    return html


# ═══════════════════════════════════════════════════════
# Envío de email
# ═══════════════════════════════════════════════════════


def _send_email(subject: str, html_body: str, to_email: str) -> bool:
    """Envía un email HTML vía SMTP (Gmail)."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning(
            "[ReportAgent] SMTP no configurado (SMTP_USER/SMTP_PASS vacíos). "
            "Informe guardado localmente pero NO enviado por email."
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to_email

    # Versión texto plano (fallback)
    text_part = MIMEText(
        "Este informe requiere un cliente de email con soporte HTML.", "plain", "utf-8"
    )
    html_part = MIMEText(html_body, "html", "utf-8")

    msg.attach(text_part)
    msg.attach(html_part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())

        logger.info(f"[ReportAgent] Email enviado a {to_email}")
        return True

    except Exception as e:
        logger.error(f"[ReportAgent] Error enviando email: {e}", exc_info=True)
        return False


# ═══════════════════════════════════════════════════════
# Orchestrator — ciclo completo
# ═══════════════════════════════════════════════════════


async def run_report() -> dict:
    """
    Ejecuta un ciclo completo del reporting agent:
    1. Lee datos de las últimas 24h
    2. Analiza conversaciones y métricas
    3. Ejecuta mejoras automáticas
    4. Genera y envía informe por email
    5. Guarda copia local del reporte
    """
    t0 = datetime.now(timezone.utc)
    since = t0 - timedelta(hours=24)

    logger.info("[ReportAgent] ═══ Iniciando ciclo de reporting ═══")

    # 1. Recolectar datos
    messages = _read_webui_chats(since)
    critic_entries = _read_critic_log(since)
    gold = _read_gold_captures(since)
    knowledge_reports = _read_knowledge_reports(since)
    qdrant_stats = _get_qdrant_stats()

    # 2. Análisis
    analysis = _analyze_conversations(
        messages, critic_entries, gold, knowledge_reports, qdrant_stats
    )

    # 2b. Datos de comportamiento animal
    behavior_data = await _read_behavior_data(since)
    analysis["behavior"] = behavior_data

    # 3. Mejoras automáticas
    improvements = await _propose_and_execute_improvements(analysis)
    analysis["mejoras_ejecutadas"] = improvements

    # 4. Generar informe HTML
    html = _build_html_report(analysis, improvements)

    # 5. Enviar por email
    fecha = t0.strftime("%d/%m/%Y")
    subject = f"🌱 Seedy Informe Diario — {fecha}"
    email_sent = _send_email(subject, html, REPORT_EMAIL)

    # 6. Guardar copia local (siempre)
    report_data = {
        "analysis": analysis,
        "improvements": improvements,
        "email_sent": email_sent,
        "email_to": REPORT_EMAIL,
    }

    report_file = _REPORT_HISTORY / f"report_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    html_file = _REPORT_HISTORY / f"report_{t0.strftime('%Y%m%d_%H%M%S')}.html"
    try:
        report_file.write_text(json.dumps(report_data, ensure_ascii=False, indent=2))
        html_file.write_text(html)
        logger.info(f"[ReportAgent] Reporte guardado: {report_file.name}")
    except Exception as e:
        logger.error(f"[ReportAgent] Error guardando reporte: {e}")

    t1 = datetime.now(timezone.utc)
    duration = (t1 - t0).total_seconds()

    logger.info(
        f"[ReportAgent] ═══ Ciclo completado en {duration:.0f}s: "
        f"{analysis['actividad']['total_mensajes']} msgs, "
        f"{len(critic_entries)} critic, "
        f"{len(improvements)} mejoras, "
        f"email={'OK' if email_sent else 'NO_SMTP'} ═══"
    )

    return report_data


# ═══════════════════════════════════════════════════════
# Loop asyncio — para auto_learn.py
# ═══════════════════════════════════════════════════════


async def reporting_agent_loop():
    """Loop periódico del reporting agent. Lanzar desde auto_learn.py."""
    # Esperar 60min tras arranque para que haya datos
    await asyncio.sleep(3600)
    logger.info(f"[ReportAgent] Loop iniciado — intervalo={REPORT_INTERVAL // 3600}h")

    while True:
        try:
            await run_report()
        except Exception as e:
            logger.error(f"[ReportAgent] Error en ciclo: {e}", exc_info=True)

        await asyncio.sleep(REPORT_INTERVAL)
