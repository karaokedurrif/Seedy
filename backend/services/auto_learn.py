"""Seedy Backend — Auto-Learning Orchestrator.

Cinco ciclos de aprendizaje automatizados:

1. **YOLO breed retrain** (cada 6h)
   - Cuenta frames acumulados desde el último entrenamiento
   - Si hay ≥ YOLO_RETRAIN_THRESHOLD nuevos → lanza train_model()
   - Auto-recarga el modelo breed en el detector (hot-reload)
   - Guarda métricas en marker file

2. **DPO dataset snapshot** (cada 24h)
   - Lee dpo_pairs.jsonl, cuenta pares nuevos
   - Crea snapshot fechado + resumen para fine-tune manual
   - Genera training_config.json listo para TRL DPOTrainer

3. **Vision dataset stats** (cada 24h)
   - Cuenta imágenes y pares en vision_dataset/
   - Log de progreso, snapshot cuando > umbral

4. **Knowledge agent** (cada 4h en puesta en marcha, luego 12h)
   - Detecta gaps en colecciones, busca contenido, promueve de fresh_web

5. **Reporting agent** (cada 24h)
   - Lee chats de Open WebUI + critic_log + knowledge reports
   - Analiza conversaciones, ejecuta mejoras automáticas
   - Envía informe por email

Todos los loops corren como asyncio tasks lanzadas desde main.py.
"""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Configuración (env vars con defaults sensatos) ──

# YOLO
YOLO_RETRAIN_INTERVAL = int(os.environ.get("YOLO_RETRAIN_INTERVAL", 6 * 3600))  # 6h
YOLO_RETRAIN_THRESHOLD = int(os.environ.get("YOLO_RETRAIN_THRESHOLD", 100))  # mínimo frames nuevos
YOLO_RETRAIN_MIN_TOTAL = int(os.environ.get("YOLO_RETRAIN_MIN_TOTAL", 50))  # mínimo total
YOLO_DATA_DIR = Path(os.environ.get("YOLO_DATA_DIR", "/app/yolo_dataset"))
YOLO_MODELS_DIR = Path(os.environ.get("YOLO_MODELS_DIR", "/app/yolo_models"))

# DPO
DPO_SNAPSHOT_INTERVAL = int(os.environ.get("DPO_SNAPSHOT_INTERVAL", 24 * 3600))  # 24h
DPO_SNAPSHOT_THRESHOLD = int(os.environ.get("DPO_SNAPSHOT_THRESHOLD", 20))  # mínimo pares nuevos

# Vision dataset
VISION_STATS_INTERVAL = int(os.environ.get("VISION_STATS_INTERVAL", 24 * 3600))  # 24h
VISION_DATASET_DIR = Path(os.environ.get("VISION_DATASET_DIR", "/app/vision_dataset"))

# Data dir (logs, DPO, snapshots)
DATA_DIR = Path("/app/data") if Path("/app/data").exists() else Path("data")

# Marker files para tracking de estado
_MARKERS_DIR = DATA_DIR / "auto_learn"
_MARKERS_DIR.mkdir(parents=True, exist_ok=True)


# ── Utilidades ──────────────────────────────────────


def _read_marker(name: str) -> dict:
    """Lee un marker JSON. Devuelve {} si no existe."""
    path = _MARKERS_DIR / f"{name}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _write_marker(name: str, data: dict):
    """Escribe un marker JSON."""
    path = _MARKERS_DIR / f"{name}.json"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _count_lines(path: Path) -> int:
    """Cuenta líneas de un archivo (rápido, sin cargar en memoria)."""
    if not path.exists():
        return 0
    count = 0
    with open(path, "rb") as f:
        for _ in f:
            count += 1
    return count


def _count_images(base_dir: Path) -> int:
    """Cuenta imágenes .jpg en subdirectorios."""
    if not base_dir.exists():
        return 0
    return sum(1 for _ in base_dir.rglob("*.jpg"))


# ═══════════════════════════════════════════════════════
# 1. YOLO Breed Auto-Retrain
# ═══════════════════════════════════════════════════════


