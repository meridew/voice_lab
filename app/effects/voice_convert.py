"""Seed-VC voice conversion as effects.

v1 ("pitch" model family): timbre conversion to a reference voice; the F0-conditioned variant keeps
your pitch contour and can shift it by semitones, the base variant re-synthesises pitch in the
target's range. v2 ("style"): also converts accent and emotion, with intelligibility/similarity
control. Both run on the CPU here. The models come from Hugging Face on first use and are cached.

The v1 wrapper is kept warm in-process so repeated conversions do not reload models; v2 runs the
project's CLI in a subprocess because its model assembly lives in hydra configs.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

from . import Param, effect
from audio import load, save
import library

VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "seed-vc"
_lock = threading.Lock()
_wrapper = None


def _voice_choices() -> list[str]:
    return library.list_voices()


def _bool(value) -> str:
    return "True" if bool(value) else "False"


def _v1_wrapper():
    global _wrapper
    with _lock:
        if _wrapper is None:
            if str(VENDOR) not in sys.path:
                sys.path.insert(0, str(VENDOR))
            cwd = os.getcwd()
            os.chdir(VENDOR)                                   # the wrapper resolves relative config paths
            try:
                import torch
                # The wrapper hard-codes float16 autocast; on the CPU that is slow or unsupported, so
                # autocast becomes a no-op there and everything runs in float32.
                if not getattr(torch, "_voice_lab_autocast_patched", False):
                    _orig_autocast = torch.autocast

                    class _CpuSafeAutocast(_orig_autocast):
                        def __init__(self, device_type, dtype=None, enabled=True, cache_enabled=None):
                            if device_type == "cpu" and dtype == torch.float16:
                                enabled = False
                            super().__init__(device_type, dtype=dtype, enabled=enabled, cache_enabled=cache_enabled)
                    torch.autocast = _CpuSafeAutocast
                    torch._voice_lab_autocast_patched = True
                from seed_vc_wrapper import SeedVCWrapper
                _wrapper = SeedVCWrapper(device=torch.device("cpu"))
            finally:
                os.chdir(cwd)
        return _wrapper


def _run_cli(script: str, args: list[str], src_path: str, tgt_path: str) -> tuple[np.ndarray, int]:
    with tempfile.TemporaryDirectory(prefix="vc_") as out_dir:
        cmd = [sys.executable, script, "--source", src_path, "--target", tgt_path, "--output", out_dir, *args]
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.run(cmd, cwd=VENDOR, env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"{script} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}")
        outputs = sorted(glob.glob(os.path.join(out_dir, "*.wav")), key=os.path.getmtime)
        if not outputs:
            raise RuntimeError(f"{script} produced no wav:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
        return load(outputs[-1])


def _temp_wav(audio: np.ndarray, sr: int) -> str:
    fd, path = tempfile.mkstemp(prefix="vc_src_", suffix=".wav")
    os.close(fd)
    save(path, audio, sr)
    return path


@effect("voice_convert", "Voice convert (Seed-VC v1)", "voice",
        [Param("voice", "Target voice", "voice", ""),
         Param("keep_pitch_contour", "Keep my pitch contour (F0 model)", "bool", False,
               help="Off: the base model re-synthesises pitch in the target's range. On: your melody is kept and shifted."),
         Param("semitones", "Semitone shift (F0 model only)", "int", 8, -24, 24, 1),
         Param("auto_f0", "Auto-match pitch level (F0 model only)", "bool", True),
         Param("steps", "Diffusion steps", "int", 25, 4, 60, 1),
         Param("cfg", "Guidance (cfg rate)", "float", 0.7, 0.0, 1.0, 0.05),
         Param("length", "Length adjust", "float", 1.0, 0.5, 2.0, 0.05),
         Param("engine", "Engine", "choice", "inproc", choices=["inproc", "cli"])],
        "Timbre conversion to a library voice. Keeps your timing and emotion.")
def voice_convert(audio, sr, voice="", keep_pitch_contour=False, semitones=8, auto_f0=True, steps=25, cfg=0.7, length=1.0, engine="inproc"):
    if not voice:
        raise ValueError("Pick a target voice (make one on the Voices tab).")
    src_path = _temp_wav(audio, sr)
    tgt_path = library.voice_path(voice)
    try:
        if engine == "inproc":
            wrapper = _v1_wrapper()
            with _lock:
                out = wrapper.convert_voice(src_path, tgt_path, diffusion_steps=int(steps), length_adjust=float(length),
                                            inference_cfg_rate=float(cfg), f0_condition=bool(keep_pitch_contour),
                                            auto_f0_adjust=bool(auto_f0), pitch_shift=int(semitones), stream_output=False)
            out = np.asarray(out, dtype=np.float32).squeeze()
            out_sr = getattr(wrapper, "sr", None) or (44100 if keep_pitch_contour else 22050)
            return out, int(out_sr)
        return _run_cli("inference.py", ["--diffusion-steps", str(int(steps)), "--length-adjust", str(float(length)),
                                         "--inference-cfg-rate", str(float(cfg)), "--f0-condition", _bool(keep_pitch_contour),
                                         "--auto-f0-adjust", _bool(auto_f0), "--semi-tone-shift", str(int(semitones)),
                                         "--fp16", "False"], src_path, tgt_path)
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass


@effect("voice_convert_v2", "Voice convert (Seed-VC v2, style)", "voice",
        [Param("voice", "Target voice", "voice", ""),
         Param("convert_style", "Convert accent and emotion too", "bool", True),
         Param("steps", "Diffusion steps", "int", 30, 4, 60, 1),
         Param("intelligibility", "Intelligibility cfg", "float", 0.7, 0.0, 1.0, 0.05),
         Param("similarity", "Similarity cfg", "float", 0.7, 0.0, 1.0, 0.05),
         Param("length", "Length adjust", "float", 1.0, 0.5, 2.0, 0.05),
         Param("top_p", "Top-p", "float", 0.7, 0.5, 1.0, 0.05),
         Param("temperature", "Temperature", "float", 0.7, 0.5, 1.2, 0.05),
         Param("repetition_penalty", "Repetition penalty", "float", 1.5, 1.0, 2.0, 0.05),
         Param("anonymize", "Anonymise only (ignore target)", "bool", False)],
        "Suppresses more of the source speaker; can change accent and emotion. Slower on CPU.")
def voice_convert_v2(audio, sr, voice="", convert_style=True, steps=30, intelligibility=0.7, similarity=0.7, length=1.0,
                     top_p=0.7, temperature=0.7, repetition_penalty=1.5, anonymize=False):
    if not voice and not anonymize:
        raise ValueError("Pick a target voice (make one on the Voices tab).")
    src_path = _temp_wav(audio, sr)
    tgt_path = library.voice_path(voice) if voice else src_path
    try:
        return _run_cli("inference_v2.py", ["--diffusion-steps", str(int(steps)), "--length-adjust", str(float(length)),
                                            "--intelligibility-cfg-rate", str(float(intelligibility)), "--similarity-cfg-rate", str(float(similarity)),
                                            "--convert-style", _bool(convert_style), "--anonymization-only", _bool(anonymize),
                                            "--top-p", str(float(top_p)), "--temperature", str(float(temperature)),
                                            "--repetition-penalty", str(float(repetition_penalty))], src_path, tgt_path)
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass
