#!/usr/bin/env python3
"""
Clasificador baseline de vocalizaciones de gallinas — CNN sobre Mel-spectrograms.

Entrada:  data/audio_datasets/unified/manifest.csv + clips/
Salida:   data/audio_models/baseline_v1/
            ├── model.pt          — pesos PyTorch
            ├── model_scripted.pt — TorchScript para inferencia
            ├── config.json       — hiperparámetros + label_map
            ├── metrics.json      — accuracy, F1, confusion matrix
            └── training_log.csv  — loss/acc por época

Clases operativas (5) — agrupación desde las 8 originales:
  0: alarm        ← alarm_aerial + alarm_ground
  1: distress     ← distress
  2: contact      ← contact_call
  3: contentment  ← contentment + tidbitting + egg_song
  4: normal       ← normal

Uso:
  python scripts/train_audio_classifier.py [--epochs 60] [--batch-size 32] [--lr 0.001]
"""

import argparse
import csv
import json
import logging
import os
import random
import wave
from collections import Counter
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Paths ──
BASE = Path(__file__).resolve().parent.parent / "data" / "audio_datasets"
UNIFIED = BASE / "unified"
MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "audio_models" / "baseline_v1"

# ── Clase mapping: 8 → 5 ──
CLASS_REMAP = {
    "alarm_aerial": "alarm",
    "alarm_ground": "alarm",
    "distress": "distress",
    "contact_call": "contact",
    "contentment": "contentment",
    "tidbitting": "contentment",
    "egg_song": "contentment",
    "normal": "normal",
}

CLASSES = ["alarm", "distress", "contact", "contentment", "normal"]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

# ── Audio constants ──
SR = 16000
CLIP_SECONDS = 5
N_SAMPLES = SR * CLIP_SECONDS  # 80000
N_MELS = 64
N_FFT = 1024
HOP_LENGTH = 256
N_FRAMES = 1 + (N_SAMPLES - N_FFT) // HOP_LENGTH  # ~309


# ══════════════════════════════════════════════════════════════
# Audio processing (no torchaudio dependency — pure numpy)
# ══════════════════════════════════════════════════════════════

