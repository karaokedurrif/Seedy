#!/usr/bin/env python3
"""
Preparar dataset unificado de audio para clasificación de vocalizaciones de gallinas.

Inputs:
  - data/audio_datasets/chicken_language/  (GitHub zebular13 — 154 WAV, 14 categorías)
  - data/audio_datasets/laying_hens_stress/ (Zenodo Neethirajan — 102 MP3, control+estrés)
  - data/audio_datasets/custom_seedy/       (grabaciones propias ESP32, estructura libre)

Output:
  - data/audio_datasets/unified/
      ├── clips/           ← WAV 16kHz mono 16-bit, 5s cada uno
      ├── manifest.csv     ← path, label, source, duration_s, rms, peak
      └── label_map.json   ← id → label, con conteos

Clases objetivo (8 relevantes para Seedy):
  alarm_ground   — alarma depredador terrestre
  alarm_aerial   — alarma depredador aéreo
  egg_song       — aviso de puesta
  distress       — estrés / malestar (hambre, sed, calor, perturbación)
  contact_call   — llamada de localización ("dónde estáis")
  tidbitting     — ofrecimiento de comida
  contentment    — bienestar (comer, baño de polvo)
  normal         — actividad normal / background

Uso:
  python scripts/prepare_audio_dataset.py [--skip-zenodo] [--clip-seconds 5]
"""

import argparse
import csv
import json
import logging
import os
import struct
import wave
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent / "data" / "audio_datasets"
OUT = BASE / "unified"
CLIPS_DIR = OUT / "clips"
TARGET_SR = 16000
TARGET_CHANNELS = 1
TARGET_BITS = 16

# ── Mapping de subcarpetas → clase unificada ──

CHICKEN_LANG_MAP = {
    # single_vocalizations/
    "eating": "contentment",
    "greeting": "contact_call",
    "hungry": "distress",
    "need_nest_box": "egg_song",
    "disturbed_in_nest_box": "distress",
    "ouch": "distress",
    "tidbitting_hen": "tidbitting",
    "where_is_everyone": "contact_call",
    "unknown": "normal",
    # longer_segments/
    "aerial_alarm": "alarm_aerial",
    "ground_alarm": "alarm_ground",
    "let_us_out": "distress",
}

ZENODO_MAP = {
    "PrestressControl": "normal",
    "PoststressControl": "normal",
    "PrestressTreatment": "normal",       # pre-stress = baseline
    "PoststressTreatment": "distress",     # post-stress = reacción estrés
}


def audio_to_numpy(filepath: Path) -> tuple[np.ndarray, int]:
    """Lee un fichero de audio y devuelve (samples_int16, sample_rate).
    Soporta WAV nativo. Para MP3 usa ffmpeg/pydub como fallback."""
    ext = filepath.suffix.lower()

    if ext == ".wav":
        try:
            with wave.open(str(filepath), "rb") as wf:
                sr = wf.getframerate()
                nch = wf.getnchannels()
                sw = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())

            if sw == 2:
                samples = np.frombuffer(frames, dtype=np.int16)
            elif sw == 1:
                samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128) * 256
            elif sw == 4:
                samples = (np.frombuffer(frames, dtype=np.int32) >> 16).astype(np.int16)
            else:
                raise ValueError(f"Unsupported sample width: {sw}")

            if nch > 1:
                samples = samples.reshape(-1, nch)[:, 0]  # take left channel

            return samples, sr
        except Exception as e:
            log.warning(f"wave failed for {filepath}: {e}, trying pydub")

    # Fallback: pydub (handles MP3, MP4, etc.)
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(filepath))
        audio = audio.set_channels(1).set_sample_width(2)
        sr = audio.frame_rate
        samples = np.frombuffer(audio.raw_data, dtype=np.int16)
        return samples, sr
    except ImportError:
        log.error("pydub not installed. Run: pip install pydub")
        raise
    except Exception as e:
        log.error(f"Failed to load {filepath}: {e}")
        raise


