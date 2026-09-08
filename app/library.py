"""The library on disk: originals, augmented clips and reference voices.

  sources/            originals: recordings and imports, <stamp>_<slug>.wav + .json sidecar (label, type, seconds)
  library/renders/    augmented: conversions and renders, <stamp>_<slug>.wav + .json sidecar (label, type, voice, mode, effects, input, stats)
  library/voices/     reference voices: <name>.wav + voices.json

Kinds are original | augmented | voice; the page refers to a clip as "<kind>:<name>". Exports are encoded on
demand into a temp file and streamed; nothing is kept beyond the library itself.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from audio import duration, ensure_ffmpeg, load, peak_normalize, resample, save

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = {"original": ROOT / "sources", "augmented": ROOT / "library" / "renders", "voice": ROOT / "library" / "voices"}
for folder in FOLDERS.values():
    folder.mkdir(parents=True, exist_ok=True)
EXPORT_FORMATS = {
    # ffmpeg arguments per format: Opus for the game (Chromium decodes it natively, ~20 KB per 4 s line),
    # MP3 for sharing (plays inline in every chat app), WAV as the master.
    "opus": (".ogg", ["-c:a", "libopus", "-b:a", "48k", "-vbr", "on", "-application", "audio"]),
    "mp3": (".mp3", ["-c:a", "libmp3lame", "-b:a", "128k"]),
    "wav": (".wav", None),
}


def slug(text: str, limit: int = 48) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
    return text[:limit] or "untitled"


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def when(name: str) -> str:
    """'YYYY-MM-DD HH:MM' from a stamped name."""
    head = name.split("_", 1)[0]
    return f"{head[0:4]}-{head[4:6]}-{head[6:8]} {head[9:11]}:{head[11:13]}" if len(head) >= 13 else ""


# ----------------------------------------------------------------------------- clips of every kind
def clip_path(kind: str, name: str) -> str:
    return str(FOLDERS[kind] / f"{name}.wav")


def _seconds(path: Path) -> float:
    try:
        info = sf.info(str(path))
        return info.frames / info.samplerate
    except Exception:
        return 0.0


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def meta(kind: str, name: str) -> dict:
    if kind == "voice":
        return _voices_index().get(name, {})
    return _read_json(FOLDERS[kind] / f"{name}.json")


def _clip_at(kind: str, path: Path) -> dict:
    """One clip's record: kind, name, label, type (Voice | SFX), seconds, when, plus voice/mode/effects/input when known."""
    side = meta(kind, path.stem)
    if kind == "voice":
        return {"kind": kind, "name": path.stem, "label": path.stem, "type": "Voice",
                "seconds": float(side.get("seconds") or _seconds(path)), "when": when(side.get("created", ""))}
    clip = {"kind": kind, "name": path.stem, "label": side.get("label") or path.stem.split("_", 1)[-1], "type": side.get("type", "Voice"),
            "seconds": float(side.get("seconds") or _seconds(path)), "when": when(path.stem)}
    clip.update({key: side[key] for key in ("voice", "mode", "effects", "input") if side.get(key)})
    return clip


_version = 0                     # bumped by every write below; listings are cached against it (sidecar reads over /mnt/c are slow)
_listings: dict = {}


def _changed() -> None:
    global _version
    _version += 1


def list_clips(kind: str) -> list[dict]:
    """Voices by name; everything else newest first."""
    if _listings.get(kind, (None,))[0] != _version:
        _listings[kind] = (_version, [_clip_at(kind, p) for p in sorted(FOLDERS[kind].glob("*.wav"), reverse=kind != "voice")])
    return [dict(c) for c in _listings[kind][1]]


def clip(kind: str, name: str) -> dict | None:
    path = Path(clip_path(kind, name))
    return _clip_at(kind, path) if path.exists() else None


def delete_clip(kind: str, name: str) -> None:
    for path in (Path(clip_path(kind, name)), FOLDERS[kind] / f"{name}.json"):
        path.unlink(missing_ok=True)
    if kind == "voice":
        index = _voices_index()
        index.pop(name, None)
        _write_json(FOLDERS["voice"] / "voices.json", index)
    _changed()


