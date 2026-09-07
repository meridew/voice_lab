"""DSP effects: Spotify's pedalboard for the classic processors, numpy for the odd ones.

These are the seeds of the sound-design side: record a real-world sound, then fold, crush, ring
modulate and filter it into something that reads as an analogue-flavoured digital synth.
"""
from __future__ import annotations

import numpy as np
import pedalboard as pb

from . import Param, effect
from audio import peak_normalize


def _board(audio, sr, *plugins):
    out = pb.Pedalboard(list(plugins))(np.asarray(audio, dtype=np.float32)[None, :], sr)
    return out[0].astype(np.float32), sr


@effect("pitch_shift", "Pitch shift", "dsp", [Param("semitones", "Semitones", "float", 0.0, -24, 24, 0.5)],
        "Formant-agnostic pitch shift. For voices use the conversion effect instead; this is for sounds.")
def pitch_shift(audio, sr, semitones=0.0):
    return _board(audio, sr, pb.PitchShift(semitones=float(semitones)))


@effect("gain", "Gain", "dsp", [Param("db", "Gain (dB)", "float", 0.0, -40, 24, 0.5)])
def gain(audio, sr, db=0.0):
    return _board(audio, sr, pb.Gain(gain_db=float(db)))


@effect("distortion", "Distortion", "dsp", [Param("drive_db", "Drive (dB)", "float", 12.0, 0, 60, 1)])
def distortion(audio, sr, drive_db=12.0):
    return _board(audio, sr, pb.Distortion(drive_db=float(drive_db)))


@effect("clip", "Hard clip", "dsp", [Param("threshold_db", "Threshold (dB)", "float", -6.0, -40, 0, 0.5)])
def clip(audio, sr, threshold_db=-6.0):
    return _board(audio, sr, pb.Clipping(threshold_db=float(threshold_db)))


@effect("bitcrush", "Bitcrush", "dsp", [Param("bits", "Bit depth", "float", 8.0, 2, 16, 0.5)])
def bitcrush(audio, sr, bits=8.0):
    return _board(audio, sr, pb.Bitcrush(bit_depth=float(bits)))


@effect("lofi_resample", "Sample-rate reduce", "dsp", [Param("rate", "Internal rate (Hz)", "int", 8000, 1000, 44100, 500)],
        "Resamples down and back up: aliasing and band-limiting, the digital grit.")
def lofi_resample(audio, sr, rate=8000):
    return _board(audio, sr, pb.Resample(target_sample_rate=float(rate), quality=pb.Resample.Quality.ZeroOrderHold))


@effect("lowpass", "Low-pass", "dsp", [Param("cutoff", "Cutoff (Hz)", "float", 4000.0, 50, 20000, 50)])
def lowpass(audio, sr, cutoff=4000.0):
    return _board(audio, sr, pb.LowpassFilter(cutoff_frequency_hz=float(cutoff)))


@effect("highpass", "High-pass", "dsp", [Param("cutoff", "Cutoff (Hz)", "float", 120.0, 20, 8000, 10)])
def highpass(audio, sr, cutoff=120.0):
    return _board(audio, sr, pb.HighpassFilter(cutoff_frequency_hz=float(cutoff)))


@effect("chorus", "Chorus", "dsp", [Param("rate", "Rate (Hz)", "float", 1.0, 0.05, 10, 0.05), Param("depth", "Depth", "float", 0.25, 0, 1, 0.01),
                                    Param("mix", "Mix", "float", 0.5, 0, 1, 0.01)])
def chorus(audio, sr, rate=1.0, depth=0.25, mix=0.5):
    return _board(audio, sr, pb.Chorus(rate_hz=float(rate), depth=float(depth), mix=float(mix)))


@effect("phaser", "Phaser", "dsp", [Param("rate", "Rate (Hz)", "float", 1.0, 0.05, 10, 0.05), Param("depth", "Depth", "float", 0.5, 0, 1, 0.01),
                                    Param("mix", "Mix", "float", 0.5, 0, 1, 0.01)])
def phaser(audio, sr, rate=1.0, depth=0.5, mix=0.5):
    return _board(audio, sr, pb.Phaser(rate_hz=float(rate), depth=float(depth), mix=float(mix)))


@effect("delay", "Delay", "dsp", [Param("seconds", "Time (s)", "float", 0.25, 0.01, 2, 0.01), Param("feedback", "Feedback", "float", 0.3, 0, 0.95, 0.01),
                                  Param("mix", "Mix", "float", 0.3, 0, 1, 0.01)])
def delay(audio, sr, seconds=0.25, feedback=0.3, mix=0.3):
    return _board(audio, sr, pb.Delay(delay_seconds=float(seconds), feedback=float(feedback), mix=float(mix)))


