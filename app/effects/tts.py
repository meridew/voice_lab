"""Kokoro text-to-speech: makes reference voices (and stand-in test material) locally on the CPU."""
from __future__ import annotations

import numpy as np

from . import Param, effect

KOKORO_SR = 24000
FEMALE = ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_alloy", "af_aoede", "af_jessica", "af_kore",
          "af_nova", "af_river", "bf_emma", "bf_isabella", "bf_alice", "bf_lily"]
MALE = ["am_adam", "am_michael", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_onyx", "am_puck", "bm_george",
        "bm_lewis", "bm_daniel", "bm_fable"]
VOICES = FEMALE + MALE

_pipelines: dict = {}


def _pipeline(lang_code: str):
    if lang_code not in _pipelines:
        from kokoro import KPipeline
        _pipelines[lang_code] = KPipeline(lang_code=lang_code)
    return _pipelines[lang_code]


def synthesize(text: str, voice: str = "af_heart", speed: float = 1.0) -> tuple[np.ndarray, int]:
    """American voices start with 'a', British with 'b'; the pipeline language follows the voice."""
    pipeline = _pipeline(voice[0] if voice[0] in "ab" else "a")
    chunks = []
    for result in pipeline(text, voice=voice, speed=float(speed)):
        audio = result[2] if isinstance(result, tuple) else getattr(result, "audio", result)
        audio = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
        chunks.append(np.asarray(audio, dtype=np.float32))
        chunks.append(np.zeros(int(KOKORO_SR * 0.25), dtype=np.float32))
    if not chunks:
        return np.zeros(KOKORO_SR, dtype=np.float32), KOKORO_SR
    return np.concatenate(chunks), KOKORO_SR


@effect("tts_replace", "Replace with TTS", "voice",
        [Param("text", "Text", "text", "Docking clearance granted."), Param("voice", "Kokoro voice", "choice", "af_heart", choices=VOICES),
         Param("speed", "Speed", "float", 1.0, 0.5, 1.6, 0.05)],
        "Ignores the input audio and speaks the text: for scripted lines that need no performance.")
def tts_replace(audio, sr, text="", voice="af_heart", speed=1.0):
    return synthesize(text, voice, speed)