def update_meta(kind: str, name: str, fields: dict) -> None:
    """Change a clip's label or type; the audio and its stamped file name stay."""
    side = FOLDERS[kind] / f"{name}.json"
    _write_json(side, {**_read_json(side), "name": name, **fields})
    _changed()


# ----------------------------------------------------------------------------- originals
def add_original(path: str, name: str | None = None, meta: dict | None = None) -> str:
    """Store a recording or import as an original with its sidecar; returns its name."""
    audio, sr = load(path)
    label = (name or "").strip() or f"take {time.strftime('%H:%M')}"
    out = FOLDERS["original"] / f"{stamp()}_{slug(label)}.wav"
    save(str(out), audio, sr)
    _write_json(out.with_suffix(".json"), {"name": out.stem, "label": label, "type": "Voice", **(meta or {}), "seconds": round(duration(audio, sr), 2)})
    _changed()
    return out.stem


def update_original(name: str, path: str) -> None:
    """Replace an original's audio (a crop) and refresh its length."""
    audio, sr = load(path)
    save(clip_path("original", name), audio, sr)
    side = FOLDERS["original"] / f"{name}.json"
    _write_json(side, {**_read_json(side), "name": name, "seconds": round(duration(audio, sr), 2)})
    _changed()


# ----------------------------------------------------------------------------- augmented
def save_augmented(audio: np.ndarray, sr: int, meta: dict, label: str) -> str:
    name = f"{stamp()}_{slug(label)}"
    save(clip_path("augmented", name), audio, sr)
    _write_json(FOLDERS["augmented"] / f"{name}.json", {"name": name, "seconds": round(duration(audio, sr), 2), "sr": sr, **meta})
    _changed()
    return name


# ----------------------------------------------------------------------------- voices
def _voices_index() -> dict:
    return _read_json(FOLDERS["voice"] / "voices.json")


def list_voices() -> list[str]:
    return sorted(p.stem for p in FOLDERS["voice"].glob("*.wav"))


def voice_path(name: str) -> str:
    return clip_path("voice", name)


MAX_VOICE_SECONDS = 12           # the model diffuses the reference alongside every take, so its length is paid on every step


def add_voice(name: str, audio: np.ndarray, sr: int, meta: dict | None = None) -> str:
    name = slug(name)
    audio = np.asarray(audio)[: int(MAX_VOICE_SECONDS * sr)]
    save(voice_path(name), audio, sr)
    index = _voices_index()
    index[name] = {"created": stamp(), "seconds": round(duration(audio, sr), 2), **(meta or {})}
    _write_json(FOLDERS["voice"] / "voices.json", index)
    _changed()
    return name


# ----------------------------------------------------------------------------- export
def export_clip(kind: str, name: str, fmt: str = "opus", sr: int = 48000, peak_db: float = -1.0) -> tuple[str, str]:
    """Encode a clip for delivery into its own temp folder: 48 kHz mono, peak-normalised, per EXPORT_FORMATS.

    Returns (path, download name); the caller removes the folder once the file has been sent.
    """
    ext, encode = EXPORT_FORMATS[fmt]
    audio, native_sr = load(clip_path(kind, name))
    audio, _ = resample(audio, native_sr, int(sr))
    audio = peak_normalize(audio, 10 ** (float(peak_db) / 20.0))
    filename = f"{slug(meta(kind, name).get('label') or name, 80)}{ext}"
    out = Path(tempfile.mkdtemp(prefix="lab_export_")) / filename
    if encode is None:
        save(str(out), audio, int(sr))
        return str(out), filename
    ffmpeg = ensure_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("No ffmpeg available for encoding; export as wav instead.")
    master = out.with_suffix(".master.wav")
    save(str(master), audio, int(sr))
    proc = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(master), "-ac", "1", *encode, str(out)],
                          capture_output=True, text=True)
    master.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-400:]}")
    return str(out), filename