def load_wav_np(path: Path) -> np.ndarray:
    """Load 16-bit mono WAV → float32 array [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    # Pad/trim to exact length
    if len(samples) >= N_SAMPLES:
        return samples[:N_SAMPLES]
    out = np.zeros(N_SAMPLES, dtype=np.float32)
    out[:len(samples)] = samples
    return out


def mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    """Create mel filterbank matrix (n_mels × (n_fft//2+1))."""
    def hz_to_mel(f):
        return 2595 * np.log10(1 + f / 700)

    def mel_to_hz(m):
        return 700 * (10 ** (m / 2595) - 1)

    n_freqs = n_fft // 2 + 1
    mel_min = hz_to_mel(0)
    mel_max = hz_to_mel(sr / 2)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sr).astype(int)

    fb = np.zeros((n_mels, n_freqs), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = bins[i], bins[i + 1], bins[i + 2]
        for j in range(left, center):
            if center > left:
                fb[i, j] = (j - left) / (center - left)
        for j in range(center, right):
            if right > center:
                fb[i, j] = (right - j) / (right - center)
    return fb


_MEL_FB = None


def compute_mel_spectrogram(audio: np.ndarray) -> np.ndarray:
    """Compute log-mel spectrogram. Returns (n_mels, n_frames) float32."""
    global _MEL_FB
    if _MEL_FB is None:
        _MEL_FB = mel_filterbank(SR, N_FFT, N_MELS)

    # STFT with Hann window
    window = np.hanning(N_FFT).astype(np.float32)
    n_frames = 1 + (len(audio) - N_FFT) // HOP_LENGTH
    stft = np.zeros((N_FFT // 2 + 1, n_frames), dtype=np.float32)

    for i in range(n_frames):
        start = i * HOP_LENGTH
        frame = audio[start:start + N_FFT] * window
        spectrum = np.fft.rfft(frame)
        stft[:, i] = np.abs(spectrum).astype(np.float32)

    # Power spectrogram → mel → log
    power = stft ** 2
    mel = _MEL_FB @ power
    log_mel = np.log(mel + 1e-9)
    return log_mel


# ══════════════════════════════════════════════════════════════
# Data augmentation (numpy-based)
# ══════════════════════════════════════════════════════════════

def augment_time_shift(audio: np.ndarray, max_shift: int = 4000) -> np.ndarray:
    """Random circular shift."""
    shift = random.randint(-max_shift, max_shift)
    return np.roll(audio, shift)


def augment_add_noise(audio: np.ndarray, noise_level: float = 0.005) -> np.ndarray:
    """Add Gaussian noise."""
    noise = np.random.randn(len(audio)).astype(np.float32) * noise_level
    return audio + noise


def augment_gain(audio: np.ndarray, min_db: float = -6, max_db: float = 6) -> np.ndarray:
    """Random gain change."""
    db = random.uniform(min_db, max_db)
    return audio * (10 ** (db / 20))


def augment_time_mask(spec: np.ndarray, max_width: int = 30) -> np.ndarray:
    """Mask random time frames (SpecAugment)."""
    spec = spec.copy()
    n_frames = spec.shape[1]
    width = random.randint(1, min(max_width, n_frames // 4))
    start = random.randint(0, n_frames - width)
    spec[:, start:start + width] = spec.mean()
    return spec


def augment_freq_mask(spec: np.ndarray, max_width: int = 8) -> np.ndarray:
    """Mask random frequency bands (SpecAugment)."""
    spec = spec.copy()
    n_mels = spec.shape[0]
    width = random.randint(1, min(max_width, n_mels // 4))
    start = random.randint(0, n_mels - width)
    spec[start:start + width, :] = spec.mean()
    return spec


# ══════════════════════════════════════════════════════════════
# Dataset
# ══════════════════════════════════════════════════════════════

def load_manifest() -> list[dict]:
    """Load and remap manifest to 5 classes."""
    manifest_path = UNIFIED / "manifest.csv"
    rows = []
    with open(manifest_path, "r") as f:
        for row in csv.DictReader(f):
            orig_label = row["label"]
            mapped = CLASS_REMAP.get(orig_label)
            if mapped is None:
                continue
            row["label_5"] = mapped
            row["label_idx"] = CLASS_TO_IDX[mapped]
            row["full_path"] = str(UNIFIED / row["path"])
            rows.append(row)
    return rows


def stratified_split(rows: list[dict], train_ratio=0.7, val_ratio=0.15,
                     seed=42) -> tuple[list, list, list]:
    """Stratified split by label_5."""
    rng = random.Random(seed)
    by_class = {}
    for r in rows:
        by_class.setdefault(r["label_5"], []).append(r)

    train, val, test = [], [], []
    for cls, items in by_class.items():
        rng.shuffle(items)
        n = len(items)
        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))
        train.extend(items[:n_train])
        val.extend(items[n_train:n_train + n_val])
        test.extend(items[n_train + n_val:])

    rng.shuffle(train)
    rng.shuffle(val)
    rng.shuffle(test)
    return train, val, test


def compute_class_weights(rows: list[dict]) -> np.ndarray:
    """Inverse frequency weights, capped at 50x."""
    counts = Counter(r["label_idx"] for r in rows)
    total = sum(counts.values())
    n_classes = len(CLASSES)
    weights = np.ones(n_classes, dtype=np.float32)
    for idx in range(n_classes):
        if counts[idx] > 0:
            weights[idx] = total / (n_classes * counts[idx])
    # Cap extreme weights
    max_w = 50.0
    weights = np.minimum(weights, max_w)
    return weights


# ══════════════════════════════════════════════════════════════
# Oversampling for minority classes
# ══════════════════════════════════════════════════════════════

def oversample_minority(rows: list[dict], target_min: int = 200) -> list[dict]:
    """Duplicate minority class samples to reach target_min."""
    by_class = {}
    for r in rows:
        by_class.setdefault(r["label_5"], []).append(r)

    result = []
    for cls, items in by_class.items():
        result.extend(items)
        if len(items) < target_min:
            # Oversample with augmentation flag
            n_extra = target_min - len(items)
            for i in range(n_extra):
                dup = dict(items[i % len(items)])
                dup["_augment"] = True
                result.append(dup)
            log.info(f"  Oversampled {cls}: {len(items)} → {len(items) + n_extra}")

    random.shuffle(result)
    return result


# ══════════════════════════════════════════════════════════════
# PyTorch Model — lightweight CNN
# ══════════════════════════════════════════════════════════════

def build_model_and_train(train_data, val_data, test_data, class_weights,
                          epochs=60, batch_size=32, lr=0.001):
    """Build and train CNN classifier."""
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from torch.utils.data import Dataset, DataLoader
    except ImportError:
        log.error("PyTorch no instalado. Ejecuta: pip install torch")
        raise

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {device}")

    # ── Dataset class ──
    class AudioDataset(Dataset):
        def __init__(self, rows, augment=False):
            self.rows = rows
            self.augment = augment

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, idx):
            row = self.rows[idx]
            audio = load_wav_np(Path(row["full_path"]))

            should_augment = self.augment or row.get("_augment", False)
            if should_augment:
                if random.random() > 0.5:
                    audio = augment_time_shift(audio)
                if random.random() > 0.5:
                    audio = augment_add_noise(audio)
                if random.random() > 0.5:
                    audio = augment_gain(audio)

            spec = compute_mel_spectrogram(audio)

            if should_augment:
                if random.random() > 0.5:
                    spec = augment_time_mask(spec)
                if random.random() > 0.5:
                    spec = augment_freq_mask(spec)

            # Normalize per-sample
            mean = spec.mean()
            std = spec.std() + 1e-9
            spec = (spec - mean) / std

            tensor = torch.from_numpy(spec).unsqueeze(0)  # (1, n_mels, n_frames)
            label = row["label_idx"]
            return tensor, label

    # ── CNN Model ──
    class AudioCNN(nn.Module):
        """Lightweight CNN for mel-spectrogram classification.
        Input: (batch, 1, 64, ~309) → 5 classes."""

        def __init__(self, n_classes=5):
            super().__init__()
            self.features = nn.Sequential(
                # Block 1
                nn.Conv2d(1, 32, 3, padding=1),
                nn.BatchNorm2d(32),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Dropout2d(0.1),
                # Block 2
                nn.Conv2d(32, 64, 3, padding=1),
                nn.BatchNorm2d(64),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Dropout2d(0.1),
                # Block 3
                nn.Conv2d(64, 128, 3, padding=1),
                nn.BatchNorm2d(128),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Dropout2d(0.2),
                # Block 4
                nn.Conv2d(128, 128, 3, padding=1),
                nn.BatchNorm2d(128),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d((4, 4)),
            )
            self.classifier = nn.Sequential(
                nn.Flatten(),
                nn.Linear(128 * 4 * 4, 128),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(128, n_classes),
            )

        def forward(self, x):
            x = self.features(x)
            x = self.classifier(x)
            return x

    # ── Training ──
    model = AudioCNN(n_classes=len(CLASSES)).to(device)
    log.info(f"Model params: {sum(p.numel() for p in model.parameters()):,}")

    weight_tensor = torch.from_numpy(class_weights).to(device)
    criterion = nn.CrossEntropyLoss(weight=weight_tensor)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    train_ds = AudioDataset(train_data, augment=True)
    val_ds = AudioDataset(val_data, augment=False)
    test_ds = AudioDataset(test_data, augment=False)

    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                          num_workers=4, pin_memory=True, persistent_workers=True)
    val_dl = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                        num_workers=2, pin_memory=True, persistent_workers=True)
    test_dl = DataLoader(test_ds, batch_size=batch_size, shuffle=False,
                         num_workers=2, pin_memory=True, persistent_workers=True)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    log_path = MODEL_DIR / "training_log.csv"
    best_val_acc = 0.0
    patience = 10
    patience_counter = 0

    with open(log_path, "w", newline="") as logf:
        writer = csv.writer(logf)
        writer.writerow(["epoch", "train_loss", "train_acc", "val_loss", "val_acc", "lr"])

        for epoch in range(1, epochs + 1):
            # Train
            model.train()
            train_loss, train_correct, train_total = 0.0, 0, 0
            for batch_x, batch_y in train_dl:
                batch_x = batch_x.to(device)
                batch_y = torch.tensor(batch_y, dtype=torch.long).to(device)
                optimizer.zero_grad()
                out = model(batch_x)
                loss = criterion(out, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item() * batch_x.size(0)
                preds = out.argmax(dim=1)
                train_correct += (preds == batch_y).sum().item()
                train_total += batch_x.size(0)

            scheduler.step()

            # Validate
            model.eval()
            val_loss, val_correct, val_total = 0.0, 0, 0
            with torch.no_grad():
                for batch_x, batch_y in val_dl:
                    batch_x = batch_x.to(device)
                    batch_y = torch.tensor(batch_y, dtype=torch.long).to(device)
                    out = model(batch_x)
                    loss = criterion(out, batch_y)
                    val_loss += loss.item() * batch_x.size(0)
                    preds = out.argmax(dim=1)
                    val_correct += (preds == batch_y).sum().item()
                    val_total += batch_x.size(0)

            t_loss = train_loss / train_total
            t_acc = train_correct / train_total
            v_loss = val_loss / val_total
            v_acc = val_correct / val_total
            cur_lr = scheduler.get_last_lr()[0]

            writer.writerow([epoch, f"{t_loss:.4f}", f"{t_acc:.4f}",
                            f"{v_loss:.4f}", f"{v_acc:.4f}", f"{cur_lr:.6f}"])
            logf.flush()

            if epoch % 5 == 0 or epoch == 1:
                log.info(f"Ep {epoch:3d}/{epochs} | "
                         f"train {t_loss:.3f} acc={t_acc:.3f} | "
                         f"val {v_loss:.3f} acc={v_acc:.3f} | lr={cur_lr:.5f}")

            # Early stopping + best model
            if v_acc > best_val_acc:
                best_val_acc = v_acc
                patience_counter = 0
                torch.save(model.state_dict(), MODEL_DIR / "model.pt")
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    log.info(f"Early stopping at epoch {epoch} (best val_acc={best_val_acc:.4f})")
                    break

    # Load best model for evaluation
    model.load_state_dict(torch.load(MODEL_DIR / "model.pt", weights_only=True))
    model.eval()

    # ── Test evaluation ──
    all_preds = []
    all_labels = []
    with torch.no_grad():
        for batch_x, batch_y in test_dl:
            batch_x = batch_x.to(device)
            out = model(batch_x)
            preds = out.argmax(dim=1).cpu().numpy()
            all_preds.extend(preds)
            all_labels.extend(batch_y if isinstance(batch_y, list) else batch_y.numpy() if hasattr(batch_y, 'numpy') else list(batch_y))

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)

    # Metrics
    test_acc = (all_preds == all_labels).mean()
    log.info(f"\nTest accuracy: {test_acc:.4f}")

    # Per-class metrics
    per_class = {}
    for idx, cls in enumerate(CLASSES):
        mask_true = all_labels == idx
        mask_pred = all_preds == idx
        tp = int(np.sum(mask_true & mask_pred))
        fp = int(np.sum(~mask_true & mask_pred))
        fn = int(np.sum(mask_true & ~mask_pred))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": int(mask_true.sum()),
        }
        log.info(f"  {cls:15s}  P={precision:.3f} R={recall:.3f} F1={f1:.3f} n={mask_true.sum()}")

    # Confusion matrix
    n_cls = len(CLASSES)
    cm = np.zeros((n_cls, n_cls), dtype=int)
    for t, p in zip(all_labels, all_preds):
        cm[t][p] += 1

    # Macro F1
    macro_f1 = np.mean([v["f1"] for v in per_class.values()])
    log.info(f"\nMacro F1: {macro_f1:.4f}")

    # Save metrics
    metrics = {
        "test_accuracy": round(float(test_acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "best_val_accuracy": round(float(best_val_acc), 4),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "classes": CLASSES,
        "n_test": len(all_labels),
    }
    with open(MODEL_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    # Save config
    config = {
        "model": "AudioCNN_v1",
        "classes": CLASSES,
        "class_remap": CLASS_REMAP,
        "n_classes": len(CLASSES),
        "sample_rate": SR,
        "clip_seconds": CLIP_SECONDS,
        "n_mels": N_MELS,
        "n_fft": N_FFT,
        "hop_length": HOP_LENGTH,
        "epochs_trained": epoch,
        "batch_size": batch_size,
        "learning_rate": lr,
        "class_weights": class_weights.tolist(),
    }
    with open(MODEL_DIR / "config.json", "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Save TorchScript
    try:
        example = torch.randn(1, 1, N_MELS, N_FRAMES).to(device)
        scripted = torch.jit.trace(model, example)
        scripted.save(str(MODEL_DIR / "model_scripted.pt"))
        log.info(f"TorchScript saved: {MODEL_DIR / 'model_scripted.pt'}")
    except Exception as e:
        log.warning(f"TorchScript export failed: {e}")

    log.info(f"\nModel saved to: {MODEL_DIR}")
    return metrics


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Train audio vocalization classifier")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--oversample-min", type=int, default=200,
                        help="Min samples per class after oversampling (default: 200)")
    args = parser.parse_args()

    log.info("=== Audio Vocalization Classifier — Baseline v1 ===")

    # Load data
    rows = load_manifest()
    log.info(f"Total samples (remapped to 5 classes): {len(rows)}")

    counts = Counter(r["label_5"] for r in rows)
    for cls in CLASSES:
        log.info(f"  {cls:15s} {counts.get(cls, 0):6d}")

    # Split
    train, val, test = stratified_split(rows)
    log.info(f"\nSplit: train={len(train)}, val={len(val)}, test={len(test)}")

    # Oversample minority classes in train
    train = oversample_minority(train, target_min=args.oversample_min)
    log.info(f"After oversampling: train={len(train)}")

    train_counts = Counter(r["label_5"] for r in train)
    for cls in CLASSES:
        log.info(f"  {cls:15s} {train_counts.get(cls, 0):6d}")

    # Class weights
    weights = compute_class_weights(train)
    log.info(f"\nClass weights: {dict(zip(CLASSES, [f'{w:.2f}' for w in weights]))}")

    # Train
    metrics = build_model_and_train(
        train, val, test, weights,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )

    log.info(f"\n{'='*50}")
    log.info(f"Test Accuracy: {metrics['test_accuracy']:.4f}")
    log.info(f"Macro F1:      {metrics['macro_f1']:.4f}")
    log.info(f"Model dir:     {MODEL_DIR}")


if __name__ == "__main__":
    main()
