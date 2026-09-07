"""The library on disk: sources, reference voices, effect presets and rendered outputs.

Layout (all under the project root):
  sources/                 recordings and imports (wav)
  library/voices/          reference voices (wav) + voices.json
  library/presets/         <name>.json effect chains
  library/renders/         <timestamp>_<slug>.wav + .json sidecar describing how it was made
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np

from audio import duration, load, save

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
VOICES = ROOT / "library" / "voices"
PRESETS = ROOT / "library" / "presets"
RENDERS = ROOT / "library" / "renders"
for folder in (SOURCES, VOICES, PRESETS, RENDERS):
    folder.mkdir(parents=True, exist_ok=True)


def slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
    return text[:48] or "untitled"


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# ----------------------------------------------------------------------------- sources
def list_sources() -> list[str]:
    return sorted(p.name for p in SOURCES.glob("*.wav"))


def add_source(path: str, name: str | None = None) -> str:
    audio, sr = load(path)
    out = SOURCES / f"{stamp()}_{slug(name or Path(path).stem)}.wav"
    save(str(out), audio, sr)
    return out.name


def source_path(name: str) -> str:
    return str(SOURCES / name)


# ----------------------------------------------------------------------------- voices
def _voices_index() -> dict:
    index = VOICES / "voices.json"
    return json.loads(index.read_text(encoding="utf-8")) if index.exists() else {}


def _write_voices_index(data: dict) -> None:
    (VOICES / "voices.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_voices() -> list[str]:
    return sorted(p.stem for p in VOICES.glob("*.wav"))


def voice_path(name: str) -> str:
    return str(VOICES / f"{name}.wav")


def add_voice(name: str, audio: np.ndarray, sr: int, meta: dict | None = None) -> str:
    name = slug(name)
    save(voice_path(name), audio, sr)
    index = _voices_index()
    index[name] = {"created": stamp(), "seconds": round(duration(audio, sr), 2), **(meta or {})}
    _write_voices_index(index)
    return name


def voice_meta(name: str) -> dict:
    return _voices_index().get(name, {})


# ----------------------------------------------------------------------------- presets
def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def save_preset(name: str, chain: list[dict], notes: str = "") -> str:
    name = slug(name)
    (PRESETS / f"{name}.json").write_text(json.dumps({"name": name, "notes": notes, "chain": chain}, indent=2), encoding="utf-8")
    return name


def load_preset(name: str) -> list[dict]:
    path = PRESETS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))["chain"] if path.exists() else []


def delete_preset(name: str) -> None:
    path = PRESETS / f"{name}.json"
    if path.exists():
        path.unlink()


# ----------------------------------------------------------------------------- renders
def save_render(audio: np.ndarray, sr: int, meta: dict, label: str = "render") -> str:
    name = f"{stamp()}_{slug(label)}"
    save(str(RENDERS / f"{name}.wav"), audio, sr)
    (RENDERS / f"{name}.json").write_text(json.dumps({"name": name, "seconds": round(duration(audio, sr), 2), "sr": sr, **meta}, indent=2), encoding="utf-8")
    return name


def list_renders() -> list[dict]:
    items = []
    for path in sorted(RENDERS.glob("*.json"), reverse=True):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def render_path(name: str) -> str:
    return str(RENDERS / f"{name}.wav")


def delete_render(name: str) -> None:
    for ext in (".wav", ".json"):
        path = RENDERS / f"{name}{ext}"
        if path.exists():
            path.unlink()


def set_render_notes(name: str, notes: str) -> None:
    path = RENDERS / f"{name}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data["notes"] = notes
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def all_audio_choices() -> list[str]:
    """Every playable item as 'kind:name' for dropdowns."""
    return ([f"source:{n}" for n in list_sources()] + [f"render:{r['name']}" for r in list_renders()]
            + [f"voice:{n}" for n in list_voices()])


def resolve_choice(choice: str) -> str:
    kind, _, name = choice.partition(":")
    return {"source": source_path, "render": render_path, "voice": voice_path}[kind](name)
