"""
Seedy Vision — Estimación de Peso por Visión
Modelo de regresión: imagen dorsal/lateral → peso estimado (kg).

Arquitectura:
  1. YOLO detecta el animal y recorta el ROI
  2. Backbone (EfficientNet/ConvNeXt) extrae features
  3. Head de regresión predice peso en kg
  4. Opcional: medir área de píxeles (segmentación) como feature extra

Combinar con báscula walk-over para calibración automática.
"""
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import torch
import torch.nn as nn
import torchvision.transforms as T
from torch.utils.data import Dataset, DataLoader
from PIL import Image
import numpy as np
import cv2
from rich.console import Console

console = Console()


# ─────────────────────────────────────────────────────
# Dataset para regresión de peso
# ─────────────────────────────────────────────────────

class WeightDataset(Dataset):
    """
    Dataset para estimación de peso.
    
    Estructura esperada:
        images/
            img001.jpg
            img002.jpg
        labels/
            img001.json   ← {"weight_kg": 95.3, "species": "pig", "view": "dorsal"}
            img002.json
    """
    
    def __init__(self, images_dir: str, labels_dir: str,
                 transform=None, species: Optional[str] = None):
        self.images_dir = Path(images_dir)
        self.labels_dir = Path(labels_dir)
        self.transform = transform or self._default_transform()
        
        # Cargar pares imagen-peso
        self.samples = []
        for label_file in sorted(self.labels_dir.glob("*.json")):
            meta = json.loads(label_file.read_text())
            
            if species and meta.get("species") != species:
                continue
            
            img_name = label_file.stem
            for ext in [".jpg", ".jpeg", ".png"]:
                img_path = self.images_dir / f"{img_name}{ext}"
                if img_path.exists():
                    self.samples.append({
                        "image": img_path,
                        "weight": meta["weight_kg"],
                        "species": meta.get("species", "unknown"),
                        "view": meta.get("view", "unknown"),
                    })
                    break
        
        console.print(f"[cyan]WeightDataset: {len(self.samples)} muestras[/]")
    
    @staticmethod
    def _default_transform():
        return T.Compose([
            T.Resize((224, 224)),
            T.RandomHorizontalFlip(p=0.5),
            T.ColorJitter(brightness=0.2, contrast=0.2),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406],
                       std=[0.229, 0.224, 0.225]),
        ])
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        img = Image.open(sample["image"]).convert("RGB")
        
        if self.transform:
            img = self.transform(img)
        
        weight = torch.tensor(sample["weight"], dtype=torch.float32)
        return img, weight


# ─────────────────────────────────────────────────────
# Modelo de regresión de peso
# ─────────────────────────────────────────────────────

class WeightEstimator(nn.Module):
    """
    Modelo de regresión para estimar peso animal.
    
    Backbone: EfficientNet-B0 (pre-trained ImageNet)
    Head: MLP con 2 capas → 1 output (peso en kg)
    
    Input adicional opcional: área en píxeles del animal (de segmentación).
    """
    
    def __init__(self, backbone: str = "efficientnet_b0",
                 use_area_feature: bool = True,
                 pretrained: bool = True):
        super().__init__()
        
        self.use_area_feature = use_area_feature
        
        # Backbone
        if backbone == "efficientnet_b0":
            import torchvision.models as models
            self.backbone = models.efficientnet_b0(
                weights="IMAGENET1K_V1" if pretrained else None
            )
            feature_dim = self.backbone.classifier[1].in_features
            self.backbone.classifier = nn.Identity()
        
        elif backbone == "convnext_tiny":
            import torchvision.models as models
            self.backbone = models.convnext_tiny(
                weights="IMAGENET1K_V1" if pretrained else None
            )
            feature_dim = self.backbone.classifier[2].in_features
            self.backbone.classifier = nn.Identity()
        
        else:
            raise ValueError(f"Backbone no soportado: {backbone}")
        
        # Head de regresión
        extra_features = 1 if use_area_feature else 0
        self.head = nn.Sequential(
            nn.Linear(feature_dim + extra_features, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1),  # Output: peso en kg
        )
    
    def forward(self, x: torch.Tensor,
                area: Optional[torch.Tensor] = None) -> torch.Tensor:
        features = self.backbone(x)
        
        if self.use_area_feature and area is not None:
            area = area.unsqueeze(1) if area.dim() == 1 else area
            features = torch.cat([features, area], dim=1)
        
        return self.head(features).squeeze(1)


# ─────────────────────────────────────────────────────
# Training loop
# ─────────────────────────────────────────────────────

