"""Effect registry. An effect is a named, parameterised transform (audio, sr) -> (audio, sr).

Chains are plain data: [{"name": "pitch_shift", "params": {"semitones": 4}}, ...], so presets are
JSON and every render can record exactly how it was made.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


@dataclass
class Param:
    name: str
    label: str
    kind: str = "float"           # float | int | bool | choice | voice | text
    default: Any = 0.0
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list | None = None
    help: str = ""


@dataclass
class Effect:
    name: str
    label: str
    category: str                 # voice | dsp | utility
    params: list[Param] = field(default_factory=list)
    fn: Callable[..., tuple[np.ndarray, int]] | None = None
    help: str = ""

    def defaults(self) -> dict:
        return {p.name: p.default for p in self.params}

    def apply(self, audio: np.ndarray, sr: int, **params) -> tuple[np.ndarray, int]:
        merged = {**self.defaults(), **params}
        return self.fn(audio, sr, **merged)


REGISTRY: dict[str, Effect] = {}


def register(effect: Effect) -> Effect:
    REGISTRY[effect.name] = effect
    return effect


def effect(name: str, label: str, category: str, params: list[Param], help: str = ""):
    def wrap(fn):
        return register(Effect(name=name, label=label, category=category, params=params, fn=fn, help=help))
    return wrap


def by_category() -> dict[str, list[Effect]]:
    out: dict[str, list[Effect]] = {}
    for eff in REGISTRY.values():
        out.setdefault(eff.category, []).append(eff)
    return out


def apply_chain(audio: np.ndarray, sr: int, chain: list[dict], log: Callable[[str], None] | None = None) -> tuple[np.ndarray, int]:
    for step in chain:
        eff = REGISTRY[step["name"]]
        t = time.time()
        audio, sr = eff.apply(audio, sr, **(step.get("params") or {}))
        if log:
            log(f"{eff.label}: {time.time() - t:.1f}s")
    return np.asarray(audio, dtype=np.float32), int(sr)


# Importing the modules registers their effects.
from . import dsp, tts, voice_convert  # noqa: E402,F401
