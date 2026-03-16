"""
Seedy Vision — Dataset Factory
Convierte la granja en una fábrica de datasets.
Captura uto framos relevantes de las cámaras,
auto-anota con modelo entrenado, y prepara para revisión humana.
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from rich.console import Console

console = Console()


class DatasetFactory:
    """
    Sistema de captura inteligente de frames para entrenar nuevos modelos.
    
    Funciona en conjunción con el pipeline de inferencia:
    1. El modelo detecta animales
    2. DatasetFactory evalúa si el frame es "interesante"
    3. Guarda imagen + auto-anotación YOLO
    4. Marca como pendiente de revisión humana
    """
    
    def __init__(self,
                 output_dir: str = "factory",
                 max_per_hour: int = 50,
                 min_confidence: float = 0.3,
                 max_confidence: float = 0.95,
                 diversity_threshold: float = 0.1):
        """
        Args:
            output_dir: Directorio base para guardar captures
            max_per_hour: Máximo de captures por hora (evitar flood)
            min_confidence: Conf mínima para guardar (debajo = ruido)
            max_confidence: Conf máxima (arriba = ya sabemos, no aporta)
            diversity_threshold: Umbral de diversidad IoU entre frames consecutivos
        """
        self.output_dir = Path(output_dir)
        self.max_per_hour = max_per_hour
        self.min_confidence = min_confidence
        self.max_confidence = max_confidence
        self.diversity_threshold = diversity_threshold
        
        # Sub-dirs
        self.images_dir = self.output_dir / "images"
        self.labels_dir = self.output_dir / "labels"
        self.meta_dir = self.output_dir / "metadata"
        self.review_dir = self.output_dir / "pending_review"
        
        for d in [self.images_dir, self.labels_dir, self.meta_dir, self.review_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # State
        self._hour_counter = 0
        self._current_hour = datetime.now().hour
        self._last_detections = []
    
    def should_capture(self, detections: list[dict]) -> tuple[bool, str]:
        """
        Decide si un frame merece ser guardado para el dataset.
        
        Criterios:
        1. Confianza intermedia (zona de incertidumbre = más valor de entrenamiento)
        2. Diversidad respecto al último frame guardado
        3. Límite por hora no superado
        4. Presencia de clases raras o múltiples animales
        
        Returns: (should_save, reason)
        """
        # Reset counter cada hora
        now = datetime.now()
        if now.hour != self._current_hour:
            self._current_hour = now.hour
            self._hour_counter = 0
        
        # Límite horario
        if self._hour_counter >= self.max_per_hour:
            return False, "hourly_limit"
        
        if not detections:
            return False, "no_detections"
        
        # Criterio 1: Confianza intermedia (más valor para el modelo)
        confidences = [d.get("confidence", 1.0) for d in detections]
        avg_conf = sum(confidences) / len(confidences)
        has_uncertain = any(
            self.min_confidence <= c <= self.max_confidence
            for c in confidences
        )
        
        # Criterio 2: Múltiples animales (escenas complejas)
        multi_animal = len(detections) >= 3
        
        # Criterio 3: Clases raras (piglet, calf, chick)
        rare_classes = {"chick", "piglet", "calf", "lameness", "wound"}
        has_rare = any(
            d.get("class_name", "") in rare_classes
            for d in detections
        )
        
        # Criterio 4: Diversidad vs último frame
        is_diverse = self._check_diversity(detections)
        
        # Decisión
        if has_rare:
            return True, "rare_class"
        if has_uncertain and is_diverse:
            return True, "uncertain_diverse"
        if multi_animal and is_diverse:
            return True, "multi_animal"
        if avg_conf < 0.6 and is_diverse:
            return True, "low_confidence"
        
        return False, "not_interesting"
    
    def _check_diversity(self, detections: list[dict]) -> bool:
        """Verifica que las detecciones sean diferentes al último frame guardado"""
        if not self._last_detections:
            return True
        
        # Comparar por número y posición de detecciones
        if len(detections) != len(self._last_detections):
            return True
        
        # Comparar centroides
        for curr, prev in zip(
            sorted(detections, key=lambda d: d.get("class_id", 0)),
            sorted(self._last_detections, key=lambda d: d.get("class_id", 0))
        ):
            curr_bbox = curr.get("bbox_norm", [0, 0, 0, 0])
            prev_bbox = prev.get("bbox_norm", [0, 0, 0, 0])
            
            dx = abs(curr_bbox[0] - prev_bbox[0])
            dy = abs(curr_bbox[1] - prev_bbox[1])
            
            if dx > self.diversity_threshold or dy > self.diversity_threshold:
                return True
        
        return False
    
    def capture(self, frame: np.ndarray,
                detections: list[dict],
                camera_id: str = "cam0",
                force: bool = False) -> Optional[str]:
        """
        Captura un frame con auto-anotaciones.
        
        Args:
            frame: Imagen BGR
            detections: Lista de detecciones del motor de inferencia
            camera_id: ID de cámara
            force: Forzar captura (bypass criterios)
        
        Returns: Path del archivo guardado o None
        """
        if not force:
            should, reason = self.should_capture(detections)
            if not should:
                return None
        else:
            reason = "forced"
        
        self._hour_counter += 1
        self._last_detections = detections
        
        # Generar nombre único
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stem = f"{camera_id}_{ts}"
        
        # 1. Guardar imagen
        img_path = self.images_dir / f"{stem}.jpg"
        cv2.imwrite(str(img_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        # 2. Guardar annotations en formato YOLO
        h, w = frame.shape[:2]
        label_path = self.labels_dir / f"{stem}.txt"
        lines = []
        for det in detections:
            cls_id = det.get("class_id", 0)
            bbox = det.get("bbox_norm", [0.5, 0.5, 0.1, 0.1])
            lines.append(f"{cls_id} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}")
        label_path.write_text("\n".join(lines) + "\n" if lines else "")
        
        # 3. Metadata
        meta = {
            "timestamp": datetime.now().isoformat(),
            "camera_id": camera_id,
            "capture_reason": reason,
            "resolution": [w, h],
            "num_detections": len(detections),
            "auto_annotated": True,
            "reviewed": False,
            "detections": detections,
        }
        meta_path = self.meta_dir / f"{stem}.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        
        # 4. Añadir a cola de revisión
        review_path = self.review_dir / f"{stem}.json"
        review_path.write_text(json.dumps({
            "image": str(img_path),
            "label": str(label_path),
            "reason": reason,
            "needs_review": True,
        }, indent=2))
        
        return str(img_path)
    
    def get_review_queue(self) -> list[dict]:
        """Lista frames pendientes de revisión humana"""
        queue = []
        for f in sorted(self.review_dir.glob("*.json")):
            data = json.loads(f.read_text())
            data["review_file"] = str(f)
            queue.append(data)
        return queue
    
    def approve_annotation(self, review_file: str):
        """Marca una anotación como correcta (revisada)"""
        rf = Path(review_file)
        if rf.exists():
            data = json.loads(rf.read_text())
            
            # Actualizar metadata
            meta_file = self.meta_dir / rf.name
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                meta["reviewed"] = True
                meta["review_result"] = "approved"
                meta_file.write_text(json.dumps(meta, indent=2))
            
            rf.unlink()
    
    def reject_annotation(self, review_file: str):
        """Marca una anotación como incorrecta y elimina"""
        rf = Path(review_file)
        if rf.exists():
            data = json.loads(rf.read_text())
            
            # Eliminar imagen, label y metadata
            for key in ["image", "label"]:
                p = Path(data.get(key, ""))
                if p.exists():
                    p.unlink()
            
            meta_file = self.meta_dir / rf.name
            if meta_file.exists():
                meta_file.unlink()
            
            rf.unlink()
    
    def export_approved(self, output_dir: str) -> int:
        """
        Exporta todas las imágenes aprobadas a un directorio
        listo para entrenamiento YOLO.
        """
        out = Path(output_dir)
        out_imgs = out / "images"
        out_lbls = out / "labels"
        out_imgs.mkdir(parents=True, exist_ok=True)
        out_lbls.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for meta_file in self.meta_dir.glob("*.json"):
            meta = json.loads(meta_file.read_text())
            if meta.get("reviewed") and meta.get("review_result") == "approved":
                stem = meta_file.stem
                img = self.images_dir / f"{stem}.jpg"
                lbl = self.labels_dir / f"{stem}.txt"
                
                if img.exists():
                    shutil.copy2(img, out_imgs / img.name)
                if lbl.exists():
                    shutil.copy2(lbl, out_lbls / lbl.name)
                count += 1
        
        console.print(f"[green]✅ Exportados {count} frames aprobados → {output_dir}[/]")
        return count
    
    def stats(self) -> dict:
        """Estadísticas del dataset factory"""
        total_images = len(list(self.images_dir.glob("*.jpg")))
        pending = len(list(self.review_dir.glob("*.json")))
        
        reviewed = 0
        approved = 0
        for meta_file in self.meta_dir.glob("*.json"):
            meta = json.loads(meta_file.read_text())
            if meta.get("reviewed"):
                reviewed += 1
                if meta.get("review_result") == "approved":
                    approved += 1
        
        s = {
            "total_captures": total_images,
            "pending_review": pending,
            "reviewed": reviewed,
            "approved": approved,
            "rejected": reviewed - approved,
            "hourly_captures": self._hour_counter,
        }
        
        console.print(f"\n[bold]📊 Dataset Factory Stats:[/]")
        console.print(f"  Total capturas: {s['total_captures']}")
        console.print(f"  Pendientes de revisión: [yellow]{s['pending_review']}[/]")
        console.print(f"  Revisados: {s['reviewed']}")
        console.print(f"  Aprobados: [green]{s['approved']}[/]")
        console.print(f"  Rechazados: [red]{s['rejected']}[/]")
        console.print(f"  Capturas esta hora: {s['hourly_captures']}/{self.max_per_hour}")
        
        return s