@effect("reverb", "Reverb", "dsp", [Param("room", "Room size", "float", 0.5, 0, 1, 0.01), Param("damping", "Damping", "float", 0.5, 0, 1, 0.01),
                                    Param("wet", "Wet", "float", 0.3, 0, 1, 0.01), Param("dry", "Dry", "float", 0.7, 0, 1, 0.01)])
def reverb(audio, sr, room=0.5, damping=0.5, wet=0.3, dry=0.7):
    return _board(audio, sr, pb.Reverb(room_size=float(room), damping=float(damping), wet_level=float(wet), dry_level=float(dry)))


@effect("compressor", "Compressor", "dsp", [Param("threshold_db", "Threshold (dB)", "float", -18.0, -60, 0, 1), Param("ratio", "Ratio", "float", 4.0, 1, 20, 0.5)])
def compressor(audio, sr, threshold_db=-18.0, ratio=4.0):
    return _board(audio, sr, pb.Compressor(threshold_db=float(threshold_db), ratio=float(ratio)))


@effect("phone", "Telephone codec", "dsp", [], "GSM full-rate codec: the crushed radio-voice sound.")
def phone(audio, sr):
    return _board(audio, sr, pb.GSMFullRateCompressor())


@effect("ring_mod", "Ring modulator", "dsp", [Param("hz", "Carrier (Hz)", "float", 60.0, 1, 2000, 1), Param("mix", "Mix", "float", 1.0, 0, 1, 0.01)],
        "Multiplies by a sine carrier: metallic, robotic, Dalek at low mix.")
def ring_mod(audio, sr, hz=60.0, mix=1.0):
    t = np.arange(len(audio), dtype=np.float32) / sr
    carrier = np.sin(2 * np.pi * float(hz) * t).astype(np.float32)
    return ((1 - mix) * audio + mix * audio * carrier).astype(np.float32), sr


@effect("tremolo", "Tremolo", "dsp", [Param("hz", "Rate (Hz)", "float", 5.0, 0.1, 50, 0.1), Param("depth", "Depth", "float", 0.6, 0, 1, 0.01)])
def tremolo(audio, sr, hz=5.0, depth=0.6):
    t = np.arange(len(audio), dtype=np.float32) / sr
    lfo = 1 - depth * 0.5 * (1 + np.sin(2 * np.pi * float(hz) * t))
    return (audio * lfo).astype(np.float32), sr


@effect("wavefold", "Wavefolder", "dsp", [Param("drive", "Drive", "float", 3.0, 1, 12, 0.1), Param("mix", "Mix", "float", 1.0, 0, 1, 0.01)],
        "Reflects the waveform back on itself above a threshold: the West-Coast synth snarl.")
def wavefold(audio, sr, drive=3.0, mix=1.0):
    x = audio * float(drive)
    folded = np.abs(((x + 1) % 4) - 2) - 1
    return ((1 - mix) * audio + mix * folded).astype(np.float32), sr


@effect("time_stretch", "Time stretch", "dsp", [Param("rate", "Rate (x)", "float", 1.0, 0.25, 4, 0.05)],
        "Speed change without pitch change (phase vocoder).")
def time_stretch(audio, sr, rate=1.0):
    import librosa
    return librosa.effects.time_stretch(np.asarray(audio, dtype=np.float32), rate=float(rate)), sr


@effect("reverse", "Reverse", "utility", [])
def reverse(audio, sr):
    return audio[::-1].copy(), sr


@effect("normalize", "Normalize", "utility", [Param("peak", "Peak", "float", 0.95, 0.1, 1, 0.01)])
def normalize(audio, sr, peak=0.95):
    return peak_normalize(audio, float(peak)), sr


@effect("trim_silence", "Trim silence", "utility", [Param("top_db", "Threshold (dB below peak)", "float", 40.0, 10, 80, 1)])
def trim_silence(audio, sr, top_db=40.0):
    import librosa
    trimmed, _ = librosa.effects.trim(np.asarray(audio, dtype=np.float32), top_db=float(top_db))
    return trimmed, sr


@effect("fade", "Fade in/out", "utility", [Param("in_ms", "Fade in (ms)", "float", 10.0, 0, 2000, 5), Param("out_ms", "Fade out (ms)", "float", 30.0, 0, 5000, 5)])
def fade(audio, sr, in_ms=10.0, out_ms=30.0):
    out = np.array(audio, dtype=np.float32, copy=True)
    n_in, n_out = int(sr * in_ms / 1000), int(sr * out_ms / 1000)
    if n_in > 0:
        out[:n_in] *= np.linspace(0, 1, min(n_in, len(out)), dtype=np.float32)
    if n_out > 0:
        out[-n_out:] *= np.linspace(1, 0, min(n_out, len(out)), dtype=np.float32)
    return out, sr