def _sync_train_model(epochs: int = 50, batch: int = 8, imgsz: int = 640) -> dict:
    """Wrapper síncrono para train_model (se ejecuta en thread executor).

    train_model() es async def pero no tiene awaits internos (ultralytics es sync),
    así que usamos un nuevo event loop temporal para ejecutarlo.
    """
    import asyncio as _asyncio
    from services.yolo_trainer import train_model
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            train_model(epochs=epochs, batch=batch, imgsz=imgsz)
        )
    finally:
        loop.close()


async def _yolo_retrain_loop():
    """Loop de reentrenamiento automático de YOLO breed model."""
    # Esperar 10 min tras arranque (dejar que otros servicios se estabilicen)
    await asyncio.sleep(600)
    logger.info(
        f"[AutoLearn/YOLO] Loop iniciado — "
        f"intervalo={YOLO_RETRAIN_INTERVAL}s, threshold={YOLO_RETRAIN_THRESHOLD} frames"
    )

    while True:
        try:
            await _yolo_retrain_check()
        except Exception as e:
            logger.error(f"[AutoLearn/YOLO] Error en check: {e}", exc_info=True)

        await asyncio.sleep(YOLO_RETRAIN_INTERVAL)


async def _yolo_retrain_check():
    """Comprueba si hay suficientes frames nuevos y lanza retraining."""
    from services.yolo_trainer import get_dataset_summary

    summary = get_dataset_summary()
    total_images = summary["train_images"] + summary["val_images"]

    marker = _read_marker("yolo_last_train")
    last_count = marker.get("total_images", 0)
    new_images = total_images - last_count

    logger.info(
        f"[AutoLearn/YOLO] Dataset: {total_images} total, "
        f"{new_images} nuevas desde último entrenamiento"
    )

    # No suficientes datos
    if total_images < YOLO_RETRAIN_MIN_TOTAL:
        logger.info(
            f"[AutoLearn/YOLO] Insuficiente: {total_images} < {YOLO_RETRAIN_MIN_TOTAL} mínimo"
        )
        return

    # No suficientes nuevas
    if new_images < YOLO_RETRAIN_THRESHOLD:
        logger.info(
            f"[AutoLearn/YOLO] Sin cambios significativos: {new_images} < {YOLO_RETRAIN_THRESHOLD}"
        )
        return

    # Lanzar entrenamiento en executor (es CPU/GPU-bound, bloqueante)
    logger.info(
        f"[AutoLearn/YOLO] Lanzando reentrenamiento "
        f"({new_images} frames nuevos, {total_images} total)..."
    )

    # Ejecutar en thread executor para no bloquear el event loop de FastAPI
    import functools
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        functools.partial(
            _sync_train_model,
            epochs=50,
            batch=8,
            imgsz=640,
        ),
    )

    if result["status"] == "completed":
        logger.info(
            f"[AutoLearn/YOLO] Entrenamiento completado: {result.get('best_model', 'N/A')}"
        )

        # Hot-reload del modelo breed en el detector
        try:
            from services.yolo_detector import reload_breed_model
            reload_breed_model()
            logger.info("[AutoLearn/YOLO] Modelo breed recargado en detector (hot-reload)")
        except Exception as e:
            logger.warning(f"[AutoLearn/YOLO] Hot-reload falló: {e}")

        # Guardar marker
        _write_marker("yolo_last_train", {
            "total_images": total_images,
            "new_images_trained": new_images,
            "result": result,
            "class_distribution": summary.get("class_distribution", {}),
        })
    else:
        logger.warning(f"[AutoLearn/YOLO] Entrenamiento falló: {result.get('message', '?')}")
        _write_marker("yolo_last_train_error", {
            "total_images": total_images,
            "error": result.get("message", "unknown"),
        })


# ═══════════════════════════════════════════════════════
# 2. DPO Dataset Snapshot
# ═══════════════════════════════════════════════════════


