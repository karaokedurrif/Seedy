#!/usr/bin/env python3
"""
check_finetune_v6.py  –  Monitoriza y descarga el fine-tune v6 de Together.ai
═══════════════════════════════════════════════════════════════════════════════
Uso:
  python3 check_finetune_v6.py          # Estado del job
  python3 check_finetune_v6.py --wait   # Espera hasta completar + descarga
"""

import together, json, time, sys, subprocess
from pathlib import Path

API_KEY = "996aea9d34d2d688c7fcc497e101941f12f493d4084411cc4e10cd29c6e75e8e"
JOB_FILE = "finetune_v6_job.json"

client = together.Together(api_key=API_KEY)

# Load job info
with open(JOB_FILE) as f:
    info = json.load(f)

job_id = info["job_id"]
wait_mode = "--wait" in sys.argv

def check_status():
    ft = client.fine_tuning.retrieve(id=job_id)
    return ft

def print_status(ft):
    print(f"Job ID:     {ft.id}")
    print(f"Status:     {ft.status}")
    print(f"Model:      {ft.model}")
    if hasattr(ft, 'output_name') and ft.output_name:
        print(f"Output:     {ft.output_name}")
    if hasattr(ft, 'events') and ft.events:
        last = ft.events[-1] if isinstance(ft.events, list) else None
        if last:
            print(f"Last event: {last}")
    print()

ft = check_status()
print_status(ft)

if ft.status == "completed":
    output_name = ft.output_name if hasattr(ft, 'output_name') else None
    print(f"✅ Fine-tune completado!")
    if output_name:
        print(f"   Modelo: {output_name}")
        print(f"\n   Para descargar y convertir a GGUF:")
        print(f"   1. together fine-tuning download {job_id}")
        print(f"   2. python3 -m llama_cpp.convert {output_name} --outtype q8_0")
    sys.exit(0)

if ft.status in ("failed", "cancelled"):
    print(f"❌ Job {ft.status}")
    sys.exit(1)

if not wait_mode:
    print("💡 Ejecuta con --wait para esperar hasta completar")
    sys.exit(0)

# Wait mode
print("⏳ Esperando a que complete el fine-tune...")
while True:
    ft = check_status()
    status = ft.status
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] Status: {status}", end="")
    
    if hasattr(ft, 'training_steps') and ft.training_steps:
        if hasattr(ft, 'current_step') and ft.current_step:
            print(f"  Step {ft.current_step}/{ft.training_steps}", end="")
    print()
    
    if status == "completed":
        output_name = ft.output_name if hasattr(ft, 'output_name') else None
        print(f"\n✅ Fine-tune completado!")
        if output_name:
            print(f"   Modelo: {output_name}")
            info["output_name"] = output_name
            info["status"] = "completed"
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
