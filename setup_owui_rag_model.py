#!/usr/bin/env python3
"""
Configura el modelo Seedy con RAG automático en Open WebUI.

Crea un modelo wrapper "seedy-rag" que usa el backend como proveedor OpenAI.
De este modo, toda pregunta pasa automáticamente por:
  Classify → Qdrant RAG (3644 chunks) → SearXNG web → Rerank → Ollama

Uso:
    python setup_owui_rag_model.py

Requisitos:
    - Open WebUI corriendo en localhost:3000
    - Seedy Backend corriendo en localhost:8000
    - OPENAI_API_BASE_URLS configurado en docker-compose
"""

import requests
import json
import sys

BASE_URL = "http://localhost:3000"

# ── Auth ─────────────────────────────────────
r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={
    "email": "durrif@gmail.com", "password": "4431Durr$"
})
if r.status_code != 200:
    print(f"❌ Error de autenticación: {r.status_code}")
    sys.exit(1)
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


# ── System prompt para el modelo RAG ─────────
SEEDY_RAG_SYSTEM = """Eres **Seedy**, el asistente IA de **NeoFarm** especializado en ganadería de precisión.

Tu conocimiento se amplía automáticamente con:
- **Base de conocimiento Qdrant** (3644+ chunks): normativa, genética, nutrición, IoT, avicultura, digital twins
- **Wikipedia** (271 artículos ES/FR/EN/IT/DE): razas bovinas, porcinas, avícolas, ovinas
- **Búsqueda web SearXNG**: cuando el conocimiento local no es suficiente

## Áreas de Expertise
1. **Nutrición & Formulación**: dietas, piensos, NRC 2012, butirato, enzimas, lonjas
2. **Genética**: razas porcinas (Duroc, Pietrain, Landrace, LW, Ibérico), vacunas (Angus, Limusín, Charolés, Retinta, Cachena), avícolas (Bresse, Marans, Sulmtaler), cruzamientos, EPDs, BLUP
3. **IoT & Sensores**: PorciData 7+1 capas, MQTT, ESP32, LoRa
4. **Digital Twins**: gemelos digitales, GeoTwin, Cesium 3D
5. **Visión Artificial**: BCS, cojeras, comportamiento
6. **Normativa**: RD 306/2020 (SIGE), RD 1135/2002, EcoGAN
7. **Avicultura**: capones gourmet, pulardas, Label Rouge, caponización

## Directrices
- Responde SIEMPRE en español (España) salvo que pidan otro idioma
- Sé técnico pero accesible con terminología ganadera precisa
- NO inventes razas, datos ni normativa que no conozcas
- Si el contexto RAG contiene la respuesta, úsalo y cita la fuente
- Si no tienes información suficiente, dilo claramente
- Incluye datos numéricos y unidades cuando sea posible
- Prioriza precisión técnica sobre tono comercial"""


# ── Verificar conexiones OpenAI ──────────────
print("=" * 60)
print("Configurando Seedy RAG Model en Open WebUI")
print("=" * 60)

# Check OpenAI connections
try:
    r = requests.get(f"{BASE_URL}/api/v1/configs", headers=H)
    if r.status_code == 200:
        print("✅ Open WebUI accesible")
except Exception as e:
    print(f"❌ Open WebUI no accesible: {e}")
    sys.exit(1)

# List available models (including OpenAI ones from backend)
r = requests.get(f"{BASE_URL}/api/models", headers=H)
if r.status_code == 200:
    models = r.json()
    openai_models = [m for m in models.get("data", []) if "seedy" in m.get("id", "").lower()]
    print(f"\nModelos 'seedy' disponibles:")
    for m in openai_models:
        print(f"  - {m['id']} ({m.get('owned_by', '?')})")
else:
    print(f"⚠️ No se pudieron listar modelos: {r.status_code}")


# ── Crear/actualizar modelo wrapper ──────────
r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
existing = {m["id"] for m in r.json().get("items", [])} if r.status_code == 200 else set()
print(f"\nModelos custom existentes: {existing}")

