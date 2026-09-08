"""Model work that runs in a worker process, so the web server stays responsive while Seed-VC is busy.

The server keeps one worker alive across jobs (the models stay warm in it) and hands it wav paths and settings.
"""
from __future__ import annotations

import voice_convert
from audio import duration, load, median_f0, peak_normalize, save


def convert(in_path: str, out_path: str, voice: str, mode: str, steps: int, pitch: int) -> dict:
    """Convert the wav at in_path, write the normalised result to out_path, and report what happened."""
    audio, sr = load(in_path)
    out, out_sr = voice_convert.convert(audio, sr, voice, mode, steps, pitch)
    out = peak_normalize(out)
    save(out_path, out, out_sr)
    f_in, f_out = median_f0(audio, sr), median_f0(out, out_sr)
    return {"seconds": round(duration(out, out_sr), 2), "sr": int(out_sr), "f0_in": round(f_in or 0), "f0_out": round(f_out or 0)}
