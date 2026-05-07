#!/usr/bin/env python3
"""
Launcher para el sistema edge Jetson — Procesa las 3 cámaras del gallinero_palacio
"""
import asyncio
import logging
from jetson_edge_camera_supervisor import CameraSupervisor
from jetson_edge_yolo_engine import YOLOEngine
from jetson_edge_dgx_relay import DGXRelay
from jetson_edge_config import load_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def main():
    """Iniciar supervisores para las 3 cámaras"""
    logger.info("=" * 60)
    logger.info("JETSON EDGE v4.5 — gallinero_palacio (3 cámaras)")
    logger.info("=" * 60)
    
    # Cargar config
    config = load_config("jetson_edge_config.yaml")
    logger.info(f"Config cargada: {len(config['cameras'])} cámaras")
    
    # Crear YOLOEngine compartido (1 instancia para las 3 cámaras)
    logger.info("Inicializando YOLO Engine...")
    yolo_engine = YOLOEngine(
        model_path=config["yolo"]["model_path"],
        device=config["yolo"]["device"],
        conf_threshold=config["yolo"]["conf_threshold"],
        iou_threshold=config["yolo"]["iou_threshold"],
        classes=config["yolo"]["classes"],
        max_det=config["yolo"].get("max_det", 50),
        imgsz=config["yolo"]["imgsz"]
    )
    
    # CARGAR MODELO (crítico - __init__ no lo hace)
    if not yolo_engine.load_model():
        logger.error("❌ Fallo al cargar modelo YOLO")
        return
    
    logger.info("✅ YOLO Engine listo")
    
    # Crear DGXRelay compartido
    logger.info("Inicializando DGX Relay...")
    dgx_relay = DGXRelay(
        dgx_url=config["dgx"]["url"],
        endpoint=config["dgx"]["endpoint"],
        timeout=config["dgx"]["timeout"],
        retry_attempts=config["dgx"]["retry_attempts"],
        retry_delay=config["dgx"]["retry_delay"]
    )
    logger.info("✅ DGX Relay listo")
    
    # Crear supervisores
    supervisors = []
    for camera_id, camera_cfg in config["cameras"].items():
        logger.info(f"  + {camera_id}: {camera_cfg['name']}")
        supervisor = CameraSupervisor(
            camera_id=camera_id,
            camera_config=camera_cfg,
            yolo_engine=yolo_engine,
            dgx_relay=dgx_relay,
            gallinero_id=config["gallinero_id"],
            edge_node_id=config["edge_node_id"],
            tracking_config=config["tracking"]
        )
        supervisors.append(supervisor)
    
    logger.info("")
    logger.info("🚀 Iniciando procesamiento (Ctrl+C para detener)...")
    
    # Ejecutar todos en paralelo
    tasks = [supervisor.start() for supervisor in supervisors]
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("\n⏹️  Deteniendo gracefully...")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
    finally:
        logger.info("✅ Supervisores detenidos")

if __name__ == "__main__":
    asyncio.run(main())
