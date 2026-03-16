#!/usr/bin/env python3
"""
build_dataset_v11.py — Fusión de datasets para Seedy v11
=========================================================
Combina:
  - seedy_dataset_sft_v10.jsonl (1,991 ejemplos originales)
  - seedy_dataset_cda.jsonl (90 ejemplos CDA/FIWARE)
  - hf_datasets/agri_qa.jsonl (22,615 Q&A agricultura)
  - hf_datasets/soil_qa.jsonl (3,447 Q&A suelos)
  - hf_datasets/crop_dataset.jsonl (90,039 EN — cultivos arroz/maíz)
  - hf_datasets/empathetic_dialogues.jsonl (23,149 conversaciones)
  - hf_datasets/hh_rlhf.jsonl (169,352 preferencia)

Formato salida: JSONL con {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
"""

import json
import random
import os
from collections import Counter

random.seed(42)

WORKSPACE = "/home/davidia/Documentos/Seedy"
HF = f"{WORKSPACE}/hf_datasets"
OUTPUT = f"{WORKSPACE}/seedy_dataset_sft_v11.jsonl"

SYSTEM_PROMPT = (
    "Eres Seedy, el asistente inteligente de NeoFarm para ganadería y agricultura de precisión. "
    "Respondes en español de forma técnica pero accesible. "
    "Cuando no tengas certeza, indícalo claramente. "
    "Nunca inventes datos, razas o productos que no existan."
)

# ─── Configuración de sampling ───
# Objetivo: dataset equilibrado ~5,000-6,000 ejemplos
SAMPLE_CONFIG = {
    "agri_qa": 800,          # De 22,615 → 800 Q&A agricultura
    "soil_qa": 400,          # De 3,447 → 400 Q&A suelos (buena calidad)
    "crop_en_qa": 600,       # De 24,547 → 600 solo Q&A en inglés de CROP
    "crop_en_summary": 200,  # De 3,146 → 200 resúmenes de CROP EN
    "empathetic": 500,       # De 23,149 conv → 500 diálogos empáticos
    "hh_rlhf_helpful": 400,  # De ~80K helpfulness → 400 chosen responses
}
# Total HF: ~2,900 nuevos + 1,991 v10 + 90 CDA = ~5,000


def make_sft(user_msg: str, assistant_msg: str, system: str = SYSTEM_PROMPT) -> dict:
    """Crear ejemplo SFT en formato messages."""
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg.strip()},
            {"role": "assistant", "content": assistant_msg.strip()},
        ]
    }


def load_existing():
    """Cargar datasets existentes v10 + CDA."""
    examples = []
    
    # v10 (ya en formato SFT)
    v10_path = f"{WORKSPACE}/seedy_dataset_sft_v10.jsonl"
    if os.path.exists(v10_path):
        with open(v10_path) as f:
            for line in f:
                examples.append(json.loads(line))
        print(f"  ✅ v10: {len(examples)} ejemplos")
    
    # CDA (ya en formato SFT)
    cda_path = f"{WORKSPACE}/seedy_dataset_cda.jsonl"
    n_before = len(examples)
    if os.path.exists(cda_path):
        with open(cda_path) as f:
            for line in f:
                examples.append(json.loads(line))
        print(f"  ✅ CDA: {len(examples) - n_before} ejemplos")
    
    return examples


def process_agri_qa(n_sample: int) -> list:
    """Procesar KisanVaani Agriculture Q&A → SFT."""
    rows = []
    with open(f"{HF}/agri_qa.jsonl") as f:
        for line in f:
            d = json.loads(line)
            q = d.get("question", "").strip()
            a = d.get("answers", "").strip()
            if q and a and len(a) > 20:  # Filtrar respuestas muy cortas
                rows.append((q, a))
    
    sampled = random.sample(rows, min(n_sample, len(rows)))
    results = []
    for q, a in sampled:
        results.append(make_sft(q, a))
    
    print(f"  ✅ AgriQA: {len(results)}/{len(rows)} sampled (filtro: len>20)")
    return results


