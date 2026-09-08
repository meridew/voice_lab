# Voice Lab

Local audio lab for Supreme Perilous voices and sound design: one page, one waveform. Tag the take Voice
or SFX, record or import it, crop it, convert it to a synthetic character voice, add effects that run live
while it plays, render, and export Opus for the game or MP3 for sharing. Originals and augmented clips save
themselves into a library you can filter by type, stage, voice, mode and effects; a second page browses that
library to play, rename, re-tag, export or delete. Nothing leaves the laptop after the one-time model download.

Runs on the CPU inside WSL2 (Ubuntu 24.04, ARM64). The Snapdragon has no CUDA, so this is offline
conversion, not real-time: measured about 9x real time at 15 diffusion steps (a 7 s take converts in
a minute once the models are warm); time scales with the step count, so use 8-10 steps for drafts.

## Layout

```
app/server.py            FastAPI: the page, the JSON API (library, originals, convert jobs, renders, voices, exports), the audio files
app/jobs.py              the model work, run in one long-lived worker process so the server keeps answering
app/static/              the lab page: index.html (markup), app.js (the flow), editor.js (waveform), effects.js (Web Audio chain);
                         the library page: library.html, library.js; shared: list.js (filterable list), modal.js (list modal and
                         dialog), lab.js (shell, helpers), api.js, lab.css
app/voice_convert.py     Seed-VC v1 and v2 on the CPU, warm in the worker, with the ARM64 workarounds
app/tts.py               Kokoro reference voices
app/library.py           on-disk library: sources/ and library/renders (wav + json sidecars), library/voices; exports are streamed
patches/                 the two changes to the vendored Seed-VC (BigVGAN's anti-aliasing filter as a matmul; v2's generate takes a token budget)
docs/                    design notes (sound-design-surface.md: the research behind the effects)
scripts/setup.sh         one-time WSL2 setup (uv-managed Python 3.10, torch CPU, Seed-VC at a pinned commit plus the patch, deps); no sudo
scripts/run.sh           launch the server
scripts/check.sh         the verification kernel: ruff and the API in-process (no models, no UI)
scripts/convert-check.sh a real conversion against the running server, proving it keeps answering meanwhile
~/.cache/voice-lab/seed-vc   Seed-VC source and checkpoints, on the Linux filesystem (cloned and patched by setup; VOICE_LAB_VENDOR overrides)
```

## Setup and run

```bash
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/setup.sh
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/danie/vscode-workspace/voice-lab/scripts/run.sh
```

Then open http://localhost:7860 in a Windows browser. The first conversion downloads the Seed-VC
checkpoints from Hugging Face into `~/.cache/huggingface` inside WSL.

## Workflow

One library, two kinds of clip: **originals** (recordings and imports) and **augmented** (conversions and
renders), plus reference **voices**. Every clip carries its type (Voice or SFX), and augmented clips carry the
voice and mode or the effects that made them. The page, top to bottom:

1. **Voice / SFX** switch: tags everything saved from here on; SFX hides the voice parts.
2. **Voice** select with a play button and a plus that makes a new reference voice with Kokoro, and an
   optional **Name**.
3. **The waveform**: record, play, crop the selection, import a file, or open the **library** (search, a filter
   per facet: Type, Stage, Voice, Mode, Effects; sorting; a bin on each row). The sliders icon beside record
   opens the microphone: input device and processing switches, remembered in the browser (see Microphone below).
   A take saves itself as an original the moment it lands; a crop updates it.
4. **Convert** (voices): *Timbre* is the v1 F0 model, which keeps the melody of your delivery and moves its
   level onto the reference's, the reliable male-to-female path (real 123-139 Hz voice notes landed at 207-215
   Hz against a 209 Hz reference). *Emotion* is v2, which takes the reference's accent and emotion too, follows
   its range loosely, and is slower. Quality is the diffusion step count; Pitch nudges the level in semitones.
   The bar follows the server's estimate; the result replaces the take in the waveform and saves itself.
5. **Effects**: add cards that run live while the waveform plays (pitch as tape speed, low-pass, high-pass,
   telephone, gain, distortion, hard clip, wavefolder, bitcrush, ring mod, compressor, delay, reverb, chorus,
   phaser, tremolo), each with bypass, move and remove. Reverse sits beside crop in the waveform's own row.
   **Render** bakes the chain into the next step and saves it.
6. **Undo** walks back through render, conversion, take. **Export** downloads what is showing as Opus 48 kbps
   for the game (Chromium decodes it natively, about 20 KB per line) or MP3 128 kbps for sharing, 48 kHz
   mono, peak-normalised to −1 dBFS, encoded on demand; WAV masters stay in the library.

The **Library** page (the list icon in the header) shows every original, augmented clip and reference voice with the
same search, filters and sorts as the picker. On each row: play, click the name to rename, click the Type tag to flip
Voice and SFX, export for the game or for sharing, delete.

