#!/usr/bin/env python3
"""
Convierte los artículos Markdown de CarlosStro.com a PDF legibles.
Usa WeasyPrint + markdown para generar PDFs con buen formato tipográfico.
"""

import os
import sys
import markdown
from weasyprint import HTML
from pathlib import Path

NAS_PATH = "/run/user/1000/gvfs/smb-share:server=192.168.30.100,share=datos/Fran"

# Páginas meta que NO son artículos de contenido
SKIP = {
    "Descargas.md",
    "Gestión de suscripción y compras.md",
    "miembros_irene-masullo.md",
    "miembros_pablogallego.md",
    "register.md",
    "Webinarios.md",
}

CSS = """
@page {
    size: A4;
    margin: 2.5cm 2cm 2.5cm 2cm;
    @bottom-center {
        content: "Página " counter(page) " de " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}

body {
    font-family: 'DejaVu Serif', 'Noto Serif', Georgia, 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #222;
    max-width: 100%;
}

h1 {
    font-size: 22pt;
    color: #1a1a2e;
    border-bottom: 2px solid #e07000;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 16pt;
    page-break-after: avoid;
}

h2 {
    font-size: 16pt;
    color: #2c3e50;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4px;
    margin-top: 20pt;
    page-break-after: avoid;
}

h3 {
    font-size: 13pt;
    color: #34495e;
    margin-top: 16pt;
    page-break-after: avoid;
}

h4, h5, h6 {
    font-size: 11.5pt;
    color: #555;
    margin-top: 12pt;
    page-break-after: avoid;
}

p {
    margin-bottom: 8pt;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

blockquote {
    border-left: 3px solid #e07000;
    margin: 12pt 0;
    padding: 8pt 16pt;
    background: #fdf6ec;
    color: #444;
    font-style: italic;
}

ul, ol {
    margin-bottom: 8pt;
    padding-left: 24pt;
}

li {
    margin-bottom: 4pt;
}

code {
    font-family: 'DejaVu Sans Mono', 'Courier New', monospace;
    font-size: 9.5pt;
    background: #f4f4f4;
    padding: 1pt 3pt;
    border-radius: 2pt;
}

pre {
    background: #f4f4f4;
    padding: 10pt;
    border-radius: 4pt;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
    page-break-inside: avoid;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 12pt 0;
    font-size: 10pt;
    page-break-inside: avoid;
}

th, td {
    border: 1px solid #ccc;
    padding: 6pt 8pt;
    text-align: left;
}

th {
    background: #f0f0f0;
    font-weight: bold;
}

tr:nth-child(even) {
    background: #fafafa;
}

img {
    max-width: 100%;
    height: auto;
    margin: 8pt 0;
}

a {
    color: #2980b9;
    text-decoration: none;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 16pt 0;
}

.header-meta {
    text-align: center;
    color: #888;
    font-size: 9pt;
    margin-bottom: 24pt;
    border-bottom: 1px solid #eee;
    padding-bottom: 8pt;
}
"""


def md_to_html(md_text: str, title: str) -> str:
    """Convierte Markdown a HTML completo con CSS embebido."""
    extensions = [
        "tables",
        "fenced_code",
        "toc",
        "nl2br",
        "sane_lists",
        "smarty",
    ]
    html_body = markdown.markdown(md_text, extensions=extensions)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>{CSS}</style>
</head>
<body>
    <div class="header-meta">CarlosStro.com — Comunidad STRO</div>
    <h1>{title}</h1>
    {html_body}
</body>
</html>"""


def convert_file(md_path: Path, pdf_dir: Path) -> tuple[bool, str]:
    """Convierte un .md a .pdf. Devuelve (éxito, mensaje)."""
    title = md_path.stem
    pdf_path = pdf_dir / f"{title}.pdf"

    try:
        md_text = md_path.read_text(encoding="utf-8")
        # Quitar el título si ya aparece como # al inicio
        lines = md_text.split("\n")
        if lines and lines[0].startswith("# "):
            md_text = "\n".join(lines[1:])

        html = md_to_html(md_text, title)
        HTML(string=html).write_pdf(str(pdf_path))
        size_kb = pdf_path.stat().st_size / 1024
        return True, f"✅ {title}.pdf ({size_kb:.0f} KB)"
    except Exception as e:
        return False, f"❌ {title}: {e}"


def main():
    nas = Path(NAS_PATH)
    if not nas.exists():
        print(f"❌ NAS no accesible: {NAS_PATH}")
        sys.exit(1)

    pdf_dir = nas / "PDFs"
    pdf_dir.mkdir(exist_ok=True)

    md_files = sorted(nas.glob("*.md"))
    articles = [f for f in md_files if f.name not in SKIP]

    print(f"📄 {len(articles)} artículos a convertir → {pdf_dir}")
    print()

    ok = 0
    errors = 0
    for i, md_path in enumerate(articles, 1):
        success, msg = convert_file(md_path, pdf_dir)
        print(f"  [{i}/{len(articles)}] {msg}")
        if success:
            ok += 1
        else:
            errors += 1

    print()
    print("=" * 60)
    print(f"✅ Conversión completada: {ok} PDFs generados, {errors} errores")
    print(f"   Carpeta: {pdf_dir}")

    # Tamaño total
    total = sum(f.stat().st_size for f in pdf_dir.glob("*.pdf"))
    print(f"   Tamaño total PDFs: {total / (1024*1024):.1f} MB")


if __name__ == "__main__":
    main()