def process_soil_qa(n_sample: int) -> list:
    """Procesar Soil Q&A Dataset → SFT."""
    rows = []
    with open(f"{HF}/soil_qa.jsonl") as f:
        for line in f:
            d = json.loads(line)
            q = d.get("QUESTION.question", "").strip()
            a = d.get("ANSWER", "").strip()
            ctx = d.get("QUESTION.paragraph", "").strip()
            if q and a and len(a) > 10:
                # Incluir contexto en la respuesta si es más informativo
                full_a = f"{a}. {ctx}" if ctx and len(ctx) > len(a) else a
                rows.append((q, full_a))
    
    sampled = random.sample(rows, min(n_sample, len(rows)))
    results = [make_sft(q, a) for q, a in sampled]
    print(f"  ✅ SoilQA: {len(results)}/{len(rows)} sampled")
    return results


def process_crop_en(n_qa: int, n_summary: int) -> list:
    """Procesar CROP-dataset (solo EN, solo QA+Summary) → SFT."""
    qa_rows = []
    sum_rows = []
    
    with open(f"{HF}/crop_dataset.jsonl") as f:
        for line in f:
            d = json.loads(line)
            inst = d.get("instruction", "")
            inp = d.get("input", "")
            out = d.get("output", "")
            
            # Solo inglés
            if any('\u4e00' <= c <= '\u9fff' for c in inst):
                continue
            
            if not inst or not out or len(out) < 15:
                continue
            
            il = inst.lower()
            
            if "question" in il or "answer" in il or "qa" in il:
                user_q = f"{inst}\n\n{inp}" if inp else inst
                qa_rows.append((user_q, out))
            elif "summar" in il:
                user_q = f"{inst}\n\n{inp}" if inp else inst
                sum_rows.append((user_q, out))
    
    sampled_qa = random.sample(qa_rows, min(n_qa, len(qa_rows)))
    sampled_sum = random.sample(sum_rows, min(n_summary, len(sum_rows)))
    
    results = [make_sft(q, a) for q, a in sampled_qa + sampled_sum]
    print(f"  ✅ CROP EN: {len(sampled_qa)} QA + {len(sampled_sum)} Summary = {len(results)} total")
    return results


def process_empathetic(n_sample: int) -> list:
    """Procesar Empathetic Dialogues → SFT (convertir conv a Q&A empáticos)."""
    # Agrupar por conversación
    convs = {}
    with open(f"{HF}/empathetic_dialogues.jsonl") as f:
        for line in f:
            d = json.loads(line)
            cid = d.get("conv_id", "")
            if cid not in convs:
                convs[cid] = {"context": d.get("context", ""), "utterances": []}
            convs[cid]["utterances"].append({
                "idx": d.get("utterance_idx", 0),
                "speaker": d.get("speaker_idx", 0),
                "text": d.get("utterance", "").replace("_comma_", ",").strip()
            })
    
    # Convertir a pares: turnos alternos (idx impar = user, idx par = listener)
    pairs = []
    for cid, conv in convs.items():
        utts = sorted(conv["utterances"], key=lambda x: x["idx"])
        context = conv["context"]
        
        # Identificar los 2 speakers de la conversación
        speakers = list(set(u["speaker"] for u in utts))
        if len(speakers) < 2 or len(utts) < 2:
            continue
        
        # El primer speaker es el "talker" (comparte experiencia)
        talker = utts[0]["speaker"]
        
        for i in range(len(utts) - 1):
            # talker habla → listener responde con empatía
            if utts[i]["speaker"] == talker and utts[i+1]["speaker"] != talker:
                user_msg = utts[i]["text"]
                assistant_msg = utts[i+1]["text"]
                if len(user_msg) > 10 and len(assistant_msg) > 10:
                    sys_prompt = (
                        f"Eres Seedy, el asistente inteligente de NeoFarm. "
                        f"Responde con empatía y comprensión. "
                        f"El usuario expresa un sentimiento de: {context}."
                    )
                    pairs.append(make_sft(user_msg, assistant_msg, system=sys_prompt))
    
    sampled = random.sample(pairs, min(n_sample, len(pairs)))
    print(f"  ✅ Empathetic: {len(sampled)}/{len(pairs)} pares empáticos")
    return sampled


