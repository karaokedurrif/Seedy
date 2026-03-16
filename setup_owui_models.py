#!/usr/bin/env python3
"""
Configure Seedy models in Open WebUI: system prompts + tool assignments
"""
import requests, json, sys

BASE_URL = "http://localhost:3000"

# Auth
r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={
    "email": "durrif@gmail.com", "password": "4431Durr$"
})
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# ─────────────────────────────────────────────
# System prompt for Seedy main model
# ─────────────────────────────────────────────
SEEDY_SYSTEM = """Eres **Seedy**, el asistente IA de **NeoFarm** especializado en ganadería de precisión (porcino intensivo y vacuno extensivo).

## Identidad
- Nombre: Seedy (de "seed" = semilla + "see" = ver + "-dy" = dinámico)
- Creador: David Durrif, CEO de NeoFarm
- Plataforma: NeoFarm — gestión inteligente ganadera con IoT, Digital Twins, IA y visión artificial

## Áreas de Expertise
1. **Nutrición & Formulación**: dietas, piensos, aminoácidos, lonjas de precios
2. **Genética**: razas porcinas (Duroc, Pietrain, Landrace, Large White, Ibérico), vacunas (Angus, Limusín, Charolés, Retinta), cruzamientos, índices genéticos
3. **IoT & Sensores**: PorciData (sensores ambientales), monitorización temperatura/humedad/CO2/NH3, alertas
4. **Digital Twins**: gemelos digitales de explotaciones, simulación predictiva
5. **Visión Artificial**: detección de cojeras, BCS, comportamiento, conteo, identificación
6. **Normativa & Bienestar**: RD 306/2020 (SIGE), RD 1135/2002, EcoGAN, bienestar animal
7. **Estrategia & Mercado**: análisis competitivo, precios de mercado, tendencias sector

## Herramientas Disponibles
Tienes acceso a herramientas para ampliar tu conocimiento:
- **Wikipedia Search**: Busca definiciones y conceptos en Wikipedia
- **NeoFarm KB**: Consulta la base de conocimiento técnico con 298 documentos
- **Calculadora**: Realiza cálculos (índices de conversión, fórmulas nutricionales, costes)
- **Lector Web**: Lee páginas web para obtener información actualizada
- **Búsqueda Web**: SearXNG integrado para buscar en Google, Scholar, PubMed, arXiv

Usa las herramientas cuando necesites información que no tienes en tu conocimiento base.

## Directrices
- Responde SIEMPRE en español (España) salvo que te pidan otro idioma
- Sé técnico pero accesible. Usa terminología ganadera precisa
- Cuando no sepas algo, busca en la KB o en la web antes de decir que no sabes
- Cita fuentes cuando uses información de herramientas
- Para preguntas técnicas complejas, estructura la respuesta con secciones
- Incluye datos numéricos y referencias cuando sea posible
- Si detectas una pregunta sobre precios de mercado, sugiere consultar lonjas actualizadas"""

# ─────────────────────────────────────────────
# Tool IDs to assign
# ─────────────────────────────────────────────
ALL_TOOL_IDS = ["wikipedia_search", "neofarm_kb", "datetime_calc", "webpage_reader"]

# ─────────────────────────────────────────────
# 1. Create main Seedy model wrapping seedy:v10
# ─────────────────────────────────────────────
print("=" * 60)
print("Configurando modelos Seedy en Open WebUI")
print("=" * 60)

# Check if seedy-main already exists
r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
existing = {m["id"] for m in r.json().get("items", [])}
print(f"\nModelos custom existentes: {existing}")

if "seedy-main" not in existing:
    # Create main Seedy model
    payload = {
        "id": "seedy-main",
        "name": "🌱 Seedy — NeoFarm AI",
        "base_model_id": "seedy:v10",
        "params": {
            "system": SEEDY_SYSTEM,
            "temperature": 0.7,
            "top_p": 0.9,
            "num_ctx": 8192,
        },
        "meta": {
            "description": "Asistente IA de NeoFarm - Ganadería de Precisión (Porcino & Vacuno)",
            "profile_image_url": "",
            "toolIds": ALL_TOOL_IDS,
            "capabilities": {
                "vision": False,
                "usage": True
            },
            "suggestion_prompts": [
                {"title": "Nutrición porcina", "content": "¿Cuáles son los requerimientos nutricionales de un cerdo en fase de cebo (60-100kg)?"},
                {"title": "Normativa SIGE", "content": "Explica los requisitos del RD 306/2020 sobre el SIGE para explotaciones porcinas"},
                {"title": "IoT y sensores", "content": "¿Qué sensores necesito para monitorizar una nave de gestación porcina?"},
                {"title": "Genética porcina", "content": "Compara las líneas genéticas Duroc vs Pietrain para uso como línea padre terminal"},
            ]
        },
        "access_grants": []
    }
    r = requests.post(f"{BASE_URL}/api/v1/models/create", headers=H, json=payload)
    if r.status_code == 200:
        print("✅ Modelo 'seedy-main' (🌱 Seedy — NeoFarm AI) CREADO")
    else:
        print(f"❌ Error creando seedy-main: {r.status_code} - {r.text[:200]}")
