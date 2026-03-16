#!/usr/bin/env python3
"""
Setup completo de Dify: instalar plugin Ollama, añadir modelos, crear KB, subir documentos.
"""
import json, time, base64, os, sys, glob
import requests

DIFY_URL = "http://localhost:3002"
EMAIL = "david@neofarm.io"
PASSWORD = "NeoFarm2026"
OLLAMA_URL = "http://ollama:11434"  # Docker container name on same network
PROVIDER = "langgenius/ollama/ollama"
CONOCIMIENTOS_DIR = "/home/davidia/Documentos/Seedy/conocimientos"

session = requests.Session()

def login():
    """Login and set CSRF token."""
    pwd_b64 = base64.b64encode(PASSWORD.encode()).decode()
    r = session.post(f"{DIFY_URL}/console/api/login", json={
        "email": EMAIL, "password": pwd_b64, "language": "es-ES"
    })
    r.raise_for_status()
    csrf = session.cookies.get("csrf_token")
    if csrf:
        session.headers["X-CSRF-TOKEN"] = csrf
    print(f"✅ Login OK (CSRF={csrf[:20]}...)")
    return True

def refresh_csrf():
    """Refresh CSRF token from cookies."""
    csrf = session.cookies.get("csrf_token")
    if csrf:
        session.headers["X-CSRF-TOKEN"] = csrf

def check_plugin_installed():
    """Check if Ollama plugin is already installed."""
    refresh_csrf()
    r = session.get(f"{DIFY_URL}/console/api/workspaces/current/plugin/list?page=1&page_size=256")
    r.raise_for_status()
    data = r.json()
    plugins = data.get("plugins", [])
    for p in plugins:
        pid = p.get("plugin_id", "")
        if "ollama" in pid.lower():
            print(f"✅ Ollama plugin ya instalado: {pid}")
            return True
    return False

def install_ollama_plugin():
    """Install Ollama plugin from marketplace."""
    OLLAMA_IDENTIFIER = "langgenius/ollama:0.1.2@fcf107badccaf57948634ad2c557d393c3894138d83f4eb3f959e9a1d3a86512"
    refresh_csrf()
    r = session.post(f"{DIFY_URL}/console/api/workspaces/current/plugin/install/marketplace", json={
        "plugin_unique_identifiers": [OLLAMA_IDENTIFIER]
    })
    r.raise_for_status()
    data = r.json()
    task_id = data.get("task_id")
    if data.get("all_installed"):
        print("✅ Ollama plugin ya estaba instalado")
        return True
    
    print(f"⏳ Instalando plugin (task: {task_id})...")
    for i in range(30):
        time.sleep(2)
        refresh_csrf()
        r2 = session.get(f"{DIFY_URL}/console/api/workspaces/current/plugin/tasks/{task_id}")
        r2.raise_for_status()
        task = r2.json().get("task", {})
        status = task.get("status")
        if status == "success":
            print("✅ Plugin Ollama instalado correctamente")
            return True
        elif status in ("failed", "error"):
            print(f"❌ Error instalando plugin: {task}")
            return False
    print("⚠️ Timeout esperando instalación del plugin")
    return False

def add_model(model_name, model_type, extra_creds=None):
    """Add a model to the Ollama provider."""
    refresh_csrf()
    creds = {"base_url": OLLAMA_URL}
    if model_type == "llm":
        creds.update({"mode": "chat", "context_size": "8192", "max_tokens": "4096"})
    elif model_type == "text-embedding":
        creds.update({"context_size": "512"})
    if extra_creds:
        creds.update(extra_creds)
    
    payload = {
        "model": model_name,
        "model_type": model_type,
        "credentials": creds,
    }
    
    print(f"⏳ Añadiendo modelo {model_name} ({model_type})...")
    try:
        r = session.post(
            f"{DIFY_URL}/console/api/workspaces/current/model-providers/{PROVIDER}/models/credentials",
            json=payload,
            timeout=120
        )
        if r.status_code == 201:
            print(f"✅ Modelo {model_name} ({model_type}) añadido")
            return True
        else:
            print(f"❌ Error añadiendo modelo {model_name}: {r.status_code} {r.text[:200]}")
            return False
    except requests.Timeout:
        print(f"⚠️ Timeout añadiendo modelo {model_name} — puede que se haya añadido igualmente")
        return False

def set_default_model(model_name, model_type, provider=PROVIDER):
    """Set a model as default for a model type."""
    refresh_csrf()
    r = session.post(f"{DIFY_URL}/console/api/workspaces/current/default-model", json={
        "model_settings": [{
            "model_type": model_type,
            "provider": provider,
            "model": model_name
        }]
    })
    if r.status_code == 200:
        print(f"✅ Default {model_type} → {model_name}")
        return True
    else:
        print(f"❌ Error setting default {model_type}: {r.status_code} {r.text[:200]}")
        return False

def check_models():
    """Check which models are currently configured."""
    refresh_csrf()
    r = session.get(f"{DIFY_URL}/console/api/workspaces/current/model-providers/{PROVIDER}/models")
    r.raise_for_status()
    data = r.json()
    models = data.get("data", [])
    print(f"📋 Modelos configurados en Ollama: {len(models)}")
    for m in models:
        print(f"   - {m.get('model', '?')} ({m.get('model_type', '?')}) status={m.get('status','?')}")
    return models

