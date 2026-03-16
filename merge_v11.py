#!/usr/bin/env python3
"""
Merge Seedy v11 LoRA adapter with Qwen2.5-14B-Instruct base model.
Same process as v10 but with v11 adapter.
"""
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import os

BASE_MODEL = "Qwen/Qwen2.5-14B-Instruct"
ADAPTER_PATH = "/home/davidia/models/seedy_v11_adapter"
OUTPUT_PATH = "/home/davidia/models/seedy_v11_merged"

print("=" * 60)
print("Merging Seedy v11 LoRA adapter with Qwen2.5-14B-Instruct")
print("=" * 60)

# Step 1: Load base model
print("\n[1/4] Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16,
    device_map="cpu",  # CPU for merge to save GPU memory
    trust_remote_code=True,
)
print(f"  Base model loaded: {BASE_MODEL}")

# Step 2: Load tokenizer
print("\n[2/4] Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH, trust_remote_code=True)
print(f"  Tokenizer loaded from adapter path")

# Step 3: Load and merge adapter
print("\n[3/4] Loading and merging LoRA adapter...")
model = PeftModel.from_pretrained(model, ADAPTER_PATH)
model = model.merge_and_unload()
print(f"  Adapter merged successfully")

# Step 4: Save merged model
print(f"\n[4/4] Saving merged model to {OUTPUT_PATH}...")
os.makedirs(OUTPUT_PATH, exist_ok=True)
model.save_pretrained(OUTPUT_PATH, safe_serialization=True)
tokenizer.save_pretrained(OUTPUT_PATH)
print(f"  Merged model saved!")

# Verify
total_size = sum(
    os.path.getsize(os.path.join(OUTPUT_PATH, f))
    for f in os.listdir(OUTPUT_PATH)
    if f.endswith('.safetensors')
)
print(f"\n{'='*60}")
print(f"Total model size: {total_size / 1e9:.1f} GB")
print(f"Files: {os.listdir(OUTPUT_PATH)}")
print(f"{'='*60}")
print("DONE! Next: convert to GGUF with llama.cpp")