async def _dpo_snapshot_loop():
    """Loop de snapshot periódico de pares DPO."""
    # Esperar 15 min tras arranque
    await asyncio.sleep(900)
    logger.info(f"[AutoLearn/DPO] Loop iniciado — intervalo={DPO_SNAPSHOT_INTERVAL}s")

    while True:
        try:
            await _dpo_snapshot_check()
        except Exception as e:
            logger.error(f"[AutoLearn/DPO] Error en check: {e}", exc_info=True)

        await asyncio.sleep(DPO_SNAPSHOT_INTERVAL)


async def _dpo_snapshot_check():
    """Comprueba pares DPO nuevos y crea snapshot si necesario."""
    dpo_file = DATA_DIR / "dpo_pairs.jsonl"
    total_pairs = _count_lines(dpo_file)

    marker = _read_marker("dpo_last_snapshot")
    last_count = marker.get("total_pairs", 0)
    new_pairs = total_pairs - last_count

    logger.info(
        f"[AutoLearn/DPO] Pares: {total_pairs} total, "
        f"{new_pairs} nuevos desde último snapshot"
    )

    if new_pairs < DPO_SNAPSHOT_THRESHOLD:
        return

    # Crear directorio de snapshots
    snap_dir = DATA_DIR / "dpo_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Copiar archivo completo como snapshot fechado
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_path = snap_dir / f"dpo_pairs_{ts}.jsonl"
    shutil.copy2(dpo_file, snap_path)

    # Analizar distribución de bloqueos
    stats = {"total": 0, "block_sources": {}, "categories": {}}
    with open(dpo_file, encoding="utf-8") as f:
        for line in f:
            try:
                pair = json.loads(line)
                stats["total"] += 1
                meta = pair.get("metadata", {})
                src = meta.get("block_source", "unknown")
                cat = meta.get("category", "unknown")
                stats["block_sources"][src] = stats["block_sources"].get(src, 0) + 1
                stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
            except json.JSONDecodeError:
                continue

    # Generar config para TRL DPOTrainer
    training_config = {
        "_comment": "Config generado automáticamente por auto_learn.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(snap_path),
        "total_pairs": stats["total"],
        "block_distribution": stats["block_sources"],
        "category_distribution": stats["categories"],
        "trl_config": {
            "model_name_or_path": "Qwen/Qwen2.5-14B",
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "learning_rate": 5e-6,
            "num_train_epochs": 2,
            "beta": 0.1,
            "max_length": 2048,
            "max_prompt_length": 1024,
            "bf16": True,
        },
    }

    config_path = snap_dir / f"training_config_{ts}.json"
    config_path.write_text(json.dumps(training_config, ensure_ascii=False, indent=2))

    logger.info(
        f"[AutoLearn/DPO] Snapshot creado: {snap_path.name} "
        f"({stats['total']} pares, bloques: {stats['block_sources']})"
    )
    logger.info(f"[AutoLearn/DPO] Training config: {config_path.name}")

    # Guardar marker
    _write_marker("dpo_last_snapshot", {
        "total_pairs": total_pairs,
        "snapshot_path": str(snap_path),
        "config_path": str(config_path),
        "stats": stats,
    })


# ═══════════════════════════════════════════════════════
# 3. Vision Dataset Stats & Snapshot
# ═══════════════════════════════════════════════════════


async def _vision_stats_loop():
    """Loop de estadísticas y snapshot del dataset de visión."""
    # Esperar 20 min tras arranque
    await asyncio.sleep(1200)
    logger.info(f"[AutoLearn/Vision] Loop iniciado — intervalo={VISION_STATS_INTERVAL}s")

    while True:
        try:
            await _vision_stats_check()
        except Exception as e:
            logger.error(f"[AutoLearn/Vision] Error en check: {e}", exc_info=True)

        await asyncio.sleep(VISION_STATS_INTERVAL)


