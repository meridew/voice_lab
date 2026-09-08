"""Audio I/O helpers. Everything internal is float32 mono in [-1, 1] plus a sample rate."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def ensure_ffmpeg() -> str | None:
    """Put an ffmpeg on PATH without apt (imageio-ffmpeg bundles a static binary) and return its path."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        shim = Path.home() / ".cache" / "voice-lab" / "bin"
        shim.mkdir(parents=True, exist_ok=True)
        link = shim / "ffmpeg"
        if not link.exists():
            link.symlink_to(exe)
        os.environ["PATH"] = f"{shim}{os.pathsep}{os.environ.get('PATH', '')}"
        return str(link)
    except Exception:
        return None


def load(path: str, sr: int | None = None) -> tuple[np.ndarray, int]:
    audio, native_sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr is not None and sr != native_sr:
        audio = librosa.resample(audio, orig_sr=native_sr, target_sr=sr)
        native_sr = sr
    return np.ascontiguousarray(audio, dtype=np.float32), int(native_sr)


def save(path: str, audio: np.ndarray, sr: int) -> str:
    sf.write(path, np.asarray(audio, dtype=np.float32), sr, subtype="PCM_16")
    return path


def resample(audio: np.ndarray, sr: int, target_sr: int) -> tuple[np.ndarray, int]:
    if sr == target_sr:
        return audio, sr
    return librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=sr, target_sr=target_sr), target_sr


def peak_normalize(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    m = float(np.max(np.abs(audio))) if audio.size else 0.0
    return audio if m < 1e-9 else (audio / m * peak).astype(np.float32)


def duration(audio: np.ndarray, sr: int) -> float:
    return float(len(audio)) / float(sr)


def median_f0(audio: np.ndarray, sr: int) -> float | None:
    """Median voiced pitch in Hz (a crude objective check: adult male ~85-155, adult female ~165-255)."""
    try:
        f0, voiced, _ = librosa.pyin(audio, fmin=60, fmax=500, sr=sr, frame_length=2048)
        f0 = f0[voiced & np.isfinite(f0)]
        return float(np.median(f0)) if f0.size else None
    except Exception:
        return None
