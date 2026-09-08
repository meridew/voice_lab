"""Kokoro text-to-speech: makes reference voices locally on the CPU (nobody's real voice)."""
from __future__ import annotations

import numpy as np

KOKORO_SR = 24000
# Kokoro's English voices, American (a) and British (b); the page offers these when making a reference voice.
KOKORO_VOICES = {
    "female": ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_alloy", "af_aoede", "af_jessica", "af_kore", "af_nova",
               "af_river", "bf_emma", "bf_isabella", "bf_alice", "bf_lily"],
    "male": ["am_adam", "am_michael", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_onyx", "am_puck", "bm_george", "bm_lewis",
             "bm_daniel", "bm_fable"],
}
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
