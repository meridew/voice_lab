"""Model work that runs in a worker process, so the web server stays responsive while Seed-VC is busy.

The server keeps one worker alive across jobs (the models stay warm in it) and hands it wav paths and settings.
"""
from __future__ import annotations

import sys
import time

import numpy as np

import library
import voice_convert
from audio import duration, load, median_f0, peak_normalize, save


def warm() -> None:
    """Run one tiny Timbre conversion in the worker, so the session's first real one pays for none of the loading.

    The F0 path loads its own vocoder on first use and the pitch analysis compiles on first call, so loading the
    wrapper alone is not enough.
    """
    t0 = time.time()
    voices = library.list_voices()
    if not voices:
        voice_convert.warm_v1()
    else:
        sr = 16000
        tone = (0.3 * np.sin(2 * np.pi * 120 * np.arange(sr) / sr)).astype(np.float32)
        out, out_sr = voice_convert.convert(tone, sr, voices[0], "v1", steps=2, pitch=0)
        median_f0(out, out_sr)
    print(f"warm-up done in {time.time() - t0:.0f} s", file=sys.stderr, flush=True)


def convert(in_path: str, out_path: str, voice: str, mode: str, steps: int, pitch: int) -> dict:
    """Convert the wav at in_path, write the normalised result to out_path, and report what happened."""
    audio, sr = load(in_path)
    out, out_sr = voice_convert.convert(audio, sr, voice, mode, steps, pitch)
    out = peak_normalize(out)
    save(out_path, out, out_sr)
    f_in, f_out = median_f0(audio, sr), median_f0(out, out_sr)
    return {"seconds": round(duration(out, out_sr), 2), "sr": int(out_sr), "f0_in": round(f_in or 0), "f0_out": round(f_out or 0)}
