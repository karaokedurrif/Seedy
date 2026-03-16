#!/usr/bin/env python3
"""
Seedy — Actualizar motor del modelo visible en Open WebUI.

Cambia el modelo base de "🌱 Seedy — NeoFarm AI" sin que los usuarios
noten el cambio. Solo necesitas el nombre del nuevo modelo Ollama.

Uso:
    python scripts/update_seedy_engine.py seedy:v14
    python scripts/update_seedy_engine.py seedy:v15-dpo

Los usuarios siempre ven: 🌱 Seedy — NeoFarm AI
"""
import sys
import requests
import json

BASE_URL = "http://localhost:3000"
CUSTOM_MODEL_ID = "seedy-rag"

def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/update_seedy_engine.py <nuevo_modelo_ollama>")
        print("Ejemplo: python scripts/update_seedy_engine.py seedy:v14")
        sys.exit(1)

    new_engine = sys.argv[1]

    # Login as admin
    r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={
        "email": "durrif@gmail.com", "password": "4431Durr$"
    })
    if r.status_code != 200:
        print(f"❌ Login fallido: {r.status_code}")
        sys.exit(1)

    TOKEN = r.json()["token"]
    H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    # Get current model data
    r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
    seedy_model = None
    for m in r.json().get("items", []):
        if m["id"] == CUSTOM_MODEL_ID:
            seedy_model = m
            break

    if not seedy_model:
        print(f"❌ Modelo '{CUSTOM_MODEL_ID}' no encontrado en Open WebUI")
        sys.exit(1)

    old_engine = seedy_model.get("base_model_id", "?")
    print(f"Motor actual: {old_engine}")
    print(f"Motor nuevo:  {new_engine}")

    # Verify new engine exists in Ollama
    r = requests.get(f"{BASE_URL}/ollama/api/tags", headers=H)
    ollama_models = {m["name"] for m in r.json().get("models", [])}
    if new_engine not in ollama_models:
        print(f"\n⚠️  '{new_engine}' no está en Ollama. Modelos disponibles:")
        for m in sorted(ollama_models):
            print(f"    {m}")
        print("\nContinuando de todas formas (puede ser un modelo OpenAI)...")

    # Update base_model_id
    update = {
        "id": CUSTOM_MODEL_ID,
        "name": "🌱 Seedy — NeoFarm AI",
        "base_model_id": new_engine,
        "params": seedy_model.get("params", {}),
        "meta": seedy_model.get("meta", {}),
        "access_control": None,
        "is_active": True,
    }

    r = requests.post(f"{BASE_URL}/api/v1/models/model/update", headers=H, json=update)
    if r.status_code == 200:
        print(f"\n✅ Motor actualizado: {old_engine} → {new_engine}")
        print("   Los usuarios siguen viendo: 🌱 Seedy — NeoFarm AI")
    else:
        print(f"\n❌ Error actualizando: {r.status_code} {r.text[:200]}")
        sys.exit(1)

    # Ensure public access_grant exists (OWUI 0.8.8+)
    r = requests.post(
        f"{BASE_URL}/api/v1/models/model/access/update",
        headers=H,
        json={
            "id": CUSTOM_MODEL_ID,
            "access_grants": [
                {"principal_type": "user", "principal_id": "*", "permission": "read"}
            ],
        },
    )
    if r.status_code == 200:
        print("   AccessGrant público confirmado ✅")
    else:
        print(f"   ⚠️  No se pudo crear access_grant: {r.status_code}")


if __name__ == "__main__":
    main()
