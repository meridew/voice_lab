# Voice Lab

Local audio lab for Supreme Perilous voices and sound design. Record or import a take, convert it to a
synthetic character voice, chain DSP effects, and keep everything in a library of presets and renders.
Nothing leaves the laptop after the one-time model download.

Runs on the CPU inside WSL2 (Ubuntu 24.04, ARM64). The Snapdragon has no CUDA, so this is offline
conversion, not real-time: measured about 9x real time at 15 diffusion steps (a 7 s take converts in
a minute once the models are warm); time scales with the step count, so use 8-10 steps for drafts.

## Layout

```
app/main.py              Gradio UI (Sources, Voices, Convert, Effects chain, Library)
app/effects/             effect registry: voice_convert.py (Seed-VC v1/v2), tts.py (Kokoro), dsp.py (pedalboard + numpy)
app/library.py           on-disk library: sources/, library/voices, library/presets, library/renders (+ json sidecars)
scripts/setup.sh         one-time WSL2 setup (uv-managed Python 3.10, torch CPU, Seed-VC clone, deps); no sudo
scripts/run.sh           launch the UI
vendor/seed-vc           Seed-VC source (cloned by setup, git-ignored)
```

## Setup and run

```bash
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/setup.sh
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/run.sh
```

Then open http://localhost:7860 in a Windows browser. The first conversion downloads the Seed-VC
checkpoints from Hugging Face into `~/.cache/huggingface` inside WSL.

## Workflow

1. **Voices**: synthesise a reference voice with Kokoro (a female `af_*`/`bf_*` voice, 10-20 seconds of
   text). This becomes the character; it is nobody's real voice.
2. **Sources**: record a take in the browser or upload a wav. Record dry and close, and deliver lines
   lighter and higher than your natural voice: the model keeps your performance.
3. **Convert**: pick the take and the voice. v1 base model re-synthesises pitch in the target's range;
   tick *keep my pitch contour* to use the F0 model with an explicit semitone shift (try 6-10). v2 also
   converts accent and emotion but is slower. Every conversion is saved as a render with a sidecar that
   records the exact chain and parameters.
4. **Effects chain**: build a chain of effects on any source, render or voice, and save it as a preset.
   The DSP effects (bitcrush, sample-rate reduce, wavefolder, ring modulator, filters, delay, reverb,
   telephone codec, ...) are the start of the sound-design side: record real-world sounds and mangle
   them into analogue-flavoured digital synth material.
5. **Library**: play, annotate and delete renders.

## Effects

An effect is one function decorated with `@effect(name, label, category, params)` in `app/effects/`
that maps `(audio, sr, **params) -> (audio, sr)`. Chains are JSON lists of `{name, params}`, so
presets are plain files and renders are reproducible.

## Measured on this laptop (Snapdragon X2 Elite Extreme, CPU only, 2026-09-07)

A 6.8 s male stand-in take (Kokoro `am_adam`, median pitch 103 Hz) converted to a Kokoro `af_heart`
reference (198 Hz) at 15 diffusion steps:

| Path | Output | Median pitch | Time |
| --- | --- | --- | --- |
| v1 base, cold (first conversion in the app, loads models) | 22.05 kHz | 203 Hz | 82 s |
| v1 base, warm | 22.05 kHz | 199 Hz | 61 s |
| v1 F0 model, auto-match, 0 st (fresh process) | 44.1 kHz | 201 Hz | 86 s |

So roughly 9x real time at 15 steps with the models warm. Cheaper knobs in order: fewer diffusion
steps, shorter takes, then (untried) bfloat16 autocast on the Oryon cores or the Seed-VC "tiny"
real-time checkpoint at lower quality. See `scripts/smoke.sh` and `scripts/warmprobe.sh`.

## ARM64 notes (what setup.sh works around)

- No sudo in WSL, so uv supplies Python 3.10 and every dependency is a wheel.
- `soundfile` 0.12.1 has no bundled libsndfile on aarch64; 0.13 does.
- Seed-VC pins CUDA nightlies and float16; CPU wheels are installed instead, the in-process wrapper
  gets a CPU-safe autocast, and `inference_v2.py` is patched to float32 on CPU.
- oneDNN's aarch64 JIT fails inside these models ("Xbyak ... illegal immediate parameter"); the
  mkldnn backend is disabled so PyTorch's native kernels run.
- Invoke `wsl` from PowerShell, not Git Bash, which rewrites `/mnt/c` paths.

## Notes

- Models: Seed-VC (GPL-3), Kokoro-82M (Apache-2), pedalboard (GPL-3), Gradio (Apache-2).
- Cloning a specific real person's voice needs their consent; the intended use is synthetic voices.
- Uploads of mp3/webm need ffmpeg; `imageio-ffmpeg` provides a static binary when its wheel is available.
