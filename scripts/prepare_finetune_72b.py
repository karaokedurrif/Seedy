#!/usr/bin/env python3
"""
Fine-tuning Qwen2.5-72B para Seedy en DGX GB10
Optimizado para ARM64 + NVIDIA Grace Blackwell

Requisitos:
- 128GB RAM unified (✅ GB10)
- Modelo base: qwen2.5:72b-instruct-q4_K_M (~42GB)
- Dataset: seedy_dataset_sft_v6.jsonl (302 ejemplos)
- LoRA rank: 32, alpha: 64
- Batch size: 1 (gradient accumulation 8)
- Estimado VRAM: ~60GB total
"""

import json
import subprocess
from pathlib import Path

# Configuración
BASE_MODEL = "qwen2.5:72b-instruct-q4_K_M"
DATASET_PATH = "~/Documentos/Seedy/seedy_dataset_sft_v6.jsonl"
OUTPUT_MODEL = "seedy:v17-72b"
LORA_RANK = 32
LORA_ALPHA = 64
LEARNING_RATE = 2e-5
EPOCHS = 3
BATCH_SIZE = 1
GRAD_ACCUM = 8

def check_model_available():
    """Verificar que el modelo base está descargado"""
    result = subprocess.run(
        ["docker", "compose", "-f", "~/seedy/docker-compose.yml", 
         "exec", "ollama", "ollama", "list"],
        capture_output=True, text=True
    )
    return BASE_MODEL in result.stdout

def expand_dataset():
    """Expandir dataset con ejemplos sintéticos"""
    dataset_path = Path(DATASET_PATH).expanduser()
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        examples = [json.loads(line) for line in f]
    
    print(f"📊 Dataset actual: {len(examples)} ejemplos")
    
    # Analizar gaps
    categories = {}
    for ex in examples:
        cat = ex.get('metadata', {}).get('category', 'general')
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\n📈 Distribución por categoría:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1]):
        print(f"   {cat}: {count} ejemplos")
    
    return examples

def create_modelfile(base_model, output_name):
    """Crear Modelfile para fine-tune"""
    modelfile = f"""FROM {base_model}

# System prompt optimizado para ganadería
SYSTEM \"\"\"Eres Seedy, asistente experto en ganadería de precisión especializado en:
- Porcino, bovino y avicultura extensiva  
- Genética (BLUP, cruces, predicción genealógica)
- Visión artificial (identificación aves, comportamiento)
- Nutrición (formulación raciones, aditivos)
- IoT y sensores (Zigbee, Ecowitt, análisis telemetría)
- Gemelos digitales y BIM agrícola
- Normativa (bienestar animal, trazabilidad)

Respondes en español técnico pero claro, con datos precisos y referencias cuando es posible.
\"\"\"

# Parámetros optimizados para 72B
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 8192
PARAMETER num_gpu 1
"""
    
    output_path = Path(f"~/Documentos/Seedy/Modelfile.{output_name}").expanduser()
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(modelfile)
    
    print(f"✅ Modelfile creado: {output_path}")
    return output_path

def finetune_with_unsloth():
    """
    Fine-tune usando Unsloth (optimizado para GB10)
    
    Unsloth soporta:
    - ARM64 nativo
    - Quantización eficiente
    - LoRA optimizado
    - Gradient checkpointing
    """
    
    script = """
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset

# Configuración
max_seq_length = 2048
dtype = torch.float16
load_in_4bit = True

# Cargar modelo base
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Qwen2.5-72B-Instruct",  # Unsloth optimizado
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

# Configurar LoRA
model = FastLanguageModel.get_peft_model(
    model,
    r = 32,  # Rank
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 64,
    lora_dropout = 0.05,
    bias = "none",
    use_gradient_checkpointing = True,
    random_state = 3407,
)

# Cargar dataset
dataset = load_dataset("json", data_files="seedy_dataset_sft_v6.jsonl", split="train")

# Tokenizar
def formatting_func(examples):
    texts = []
    for user_msg, assistant_msg in zip(examples["user"], examples["assistant"]):
        text = f"<|im_start|>user\\n{user_msg}<|im_end|>\\n<|im_start|>assistant\\n{assistant_msg}<|im_end|>"
        texts.append(text)
    return {"text": texts}

dataset = dataset.map(formatting_func, batched=True)

# Entrenar
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    args = TrainingArguments(
        per_device_train_batch_size = 1,
        gradient_accumulation_steps = 8,
        warmup_steps = 10,
        max_steps = 100,  # Ajustar según dataset
        learning_rate = 2e-5,
        fp16 = True,
        logging_steps = 10,
        output_dir = "outputs",
        optim = "adamw_8bit",
    ),
)

trainer.train()

# Guardar
model.save_pretrained("seedy_v17_72b_lora")
tokenizer.save_pretrained("seedy_v17_72b_lora")

print("✅ Fine-tuning completado!")
"""
    
    script_path = Path("~/Documentos/Seedy/finetune_qwen72b_unsloth.py").expanduser()
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script)
    
    print(f"✅ Script Unsloth creado: {script_path}")
    return script_path

def main():
    print("="*50)
    print("  🚀 FINE-TUNING QWEN2.5-72B PARA SEEDY")
    print("  DGX GB10 ARM64 + Grace Blackwell")
    print("="*50)
    print("")
    
    # 1. Verificar modelo base
    print("1️⃣ Verificando modelo base...")
    if not check_model_available():
        print(f"⚠️  Modelo {BASE_MODEL} no encontrado")
        print("   Ejecuta primero: bash monitor_ollama_72b.sh")
        return
    print("✅ Modelo base disponible")
    print("")
    
    # 2. Analizar dataset
    print("2️⃣ Analizando dataset...")
    examples = expand_dataset()
    print("")
    
    # 3. Crear Modelfile
    print("3️⃣ Creando Modelfile...")
    modelfile_path = create_modelfile(BASE_MODEL, OUTPUT_MODEL)
    print("")
    
    # 4. Crear script Unsloth
    print("4️⃣ Generando script Unsloth...")
    script_path = finetune_with_unsloth()
    print("")
    
    # 5. Instrucciones
    print("="*50)
    print("  ✅ PREPARACIÓN COMPLETADA")
    print("="*50)
    print("")
    print("📋 PRÓXIMOS PASOS:")
    print("")
    print("OPCIÓN 1: Fine-tune con Unsloth (RECOMENDADO)")
    print("  1. Instalar Unsloth en DGX:")
    print("     ssh daviddgx@192.168.20.57")
    print("     pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")
    print("")
    print(f"  2. Ejecutar fine-tuning:")
    print(f"     python3 {script_path}")
    print("")
    print(f"  3. Convertir a Ollama:")
    print(f"     ollama create {OUTPUT_MODEL} -f {modelfile_path}")
    print("")
    print("OPCIÓN 2: Fine-tune via Together.ai (CLOUD)")
    print("  - Mismo método actual (seedy_dataset_sft_v6.jsonl)")
    print("  - Base: Qwen/Qwen2.5-72B-Instruct")
    print("  - Coste estimado: ~$50-100 (3 épocas)")
    print("")
    print("="*50)
    print(f"  Dataset: {len(examples)} ejemplos")
    print(f"  Modelo salida: {OUTPUT_MODEL}")
    print(f"  Tiempo estimado: 4-6 horas (GB10)")
    print("="*50)

if __name__ == "__main__":
    main()