def train_weight_model(
    train_images: str,
    train_labels: str,
    val_images: str,
    val_labels: str,
    species: str = "pig",
    backbone: str = "efficientnet_b0",
    epochs: int = 50,
    batch_size: int = 32,
    lr: float = 1e-4,
    device: str = "cuda:0",
    output_dir: str = "models/weight_estimation",
):
    """Entrena el modelo de estimación de peso"""
    
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    # Datasets
    train_ds = WeightDataset(train_images, train_labels, species=species)
    val_ds = WeightDataset(val_images, val_labels, species=species,
                           transform=T.Compose([
                               T.Resize((224, 224)),
                               T.ToTensor(),
                               T.Normalize([0.485, 0.456, 0.406],
                                          [0.229, 0.224, 0.225]),
                           ]))
    
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                            num_workers=4, pin_memory=True)
    
    # Modelo
    model = WeightEstimator(backbone=backbone, use_area_feature=False)
    model = model.to(device)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.HuberLoss(delta=5.0)  # Huber: robusto a outliers de peso
    
    best_val_mae = float("inf")
    
    console.print(f"\n[bold cyan]🏋️ Training Weight Estimator ({species})[/]")
    console.print(f"  Backbone: {backbone}, Epochs: {epochs}, LR: {lr}")
    console.print(f"  Train: {len(train_ds)}, Val: {len(val_ds)}")
    
    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0.0
        for imgs, weights in train_loader:
            imgs = imgs.to(device)
            weights = weights.to(device)
            
            preds = model(imgs)
            loss = criterion(preds, weights)
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        # Validation
        model.eval()
        val_mae = 0.0
        val_mape = 0.0
        n_val = 0
        
        with torch.no_grad():
            for imgs, weights in val_loader:
                imgs = imgs.to(device)
                weights = weights.to(device)
                
                preds = model(imgs)
                mae = torch.abs(preds - weights).sum().item()
                mape = (torch.abs(preds - weights) / weights.clamp(min=1)).sum().item()
                
                val_mae += mae
                val_mape += mape
                n_val += weights.size(0)
        
        val_mae /= n_val
        val_mape = (val_mape / n_val) * 100
        
        scheduler.step()
        
        if (epoch + 1) % 5 == 0 or epoch == 0:
            console.print(
                f"  Epoch {epoch+1:3d}/{epochs} | "
                f"Loss: {train_loss:.4f} | "
                f"Val MAE: {val_mae:.2f} kg | "
                f"Val MAPE: {val_mape:.1f}%"
            )
        
        # Save best
        if val_mae < best_val_mae:
            best_val_mae = val_mae
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_mae": val_mae,
                "val_mape": val_mape,
                "species": species,
                "backbone": backbone,
            }, out / "best.pt")
    
    console.print(f"\n[green]✅ Best MAE: {best_val_mae:.2f} kg → {out / 'best.pt'}[/]")
    
    # Export ONNX
    model.eval()
    dummy = torch.randn(1, 3, 224, 224).to(device)
    torch.onnx.export(model, dummy, str(out / "weight_estimator.onnx"),
                      input_names=["image"], output_names=["weight_kg"],
                      dynamic_axes={"image": {0: "batch"}})
    console.print(f"[green]✅ ONNX exported → {out / 'weight_estimator.onnx'}[/]")
    
    return model


# ─────────────────────────────────────────────────────
# Inferencia combinada: YOLO detect + weight estimate
# ─────────────────────────────────────────────────────

class WeightInferencePipeline:
    """
    Pipeline combinado:
    1. YOLO detecta el animal
    2. Recorta ROI
    3. WeightEstimator predice peso
    
    Para Jetson: usar ONNX/TensorRT del weight estimator.
    """
    
    def __init__(self, weight_model_path: str,
                 device: str = "cuda:0"):
        self.device = device
        
        # Cargar modelo de peso
        checkpoint = torch.load(weight_model_path, map_location=device,
                                weights_only=False)
        backbone = checkpoint.get("backbone", "efficientnet_b0")
        
        self.model = WeightEstimator(backbone=backbone, use_area_feature=False)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model = self.model.to(device).eval()
        
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        
        self.species = checkpoint.get("species", "unknown")
        console.print(
            f"[green]✅ WeightEstimator cargado ({self.species}, "
            f"MAE={checkpoint.get('val_mae', '?'):.2f} kg)[/]"
        )
    
    def estimate_weight(self, frame: np.ndarray,
                         bbox: list[float]) -> float:
        """
        Estima peso de un animal recortado del frame.
        
        Args:
            frame: Imagen BGR completa
            bbox: [x1, y1, x2, y2] en píxeles
        
        Returns: Peso estimado en kg
        """
        x1, y1, x2, y2 = [int(v) for v in bbox]
        
        # Recortar ROI con margen
        h, w = frame.shape[:2]
        margin = 0.1
        mw = int((x2 - x1) * margin)
        mh = int((y2 - y1) * margin)
        x1 = max(0, x1 - mw)
        y1 = max(0, y1 - mh)
        x2 = min(w, x2 + mw)
        y2 = min(h, y2 + mh)
        
        roi = frame[y1:y2, x1:x2]
        roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(roi_rgb)
        
        tensor = self.transform(pil_img).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            weight = self.model(tensor).item()
        
        return max(0, weight)  # No puede ser negativo


