#!/usr/bin/env python3
"""
Create Knowledge collections in Open WebUI and upload key documents.
We upload the summary/RAG docs to Open WebUI's native RAG, while the full
298-doc KB stays in Dify (accessible via the neofarm_kb tool).
"""
import requests, json, os, glob

BASE_URL = "http://localhost:3000"

# Auth
r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={"email": "durrif@gmail.com", "password": "4431Durr$"})
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
H_UPLOAD = {"Authorization": f"Bearer {TOKEN}"}

CONOCIMIENTOS = "/home/davidia/Documentos/Seedy/conocimientos"

# ─────────────────────────────────────────────
# Step 1: Check current knowledge & upload endpoint
# ─────────────────────────────────────────────
r = requests.get(f"{BASE_URL}/api/v1/knowledge/", headers=H)
print(f"Current knowledge collections: {len(r.json()) if r.status_code == 200 else r.status_code}")

# ─────────────────────────────────────────────
# Step 2: Upload files first 
# ─────────────────────────────────────────────
# Key summary/RAG docs to upload to Open WebUI
key_docs = [
    # Resúmenes
    f"{CONOCIMIENTOS}/1.PorciData — IoT & Hardware/_RESUMEN_PorciData_IoT_Hardware.md",
    f"{CONOCIMIENTOS}/2.Nutricion & Formulacion/_RESUMEN_NeoFarm_Nutricion_Papers.md",
    f"{CONOCIMIENTOS}/6.Normativa & SIGE  /_RESUMEN_Normativa_SIGE_Porcino.md",
    # Genética
    f"{CONOCIMIENTOS}/3.NeoFarm Genetica/MODULO_GENETICA_PORCINO_INTENSIVO_RAG.md",
    f"{CONOCIMIENTOS}/3.NeoFarm Genetica/MODULO_GENETICA_VACUNO_EXTENSIVO_RAG.md",
    # Digital Twins & IoT
    f"{CONOCIMIENTOS}/5.Digital Twins & IoT/NeoFarm_DigitalTwins_IA_Porcino_RAG.md",
    f"{CONOCIMIENTOS}/5.Digital Twins & IoT/NeoFarm_DigitalTwins_IA_Vacuno_RAG.md",
    f"{CONOCIMIENTOS}/5.Digital Twins & IoT/IOT_SOW_MONITORING_SYSTEM_RAG_v2.md",
    # Normativa
    f"{CONOCIMIENTOS}/6.Normativa & SIGE  /ECOGAN_PORCINO_2026_RAG.md",
    f"{CONOCIMIENTOS}/6.Normativa & SIGE  /RD1135_2002_GUIA_APLICACION_RAG_PORCINO.md",
    f"{CONOCIMIENTOS}/6.Normativa & SIGE  /RD306_2020_SIGE_Porcino.md",
    # Estrategia
    f"{CONOCIMIENTOS}/4.Estrategia & Competencia/NEOFARM_ARQUITECTURA_MAESTRA_PORCINO_VACUNO_RAG_2026.md",
    # Avicultura
    f"{CONOCIMIENTOS}/7.Avicultura Extensiva & Capones/MODULO_AVICULTURA_CAPONES_RAG.md",
    # Fuentes externas
    f"{CONOCIMIENTOS}/7.Fuentes_Externas/Vision_Artificial_Porcino_AIFARMS_PigLife.md",
    f"{CONOCIMIENTOS}/7.Fuentes_Externas/CEP_AgrospAI_Alimentacion_Automatica_Porcino.md",
    # GeoTwin
    f"{CONOCIMIENTOS}/7.GeoTwin & GIS 3D/GEOTWIN_PLATAFORMA_GIS_3D_RAG.md",
    # Nutrición RAF completo
    f"{CONOCIMIENTOS}/2.Nutricion & Formulacion/RAF Nutricion & Formulacion + Lonjas.md",
    # Roadmap
    f"{CONOCIMIENTOS}/SEEDY_MASTER_ROADMAP_2026.md",
]

uploaded_file_ids = []
print(f"\nSubiendo {len(key_docs)} documentos clave a Open WebUI...")

for doc_path in key_docs:
    if not os.path.exists(doc_path):
        print(f"  ⚠️ No existe: {os.path.basename(doc_path)}")
        continue
    
    filename = os.path.basename(doc_path)
    
    with open(doc_path, "rb") as f:
        files = {"file": (filename, f, "text/markdown")}
        r = requests.post(f"{BASE_URL}/api/v1/files/", headers=H_UPLOAD, files=files)
    
    if r.status_code == 200:
        file_data = r.json()
        file_id = file_data.get("id", "?")
        uploaded_file_ids.append(file_id)
        print(f"  ✅ {filename} → {file_id}")
    else:
        print(f"  ❌ {filename}: {r.status_code} - {r.text[:100]}")

print(f"\nTotal archivos subidos: {len(uploaded_file_ids)}")

# ─────────────────────────────────────────────
# Step 3: Create Knowledge collection
# ─────────────────────────────────────────────
print("\nCreando colección de conocimiento...")

knowledge_payload = {
    "name": "NeoFarm - Base de Conocimiento Técnico",
    "description": "Documentación técnica de NeoFarm: genética, nutrición, IoT, digital twins, normativa, visión artificial, avicultura y estrategia para ganadería de precisión porcina y vacuna.",
    "data": {
        "file_ids": uploaded_file_ids
    }
}

r = requests.post(f"{BASE_URL}/api/v1/knowledge/create", headers=H, json=knowledge_payload)
if r.status_code == 200:
    kb = r.json()
    kb_id = kb.get("id", "?")
    print(f"✅ Colección creada: {kb.get('name', '?')} (id={kb_id})")
    print(f"   Archivos: {len(uploaded_file_ids)}")
    
    # Now add files to the knowledge collection
    for fid in uploaded_file_ids:
        r2 = requests.post(f"{BASE_URL}/api/v1/knowledge/{kb_id}/file/add", 
                          headers=H, json={"file_id": fid})
        if r2.status_code == 200:
            pass  # silently added
        else:
            print(f"  ⚠️ Error añadiendo file {fid}: {r2.status_code}")
    
    print(f"   ✅ Todos los archivos vinculados a la colección")
else:
    print(f"❌ Error creando colección: {r.status_code} - {r.text[:300]}")

# ─────────────────────────────────────────────
# Step 4: Verify
# ─────────────────────────────────────────────
print(f"\n{'='*60}")
print("Verificación final:")
r = requests.get(f"{BASE_URL}/api/v1/knowledge/", headers=H)
if r.status_code == 200:
    collections = r.json()
    if isinstance(collections, dict):
        items = collections.get("items", collections.get("data", []))
    else:
        items = collections
    print(f"Total colecciones: {len(items)}")
    for c in items:
        if isinstance(c, dict):
            print(f"  📚 {c.get('name', '?')} - {c.get('description', '')[:80]}...")
            files = c.get("data", {}).get("file_ids", []) if isinstance(c.get("data"), dict) else []
            print(f"     Archivos: {len(files)}")
else:
    print(f"Error: {r.status_code}")

r = requests.get(f"{BASE_URL}/api/v1/files/", headers=H)
if r.status_code == 200:
    files = r.json()
    if isinstance(files, list):
        print(f"\nTotal archivos en Open WebUI: {len(files)}")
    elif isinstance(files, dict):
        print(f"\nTotal archivos en Open WebUI: {files.get('total', len(files.get('items', [])))}")
