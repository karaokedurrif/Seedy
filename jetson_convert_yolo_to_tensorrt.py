#!/usr/bin/env python3
"""
Seedy Edge v4.5 — YOLOv8s → TensorRT Conversion Script
Jetson Orin Nano 8GB

DEBE EJECUTARSE EN EL JETSON (no en laptop/DGX).
Convierte yolov8s.pt → yolov8s.engine (FP16, optimizado para Orin).

Expected output:
- models/yolov8s.engine (~22 MB)
- Inference: ~15-20ms (50-70 FPS) en Jetson Orin Nano Super Mode
"""

import sys
import os
import time
import logging
from pathlib import Path

# Verificar que está en Jetson (opcional, comentar si molesta)
try:
    import jtop
    print("✅ jtop detectado — ejecutando en Jetson")
except ImportError:
    print("⚠️  Warning: jtop no detectado, ¿estás en el Jetson?")

from ultralytics import YOLO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def download_yolov8s(output_path: str) -> bool:
    """Descargar YOLOv8s.pt desde Ultralytics."""
    try:
        logger.info("📥 Descargando YOLOv8s.pt...")
        model = YOLO("yolov8s.pt")  # Auto-descarga si no existe
        
        # Mover a models/
        import shutil
        shutil.move("yolov8s.pt", output_path)
        
        logger.info(f"✅ Descargado: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error descargando modelo: {e}")
        return False


def convert_to_tensorrt(
    pt_path: str,
    output_dir: str,
    imgsz: int = 640,
    half: bool = True,
    workspace: int = 4,
    dynamic: bool = True
) -> bool:
    """
    Convertir .pt → .engine con TensorRT.
    
    Args:
        pt_path: Path al .pt
        output_dir: Directorio de salida
        imgsz: Tamaño de imagen (640)
        half: FP16 (True)
        workspace: GB de workspace TensorRT (4)
        dynamic: Dynamic shapes (True para multi-resolution)
    
    Returns:
        True si éxito
    """
    try:
        logger.info("🔧 Iniciando conversión TensorRT...")
        logger.info(f"  - Input: {pt_path}")
        logger.info(f"  - Output dir: {output_dir}")
        logger.info(f"  - Image size: {imgsz}")
        logger.info(f"  - FP16: {half}")
        logger.info(f"  - Workspace: {workspace} GB")
        logger.info(f"  - Dynamic: {dynamic}")
        
        # Cargar modelo PyTorch
        model = YOLO(pt_path)
        
        # Exportar a TensorRT
        # Esto puede tardar 5-10 minutos en Jetson
        logger.info("⏳ Exportando... (puede tardar 5-10 min)")
        start = time.time()
        
        model.export(
            format="engine",
            half=half,
            dynamic=dynamic,
            workspace=workspace,
            imgsz=imgsz,
            device=0  # GPU 0
        )
        
        elapsed = time.time() - start
        
        # El .engine se genera en el mismo dir que el .pt
        engine_path = pt_path.replace(".pt", ".engine")
        
        if not os.path.exists(engine_path):
            logger.error("❌ .engine no encontrado tras export")
            return False
        
        # Mover a output_dir si es diferente
        output_engine = os.path.join(output_dir, "yolov8s.engine")
        if engine_path != output_engine:
            import shutil
            shutil.move(engine_path, output_engine)
        
        # Stats
        size_mb = os.path.getsize(output_engine) / (1024 * 1024)
        
        logger.info("=" * 60)
        logger.info("✅ CONVERSIÓN COMPLETADA")
        logger.info(f"  - Output: {output_engine}")
        logger.info(f"  - Tamaño: {size_mb:.1f} MB")
        logger.info(f"  - Tiempo: {elapsed:.1f}s ({elapsed/60:.1f} min)")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en conversión: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_engine(engine_path: str) -> bool:
    """Verificar que el .engine funciona."""
    try:
        logger.info("🧪 Verificando .engine con inferencia de prueba...")
        
        model = YOLO(engine_path, task='detect')
        
        # Crear imagen de prueba
        import numpy as np
        test_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        
        # Warmup
        _ = model.predict(test_img, device=0, verbose=False)
        
        # 10 inferencias para medir FPS
        times = []
        for _ in range(10):
            start = time.time()
            _ = model.predict(test_img, device=0, verbose=False)
            times.append(time.time() - start)
        
        avg_time = sum(times) / len(times)
        fps = 1.0 / avg_time
        
        logger.info("=" * 60)
        logger.info("✅ VERIFICACIÓN EXITOSA")
        logger.info(f"  - Avg inference time: {avg_time*1000:.1f} ms")
        logger.info(f"  - FPS: {fps:.1f}")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error verificando engine: {e}")
        return False


def main():
    """Main entry point."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           Seedy Edge v4.5 — YOLOv8s TensorRT Converter      ║
║                   Jetson Orin Nano 8GB                       ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Paths
    workspace_dir = Path.home() / "seedy-edge"
    models_dir = workspace_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    
    pt_path = str(models_dir / "yolov8s.pt")
    engine_path = str(models_dir / "yolov8s.engine")
    
    # Step 1: Descargar .pt si no existe
    if not os.path.exists(pt_path):
        logger.info(f"📦 yolov8s.pt no encontrado, descargando...")
        if not download_yolov8s(pt_path):
            logger.error("❌ Fallo en descarga")
            sys.exit(1)
    else:
        logger.info(f"✅ yolov8s.pt ya existe: {pt_path}")
    
    # Step 2: Convertir a TensorRT
    if os.path.exists(engine_path):
        logger.warning(f"⚠️  {engine_path} ya existe")
        response = input("¿Reconvertir? (s/N): ")
        if response.lower() != 's':
            logger.info("❎ Conversión cancelada")
            sys.exit(0)
    
    if not convert_to_tensorrt(
        pt_path=pt_path,
        output_dir=str(models_dir),
        imgsz=640,
        half=True,
        workspace=4,
        dynamic=True
    ):
        logger.error("❌ Fallo en conversión")
        sys.exit(1)
    
    # Step 3: Verificar
    if not verify_engine(engine_path):
        logger.error("❌ Fallo en verificación")
        sys.exit(1)
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    ✅ PROCESO COMPLETADO                     ║
║                                                              ║
║  El modelo TensorRT está listo para producción.             ║
║  Archivo: ~/seedy-edge/models/yolov8s.engine                ║
║                                                              ║
║  Siguiente paso: ejecutar camera_supervisor.py              ║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
