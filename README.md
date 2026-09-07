# Voice Lab

Local audio lab for Supreme Perilous voices and sound design. Record or import a take, convert it to a
synthetic character voice, chain DSP effects, and keep everything in a library of presets and renders.
Nothing leaves the laptop after the one-time model download.

Runs on the CPU inside WSL2 (Ubuntu 24.04, ARM64). The Snapdragon has no CUDA, so this is offline
conversion, not real-time: expect roughly a minute of compute per ten seconds of audio at 25 diffusion
steps, and a few seconds at 10 steps for drafts.

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

## Notes

- Models: Seed-VC (GPL-3), Kokoro-82M (Apache-2), pedalboard (GPL-3), Gradio (Apache-2).
- Cloning a specific real person's voice needs their consent; the intended use is synthetic voices.
- Uploads of mp3/webm need ffmpeg; `imageio-ffmpeg` provides a static binary when its wheel is available.
