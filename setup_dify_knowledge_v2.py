#!/usr/bin/env python3
"""
setup_dify_knowledge.py — v2
Configura Dify: Ollama como provider + crea Knowledge Base + sube documentos
Usa subprocess + curl para manejar cookies correctamente
"""
import json, os, time, subprocess, sys, base64

DIFY_BASE = "http://localhost:3002"
COOKIES_FILE = "/tmp/dify_cookies.txt"
DOCS_DIR = "/home/davidia/Documentos/Seedy/conocimientos/Carga de documentos nuevos"
CONOCIMIENTOS_DIR = "/home/davidia/Documentos/Seedy/conocimientos"


def dify_login():
    password_b64 = base64.b64encode(b"NeoFarm2026").decode()
    result = subprocess.run([
        "curl", "-s", "-c", COOKIES_FILE,
        "-X", "POST", f"{DIFY_BASE}/console/api/login",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"email": "david@neofarm.io", "password": password_b64})
    ], capture_output=True, text=True, timeout=30)
    resp = json.loads(result.stdout) if result.stdout else {}
    if resp.get("result") == "success":
        print("  ✅ Login exitoso")
        return True
    print(f"  ❌ Login fallido: {result.stdout}")
    return False


def get_csrf():
    with open(COOKIES_FILE) as f:
        for line in f:
            if "csrf_token" in line and not line.startswith("#"):
                return line.strip().split("\t")[-1]
    return ""


def api(method, path, data=None):
    csrf = get_csrf()
    cmd = ["curl", "-s", "-b", COOKIES_FILE, "-H", f"X-CSRF-TOKEN: {csrf}", "-X", method]
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    cmd.append(f"{DIFY_BASE}{path}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return {"raw": result.stdout[:300]}
    return {}


def setup_ollama_models():
    print("\n📡 Configurando Ollama como proveedor de modelos...")
    models = [
        {"model": "seedy:v7-local", "model_type": "llm",
         "credentials": {"base_url": "http://host.docker.internal:11434", "mode": "chat", "context_size": "32768", "max_tokens": "8192"}},
        {"model": "mxbai-embed-large", "model_type": "text-embedding",
         "credentials": {"base_url": "http://host.docker.internal:11434", "context_size": "512"}},
    ]
    for mc in models:
        result = api("POST", "/console/api/workspaces/current/model-providers/ollama/models", data=mc)
        err = result.get("code", "") if result else ""
        if err:
            print(f"  ℹ {mc['model']}: {err} — {result.get('message','')[:80]}")
        else:
            print(f"  ✅ Modelo {mc['model']} ({mc['model_type']}) configurado")

    result = api("GET", "/console/api/workspaces/current/model-providers")
    for p in result.get("data", []):
        print(f"  📊 Provider: {p.get('provider','?')}")


def create_knowledge_base():
    print("\n📚 Creando base de conocimiento...")
    result = api("GET", "/console/api/datasets?page=1&limit=20")
    if result and result.get("data"):
        for ds in result["data"]:
            if "NeoFarm" in ds.get("name", "") or "Seedy" in ds.get("name", ""):
                print(f"  ℹ Ya existe: {ds['name']} (ID: {ds['id']})")
                return ds["id"]

    result = api("POST", "/console/api/datasets", data={
        "name": "NeoFarm Seedy - Ganadería & Agrotech",
        "description": "Docs técnicos ganadería, avicultura, porcino, vacuno, nutrición, IoT, genética, normativa.",
        "indexing_technique": "high_quality",
        "permission": "all_team_members",
    })
    if result and result.get("id"):
        print(f"  ✅ Created: {result['id']}")
        return result["id"]
    print(f"  ⚠ Response: {result}")
    return None


def upload_document(dataset_id, filepath):
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {'.pdf', '.md', '.txt', '.csv', '.xlsx'}:
        return "skipped"
    if os.path.getsize(filepath) == 0:
        return "empty"
    if os.path.getsize(filepath) > 15 * 1024 * 1024:
        return "too_large"

    csrf = get_csrf()
    process_rule = json.dumps({
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"}
    })
    cmd = [
        "curl", "-s", "-b", COOKIES_FILE,
        "-H", f"X-CSRF-TOKEN: {csrf}",
        "-X", "POST",
        "-F", f"file=@{filepath}",
        "-F", f"data={process_rule}",
        f"{DIFY_BASE}/console/api/datasets/{dataset_id}/document/create-by-file"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.stdout:
        try:
            resp = json.loads(result.stdout)
            if resp.get("document") or resp.get("batch"):
                return "ok"
            if "already" in str(resp).lower():
                return "exists"
            return f"error: {str(resp)[:150]}"
        except:
            return f"error: {result.stdout[:150]}"
    return "error: no response"


def upload_all_documents(dataset_id):
    print(f"\n📤 Subiendo documentos a Dify Knowledge Base...")
    files = []

    # From Carga de documentos nuevos
    for item in sorted(os.listdir(DOCS_DIR)):
        full_path = os.path.join(DOCS_DIR, item)
        if os.path.isfile(full_path):
            files.append(full_path)
        elif os.path.isdir(full_path) and "ScienceDirect" in item:
            for f in sorted(os.listdir(full_path)):
                fp = os.path.join(full_path, f)
                if os.path.isfile(fp):
                    files.append(fp)

    # From existing conocimientos
    for root, dirs, fnames in os.walk(CONOCIMIENTOS_DIR):
        if "Carga de documentos nuevos" in root:
            continue
        for f in sorted(fnames):
            ext = os.path.splitext(f)[1].lower()
            if ext in {'.md', '.csv', '.pdf', '.txt'}:
                files.append(os.path.join(root, f))

    print(f"  📂 {len(files)} archivos encontrados")
    stats = {"ok": 0, "skipped": 0, "error": 0, "exists": 0, "too_large": 0}

    for i, filepath in enumerate(files):
        filename = os.path.basename(filepath)
        size_mb = os.path.getsize(filepath) / (1024*1024)
        result = upload_document(dataset_id, filepath)
        if result == "ok":
            stats["ok"] += 1
            print(f"  ✅ [{i+1}/{len(files)}] {filename} ({size_mb:.1f} MB)")
        elif result in ("skipped", "empty"):
            stats["skipped"] += 1
        elif result == "too_large":
            stats["too_large"] += 1
            print(f"  ⚠ [{i+1}/{len(files)}] {filename} demasiado grande ({size_mb:.1f} MB)")
        elif result == "exists":
            stats["exists"] += 1
        else:
            stats["error"] += 1
            print(f"  ❌ [{i+1}/{len(files)}] {filename} — {result}")
        time.sleep(0.3)

    print(f"\n  📊 Subidos: {stats['ok']}, Omitidos: {stats['skipped']}, "
          f"Ya existían: {stats['exists']}, Muy grandes: {stats['too_large']}, Errores: {stats['error']}")


def main():
    print("=" * 60)
    print("🌱 CONFIGURACIÓN DIFY PARA SEEDY")
    print("=" * 60)
    print("\n🔑 Login...")
    if not dify_login():
        sys.exit(1)

    setup_ollama_models()
    dataset_id = create_knowledge_base()
    if not dataset_id:
        print("❌ No se pudo crear la Knowledge Base")
        sys.exit(1)

    upload_all_documents(dataset_id)
    print(f"\n{'='*60}")
    print(f"✅ Dify configurado!")
    print(f"   URL: http://localhost:3002")
    print(f"   Email: david@neofarm.io / Password: NeoFarm2026")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