Voices are synthesised with Kokoro (nobody's real voice): `bf_alice` and
`af_jessica` read at about 213 Hz, `af_bella` 209, `af_sarah` 204, `af_heart` 202; the breathy `af_nicole` and
`af_sky` sit near 157 Hz. Variation at play time (a little random pitch and gain per trigger) is the game
engine's job, as in Wwise and FMOD, so the lab does not generate variation batches.

## Effects

The chain runs in the browser with Web Audio (`app/static/effects.js`): each effect builds the same node graph
for live playback and for the offline render, so what you hear is what gets saved. Pitch is playback rate,
tape-style. The Python sound-design vocabulary researched in `docs/sound-design-surface.md` (layering,
granular, spectral freeze, paulstretch, tape wobble, envelope filter, cleanup) was implemented on pedalboard
and numpy, then removed from the tree in the 2026-09-08 cleanup as unused by the page; it is in git history
for when the chain needs more than Web Audio nodes can do.

## Microphone

Everything is off by default: the browser's call-oriented processing thins a voice out. What each switch reaches,
read from Chromium's Windows capture code (`media/audio/win/audio_low_latency_input_win.cc`):

- **Noise suppression** and **auto gain** are the browser's own WebRTC processing, applied in software.
- **Echo cancellation** is the one that reaches the laptop. Chromium opens the Windows microphone in raw mode, which
  bypasses every system effect, unless echo cancellation is requested, when it uses a normal stream "so that Voice
  Clarity can kick in". Windows applies its effects as a package (echo cancellation, noise suppression and gain
  together), and on this Snapdragon that package includes Windows Studio Effects **Voice Focus** when it is on in
  Quick Settings > Studio effects > Microphone (or Settings > System > Sound > the microphone > Voice focus). To put
  every capture through the system chain instead, start the browser with `--disable-features=WASAPIRawAudioCapture`.
- **Voice isolation** is in the spec and Chromium accepts it, but it only acts on ChromeOS devices so far.

When recording starts the toast names the device and the processing the browser reports as actually applied, and
the take's sidecar keeps the same `mic` record, so takes made with different settings can be compared later.

## Measured on this laptop (Snapdragon X2 Elite Extreme, CPU only, 2026-09-07)

A 6.8 s male stand-in take (Kokoro `am_adam`, median pitch 103 Hz) converted to a Kokoro `af_heart`
reference (198 Hz) at 15 diffusion steps, models warm unless noted:

| Path | oneDNN off | oneDNN on (current default) | Output |
| --- | --- | --- | --- |
| v1 base, cold (first conversion, loads models) | 74 s | 48 s | 22.05 kHz, ~200 Hz |
| v1 base, warm | 58 s | 36 s | 22.05 kHz, ~200 Hz |
| v2, style off, warm | 49 s | 34 s | 22.05 kHz, ~200 Hz |
| v2, accent and emotion, warm | 81 s | 73 s | 22.05 kHz, ~190 Hz |
| v1 F0 model, auto-match, 0 st (fresh process, oneDNN off) | 86 s | | 44.1 kHz, 201 Hz |

Those were the numbers before the performance pass. A profile of a warm F0-model conversion then showed most of
its fixed cost inside BigVGAN's anti-aliasing filter: a depthwise conv1d that crashes oneDNN's aarch64 JIT and,
bypassed onto the native kernel, cost about 10 s per conversion. `patches/seed-vc.patch` rewrites it as unfold
plus matmul (same taps on every channel, identical output, no convolution kernel), which took a warm conversion
of a 1.3 s take at 8 steps from 29 s to 12 s and a cold one from 39 s to 26 s. What remains is the diffusion
itself, about 1.15 s per step, driven by the reference voice's length (capped at 12 s) more than the take's.
v2's autoregressive stage stays on the native kernels (one run under oneDNN produced a runaway silent output),
its generation is budgeted from the take's length, and retries sample more conservatively. Set
`VOICE_LAB_ONEDNN=0` to revert to all-native kernels. Cheaper knobs in order: fewer diffusion steps, a shorter
reference voice, then (untried) bfloat16 autocast on the Oryon cores or the Seed-VC "tiny" real-time checkpoint.

## ARM64 notes (what setup.sh works around)

- No sudo in WSL, so uv supplies Python 3.10 and every dependency is a wheel.
- `soundfile` 0.12.1 has no bundled libsndfile on aarch64; 0.13 does.
- Seed-VC pins CUDA nightlies and float16; CPU wheels are installed instead, the in-process wrapper
  gets a CPU-safe autocast, and `inference_v2.py` is patched to float32 on CPU.
- oneDNN's aarch64 JIT fails on BigVGAN's depthwise anti-aliasing conv1d ("Xbyak ... illegal immediate
  parameter"); that one filter is patched to bypass oneDNN, everything else keeps the fast kernels.
- Seed-VC v2 only hands its result back through its MP3 streaming path, so an ffmpeg (imageio-ffmpeg's
  static binary) is put on PATH; v2 is kept warm in-process because reloading its 1.2 GB of checkpoints over
  the Windows filesystem cost more than a conversion.
- Invoke `wsl` from PowerShell, not Git Bash, which rewrites `/mnt/c` paths.

## Notes

- Models and libraries: Seed-VC (GPL-3), Kokoro-82M (Apache-2), pedalboard (GPL-3), FastAPI and uvicorn (MIT/BSD),
  WaveSurfer.js (BSD-3), Lucide (ISC).
- Cloning a specific real person's voice needs their consent; the intended use is synthetic voices.
- Uploads of mp3/webm need ffmpeg; `imageio-ffmpeg` provides a static binary when its wheel is available.
