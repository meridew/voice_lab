"""End-to-end smoke test without the UI: make a female reference and a male stand-in take with Kokoro,
convert with Seed-VC v1 (base and F0 modes), report timing and median pitch, save renders.

  PYTHONPATH=app python scripts/smoke.py [--v2] [--steps 10]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import library  # noqa: E402
from audio import duration, load, median_f0, peak_normalize, save  # noqa: E402
from effects import apply_chain  # noqa: E402
from effects.tts import synthesize  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--steps", type=int, default=15)
parser.add_argument("--v2", action="store_true")
parser.add_argument("--engine", default="inproc", choices=["inproc", "cli"])
args = parser.parse_args()

REFERENCE_TEXT = ("Docking clearance granted. Hold your approach vector and cut thrust at two hundred metres. "
                  "Welcome to Meridian Port; the harbour master will be with you shortly.")
TAKE_TEXT = "Meridian control, this is Wayfarer, requesting a berth on the outer ring. We are heavy and running late."

fmt = lambda f: f"{f:.0f} Hz" if f else "n/a"

t = time.time()
if "harbour-master" not in library.list_voices():
    audio, sr = synthesize(REFERENCE_TEXT, "af_heart", 1.0)
    library.add_voice("harbour-master", peak_normalize(audio), sr, {"text": REFERENCE_TEXT, "kokoro_voice": "af_heart"})
ref, ref_sr = load(library.voice_path("harbour-master"))
print(f"reference: {duration(ref, ref_sr):.1f}s, median pitch {fmt(median_f0(ref, ref_sr))} ({time.time() - t:.1f}s)")

t = time.time()
take_name = next((n for n in library.list_sources() if "male-stand-in" in n), None)
if take_name is None:
    audio, sr = synthesize(TAKE_TEXT, "am_adam", 1.0)
    tmp = library.SOURCES / "tmp_take.wav"
    save(str(tmp), peak_normalize(audio), sr)
    take_name = library.add_source(str(tmp), "male-stand-in")
    tmp.unlink()
take, take_sr = load(library.source_path(take_name))
print(f"take: {take_name}, {duration(take, take_sr):.1f}s, median pitch {fmt(median_f0(take, take_sr))} ({time.time() - t:.1f}s)")

runs = [("v1 base", [{"name": "voice_convert", "params": {"voice": "harbour-master", "keep_pitch_contour": False, "steps": args.steps, "engine": args.engine}}]),
        ("v1 f0 +8st", [{"name": "voice_convert", "params": {"voice": "harbour-master", "keep_pitch_contour": True, "semitones": 8, "auto_f0": True, "steps": args.steps, "engine": args.engine}}])]
if args.v2:
    runs.append(("v2 style", [{"name": "voice_convert_v2", "params": {"voice": "harbour-master", "convert_style": True, "steps": args.steps}}]))

for label, chain in runs:
    t = time.time()
    try:
        out, out_sr = apply_chain(take, take_sr, chain, log=lambda m: print("   ", m))
    except Exception as e:
        print(f"{label}: FAILED: {e}")
        continue
    out = peak_normalize(out)
    name = library.save_render(out, out_sr, {"label": f"smoke {label}", "input": f"source:{take_name}", "chain": chain}, label=f"smoke-{label}")
    print(f"{label}: {time.time() - t:.0f}s, {duration(out, out_sr):.1f}s @ {out_sr} Hz, median pitch {fmt(median_f0(out, out_sr))} -> renders/{name}.wav")