def process_hh_rlhf(n_sample: int) -> list:
    """Procesar HH-RLHF → SFT (solo chosen, solo helpfulness, filtrar content)."""
    rows = []
    skipped_harmful = 0
    
    with open(f"{HF}/hh_rlhf.jsonl") as f:
        for line in f:
            d = json.loads(line)
            chosen = d.get("chosen", "")
            
            # Parsear formato "\n\nHuman: ...\n\nAssistant: ..."
            parts = chosen.split("\n\nHuman: ")
            if len(parts) < 2:
                continue
            
            # Tomar el último turno Human/Assistant
            last_part = parts[-1]
            ha = last_part.split("\n\nAssistant: ")
            if len(ha) < 2:
                continue
            
            human_msg = ha[0].strip()
            assistant_msg = ha[1].strip()
            
            # Filtrar contenido problemático
            bad_words = ["kill", "murder", "suicide", "bomb", "weapon", "hack", 
                        "steal", "drugs", "cuss", "swear", "profanity", "slur",
                        "racist", "sexist", "porn", "nsfw", "nude"]
            human_lower = human_msg.lower()
            if any(w in human_lower for w in bad_words):
                skipped_harmful += 1
                continue
            
            if len(human_msg) > 15 and len(assistant_msg) > 30:
                rows.append((human_msg, assistant_msg))
    
    sampled = random.sample(rows, min(n_sample, len(rows)))
    results = [make_sft(q, a) for q, a in sampled]
    print(f"  ✅ HH-RLHF: {len(results)}/{len(rows)} helpful (skipped {skipped_harmful} harmful)")
    return results


def main():
    print("╔══════════════════════════════════════════╗")
    print("║     BUILD SEEDY DATASET v11 — FUSIÓN     ║")
    print("╚══════════════════════════════════════════╝\n")
    
    all_examples = []
    
    # 1. Cargar existentes
    print("📦 Cargando datasets existentes...")
    existing = load_existing()
    all_examples.extend(existing)
    
    # 2. Procesar HF datasets
    print("\n📥 Procesando HF datasets...")
    all_examples.extend(process_agri_qa(SAMPLE_CONFIG["agri_qa"]))
    all_examples.extend(process_soil_qa(SAMPLE_CONFIG["soil_qa"]))
    all_examples.extend(process_crop_en(SAMPLE_CONFIG["crop_en_qa"], SAMPLE_CONFIG["crop_en_summary"]))
    all_examples.extend(process_empathetic(SAMPLE_CONFIG["empathetic"]))
    all_examples.extend(process_hh_rlhf(SAMPLE_CONFIG["hh_rlhf_helpful"]))
    
    # 3. Deduplicar por contenido del user message
    print("\n🔍 Deduplicando...")
    seen = set()
    unique = []
    for ex in all_examples:
        msgs = ex.get("messages", [])
        user_msg = ""
        for m in msgs:
            if m["role"] == "user":
                user_msg = m["content"][:200]  # Primeros 200 chars como key
                break
        if user_msg and user_msg not in seen:
            seen.add(user_msg)
            unique.append(ex)
    
    dup_count = len(all_examples) - len(unique)
    print(f"  Eliminados {dup_count} duplicados")
    
    # 4. Shuffle y guardar
    random.shuffle(unique)
    
    with open(OUTPUT, "w") as f:
        for ex in unique:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    # 5. Estadísticas finales
    print(f"\n{'='*50}")
    print(f"📊 DATASET v11 GENERADO: {OUTPUT}")
    print(f"   Total ejemplos: {len(unique):,}")
    print(f"   Tamaño: {os.path.getsize(OUTPUT) / 1024 / 1024:.1f} MB")
    
    # Contar por tipo de system prompt
    types = Counter()
    for ex in unique:
        sys_msg = ex["messages"][0]["content"] if ex["messages"] else ""
        if "empatía" in sys_msg or "sentimiento" in sys_msg:
            types["empathetic"] += 1
        elif "NeoFarm" in sys_msg or "Seedy" in sys_msg:
            types["seedy_core"] += 1
        else:
            types["generic"] += 1
    print(f"   Distribución: {dict(types)}")
    
    # Verificar formato
    with open(OUTPUT) as f:
        first = json.loads(f.readline())
    print(f"   Formato OK: {list(first.keys())}")
    print(f"   Roles: {[m['role'] for m in first['messages']]}")


if __name__ == "__main__":
    main()
