"""Limpieza del registro de aves — dedup contra censo.

Reconstruye birds_registry.json alineado con flock_census.json (26 aves),
preservando las mejores fotos del registro anterior.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

REG_PATH = Path("/app/data/birds_registry.json")
CENSUS_PATH = Path("/app/config/flock_census.json")
BACKUP = Path("/app/data/birds_registry_backup_pre_cleanup.json")

# ── Mapa de normalización: variantes de Gemini → (breed, color) del censo ──
BREED_NORM = {
    "vorwerk": ("Vorwerk", "dorado"),
    "vorwerk dorado": ("Vorwerk", "dorado"),
    "sussex": ("Sussex", None),  # color varía
    "sussex silver": ("Sussex", "silver"),
    "sussex white": ("Sussex", "white"),
    "sussex armiñada": ("Sussex", "white"),
    "bresse": ("Bresse", "blanco"),
    "bresse blanco": ("Bresse", "blanco"),
    "marans": ("Marans", "negro cobrizo"),
    "marans negro cobrizo": ("Marans", "negro cobrizo"),
    "sulmtaler": ("Sulmtaler", "trigueño"),
    "sulmtaler trigueño": ("Sulmtaler", "trigueño"),
    "f1 (cruce)": ("F1 (cruce)", "variado"),
    "f1 (cruce) variado": ("F1 (cruce)", "variado"),
    "andaluza azul": ("Andaluza Azul", "azul"),
    "andaluza azul azul": ("Andaluza Azul", "azul"),
    "pita pinta": ("Pita Pinta", "pinta"),
    "pita pinta pinta": ("Pita Pinta", "pinta"),
    "araucana": ("Araucana", None),  # color varía
    "araucana trigueña": ("Araucana", "trigueña"),
    "araucana negra": ("Araucana", "negra"),
    "ameraucana": ("Ameraucana", "trigueño"),
}


def normalize_bird(b):
    breed_key = b["breed"].lower().strip()
    norm = BREED_NORM.get(breed_key)
    if norm:
        breed, color = norm
        if color is None:
            orig_color = b.get("color", "").lower()
            if "silver" in orig_color or "plat" in orig_color:
                color = "silver"
            elif "white" in orig_color or "blanc" in orig_color or "armiñ" in orig_color:
                color = "white"
            else:
                color = "silver"
        return breed, color
    return b["breed"], b.get("color", "")


def main():
    if not REG_PATH.exists():
        print("ERROR: No existe birds_registry.json")
        sys.exit(1)

    # Load
    old_data = json.loads(REG_PATH.read_text(encoding="utf-8"))
    old_birds = old_data["birds"]
    census = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))

    # Backup
    BACKUP.write_text(json.dumps(old_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Backup → {BACKUP} ({len(old_birds)} aves)")

    # Normalize old birds
    for b in old_birds:
        b["_norm_breed"], b["_norm_color"] = normalize_bird(b)

    # Build census entries
    census_entries = []
    for gal_id, gal_data in census.items():
        if not isinstance(gal_data, dict) or "aves" not in gal_data:
            continue
        for entry in gal_data["aves"]:
            census_entries.append({
                "raza": entry["raza"],
                "color": entry["color"],
                "sexo": entry["sexo"],
                "cantidad": entry.get("cantidad", 0),
                "gallinero": gal_id if gal_id.startswith("gallinero_") else None,
                "notas": entry.get("notas", ""),
            })

    # For each census entry, find best matching old birds
    new_registry = []
    seq = 1
    used_ids = set()

    for ce in census_entries:
        raza = ce["raza"]
        color = ce["color"]
        sexo = ce["sexo"]
        cantidad = ce["cantidad"]
        gal = ce["gallinero"]

        if cantidad == 0:
            continue

        # Find candidate matches
        candidates = []
        for b in old_birds:
            if id(b) in used_ids:
                continue
            if b["_norm_breed"].lower() != raza.lower():
                continue
            if b["_norm_color"].lower() != color.lower():
                continue
            if b.get("sex", "unknown") != sexo:
                continue
            if gal and b.get("gallinero", "") != gal:
                continue
            candidates.append(b)

        candidates.sort(key=lambda x: (
            1 if x.get("photo_b64") else 0,
            x.get("confidence", 0),
            x.get("last_seen", ""),
        ), reverse=True)

        created = 0
        for c in candidates[:cantidad]:
            used_ids.add(id(c))
            bird_id = f"PAL-2026-{seq:04d}"
            new_bird = {
                "bird_id": bird_id,
                "breed": raza,
                "color": color,
                "sex": sexo,
                "gallinero": gal or c.get("gallinero", "gallinero_durrif_2"),
                "first_seen": c.get("first_seen", datetime.now(timezone.utc).isoformat()),
                "last_seen": c.get("last_seen", datetime.now(timezone.utc).isoformat()),
                "ia_vision_number": seq,
                "ai_vision_id": "",
                "confidence": c.get("confidence", 0.5),
                "photo_path": c.get("photo_path", ""),
                "photo_b64": c.get("photo_b64", ""),
                "notes": ce.get("notas", ""),
            }
            new_registry.append(new_bird)
            seq += 1
            created += 1

        # Placeholders for missing
        for _ in range(created, cantidad):
            bird_id = f"PAL-2026-{seq:04d}"
            new_bird = {
                "bird_id": bird_id,
                "breed": raza,
                "color": color,
                "sex": sexo,
                "gallinero": gal or "gallinero_durrif_2",
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "ia_vision_number": seq,
                "ai_vision_id": "",
                "confidence": 0.0,
                "photo_path": "",
                "photo_b64": "",
                "notes": f"Pendiente de identificar. {ce.get('notas', '')}",
            }
            new_registry.append(new_bird)
            seq += 1
            created += 1

        print(f"  {raza} {color} {sexo} [{gal or 'sin_asignar'}]: "
              f"{created}/{cantidad} (de {len(candidates)} candidatas)")

    # Rebuild ai_vision_id
    vid_counter: Counter = Counter()
    for b in new_registry:
        breed_slug = b["breed"].lower().replace(" ", "").replace("(", "").replace(")", "")
        color_slug = b["color"][:4].lower().replace(" ", "")
        vid_counter[(breed_slug, color_slug)] += 1
        b["ai_vision_id"] = f"{breed_slug}{color_slug}{vid_counter[(breed_slug, color_slug)]}"
        b["ia_vision_number"] = vid_counter[(breed_slug, color_slug)]

    # Save
    new_data = {"birds": new_registry, "next_seq": seq}
    REG_PATH.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== Resultado ===")
    print(f"Antes: {len(old_birds)} → Después: {len(new_registry)} aves")
    breed_counts = Counter(f"{b['breed']} {b['color']}" for b in new_registry)
    for breed, count in breed_counts.most_common():
        print(f"  {breed}: {count}")
    with_photo = sum(1 for b in new_registry if b.get("photo_b64"))
    print(f"Con foto: {with_photo} / Sin foto: {len(new_registry) - with_photo}")


if __name__ == "__main__":
    main()