else:
    # Update existing
    payload = {
        "id": "seedy-main",
        "name": "🌱 Seedy — NeoFarm AI",
        "base_model_id": "seedy:v10",
        "params": {
            "system": SEEDY_SYSTEM,
            "temperature": 0.7,
            "top_p": 0.9,
            "num_ctx": 8192,
        },
        "meta": {
            "description": "Asistente IA de NeoFarm - Ganadería de Precisión (Porcino & Vacuno)",
            "toolIds": ALL_TOOL_IDS,
            "suggestion_prompts": [
                {"title": "Nutrición porcina", "content": "¿Cuáles son los requerimientos nutricionales de un cerdo en fase de cebo (60-100kg)?"},
                {"title": "Normativa SIGE", "content": "Explica los requisitos del RD 306/2020 sobre el SIGE para explotaciones porcinas"},
                {"title": "IoT y sensores", "content": "¿Qué sensores necesito para monitorizar una nave de gestación porcina?"},
                {"title": "Genética porcina", "content": "Compara las líneas genéticas Duroc vs Pietrain para uso como línea padre terminal"},
            ]
        }
    }
    r = requests.post(f"{BASE_URL}/api/v1/models/update", headers=H, json=payload)
    if r.status_code == 200:
        print("✅ Modelo 'seedy-main' ACTUALIZADO")
    else:
        print(f"❌ Error actualizando seedy-main: {r.status_code} - {r.text[:200]}")

# ─────────────────────────────────────────────
# 2. Assign tools to worker models
# ─────────────────────────────────────────────
worker_tools = {
    "seedy-chief-planner": ALL_TOOL_IDS,
    "seedy-worker-rag": ["neofarm_kb", "wikipedia_search", "webpage_reader"],
    "seedy-worker-iot-data": ["neofarm_kb", "datetime_calc"],
    "seedy-worker-digital-twin": ["neofarm_kb", "datetime_calc"],
    "seedy-worker-web-automation": ["webpage_reader", "wikipedia_search", "datetime_calc"],
    "seedy-worker-coder-data": ["datetime_calc", "neofarm_kb"],
}

print("\nAsignando herramientas a workers:")
for model_id, tools in worker_tools.items():
    if model_id not in existing:
        print(f"  ⚠️ {model_id} no existe, saltando")
        continue
    
    # Get current config
    r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
    current_model = None
    for m in r.json().get("items", []):
        if m["id"] == model_id:
            current_model = m
            break
    
    if not current_model:
        print(f"  ⚠️ {model_id} no encontrado")
        continue
    
    # Update with tools
    meta = current_model.get("meta", {})
    meta["toolIds"] = tools
    
    update_payload = {
        "id": model_id,
        "name": current_model["name"],
        "base_model_id": current_model.get("base_model_id", "seedy:v10"),
        "params": current_model.get("params", {}),
        "meta": meta
    }
    
    r = requests.post(f"{BASE_URL}/api/v1/models/update", headers=H, json=update_payload)
    if r.status_code == 200:
        print(f"  ✅ {model_id}: tools={tools}")
    else:
        print(f"  ❌ {model_id}: {r.status_code} - {r.text[:100]}")

# ─────────────────────────────────────────────
# 3. Verify final state
# ─────────────────────────────────────────────
print(f"\n{'='*60}")
print("Estado final de modelos configurados:")
print(f"{'='*60}")
r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
for m in r.json().get("items", []):
    mid = m["id"]
    name = m["name"]
    tools = m.get("meta", {}).get("toolIds", [])
    sys_len = len(m.get("params", {}).get("system", ""))
    print(f"  {name}")
    print(f"    ID: {mid}, Base: {m.get('base_model_id','?')}")
    print(f"    System prompt: {sys_len} chars")
    print(f"    Tools: {tools}")
    print()
