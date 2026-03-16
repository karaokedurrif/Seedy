#!/usr/bin/env python3
"""
Merge Seedy v15 LoRA adapter with Qwen2.5-14B-Instruct base model.
Then convert to GGUF and quantize to Q4_K_M for Ollama.
"""
import torch
import os
import subprocess
import sys

BASE_MODEL = "/home/davidia/models/qwen25_14b_base"
ADAPTER_PATH = "/home/davidia/models/seedy_v15_adapter"
MERGED_PATH = "/home/davidia/models/seedy_v15_merged"
GGUF_F16 = "/home/davidia/models/gguf/seedy_v15_f16.gguf"
GGUF_Q4KM = "/home/davidia/models/gguf/seedy_v15_q4km.gguf"
LLAMA_CPP = "/home/davidia/llama.cpp"

def step1_merge():
    """Merge LoRA adapter with base model."""
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print("=" * 60)
    print("STEP 1: Merge LoRA adapter with Qwen2.5-14B-Instruct")
    print("=" * 60)

    print("\n[1a] Loading base model (this downloads ~28 GB first time)...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
    )
    print(f"  Base model loaded: {BASE_MODEL}")

    print("\n[1b] Loading tokenizer from adapter...")
    tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH, trust_remote_code=True)

    print("\n[1c] Loading and merging LoRA adapter...")
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    model = model.merge_and_unload()
    print("  LoRA merged successfully")

    print(f"\n[1d] Saving merged model to {MERGED_PATH}...")
    os.makedirs(MERGED_PATH, exist_ok=True)
    model.save_pretrained(MERGED_PATH, safe_serialization=True)
    tokenizer.save_pretrained(MERGED_PATH)

    total_size = sum(
        os.path.getsize(os.path.join(MERGED_PATH, f))
        for f in os.listdir(MERGED_PATH)
        if f.endswith('.safetensors')
    )
    print(f"  Merged model: {total_size / 1e9:.1f} GB")

    # Free memory
    del model
    del tokenizer
    torch.cuda.empty_cache() if torch.cuda.is_available() else None
    import gc; gc.collect()


def step2_convert_gguf():
    """Convert merged model to GGUF format."""
    print("\n" + "=" * 60)
    print("STEP 2: Convert to GGUF (F16)")
    print("=" * 60)

    convert_script = os.path.join(LLAMA_CPP, "convert_hf_to_gguf.py")
    cmd = [
        sys.executable, convert_script,
        MERGED_PATH,
        "--outfile", GGUF_F16,
        "--outtype", "f16",
    ]
    print(f"  Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"  F16 GGUF: {os.path.getsize(GGUF_F16) / 1e9:.1f} GB")


def step3_quantize():
    """Quantize GGUF to Q4_K_M."""
    print("\n" + "=" * 60)
    print("STEP 3: Quantize to Q4_K_M")
    print("=" * 60)

    quantize_bin = os.path.join(LLAMA_CPP, "build", "bin", "llama-quantize")
    cmd = [quantize_bin, GGUF_F16, GGUF_Q4KM, "Q4_K_M"]
    print(f"  Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    size_gb = os.path.getsize(GGUF_Q4KM) / 1e9
    print(f"  Q4_K_M GGUF: {size_gb:.1f} GB")

    # Clean up F16 (huge)
    print(f"  Removing F16 intermediate ({os.path.getsize(GGUF_F16) / 1e9:.1f} GB)...")
    os.remove(GGUF_F16)
    print("  Done")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=0, help="Run specific step (1=merge, 2=convert, 3=quantize, 0=all)")
    args = parser.parse_args()

    if args.step == 0 or args.step == 1:
        step1_merge()
    if args.step == 0 or args.step == 2:
        step2_convert_gguf()
    if args.step == 0 or args.step == 3:
        step3_quantize()

    print("\n" + "=" * 60)
    print("ALL DONE!")
    print(f"  GGUF Q4_K_M: {GGUF_Q4KM}")
    print("  Next: ollama create seedy:v15 -f Modelfile.seedy-v15")
    print("=" * 60)
