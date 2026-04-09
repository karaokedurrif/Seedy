"""
POST /report/generate — convierte Markdown de informe a PDF con identidad NeoFarm.

Recibe { "markdown": "...", "title": "...", "date": "..." }
Devuelve application/pdf.
"""

import io
import logging
from datetime import datetime

import markdown as md_lib
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from weasyprint import HTML

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"])

# ─── NeoFarm brand CSS ────────────────────────────────────────────────────────

NEOFARM_CSS = """
/* ═══════════════════════════════════════════════════════
   NeoFarm — Professional Report Stylesheet v4
   Brand: primary #0F4C4C / accent #1A6B6B / light #E6F2F2
   Designed for WeasyPrint — McKinsey-grade layout
   ═══════════════════════════════════════════════════════ */

/* ─── Page setup ─── */
@page {
    size: A4;
    margin: 2.4cm 2.2cm 2.6cm 2.2cm;

    @top-left {
        content: "NEOFARM";
        font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
        font-size: 7.5pt;
        font-weight: 700;
        color: #0F4C4C;
        letter-spacing: 2.5pt;
    }
    @top-right {
        content: string(doc-subtitle);
        font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
        font-size: 7.5pt;
        color: #999;
    }
    @bottom-left {
        content: "Confidencial — " string(doc-footer);
        font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
        font-size: 7pt;
        color: #bbb;
    }
    @bottom-center {
        content: "";
        border-top: 0.5pt solid #ddd;
        width: 100%;
    }
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
        font-size: 7.5pt;
        color: #999;
    }
}

@page :first {
    margin-top: 0;
    margin-bottom: 0;
    @top-left    { content: none; }
    @top-right   { content: none; }
    @bottom-left { content: none; }
    @bottom-center { content: none; border: none; }
    @bottom-right { content: none; }
}

/* Running strings */
.doc-subtitle { string-set: doc-subtitle content(); display: none; }
.doc-footer   { string-set: doc-footer content();   display: none; }

/* ═══ COVER PAGE ═══ */
.cover {
    page-break-after: always;
    margin: 0 -2.2cm;
    padding: 0;
    height: 100%;
    position: relative;
}
.cover-top-bar {
    background: #0F4C4C;
    height: 8pt;
    width: 100%;
}
.cover-body {
    padding: 4cm 3cm 3cm 3cm;
}
.cover-brand {
    font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 4pt;
    text-transform: uppercase;
    color: #0F4C4C;
    margin-bottom: 0.8cm;
}
.cover-rule {
    width: 60pt;
    height: 3pt;
    background: #0F4C4C;
    margin-bottom: 1.2cm;
}
.cover-title {
    font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
    font-size: 28pt;
    font-weight: 700;
    color: #111;
    line-height: 1.15;
    margin-bottom: 0.5cm;
    max-width: 85%;
}
.cover-subtitle {
    font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
    font-size: 12pt;
    font-weight: 400;
    color: #555;
    line-height: 1.4;
    margin-bottom: 2.5cm;
    max-width: 75%;
}
.cover-meta-box {
    border-top: 1.5pt solid #0F4C4C;
    padding-top: 0.6cm;
    display: flex;
    font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
}
.cover-meta-box .label {
    font-size: 7pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1pt;
    color: #0F4C4C;
    margin-bottom: 2pt;
}
.cover-meta-box .value {
    font-size: 9pt;
    color: #333;
}
.cover-meta-col {
    margin-right: 2cm;
}
.cover-bottom-bar {
    background: #0F4C4C;
    height: 4pt;
    width: 100%;
    position: absolute;
    bottom: 0;
    left: 0;
}
.cover-confidential {
    font-size: 7pt;
    color: #aaa;
    text-transform: uppercase;
    letter-spacing: 1.5pt;
    position: absolute;
    bottom: 1.2cm;
    right: 3cm;
}

/* ═══ BODY ═══ */
body {
    font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.65;
    color: #222;
}

/* ─── Headings ─── */
h1 {
    font-size: 18pt;
    font-weight: 700;
    color: #0F4C4C;
    border-bottom: 2pt solid #0F4C4C;
    padding-bottom: 5pt;
    margin-top: 6pt;
    margin-bottom: 14pt;
    letter-spacing: 0.3pt;
    page-break-after: avoid;
}

h2 {
    font-size: 13pt;
    font-weight: 700;
    color: #0F4C4C;
    margin-top: 28pt;
    margin-bottom: 10pt;
    padding-bottom: 4pt;
    border-bottom: 1pt solid #ccdede;
    page-break-after: avoid;
}

h3 {
    font-size: 10.5pt;
    font-weight: 700;
    color: #1A6B6B;
    margin-top: 18pt;
    margin-bottom: 6pt;
    page-break-after: avoid;
}

h4, h5, h6 {
    font-size: 9.5pt;
    font-weight: 700;
    color: #2a7a7a;
    margin-top: 12pt;
    margin-bottom: 4pt;
    page-break-after: avoid;
}

/* ─── Paragraphs ─── */
p {
    margin-bottom: 8pt;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

strong { color: #111; }
em { color: #555; }

/* ═══ TABLES ═══ */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 14pt 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
}

th {
    background: #0F4C4C;
    color: #fff;
    font-weight: 700;
    padding: 9pt 10pt;
    text-align: left;
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.6pt;
}

td {
    padding: 8pt 10pt;
    border-bottom: 0.5pt solid #dde8e8;
    vertical-align: top;
}

tr:nth-child(even) td {
    background: #f6fafa;
}

/* KPI emphasis: bold values in tables */
td strong {
    color: #0F4C4C;
    font-size: 10.5pt;
}

/* ─── KPI table ─── first table after an h1 gets special treatment */
h1 + table,
h1 + p + table {
    border: 1.5pt solid #0F4C4C;
}
h1 + table th,
h1 + p + table th {
    background: #E6F2F2;
    color: #0F4C4C;
    font-size: 8pt;
    text-align: center;
    letter-spacing: 1pt;
    padding: 10pt 8pt;
}
h1 + table td,
h1 + p + table td {
    text-align: center;
    font-size: 9.5pt;
    padding: 12pt 8pt;
    border-bottom: 0.5pt solid #c0dada;
}
h1 + table td strong,
h1 + p + table td strong {
    font-size: 16pt;
    color: #0F4C4C;
    display: block;
    margin-bottom: 1pt;
    font-weight: 700;
}

/* ═══ BLOCKQUOTES = Callouts ═══ */
blockquote {
    margin: 16pt 0;
    padding: 14pt 18pt 14pt 16pt;
    background: #f4f9f9;
    border-left: 4pt solid #0F4C4C;
    color: #1a3636;
    font-style: normal;
    font-size: 9pt;
    page-break-inside: avoid;
}
blockquote strong {
    color: #0F4C4C;
    font-size: 9.5pt;
    display: inline;
}
blockquote p {
    margin-bottom: 4pt;
    text-align: left;
}
blockquote p:last-child {
    margin-bottom: 0;
}

/* Nested blockquote = warning/highlight */
blockquote blockquote {
    border-left: 3pt solid #c97a00;
    background: #fff8ed;
    color: #5a4000;
    padding: 10pt 14pt;
    margin: 10pt 0 0 0;
}

/* ═══ LISTS ═══ */
ul, ol {
    margin-bottom: 8pt;
    padding-left: 18pt;
}
li {
    margin-bottom: 4pt;
    line-height: 1.5;
}
li strong {
    color: #0F4C4C;
}

/* Numbered action items (A/B/C recommendations) */
h3 + ol li,
h3 + ul li {
    padding: 4pt 0;
    border-bottom: 0.5pt solid #eee;
}

/* ═══ HORIZONTAL RULES ═══ */
hr {
    border: none;
    height: 1.5pt;
    background: linear-gradient(to right, #0F4C4C, #ddd);
    margin: 24pt 0;
}

/* ═══ CODE (rare in reports) ═══ */
code {
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 8pt;
    background: #f0f0f0;
    padding: 1pt 4pt;
    border-radius: 2pt;
    color: #333;
}
pre {
    background: #f5f5f5;
    padding: 10pt;
    font-size: 7.5pt;
    border-left: 3pt solid #bbb;
    page-break-inside: avoid;
}

/* ═══ SOURCE FOOTER ═══ */
p:last-of-type em {
    font-size: 7.5pt;
    color: #aaa;
    display: block;
    margin-top: 20pt;
    padding-top: 10pt;
    border-top: 0.5pt solid #ddd;
}
"""


