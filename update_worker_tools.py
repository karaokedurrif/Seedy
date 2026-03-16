#!/usr/bin/env python3
"""Update worker models to assign tools"""
import requests, json

BASE_URL = "http://localhost:3000"
r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={"email": "durrif@gmail.com", "password": "4431Durr$"})
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Get all custom models
r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
items = r.json().get("items", [])

worker_tools = {
    "seedy-chief-planner": ["wikipedia_search", "neofarm_kb", "datetime_calc", "webpage_reader"],
    "seedy-worker-rag": ["neofarm_kb", "wikipedia_search", "webpage_reader"],
    "seedy-worker-iot-data": ["neofarm_kb", "datetime_calc"],
    "seedy-worker-digital-twin": ["neofarm_kb", "datetime_calc"],
    "seedy-worker-web-automation": ["webpage_reader", "wikipedia_search", "datetime_calc"],
    "seedy-worker-coder-data": ["datetime_calc", "neofarm_kb"],
}

for model in items:
    mid = model["id"]
    if mid not in worker_tools:
        continue
    
    tools = worker_tools[mid]
    
    # Build full ModelForm payload
    meta = model.get("meta", {})
    meta["toolIds"] = tools
    
    payload = {
        "id": mid,
        "name": model["name"],
        "base_model_id": model.get("base_model_id", "seedy:v10"),
        "meta": meta,
        "params": model.get("params", {}),
        "is_active": model.get("is_active", True),
    }
    
    # Use correct endpoint: POST /api/v1/models/model/update
    r = requests.post(f"{BASE_URL}/api/v1/models/model/update", headers=H, json=payload)
    if r.status_code == 200:
        result = r.json()
        assigned = result.get("meta", {}).get("toolIds", [])
        print(f"✅ {mid}: tools={assigned}")
    else:
        print(f"❌ {mid}: {r.status_code} - {r.text[:200]}")

# Final verification
print("\n" + "=" * 60)
print("Estado final:")
r = requests.get(f"{BASE_URL}/api/v1/models/list", headers=H)
for m in r.json().get("items", []):
    tools = m.get("meta", {}).get("toolIds", [])
    print(f"  {m['id']}: tools={tools}")
