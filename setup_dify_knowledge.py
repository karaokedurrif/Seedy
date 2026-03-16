#!/usr/bin/env python3
"""
setup_dify_knowledge.py
Configura Dify: Ollama como provider + crea Knowledge Base + sube documentos
"""
import json, os, time, glob, sys
import urllib.request
import urllib.parse

DIFY_BASE = "http://localhost:3002"
DOCS_DIR = "/home/davidia/Documentos/Seedy/conocimientos/Carga de documentos nuevos"
CONOCIMIENTOS_DIR = "/home/davidia/Documentos/Seedy/conocimientos"

# Read cookies from file
def load_auth():
    cookies = {}
    with open("/tmp/dify_cookies.txt") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    
    return {
        "access_token": cookies.get("access_token", ""),
        "csrf_token": cookies.get("csrf_token", ""),
        "refresh_token": cookies.get("refresh_token", ""),
    }

AUTH = load_auth()

def api_request(method, path, data=None, files=None):
    """Make authenticated API request to Dify."""
    url = f"{DIFY_BASE}{path}"
    
    headers = {
        "Cookie": f"access_token={AUTH['access_token']}; csrf_token={AUTH['csrf_token']}; refresh_token={AUTH['refresh_token']}",
        "X-CSRF-TOKEN": AUTH["csrf_token"],
    }
    
    if files:
        # Multipart form upload
        import http.client
        import mimetypes
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        
        body = b""
        for key, value in (data or {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            body += f"{value}\r\n".encode()
        
        for key, (filename, filedata, content_type) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            body += f"Content-Type: {content_type}\r\n\r\n".encode()
            body += filedata + b"\r\n"
        
        body += f"--{boundary}--\r\n".encode()
        
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = resp.read().decode("utf-8")
            if result:
                return json.loads(result)
            return {"status": resp.status}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  ⚠ HTTP {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  ⚠ Error: {e}")
        return None


def setup_ollama_models():
    """Add Ollama models to Dify."""
    print("\n📡 Configurando Ollama como proveedor de modelos...")
    
    models = [
        {
            "model": "seedy:v7-local",
            "model_type": "llm",
            "credentials": {
                "base_url": "http://host.docker.internal:11434",
                "mode": "chat",
                "context_size": "32768",
                "max_tokens": "8192"
            }
        },
        {
            "model": "mxbai-embed-large",
            "model_type": "text-embedding",
            "credentials": {
                "base_url": "http://host.docker.internal:11434",
                "context_size": "512"
            }
        },
    ]
    
    for model_config in models:
        result = api_request("POST", 
            "/console/api/workspaces/current/model-providers/ollama/models",
            data=model_config)
        if result is not None:
            print(f"  ✅ Modelo {model_config['model']} ({model_config['model_type']}) configurado")
        else:
            print(f"  ⚠ Error configurando {model_config['model']} (quizá ya existe)")
    
    # Check providers
    result = api_request("GET", "/console/api/workspaces/current/model-providers")
    if result:
        providers = result.get("data", [])
        print(f"  📊 Proveedores configurados: {len(providers)}")


def create_knowledge_base():
    """Create a knowledge base for Seedy documents."""
    print("\n📚 Creando base de conocimiento 'NeoFarm Seedy'...")
    
    result = api_request("POST", "/console/api/datasets", data={
        "name": "NeoFarm Seedy - Ganadería & Agrotech",
        "description": "Documentos técnicos de ganadería, avicultura, porcino, vacuno, nutrición animal, IoT ganadero, genética, normativa y agrotech para NeoFarm.",
        "indexing_technique": "high_quality",
        "permission": "all_team_members",
    })
    
    if result:
        dataset_id = result.get("id", "")
        print(f"  ✅ Knowledge Base creada: {dataset_id}")
        return dataset_id
    else:
        # Maybe it already exists, list datasets
        result = api_request("GET", "/console/api/datasets?page=1&limit=20")
        if result and result.get("data"):
            for ds in result["data"]:
                if "NeoFarm" in ds.get("name", "") or "Seedy" in ds.get("name", ""):
                    print(f"  ℹ Knowledge Base ya existe: {ds['id']} ({ds['name']})")
                    return ds["id"]
        return None


def upload_document(dataset_id, filepath):
    """Upload a single document to the knowledge base."""
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    
    # Skip unsupported formats
    supported = {'.pdf', '.md', '.txt', '.csv', '.xlsx', '.xls', '.docx', '.html'}
    if ext not in supported:
        return "skipped"
    
    # Content type mapping
    content_types = {
        '.pdf': 'application/pdf',
        '.md': 'text/markdown',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.html': 'text/html',
    }
    
    with open(filepath, 'rb') as f:
        file_data = f.read()
    
    if len(file_data) == 0:
        return "empty"
    
    # Dify uses multipart upload with specific process_rule
    ct = content_types.get(ext, 'application/octet-stream')
    
    result = api_request("POST", f"/console/api/datasets/{dataset_id}/document/create-by-file",
        data={
            "data": json.dumps({
                "indexing_technique": "high_quality",
                "process_rule": {
                    "mode": "automatic"
                }
            })
        },
        files={
            "file": (filename, file_data, ct)
        }
    )
    
    if result:
        doc = result.get("document", {})
        return doc.get("id", "ok")
    return "error"


def upload_all_documents(dataset_id):
    """Upload all documents from the Carga de documentos directory."""
    print(f"\n📤 Subiendo documentos a la base de conocimiento...")
    
    # Collect all files to upload
    files_to_upload = []
    
    # 1. From "Carga de documentos nuevos"
    for item in os.listdir(DOCS_DIR):
        full_path = os.path.join(DOCS_DIR, item)
        if os.path.isfile(full_path):
            files_to_upload.append(full_path)
        elif os.path.isdir(full_path) and item.startswith("ScienceDirect"):
            # ScienceDirect folders contain PDFs
            for f in os.listdir(full_path):
                fp = os.path.join(full_path, f)
                if os.path.isfile(fp):
                    files_to_upload.append(fp)
    
    # 2. From existing conocimientos (RAG docs)
    for root, dirs, files in os.walk(CONOCIMIENTOS_DIR):
        # Skip the "Carga de documentos nuevos" dir (already handled)
        if "Carga de documentos nuevos" in root:
            continue
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in {'.md', '.csv', '.pdf', '.txt'}:
                files_to_upload.append(os.path.join(root, f))
    
    print(f"  📂 {len(files_to_upload)} archivos encontrados")
    
    uploaded = 0
    skipped = 0
    errors = 0
    
    for i, filepath in enumerate(files_to_upload):
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in {'.pdf', '.md', '.txt', '.csv', '.xlsx', '.xls'}:
            skipped += 1
            continue
        
        size_mb = os.path.getsize(filepath) / (1024*1024)
        
        result = upload_document(dataset_id, filepath)
        
        if result == "skipped" or result == "empty":
            skipped += 1
        elif result == "error":
            errors += 1
            print(f"  ❌ [{i+1}/{len(files_to_upload)}] {filename}")
        else:
            uploaded += 1
            print(f"  ✅ [{i+1}/{len(files_to_upload)}] {filename} ({size_mb:.1f} MB)")
        
        time.sleep(0.5)  # Rate limit
    
    print(f"\n  📊 Resultado: {uploaded} subidos, {skipped} omitidos, {errors} errores")
    return uploaded


def main():
    print("=" * 60)
    print("🌱 CONFIGURACIÓN DIFY PARA SEEDY")
    print("=" * 60)
    
    # 1. Setup Ollama models
    setup_ollama_models()
    
    # 2. Create knowledge base
    dataset_id = create_knowledge_base()
    if not dataset_id:
        print("❌ No se pudo crear la Knowledge Base")
        sys.exit(1)
    
    # 3. Upload documents
    upload_all_documents(dataset_id)
    
    print(f"\n{'='*60}")
    print(f"✅ Dify configurado. Accede a http://localhost:3002")
    print(f"   Email: david@neofarm.io")
    print(f"   Password: NeoFarm2026")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