async def _vision_stats_check():
    """Comprueba estado del dataset de imágenes para VL fine-tune."""
    jsonl_path = VISION_DATASET_DIR / "dataset.jsonl"
    total_pairs = _count_lines(jsonl_path)
    total_images = _count_images(VISION_DATASET_DIR / "images")

    # Calcular tamaño en disco
    disk_mb = 0.0
    if VISION_DATASET_DIR.exists():
        disk_mb = sum(
            f.stat().st_size for f in VISION_DATASET_DIR.rglob("*") if f.is_file()
        ) / (1024 * 1024)

    marker = _read_marker("vision_last_check")
    last_count = marker.get("total_pairs", 0)
    new_pairs = total_pairs - last_count

    logger.info(
        f"[AutoLearn/Vision] Dataset: {total_pairs} pares, "
        f"{total_images} imágenes, {disk_mb:.1f} MB, "
        f"{new_pairs} nuevos desde último check"
    )

    # Si hay suficientes imágenes nuevas, crear snapshot de metadata
    if new_pairs >= 50:
        snap_dir = DATA_DIR / "vision_snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Generar config para LLaMA-Factory
        llama_factory_config = {
            "_comment": "Config generado automáticamente por auto_learn.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_dir": str(VISION_DATASET_DIR),
            "dataset_jsonl": str(jsonl_path),
            "total_pairs": total_pairs,
            "total_images": total_images,
            "disk_mb": round(disk_mb, 1),
            "llama_factory_config": {
                "stage": "sft",
                "model_name_or_path": "Qwen/Qwen2.5-VL-7B-Instruct",
                "dataset": "seedy_vision",
                "template": "qwen2_vl",
                "finetuning_type": "lora",
                "lora_rank": 16,
                "lora_alpha": 32,
                "lora_target": "all",
                "per_device_train_batch_size": 1,
                "gradient_accumulation_steps": 8,
                "learning_rate": 1e-5,
                "num_train_epochs": 3,
                "bf16": True,
                "max_samples": 5000,
            },
        }

        config_path = snap_dir / f"vision_config_{ts}.json"
        config_path.write_text(json.dumps(llama_factory_config, ensure_ascii=False, indent=2))

        logger.info(f"[AutoLearn/Vision] Training config: {config_path.name}")

    # Guardar marker
    _write_marker("vision_last_check", {
        "total_pairs": total_pairs,
        "total_images": total_images,
        "disk_mb": round(disk_mb, 1),
    })


# ═══════════════════════════════════════════════════════
# API: Estado global del auto-learning
# ═══════════════════════════════════════════════════════


def get_auto_learn_status() -> dict:
    """Devuelve estado completo de los tres ciclos de aprendizaje."""
    from services.yolo_trainer import get_dataset_summary

    yolo_summary = {}
    try:
        yolo_summary = get_dataset_summary()
    except Exception:
        pass

    yolo_marker = _read_marker("yolo_last_train")
    dpo_marker = _read_marker("dpo_last_snapshot")
    vision_marker = _read_marker("vision_last_check")

    # DPO actual
    dpo_file = DATA_DIR / "dpo_pairs.jsonl"
    dpo_total = _count_lines(dpo_file)

    # Vision actual
    jsonl_path = VISION_DATASET_DIR / "dataset.jsonl"
    vision_total = _count_lines(jsonl_path)

    return {
        "yolo": {
            "dataset": yolo_summary,
            "last_train": yolo_marker,
            "config": {
                "retrain_interval_h": YOLO_RETRAIN_INTERVAL / 3600,
                "retrain_threshold": YOLO_RETRAIN_THRESHOLD,
                "min_total": YOLO_RETRAIN_MIN_TOTAL,
            },
        },
        "dpo": {
            "total_pairs": dpo_total,
            "last_snapshot": dpo_marker,
            "config": {
                "snapshot_interval_h": DPO_SNAPSHOT_INTERVAL / 3600,
                "snapshot_threshold": DPO_SNAPSHOT_THRESHOLD,
            },
        },
        "vision": {
            "total_pairs": vision_total,
            "last_check": vision_marker,
            "config": {
                "stats_interval_h": VISION_STATS_INTERVAL / 3600,
            },
        },
    }


# ═══════════════════════════════════════════════════════
# Behavior maintenance loop
# ═══════════════════════════════════════════════════════

