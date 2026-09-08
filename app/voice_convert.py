"""Seed-VC voice conversion on the CPU, both models kept warm in the process that calls it (the worker).

v1 ("pitch" model family): timbre conversion to a reference voice; its F0-conditioned variant keeps your pitch
contour and moves its level onto the reference's, the reliable male-to-female path. v2 ("style") also converts
accent and emotion. The models come from Hugging Face on first use.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

from audio import duration, ensure_ffmpeg, save
from library import voice_path

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "seed-vc"
_lock = threading.Lock()
_wrapper = None
_wrapper_v2 = None
_ar_budget = 4000                # v2 token budget for the current conversion; set from the take's length, see convert_v2


def _prepare_torch():
    """CPU workarounds shared by both wrappers; idempotent."""
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    import torch
    # oneDNN's aarch64 JIT (Xbyak) fails with "illegal immediate parameter" in BigVGAN's anti-aliasing depthwise conv1d
    # (reproduced in v1 and v2). setup.sh patches that one filter to bypass oneDNN, and with the fast kernels on
    # everywhere else v1 runs 1.6x faster (36 s vs 58 s for a 6.8 s take at 15 steps). VOICE_LAB_ONEDNN=0 reverts.
    torch.backends.mkldnn.enabled = os.environ.get("VOICE_LAB_ONEDNN", "1") != "0"
    # The wrappers hard-code float16 autocast; on the CPU that is slow or unsupported, so autocast becomes a no-op
    # there and everything runs in float32.
    if not getattr(torch, "_voice_lab_autocast_patched", False):
        _orig_autocast = torch.autocast

        class _CpuSafeAutocast(_orig_autocast):
            def __init__(self, device_type, dtype=None, enabled=True, cache_enabled=None):
                if device_type == "cpu" and dtype in (torch.float16, torch.float32):
                    enabled = False
                super().__init__(device_type, dtype=dtype, enabled=enabled, cache_enabled=cache_enabled)
        torch.autocast = _CpuSafeAutocast
        torch._voice_lab_autocast_patched = True
    return torch


@contextlib.contextmanager
def _in_vendor():
    """The wrappers resolve config and checkpoint paths relative to the Seed-VC checkout."""
    cwd = os.getcwd()
    os.chdir(VENDOR)
    try:
        yield
    finally:
        os.chdir(cwd)


def _v1_wrapper():
    global _wrapper
    with _lock:
        if _wrapper is None:
            torch = _prepare_torch()
            with _in_vendor():
                from seed_vc_wrapper import SeedVCWrapper
                _wrapper = SeedVCWrapper(device=torch.device("cpu"))
        return _wrapper


def _v2_wrapper():
    """The v2 model assembly lives in a hydra config; this mirrors inference_v2.py's load_v2_models on the CPU."""
    global _wrapper_v2
    with _lock:
        if _wrapper_v2 is None:
            torch = _prepare_torch()
            ffmpeg = ensure_ffmpeg()                           # v2 renders its output through pydub's mp3 export
            with _in_vendor():
                import yaml
                from hydra.utils import instantiate
                from omegaconf import DictConfig
                with open("configs/v2/vc_wrapper.yaml", encoding="utf-8") as f:
                    wrapper = instantiate(DictConfig(yaml.safe_load(f)))
                wrapper.load_checkpoints(ar_checkpoint_path=None, cfm_checkpoint_path=None)
                wrapper.to(torch.device("cpu"))
                wrapper.eval()
                wrapper.setup_ar_caches(max_batch_size=1, max_seq_len=4096, dtype=torch.float32, device=torch.device("cpu"))
                # The autoregressive decode is small matmuls where oneDNN gains nothing, and one run under oneDNN
                # produced a runaway silent output, so that stage keeps the native kernels. It also gets the token
                # budget (the vendored generate is patched to take one), so a runaway stops early.
                orig_generate = wrapper.ar.generate

                def generate_native(*args, **kwargs):
                    with torch.backends.mkldnn.flags(enabled=False):
                        return orig_generate(*args, max_new_tokens=_ar_budget, **kwargs)
                wrapper.ar.generate = generate_native
                if ffmpeg:
                    from pydub import AudioSegment
                    AudioSegment.converter = ffmpeg
            _wrapper_v2 = wrapper
        return _wrapper_v2


@contextlib.contextmanager
def _temp_wav(audio: np.ndarray, sr: int):
    fd, path = tempfile.mkstemp(prefix="vc_src_", suffix=".wav")
    os.close(fd)
    save(path, audio, sr)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


