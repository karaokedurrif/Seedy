"""
Seedy Vision — Computer Vision Pipeline para Agritech
Detección, clasificación, estimación y comportamiento de gallinas, cerdos y vacuno.

Módulos:
  - dataset_discovery: Descarga datasets públicos (Kaggle, Roboflow, Zenodo)
  - prepare_datasets: Pipeline completo descarga → limpieza → split → YOLO
  - train_yolo: Entrenamiento YOLO multi-tarea (detect, segment, classify)
  - jetson_inference: Inferencia edge en Jetson Orin Nano
  - dataset_factory: Auto-captura de frames para dataset propio
  
  utils/
    - convert_annotations: COCO/VOC/folder → YOLO
    - dataset_cleaning: Deduplicación, validación, balance
    - augmentation: Data augmentation por especie
"""

__version__ = "0.1.0"
