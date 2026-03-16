#!/usr/bin/env python3
"""
Upload all documents from conocimientos/ to Dify Knowledge Base.
Flow: 1) Upload file → get file_id  2) Create document using file_id
"""
import json, time, base64, os, sys
import requests

DIFY_URL = "http://localhost:3002"
EMAIL = "david@neofarm.io"
PASSWORD = "NeoFarm2026"
PROVIDER = "langgenius/ollama/ollama"
DATASET_ID = "880d67ee-3bd3-40ce-a457-ef46a3ad6be6"
CONOCIMIENTOS_DIR = "/home/davidia/Documentos/Seedy/conocimientos"

SUPPORTED_EXTS = {'.pdf', '.md', '.txt', '.csv', '.xlsx', '.xls', '.docx', '.html', '.htm', '.json', '.jsonl'}

session = requests.Session()

def login():
    pwd_b64 = base64.b64encode(PASSWORD.encode()).decode()
    r = session.post(f"{DIFY_URL}/console/api/login", json={
        "email": EMAIL, "password": pwd_b64, "language": "es-ES"
    })
    r.raise_for_status()
    csrf = session.cookies.get("csrf_token")
    if csrf:
        session.headers["X-CSRF-TOKEN"] = csrf
    print(f"✅ Login OK")

def upload_file(filepath):
    """Upload file and return file_id."""
    filename = os.path.basename(filepath)
    csrf = session.cookies.get("csrf_token")
    if csrf:
        session.headers["X-CSRF-TOKEN"] = csrf
    
    with open(filepath, 'rb') as f:
        files = {'file': (filename, f)}
        data = {'source': 'datasets'}
        r = session.post(
            f"{DIFY_URL}/console/api/files/upload",
            files=files,
            data=data,
            timeout=120
        )
    
    if r.status_code == 201:
        file_data = r.json()
        file_id = file_data.get("id")
        return file_id
    else:
        print(f"    Upload failed: {r.status_code} {r.text[:150]}")
        return None

def create_document(dataset_id, file_id, filename):
    """Create document in dataset from uploaded file."""
    csrf = session.cookies.get("csrf_token")
    if csrf:
        session.headers["X-CSRF-TOKEN"] = csrf
    
    payload = {
        "data_source": {
            "info_list": {
                "data_source_type": "upload_file",
                "file_info_list": {
                    "file_ids": [file_id]
                }
            }
        },
        "indexing_technique": "high_quality",
        "process_rule": {
            "mode": "automatic"
        },
        "doc_form": "text_model",
        "doc_language": "Spanish",
        "embedding_model": "mxbai-embed-large",
        "embedding_model_provider": PROVIDER,
    }
    
    r = session.post(
        f"{DIFY_URL}/console/api/datasets/{dataset_id}/documents",
        json=payload,
        timeout=120
    )
    
    if r.status_code in (200, 201):
        data = r.json()
        docs = data.get("documents", [])
        batch = data.get("batch", "?")
        if docs:
            doc_id = docs[0].get("id", "?")
            return doc_id, batch
        return "ok", batch
    else:
        print(f"    Doc create failed: {r.status_code} {r.text[:200]}")
        return None, None

def collect_documents():
    """Collect all uploadable documents from conocimientos directory."""
    docs = []
    for root, dirs, files in os.walk(CONOCIMIENTOS_DIR):
        for f in sorted(files):
            if f.startswith('.') or f.startswith('_'):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            filepath = os.path.join(root, f)
            filesize = os.path.getsize(filepath)
            if filesize == 0 or filesize > 50 * 1024 * 1024:
                continue
            docs.append(filepath)
    return docs

def main():
    print("=" * 60)
    print("📤 Upload documentos a Dify Knowledge Base")
    print(f"   KB: {DATASET_ID}")
    print("=" * 60)
    
    login()
    
    docs = collect_documents()
    print(f"\n📂 {len(docs)} documentos a subir\n")
    
    uploaded = 0
    failed = 0
    
    for i, doc_path in enumerate(docs):
        rel = os.path.relpath(doc_path, CONOCIMIENTOS_DIR)
        
        # Re-login every 8 documents
        if i > 0 and i % 8 == 0:
            login()
        
        print(f"[{i+1}/{len(docs)}] {rel}")
        
        # Step 1: Upload file
        file_id = upload_file(doc_path)
        if not file_id:
            failed += 1
            continue
        
        # Step 2: Create document
        doc_id, batch = create_document(DATASET_ID, file_id, os.path.basename(doc_path))
        if doc_id:
            print(f"  ✅ doc={doc_id} batch={batch}")
            uploaded += 1
        else:
            failed += 1
        
        time.sleep(0.3)
    
    print("\n" + "=" * 60)
    print(f"📊 Resultado: {uploaded} subidos, {failed} fallidos de {len(docs)} total")
    print("=" * 60)

if __name__ == "__main__":
    main()