def create_knowledge_base(name="NeoFarm Seedy - Ganadería & Agrotech"):
    """Create a knowledge base."""
    refresh_csrf()
    
    # Check if KB already exists
    r = session.get(f"{DIFY_URL}/console/api/datasets?page=1&limit=100")
    r.raise_for_status()
    for ds in r.json().get("data", []):
        if ds.get("name") == name:
            print(f"✅ Knowledge Base ya existe: {ds['id']}")
            return ds["id"]
    
    payload = {
        "name": name,
        "description": "Base de conocimientos de NeoFarm: ganadería, avicultura, IoT, nutrición, genética, normativa, digital twins.",
        "indexing_technique": "high_quality",
        "permission": "only_me",
    }
    r = session.post(f"{DIFY_URL}/console/api/datasets", json=payload)
    if r.status_code in (200, 201):
        ds_id = r.json().get("id")
        print(f"✅ Knowledge Base creada: {ds_id}")
        return ds_id
    else:
        print(f"❌ Error creando KB: {r.status_code} {r.text[:300]}")
        return None

def upload_document(dataset_id, filepath):
    """Upload a single document to a knowledge base."""
    refresh_csrf()
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    
    # Skip unsupported file types
    supported = {'.pdf', '.md', '.txt', '.csv', '.xlsx', '.xls', '.docx', '.html', '.htm', '.json', '.jsonl'}
    if ext not in supported:
        print(f"  ⏭ Saltando {filename} (tipo no soportado: {ext})")
        return None
    
    filesize = os.path.getsize(filepath)
    if filesize > 50 * 1024 * 1024:  # 50MB limit
        print(f"  ⏭ Saltando {filename} (demasiado grande: {filesize/1024/1024:.1f}MB)")
        return None
    
    if filesize == 0:
        print(f"  ⏭ Saltando {filename} (archivo vacío)")
        return None
    
    data_source = {
        "type": "upload_file",
        "info_list": {"data_source_type": "upload_file"},
    }
    
    process_rule = {
        "mode": "automatic",
    }
    
    with open(filepath, 'rb') as f:
        files = {'file': (filename, f)}
        form_data = {
            'data': json.dumps({
                "indexing_technique": "high_quality",
                "process_rule": process_rule,
                "doc_form": "text_model",
                "doc_language": "Spanish",
            }),
        }
        
        try:
            r = session.post(
                f"{DIFY_URL}/console/api/datasets/{dataset_id}/document/create-by-file",
                files=files,
                data=form_data,
                timeout=120
            )
            if r.status_code in (200, 201):
                doc_data = r.json()
                doc_id = doc_data.get("document", {}).get("id", "?")
                print(f"  ✅ {filename} → doc_id={doc_id}")
                return doc_id
            else:
                print(f"  ❌ {filename}: {r.status_code} {r.text[:150]}")
                return None
        except requests.Timeout:
            print(f"  ⚠️ Timeout subiendo {filename}")
            return None
        except Exception as e:
            print(f"  ❌ {filename}: {e}")
            return None

def collect_documents():
    """Collect all documents from conocimientos directory."""
    docs = []
    for root, dirs, files in os.walk(CONOCIMIENTOS_DIR):
        for f in sorted(files):
            if f.startswith('.') or f.startswith('_'):
                continue
            filepath = os.path.join(root, f)
            docs.append(filepath)
    return docs

def main():
    print("=" * 60)
    print("🚀 Setup completo de Dify para NeoFarm Seedy")
    print("=" * 60)
    
    # Step 1: Login
    print("\n📌 Paso 1: Login")
    login()
    
    # Step 2: Check/Install Ollama plugin
    print("\n📌 Paso 2: Plugin Ollama")
    if not check_plugin_installed():
        if not install_ollama_plugin():
            sys.exit(1)
        # Re-login because plugin install may invalidate session
        time.sleep(3)
        login()
    
    # Step 3: Check current models
    print("\n📌 Paso 3: Modelos configurados")
    models = check_models()
    existing_models = {(m.get("model"), m.get("model_type")) for m in models}
    
    # Step 4: Add models
    print("\n📌 Paso 4: Añadir modelos")
    if ("seedy:v7-local", "llm") not in existing_models:
        login()  # fresh session
        add_model("seedy:v7-local", "llm")
    else:
        print("  ✅ seedy:v7-local (llm) ya existe")
    
    login()  # fresh session for next model
    if ("mxbai-embed-large", "text-embedding") not in existing_models:
        add_model("mxbai-embed-large", "text-embedding")
    else:
        print("  ✅ mxbai-embed-large (text-embedding) ya existe")
    
    # Step 5: Set defaults
    print("\n📌 Paso 5: Modelos por defecto")
    login()
    set_default_model("seedy:v7-local", "llm")
    set_default_model("mxbai-embed-large", "text-embedding")
    
    # Step 6: Create Knowledge Base
    print("\n📌 Paso 6: Knowledge Base")
    login()
    kb_id = create_knowledge_base()
    if not kb_id:
        print("❌ No se pudo crear la KB. Abortando.")
        sys.exit(1)
    
    # Step 7: Upload documents
    print("\n📌 Paso 7: Subir documentos")
    docs = collect_documents()
    print(f"📂 {len(docs)} documentos encontrados en {CONOCIMIENTOS_DIR}")
    
    uploaded = 0
    failed = 0
    skipped = 0
    
    for i, doc_path in enumerate(docs):
        rel = os.path.relpath(doc_path, CONOCIMIENTOS_DIR)
        print(f"\n[{i+1}/{len(docs)}] {rel}")
        
        # Re-login every 10 documents to avoid token expiration
        if i > 0 and i % 10 == 0:
            login()
        
        result = upload_document(kb_id, doc_path)
        if result:
            uploaded += 1
        elif result is None:
            skipped += 1
        else:
            failed += 1
        
        time.sleep(0.5)  # Rate limiting
    
    print("\n" + "=" * 60)
    print(f"📊 Resultado: {uploaded} subidos, {skipped} saltados, {failed} fallidos")
    print(f"📚 Knowledge Base: {kb_id}")
    print("=" * 60)

if __name__ == "__main__":
    main()
