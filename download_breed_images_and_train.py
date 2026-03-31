#!/usr/bin/env python3
"""
Seedy — Descarga fotos de razas de gallinas/gallos y entrena YOLO

Lee las razas reales de OvoSfera + flock_census.json,
descarga imágenes de referencia por raza+color+sexo via DuckDuckGo,
monta un dataset YOLO clasificado y lanza fine-tune.

Uso:
  python download_breed_images_and_train.py                 # descarga + dataset
  python download_breed_images_and_train.py --train         # + lanza entrenamiento
  python download_breed_images_and_train.py --only-train    # solo entrena (ya descargado)
  python download_breed_images_and_train.py --list          # lista razas sin descargar
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import random
import sys
import time
from pathlib import Path
from collections import defaultdict

import httpx
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("breed_dl")

# ── Configuración ──────────────────────────────────────────

OVOSFERA_API = os.environ.get(
    "OVOSFERA_API_URL", "https://hub.ovosfera.com/api/ovosfera"
)
OVOSFERA_FARM = os.environ.get("OVOSFERA_FARM_SLUG", "palacio")

BASE_DIR = Path(__file__).parent
CENSUS_PATH = BASE_DIR / "backend" / "config" / "flock_census.json"
DATASET_DIR = BASE_DIR / "yolo_breed_dataset"
IMAGES_PER_CLASS = 80  # ~80 imágenes por raza+sexo (train + val)
MIN_IMG_SIZE = 200     # px mínimos de ancho/alto

# ── Clases YOLO (alineadas con yolo_trainer.py SEEDY_CLASSES) ──
#
# Mapeo: cada raza es una clase.  Gallo vs gallina se distingue
# por la variante del nombre de clase (ej. "sussex" vs "sussex_gallo").
# Esto permite que YOLO detecte raza + sexo de un vistazo.

BREED_CLASSES = {
    # clase_id: (nombre_clase, queries_busqueda_ES, queries_EN)
    0:  ("vorwerk_gallina",
         ["gallina Vorwerk dorado", "gallina raza Vorwerk", "Vorwerk hen gold"],
         ["Vorwerk chicken hen", "Vorwerk poultry female"]),
    1:  ("vorwerk_gallo",
         ["gallo Vorwerk", "Vorwerk rooster gold black"],
         ["Vorwerk rooster", "Vorwerk chicken male"]),
    2:  ("sussex_silver_gallina",
         ["gallina Sussex silver", "gallina Sussex plateada", "Sussex Light hen"],
         ["Sussex Light chicken hen", "Sussex silver hen"]),
    3:  ("sussex_silver_gallo",
         ["gallo Sussex silver", "Sussex Light rooster", "Sussex silver gallo"],
         ["Sussex Light rooster", "Sussex silver rooster"]),
    4:  ("sussex_white_gallina",
         ["gallina Sussex blanca", "Sussex White hen"],
         ["Sussex White chicken hen", "white Sussex hen poultry"]),
    5:  ("sulmtaler_gallina",
         ["gallina Sulmtaler trigueña", "Sulmtaler hen wheaten"],
         ["Sulmtaler chicken hen", "Sulmtaler poultry female wheaten"]),
    6:  ("sulmtaler_gallo",
         ["gallo Sulmtaler trigueño", "Sulmtaler rooster wheaten"],
         ["Sulmtaler rooster", "Sulmtaler chicken male"]),
    7:  ("marans_gallina",
         ["gallina Marans negro cobrizo", "Marans Black Copper hen"],
         ["Marans Black Copper Maran hen", "Black Copper Marans chicken"]),
    8:  ("bresse_gallina",
         ["gallina Bresse blanca", "Bresse Gauloise hen white"],
         ["Bresse Gauloise white hen", "Bresse chicken white female"]),
    9:  ("bresse_gallo",
         ["gallo Bresse blanco", "Bresse Gauloise rooster white"],
         ["Bresse Gauloise white rooster", "Bresse chicken white male"]),
    10: ("andaluza_azul_gallina",
         ["gallina Andaluza Azul", "Blue Andalusian hen"],
         ["Blue Andalusian chicken hen", "Andaluza Azul poultry"]),
    11: ("pita_pinta_gallina",
         ["gallina Pita Pinta Asturiana", "Pita Pinta Asturiana hen"],
         ["Pita Pinta Asturiana chicken", "Pita Pinta hen poultry"]),
    12: ("araucana_gallina",
         ["gallina Araucana trigueña", "gallina Araucana negra", "Araucana hen"],
         ["Araucana chicken hen", "Araucana rumpless hen"]),
    13: ("ameraucana_gallina",
         ["gallina Ameraucana", "Ameraucana hen blue egg", "Easter Egger hen"],
         ["Ameraucana chicken hen", "Ameraucana poultry female"]),
}

# Total: 14 clases visuales.
# F1 (cruces) se identifican por DESCARTE del censo.


def list_breeds():
    """Lista las razas configuradas para descarga."""
    print(f"\n{'ID':>3}  {'Clase YOLO':25s}  Queries")
    print("─" * 80)
    for cls_id, (name, q_es, q_en) in sorted(BREED_CLASSES.items()):
        print(f"{cls_id:3d}  {name:25s}  {q_es[0]}")
    print(f"\nTotal: {len(BREED_CLASSES)} clases")
    print(f"Imágenes por clase: {IMAGES_PER_CLASS}")
    print(f"Dataset dir: {DATASET_DIR}")


def download_images_bing(query: str, max_results: int = 50) -> list[dict]:
    """Descarga URLs de imágenes via Bing Image Search (scraping, sin API key)."""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        encoded_q = httpx.URL(f"https://www.bing.com/images/search?q={query}&first=1&count={max_results}&qft=+filterui:photo-photo")
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(str(encoded_q))
            if resp.status_code != 200:
                log.warning(f"Bing returned {resp.status_code} for '{query}'")
                return results

            import re
            # Extract image URLs from murl="..." attributes
            urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)
            for url in urls[:max_results]:
                results.append({"image": url})
    except Exception as e:
        log.warning(f"Bing search failed for '{query}': {e}")
    return results


def download_images_ddg(query: str, max_results: int = 50) -> list[dict]:
    """Intenta Bing primero, fallback a DDG si Bing falla."""
    results = download_images_bing(query, max_results)
    if results:
        return results

    # Fallback DDG
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for r in ddgs.images(query, max_results=max_results):
                results.append(r)
    except Exception as e:
        log.debug(f"DDG fallback also failed for '{query}': {e}")
    return results


def download_and_validate_image(url: str, save_path: Path, timeout: float = 10.0) -> bool:
    """Descarga una imagen, valida que sea un JPEG/PNG válido y la guarda como JPEG."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return False
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                return False

            img = Image.open(__import__("io").BytesIO(resp.content))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            elif img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg

            w, h = img.size
            if w < MIN_IMG_SIZE or h < MIN_IMG_SIZE:
                return False

            # Resize si es muy grande (>1024px)
            if max(w, h) > 1024:
                img.thumbnail((1024, 1024), Image.LANCZOS)

            img.save(save_path, "JPEG", quality=90)
            return True
    except Exception:
        return False


