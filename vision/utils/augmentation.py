"""
Seedy Vision — Data Augmentation Pipeline
Augmentaciones específicas para cada especie/escenario de granja
"""
from pathlib import Path
from typing import Optional

import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2


def get_detection_augmentation(species: str = "pig",
                                 target_size: int = 640) -> A.Compose:
    """
    Pipeline de augmentation para detección YOLO.
    Adapta las transformaciones al tipo de animal y entorno.
    """
    # Base transforms para todas las especies
    base = [
        A.LongestMaxSize(max_size=target_size),
        A.PadIfNeeded(
            min_height=target_size, min_width=target_size,
            border_mode=cv2.BORDER_CONSTANT, value=(114, 114, 114)
        ),
    ]
    
    # Augmentaciones comunes
    common = [
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(
            brightness_limit=0.2, contrast_limit=0.2, p=0.5
        ),
        A.GaussNoise(var_limit=(10, 50), p=0.3),
        A.MotionBlur(blur_limit=5, p=0.2),
    ]
    
    # Augmentaciones específicas por especie
    species_augs = {
        "chicken": [
            # Gallinas: picoteo rápido, mucho movimiento, exterior
            A.RandomSunFlare(
                src_radius=100, num_flare_circles_lower=1,
                num_flare_circles_upper=3, p=0.15
            ),
            A.RandomShadow(p=0.3),  # sombras en exterior
            A.RandomRain(rain_type="drizzle", p=0.1),  # lluvia ligera
            A.ColorJitter(
                brightness=0.3, contrast=0.3,
                saturation=0.4, hue=0.1, p=0.4
            ),
            A.Rotate(limit=15, p=0.3),
        ],
        "pig": [
            # Cerdos: interior, iluminación artificial, barro/suciedad
            A.RandomBrightnessContrast(
                brightness_limit=0.3, contrast_limit=0.3, p=0.5
            ),
            A.CLAHE(clip_limit=4.0, p=0.3),  # mejorar contraste en naves
            A.GaussianBlur(blur_limit=7, p=0.2),
            A.ISONoise(p=0.2),  # ruido de cámaras baratas
            A.Rotate(limit=10, p=0.2),
        ],
        "cattle": [
            # Vacuno: exterior extensivo, drones, distancias variables
            A.RandomSunFlare(p=0.2),
            A.RandomShadow(p=0.3),
            A.RandomFog(fog_coef_lower=0.1, fog_coef_upper=0.3, p=0.1),
            A.RandomScale(scale_limit=0.3, p=0.3),  # diferentes distancias
            A.Rotate(limit=20, p=0.3),  # ángulos de drone
            A.Perspective(scale=(0.02, 0.08), p=0.2),
        ],
    }
    
    augs = species_augs.get(species, [])
    
    return A.Compose(
        base + common + augs,
        bbox_params=A.BboxParams(
            format="yolo",
            min_visibility=0.3,
            label_fields=["class_labels"],
        ),
    )


def get_classification_augmentation(species: str = "pig",
                                      target_size: int = 224) -> A.Compose:
    """Pipeline de augmentation para clasificación (raza, BCS, etc.)"""
    return A.Compose([
        A.Resize(target_size, target_size),
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.5),
        A.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.3, hue=0.05, p=0.4),
        A.GaussNoise(var_limit=(10, 40), p=0.3),
        A.GaussianBlur(blur_limit=5, p=0.2),
        A.ShiftScaleRotate(
            shift_limit=0.1, scale_limit=0.15, rotate_limit=15, p=0.4
        ),
        A.CoarseDropout(
            max_holes=4, max_height=32, max_width=32,
            min_holes=1, fill_value=0, p=0.2
        ),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
    ])


def get_thermal_augmentation(target_size: int = 640) -> A.Compose:
    """Pipeline de augmentation para imágenes térmicas"""
    return A.Compose([
        A.LongestMaxSize(max_size=target_size),
        A.PadIfNeeded(
            min_height=target_size, min_width=target_size,
            border_mode=cv2.BORDER_CONSTANT, value=0
        ),
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.4),
        A.GaussNoise(var_limit=(5, 25), p=0.3),
        A.Rotate(limit=10, p=0.2),
        # En térmico no aplicamos saturación ni color
    ],
    bbox_params=A.BboxParams(
        format="yolo",
        min_visibility=0.3,
        label_fields=["class_labels"],
    ))


def augment_image_with_labels(image_path: Path, label_path: Path,
                                output_img_dir: Path, output_lbl_dir: Path,
                                transform: A.Compose,
                                num_augmented: int = 5):
    """
    Genera N versiones augmentadas de una imagen con sus labels YOLO.
    """
    output_img_dir.mkdir(parents=True, exist_ok=True)
    output_lbl_dir.mkdir(parents=True, exist_ok=True)
    
    img = cv2.imread(str(image_path))
    if img is None:
        return
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Leer labels YOLO
    bboxes = []
    class_labels = []
    if label_path.exists():
        for line in label_path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split()
            cls_id = int(parts[0])
            bbox = [float(x) for x in parts[1:5]]
            class_labels.append(cls_id)
            bboxes.append(bbox)
    
    stem = image_path.stem
    
    for i in range(num_augmented):
        try:
            result = transform(
                image=img,
                bboxes=bboxes,
                class_labels=class_labels,
            )
            
            aug_img = result["image"]
            aug_bboxes = result["bboxes"]
            aug_labels = result["class_labels"]
            
            # Guardar imagen
            out_img = output_img_dir / f"{stem}_aug{i:02d}{image_path.suffix}"
            aug_bgr = cv2.cvtColor(aug_img, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(out_img), aug_bgr)
            
            # Guardar labels
            out_lbl = output_lbl_dir / f"{stem}_aug{i:02d}.txt"
            lines = []
            for cls, bbox in zip(aug_labels, aug_bboxes):
                lines.append(f"{cls} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}")
            out_lbl.write_text("\n".join(lines) + "\n" if lines else "")
            
        except Exception:
            continue