model_payload = {
    "id": "seedy-rag",
    "name": "🌱 Seedy RAG — NeoFarm AI",
    "base_model_id": "seedy",  # → backend OpenAI model "seedy"
    "params": {
        "system": SEEDY_RAG_SYSTEM,
        "temperature": 0.3,
        "top_p": 0.9,
        "num_ctx": 8192,
    },
    "meta": {
        "description": "Seedy con RAG automático (Qdrant + Wikipedia + SearXNG). Toda pregunta pasa por el pipeline inteligente.",
        "profile_image_url": "",
        "capabilities": {
            "vision": False,
            "usage": True
        },
        "suggestion_prompts": [
            {"title": "🐄 Raza Cachena", "content": "¿Qué tipo de animal es la Cachena y de dónde es originaria?"},
            {"title": "🐔 Bresse", "content": "¿Cuál es el apodo histórico de la raza Bresse y por qué es tan valorada?"},
            {"title": "📋 Normativa SIGE", "content": "¿Cuáles son los 11 planes obligatorios del RD 306/2020 sobre el SIGE?"},
            {"title": "🧬 Genética porcina", "content": "Compara Duroc vs Pietrain como línea padre terminal"},
            {"title": "📡 IoT PorciData", "content": "¿Qué sensores necesito para monitorizar una nave de gestación porcina?"},
            {"title": "🥗 Nutrición", "content": "¿Cuáles son los requerimientos de lisina digestible ileal de un cerdo en cebo (60-100kg)?"},
        ]
    },
    "access_grants": []
}

if "seedy-rag" not in existing:
    r = requests.post(f"{BASE_URL}/api/v1/models/create", headers=H, json=model_payload)
    if r.status_code == 200:
        print("✅ Modelo 'seedy-rag' (🌱 Seedy RAG — NeoFarm AI) CREADO")
    else:
        print(f"❌ Error creando seedy-rag: {r.status_code} - {r.text[:300]}")
else:
    r = requests.post(f"{BASE_URL}/api/v1/models/update", headers=H, json=model_payload)
    if r.status_code == 200:
        print("✅ Modelo 'seedy-rag' ACTUALIZADO")
    else:
        print(f"❌ Error actualizando seedy-rag: {r.status_code} - {r.text[:300]}")

# ── También actualizar seedy-main a v12 ──────
if "seedy-main" in existing:
    print("\nActualizando seedy-main a base seedy:v12...")
    r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
    for m in r.json().get("items", []):
        if m["id"] == "seedy-main":
            m["base_model_id"] = "seedy:v12"
            r2 = requests.post(f"{BASE_URL}/api/v1/models/update", headers=H, json=m)
            if r2.status_code == 200:
                print("✅ seedy-main actualizado a base seedy:v12")
            else:
                print(f"❌ Error: {r2.status_code}")
            break

# ── Estado final ─────────────────────────────
print(f"\n{'='*60}")
print("Estado final:")
print(f"{'='*60}")
r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
for m in r.json().get("items", []):
    mid = m["id"]
    name = m["name"]
    base = m.get("base_model_id", "?")
    tools = m.get("meta", {}).get("toolIds", [])
    print(f"  {name}")
    print(f"    ID: {mid}, Base: {base}, Tools: {tools}")

print(f"""
╔══════════════════════════════════════════════════════════╗
║  Para activar RAG automático:                           ║
║                                                         ║
║  1. docker compose up -d (recrea open-webui + backend)  ║
║  2. En Open WebUI, seleccionar modelo:                  ║
║     🌱 Seedy RAG — NeoFarm AI                          ║
║                                                         ║
║  Flujo automático por cada pregunta:                    ║
║    User → OpenWebUI → Backend → Classify → Qdrant RAG  ║
║    + SearXNG → Rerank → Ollama → Respuesta              ║
╚══════════════════════════════════════════════════════════╝
""")