def download_breed_images():
    """Descarga imágenes para todas las razas configuradas."""
    log.info(f"📸 Descargando imágenes de {len(BREED_CLASSES)} razas...")
    log.info(f"   Objetivo: {IMAGES_PER_CLASS} imágenes por clase")
    log.info(f"   Destino: {DATASET_DIR}")

    raw_dir = DATASET_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    total_downloaded = 0

    for cls_id, (cls_name, queries_es, queries_en) in sorted(BREED_CLASSES.items()):
        cls_dir = raw_dir / cls_name
        cls_dir.mkdir(parents=True, exist_ok=True)

        existing = len(list(cls_dir.glob("*.jpg")))
        if existing >= IMAGES_PER_CLASS:
            log.info(f"  ✅ {cls_name}: ya tiene {existing} imágenes, skip")
            total_downloaded += existing
            continue

        needed = IMAGES_PER_CLASS - existing
        log.info(f"  🔍 {cls_name}: descargando {needed} imágenes más (tiene {existing})...")

        # Recopilar URLs de todas las queries
        all_urls = []
        all_queries = queries_es + queries_en
        per_query = max(30, needed // len(all_queries) + 10)

        for query in all_queries:
            results = download_images_ddg(query, max_results=per_query)
            for r in results:
                url = r.get("image", "")
                if url and url not in [u for u, _ in all_urls]:
                    all_urls.append((url, query))
            time.sleep(0.5)  # Rate limit DDG

        random.shuffle(all_urls)
        log.info(f"    Encontrados {len(all_urls)} URLs candidatos")

        downloaded = existing
        for url, _q in all_urls:
            if downloaded >= IMAGES_PER_CLASS:
                break

            # Hash del URL para nombre único
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            save_path = cls_dir / f"{cls_name}_{url_hash}.jpg"
            if save_path.exists():
                continue

            if download_and_validate_image(url, save_path):
                downloaded += 1
                if downloaded % 10 == 0:
                    log.info(f"    {cls_name}: {downloaded}/{IMAGES_PER_CLASS}")
            time.sleep(0.3)

        total_downloaded += downloaded
        log.info(f"  ✅ {cls_name}: {downloaded}/{IMAGES_PER_CLASS} imágenes")

    log.info(f"\n📸 Total descargado: {total_downloaded} imágenes")
    return total_downloaded


def build_yolo_dataset():
    """Construye dataset YOLO clasificación → detección a partir de raw/.

    Como las imágenes descargadas son fotos completas de una gallina/gallo,
    la bbox es toda la imagen (o ~90% centro).
    Para YOLO: label = cls_id cx cy w h (normalizado).
    """
    raw_dir = DATASET_DIR / "raw"
    if not raw_dir.exists():
        log.error("No hay imágenes descargadas. Ejecuta primero sin --only-train")
        return False

    # Limpiar dataset previo
    for split in ("train", "val"):
        img_dir = DATASET_DIR / "images" / split
        lbl_dir = DATASET_DIR / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    class_counts = defaultdict(lambda: {"train": 0, "val": 0})

    for cls_id, (cls_name, _, _) in sorted(BREED_CLASSES.items()):
        cls_dir = raw_dir / cls_name
        if not cls_dir.exists():
            continue

        images = sorted(cls_dir.glob("*.jpg"))
        random.shuffle(images)

        for i, img_path in enumerate(images):
            # 85% train, 15% val
            split = "val" if i < max(1, len(images) * 15 // 100) else "train"

            dest_img = DATASET_DIR / "images" / split / img_path.name
            dest_lbl = DATASET_DIR / "labels" / split / img_path.with_suffix(".txt").name

            # Copiar imagen
            shutil.copy2(img_path, dest_img)

            # Label: bbox cubriendo ~90% centro de la imagen
            # YOLO format: cls_id cx cy w h (normalizado 0-1)
            # Usamos bbox centered 0.5 0.5 0.9 0.9 (90% del frame)
            dest_lbl.write_text(f"{cls_id} 0.5 0.5 0.9 0.9\n")

            class_counts[cls_name][split] += 1
            total += 1

    # Generar dataset.yaml
    names_block = "\n".join(
        f"  {cls_id}: {name}"
        for cls_id, (name, _, _) in sorted(BREED_CLASSES.items())
    )
    yaml_content = (
        f"# Seedy Breed Dataset — Auto-generated\n"
        f"# {len(BREED_CLASSES)} razas de gallinas/gallos\n\n"
        f"path: {DATASET_DIR}\n"
        f"train: images/train\n"
        f"val: images/val\n\n"
        f"nc: {len(BREED_CLASSES)}\n"
        f"names:\n{names_block}\n"
    )
    yaml_path = DATASET_DIR / "dataset.yaml"
    yaml_path.write_text(yaml_content)

    log.info(f"\n📊 Dataset YOLO montado: {total} imágenes")
    log.info(f"   YAML: {yaml_path}")
    for cls_name, counts in sorted(class_counts.items()):
        log.info(f"   {cls_name:30s}  train={counts['train']:3d}  val={counts['val']:3d}")

    return True


def train_yolo(epochs: int = 100, batch: int = 16, imgsz: int = 640):
    """Lanza fine-tune de YOLO con el dataset de razas."""
    from ultralytics import YOLO

    yaml_path = DATASET_DIR / "dataset.yaml"
    if not yaml_path.exists():
        log.error("No hay dataset.yaml. Ejecuta primero sin --only-train")
        return

    models_dir = BASE_DIR / "yolo_breed_models"
    models_dir.mkdir(parents=True, exist_ok=True)

    run_name = f"seedy_breeds_{time.strftime('%Y%m%d_%H%M%S')}"
    base_model = os.environ.get("YOLO_MODEL", "yolov8s.pt")

    log.info(f"\n🚂 Entrenando YOLO {base_model} → {len(BREED_CLASSES)} clases de razas")
    log.info(f"   Epochs: {epochs}, Batch: {batch}, Imgsz: {imgsz}")
    log.info(f"   Dataset: {yaml_path}")
    log.info(f"   Run: {run_name}")

    model = YOLO(base_model)
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        project=str(models_dir),
        name=run_name,
        device="0",          # GPU
        patience=15,          # Early stopping
        save=True,
        plots=True,
        verbose=True,
        # Augmentaciones para pocas imágenes
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        degrees=10.0,
        translate=0.1,
        scale=0.3,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
    )

    # Copiar best.pt
    best_pt = models_dir / run_name / "weights" / "best.pt"
    if best_pt.exists():
        target = models_dir / "seedy_breeds_best.pt"
        shutil.copy2(best_pt, target)
        log.info(f"\n✅ Modelo guardado: {target}")
        log.info(f"   Para usar en Seedy: docker cp {target} seedy-backend:/app/yolo_models/")
        log.info(f"   Luego: YOLO_MODEL=/app/yolo_models/seedy_breeds_best.pt")
    else:
        log.warning("No se encontró best.pt tras entrenamiento")


def main():
    parser = argparse.ArgumentParser(
        description="Descarga fotos de razas de gallinas y entrena YOLO"
    )
    parser.add_argument("--list", action="store_true",
                        help="Solo listar razas sin descargar")
    parser.add_argument("--train", action="store_true",
                        help="Descargar imágenes + entrenar YOLO")
    parser.add_argument("--only-train", action="store_true",
                        help="Solo entrenar (imágenes ya descargadas)")
    parser.add_argument("--epochs", type=int, default=100,
                        help="Epochs de entrenamiento (default: 100)")
    parser.add_argument("--batch", type=int, default=16,
                        help="Batch size (default: 16)")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="Tamaño de imagen YOLO (default: 640)")
    parser.add_argument("--images-per-class", type=int, default=80,
                        help="Imágenes a descargar por clase (default: 80)")
    args = parser.parse_args()

    if args.list:
        list_breeds()
        return

    global IMAGES_PER_CLASS
    IMAGES_PER_CLASS = args.images_per_class

    if args.only_train:
        if not build_yolo_dataset():
            return
        train_yolo(epochs=args.epochs, batch=args.batch, imgsz=args.imgsz)
        return

    # Descarga
    download_breed_images()
    # Montar dataset
    if not build_yolo_dataset():
        return

    if args.train:
        train_yolo(epochs=args.epochs, batch=args.batch, imgsz=args.imgsz)
    else:
        log.info("\n💡 Imágenes descargadas y dataset montado.")
        log.info("   Para entrenar YOLO añade --train:")
        log.info(f"   python {Path(__file__).name} --train --epochs {args.epochs}")


if __name__ == "__main__":
    main()
