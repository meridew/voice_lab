# Sound-design surface: what we actually need

Research note, 2026-09-07. Question: when Voice Lab is also used to turn real-world recordings into
game sound effects, what surface does the app need, and what can we leave out?

## How the work is actually done

Practitioner sources agree on a short recipe (see Sources):

1. **Record raw material**, ideally at a high sample rate so it survives being pitched down an octave
   or two. Dedicated recorders or a phone app are the norm; the material is imported, not captured in a DAW.
2. **Layer two to four sources**: a transient, a body, a tail. "Duplicate and pitch the copy down an
   octave" is the single most common move for weight.
3. **Process the stack**: pitch shift, EQ, saturation or distortion, compression and limiting, transient
   shaping, reverb or convolution for space, granular or time stretch for texture, reverse for whooshes.
4. **Bounce and re-process**: the result is resampled back in as new source material and mangled again.
5. **Variation is the engine's job at playback**: Wwise and FMOD pick one of 5 to 10 files and randomise
   pitch by about ±5 to 10 % and volume by about ±3 dB per play. Designers hand-make a few variants; they
   do not generate hundreds offline.
6. **Export** masters per category, peak- or loudness-normalised, mono unless the sound is a bed.

The tools people reach for split into DAWs (timeline, effect chain, bounce) and sample managers (audition
fast, clip, tag, export). Nobody's core loop needs a timeline for one-shot effects: it is input, chain,
listen, keep.

## What that implies for our app

The existing Effects tab is already the right shape. Sound design changes its tempo, not its structure:
DSP is instant, so the loop must be tweak → hear with no button press, and the result must feed back in.

### Minimal surface (v1)

| Step | Surface | Status |
|---|---|---|
| Input | Record, import, or pick from the library; crop by selecting on the waveform. | Done |
| Chain | Ordered effect cards, each with a **bypass** toggle; **auto-apply on change** when the chain has no voice-conversion step, Apply button otherwise. | Bypass and auto-apply to add |
| Layering | Two chain steps, not a timeline: **Layer** (mix another library sound: gain, offset, pitch) and **Sub** (duplicate the signal, pitch it down N semitones, mix under). | Two effects to add |
| Result | Player, then **Keep** (label + tag) and **Bounce** (use this result as the input). | Bounce and tag to add |
| Library | Tag column and filter; **Export** to a folder at 48 kHz mono, peak-normalised to −1 dBFS: Opus for the game, MP3 for sharing, WAV as the master. | Tag and export to add |

Recording in the browser stays for quick sketches only. Browser microphone capture is Opus-compressed,
which is fine for voice lines and poor for material that will be pitched down two octaves. Real-world
sounds should come in as WAV from a phone recorder app, so the import path matters more than the recorder.

### Effect vocabulary (buy first, glue only)

Already installed and covering most of the recipe: **pedalboard** (PitchShift via Rubber Band, Bitcrush,
Chorus, Phaser, Delay, Reverb, Distortion, Clipping, Compressor, Limiter, NoiseGate, Ladder/shelf/peak
filters, Resample, Invert, **Convolution** from any file or array, and **Mix/Chain** for parallel paths),
**librosa** (time stretch, resampling, analysis), **scipy**.

Add, all pure Python or with Linux aarch64 wheels:

- **noisereduce** (MIT): cleanup for field recordings before mangling.
- **pyloudnorm** (MIT): LUFS measurement and normalisation for consistent exports.
- **soxr**: high-quality resampling for the export step.
- **audiomentations** (MIT, 43 transforms with min/max ranges and a probability): only if we ever want
  offline variation batches; not needed for v1 because the engine will randomise at playback.

Write ourselves, each about 30 lines of numpy: granular cloud, spectral freeze, paulstretch-style extreme
stretch, tape wobble (LFO on a short delay line), envelope-follower filter, ring modulation (exists).

Not available without compiling on this laptop: praat-parselmouth and pyworld (formant shifting), pyo,
python-stretch. VST3 hosting through pedalboard works on Linux but ARM64 Linux VST3 builds barely exist.

### Non-goals

No timeline or multitrack, no automation curves, no VST hosting, no real-time streaming, no similarity
search across the library, no offline variation generator, no spectrogram view in v1, no formant shifting,
no NPU path. Each is a real feature in a real tool; none is on the critical path of input → chain → keep.

### The game side

The game has no audio playback yet (capability CAP-AUDIO-PRESENTATION is planned for a later horizon), so
the export format is ours to choose. Web Audio decodes WAV directly; runtime pitch and gain randomisation
is a two-line `playbackRate` and gain jitter when playback lands, which is why the app does not generate
variations.

## Status

2026-09-08: the page is one waveform with a Voice/SFX switch; effects run live in Web Audio (pitch as tape
speed, filters, gain, distortion, delay, reverb, tremolo) and render offline in the browser; undo walks back
through take, conversion and render; the library modal filters by type, stage, voice, mode and effects. The
Python vocabulary above (layering, granular, freeze, paulstretch, wobble, envelope filter, cleanup) was
implemented in `app/effects/sound.py` and removed from the tree the same day as unused by the page; it is in
git history, the pool to draw from when the live chain needs more than Web Audio nodes can do.

## Sources

- SFX Engine, Game Sound Effects Masterclass: https://sfxengine.com/blog/game-sound-effects
- Generalist Programmer, Game Sound Design guide: https://generalistprogrammer.com/tutorials/game-sound-design-complete-audio-production-guide-2025
- Gamine, Creating Game Sound Effects from Recording to Implementation: https://gamineai.com/blog/creating-game-sound-effects-from-recording-to-implementation
- Pixflow, Sound Effects Layering: https://pixflow.net/blog/sound-effects-layering/
- David Dumais, Foley-to-Explosion workflow in Reaper: https://www.daviddumaisaudio.com/turn-simple-foley-into-pro-explosion-sfx/
- A Sound Effect, AK74 library notes on 192 kHz and pitching down: https://www.asoundeffect.com/sound-library/ak74/
- Javier Zúmer, Differences between FMOD and Wwise: https://javierzumer.com/blog/2022/8/28/differences-between-fmod-amp-wwise-part-3
- Pedalboard reference: https://spotify.github.io/pedalboard/reference/pedalboard.html
- audiomentations: https://iver56.github.io/audiomentations/
- Gradio Audio component: https://www.gradio.app/docs/gradio/audio
- PyPI wheel availability checked 2026-09-07 for linux aarch64 (pedalboard, soxr present; parselmouth, pyworld, pyo, python-stretch absent; noisereduce, pyloudnorm, audiomentations, paulstretch pure Python).