# ─── Request model ────────────────────────────────────────────────────────────

class ReportRequest(BaseModel):
    markdown: str
    title: str | None = None
    date: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _md_to_html(md_text: str, title: str, subtitle: str, footer: str, date: str = "") -> str:
    """Convierte Markdown de informe a HTML completo con CSS NeoFarm embebido."""
    extensions = ["tables", "fenced_code", "toc", "sane_lists", "smarty"]
    body = md_lib.markdown(md_text, extensions=extensions)

    # Extract first h1 from the body for the cover title
    import re
    cover_title = title
    cover_subtitle = subtitle
    h1_match = re.search(r'<h1>(.*?)</h1>', body, re.DOTALL)
    if h1_match:
        cover_title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
        em_match = re.search(r'<h1>.*?</h1>\s*<p><em>(.*?)</em></p>', body, re.DOTALL)
        if em_match:
            cover_subtitle = re.sub(r'<[^>]+>', '', em_match.group(1)).strip()

    # Build professional cover page (clean white design w/ teal accents)
    meta_date = date or datetime.now().strftime("%B %Y").capitalize()
    cover_html = (
        '<div class="cover">'
        '<div class="cover-top-bar"></div>'
        '<div class="cover-body">'
        '<div class="cover-brand">NEOFARM</div>'
        '<div class="cover-rule"></div>'
        f'<div class="cover-title">{cover_title}</div>'
        f'<div class="cover-subtitle">{cover_subtitle}</div>'
        '<div class="cover-meta-box">'
        '<div class="cover-meta-col">'
        '<div class="label">Fecha</div>'
        f'<div class="value">{meta_date}</div>'
        '</div>'
        '<div class="cover-meta-col">'
        '<div class="label">Tipo</div>'
        '<div class="value">Análisis operativo</div>'
        '</div>'
        '<div class="cover-meta-col">'
        '<div class="label">Clasificación</div>'
        '<div class="value">Confidencial</div>'
        '</div>'
        '</div>'
        '</div>'
        '<div class="cover-confidential">Uso interno</div>'
        '<div class="cover-bottom-bar"></div>'
        '</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{NEOFARM_CSS}</style>
</head>
<body>
{cover_html}
<span class="doc-subtitle">{subtitle}</span>
<span class="doc-footer">{footer}</span>
{body}
</body>
</html>"""


# ─── Reusable PDF generation ──────────────────────────────────────────────────

def generate_pdf_bytes(
    markdown_text: str,
    title: str | None = None,
    date: str | None = None,
) -> bytes:
    """Genera PDF con identidad NeoFarm a partir de Markdown. Devuelve bytes."""
    title = title or "Informe NeoFarm"
    date = date or datetime.now().strftime("%B %Y").capitalize()
    subtitle = f"Análisis operativo — {date}"
    footer = f"{title} — Informe técnico"
    html_str = _md_to_html(markdown_text, title, subtitle, footer, date)
    return HTML(string=html_str).write_pdf()


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_pdf(req: ReportRequest):
    """Convierte Markdown de informe a PDF con identidad visual NeoFarm."""
    if not req.markdown or not req.markdown.strip():
        raise HTTPException(400, "markdown cannot be empty")

    try:
        pdf_bytes = generate_pdf_bytes(req.markdown, req.title, req.date)
    except Exception as e:
        logger.error(f"Error generando PDF: {e}")
        raise HTTPException(500, f"Error generating PDF: {e}")

    title = req.title or "Informe NeoFarm"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{title.replace(" ", "_")}.pdf"',
        },
    )