BEHAVIOR_MAINTENANCE_INTERVAL = int(os.environ.get("BEHAVIOR_MAINTENANCE_INTERVAL", 24 * 3600))  # 24h


async def _behavior_maintenance_loop():
    """Loop de mantenimiento del sistema conductual (cada 24h):
    - Cleanup de JSONL del event store (retención 7 días)
    - Health check: verifica que llegan snapshots frescos
    - Prune de baselines de aves inactivas (>30 días sin datos)
    """
    await asyncio.sleep(600)  # esperar 10 min tras arranque
    while True:
        try:
            from services.behavior_event_store import get_event_store
            store = get_event_store()

            # 1. Cleanup ficheros antiguos
            deleted = store.cleanup()
            if deleted:
                logger.info(f"[AutoLearn:Behavior] Cleanup: {deleted} ficheros JSONL eliminados")

            # 2. Health check: verificar frescura de snapshots
            stats = store.get_stats()
            for gall_id, gall_stats in stats.get("gallineros", {}).items():
                newest = gall_stats.get("newest", "")
                if newest:
                    from datetime import datetime as dt
                    try:
                        newest_date = dt.strptime(newest, "%Y-%m-%d").date()
                        days_stale = (dt.now().date() - newest_date).days
                        if days_stale > 1:
                            logger.warning(
                                f"[AutoLearn:Behavior] {gall_id}: último snapshot hace {days_stale} días — "
                                "¿tracker activo?"
                            )
                    except ValueError:
                        pass

            # 3. Prune baselines de aves inactivas (>30 días sin update)
            try:
                from services.behavior_baseline import get_baseline
                baseline = get_baseline()
                pruned = baseline.prune_stale(max_age_days=30)
                if pruned:
                    logger.info(f"[AutoLearn:Behavior] Pruned {pruned} baselines inactivas")
            except Exception as e:
                logger.debug(f"[AutoLearn:Behavior] Baseline prune skip: {e}")

            logger.info(
                f"[AutoLearn:Behavior] Mantenimiento completado — "
                f"store: {stats.get('total_files', 0)} ficheros, "
                f"{stats.get('total_bytes', 0) / 1024:.0f} KB"
            )
        except Exception as e:
            logger.error(f"[AutoLearn:Behavior] Error en mantenimiento: {e}")

        await asyncio.sleep(BEHAVIOR_MAINTENANCE_INTERVAL)


# ═══════════════════════════════════════════════════════
# Entry: lanza los loops
# ═══════════════════════════════════════════════════════


def start_all_loops() -> list[asyncio.Task]:
    """Lanza los loops de auto-learning como asyncio tasks."""
    from services.knowledge_agent import knowledge_agent_loop
    from services.reporting_agent import reporting_agent_loop

    ka_interval = int(os.environ.get("KNOWLEDGE_AGENT_INTERVAL", 12 * 3600))
    report_interval = int(os.environ.get("REPORT_INTERVAL", 24 * 3600))

    tasks = [
        asyncio.create_task(_yolo_retrain_loop(), name="auto_learn_yolo"),
        asyncio.create_task(_dpo_snapshot_loop(), name="auto_learn_dpo"),
        asyncio.create_task(_vision_stats_loop(), name="auto_learn_vision"),
        asyncio.create_task(knowledge_agent_loop(), name="auto_learn_knowledge"),
        asyncio.create_task(reporting_agent_loop(), name="auto_learn_reporting"),
        asyncio.create_task(_behavior_maintenance_loop(), name="auto_learn_behavior"),
    ]
    logger.info(
        "[AutoLearn] 6 loops lanzados: "
        f"YOLO (cada {YOLO_RETRAIN_INTERVAL // 3600}h), "
        f"DPO (cada {DPO_SNAPSHOT_INTERVAL // 3600}h), "
        f"Vision (cada {VISION_STATS_INTERVAL // 3600}h), "
        f"Knowledge (cada {ka_interval // 3600}h), "
        f"Reporting (cada {report_interval // 3600}h), "
        f"Behavior (cada {BEHAVIOR_MAINTENANCE_INTERVAL // 3600}h)"
    )
    return tasks
