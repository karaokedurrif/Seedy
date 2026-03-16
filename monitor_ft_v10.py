#!/usr/bin/env python3
"""Monitor fine-tune v10 job on Together.ai"""
import time
from together import Together

client = Together(api_key="996aea9d34d2d688c7fcc497e101941f12f493d4084411cc4e10cd29c6e75e8e")
JOB_ID = "ft-5007f821-da89"

while True:
    job = client.fine_tuning.retrieve(JOB_ID)
    status = job.status
    events = getattr(job, 'events', []) or []
    last_event = events[-1].message if events else "—"
    
    print(f"[{time.strftime('%H:%M:%S')}] Status: {status} | {last_event}", flush=True)
    
    if status in ("completed", "failed", "cancelled"):
        print(f"\n{'✅' if status == 'completed' else '❌'} Fine-tune {status}!")
        if status == "completed":
            print(f"   Output model: {getattr(job, 'output_name', '?')}")
            print(f"   FT ID: {JOB_ID}")
        break
    
    time.sleep(60)
