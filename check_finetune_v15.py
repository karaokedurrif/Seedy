#!/usr/bin/env python3
"""
check_finetune_v15.py — Monitoriza el fine-tune v15 de Together.ai
═══════════════════════════════════════════════════════════════════
Dataset: seedy_dataset_sft_v15.jsonl (4,676 ejemplos = v11 + corrections_v14)
Uso:
  python3 check_finetune_v15.py          # Estado del job
  python3 check_finetune_v15.py --wait   # Espera hasta completar
"""

import together, json, time, sys
from pathlib import Path

API_KEY = "996aea9d34d2d688c7fcc497e101941f12f493d4084411cc4e10cd29c6e75e8e"
JOB_FILE = "finetune_v15_job.json"

client = together.Together(api_key=API_KEY)

with open(JOB_FILE) as f:
    info = json.load(f)

job_id = info["job_id"]
wait_mode = "--wait" in sys.argv


def check_status():
    return client.fine_tuning.retrieve(id=job_id)


def print_status(ft):
    print(f"Job ID:     {ft.id}")
    print(f"Status:     {ft.status}")
    print(f"Model:      {ft.model}")
    if hasattr(ft, "output_name") and ft.output_name:
        print(f"Output:     {ft.output_name}")
    if hasattr(ft, "training_steps") and ft.training_steps:
        print(f"Steps:      {getattr(ft, 'current_step', '?')}/{ft.training_steps}")
    print()


ft = check_status()
print_status(ft)

if ft.status == "completed":
    output_name = ft.output_name if hasattr(ft, "output_name") else None
    print("✅ Fine-tune completado!")
    if output_name:
        print(f"   Modelo: {output_name}")
        print(f"\n   Próximos pasos:")
        print(f"   1. together fine-tuning download {job_id}")
        print(f"   2. python3 merge_v15.py")
        print(f"   3. ollama create seedy:v15 -f Modelfile.seedy-v15")
    info["status"] = "completed"
    info["output_name"] = output_name
    with open(JOB_FILE, "w") as f:
        json.dump(info, f, indent=2)
    sys.exit(0)

if ft.status in ("failed", "cancelled"):
    print(f"❌ Job {ft.status}")
    info["status"] = ft.status
    with open(JOB_FILE, "w") as f:
        json.dump(info, f, indent=2)
    sys.exit(1)

if not wait_mode:
    print("💡 Ejecuta con --wait para esperar hasta completar")
    sys.exit(0)

# Wait mode
print("⏳ Esperando a que complete el fine-tune v15...")
while True:
    ft = check_status()
    status = ft.status
    ts = time.strftime("%H:%M:%S")
    step_info = ""
    if hasattr(ft, "training_steps") and ft.training_steps:
        current = getattr(ft, "current_step", "?")
        step_info = f"  Step {current}/{ft.training_steps}"
    print(f"  [{ts}] Status: {status}{step_info}")

    if status == "completed":
        output_name = ft.output_name if hasattr(ft, "output_name") else None
        print(f"\n✅ Fine-tune v15 completado!")
        if output_name:
            print(f"   Modelo: {output_name}")
        info["status"] = "completed"
        info["output_name"] = output_name
        with open(JOB_FILE, "w") as f:
            json.dump(info, f, indent=2)
        break

    if status in ("failed", "cancelled"):
        print(f"\n❌ Job {status}")
        info["status"] = status
        with open(JOB_FILE, "w") as f:
            json.dump(info, f, indent=2)
        sys.exit(1)

    time.sleep(30)
