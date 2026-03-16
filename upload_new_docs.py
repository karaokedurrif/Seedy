#!/usr/bin/env python3
"""Upload new files to Dify Knowledge Base (only files not already present)."""
import requests, os, time, json, re

DIFY_URL = "http://localhost:3002"
DATASET_ID = "880d67ee-3bd3-40ce-a457-ef46a3ad6be6"
CONOCIMIENTOS = "/home/davidia/Documentos/Seedy/conocimientos"
EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".xlsx", ".xls", ".docx", ".html", ".htm", ".json", ".jsonl"}

session = requests.Session()

def login():
    r = session.post(f"{DIFY_URL}/console/api/login", json={
        "email": "david@neofarm.io",
        "password": "TmVvRmFybTIwMjY=",
        "language": "es-ES",
        "remember_me": True
    })
    csrf = session.cookies.get("csrf_token", "")
    session.headers.update({"X-CSRF-TOKEN": csrf})
    return csrf

def get_existing_docs():
    docs = []
    page = 1
    while True:
        r = session.get(f"{DIFY_URL}/console/api/datasets/{DATASET_ID}/documents",
                        params={"page": page, "limit": 100})
        data = r.json()
        for doc in data.get("data", []):
            docs.append(doc.get("name", ""))
        if not data.get("has_more", False):
            break
        page += 1
    return set(docs)

def find_all_files():
    files = []
    for root, dirs, fnames in os.walk(CONOCIMIENTOS):
        for f in fnames:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXTENSIONS:
                files.append(os.path.join(root, f))
    return files

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (updated in Dify .env)

def sanitize_filename(name):
    """Remove/replace characters Dify considers invalid."""
    # Replace em-dash, en-dash, colons, etc.
    name = name.replace("—", "-").replace("–", "-").replace(":", "-")
    # Remove other non-ASCII punctuation but keep Spanish chars
    name = re.sub(r'[^\w\s\-_.()&+áéíóúñÁÉÍÓÚÑüÜ]', '', name)
    return name.strip()

def upload_file(filepath):
    fsize = os.path.getsize(filepath)
    if fsize > MAX_FILE_SIZE:
        return None, 413, f"too large ({fsize // (1024*1024)} MB)"
    fname = sanitize_filename(os.path.basename(filepath))
    with open(filepath, "rb") as f:
        r = session.post(
            f"{DIFY_URL}/console/api/files/upload",
            files={"file": (fname, f)},
            data={"source": "datasets"}
        )
    if r.status_code != 201:
        return None, r.status_code, r.text[:200]
    return r.json().get("id"), 201, ""

def create_document(file_id, filename):
    payload = {
        "data_source": {
            "type": "upload_file",
            "info_list": {
                "data_source_type": "upload_file",
                "file_info_list": {
                    "file_ids": [file_id]
                }
            }
        },
        "process_rule": {"mode": "automatic"},
        "indexing_technique": "high_quality",
        "doc_form": "text_model",
        "doc_language": "Spanish"
    }
    r = session.post(
        f"{DIFY_URL}/console/api/datasets/{DATASET_ID}/documents",
        json=payload
    )
    return r.status_code, r.text[:200]

if __name__ == "__main__":
    csrf = login()
    print(f"✅ Login OK, CSRF: {csrf[:20]}...")

    existing = get_existing_docs()
    print(f"📚 Documentos ya en KB: {len(existing)}")

    all_files = find_all_files()
    print(f"📁 Total archivos en conocimientos: {len(all_files)}")

    new_files = [f for f in all_files if os.path.basename(f) not in existing]
    print(f"🆕 Archivos NUEVOS a subir: {len(new_files)}")

    if not new_files:
        print("✅ No hay archivos nuevos. Todo está al día.")
    else:
        for f in new_files:
            print(f"  → {os.path.basename(f)}")
        print()
        
        ok = fail = skip = 0
        for i, fpath in enumerate(new_files):
            fname = os.path.basename(fpath)
            if i > 0 and i % 8 == 0:
                csrf = login()
            try:
                file_id, status, errmsg = upload_file(fpath)
                if status == 413:
                    skip += 1
                    print(f"  ⏭️  [{i+1}/{len(new_files)}] {fname} → {errmsg}")
                elif file_id:
                    doc_status, doc_msg = create_document(file_id, fname)
                    if doc_status == 200:
                        ok += 1
                        print(f"  ✅ [{i+1}/{len(new_files)}] {fname}")
                    else:
                        fail += 1
                        print(f"  ❌ [{i+1}/{len(new_files)}] {fname} → doc {doc_status}: {doc_msg}")
                else:
                    fail += 1
                    print(f"  ❌ [{i+1}/{len(new_files)}] {fname} → upload {status}: {errmsg}")
            except Exception as e:
                fail += 1
                print(f"  ❌ [{i+1}/{len(new_files)}] {fname} → {e}")
            time.sleep(0.3)

        print(f"\n📊 Resultado: {ok} subidos, {fail} fallidos, {skip} omitidos (>15MB) de {len(new_files)} nuevos")
