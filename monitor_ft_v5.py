#!/usr/bin/env python3
"""
Monitoriza el fine-tuning v5, descarga el merged model y crea seedy:v5-q8 en Ollama.
Uso: python3 monitor_ft_v5.py
"""
import time, subprocess, os, json
from together import Together

JOB_ID = "ft-e0f71c8c-45d3"
API_KEY = "996aea9d34d2d688c7fcc497e101941f12f493d4084411cc4e10cd29c6e75e8e"
MODEL_DIR = "/home/davidia/models"
MERGED_PATH = f"{MODEL_DIR}/seedy_v5_merged.tar.zst"

client = Together(api_key=API_KEY)


def poll():
    """Espera a que el job termine."""
    prev_status = None
    while True:
        job = client.fine_tuning.retrieve(id=JOB_ID)
        status = job.status
        if status != prev_status:
            print(f"\n[{time.strftime('%H:%M:%S')}] Status: {status}")
            prev_status = status

        if status == "completed":
            print(f"✅ Fine-tuning completado!")
            return job
        elif status in ("failed", "cancelled", "error"):
            print(f"❌ Job terminó con estado: {status}")
            try:
                events = client.fine_tuning.list_events(id=JOB_ID)
                for e in list(events)[-5:]:
                    print(f"  {e}")
            except Exception:
                pass
            raise SystemExit(1)
        else:
            print(".", end="", flush=True)
            time.sleep(30)


def download_merged():
    """Descarga el modelo merged."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"\nDescargando merged model → {MERGED_PATH}")
    resp = client.fine_tuning.content(ft_id=JOB_ID, checkpoint="merged")
    written = 0
    with open(MERGED_PATH, "wb") as f:
        for chunk in resp.iter_bytes(chunk_size=131072):
            f.write(chunk)
            written += len(chunk)
            mb = written / (1024 * 1024)
            if int(mb) % 500 == 0 and int(mb) > 0:
                print(f"  {mb:.0f} MB...", flush=True)
    gb = written / (1024**3)
    print(f"✅ Descarga completa: {gb:.2f} GB")
    return MERGED_PATH


def extract_and_quantize(tar_path):
    """Extrae, convierte a GGUF Q8_0 y crea modelo Ollama."""
    extract_dir = f"{MODEL_DIR}/seedy_v5_merged"
    gguf_path = f"{MODEL_DIR}/seedy_v5_q8.gguf"

    # Extraer
    print(f"\nExtrayendo {tar_path}...")
    os.makedirs(extract_dir, exist_ok=True)
    subprocess.run(
        ["tar", "--zstd", "-xf", tar_path, "-C", extract_dir],
        check=True,
    )
    print(f"✅ Extraído en {extract_dir}")

    # Buscar la carpeta real (puede haber un subdirectorio)
    entries = os.listdir(extract_dir)
    if len(entries) == 1 and os.path.isdir(f"{extract_dir}/{entries[0]}"):
        model_path = f"{extract_dir}/{entries[0]}"
    else:
        model_path = extract_dir
    print(f"Model path: {model_path}")

    # Convertir a GGUF
    print(f"\nConvirtiendo a GGUF Q8_0...")
    convert_script = os.path.expanduser("~/llama.cpp/convert_hf_to_gguf.py")
    if not os.path.exists(convert_script):
        # Try alternative location
        convert_script = os.path.expanduser("~/llama.cpp/convert-hf-to-gguf.py")
    
    subprocess.run(
        ["python3", convert_script, model_path,
         "--outfile", gguf_path, "--outtype", "q8_0"],
        check=True,
    )
    print(f"✅ GGUF generado: {gguf_path}")
    return gguf_path


def create_ollama_model(gguf_path):
    """Crea el modelo seedy:v5-q8 en Ollama."""
    modelfile = f"""FROM {gguf_path}
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
SYSTEM \"\"\"Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.
Dominios principales: IoT ganadero (PorciData), costes por nave, nutrición porcina, genética aplicada, normativa SIGE, Digital Twins productivos y avicultura extensiva (capones, pulardas, razas, genética aviar, Label Rouge).

Responde siempre en español, en prosa natural y profesional.
No uses secciones tipo Notes, References o Explanation.
No repitas la pregunta.
No inventes cifras, normativa ni parámetros técnicos.
Si falta un dato imprescindible, pide solo el mínimo necesario (máximo 2 preguntas).
Si das un número, incluye unidades y aclara si es aproximado.
Prioriza precisión técnica sobre tono comercial.
Nunca confundas razas bovinas con avícolas ni porcinas entre sí.\"\"\"
"""
    mf_path = "/tmp/Modelfile.seedy-v5-q8"
    with open(mf_path, "w") as f:
        f.write(modelfile)
    
    print(f"\nCreando modelo Ollama seedy:v5-q8...")
    # Copy GGUF into ollama container if using docker
    subprocess.run(
        ["docker", "cp", gguf_path, f"ollama:{gguf_path}"],
        check=False,
    )
    subprocess.run(
        ["docker", "cp", mf_path, f"ollama:{mf_path}"],
        check=False,
    )
    result = subprocess.run(
        ["docker", "exec", "ollama", "ollama", "create", "seedy:v5-q8", "-f", mf_path],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"✅ Modelo seedy:v5-q8 creado en Ollama")
        print(result.stdout)
    else:
        print(f"⚠️  Error creando en Ollama via docker, intentando local...")
        print(result.stderr)
        subprocess.run(["ollama", "create", "seedy:v5-q8", "-f", mf_path], check=True)
        print(f"✅ Modelo seedy:v5-q8 creado en Ollama (local)")


def test_model():
    """Test rápido del modelo v5."""
    import httpx
    print("\n🧪 Test rápido v5...")
    tests = [
        "¿Qué es un capón?",
        "¿Qué capas IoT tiene PorciData?",
        "¿Quién eres?",
    ]
    for q in tests:
        try:
            r = httpx.post(
                "http://localhost:11434/api/generate",
                json={"model": "seedy:v5-q8", "prompt": q, "stream": False},
                timeout=60,
            )
            ans = r.json().get("response", "")[:150]
            print(f"\n  Q: {q}")
            print(f"  A: {ans}...")
        except Exception as e:
            print(f"  Q: {q} → Error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("MONITOR FINE-TUNING SEEDY v5")
    print(f"Job: {JOB_ID}")
    print("=" * 60)

    # 1. Poll until complete
    job = poll()

    # 2. Download merged
    tar_path = download_merged()

    # 3. Extract + GGUF Q8
    gguf_path = extract_and_quantize(tar_path)

    # 4. Create Ollama model
    create_ollama_model(gguf_path)

    # 5. Test
    test_model()

    print("\n" + "=" * 60)
    print("🎉 SEEDY v5 LISTO")
    print("=" * 60)
