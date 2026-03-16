"""Pipeline de autoingesta — Daily Brief: resumen diario en Markdown."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from pipelines.ingest.settings import get_settings
from pipelines.ingest.state_db import StateDB

logger = logging.getLogger(__name__)


def generate_brief(db: StateDB) -> str:
    """
    Genera un brief diario en Markdown con los artículos indexados hoy.
    Lo guarda en briefs/YYYY-MM-DD.md y devuelve el path.
    """
    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Stats del día
    stats = db.get_today_stats()
    indexed_docs = db.get_today_indexed()

    # Agrupar por colección
    by_collection: dict[str, list[dict]] = {}
    for doc in indexed_docs:
        col = doc.get("collection", "otros")
        by_collection.setdefault(col, []).append(doc)

    # Generar markdown
    lines = [
        f"# 📰 Seedy Daily Brief — {today}",
        "",
        "## Resumen",
        "",
        f"| Métrica | Valor |",
        f"|---------|-------|",
        f"| Indexados | {stats.get('indexed', 0)} |",
        f"| Cuarentena | {stats.get('quarantine', 0)} |",
        f"| Rechazados | {stats.get('rejected', 0)} |",
        f"| Errores | {stats.get('error', 0)} |",
        "",
    ]

    if not indexed_docs:
        lines.append("*Sin artículos nuevos indexados hoy.*")
    else:
        for collection, docs in sorted(by_collection.items()):
            lines.append(f"## {collection.replace('_', ' ').title()}")
            lines.append("")
            for doc in docs:
                score = doc.get("score", 0)
                title = doc.get("title", "Sin título")
                source = doc.get("source_name", "")
                url = doc.get("url", "")
                chunks = doc.get("chunks", 0)
                lines.append(f"- **[{score:.0f}]** [{title}]({url})")
                lines.append(f"  - Fuente: {source} | Chunks: {chunks}")
            lines.append("")

    content = "\n".join(lines)

    # Guardar archivo
    briefs_dir = Path(settings.briefs_dir)
    briefs_dir.mkdir(parents=True, exist_ok=True)
    brief_path = briefs_dir / f"{today}.md"
    brief_path.write_text(content, encoding="utf-8")

    logger.info(f"📝 Brief generado: {brief_path}")
    return str(brief_path)