# ─────────────────────────────────────────────────────
# Calibración con báscula walk-over
# ─────────────────────────────────────────────────────

@dataclass
class CalibrationPoint:
    """Un punto de calibración: peso real vs estimado"""
    timestamp: str
    animal_id: str
    weight_real_kg: float
    weight_estimated_kg: float
    error_kg: float
    error_pct: float


class WalkoverCalibrator:
    """
    Calibra el modelo de peso usando datos de la báscula walk-over.
    
    Cuando un animal pasa por la báscula:
    1. Se registra peso real (báscula)
    2. Se registra peso estimado (visión)
    3. Se calcula un factor de corrección lineal
    
    El factor se envía al modelo para ajustar predicciones sin reentrenar.
    """
    
    def __init__(self, calibration_file: str = "calibration.json"):
        self.calibration_file = Path(calibration_file)
        self.points: list[CalibrationPoint] = []
        self.correction_factor = 1.0
        self.correction_bias = 0.0
        
        self._load()
    
    def _load(self):
        if self.calibration_file.exists():
            data = json.loads(self.calibration_file.read_text())
            self.correction_factor = data.get("correction_factor", 1.0)
            self.correction_bias = data.get("correction_bias", 0.0)
            self.points = [CalibrationPoint(**p) for p in data.get("points", [])]
    
    def _save(self):
        data = {
            "correction_factor": self.correction_factor,
            "correction_bias": self.correction_bias,
            "n_points": len(self.points),
            "points": [
                {
                    "timestamp": p.timestamp,
                    "animal_id": p.animal_id,
                    "weight_real_kg": p.weight_real_kg,
                    "weight_estimated_kg": p.weight_estimated_kg,
                    "error_kg": p.error_kg,
                    "error_pct": p.error_pct,
                }
                for p in self.points[-100:]  # Últimos 100 puntos
            ],
        }
        self.calibration_file.write_text(json.dumps(data, indent=2))
    
    def add_point(self, animal_id: str,
                   weight_real: float, weight_estimated: float):
        """Añade un punto de calibración"""
        error = weight_estimated - weight_real
        error_pct = abs(error) / max(weight_real, 0.1) * 100
        
        from datetime import datetime
        point = CalibrationPoint(
            timestamp=datetime.now().isoformat(),
            animal_id=animal_id,
            weight_real_kg=weight_real,
            weight_estimated_kg=weight_estimated,
            error_kg=error,
            error_pct=error_pct,
        )
        self.points.append(point)
        
        # Recalcular corrección con regresión lineal simple
        if len(self.points) >= 5:
            self._update_correction()
        
        self._save()
    
    def _update_correction(self):
        """Regresión lineal simple: real = factor * estimated + bias"""
        n = len(self.points)
        x = [p.weight_estimated_kg for p in self.points]
        y = [p.weight_real_kg for p in self.points]
        
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        den = sum((xi - x_mean) ** 2 for xi in x)
        
        if den > 0:
            self.correction_factor = num / den
            self.correction_bias = y_mean - self.correction_factor * x_mean
    
    def correct(self, estimated_weight: float) -> float:
        """Aplica factor de corrección al peso estimado"""
        return self.correction_factor * estimated_weight + self.correction_bias
    
    def stats(self) -> dict:
        """Estadísticas de calibración"""
        if not self.points:
            return {"n_points": 0}
        
        errors = [abs(p.error_kg) for p in self.points]
        return {
            "n_points": len(self.points),
            "mae_kg": sum(errors) / len(errors),
            "max_error_kg": max(errors),
            "correction_factor": self.correction_factor,
            "correction_bias": self.correction_bias,
        }