def convert_v1(audio, sr, voice, *, semitones=0, steps=15, cfg=0.7, length=1.0, keep_pitch_contour=True, auto_f0=True):
    """Timbre: the F0 model keeps the melody of the delivery, auto-matched to the voice's level plus `semitones`."""
    wrapper = _v1_wrapper()
    with _temp_wav(audio, sr) as src_path, _lock:
        # convert_voice contains `yield`, so it is always a generator; with stream_output=False the full waveform
        # arrives as the generator's return value (StopIteration.value).
        gen = wrapper.convert_voice(src_path, voice_path(voice), diffusion_steps=int(steps), length_adjust=float(length),
                                    inference_cfg_rate=float(cfg), f0_condition=bool(keep_pitch_contour), auto_f0_adjust=bool(auto_f0),
                                    pitch_shift=int(semitones), stream_output=False)
        out, last = None, None
        try:
            while True:
                last = next(gen)
        except StopIteration as stop:
            out = stop.value
        if out is None and isinstance(last, tuple) and len(last) == 2 and last[1] is not None:
            out = last[1][1] if isinstance(last[1], tuple) else last[1]
        if out is None:
            raise RuntimeError("Seed-VC returned no audio")
    out = np.asarray(out, dtype=np.float32).squeeze()
    if np.max(np.abs(out)) > 2.0:
        out = out / 32768.0
    # The F0-conditioned model works at wrapper.sr_f0 (44.1 kHz); the base model at wrapper.sr (22.05 kHz).
    out_sr = (getattr(wrapper, "sr_f0", None) or 44100) if keep_pitch_contour else (getattr(wrapper, "sr", None) or 22050)
    return out, int(out_sr)


def convert_v2(audio, sr, voice, *, steps=15, convert_style=True, intelligibility=0.7, similarity=0.7, length=1.0,
               top_p=0.7, temperature=0.7, repetition_penalty=1.5):
    """Emotion: v2 takes the voice's accent and emotion as well, following its pitch range loosely."""
    global _ar_budget
    wrapper = _v2_wrapper()
    torch = _prepare_torch()
    # The style path samples tokens until an end marker and occasionally runs away into a long silent output. The
    # budget (content tokens run at 50 a second) stops a runaway after twice the expected length instead of the
    # vendor's 4000, and each retry samples more conservatively, which makes the marker far more likely.
    schedule = [(float(temperature), float(top_p)), (0.5, 0.6), (0.3, 0.5)]
    with _temp_wav(audio, sr) as src_path:
        for attempt, (temp, p) in enumerate(schedule):
            with _lock:
                _ar_budget = int(duration(audio, sr) * 50 * 2 * float(length)) + 50
                # stream_output=False drops the result on the floor inside the wrapper (it never returns it), so stream
                # and keep the (sr, audio) pair the last chunk carries; the mp3 bytes alongside it are ignored.
                gen = wrapper.convert_voice_with_streaming(
                    source_audio_path=src_path, target_audio_path=voice_path(voice), diffusion_steps=int(steps), length_adjust=float(length),
                    intelligebility_cfg_rate=float(intelligibility), similarity_cfg_rate=float(similarity), top_p=p, temperature=temp,
                    repetition_penalty=float(repetition_penalty), convert_style=bool(convert_style), anonymization_only=False,
                    device=torch.device("cpu"), dtype=torch.float32, stream_output=True)
                full = None
                for _, full_audio in gen:
                    if full_audio is not None:
                        full = full_audio
            if full is None:
                raise RuntimeError("Seed-VC v2 returned no audio")
            out_sr, out = full
            out = np.asarray(out, dtype=np.float32).squeeze()
            # Legitimate results run up to ~1.3x the take; the budget stops a runaway at 2x + 1 s, so this catches every capped one.
            runaway = duration(out, int(out_sr)) > 2.0 * duration(audio, sr) + 0.5 or float(np.max(np.abs(out))) < 1e-3
            if not runaway:
                return out, int(out_sr)
            print(f"Seed-VC v2 runaway ({duration(out, int(out_sr)):.1f} s, peak {float(np.max(np.abs(out))):.3f}) at temperature {temp}; "
                  f"retry {attempt + 1} of {len(schedule) - 1}", file=sys.stderr, flush=True)
    raise RuntimeError("Seed-VC v2 ran away three times, even sampling conservatively; try a longer take")


def warm_v1() -> None:
    """Load the v1 model ahead of the first conversion."""
    _v1_wrapper()


def convert(audio, sr, voice, mode="v1", steps=15, pitch=0):
    """The app's two modes: Timbre (v1) nudged by `pitch` semitones, or Emotion (v2)."""
    if mode == "v2":
        return convert_v2(audio, sr, voice, steps=steps)
    return convert_v1(audio, sr, voice, semitones=pitch, steps=steps)