def resample_simple(samples: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Resample con interpolación lineal (sin dependencias extra)."""
    if sr_in == sr_out:
        return samples
    ratio = sr_out / sr_in
    n_out = int(len(samples) * ratio)
    indices = np.linspace(0, len(samples) - 1, n_out)
    return np.interp(indices, np.arange(len(samples)), samples.astype(np.float64)).astype(np.int16)


def write_wav(filepath: Path, samples: np.ndarray, sr: int = TARGET_SR):
    """Escribe WAV 16-bit mono."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.astype(np.int16).tobytes())


def segment_audio(samples: np.ndarray, sr: int, clip_seconds: float,
                  overlap: float = 0.5, min_rms: float = 200.0
                  ) -> list[np.ndarray]:
    """Segmenta audio en clips de duración fija con overlap.
    Descarta clips con RMS < min_rms (silencio)."""
    clip_len = int(sr * clip_seconds)
    step = int(clip_len * (1 - overlap))
    clips = []
    for start in range(0, len(samples) - clip_len + 1, step):
        clip = samples[start:start + clip_len]
        rms = np.sqrt(np.mean(clip.astype(np.float64) ** 2))
        if rms >= min_rms:
            clips.append(clip)
    return clips


def pad_or_trim(samples: np.ndarray, target_len: int) -> np.ndarray:
    """Ajusta a longitud exacta: pad con ceros o trim."""
    if len(samples) >= target_len:
        return samples[:target_len]
    padded = np.zeros(target_len, dtype=np.int16)
    padded[:len(samples)] = samples
    return padded


def process_chicken_language(clip_seconds: float) -> list[dict]:
    """Procesa ChickenLanguageDataset → clips etiquetados."""
    src = BASE / "chicken_language"
    rows = []
    clip_len = int(TARGET_SR * clip_seconds)

    for subdir in ["single_vocalizations", "longer_segments"]:
        root = src / subdir
        if not root.exists():
            continue
        for category_dir in sorted(root.iterdir()):
            if not category_dir.is_dir():
                continue
            cat_name = category_dir.name.strip()
            if cat_name == "3seconds":
                continue
            label = CHICKEN_LANG_MAP.get(cat_name)
            if not label:
                log.warning(f"  Unmapped category: {cat_name}")
                label = "normal"

            for wav_file in sorted(category_dir.rglob("*.wav")):
                try:
                    samples, sr = audio_to_numpy(wav_file)
                    samples = resample_simple(samples, sr, TARGET_SR)

                    if len(samples) < TARGET_SR:  # < 1 second
                        continue

                    if len(samples) <= clip_len * 1.5:
                        # Short: pad/trim to exact clip length
                        clip = pad_or_trim(samples, clip_len)
                        row = _save_clip(clip, label, "chicken_language",
                                         wav_file.stem, 0)
                        if row:
                            rows.append(row)
                    else:
                        # Long: segment
                        clips = segment_audio(samples, TARGET_SR, clip_seconds)
                        for i, clip in enumerate(clips):
                            clip = pad_or_trim(clip, clip_len)
                            row = _save_clip(clip, label, "chicken_language",
                                             wav_file.stem, i)
                            if row:
                                rows.append(row)
                except Exception as e:
                    log.warning(f"  Skip {wav_file}: {e}")

    log.info(f"ChickenLanguage: {len(rows)} clips")
    return rows


def process_zenodo_stress(clip_seconds: float) -> list[dict]:
    """Procesa Zenodo laying hens stress dataset → clips etiquetados."""
    src = BASE / "laying_hens_stress"
    rows = []
    clip_len = int(TARGET_SR * clip_seconds)

    for group_dir in ["control", "treatment"]:
        root = src / group_dir
        if not root.exists():
            continue
        for mp3_file in sorted(root.rglob("*.mp3")):
            # Determine label from parent dir
            parent = mp3_file.parent.name
            label = ZENODO_MAP.get(parent)
            if not label:
                log.warning(f"  Unmapped Zenodo dir: {parent}")
                label = "normal"

            try:
                samples, sr = audio_to_numpy(mp3_file)
                samples = resample_simple(samples, sr, TARGET_SR)

                clips = segment_audio(samples, TARGET_SR, clip_seconds,
                                      overlap=0.3, min_rms=300.0)
                for i, clip in enumerate(clips):
                    clip = pad_or_trim(clip, clip_len)
                    row = _save_clip(clip, label, "zenodo_stress",
                                     mp3_file.stem, i)
                    if row:
                        rows.append(row)
            except Exception as e:
                log.warning(f"  Skip {mp3_file}: {e}")

    log.info(f"Zenodo stress: {len(rows)} clips")
    return rows


def process_custom_seedy(clip_seconds: float) -> list[dict]:
    """Procesa grabaciones propias del ESP32.
    Estructura esperada: custom_seedy/{label}/*.wav
    O custom_seedy/*.wav (se etiquetan como 'unlabeled')."""
    src = BASE / "custom_seedy"
    rows = []
    clip_len = int(TARGET_SR * clip_seconds)

    if not src.exists():
        return rows

    for wav_file in sorted(src.rglob("*.wav")):
        # Label from parent dir if is a category folder
        parent = wav_file.parent.name
        if parent == "custom_seedy":
            label = "unlabeled"
        else:
            label = parent

        try:
            samples, sr = audio_to_numpy(wav_file)
            samples = resample_simple(samples, sr, TARGET_SR)

            if len(samples) <= clip_len * 1.5:
                clip = pad_or_trim(samples, clip_len)
                row = _save_clip(clip, label, "custom_seedy",
                                 wav_file.stem, 0)
                if row:
                    rows.append(row)
            else:
                clips = segment_audio(samples, TARGET_SR, clip_seconds)
                for i, clip in enumerate(clips):
                    clip = pad_or_trim(clip, clip_len)
                    row = _save_clip(clip, label, "custom_seedy",
                                     wav_file.stem, i)
                    if row:
                        rows.append(row)
        except Exception as e:
            log.warning(f"  Skip {wav_file}: {e}")

    if rows:
        log.info(f"Custom Seedy: {len(rows)} clips")
    return rows


_clip_counter = 0


def _save_clip(samples: np.ndarray, label: str, source: str,
               stem: str, idx: int) -> dict | None:
    """Guarda clip WAV y devuelve metadata."""
    global _clip_counter
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    peak = int(np.max(np.abs(samples.astype(np.int32))))

    if rms < 100:  # nearly silent
        return None

    _clip_counter += 1
    fname = f"{label}_{_clip_counter:05d}.wav"
    out_path = CLIPS_DIR / fname
    write_wav(out_path, samples)

    return {
        "path": f"clips/{fname}",
        "label": label,
        "source": source,
        "original": stem,
        "clip_idx": idx,
        "duration_s": len(samples) / TARGET_SR,
        "rms": round(rms, 1),
        "peak": peak,
    }


def main():
    parser = argparse.ArgumentParser(description="Preparar dataset audio unificado")
    parser.add_argument("--clip-seconds", type=float, default=5.0,
                        help="Duración de cada clip en segundos (default: 5)")
    parser.add_argument("--skip-zenodo", action="store_true",
                        help="Saltar dataset Zenodo (2.5 GB, lento)")
    args = parser.parse_args()

    log.info(f"=== Preparando dataset unificado (clips de {args.clip_seconds}s) ===")
    log.info(f"Output: {OUT}")

    # Clean output
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    global _clip_counter
    _clip_counter = 0
    all_rows = []

    # 1. ChickenLanguageDataset
    log.info("\n[1/3] ChickenLanguageDataset...")
    all_rows.extend(process_chicken_language(args.clip_seconds))

    # 2. Zenodo stress
    if not args.skip_zenodo:
        log.info("\n[2/3] Zenodo Laying Hens Stress...")
        all_rows.extend(process_zenodo_stress(args.clip_seconds))
    else:
        log.info("\n[2/3] Zenodo: SKIPPED")

    # 3. Custom Seedy
    log.info("\n[3/3] Custom Seedy recordings...")
    all_rows.extend(process_custom_seedy(args.clip_seconds))

    # Write manifest
    manifest_path = OUT / "manifest.csv"
    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "path", "label", "source", "original", "clip_idx",
            "duration_s", "rms", "peak"])
        writer.writeheader()
        writer.writerows(all_rows)

    # Label map + stats
    from collections import Counter
    counts = Counter(r["label"] for r in all_rows)
    label_map = {i: {"label": lbl, "count": cnt}
                 for i, (lbl, cnt) in enumerate(sorted(counts.items()))}

    with open(OUT / "label_map.json", "w") as f:
        json.dump(label_map, f, indent=2, ensure_ascii=False)

    # Summary
    log.info(f"\n{'='*50}")
    log.info(f"Total clips: {len(all_rows)}")
    log.info(f"Clases ({len(counts)}):")
    for lbl, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        log.info(f"  {lbl:20s} {cnt:5d}")
    log.info(f"\nManifest: {manifest_path}")
    log.info(f"Label map: {OUT / 'label_map.json'}")
    log.info(f"Clips: {CLIPS_DIR}")


if __name__ == "__main__":
    main()
