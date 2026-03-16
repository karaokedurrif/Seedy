#!/usr/bin/env python3
"""
build_v6.py  –  Genera seedy_dataset_sft_v6.jsonl
═══════════════════════════════════════════════════
Fusiona:
  • seedy_dataset_sft_v5.jsonl   (267 ejemplos – core agrotech + avicultura)
  • seedy_dataset_sft_geotwin.jsonl (35 ejemplos – GeoTwin GIS 3D)

Pasos:
  1. Unifica el system prompt a SYSTEM_V6 (todos los dominios)
  2. Deduplica por pregunta (normalizada)
  3. Rechaza respuestas <100 chars (demasiado cortas)
  4. Valida formato JSONL (3 mensajes: system/user/assistant)
  5. Escribe seedy_dataset_sft_v6.jsonl
"""

import json, re, sys
from pathlib import Path

# ── System prompt v6: unifica TODOS los dominios ────────────────────────
SYSTEM_V6 = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData), costes por nave, "
    "nutrición porcina, genética aplicada (porcino, vacuno y aviar), "
    "normativa SIGE, Digital Twins productivos, avicultura extensiva "
    "(capones, pulardas, razas, genética aviar, Label Rouge), "
    "GeoTwin (plataforma GIS 3D), CesiumJS, BlenderGIS, "
    "renderización web 3D y simulación geoespacial.\n\n"
    "Responde siempre en español, en prosa natural y profesional.\n"
    "No uses secciones tipo Notes, References o Explanation.\n"
    "No repitas la pregunta.\n"
    "No inventes cifras, normativa ni parámetros técnicos.\n"
    "Si falta un dato imprescindible, pide solo el mínimo necesario "
    "(máximo 2 preguntas).\n"
    "Si das un número, incluye unidades y aclara si es aproximado.\n"
    "Prioriza precisión técnica sobre tono comercial.\n"
    "Nunca confundas razas bovinas con avícolas ni porcinas entre sí."
)

# ── Helpers ──────────────────────────────────────────────────────────────
def normalise(text: str) -> str:
    """Normaliza pregunta para detección de duplicados."""
    t = text.lower().strip()
    t = re.sub(r"[¿?¡!.,;:\"'()\[\]{}\-–—]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def extract_roles(msg_list: list) -> tuple:
    """Extrae (system, user, assistant) de la lista de mensajes."""
    system = user = assistant = ""
    for m in msg_list:
        if m["role"] == "system":
            system = m["content"]
        elif m["role"] == "user":
            user = m["content"]
        elif m["role"] == "assistant":
            assistant = m["content"]
    return system, user, assistant

def rewrite(msgs: list) -> dict:
    """Reescribe ejemplo con el system prompt v6."""
    _, user, assistant = extract_roles(msgs)
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_V6},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }

# ── Carga ────────────────────────────────────────────────────────────────
sources = [
    ("seedy_dataset_sft_v5.jsonl", "v5-core"),
    ("seedy_dataset_sft_geotwin.jsonl", "geotwin"),
]

all_examples = []
for fname, tag in sources:
    p = Path(fname)
    if not p.exists():
        print(f"⚠  {fname} no encontrado, se omite")
        continue
    with p.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  ✗ {fname}:{i} JSON inválido: {e}")
                continue
            msgs = d.get("messages", [])
            roles = [m["role"] for m in msgs]
            if roles != ["system", "user", "assistant"]:
                print(f"  ✗ {fname}:{i} roles incorrectos: {roles}")
                continue
            _, user_text, asst_text = extract_roles(msgs)
            if len(asst_text) < 100:
                print(f"  ✗ {fname}:{i} respuesta demasiado corta ({len(asst_text)} chars)")
                continue
            all_examples.append((tag, user_text, asst_text))
    print(f"✓ {fname}: {sum(1 for t,_,_ in all_examples if t==tag)} ejemplos válidos")

# ── Deduplicar por pregunta ──────────────────────────────────────────────
seen = {}
deduped = []
dups = 0
for tag, user_text, asst_text in all_examples:
    key = normalise(user_text)
    if key in seen:
        dups += 1
        # Si el nuevo tiene respuesta más larga, reemplazar
        if len(asst_text) > len(seen[key][2]):
            idx = seen[key][3]
            deduped[idx] = (tag, user_text, asst_text)
            seen[key] = (tag, user_text, asst_text, idx)
        continue
    seen[key] = (tag, user_text, asst_text, len(deduped))
    deduped.append((tag, user_text, asst_text))

print(f"\nDuplicados eliminados: {dups}")
print(f"Ejemplos finales: {len(deduped)}")

# ── Stats por dominio ────────────────────────────────────────────────────
from collections import Counter
tag_counts = Counter(tag for tag,_,_ in deduped)
for tag, cnt in sorted(tag_counts.items()):
    print(f"  {tag}: {cnt}")

# ── Escribir v6 ─────────────────────────────────────────────────────────
out = Path("seedy_dataset_sft_v6.jsonl")
with out.open("w") as f:
    for _, user_text, asst_text in deduped:
        row = {
            "messages": [
                {"role": "system", "content": SYSTEM_V6},
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": asst_text},
            ]
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

# ── Validación rápida ───────────────────────────────────────────────────
with out.open() as f:
    lines = f.readlines()
valid = 0
for i, line in enumerate(lines, 1):
    d = json.loads(line)
    assert len(d["messages"]) == 3
    assert d["messages"][0]["role"] == "system"
    assert d["messages"][1]["role"] == "user"
    assert d["messages"][2]["role"] == "assistant"
    valid += 1

resp_lens = [len(json.loads(l)["messages"][2]["content"]) for l in lines]
avg_len = sum(resp_lens) / len(resp_lens)
min_len = min(resp_lens)
max_len = max(resp_lens)

print(f"\n{'='*50}")
print(f"✅ {out.name}: {valid} ejemplos válidos")
print(f"   Respuesta media: {avg_len:.0f} chars")
print(f"   Respuesta min:   {min_len} chars")
print(f"   Respuesta max:   {max_len} chars")
print(f"   Tamaño:          {out.stat().st_size / 1024:.1f} KB")
print(f"{'='*50}")
